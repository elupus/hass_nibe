"""Update sensors for nibe uplink."""
from __future__ import annotations

from homeassistant.components.update import ENTITY_ID_FORMAT, UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NibeData, NibeSystem
from .const import DATA_NIBE_ENTRIES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]

    entities = [NibeUpdateSensor(system) for system in data.systems.values()]
    async_add_entities(entities, False)


class NibeUpdateSensor(CoordinatorEntity[NibeSystem], UpdateEntity):
    """Update sensor."""

    def __init__(self, system: NibeSystem):
        """Init."""
        super().__init__(system)
        self._attr_name = "software update"
        self._attr_device_info = {"identifiers": {(DOMAIN, system.system_id)}}
        self._attr_unique_id = f"{system.system_id}_system_update"
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{system.system_id}_update")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update when the coordinator updates."""
        if not self.coordinator.software:
            return
        self._attr_installed_version = self.coordinator.software["current"]["name"]
        if self.coordinator.software["upgrade"]:
            self._attr_latest_version = self.coordinator.software["upgrade"]["name"]
            self._attr_release_summary = self.coordinator.software["upgrade"][
                "releaseDate"
            ]
        else:
            self._attr_latest_version = self._attr_installed_version
            self._attr_release_summary = None
        self._attr_release_url = f"https://nibeuplink.com/System/{self.coordinator.system_id}/Support/Software"
        super()._handle_coordinator_update()
