"""Water heater entity for nibe uplink."""

import asyncio
import logging
from collections import OrderedDict
from typing import Set

import aiohttp

from homeassistant.components.water_heater import (
    ENTITY_ID_FORMAT,
    STATE_ECO,
    STATE_HEAT_PUMP,
    STATE_HIGH_DEMAND,
    SUPPORT_OPERATION_MODE,
    WaterHeaterEntity,
)
from homeassistant.const import STATE_OFF
from homeassistant.exceptions import PlatformNotReady

from nibeuplink import get_active_hotwater

from .const import DATA_NIBE
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)

OPERATION_AUTO = "auto"
OPERATION_BOOST_ONE_TIME = "boost_one_time"
OPERATION_BOOST_THREE_HOURS = "boost_three_hours"
OPERATION_BOOST_SIX_HOUR = "boost_six_hours"
OPERATION_BOOST_TWELVE_HOURS = "boost_twelve_hours"

NIBE_STATE_TO_HA = {
    "economy": {
        "state": STATE_ECO,
        "start": "start_temperature_water_economy",
        "stop": "stop_temperature_water_economy",
    },
    "normal": {
        "state": STATE_HEAT_PUMP,
        "start": "start_temperature_water_normal",
        "stop": "stop_temperature_water_normal",
    },
    "luxuary": {
        "state": STATE_HIGH_DEMAND,
        "start": "start_temperature_water_luxary",
        "stop": "stop_temperature_water_luxary",
    },
}

NIBE_BOOST_TO_OPERATION = {
    0: OPERATION_AUTO,
    1: OPERATION_BOOST_THREE_HOURS,
    2: OPERATION_BOOST_SIX_HOUR,
    3: OPERATION_BOOST_TWELVE_HOURS,
    4: OPERATION_BOOST_ONE_TIME,
}

HA_BOOST_TO_NIBE = {v: k for k, v in NIBE_BOOST_TO_OPERATION.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE].uplink
    systems = hass.data[DATA_NIBE].systems

    entities = []

    async def add_active(system):
        hwsyses = await get_active_hotwater(uplink, system.system_id)
        for hwsys in hwsyses.values():
            entities.append(
                NibeWaterHeater(uplink, system.system_id, system.statuses, hwsys)
            )

    await asyncio.gather(
        *[
            add_active(system)
            for system in systems.values()
        ]
    )

    async_add_entities(entities, True)


class NibeWaterHeater(NibeEntity, WaterHeaterEntity):
    """Water heater entity."""

    def __init__(self, uplink, system_id: int, statuses: Set[str], hwsys):
        """Init."""
        super().__init__(uplink, system_id)

        self._name = hwsys.name
        self._current_operation = STATE_OFF
        self._current_state = STATE_OFF
        self._hwsys = hwsys

        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}".format(DOMAIN_NIBE, self.unique_id)
        )

        self.get_parameters(
            [
                self._hwsys.hot_water_charging,
                self._hwsys.hot_water_comfort_mode,
                self._hwsys.hot_water_top,
                self._hwsys.start_temperature_water_economy,
                self._hwsys.start_temperature_water_normal,
                self._hwsys.start_temperature_water_luxary,
                self._hwsys.stop_temperature_water_economy,
                self._hwsys.stop_temperature_water_normal,
                self._hwsys.stop_temperature_water_luxary,
                self._hwsys.hot_water_boost,
            ]
        )
        self.parse_statuses(statuses)

    @property
    def name(self):
        """Return name of entity."""
        return self._name

    @property
    def temperature_unit(self):
        """Return temperature unit."""
        data = self._parameters[self._hwsys.hot_water_charging]
        if data:
            return data["unit"]
        else:
            return None

    @property
    def device_state_attributes(self):
        """Return extra state attributes."""
        data = OrderedDict()
        data["current_temperature"] = self.current_temperature
        data["target_temp_low"] = self.target_temperature_low
        data["target_temp_high"] = self.target_temperature_high
        return data

    @property
    def available(self):
        """Return if entity is available."""
        value = self.get_value(self._hwsys.hot_water_charging)
        return value is not None

    @property
    def is_on(self):
        """Is the entity on."""
        return self._is_on

    @property
    def supported_features(self):
        """Return supported operation modes."""
        return SUPPORT_OPERATION_MODE

    @property
    def state(self):
        """Return the current state."""
        if self._is_on:
            return self._current_state
        else:
            return STATE_OFF

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def current_temperature(self):
        """Returrn current temperature."""
        return self.get_float(self._hwsys.hot_water_charging)

    def get_float_named(self, name):
        """Return a float attribute for system."""
        parameter_id = getattr(self._hwsys, name, None)
        return self.get_float(parameter_id)

    def get_float_operation(self, name):
        """Return a float based on operation mode."""
        if self._current_operation == OPERATION_AUTO:
            mode = self.get_value(self._hwsys.hot_water_comfort_mode)
        else:
            mode = "luxuary"
        if mode in NIBE_STATE_TO_HA:
            return self.get_float_named(NIBE_STATE_TO_HA[mode][name])
        else:
            return None

    @property
    def target_temperature_high(self):
        """Return the target high temperature."""
        return self.get_float_operation("stop")

    @property
    def target_temperature_low(self):
        """Return the target low temperature."""
        return self.get_float_operation("start")

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return list(NIBE_BOOST_TO_OPERATION.values())

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        try:
            if operation_mode in HA_BOOST_TO_NIBE:
                await self._uplink.put_parameter(
                    self._system_id,
                    self._hwsys.hot_water_boost,
                    HA_BOOST_TO_NIBE[operation_mode],
                )
            else:
                _LOGGER.error("Operation mode %s not supported", operation_mode)
        except aiohttp.client_exceptions.ClientResponseError as e:
            _LOGGER.error("Error trying to set mode %s", str(e))

    @property
    def unique_id(self):
        """Return the unique id."""
        return "{}_{}_{}".format(
            self._system_id,
            self._hwsys.hot_water_charging,
            self._hwsys.hot_water_production,
        )

    async def async_statuses_updated(self, system_id: int, statuses: Set[str]):
        """React to statuses updated."""
        if system_id != self._system_id:
            return
        self.parse_statuses(statuses)
        self.parse_data()
        self.async_schedule_update_ha_state()

    def parse_statuses(self, statuses: Set[str]):
        """Parse status values."""
        if "Hot Water" in statuses:
            self._is_on = True
        else:
            self._is_on = False

    def parse_data(self):
        """Parse data values."""
        super().parse_data()

        mode = self.get_value(self._hwsys.hot_water_comfort_mode)
        if mode in NIBE_STATE_TO_HA:
            self._current_state = NIBE_STATE_TO_HA[mode]["state"]
        else:
            self._current_state = STATE_OFF

        boost = self.get_raw(self._hwsys.hot_water_boost)
        if boost in NIBE_BOOST_TO_OPERATION:
            self._current_operation = NIBE_BOOST_TO_OPERATION[boost]
        else:
            self._current_operation = None
