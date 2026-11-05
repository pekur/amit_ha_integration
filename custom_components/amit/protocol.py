"""
AMiT DB-Net/IP Protocol Implementation.
Reverse-engineered from AMiT libdbnet2.a
"""

import struct
import asyncio
import logging
from typing import Callable, Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

HEADER_SIZE = 15
TYPE_SYNC_KEY = 0x1111
MAX_KEY_SYNC_RETRIES = 2


class VarType(IntEnum):
    """Variable types in AMiT PLC."""
    INT16 = 0
    INT32 = 1
    FLOAT = 2
    MATRIX_INT16 = 3
    MATRIX_INT32 = 4
    MATRIX_FLOAT = 5
    # Keep the old names as aliases for callers using earlier releases.
    ARRAY = MATRIX_INT16
    TIME_ARRAY = MATRIX_INT32
    STRUCTURE = MATRIX_FLOAT


@dataclass
class Variable:
    """Represents an AMiT PLC variable."""
    name: str
    wid: int
    var_type: VarType | int
    value: Any = None
    writable: bool = True
    rows: Optional[int] = None
    cols: Optional[int] = None
    station: Optional[int] = None
    metadata_version: Optional[int] = None
    catalog_index: Optional[int] = None
    
    @property
    def type_name(self) -> str:
        """Return human-readable type name."""
        names = {
            VarType.INT16: "Int",
            VarType.INT32: "Long", 
            VarType.FLOAT: "Float",
            VarType.MATRIX_INT16: "Matrix Integer",
            VarType.MATRIX_INT32: "Matrix Long",
            VarType.MATRIX_FLOAT: "Matrix Float",
        }
        return names.get(self.var_type, "Unknown")
    
    def is_readable(self) -> bool:
        """Check if variable can be read (simple types only)."""
        return self.var_type in (VarType.INT16, VarType.INT32, VarType.FLOAT)


class _InvalidVariableMetadata(ValueError):
    """Catalog data cannot be safely interpreted."""


def _parse_variable_info(data: bytes) -> Optional[Variable]:
    """Decode the 26-byte DB-Net catalog record, or an empty slot."""
    if len(data) != 26:
        raise _InvalidVariableMetadata("Catalog response must contain 26 bytes")
    if not any(data):
        return None
    version = struct.unpack_from('<H', data)[0]
    # The published layout says 0x0100; a live DB-Net/IP PLC returns 0x0001.
    if version not in (0x0001, 0x0100):
        raise _InvalidVariableMetadata("Unsupported catalog metadata version")
    type_code = data[2] & 0x07
    rows, cols, wid, index = struct.unpack_from('<HHHH', data, 4)
    if not rows or not cols or (type_code <= 2 and (rows, cols) != (1, 1)):
        raise _InvalidVariableMetadata("Invalid catalog variable dimensions")
    try:
        var_type = VarType(type_code)
    except ValueError:
        var_type = type_code  # Preserve reserved codes 6 and 7 as unknown.
    return Variable(
        name=data[12:26].split(b'\x00', 1)[0].decode('latin-1'),
        wid=wid, var_type=var_type, rows=rows, cols=cols,
        station=data[3] & 0x1F, metadata_version=version, catalog_index=index,
    )


def _randomize(seed: int, password: int) -> int:
    """PRNG for encryption."""
    if password == 0:
        password = 1
    mult = seed * password
    key = password
    for _ in range(4):
        key = (key << 1) + 13
        mult = (mult + key) * seed
    result = password + mult + key
    return result & 0xFFFFFFFF


def _calc_checksum(data: bytes) -> int:
    """Calculate DB-Net checksum."""
    cs = 0
    for b in data:
        cs += b
        if cs > 0xFF:
            cs = (cs + 1) & 0xFF
    return cs


def _encrypt_msg(msg: bytearray, password: int) -> None:
    """Encrypt/decrypt message payload in-place."""
    payload_len = msg[14] + 6
    payload_start = 15
    key = struct.unpack_from('<I', msg, 6)[0]
    transaction_id = struct.unpack_from('<I', msg, 0)[0]
    rand_val = _randomize(key, (~transaction_id) & 0xFFFFFFFF)
    rand_bytes = struct.pack('<I', rand_val)
    pos = 0
    for i in range(payload_len):
        if i == 8:
            rand_val = _randomize(key, transaction_id)
            rand_bytes = struct.pack('<I', rand_val)
        msg[payload_start + i] ^= rand_bytes[pos % 4]
        pos += 1


