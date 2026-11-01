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
- 📈 **Live variable monitor** - Browse discovered values and plot selected variables with temporary, in-memory history
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
| Target system | Biosuntec | Variable filtering and classification profile |

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

The integration creates entities based on variable naming patterns and the writable selection made during configuration. The patterns below apply to the **Biosuntec** target profile; the Generic profile does not restrict variable names.

| Variable Pattern | Writable? | Entity Type | Description |
|-----------------|-----------|-------------|-------------|
| `TE*`, `Teoko*`, `Trek*`, `TTUV*`, `TPRIV*`, `TVENK*`, `pokoj*`, `koupl*`, `T1p*`, `T*` (float) | No | Sensor | Temperature readings (°C) |
| `Zad*`, `Komf*`, `komf*`, `Utl*`, `utl*`, `ZADANA*`, `Hmax*`, `Hmin*` | Yes | Number | Temperature setpoints (°C, 5–35) |
| `Hposun*`, `hposun*`, `Hyst*`, `hyst*`, `posun*`, `Posun*`, `dT*`, `delta*` | Yes | Number | Offset / hysteresis values (°C, −10–10) |
| `Zap*`, `Povol*`, `RUC*`, `AUT*`, `Blok*`, `zapni*` | Yes | Switch | On/off controls |
| `Por*`, `ALARM*`, `HAVARIE*`, `Odtavani*`, `Leto*`, `TOPIT*`, `Stav*` | No | Binary Sensor | Alarms and states |
| any other readable variable | No | Sensor | Generic numeric sensor |
| any other readable variable | Yes | Number | Generic adjustable number |

Variables that match a **read-only prefix** (`TE*`, `Por*`, `ALARM*`, `Stav*`, `status*`, `CO2_*`, etc.) are automatically locked as read-only by the Biosuntec profile regardless of the writable selection.

The **Generic** profile creates plain numeric sensors and number controls, without Biosuntec naming rules, temperature units, switches, or binary sensors. Existing Generic entities previously classified as switches or binary sensors will be replaced by number or sensor entities; update automations using those entity IDs. Biosuntec and configurations without a profile retain their existing classification and identifier formats.

Read-only variables are excluded from the writable selection. Older selections and imported backups cannot override the current profile's read-only policy; those variables remain monitored.

To identify the PLC variable behind a sensor, number, switch, or binary sensor, open the entity's detail and expand **Attributes**. The `variable_name` attribute (displayed as **Variable name** in English) contains the original PLC name, alongside `wid` when readings are available. The original name remains available when the entity is unavailable and stays independent of the custom entity name and entity ID.

## Live Variable Monitor

Open **AMiT Monitor** in the Home Assistant sidebar with an administrator account. The panel appears when at least one AMiT entry is loaded and the Home Assistant frontend is enabled. It supports Czech and English, follows the active theme, and adapts to mobile screens.

