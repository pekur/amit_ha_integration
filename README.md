# AMiT PLC Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/pekur/amit_ha_integration.svg)](https://github.com/pekur/amit_ha_integration/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Native Home Assistant integration for AMiT PLCs (AMiNi, AC4 series) using the DB-Net/IP protocol.

## Features

- 🔌 **Auto-discovery of variables** - Automatically loads all available variables from PLC
- 🌡️ **Temperature sensors** - Creates sensor entities for temperature readings
- 🎚️ **Setpoint controls** - Number entities for adjusting temperature setpoints
- 🔘 **Switches** - Control on/off boolean variables
- ⚠️ **Binary sensors** - Monitor alarms and states
- 💾 **Export/Import** - Backup and restore configuration including custom entity names
- 🔄 **Reload button** - Reload variables from PLC without restarting
- 📝 **Service calls** - Write any variable value programmatically
- ⚙️ **Options flow** - Reconfigure variables without removing the integration
- 🇨🇿 **Czech language support** - Full localization

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on **Integrations**
3. Click the three dots menu (⋮) in the top right corner
4. Select **Custom repositories**
5. Add `https://github.com/pekur/amit_ha_integration` with category **Integration**
6. Click **Download**
7. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/pekur/amit_ha_integration/releases)
2. Extract and copy the `custom_components/amit` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### New Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **AMiT PLC**
4. Select **New configuration**
5. Enter connection details:

| Parameter | Default | Description |
|-----------|---------|-------------|
| IP Address | - | Your PLC's IP address |
| Port | 59 | DB-Net/IP port (UDP) |
| Station Address | 4 | PLC station address |
| Client Address | 31 | Your client address |
| Password | 0 | Numeric password (0 = no password) |
| Scan Interval | 30 | Polling interval in seconds |

6. Select which variables to monitor
7. Select which variables should be writable (controllable)
8. Done!

### Import from Backup

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **AMiT PLC**
4. Select **Import from backup**
5. Choose a backup file from the list
6. Confirm/adjust connection settings (password needs to be re-entered)
7. Done! All variables and custom entity names will be restored.

## Entity Types

The integration creates entities based on variable naming patterns and user selection:

| Variable Pattern | Entity Type | Description |
|-----------------|-------------|-------------|
| `TE*`, `Teoko*`, `pokoj*`, `koupl*`, `TTUV*`, `TVENK*` | Sensor | Temperature readings |
| `Zad*`, `Komf*`, `Utl*`, `Hyst*`, `TPRIV*` | Number | Temperature setpoints |
| `Zap*`, `Povol*`, `AUT*` | Switch | On/off controls |
| `Por*`, `ALARM*`, `Stav*` | Binary Sensor | Alarms and states |

Variables marked as **writable** in configuration will allow control; others are read-only.

## Device Buttons

Each AMiT PLC device has two built-in buttons:

### Export Configuration
- **Icon:** Download (mdi:download)
- **Function:** Exports current configuration to a JSON file
- **Saves to:** `config/www/amit/amit_export_YYYYMMDD_HHMMSS.json`
- **Includes:** Connection settings, selected variables, writable variables, custom entity names
- **Output:** Creates a persistent notification with a download link

### Reload Variables
- **Icon:** Refresh (mdi:refresh)
- **Function:** Reloads variable list from PLC
- **Use case:** After PLC program changes, reload to see new/changed variables

## Export/Import (Backup & Restore)

### Creating a Backup

1. Go to the AMiT PLC device in Home Assistant
2. Press the **Export Configuration** button
3. A notification will appear with a download link
4. The backup file is saved to `config/www/amit/`

The export includes:
- PLC connection settings (host, port, addresses)
- Scan interval
- List of monitored variables with their WIDs
- List of writable variables
- **Custom entity names** you've set in Home Assistant

### Restoring from Backup

1. Make sure backup files are in `config/www/amit/`
2. Add a new AMiT PLC integration
3. Select **Import from backup**
4. Choose the backup file
5. Enter password (not stored in backup for security)
6. All settings including custom entity names will be restored

## Services

### `amit.write_variable`

Write a value to any PLC variable.

```yaml
# By WID (variable index)
service: amit.write_variable
data:
  wid: 4723
  value: 22.5

# By variable name
service: amit.write_variable
data:
  name: "Zad_UT1"
  value: 22.5
```

### `amit.reload_variables`

Reload the variable list from PLC.

```yaml
service: amit.reload_variables
```

## Reconfiguration

To add/remove monitored variables or change writable settings:

1. Go to **Settings** → **Devices & Services**
2. Find **AMiT PLC** integration
3. Click **Configure**
4. Modify your selection
5. Click **Submit**

## Troubleshooting

### Cannot connect to PLC

1. Verify the PLC is reachable: `ping <ip_address>`
2. Check that port 59 (UDP) is not blocked by firewall
3. Verify station address matches PLC configuration in DetStudio
4. Try with password = 0 first

### Variables not updating

1. Check Home Assistant logs for errors
2. Verify the scan interval setting
3. Press the **Reload Variables** button on the device
4. Check PLC communication in DetStudio

### Temperature shows as "unknown"

Temperature value ~146.19°C indicates a disconnected sensor. The integration filters these out and shows "unknown" instead.

### Entity not appearing

- Check if the variable is selected in the integration configuration
- Verify the variable type matches expected patterns
- Check Home Assistant logs for entity creation errors

### Import doesn't restore custom names

- Make sure you're using a backup file created after the custom names feature was added
- Check Home Assistant logs for "Applied X custom entity names" message
- Verify the WIDs in the backup match the current PLC variables

## Protocol Details

This integration implements the **DB-Net/IP** protocol, which is AMiT's proprietary UDP-based protocol for PLC communication (port 59). The protocol was reverse-engineered from DetStudio software using Wireshark captures.

Key protocol features:
- XOR-based encryption with session key synchronization
- Checksum verification using password-based randomization
- Commands: `0x21` (read var info), `0x22` (read value), `0x23` (write value)
- Support for multiple data types: bool, int8, int16, int32, float

## Supported Hardware

Tested on:
- AMiNi series PLCs
- AC4 series PLCs

Should work with any AMiT PLC supporting DB-Net/IP protocol.

## File Structure

```
config/
├── custom_components/
│   └── amit/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── protocol.py
│       ├── sensor.py
│       ├── number.py
│       ├── switch.py
│       ├── binary_sensor.py
│       ├── button.py
│       ├── manifest.json
│       ├── services.yaml
│       ├── strings.json
│       └── translations/
│           ├── en.json
│           └── cs.json
└── www/
    └── amit/
        └── amit_export_*.json  (backup files)
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file.

## Credits

- Protocol reverse-engineering based on Wireshark analysis of DetStudio communication
- Developed for home automation of heating systems controlled by AMiT PLCs
