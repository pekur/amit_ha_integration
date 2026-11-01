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


if __name__ == "__main__":
    unittest.main()