To hide or show the sidebar item, open your **User profile → Appearance**, then select **Edit** next to the option for changing the order and hiding sidebar items. Toggle **AMiT Monitor** there. This changes the shortcut's visibility; it does not stop a monitor that is still open. Close or pause the monitor to stop its subscription. See [Home Assistant's profile documentation](https://www.home-assistant.io/docs/configuration/user-configuration/).

1. Choose the PLC in the header.
2. Search by PLC variable name, Home Assistant entity name, or WID. Combine the type filter with **All variables / With HA entity**.
3. Select variables to start recording new readings in their graphs.
4. Use the graph pointer or sample slider to inspect an actual reading and its time. The slider also supports keyboard navigation.

The table includes all variables discovered by the selected target profile, including variables without Home Assistant entities. It reads Int16, Int32, and Float values. Arrays, time arrays, and structures remain listed as unsupported for reading. The table shows 50 rows per page; the graph area shows four selected variables per page. Other selected variables continue recording while their graphs are on another page.

For variables with HA entities, the table and graphs show their entity names, including custom names. The original PLC name, WID, and entity IDs remain visible below. Disabled entities are marked and included in **With HA entity**; a variable selected in configuration without a registry entity is marked separately. Renaming an entity updates its labels without interrupting the graph. Filtering the table keeps the selection and continues recording hidden variables.

Values are raw decoded PLC readings. Units come from the target profile where available. Entity-specific filtering is not applied: for example, a temperature value that an existing sensor treats as unavailable can still appear in the monitor. Failed or invalid readings create gaps in graphs instead of zeros. Each reading carries its own timestamp; an old value is not presented as a new measurement.

### Add selected variables as Home Assistant entities

1. Select readable variables in the table, then click **Add selected as HA entities** in the graph section. The preview includes the whole selection, including variables hidden by filters or on other table and graph pages.
2. Check the PLC, variable names and WIDs, existing entities, and configuration changes. If the device uses **all readable variables**, that setting stays enabled: reloading can also add the other variables listed in the preview.
3. Click **Save and load entities** to save the selection in Home Assistant and reload that AMiT entry. **Cancel** closes the preview without saving. A selection already configured with no changes needed has no save action.

The saved selection includes the existing variables and preserves other device settings and entity customizations. New variables are added for reading. Existing valid write permissions are retained; obsolete permissions shown in the preview are removed. This action does not write control values to the PLC or change its program. Existing disabled entities stay disabled.

Saving and loading are reported separately. **Selection saved** means that Home Assistant has accepted the configuration; it does not yet mean that the device has loaded successfully. If Home Assistant is waiting to retry, the monitor shows that state. A loading failure leaves the saved selection in place; check the integration in **Settings → Devices & services**. When a connection interruption prevents verification of the confirmation, the monitor reports an unknown result: refresh the PLC list and prepare a new preview before trying again.

Changing the PLC closes the preview. Changes to the selection, variable definitions, entity information, or configuration can require a new preview. Previews expire after five minutes. Reloading clears the old temporary monitor history; samples collected in the new session are kept when a delayed loading result arrives. Permanently added entities use Home Assistant's normal history settings, including Recorder exclusions.

### Temporary history

- History starts with the next new reading after selection. Initial snapshots update the table without adding old readings to a graph.
- History stays only in the open panel's memory. Selecting variables for graphs does not create entities or save these graph samples to Recorder, files, or browser storage. Entities explicitly added with **Add selected as HA entities** retain their normal Home Assistant history behavior.
- The limit is **2,000 samples per variable and 50,000 samples in total**. The oldest samples are removed when a limit is reached.
- Deselecting a variable clears its series. **Clear history** removes recorded samples while keeping the current selection and latest table values.
- Leaving the monitor, reloading the page, changing PLC, or destroying the panel clears its history and selection.
- **Pause** and a hidden browser tab stop the panel's live subscription. Existing integration polling continues. Returning to the monitor keeps the available in-memory history and starts a new graph segment. Home Assistant can destroy a suspended panel; a recreated panel starts a new session.
- A connection interruption keeps existing graph samples. Reconnection updates the table from a snapshot and resumes recording new samples without filling the missed interval.

PLC values in the panel are read-only. It shares ordinary polling results and uses one additional reader per PLC for other readable variables while viewers are connected. Extra reads run sequentially, with at least 0.2 seconds between requests and a delay after transport errors. Large catalogs and slow PLC replies can make a full scan longer than the configured interval. Check each value's reading time and age. Opening several panels does not multiply the extra PLC reads. The monitor currently has no separate reading-interval control.

### Monitor troubleshooting

- If the panel is missing, check administrator access, frontend availability, and whether an AMiT entry has finished loading.
- If a PLC is unavailable, the monitor keeps that selection instead of switching to another device. Use **Refresh PLC list** after the entry recovers, or select another PLC explicitly.
- After an integration update, reload the browser page to load the current panel code. This clears the temporary session.

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

Write a value to a monitored PLC variable selected for writing in the integration configuration. The target profile's read-only policy also applies. With multiple PLCs, include the config entry ID in `entry_id`. An explicitly supplied ID must identify a loaded PLC; unknown or unavailable IDs cause an error without writing to another device. Omitting `entry_id` selects the only loaded PLC when exactly one is available.

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

## Target Profiles

When adding the integration you choose a **Target system** that controls which variables are loaded and how they are classified:

| Profile | Key | WID range | Read-only detection | Description |
|---------|-----|-----------|---------------------|-------------|
| **Biosuntec** | `biosuntec` | 4000–6000 | Yes (by name prefix) | Biosuntec HVAC systems (fan coils, floor heating, recuperation, DHW) controlled via AMiT PLC |
| **Generic AMiT PLC** | `generic` | all | No | Any AMiT DB-Net/IP device without product-specific variable filtering |

The Biosuntec profile automatically marks measurement variables (temperatures, alarms, states, CO₂) as read-only so they cannot accidentally be written to.  Adding a new product type requires only a new profile entry in `targets.py`.

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
│       ├── entity.py
│       ├── protocol.py
│       ├── monitor.py
│       ├── websocket.py
│       ├── frontend.py
│       ├── frontend/
│       │   └── monitor.js
│       ├── targets.py
│       ├── sensor.py
│       ├── number.py
│       ├── switch.py
│       ├── binary_sensor.py
│       ├── button.py
│       ├── manifest.json
│       ├── services.yaml
│       ├── strings.json
│       ├── biosuntec/
│       │   ├── __init__.py
│       │   └── heuristics.py
│       └── translations/
│           ├── en.json
│           └── cs.json
└── www/
    └── amit/
        └── amit_export_*.json  (backup files)
```

## Contributing

Offline backend tests use Python's standard test runner:

```sh
python -B -m unittest discover -s tests -q
```

History and number-formatting tests use Node.js without additional packages:

```sh
node --test tests/test_monitor_frontend.mjs
```

With Playwright and Chromium available in the development environment, run the browser scenarios:

```sh
node tests/test_monitor_ui.cjs
```

The browser runner accepts `AMIT_PLAYWRIGHT_MODULE` and `AMIT_CHROME_PATH` for existing installations in non-default locations. It uses a simulated Home Assistant connection and does not contact a PLC. Screenshots are written only when `AMIT_SCREENSHOT_DIR` is set; these contain simulated data.

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file.

## Credits

- Protocol reverse-engineering based on Wireshark analysis of DetStudio communication
- Developed for home automation of heating systems controlled by AMiT PLCs
