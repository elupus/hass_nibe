"""Base entites for nibe."""
from __future__ import annotations

import logging
from typing import Dict, Optional

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from nibeuplink.typing import ParameterId, ParameterType

from . import NibeSystem
from .const import DOMAIN as DOMAIN_NIBE

ParameterSet = Dict[ParameterId, Optional[ParameterType]]

_LOGGER = logging.getLogger(__name__)

UNIT_ICON = {"A": "mdi:power-plug", "Hz": "mdi:update", "h": "mdi:clock"}


class NibeEntity(CoordinatorEntity[None]):
    """Base class for all nibe sytem entities."""

    def __init__(
        self,
        system: NibeSystem,
        parameters: set[ParameterId | None],
    ):
        """Initialize base class."""
        super().__init__(system)
        self._system = system
        self._uplink = system.uplink
        self._system_id = system.system_id
        self._attr_device_info = {"identifiers": {(DOMAIN_NIBE, self._system_id)}}
        self._parameters = parameters

    def get_parameter(self, parameter_id: ParameterId | None) -> ParameterType | None:
        """Get the full parameter dict."""
        if not parameter_id:
            return None
        return self._system.get_parameter(parameter_id)

    def get_bool(self, parameter_id: ParameterId | None) -> bool | None:
        """Get bool parameter."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["value"] is None:
            return False
        else:
            return bool(data["value"])

    def get_float(
        self, parameter_id: ParameterId | None, default: float | None = None
    ) -> float | None:
        """Get float parameter."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["value"] is None:
            return default
        else:
            return float(data["value"])

    def get_value(self, parameter_id: ParameterId | None, default=None):
        """Get value in display format."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["value"] is None:
            return default
        else:
            return data["value"]

    def get_unit(
        self, parameter_id: ParameterId | None, default: str | None = None
    ) -> str | None:
        """Get value in display format."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["unit"] is None:
            return default
        else:
            return data["unit"]

    def get_raw(self, parameter_id: ParameterId | None, default=None):
        """Get value in display format."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["rawValue"] is None:
            return default
        else:
            return data["rawValue"]

    def get_scale(self, parameter_id: ParameterId | None) -> float | None:
        """Calculate scale of parameter."""
        if not parameter_id:
            return None
        data = self._system.get_parameter(parameter_id)
        if data is None or data["value"] is None:
            return 1.0
        else:
            return float(data["rawValue"]) / float(data["value"])

    def parse_data(self):
        """Parse data to update internal variables."""
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.parse_data()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(self._system.add_parameter_subscriber(self._parameters))

    async def async_update(self):
        """Handle request to update this entity."""
        if not self.enabled:
            return

        _LOGGER.debug("Update %s", self.entity_id)
        await self._system.update_parameters(self._parameters)
        self.parse_data()


class NibeParameterEntity(NibeEntity):
    """Base class with common attributes for parameter entities."""

    def __init__(
        self,
        system: NibeSystem,
        parameter_id: ParameterId,
        entity_id_format: str | None = None,
    ):
        """Initialize base class for parameters."""
        super().__init__(system, parameters={parameter_id})
        self._parameter_id = parameter_id
        self._value = None
        self._attr_unique_id = "{}_{}".format(system.system_id, parameter_id)
        self._attr_name = None
        self._attr_icon = None

        self.parse_data()

        if entity_id_format:
            self.entity_id = entity_id_format.format(
                "{}_{}_{}".format(DOMAIN_NIBE, system.system_id, str(parameter_id))
            )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        data = self.get_parameter(self._parameter_id)
        if data:
            return {
                "designation": data["designation"],
                "parameter_id": data["parameterId"],
                "display_value": data["displayValue"],
                "raw_value": data["rawValue"],
                "display_unit": data["unit"],
            }
        else:
            return {}

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self._value is not None

    def parse_data(self):
        """Parse data to update internal variables."""
        data = self.get_parameter(self._parameter_id)
        if data:
            if self._attr_name is None:
                self._attr_name = data["title"]
            self._attr_icon = UNIT_ICON.get(data["unit"], None)
            self._value = data["value"]
        else:
            self._value = None
