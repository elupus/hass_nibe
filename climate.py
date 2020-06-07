"""Climate entities for nibe uplink."""

import asyncio
import logging
from collections import OrderedDict
from datetime import timedelta
from typing import List, Set

from homeassistant.components.climate import ENTITY_ID_FORMAT, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_IDLE,
    HVAC_MODE_AUTO,
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_COOL,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

from nibeuplink import (
    PARAM_PUMP_SPEED_HEATING_MEDIUM,
    ClimateSystem,
    SetThermostatModel,
    Uplink,
    get_active_climate,
)

from . import NibeSystem
from .const import (
    ATTR_TARGET_TEMPERATURE,
    ATTR_VALVE_POSITION,
    CONF_CLIMATE_SYSTEMS,
    CONF_CURRENT_TEMPERATURE,
    CONF_THERMOSTATS,
    CONF_VALVE_POSITION,
    DATA_NIBE,
    DEFAULT_THERMOSTAT_TEMPERATURE,
)
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE].uplink  # type: Uplink
    systems = hass.data[DATA_NIBE].systems  # type: List[NibeSystem]

    entities = []

    async def add_active(system: NibeSystem):
        climates = await get_active_climate(uplink, system.system_id)
        for climate in climates.values():
            entities.append(
                NibeClimateSupply(uplink, system.system_id, system.statuses, climate)
            )
            entities.append(
                NibeClimateRoom(uplink, system.system_id, system.statuses, climate)
            )

    for system in systems.values():
        thermostats = system.config[CONF_THERMOSTATS]
        for thermostat_id, thermostat_config in thermostats.items():
            entities.append(
                NibeThermostat(
                    uplink,
                    system.system_id,
                    thermostat_id,
                    thermostat_config.get(CONF_NAME),
                    thermostat_config.get(CONF_CURRENT_TEMPERATURE),
                    thermostat_config.get(CONF_VALVE_POSITION),
                    thermostat_config.get(CONF_CLIMATE_SYSTEMS),
                )
            )

    await asyncio.gather(
        *[
            add_active(system)
            for system in systems.values()
        ]
    )

    async_add_entities(entities, True)


