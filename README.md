# AMiT PLC Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

This integration allows you to connect AMiT PLCs (AMiNi, AC4, etc.) to Home Assistant using the DB-Net/IP protocol.

## Features

- 🔌 **Auto-discovery of variables** - Automatically loads all available variables from PLC
- 🌡️ **Temperature sensors** - Creates sensor entities for temperature readings
- 🎚️ **Setpoint controls** - Number entities for adjusting setpoints
- 🔘 **Switches** - Control on/off variables
- ⚠️ **Binary sensors** - Monitor alarms and states
- 📝 **Service calls** - Write any variable value

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL with category "Integration"
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/amit` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "AMiT PLC"
4. Enter connection details:
   - **IP Address**: Your PLC's IP address
   - **Port**: Usually 59 (default)
   - **Station Address**: PLC station address (default: 4)
   - **Client Address**: Your client address (default: 31)
   - **Password**: Numeric password (default: 0)
   - **Scan Interval**: How often to poll values (default: 30 seconds)
5. Select which variables to monitor
6. Done!

## Entity Types

The integration automatically creates entities based on variable characteristics:

| Variable Pattern | Entity Type | Example |
|-----------------|-------------|---------|
| `TE*`, `Teoko*`, `pokoj*` | Sensor (temperature) | Teoko1, TEVENK |
| `Zad*`, `Komf*`, `Utl*` | Number (setpoint) | Zad_UT1, Komf1 |
| `Zap*`, `Povol*`, `AUT*` | Switch | ZapFve, PovolLG |
| `Por*`, `ALARM*` | Binary Sensor | PORCIDEL, ALARM |

## Services

### `amit.write_variable`

Write a value to any PLC variable.

```yaml
service: amit.write_variable
data:
  wid: 4723        # Variable WID
  value: 5.0       # Value to write
```

Or by name:

```yaml
service: amit.write_variable
data:
  name: "filtr_Eoko"
  value: 5.0
```

### `amit.reload_variables`

Reload the variable list from PLC.

```yaml
service: amit.reload_variables
```

## Troubleshooting

### Cannot connect to PLC

1. Check that the PLC is reachable (ping the IP address)
2. Verify the port is correct (default: 59)
3. Check that no firewall is blocking UDP traffic
4. Verify station address matches PLC configuration

### Variables not updating

1. Check the scan interval setting
2. Look for errors in Home Assistant logs
3. Try the `amit.reload_variables` service

### Temperature shows as "unknown"

Values like 146.19°C indicate a disconnected sensor. These are filtered out and shown as "unknown".

## Protocol Details

This integration implements the DB-Net/IP protocol, which is AMiT's proprietary protocol for PLC communication. The protocol was reverse-engineered from the official DetStudio software.

- **Transport**: UDP
- **Port**: 59 (default)
- **Encryption**: XOR-based with session key synchronization
- **Functions used**:
  - `0x01` - Read variable
  - `0x02` - Write variable
  - `0x03` - Read memory (for variable list)

## License

MIT License

## Credits

- Protocol reverse-engineering based on AMiT documentation and DetStudio analysis
- Inspired by the hass-dbnetbus project by Tomáš Mandys
