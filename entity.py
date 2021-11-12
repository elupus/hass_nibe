"""Base entites for nibe."""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.helpers.entity import Entity
from nibeuplink import Uplink
from nibeuplink.typing import Parameter, ParameterId, ParameterType

from .const import DOMAIN as DOMAIN_NIBE
from .const import SCAN_INTERVAL, SIGNAL_PARAMETERS_UPDATED, SIGNAL_STATUSES_UPDATED
from .services import async_track_delta_time

ParameterSet = Dict[ParameterId, Optional[Parameter]]

_LOGGER = logging.getLogger(__name__)

UNIT_ICON = {"A": "mdi:power-plug", "Hz": "mdi:update", "h": "mdi:clock"}


class NibeEntity(Entity):
    """Base class for all nibe sytem entities."""

    def __init__(
        self,
        uplink: Uplink,
        system_id: int,
        parameters: ParameterSet | None = None,
    ):
        """Initialize base class."""
        super().__init__()
        self._uplink = uplink
        self._system_id = system_id
        self._parameters: ParameterSet = OrderedDict()
        self._attr_device_info = {"identifiers": {(DOMAIN_NIBE, self._system_id)}}
        self._attr_should_poll = False
        if parameters:
            self._parameters.update(parameters)

    def get_parameters(self, parameter_ids: list[ParameterId | None]):
        """Register a parameter for retrieval."""
        for parameter_id in parameter_ids:
            if parameter_id and parameter_id not in self._parameters:
                self._parameters[parameter_id] = None

    def get_bool(self, parameter_id: ParameterId | None):
        """Get bool parameter."""
        if not parameter_id:
            return None
        data = self._parameters[parameter_id]
        if data is None or data["value"] is None:
            return False
        else:
            return bool(data["value"])

    def get_float(self, parameter_id: ParameterId | None, default=None):
        """Get float parameter."""
        if not parameter_id:
            return None
        data = self._parameters[parameter_id]
        if data is None or data["value"] is None:
            return default
        else:
            return float(data["value"])

    def get_value(self, parameter_id: ParameterId | None, default=None):
        """Get value in display format."""
        if not parameter_id:
            return None
        data = self._parameters[parameter_id]
        if data is None or data["value"] is None:
            return default
        else:
            return data["value"]

    def get_raw(self, parameter_id: ParameterId | None, default=None):
        """Get value in display format."""
        if not parameter_id:
            return None
        data = self._parameters[parameter_id]
        if data is None or data["rawValue"] is None:
            return default
        else:
            return data["rawValue"]

    def get_scale(self, parameter_id: ParameterId | None):
        """Calculate scale of parameter."""
        if not parameter_id:
            return None
        data = self._parameters[parameter_id]
        if data is None or data["value"] is None:
            return 1.0
        else:
            return float(data["rawValue"]) / float(data["value"])

    def parse_data(self):
        """Parse data to update internal variables."""
        pass

    async def async_parameters_updated(
        self, system_id: int, data: dict[str, dict[str, Any]]
    ):
        """Handle updated parameter."""
        if system_id != self._system_id:
            return

        changed = False
        for key, value in data.items():
            if key in self._parameters:
                value2 = dict(value)
                value2["timeout"] = datetime.now() + timedelta(
                    seconds=(SCAN_INTERVAL * 2)
                )
                _LOGGER.debug("Data changed for %s %s", self.entity_id, key)
                changed = True
                self._parameters[key] = value2

        if changed:
            self.parse_data()
            self.async_schedule_update_ha_state()

    async def async_statuses_updated(self, system_id, data):
        """Handle update of status."""
        pass

    async def async_added_to_hass(self):
        """Handle when entity is added to home assistant."""
        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_PARAMETERS_UPDATED, self.async_parameters_updated
            )
        )

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_STATUSES_UPDATED, self.async_statuses_updated
            )
        )

        async def update():
            await self.async_update()
            await self.async_update_ha_state()

        self.async_on_remove(async_track_delta_time(self.hass, SCAN_INTERVAL, update))

    async def async_update(self):
        """Update of entity."""
        _LOGGER.debug("Update %s", self.entity_id)

        def timedout(data):
            if data:
                timeout = data.get("timeout")
                if timeout and datetime.now() < timeout:
                    _LOGGER.debug(
                        "Skipping update for %s %s", self.entity_id, data["parameterId"]
                    )
                    return False
            return True

        async def get(parameter_id):
            self._parameters[parameter_id] = await self._uplink.get_parameter(
                self._system_id, parameter_id
            )

        await asyncio.gather(
            *[
                get(parameter_id)
                for parameter_id, data in self._parameters.items()
                if timedout(data)
            ]
        )

        self.parse_data()


class NibeParameterEntity(NibeEntity):
    """Base class with common attributes for parameter entities."""

    def __init__(
        self,
        uplink: Uplink,
        system_id: int,
        parameter_id: ParameterId,
        data: ParameterType | None = None,
        entity_id_format: str | None = None,
    ):
        """Initialize base class for parameters."""
        super().__init__(uplink, system_id, parameters={parameter_id: data})
        self._parameter_id = parameter_id
        self._value = None
        self._attr_unique_id = "{}_{}".format(system_id, parameter_id)
        self._attr_name = None
        self._attr_icon = None

        if data:
            self.parse_data()

        if entity_id_format:
            self.entity_id = entity_id_format.format(
                "{}_{}_{}".format(DOMAIN_NIBE, system_id, str(parameter_id))
            )

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        data = self._parameters[self._parameter_id]
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
        if self._value is None:
            return False
        else:
            return True

    def parse_data(self):
        """Parse data to update internal variables."""
        data = self._parameters[self._parameter_id]
        if data:
            if self._attr_name is None:
                self._attr_name = data["title"]
            self._attr_icon = UNIT_ICON.get(data["unit"], None)
            self._value = data["value"]
        else:
            self._value = None