class NibeClimate(NibeEntity, ClimateEntity):
    """Base class for nibe climate entities."""

    def __init__(
        self, uplink, system_id: int, statuses: Set[str], climate: ClimateSystem
    ):
        """Init."""
        super(NibeClimate, self).__init__(uplink, system_id)

        self.get_parameters([PARAM_PUMP_SPEED_HEATING_MEDIUM])

        self._climate = climate
        self._status = "DONE"
        self._hvac_action = CURRENT_HVAC_IDLE
        self._hvac_mode = HVAC_MODE_HEAT
        self._hvac_modes = [HVAC_MODE_HEAT_COOL, HVAC_MODE_HEAT, HVAC_MODE_COOL]
        self.parse_statuses(statuses)

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN_NIBE, self._system_id, self._climate.supply_temp)},
            "via_device": (DOMAIN_NIBE, self._system_id),
            "name": f"Climate System {self._climate.name}",
            "model": "Climate System",
            "manufacturer": "NIBE Energy Systems",
        }

    @property
    def name(self):
        """Return entity name."""
        return self._climate.name

    @property
    def device_state_attributes(self):
        """Extra state attributes."""
        data = OrderedDict()
        data["status"] = self._status
        data["pump_speed_heating_medium"] = self.get_float(
            PARAM_PUMP_SPEED_HEATING_MEDIUM
        )

        return data

    @property
    def supported_features(self):
        """Supported features."""
        return SUPPORT_TARGET_TEMPERATURE_RANGE | SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_action(self):
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_action

    @property
    def hvac_mode(self):
        """Return mode heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return operation list."""
        return self._hvac_modes

    @property
    def unique_id(self):
        """Return unique identifier."""
        return "{}_{}".format(self._system_id, self._climate.name)

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode.

        This method must be run in the event loop and returns a coroutine.
        """
        if hvac_mode in self._hvac_modes:
            self._hvac_mode = hvac_mode
            await self.async_update_ha_state()

    async def async_set_temperature_internal(self, parameter, data):
        """Set temperature."""
        _LOGGER.debug("Set temperature on parameter {} to {}".format(parameter, data))

        try:
            self._status = await self._uplink.put_parameter(
                self._system_id, parameter, data
            )
        except BaseException:
            self._status = "ERROR"
            raise
        finally:
            _LOGGER.debug("Put parameter response {}".format(self._status))

    async def async_statuses_updated(self, system_id: int, statuses: Set[str]):
        """Statuses have been updated."""
        if system_id != self._system_id:
            return
        self.parse_statuses(statuses)
        self.parse_data()
        self.async_schedule_update_ha_state()

    def parse_statuses(self, statuses: Set[str]):
        """Parse status list."""
        if "Cooling (Passive)" in statuses:
            self._hvac_action = CURRENT_HVAC_COOL
        elif "Heating" in statuses:
            self._hvac_action = CURRENT_HVAC_HEAT
        elif "Cooling" in statuses:
            self._hvac_action = CURRENT_HVAC_COOL
        else:
            self._hvac_action = CURRENT_HVAC_IDLE


class NibeClimateRoom(NibeClimate):
    """Climate entity for a room temperature sensor."""

    def __init__(
        self, uplink, system_id: int, statuses: Set[str], climate: ClimateSystem
    ):
        """Init."""
        super().__init__(uplink, system_id, statuses, climate)

        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}_room".format(DOMAIN_NIBE, system_id, str(climate.name))
        )

        self.get_parameters(
            [
                self._climate.room_temp,
                self._climate.room_setpoint_heat,
                self._climate.room_setpoint_cool,
            ]
        )

    @property
    def available(self):
        """Is entity available."""
        return self.get_value(self._climate.room_temp) is not None

    @property
    def temperature_unit(self):
        """Return temperature unit used."""
        data = self._parameters[self._climate.room_temp]
        if data:
            return data["unit"]
        else:
            return TEMP_CELSIUS

    @property
    def name(self):
        """Return name of entity."""
        return "{} Room".format(self._climate.name)

    @property
    def unique_id(self):
        """Return unique id of entity."""
        return "{}_{}".format(super().unique_id, "room")

    @property
    def max_temp(self):
        """Return maximium selectable temperature."""
        return 35.0

    @property
    def min_temp(self):
        """Return minimum selectable temperature."""
        return 5.0

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self.get_float(self._climate.room_temp)

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT:
            return self.get_float(self._climate.room_setpoint_heat)
        elif self._hvac_mode == HVAC_MODE_COOL:
            return self.get_float(self._climate.room_setpoint_cool)
        else:
            return None

    @property
    def target_temperature_low(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.room_setpoint_heat)
        else:
            return None

    @property
    def target_temperature_high(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.room_setpoint_cool)
        else:
            return None

    @property
    def target_temperature_step(self):
        """Return steps that temperature can be selected in."""
        return 0.5

    async def async_set_temperature(self, **kwargs):
        """Set temperature."""
        if ATTR_TARGET_TEMP_HIGH in kwargs:
            await self.async_set_temperature_internal(
                self._climate.room_setpoint_cool, kwargs[ATTR_TARGET_TEMP_HIGH]
            )

        if ATTR_TARGET_TEMP_LOW in kwargs:
            await self.async_set_temperature_internal(
                self._climate.room_setpoint_heat, kwargs[ATTR_TARGET_TEMP_LOW]
            )

        if ATTR_TARGET_TEMPERATURE in kwargs:
            await self.async_set_temperature_internal(
                self._climate.room_setpoint_heat, kwargs[ATTR_TARGET_TEMPERATURE]
            )


class NibeClimateSupply(NibeClimate):
    """Climate entity for supply temperature."""

    def __init__(
        self, uplink, system_id: int, statuses: Set[str], climate: ClimateSystem
    ):
        """Init."""
        super().__init__(uplink, system_id, statuses, climate)

        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}_supply".format(DOMAIN_NIBE, system_id, str(climate.name))
        )

        self.get_parameters(
            [
                self._climate.supply_temp,
                self._climate.calc_supply_temp_heat,
                self._climate.calc_supply_temp_cool,
                self._climate.offset_heat,
                self._climate.offset_cool,
                self._climate.external_adjustment_active,
            ]
        )

    @property
    def available(self):
        """Is entity available."""
        return self.get_value(self._climate.supply_temp) is not None

    @property
    def temperature_unit(self):
        """Return used temperature unit."""
        data = self._parameters[self._climate.supply_temp]
        if data:
            return data["unit"]
        else:
            return None

    @property
    def name(self):
        """Return name of entity."""
        return "{} Supply".format(self._climate.name)

    @property
    def unique_id(self):
        """Return unique id of entity."""
        return "{}_{}".format(super().unique_id, "supply")

    @property
    def max_temp(self):
        """Return maximium selectable temperature."""
        return 50.0

    @property
    def min_temp(self):
        """Return minimum selectable temperature."""
        return 5.0

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self.get_float(self._climate.supply_temp)

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT:
            return self.get_float(self._climate.calc_supply_temp_heat)
        elif self._hvac_mode == HVAC_MODE_COOL:
            return self.get_float(self._climate.calc_supply_temp_cool)
        else:
            return None

    @property
    def target_temperature_low(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.calc_supply_temp_heat)
        else:
            return None

    @property
    def target_temperature_high(self):
        """Return target temperature."""
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.calc_supply_temp_cool)
        else:
            return None

    @property
    def target_temperature_step(self):
        """Return steps that temperature can be selected in."""
        return 1.0

    async def async_set_temperature(self, **kwargs):
        """Set current temperature."""

        async def set_temperature(calc_id, offset_id, value):
            # calculate what offset was used to calculate the target
            base = self.get_float(calc_id, 0) - self.get_float(offset_id, 0)
            await self.async_set_temperature_internal(offset_id, value - base)

        if ATTR_TARGET_TEMP_HIGH in kwargs:
            await set_temperature(
                self._climate.calc_supply_temp_cool,
                self._climate.offset_cool,
                kwargs[ATTR_TARGET_TEMP_HIGH],
            )

        if ATTR_TARGET_TEMP_LOW in kwargs:
            await set_temperature(
                self._climate.calc_supply_temp_heat,
                self._climate.offset_heat,
                kwargs[ATTR_TARGET_TEMP_LOW],
            )

        if ATTR_TARGET_TEMPERATURE in kwargs:
            if self._hvac_mode == HVAC_MODE_HEAT:
                await set_temperature(
                    self._climate.calc_supply_temp_heat,
                    self._climate.offset_heat,
                    kwargs[ATTR_TARGET_TEMPERATURE],
                )
            elif self._hvac_mode == HVAC_MODE_COOL:
                await set_temperature(
                    self._climate.calc_supply_temp_cool,
                    self._climate.offset_cool,
                    kwargs[ATTR_TARGET_TEMPERATURE],
                )

    @property
    def device_state_attributes(self):
        """Return extra state."""
        data = super().device_state_attributes
        data["offset_heat"] = self.get_float(self._climate.offset_heat)
        data["offset_cool"] = self.get_float(self._climate.offset_cool)
        data["external_adjustment_active"] = self.get_bool(
            self._climate.external_adjustment_active
        )

        return data


class NibeThermostat(ClimateEntity, RestoreEntity):
    """Nibe Smarthome Thermostat."""

    def __init__(
        self,
        uplink,
        system_id: int,
        external_id: int,
        name: str,
        current_temperature_id: str,
        valve_position_id: str,
        systems: List[int],
    ):
        """Init."""
        self._name = name
        self._uplink = uplink
        self._system_id = system_id
        self._external_id = external_id
        self._hvac_mode = HVAC_MODE_OFF
        self._hvac_modes = [HVAC_MODE_OFF, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO]
        self._hvac_action = CURRENT_HVAC_IDLE
        self._current_temperature_id = current_temperature_id
        self._current_temperature = None
        self._valve_position_id = valve_position_id
        self._valve_position = None
        self._systems = systems
        self._target_temperature = DEFAULT_THERMOSTAT_TEMPERATURE
        self._scheduled_update = None

    async def async_added_to_hass(self):
        """Run whe?n entity about to be added."""
        await super().async_added_to_hass()
        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            self._target_temperature = old_state.attributes.get(
                ATTR_TARGET_TEMPERATURE, DEFAULT_THERMOSTAT_TEMPERATURE
            )
            if old_state.state:
                self._hvac_mode = old_state.state

        def track_entity_id(tracked_entity_id, update_fun):
            if tracked_entity_id:

                async def changed(entity_id, old_state, new_state):
                    update_fun(new_state)
                    await self._async_publish()
                    await self.async_update_ha_state()

                update_fun(self.hass.states.get(tracked_entity_id))

                async_track_state_change(self.hass, tracked_entity_id, changed)

        track_entity_id(self._current_temperature_id, self._update_current_temperature)
        track_entity_id(self._valve_position_id, self._update_valve_position)

        self._schedule()

    def _schedule(self):
        if self._scheduled_update:
            self._scheduled_update()
        self._scheduled_update = async_track_time_interval(
            self.hass, self._async_publish, timedelta(minutes=15)
        )

    @property
    def unique_id(self):
        """Return unique id of entity."""
        return "{}_{}_thermostat_{}".format(
            DOMAIN_NIBE, self._system_id, self._external_id
        )

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN_NIBE, self._system_id, self._external_id)},
            "via_device": (DOMAIN_NIBE, self._system_id),
            "name": f"Thermostat: {self._name}",
            "model": "Smart Thermostat",
            "manufacturer": "NIBE Energy Systems",
        }

    @property
    def name(self):
        """Return name."""
        return self._name

    @property
    def temperature_unit(self):
        """Return temperature unit."""
        return TEMP_CELSIUS

    @property
    def device_state_attributes(self):
        """Return extra state."""
        data = OrderedDict()
        data[ATTR_VALVE_POSITION] = self._valve_position
        data[ATTR_TARGET_TEMPERATURE] = self._target_temperature
        return data

    @property
    def supported_features(self):
        """Return supported features."""
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self):
        """Return mode heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return operation list."""
        return self._hvac_modes

    @property
    def hvac_action(self):
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_action

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._hvac_mode != HVAC_MODE_OFF:
            return self._target_temperature
        else:
            return None

    @property
    def target_temperature_step(self):
        """Return steps for target temperature."""
        return 0.5

    @property
    def should_poll(self):
        """Indicate that we need to poll data."""
        return False

    def _update_current_temperature(self, state):
        if state is None:
            return
        try:
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._current_temperature = None
            else:
                self._current_temperature = float(state.state)
        except ValueError as ex:
            self._current_temperature = None
            _LOGGER.error("Unable to update from sensor: %s", ex)

    def _update_valve_position(self, state):
        if state is None:
            return
        try:
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._valve_position = None
            else:
                self._valve_position = float(state.state)
        except ValueError as ex:
            self._current_temperature = None
            _LOGGER.error("Unable to update from sensor: %s", ex)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        if hvac_mode in self._hvac_modes:
            self._hvac_mode = hvac_mode
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        await self._async_publish_update()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._target_temperature = temperature
        await self._async_publish_update()

    async def _async_publish_update(self):
        self._schedule()
        await self._async_publish()
        await self.async_update_ha_state()

    async def _async_publish(self, time=None):
        def scaled(value, multi=10):
            if value is None:
                return None
            else:
                return round(value * multi)

        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            actual = scaled(self._current_temperature)
            target = scaled(self._target_temperature)
            valve = scaled(self._valve_position, 1)
            systems = self._systems
        elif self._hvac_mode == HVAC_MODE_AUTO:
            actual = scaled(self._current_temperature)
            target = None
            valve = scaled(self._valve_position, 1)
            systems = self._systems
        else:
            actual = None
            target = None
            valve = None
            systems = []

        data: SetThermostatModel = {
            "externalId": self._external_id,
            "name": self._name,
            "actualTemp": actual,
            "targetTemp": target,
            "valvePosition": valve,
            "climateSystems": systems,
        }

        _LOGGER.debug("Publish thermostat {}".format(data))
        await self._uplink.post_smarthome_thermostats(self._system_id, data)

    async def async_update(self):
        """Explicitly update thermostat state."""
        _LOGGER.debug("Update thermostat {}".format(self.name))
