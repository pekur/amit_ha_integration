"""
AMiT DB-Net/IP Protocol Implementation.
Reverse-engineered from AMiT libdbnet2.a
"""

import struct
import asyncio
import logging
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

HEADER_SIZE = 15
TYPE_SYNC_KEY = 0x1111


class VarType(IntEnum):
    """Variable types in AMiT PLC."""
    INT16 = 0
    INT32 = 1
    FLOAT = 2
    ARRAY = 3
    TIME_ARRAY = 4
    STRUCTURE = 5


@dataclass
class Variable:
    """Represents an AMiT PLC variable."""
    name: str
    wid: int
    var_type: VarType
    value: Any = None
    writable: bool = True
    
    @property
    def type_name(self) -> str:
        """Return human-readable type name."""
        names = {
            VarType.INT16: "Int",
            VarType.INT32: "Long", 
            VarType.FLOAT: "Float",
            VarType.ARRAY: "Array",
            VarType.TIME_ARRAY: "TimeArray",
            VarType.STRUCTURE: "Structure",
        }
        return names.get(self.var_type, "Unknown")
    
    def is_readable(self) -> bool:
        """Check if variable can be read (simple types only)."""
        return self.var_type in (VarType.INT16, VarType.INT32, VarType.FLOAT)


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
    """Parse a DB-Net response frame."""
    if len(data) < 6:
        raise ValueError("Frame too short")
    
    frame_type = data[0]
    
    if frame_type == 0x10:
        dest_addr = data[1]
        src_addr = data[2]
        fcb = data[3]
        status = fcb & 0x0F
        return dest_addr, src_addr, status, b''
    
    elif frame_type == 0x68:
        data_len = data[1]
        dest_addr = data[4]
        src_addr = data[5]
        fcb = data[6]
        status = fcb & 0x0F
        value_data = data[8:8 + data_len - 4]
        return dest_addr, src_addr, status, value_data
    
    else:
        raise ValueError(f"Unknown frame type: 0x{frame_type:02x}")


class AMiTProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for AMiT communication."""
    
    def __init__(self):
        self.transport = None
        self._response_future: Optional[asyncio.Future] = None
    
    def connection_made(self, transport):
        self.transport = transport
        _LOGGER.debug("UDP protocol connection made")
    
    def datagram_received(self, data, addr):
        _LOGGER.debug(f"Received {len(data)} bytes from {addr}")
        if self._response_future and not self._response_future.done():
            self._response_future.set_result(data)
        else:
            _LOGGER.warning(f"Received data but no future waiting: {len(data)} bytes")
    
    def error_received(self, exc):
        _LOGGER.error(f"UDP error received: {exc}")
        if self._response_future and not self._response_future.done():
            self._response_future.set_exception(exc)
    
    def connection_lost(self, exc):
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
            loop = asyncio.get_event_loop()
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
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
        self._connected = False
        _LOGGER.info("Disconnected from AMiT PLC")
    
    async def test_connection(self) -> bool:
        """Test connection by reading a simple value."""
        try:
            _LOGGER.debug("Testing connection - reading WID 4000...")
            await self._send_receive(self._create_read_frame(4000, VarType.INT16))
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
    
    async def _send_receive_internal(self, payload: bytes) -> bytes:
        """Internal send/receive without lock (for recursion after key sync)."""
        if not self._transport or not self._protocol:
            raise RuntimeError("Not connected")
        
        # Build header
        header = bytearray(15)
        struct.pack_into('<i', header, 0, self._transaction_id)
        struct.pack_into('<h', header, 4, 0)
        struct.pack_into('<I', header, 6, self._key)
        struct.pack_into('<I', header, 10, 0)
        header[14] = len(payload) - 6
        
        msg = header + bytearray(payload)
        _encrypt_msg(msg, self.password)
        
        frame_cs = _calc_checksum(payload[4:4+payload[1]])
        cs_input = self._transaction_id + self._key + frame_cs + 256
        checksum = _randomize(self.password, cs_input)
        struct.pack_into('<I', msg, 10, checksum)
        
        # Create NEW future for response
        loop = asyncio.get_running_loop()
        self._protocol._response_future = loop.create_future()
        
        # Send
        _LOGGER.debug(f"Sending {len(msg)} bytes, transaction_id={self._transaction_id}, key=0x{self._key:08x}")
        self._transport.sendto(bytes(msg))
        self._transaction_id += 1
        
        # Wait for response with timeout
        try:
            data = await asyncio.wait_for(
                self._protocol._response_future,
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            self._protocol._response_future = None
            raise TimeoutError("No response from PLC")
        finally:
            self._protocol._response_future = None
        
        # Check for key sync
        resp_type = struct.unpack_from('<h', data, 4)[0]
        if resp_type == TYPE_SYNC_KEY:
            self._key = struct.unpack_from('<I', data, 6)[0]
            _LOGGER.debug(f"Key sync received: 0x{self._key:08x}, retrying...")
            # Retry with new key (recursive call without lock)
            return await self._send_receive_internal(payload)
        
        self._key = struct.unpack_from('<I', data, 6)[0]
        
        # Decrypt
        resp = bytearray(data)
        _encrypt_msg(resp, self.password)
        
        return bytes(resp[15:])
    
    async def read_variable(self, variable: Variable) -> Any:
        """Read a variable value from PLC."""
        if not variable.is_readable():
            raise ValueError(f"Variable {variable.name} is not readable")
        
        frame = self._create_read_frame(variable.wid, variable.var_type)
        response = await self._send_receive(frame)
        _, _, status, value_data = _parse_response(response)
        
        if len(value_data) < 2:
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
        _, _, status, _ = _parse_response(response)
        
        return status in (0x00, 0x08)
    
    async def load_variables(self, max_variables: int = 1500) -> List[Variable]:
        """Load variable list from PLC."""
        variables = []
        index = 0
        consecutive_failures = 0
        max_failures = 10
        
        _LOGGER.info("Loading variable list from PLC...")
        
        while consecutive_failures < max_failures and index < max_variables:
            try:
                frame = self._create_read_memory_frame(0xFFFD0000 + index, 26)
                response = await self._send_receive(frame)
                
                if len(response) < 10 or response[0] != 0x68:
                    consecutive_failures += 1
                    index += 1
                    continue
                
                frame_len = response[1]
                data = response[8:4+frame_len]
                
                if len(data) < 22:
                    consecutive_failures += 1
                    index += 1
                    continue
                
                wid = struct.unpack_from('<H', data, 8)[0]
                var_type_code = data[2]
                
                name_bytes = data[12:24]
                null_idx = name_bytes.find(b'\x00')
                if null_idx > 0:
                    name = name_bytes[:null_idx].decode('latin-1', errors='replace')
                else:
                    name = name_bytes.rstrip(b'\x00').decode('latin-1', errors='replace')
                
                if name and name[0].isalpha() and 4000 <= wid <= 6000:
                    try:
                        var_type = VarType(var_type_code)
                    except ValueError:
                        var_type = VarType.STRUCTURE
                    
                    # Heuristic for read-only variables
                    writable = not self._is_readonly_name(name)
                    
                    variables.append(Variable(
                        name=name,
                        wid=wid,
                        var_type=var_type,
                        writable=writable
                    ))
                    consecutive_failures = 0
                    
                    if len(variables) % 100 == 0:
                        _LOGGER.debug(f"Loaded {len(variables)} variables...")
                else:
                    consecutive_failures += 1
                
            except TimeoutError:
                _LOGGER.debug(f"Timeout reading variable at index {index}")
                consecutive_failures += 1
            except Exception as e:
                _LOGGER.debug(f"Error reading variable at index {index}: {e}")
                consecutive_failures += 1
            
            index += 1
            await asyncio.sleep(0.02)  # 20ms delay between reads
        
        _LOGGER.info(f"Loaded {len(variables)} variables from PLC")
        return sorted(variables, key=lambda v: v.wid)
    
    @staticmethod
    def _is_readonly_name(name: str) -> bool:
        """Heuristic to determine if variable is read-only based on name."""
        readonly_prefixes = (
            'TE',      # Measured temperatures
            'TEPROST', # Room temperatures  
            'TEVEN',   # Outdoor temp
            'TTUV',    # DHW temperature
            'Trek',    # Recuperation temp
            'pokoj',   # Room sensors
            'Por',     # Faults/errors
            'ALARM',   # Alarms
            'Stav',    # States
            'status',  # Status
            'CO2_',    # CO2 sensors
            'koupl',   # Bathroom temps
            'Teoko',   # Circuit temps
        )
        return name.startswith(readonly_prefixes)