def _parse_response(data: bytes) -> Tuple[int, int, int, bytes]:
    """Validate and parse a DB-Net response frame.

    Frame layout and FCS: AMiT's DB-Net specification, sections Frame and Errors
    (https://jvalter.cz/sites/default/files/soubory/dbnet101.html).
    """
    if len(data) < 6:
        raise ValueError("Frame too short")
    if data[-1] != 0x16:
        raise ValueError("Invalid frame terminator")
    
    frame_type = data[0]
    
    if frame_type == 0x10:
        if len(data) != 6:
            raise ValueError("Invalid short frame length")
        if _calc_checksum(data[1:4]) != data[4]:
            raise ValueError("Invalid frame checksum")
        dest_addr = data[1]
        src_addr = data[2]
        fcb = data[3]
        value_data = b''
    
    elif frame_type == 0x68:
        data_len = data[1]
        if data_len < 4 or len(data) != data_len + 6:
            raise ValueError("Invalid long frame length")
        if data[2] != data_len or data[3] != 0x68:
            raise ValueError("Invalid long frame header")
        if _calc_checksum(data[4:-2]) != data[-2]:
            raise ValueError("Invalid frame checksum")
        dest_addr = data[4]
        src_addr = data[5]
        fcb = data[6]
        value_data = data[8:-2]
    
    else:
        raise ValueError(f"Unknown frame type: 0x{frame_type:02x}")

    if dest_addr > 31 or src_addr > 31 or fcb & 0xC0:
        raise ValueError("Invalid response address or control byte")
    return dest_addr, src_addr, fcb & 0x0F, value_data


class AMiTProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for AMiT communication."""
    
    def __init__(self):
        self.transport = None
        self._response_future: Optional[asyncio.Future] = None
        self._response_validator: Optional[Callable] = None
    
    def connection_made(self, transport):
        self.transport = transport
        _LOGGER.debug("UDP protocol connection made")
    
    def datagram_received(self, data, addr):
        _LOGGER.debug(f"Received {len(data)} bytes from {addr}")
        if self._response_future and not self._response_future.done():
            try:
                response = self._response_validator(data) if self._response_validator else data
            except (ValueError, struct.error) as err:
                _LOGGER.debug("Ignoring invalid or unrelated datagram: %s", err)
                return
            self._response_future.set_result(response)
        else:
            _LOGGER.warning(f"Received data but no future waiting: {len(data)} bytes")
    
    def error_received(self, exc):
        _LOGGER.error(f"UDP error received: {exc}")
        if self._response_future and not self._response_future.done():
            self._response_future.set_exception(exc)
    
    def connection_lost(self, exc):
        if self._response_future and not self._response_future.done():
            self._response_future.set_exception(ConnectionError("UDP connection lost"))
        self.transport = None
        if exc:
            _LOGGER.error(f"UDP connection lost with error: {exc}")
        else:
            _LOGGER.debug("UDP connection closed")


class AMiTClient:
    """Async client for AMiT PLC communication."""
    
    def __init__(
        self,
        host: str,
        port: int = 59,
        station_addr: int = 4,
        client_addr: int = 31,
        password: int = 0,
        timeout: float = 2.0,
    ):
        self.host = host
        self.port = port
        self.station_addr = station_addr
        self.client_addr = client_addr
        self.password = password
        self.timeout = timeout
        
        self._transport = None
        self._protocol: Optional[AMiTProtocol] = None
        self._transaction_id = 1
        self._key = 0
        self._lock = asyncio.Lock()
        self._connected = False
    
    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected
    
    async def connect(self) -> bool:
        """Establish connection to PLC."""
        try:
            loop = asyncio.get_running_loop()
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                AMiTProtocol,
                remote_addr=(self.host, self.port)
            )
            self._connected = True
            _LOGGER.info(f"Connected to AMiT PLC at {self.host}:{self.port}")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to connect: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection."""
        if self._protocol:
            future = self._protocol._response_future
            if future and not future.done():
                future.set_exception(ConnectionError("Disconnected from PLC"))
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
        self._connected = False
        _LOGGER.info("Disconnected from AMiT PLC")
    
    async def test_connection(self, test_wid: int = 4000) -> bool:
        """Test a validated round trip without requiring a particular variable.

        A PLC error reply also confirms reachability. Discovery and subsequent
        reads check capabilities and values; this legacy probe only checks that
        the configured endpoint responds with a valid, matching frame.
        """
        try:
            _LOGGER.debug(f"Testing connection - probing WID {test_wid}...")
            response = await self._send_receive(self._create_read_frame(test_wid, VarType.INT16))
            self._validate_response(response, 0x01)
            _LOGGER.debug("Connection test successful")
            return True
        except TimeoutError as e:
            _LOGGER.error(f"Connection test timeout: {e}")
            return False
        except Exception as e:
            _LOGGER.error(f"Connection test failed: {e}")
            return False
    
    def _create_read_frame(self, wid: int, var_type: VarType) -> bytes:
        """Create READ_VARIABLE frame."""
        payload = bytearray()
        payload.append(0x68)
        payload.append(0x07)
        payload.append(0x07)
        payload.append(0x68)
        payload.append(self.station_addr & 0x1F)
        payload.append(self.client_addr & 0x1F)
        payload.append(0x4D)  # FCB: CMD_READ
        payload.append(0x01)  # Function: READ_REG
        payload.append(var_type)
        payload.extend(struct.pack('<H', wid))
        fcs = _calc_checksum(payload[4:11])
        payload.append(fcs)
        payload.append(0x16)
        return bytes(payload)
    
    def _create_write_frame(self, wid: int, value: Any, var_type: VarType) -> bytes:
        """Create WRITE_VARIABLE frame."""
        payload = bytearray()
        payload.append(0x68)
        
        if var_type == VarType.INT16:
            payload.append(0x09)
            payload.append(0x09)
        else:
            payload.append(0x0B)
            payload.append(0x0B)
        
        payload.append(0x68)
        payload.append(self.station_addr & 0x1F)
        payload.append(self.client_addr & 0x1F)
        payload.append(0x45)  # FCB: CMD_WRITE
        payload.append(0x02)  # Function: WRITE_REG
        payload.append(var_type)
        payload.extend(struct.pack('<H', wid))
        
        if var_type == VarType.INT16:
            payload.extend(struct.pack('<h', int(value)))
        elif var_type == VarType.INT32:
            payload.extend(struct.pack('<i', int(value)))
        else:
            payload.extend(struct.pack('<f', float(value)))
        
        data_len = payload[1]
        fcs = _calc_checksum(payload[4:4+data_len])
        payload.append(fcs)
        payload.append(0x16)
        return bytes(payload)
    
    def _create_read_memory_frame(self, address: int, count: int) -> bytes:
        """Create READ_MEMORY frame for reading variable list."""
        payload = bytearray()
        payload.append(0x68)
        payload.append(0x0A)
        payload.append(0x0A)
        payload.append(0x68)
        payload.append(self.station_addr & 0x1F)
        payload.append(self.client_addr & 0x1F)
        payload.append(0x4D)
        payload.append(0x03)  # Function: READ_MEMORY
        payload.extend(struct.pack('<I', address))
        payload.extend(struct.pack('<H', count))
        fcs = _calc_checksum(payload[4:4+payload[1]])
        payload.append(fcs)
        payload.append(0x16)
        return bytes(payload)
    
    async def _send_receive(self, payload: bytes) -> bytes:
        """Send frame and receive response."""
        async with self._lock:
            return await self._send_receive_internal(payload)
    
    def _validate_response(self, response: bytes, function: int) -> Tuple[int, bytes]:
        """Check the response belongs to this station and requested function."""
        dest, src, status, value_data = _parse_response(response)
        if dest != (self.client_addr & 0x1F) or src != (self.station_addr & 0x1F):
            raise ValueError("Response addresses do not match request")
        if status in (0x00, 0x08):
            if response[0] == 0x68:
                if response[7] != (function | 0x80):
                    raise ValueError("Response function does not match request")
            elif function in (0x01, 0x03):
                raise ValueError("Read response contains no data")
        return status, value_data

    def _decode_response(self, data: bytes, transaction_id: int, function: int) -> Tuple[int, int, bytes]:
        """Validate the UDP envelope before accepting its key or payload."""
        if len(data) < 10:
            raise ValueError("UDP header too short")
        if struct.unpack_from('<I', data, 0)[0] != transaction_id:
            raise ValueError("Response transaction does not match request")
        resp_type = struct.unpack_from('<h', data, 4)[0]
        key = struct.unpack_from('<I', data, 6)[0]
        if resp_type == TYPE_SYNC_KEY:
            # Existing key-sync handling uses only this header prefix. Its
            # optional trailing fields are undocumented, so leave them alone.
            return resp_type, key, b''
        if len(data) < HEADER_SIZE or len(data) != HEADER_SIZE + data[14] + 6:
            raise ValueError("Invalid UDP payload length")
        response = bytearray(data)
        _encrypt_msg(response, self.password)
        frame = bytes(response[HEADER_SIZE:])
        self._validate_response(frame, function)
        # The UDP checksum's receive-side formula is not documented here;
        # validate the inner FCS without guessing an envelope algorithm.
        return resp_type, key, frame

    async def _send_receive_internal(self, payload: bytes) -> bytes:
        """Exchange one request, with a bounded number of key synchronizations."""
        for attempt in range(MAX_KEY_SYNC_RETRIES + 1):
            if not self._transport or not self._protocol:
                raise ConnectionError("Not connected")
            transport, protocol = self._transport, self._protocol
            transaction_id = self._transaction_id
            header = bytearray(HEADER_SIZE)
            struct.pack_into('<I', header, 0, transaction_id)
            struct.pack_into('<h', header, 4, 0)
            struct.pack_into('<I', header, 6, self._key)
            header[14] = len(payload) - 6
            msg = header + bytearray(payload)
            _encrypt_msg(msg, self.password)
            frame_cs = _calc_checksum(payload[4:4 + payload[1]])
            checksum = _randomize(self.password, transaction_id + self._key + frame_cs + 256)
            struct.pack_into('<I', msg, 10, checksum)

            future = asyncio.get_running_loop().create_future()
            protocol._response_future = future
            protocol._response_validator = lambda data: self._decode_response(
                data, transaction_id, payload[7]
            )
            self._transaction_id = (transaction_id + 1) & 0xFFFFFFFF or 1
            try:
                _LOGGER.debug("Sending %d bytes, transaction_id=%d", len(msg), transaction_id)
                transport.sendto(bytes(msg))
                resp_type, key, frame = await asyncio.wait_for(future, timeout=self.timeout)
            except asyncio.TimeoutError as err:
                raise TimeoutError("No response from PLC") from err
            finally:
                if protocol._response_future is future:
                    protocol._response_future = None
                    protocol._response_validator = None
                if not future.done():
                    future.cancel()

            self._key = key
            if resp_type != TYPE_SYNC_KEY:
                return frame
            if attempt == MAX_KEY_SYNC_RETRIES:
                raise ConnectionError("Too many PLC key synchronizations")
            _LOGGER.debug("Key sync received, retrying...")
    
    async def read_variable(self, variable: Variable) -> Any:
        """Read a variable value from PLC."""
        if not variable.is_readable():
            raise ValueError(f"Variable {variable.name} is not readable")
        
        frame = self._create_read_frame(variable.wid, variable.var_type)
        response = await self._send_receive(frame)
        status, value_data = self._validate_response(response, 0x01)
        if status not in (0x00, 0x08):
            raise RuntimeError(f"PLC rejected read of {variable.name}: status {status}")
        
        expected_size = 2 if variable.var_type == VarType.INT16 else 4
        if len(value_data) != expected_size:
            raise RuntimeError(f"Invalid response for {variable.name}")
        
        if variable.var_type == VarType.INT16:
            return struct.unpack('<h', value_data[:2])[0]
        elif variable.var_type == VarType.INT32:
            return struct.unpack('<i', value_data[:4])[0]
        elif variable.var_type == VarType.FLOAT:
            return struct.unpack('<f', value_data[:4])[0]
    
    async def write_variable(self, variable: Variable, value: Any) -> bool:
        """Write a value to PLC variable."""
        if not variable.writable:
            raise ValueError(f"Variable {variable.name} is read-only")
        
        if not variable.is_readable():
            raise ValueError(f"Variable type {variable.type_name} is not writable")
        
        frame = self._create_write_frame(variable.wid, value, variable.var_type)
        response = await self._send_receive(frame)
        status, _ = self._validate_response(response, 0x02)
        
        return status in (0x00, 0x08)
    
    async def load_variables(
        self,
        max_variables: int = 1500,
        is_readonly_fn: Optional[Callable[[str], bool]] = None,
        wid_min: Optional[int] = None,
        wid_max: Optional[int] = None,
    ) -> List[Variable]:
        """Load variable list from PLC.

        Args:
            max_variables: Upper bound on the number of memory slots to scan.
            is_readonly_fn: Optional callable ``(name) -> bool`` that returns
                ``True`` when a variable should be treated as read-only.  When
                ``None`` all discovered variables are considered writable.
            wid_min: If provided, only variables with ``wid >= wid_min`` are
                included.  ``None`` means no lower bound.
            wid_max: If provided, only variables with ``wid <= wid_max`` are
                included.  ``None`` means no upper bound.

        Raises:
            ConnectionError: The client is disconnected or communication fails
                and a previously readable catalog slot cannot be read again,
                or catalog metadata has an unsupported version or invalid layout.
        """
        if not self.connected:
            raise ConnectionError("Not connected to PLC")

        variables = []
        index = 0
        consecutive_failures = 0
        max_failures = 10
        last_error = None
        last_valid_index = None
        recovery_point = None
        recovery_attempted = False
        recovery_error = None
        recovery_incomplete = False
        
        _LOGGER.info("Loading variable list from PLC...")
        
        while True:
            if consecutive_failures >= max_failures or index >= max_variables:
                if recovery_point is None or recovery_attempted or last_valid_index is None:
                    break
                # Retry the interrupted range once, including any skipped slots.
                # Discard its first-pass results to avoid duplicates or stale data.
                index, variable_count, last_valid_index = recovery_point
                del variables[variable_count:]
                consecutive_failures = 0
                last_error = None
                recovery_attempted = True

            try:
                frame = self._create_read_memory_frame(0xFFFD0000 + index, 26)
                response = await self._send_receive(frame)
                last_error = None
                status, data = self._validate_response(response, 0x03)
                if status == 0x02:
                    # Invalid memory parameters mark a catalog boundary.
                    consecutive_failures += 1
                    index += 1
                    continue
                if status not in (0x00, 0x08):
                    raise RuntimeError(f"PLC rejected catalog read: status {status}")
                variable = _parse_variable_info(data)
                name = variable.name if variable is not None else ""
                wid = variable.wid if variable is not None else 0
                
                # Apply WID range filter
                wid_in_range = (
                    (wid_min is None or wid >= wid_min)
                    and (wid_max is None or wid <= wid_max)
                )

                if name and name[0].isalpha():
                    if recovery_attempted and recovery_error is not None:
                        recovery_incomplete = True
                    # A valid catalog slot is not a failure when filtered out.
                    consecutive_failures = 0
                    last_valid_index = index
                    if not wid_in_range:
                        index += 1
                        await asyncio.sleep(0.001)
                        continue

                    variable.writable = not (is_readonly_fn(name) if is_readonly_fn is not None else False)
                    variables.append(variable)
                    consecutive_failures = 0
                    
                    if len(variables) % 100 == 0:
                        _LOGGER.debug(f"Loaded {len(variables)} variables...")
                else:
                    consecutive_failures += 1
                
            except _InvalidVariableMetadata as err:
                # Do not publish a partial catalog or treat corrupt data as its end.
                raise ConnectionError("Invalid variable catalog metadata") from err
            except TimeoutError as e:
                _LOGGER.debug(f"Timeout reading variable at index {index}")
                consecutive_failures += 1
                last_error = e
            except Exception as e:
                _LOGGER.debug(f"Error reading variable at index {index}: {e}")
                consecutive_failures += 1
                last_error = e
            
            if last_error is not None and recovery_point is None:
                recovery_point = (index, len(variables), last_valid_index)
            if last_error is not None and recovery_attempted:
                recovery_error = last_error
            index += 1
            await asyncio.sleep(0.001)  # 1ms delay between reads
        
        if recovery_incomplete:
            raise ConnectionError("Variable catalog still contains unread slots") from recovery_error

        if last_error is not None:
            # Some devices may stop responding beyond the end of the catalog.
            # Re-read a known slot to distinguish that from losing the PLC.
            if last_valid_index is None:
                raise ConnectionError("Failed to load variable catalog from PLC") from last_error
            try:
                response = await self._send_receive(
                    self._create_read_memory_frame(0xFFFD0000 + last_valid_index, 26)
                )
                status, probe_data = self._validate_response(response, 0x03)
                if status not in (0x00, 0x08) or _parse_variable_info(probe_data) is None:
                    raise ValueError("Invalid catalog probe response")
            except Exception as err:
                raise ConnectionError("Failed to load variable catalog from PLC") from err

        _LOGGER.info(f"Loaded {len(variables)} variables from PLC")
        return sorted(variables, key=lambda v: v.wid)

