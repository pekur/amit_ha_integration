"""Button platform for AMiT integration."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import aiofiles

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_STATION_ADDR,
    CONF_CLIENT_ADDR,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_STATION_ADDR,
    DEFAULT_CLIENT_ADDR,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AMiT button entities."""
    async_add_entities([
        AMiTExportButton(hass, entry),
        AMiTReloadButton(hass, entry),
    ])


class AMiTExportButton(ButtonEntity):
    """Button to export AMiT configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self.hass = hass
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_export_config"
        self._attr_name = "Export Configuration"
        self._attr_icon = "mdi:download"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    async def async_press(self) -> None:
        """Handle button press - export configuration."""
        entry = self._entry
        data = self.hass.data[DOMAIN][entry.entry_id]
        variables = data["variables"]
        writable_wids = data["writable_wids"]
        
        # Get entity registry
        ent_reg = er.async_get(self.hass)
        
        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "plc_connection": {
                "host": entry.data[CONF_HOST],
                "port": entry.data.get(CONF_PORT, DEFAULT_PORT),
                "station_addr": entry.data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR),
                "client_addr": entry.data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR),
            },
            "scan_interval": entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            "monitored_variables": [],
            "writable_variables": [],
        }
        
        # Get all entities for this config entry
        entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        
        _LOGGER.debug(f"Found {len(entity_entries)} entities for export")
        
        # Create lookup: wid -> entity info (extract WID from unique_id)
        entity_info_by_wid = {}
        for entity_entry in entity_entries:
            _LOGGER.debug(f"Entity: {entity_entry.entity_id}, unique_id: {entity_entry.unique_id}, name: {entity_entry.name}, original_name: {entity_entry.original_name}")
            
            # Extract WID from unique_id (it's the numeric part)
            parts = entity_entry.unique_id.split("_")
            wid = None
            for part in reversed(parts):
                if part.isdigit():
                    wid = int(part)
                    break
            
            if wid:
                entity_info_by_wid[wid] = {
                    "entity_id": entity_entry.entity_id,
                    "custom_name": entity_entry.name,
                    "original_name": entity_entry.original_name,
                    "platform": entity_entry.platform,
                    "disabled": entity_entry.disabled,
                }
        
        _LOGGER.debug(f"Entity info by WID: {entity_info_by_wid}")
        
        # Process all selected variables
        for variable in variables:
            ent_info = entity_info_by_wid.get(variable.wid)
            
            var_export = {
                "wid": variable.wid,
                "plc_name": variable.name,
                "var_type": variable.var_type.value if hasattr(variable.var_type, 'value') else variable.var_type,
                "type_name": variable.type_name,
            }
            
            if ent_info:
                var_export["entity_id"] = ent_info["entity_id"]
                if ent_info["custom_name"]:
                    var_export["custom_name"] = ent_info["custom_name"]
                var_export["original_name"] = ent_info["original_name"]
                var_export["disabled"] = ent_info["disabled"]
            
            if variable.wid in writable_wids:
                var_export["writable"] = True
                export_data["writable_variables"].append(var_export)
            else:
                export_data["monitored_variables"].append(var_export)
        
        # Write to file in www folder for download access
        www_dir = Path(self.hass.config.config_dir) / "www" / "amit"
        www_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"amit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        export_path = www_dir / filename
        
        try:
            async with aiofiles.open(export_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(export_data, indent=2, ensure_ascii=False))
            
            _LOGGER.info(f"Exported AMiT config to {export_path}")
            
            # Create persistent notification with download link
            download_url = f"/local/amit/{filename}"
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "AMiT Export Complete",
                    "message": f"Configuration exported successfully!\n\n"
                              f"- {len(export_data['monitored_variables'])} monitored variables\n"
                              f"- {len(export_data['writable_variables'])} writable variables\n\n"
                              f"**[⬇️ Download {filename}]({download_url})**",
                    "notification_id": "amit_export",
                },
            )
        except Exception as e:
            _LOGGER.error(f"Failed to export config: {e}")
            raise


class AMiTReloadButton(ButtonEntity):
    """Button to reload variables from PLC."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self.hass = hass
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_reload_variables"
        self._attr_name = "Reload Variables"
        self._attr_icon = "mdi:refresh"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    async def async_press(self) -> None:
        """Handle button press - reload variables from PLC."""
        data = self.hass.data[DOMAIN][self._entry.entry_id]
        client = data["client"]
        
        all_vars = await client.load_variables()
        data["all_variables"] = all_vars
        
        _LOGGER.info(f"Reloaded {len(all_vars)} variables from PLC")
        
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "AMiT Variables Reloaded",
                "message": f"Loaded {len(all_vars)} variables from PLC.\n\n"
                          f"Go to integration options to select new variables.",
                "notification_id": "amit_reload",
            },
        )
