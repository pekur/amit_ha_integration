"""Discovery regressions with synthetic catalog slots and no UDP traffic."""
import asyncio
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import AsyncMock, patch


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "custom_components/amit/protocol.py"
        spec = importlib.util.spec_from_file_location("_amit_discovery_tests", path)
        cls.protocol = importlib.util.module_from_spec(spec)
        context = patch.dict(sys.modules, {spec.name: cls.protocol})
        context.start()
        cls.addClassCleanup(context.stop)
        spec.loader.exec_module(cls.protocol)

    def setUp(self):
        self.client = self.protocol.AMiTClient("plc.invalid")
        # The transport boundary is mocked; never connect to a real endpoint.
        self.client._connected = True

    def slot(self, wid=0, name="", var_type=0, *, version=1, rows=1, cols=1,
             station=4, index=0, size=26):
        data = bytearray(26)
        struct.pack_into("<H", data, 0, version)
        data[2] = var_type
        data[3] = station
        struct.pack_into("<HHHH", data, 4, rows, cols, wid, index)
        encoded = name.encode("latin-1")[:14]
        data[12:12 + len(encoded)] = encoded
        data = (data + bytes(max(0, size - 26)))[:size]
        frame = bytes([0x68, size + 4, size + 4, 0x68, 31, 4, 8, 0x83]) + data
        return frame + bytes([self.protocol._calc_checksum(frame[4:]), 0x16])

    async def test_metadata_versions_types_flags_and_dimensions(self):
        for version in (1, 0x100):
            for type_code in range(8):
                with self.subTest(version=version, type_code=type_code):
                    rows, cols = (1, 1) if type_code <= 2 else (3, 8)
                    self.client._send_receive = AsyncMock(return_value=self.slot(
                        1234, "Matrix", type_code | 0xF8, version=version,
                        rows=rows, cols=cols, station=0xE7, index=42,
                    ))
                    variable, = await self.client.load_variables(max_variables=1)
                    self.assertEqual(variable.var_type, type_code)
                    self.assertEqual((variable.rows, variable.cols), (rows, cols))
                    self.assertEqual(variable.station, 7)
                    self.assertEqual(variable.catalog_index, 42)
                    self.assertEqual(variable.metadata_version, version)
                    self.assertEqual(variable.wid, 1234)
                    self.assertEqual(variable.is_readable(), type_code <= 2)
                    if type_code >= 6:
                        self.assertEqual(variable.type_name, "Unknown")
                        self.assertNotEqual(variable.var_type, self.protocol.VarType.MATRIX_FLOAT)

    async def test_full_name_and_first_null_termination(self):
        for name, expected in (("LongVariable13", "LongVariable13"),
                               ("Name\x00Ignored", "Name"),
                               ("\x00Ignored", None), ("Teplota\xe1", "Teplota\xe1")):
            with self.subTest(name=name):
                self.client._send_receive = AsyncMock(return_value=self.slot(4001, name))
                variables = await self.client.load_variables(
                    max_variables=1, is_readonly_fn=lambda value: value == expected)
                self.assertEqual([v.name for v in variables], [] if expected is None else [expected])
                if variables:
                    self.assertFalse(variables[0].writable)

    async def test_invalid_metadata_never_publishes_partial_catalog(self):
        for options in ({"version": 0}, {"version": 2}, {"rows": 0}, {"cols": 0},
                        {"rows": 2}, {"cols": 2}, {"size": 22}, {"size": 25}, {"size": 27}):
            with self.subTest(options=options):
                self.client._send_receive = AsyncMock(side_effect=[
                    self.slot(4001, "Good"), self.slot(4002, "Invalid", **options),
                    self.slot(4003, "Later"),
                ])
                with self.assertRaisesRegex(ConnectionError, "metadata"):
                    await self.client.load_variables()
                self.assertEqual(self.client._send_receive.await_count, 2)

    async def test_zero_filled_slot_remains_a_catalog_boundary(self):
        self.client._send_receive = AsyncMock(return_value=self.slot(
            version=0, rows=0, cols=0, station=0))
        self.assertEqual(await self.client.load_variables(), [])
        self.assertEqual(self.client._send_receive.await_count, 10)

    async def test_catalog_end_probe_validates_metadata(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(4001, "Good")] + [TimeoutError("end")] * 20
            + [self.slot(4001, "Good", version=2)]
        ))
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()

    async def test_disconnected_client_raises_without_sending(self):
        self.client._connected = False
        self.client._send_receive = AsyncMock()
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()
        self.client._send_receive.assert_not_awaited()

    async def test_filtered_slots_do_not_hide_later_matching_variables(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(100, "Outside")] * 12
            + [self.slot(4001, "TE01"), self.slot(4000, "Setpoint")]
            + [self.slot()] * 10
        ))
        variables = await self.client.load_variables(
            wid_min=4000, wid_max=6000,
            is_readonly_fn=lambda name: name.startswith("TE"),
        )
        self.assertEqual([v.wid for v in variables], [4000, 4001])
        self.assertEqual([v.writable for v in variables], [True, False])
        self.assertEqual(self.client._send_receive.await_count, 24)

    async def test_valid_catalog_with_no_matching_wids_returns_empty(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(100, "Outside")] * 12 + [self.slot()] * 10
        ))
        self.assertEqual(await self.client.load_variables(wid_min=4000), [])
        self.assertEqual(self.client._send_receive.await_count, 22)

    async def test_empty_catalog_returns_empty_without_connection_error(self):
        self.client._send_receive = AsyncMock(return_value=self.slot())
        self.assertEqual(await self.client.load_variables(), [])
        self.assertEqual(self.client._send_receive.await_count, 10)

    async def test_invalid_memory_parameters_are_a_catalog_boundary(self):
        self.client._send_receive = AsyncMock(return_value=bytes.fromhex("10 1f 04 02 25 16"))
        self.assertEqual(await self.client.load_variables(), [])
        self.assertEqual(self.client._send_receive.await_count, 10)

    async def test_transfer_error_is_not_an_empty_catalog(self):
        self.client._send_receive = AsyncMock(return_value=bytes.fromhex("10 1f 04 01 24 16"))
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()

    async def test_corrupt_catalog_frames_are_not_an_empty_catalog(self):
        frame = bytearray(self.slot())
        frame[-2] ^= 1
        self.client._send_receive = AsyncMock(return_value=bytes(frame))
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()

    async def test_all_timeouts_raise_instead_of_empty_success(self):
        self.client._send_receive = AsyncMock(side_effect=TimeoutError("offline"))
        with self.assertRaises(ConnectionError) as caught:
            await self.client.load_variables()
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertEqual(self.client._send_receive.await_count, 10)

    async def test_connection_loss_does_not_publish_partial_catalog(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(4001, "Sample")] + [OSError("offline")] * 21
        ))
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()
        self.assertEqual(self.client._send_receive.await_count, 22)

    async def test_timeout_at_catalog_end_requires_successful_known_slot_probe(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(4001, "Sample")] + [TimeoutError("end")] * 20
            + [self.slot(4001, "Sample")]
        ))
        variables = await self.client.load_variables()
        self.assertEqual([v.wid for v in variables], [4001])
        last_request = self.client._send_receive.await_args.args[0]
        self.assertEqual(struct.unpack_from("<I", last_request, 8)[0], 0xFFFD0000)

    async def test_invalid_known_slot_probe_does_not_publish_partial_catalog(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(4001, "Sample")] + [TimeoutError("offline")] * 20 + [b""]
        ))
        with self.assertRaises(ConnectionError):
            await self.client.load_variables()

    async def test_transient_failure_can_recover_during_scan(self):
        first_attempt = True

        async def send(frame):
            nonlocal first_attempt
            index = struct.unpack_from("<I", frame, 8)[0] - 0xFFFD0000
            if index == 0 and first_attempt:
                first_attempt = False
                raise TimeoutError("temporary")
            if index in (0, 1):
                return self.slot(4001 + index, f"Sample{index}")
            return self.slot()

        self.client._send_receive = AsyncMock(side_effect=send)
        variables = await self.client.load_variables()
        self.assertEqual([v.wid for v in variables], [4001, 4002])

    async def test_recovers_skipped_range_after_ten_timeouts(self):
        calls = 0
        indexes = []

        async def send(frame):
            nonlocal calls
            index = struct.unpack_from("<I", frame, 8)[0] - 0xFFFD0000
            indexes.append(index)
            calls += 1
            if 2 <= calls <= 11:
                raise TimeoutError("temporary outage")
            if index in (0, 1):
                return self.slot(4001 + index, f"Sample{index}")
            return self.slot()

        self.client._send_receive = AsyncMock(side_effect=send)
        variables = await self.client.load_variables()
        self.assertEqual([v.wid for v in variables], [4001, 4002])
        self.assertEqual(indexes[11], 1)
        self.assertEqual(len(indexes), 22)

    async def test_repeated_gap_is_an_error_instead_of_partial_success(self):
        async def send(frame):
            index = struct.unpack_from("<I", frame, 8)[0] - 0xFFFD0000
            if index == 1:
                raise TimeoutError("unread slot")
            if index in (0, 2):
                return self.slot(4001 + index, f"Sample{index}")
            return self.slot()

        self.client._send_receive = AsyncMock(side_effect=send)
        with self.assertRaisesRegex(ConnectionError, "unread slots"):
            await self.client.load_variables()
        # Each catalog index is visited at most twice; recovery is bounded.
        self.assertLessEqual(self.client._send_receive.await_count, 26)

    async def test_recovery_at_scan_limit_does_not_duplicate_variables(self):
        self.client._send_receive = AsyncMock(side_effect=[
            TimeoutError("temporary"), self.slot(4002, "Second"),
            self.slot(4001, "First"), self.slot(4002, "Second"),
        ])
        variables = await self.client.load_variables(max_variables=2)
        self.assertEqual([v.wid for v in variables], [4001, 4002])
        self.assertEqual(self.client._send_receive.await_count, 4)

    async def test_cancellation_during_catalog_recovery_propagates(self):
        self.client._send_receive = AsyncMock(side_effect=(
            [self.slot(4001, "Sample")] + [TimeoutError("temporary")] * 10
            + [asyncio.CancelledError()]
        ))
        with self.assertRaises(asyncio.CancelledError):
            await self.client.load_variables()

    async def test_scan_limit_still_bounds_filtered_catalog(self):
        self.client._send_receive = AsyncMock(return_value=self.slot(100, "Outside"))
        self.assertEqual(await self.client.load_variables(max_variables=12, wid_min=4000), [])
        self.assertEqual(self.client._send_receive.await_count, 12)

    async def test_cancellation_is_not_swallowed(self):
        self.client._send_receive = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.client.load_variables()
        self.assertEqual(self.client._send_receive.await_count, 1)


if __name__ == "__main__":
    unittest.main()
