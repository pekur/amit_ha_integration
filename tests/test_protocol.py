"""DB-Net response validation and mocked encrypted UDP exchanges.

Inner frames follow AMiT's published DB-Net specification. UDP envelopes are
synthetic and follow this repository's existing encoder, not a PLC capture.
"""
import asyncio
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_protocol(test_case):
    path = Path(__file__).resolve().parents[1] / "custom_components/amit/protocol.py"
    spec = importlib.util.spec_from_file_location("_amit_protocol_tests", path)
    protocol = importlib.util.module_from_spec(spec)
    context = patch.dict(sys.modules, {spec.name: protocol})
    context.start()
    test_case.addClassCleanup(context.stop)
    spec.loader.exec_module(protocol)
    return protocol


def long_frame(data=b"\x7b\x00", *, status=8, function=0x81, dest=31, src=4):
    body = bytes([dest, src, status, function]) + data
    frame = bytes([0x68, len(body), len(body), 0x68]) + body
    return with_fcs(frame)


def with_fcs(frame):
    # Independent one's-complement sum; avoid deriving test FCS via production.
    body = frame[4:] if frame[0] == 0x68 else frame[1:]
    total = sum(body)
    while total > 255:
        total = (total & 255) + (total >> 8)
    return frame + bytes([total, 0x16])


def short_frame(status=0, dest=31, src=4):
    return with_fcs(bytes([0x10, dest, src, status]))


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = load_protocol(cls)

    def test_known_specification_frames(self):
        # Concrete examples assembled from the published layout, including FCS.
        self.assertEqual(self.protocol._parse_response(bytes.fromhex("10 1f 04 00 23 16")),
                         (31, 4, 0, b""))
        self.assertEqual(self.protocol._parse_response(bytes.fromhex("68 06 06 68 1f 04 08 81 7b 00 28 16")),
                         (31, 4, 8, b"\x7b\x00"))

    def test_station_state_bits_do_not_change_response_status(self):
        self.assertEqual(self.protocol._parse_response(long_frame(status=0x28))[2], 8)

    def test_rejects_truncation_and_extra_bytes(self):
        for frame in (short_frame(), long_frame()):
            for size in range(len(frame)):
                with self.subTest(frame=frame.hex(), size=size):
                    with self.assertRaises(ValueError):
                        self.protocol._parse_response(frame[:size])
            with self.assertRaises(ValueError):
                self.protocol._parse_response(frame + b"\x00")

    def test_rejects_bad_checksum_terminator_and_length_header(self):
        for index in (1, 2, 3, 4, 8, -2, -1):
            with self.subTest(index=index):
                frame = bytearray(long_frame())
                frame[index] ^= 1
                with self.assertRaises(ValueError):
                    self.protocol._parse_response(bytes(frame))

    def test_rejects_request_frames_and_out_of_range_addresses(self):
        for frame in (long_frame(status=0x48), long_frame(dest=32), short_frame(src=255)):
            with self.subTest(frame=frame.hex()):
                with self.assertRaises(ValueError):
                    self.protocol._parse_response(frame)

    def test_checksum_carry_is_handled(self):
        value = b"\xff" * 26
        self.assertEqual(self.protocol._parse_response(long_frame(value))[3], value)


class ExchangeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = load_protocol(cls)

    def setUp(self):
        self.client = self.protocol.AMiTClient("plc.invalid", timeout=0.02)
        self.udp = self.protocol.AMiTProtocol()
        self.transport = Mock()
        self.udp.connection_made(self.transport)
        self.client._protocol = self.udp
        self.client._transport = self.transport
        self.client._connected = True
        self.variable = self.protocol.Variable("Sample", 4001, self.protocol.VarType.INT16)

    def envelope(self, frame, tid, key=0x12345678):
        header = bytearray(15)
        struct.pack_into("<IhI", header, 0, tid, 0, key)
        header[14] = len(frame) - 6
        packet = header + bytearray(frame)
        self.protocol._encrypt_msg(packet, self.client.password)
        # Receive-side UDP checksum remains undocumented and is not guessed.
        return bytes(packet)

    @staticmethod
    def sync(tid, key):
        return struct.pack("<IhI", tid, 0x1111, key)

    @staticmethod
    def tid(request):
        return struct.unpack_from("<I", request)[0]

    def deliver(self, packet):
        self.udp.datagram_received(packet, ("plc.invalid", 59))

    def assert_waiter_cleared(self):
        self.assertIsNone(self.udp._response_future)
        self.assertIsNone(self.udp._response_validator)

    async def test_reads_all_supported_scalar_types(self):
        for var_type, fmt, value in (
            (self.protocol.VarType.INT16, "<h", -123),
            (self.protocol.VarType.INT32, "<i", 123456),
            (self.protocol.VarType.FLOAT, "<f", 22.5),
        ):
            with self.subTest(var_type=var_type):
                self.transport.sendto.side_effect = lambda request: self.deliver(self.envelope(
                    long_frame(struct.pack(fmt, value)), self.tid(request),
                ))
                variable = self.protocol.Variable("Sample", 4001, var_type)
                self.assertEqual(await self.client.read_variable(variable), value)
                self.assertEqual(self.client._key, 0x12345678)
                self.assert_waiter_cleared()

    async def test_outgoing_read_matches_original_repository_wire_vector(self):
        # Captured from the encoder at HEAD aecbfa1, not a real PLC packet.
        expected = bytes.fromhex(
            "01 00 00 00 00 00 00 00 00 00 16 14 00 00 07 "
            "c9 07 07 68 a5 1f 4d 01 d4 a1 0f 22 c2"
        )
        self.transport.sendto.side_effect = lambda request: self.deliver(
            self.envelope(long_frame(), self.tid(request)),
        )
        await self.client.read_variable(self.variable)
        self.assertEqual(self.transport.sendto.call_args.args[0], expected)

    async def test_stale_datagram_cannot_satisfy_next_request_after_timeout(self):
        self.transport.sendto.side_effect = None
        with self.assertRaises(TimeoutError):
            await self.client.read_variable(self.variable)
        old_tid = self.tid(self.transport.sendto.call_args.args[0])

        def respond(request):
            self.deliver(self.envelope(long_frame(b"\x01\x00"), old_tid, key=111))
            self.assertFalse(self.udp._response_future.done())
            self.assertEqual(self.client._key, 0)
            self.deliver(self.envelope(long_frame(), self.tid(request), key=222))

        self.transport.sendto.side_effect = respond
        self.assertEqual(await self.client.read_variable(self.variable), 123)
        self.assertEqual(self.client._key, 222)
        self.assert_waiter_cleared()

    async def test_invalid_datagrams_are_ignored_before_valid_reply(self):
        def respond(request):
            tid = self.tid(request)
            good = self.envelope(long_frame(), tid)
            bad_checksum = bytearray(long_frame())
            bad_checksum[-2] ^= 1
            packets = [
                b"", good[:9], good[:14], good[:-1], good + b"\x00",
                self.envelope(bytes(bad_checksum), tid),
                self.envelope(long_frame(dest=30), tid),
                self.envelope(long_frame(src=3), tid),
                self.envelope(long_frame(function=0x83), tid),
                self.sync(tid + 1, 99),
            ]
            for packet in packets:
                self.deliver(packet)
                self.assertFalse(self.udp._response_future.done())
                self.assertEqual(self.client._key, 0)
            self.deliver(good)

        self.transport.sendto.side_effect = respond
        self.assertEqual(await self.client.read_variable(self.variable), 123)
        self.assert_waiter_cleared()

    async def test_invalid_only_reply_times_out_without_changing_key(self):
        self.transport.sendto.side_effect = lambda request: self.deliver(b"malformed")
        with self.assertRaises(TimeoutError):
            await self.client.read_variable(self.variable)
        self.assertEqual(self.client._key, 0)
        self.assert_waiter_cleared()

    async def test_sync_then_normal_reply_uses_new_key_and_transaction(self):
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                self.deliver(self.sync(self.tid(request), 1234))
            else:
                self.assertEqual(struct.unpack_from("<I", request, 6)[0], 1234)
                self.deliver(self.envelope(long_frame(), self.tid(request)))

        self.transport.sendto.side_effect = respond
        self.assertEqual(await self.client.read_variable(self.variable), 123)
        self.assertNotEqual(self.tid(requests[0]), self.tid(requests[1]))
        self.assert_waiter_cleared()

    async def test_repeated_syncs_are_bounded(self):
        self.transport.sendto.side_effect = lambda request: self.deliver(
            self.sync(self.tid(request), 1234),
        )
        with self.assertRaisesRegex(ConnectionError, "Too many"):
            await self.client.read_variable(self.variable)
        self.assertEqual(self.transport.sendto.call_count, self.protocol.MAX_KEY_SYNC_RETRIES + 1)
        self.assert_waiter_cleared()

    async def test_send_error_clears_and_cancels_waiter(self):
        futures = []

        def fail(request):
            futures.append(self.udp._response_future)
            raise OSError("send failed")

        self.transport.sendto.side_effect = fail
        with self.assertRaises(OSError):
            await self.client.read_variable(self.variable)
        self.assertTrue(futures[0].cancelled())
        self.assert_waiter_cleared()

    async def test_cancellation_clears_waiter_and_releases_request_lock(self):
        sent = asyncio.Event()
        self.transport.sendto.side_effect = lambda request: sent.set()
        task = asyncio.create_task(self.client.read_variable(self.variable))
        await sent.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_waiter_cleared()
        self.transport.sendto.side_effect = lambda request: self.deliver(
            self.envelope(long_frame(), self.tid(request)),
        )
        self.assertEqual(await self.client.read_variable(self.variable), 123)

    async def test_disconnect_and_connection_loss_wake_waiter(self):
        for disconnect in (True, False):
            with self.subTest(disconnect=disconnect):
                self.setUp()
                sent = asyncio.Event()
                self.transport.sendto.side_effect = lambda request: sent.set()
                task = asyncio.create_task(self.client.read_variable(self.variable))
                await sent.wait()
                if disconnect:
                    await self.client.disconnect()
                else:
                    self.udp.connection_lost(None)
                with self.assertRaises(ConnectionError):
                    await task
                self.assert_waiter_cleared()

    async def test_concurrent_requests_stay_serialized(self):
        requests = []
        sent = asyncio.Event()

        def send(request):
            requests.append(request)
            sent.set()

        self.transport.sendto.side_effect = send
        first = asyncio.create_task(self.client.read_variable(self.variable))
        await sent.wait()
        second = asyncio.create_task(self.client.read_variable(self.variable))
        await asyncio.sleep(0)
        self.assertEqual(len(requests), 1)
        sent.clear()
        self.deliver(self.envelope(long_frame(), self.tid(requests[0])))
        await sent.wait()
        self.assertEqual(len(requests), 2)
        self.deliver(self.envelope(long_frame(b"\x7c\x00"), self.tid(requests[1])))
        self.assertEqual(await asyncio.gather(first, second), [123, 124])
        self.assert_waiter_cleared()

    async def test_transaction_counter_wraps_without_reusing_zero(self):
        self.client._transaction_id = 0xFFFFFFFF
        self.transport.sendto.side_effect = lambda request: self.deliver(
            self.envelope(long_frame(), self.tid(request)),
        )
        await self.client.read_variable(self.variable)
        await self.client.read_variable(self.variable)
        self.assertEqual([self.tid(call.args[0]) for call in self.transport.sendto.call_args_list],
                         [0xFFFFFFFF, 1])

    async def test_read_rejects_error_statuses_and_wrong_value_sizes(self):
        for response in (
            short_frame(status=1), short_frame(status=2),
            long_frame(status=1), long_frame(status=3),
            long_frame(b"\x01"), long_frame(b"\x01\x00\x00\x00"),
        ):
            with self.subTest(response=response.hex()):
                self.client._send_receive = AsyncMock(return_value=response)
                with self.assertRaises(RuntimeError):
                    await self.client.read_variable(self.variable)

    async def test_connection_probe_accepts_valid_replies_without_assuming_variable_type(self):
        for response in (short_frame(status=2), long_frame(struct.pack("<f", 22.5))):
            with self.subTest(response=response.hex()):
                self.client._send_receive = AsyncMock(return_value=response)
                self.assertTrue(await self.client.test_connection())

    async def test_connection_probe_rejects_invalid_or_unrelated_frames(self):
        for response in (b"bad", long_frame(dest=30), long_frame(function=0x83)):
            with self.subTest(response=response.hex()):
                self.client._send_receive = AsyncMock(return_value=response)
                with self.assertLogs(self.protocol.__name__, level="ERROR"):
                    self.assertFalse(await self.client.test_connection())

    async def test_connection_probe_timeout_is_not_reachability(self):
        self.client._send_receive = AsyncMock(side_effect=TimeoutError("offline"))
        with self.assertLogs(self.protocol.__name__, level="ERROR"):
            self.assertFalse(await self.client.test_connection())

    async def test_connection_probe_cancellation_propagates(self):
        self.client._send_receive = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.client.test_connection()

    async def test_mocked_write_accepts_ack_and_returns_false_for_error(self):
        # All writes end at this AsyncMock; no transport is used.
        self.client._send_receive = AsyncMock(return_value=short_frame())
        self.assertTrue(await self.client.write_variable(self.variable, 1))
        self.client._send_receive.return_value = short_frame(status=2)
        self.assertFalse(await self.client.write_variable(self.variable, 1))

    async def test_readonly_write_never_reaches_transport(self):
        self.variable.writable = False
        with self.assertRaises(ValueError):
            await self.client.write_variable(self.variable, 1)
        self.transport.sendto.assert_not_called()

    async def test_matrix_aliases_and_unknown_types_cannot_use_scalar_io(self):
        for code, old_name, new_name, label in (
            (3, "ARRAY", "MATRIX_INT16", "Matrix Integer"),
            (4, "TIME_ARRAY", "MATRIX_INT32", "Matrix Long"),
            (5, "STRUCTURE", "MATRIX_FLOAT", "Matrix Float"),
        ):
            old_type = getattr(self.protocol.VarType, old_name)
            new_type = getattr(self.protocol.VarType, new_name)
            self.assertIs(old_type, new_type)
            self.assertEqual(int(new_type), code)
            self.assertEqual(self.protocol.Variable("Matrix", 1, new_type).type_name, label)
        for code in range(3, 8):
            with self.subTest(code=code):
                variable = self.protocol.Variable("Unsupported", 4001, code)
                self.assertFalse(variable.is_readable())
                with self.assertRaises(ValueError):
                    await self.client.read_variable(variable)
                with self.assertRaises(ValueError):
                    await self.client.write_variable(variable, 1)
        self.transport.sendto.assert_not_called()

    def test_legacy_positional_variable_arguments_keep_their_meaning(self):
        variable = self.protocol.Variable("Sample", 4001, self.protocol.VarType.INT16, 123, False)
        self.assertEqual(variable.value, 123)
        self.assertFalse(variable.writable)
        self.assertIsNone(variable.rows)
        self.assertIsNone(variable.metadata_version)

    async def test_matrix_elements_and_windows_use_typed_reads_and_row_order(self):
        for typ, fmt, numbers in (
            (3, 'h', [-32768, -1, 0, 32767, 12, -12]),
            (4, 'i', [-2147483648, -1, 0, 2147483647, 123456, -123456]),
            (5, 'f', [-2.5, 0, 0.25, 32.5, 1.5, -1.5]),
        ):
            with self.subTest(typ=typ):
                variable = self.protocol.Variable("Matrix", 0x1234, typ, writable=False,
                                                  rows=5, cols=7)
                for block in (False, True):
                    values = numbers if block else numbers[:1]
                    self.transport.sendto.side_effect = lambda request: self.deliver(self.envelope(
                        long_frame(struct.pack('<' + fmt * len(values), *values)), self.tid(request),
                    ))
                    if block:
                        result = await self.client.read_matrix_block(variable, 1, 2, 2, 3)
                        self.assertEqual(result, [numbers[:3], numbers[3:]])
                    else:
                        self.assertEqual(await self.client.read_matrix_element(variable, 4, 6), numbers[0])
                    # Decrypt the sent packet and compare to an independently
                    # assembled layout/FCS, including nonzero row/column offsets.
                    packet = bytearray(self.transport.sendto.call_args.args[0])
                    self.protocol._encrypt_msg(packet, self.client.password)
                    expected = (bytes.fromhex('68 0f 0f 68 04 1f 4d 01')
                                + bytes([0x20 + typ - 3])
                                + bytes.fromhex('34 12 01 00 02 00 02 00 03 00')) if block else (
                                    bytes.fromhex('68 0b 0b 68 04 1f 4d 01')
                                    + bytes([0x10 + typ - 3])
                                    + bytes.fromhex('34 12 04 00 06 00'))
                    self.assertEqual(bytes(packet[15:]), with_fcs(expected))
                    self.assert_waiter_cleared()

    async def test_matrix_block_accepts_exact_protocol_limits(self):
        for typ, fmt, count in ((3, 'h', 120), (4, 'i', 60), (5, 'f', 60)):
            with self.subTest(typ=typ):
                variable = self.protocol.Variable("Matrix", 65535, typ, rows=1, cols=65535)
                self.transport.sendto.side_effect = lambda request: self.deliver(self.envelope(
                    long_frame(struct.pack('<' + fmt * count, *range(count))), self.tid(request),
                ))
                self.assertEqual(await self.client.read_matrix_block(variable, 0, 65535-count, 1, count),
                                 [list(range(count))])

    async def test_invalid_matrix_requests_never_reach_transport(self):
        variable = self.protocol.Variable("Matrix", 4001, 3, rows=20, cols=20)
        for row, col, rows, cols in (
            (-1, 0, 1, 1), (0, -1, 1, 1), (20, 0, 1, 1), (0, 20, 1, 1),
            (19, 0, 2, 1), (0, 19, 1, 2), (0, 0, 0, 1), (0, 0, 1, 0),
            (0, 0, -1, 1), (0, 0, 11, 11), (0, 0, True, 1),
            (True, 0, 1, 1), (0, False, 1, 1), (0, 0, 1, 1.0), ("0", 0, 1, 1),
        ):
            with self.subTest(window=(row, col, rows, cols)):
                with self.assertRaises(ValueError):
                    await self.client.read_matrix_block(variable, row, col, rows, cols)
        for kwargs in (
            {"var_type": 0}, {"var_type": 1}, {"var_type": 2}, {"var_type": 6}, {"var_type": 7},
            {"rows": None}, {"cols": 0}, {"rows": 65536}, {"cols": True},
            {"wid": -1}, {"wid": 65536}, {"wid": True},
        ):
            bad = self.protocol.Variable(**{
                "name": "Bad", "wid": 4001, "var_type": 3, "rows": 20, "cols": 20, **kwargs,
            })
            with self.subTest(metadata=kwargs):
                with self.assertRaises(ValueError):
                    await self.client.read_matrix_element(bad, 0, 0)
        for typ in (4, 5):
            variable.var_type = typ
            with self.assertRaises(ValueError):
                await self.client.read_matrix_block(variable, 0, 0, 1, 61)
        self.transport.sendto.assert_not_called()

    async def test_matrix_errors_and_wrong_lengths_do_not_return_partial_values(self):
        variable = self.protocol.Variable("Matrix", 4001, 3, rows=2, cols=3)
        for response in (
            short_frame(status=1), short_frame(status=2), short_frame(status=3),
            long_frame(status=2), long_frame(b''), long_frame(b'\x00' * 11),
            long_frame(b'\x00' * 13),
        ):
            with self.subTest(response=response.hex()):
                self.client._send_receive = AsyncMock(return_value=response)
                with self.assertRaises(RuntimeError):
                    await self.client.read_matrix_block(variable, 0, 0, 2, 3)

    async def test_matrix_cancellation_releases_shared_lock_for_scalar_read(self):
        variable = self.protocol.Variable("Matrix", 4001, 3, rows=1, cols=1)
        sent = asyncio.Event()
        self.transport.sendto.side_effect = lambda request: sent.set()
        task = asyncio.create_task(self.client.read_matrix_element(variable, 0, 0))
        await sent.wait()
        scalar = asyncio.create_task(self.client.read_variable(self.variable))
        await asyncio.sleep(0)
        self.assertEqual(self.transport.sendto.call_count, 1)
        self.transport.sendto.side_effect = lambda request: self.deliver(self.envelope(
            long_frame(), self.tid(request),
        ))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(await scalar, 123)
        self.assert_waiter_cleared()

    async def test_matrix_rejects_unrelated_udp_reply_and_times_out_cleanly(self):
        variable = self.protocol.Variable("Matrix", 4001, 3, rows=1, cols=1)
        self.transport.sendto.side_effect = lambda request: self.deliver(self.envelope(
            long_frame(function=0x83), self.tid(request),
        ))
        with self.assertRaises(TimeoutError):
            await self.client.read_matrix_element(variable, 0, 0)
        self.assert_waiter_cleared()


if __name__ == "__main__":
    unittest.main()
