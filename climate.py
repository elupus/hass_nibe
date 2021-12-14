"""Climate entities for nibe uplink."""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import timedelta
from typing import Callable

from homeassistant.components.climate import ENTITY_ID_FORMAT, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from nibeuplink import (
    PARAM_PUMP_SPEED_HEATING_MEDIUM,
    ClimateSystem,
    SetThermostatModel,
    get_active_climate,
)
from nibeuplink.typing import ParameterId

from . import NibeData, NibeSystem
from .const import (
    ATTR_TARGET_TEMPERATURE,
    ATTR_VALVE_POSITION,
    CONF_CLIMATE_SYSTEMS,
    CONF_CURRENT_TEMPERATURE,
    CONF_THERMOSTATS,
    CONF_VALVE_POSITION,
    DATA_NIBE_ENTRIES,
    DEFAULT_THERMOSTAT_TEMPERATURE,
)
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the climate device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]
    uplink = data.uplink
    systems = data.systems

    entities = []

    async def add_active(system: NibeSystem):
        climates = await get_active_climate(uplink, system.system_id)
        for climate in climates.values():
            entities.append(NibeClimateSupply(system, climate))
            entities.append(NibeClimateRoom(system, climate))

    for system in systems.values():
        thermostats = system.config[CONF_THERMOSTATS]
        for thermostat_id, thermostat_config in thermostats.items():
            entities.append(
                NibeThermostat(
                    system,
                    thermostat_id,
                    thermostat_config.get(CONF_NAME),
                    thermostat_config.get(CONF_CURRENT_TEMPERATURE),
                    thermostat_config.get(CONF_VALVE_POSITION),
                    thermostat_config.get(CONF_CLIMATE_SYSTEMS),
                )
            )

    await asyncio.gather(*[add_active(system) for system in systems.values()])

    async_add_entities(entities, True)


class NibeClimate(NibeEntity, ClimateEntity):
    """Base class for nibe climate entities."""

    def __init__(
        self,
        system: NibeSystem,
        climate: ClimateSystem,
        parameters: set[ParameterId | None],
    ):
        """Init."""

        parameters |= {PARAM_PUMP_SPEED_HEATING_MEDIUM}

        super().__init__(system, parameters)

        self._climate = climate
        self._status = "DONE"
        self._attr_hvac_action = CURRENT_HVAC_IDLE
        self._attr_hvac_mode = HVAC_MODE_HEAT
        self._attr_hvac_modes = [HVAC_MODE_HEAT_COOL, HVAC_MODE_HEAT, HVAC_MODE_COOL]
        self._attr_name = climate.name
        self._attr_supported_features = (
            SUPPORT_TARGET_TEMPERATURE_RANGE | SUPPORT_TARGET_TEMPERATURE
        )
        self._attr_unique_id = "{}_{}".format(self._system_id, self._climate.name)
        self.parse_data()

    @property
    def extra_state_attributes(self):
        """Extra state attributes."""
        data = OrderedDict()
        data["status"] = self._status
        data["pump_speed_heating_medium"] = self.get_float(
            PARAM_PUMP_SPEED_HEATING_MEDIUM
        )

        return data

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode.

        This method must be run in the event loop and returns a coroutine.
        """
        if hvac_mode in self._attr_hvac_modes:
            self._attr_hvac_mode = hvac_mode
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

    def parse_data(self):
        """Parse current data."""
        super().parse_data()

        if "Cooling (Passive)" in self._system.statuses:
            self._attr_hvac_action = CURRENT_HVAC_COOL
        elif "Heating" in self._system.statuses:
            self._attr_hvac_action = CURRENT_HVAC_HEAT
        elif "Cooling" in self._system.statuses:
            self._attr_hvac_action = CURRENT_HVAC_COOL
        else:
            self._attr_hvac_action = CURRENT_HVAC_IDLE


class NibeClimateRoom(NibeClimate):
    """Climate entity for a room temperature sensor."""

    def __init__(self, system: NibeSystem, climate: ClimateSystem):
        """Init."""

        parameters = {
            climate.room_temp,
            climate.room_setpoint_heat,
            climate.room_setpoint_cool,
        }

        super().__init__(system, climate, parameters)

        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}_room".format(DOMAIN_NIBE, system.system_id, str(climate.name))
        )

        self._attr_name = "{} Room".format(self._climate.name)
        self._attr_unique_id = "{}_{}".format(super().unique_id, "room")
        self._attr_max_temp = 35.0
        self._attr_min_temp = 5.0
        self._attr_target_temperature_step = 0.5

    @property
    def available(self):
        """Is entity available."""
        return self.get_value(self._climate.room_temp) is not None

    @property
    def temperature_unit(self):
        """Return temperature unit used."""
        return self.get_unit(self._climate.room_temp, TEMP_CELSIUS)

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self.get_float(self._climate.room_temp)

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT:
            return self.get_float(self._climate.room_setpoint_heat)
        elif self._attr_hvac_mode == HVAC_MODE_COOL:
            return self.get_float(self._climate.room_setpoint_cool)
        else:
            return None

    @property
    def target_temperature_low(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.room_setpoint_heat)
        else:
            return None

    @property
    def target_temperature_high(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.room_setpoint_cool)
        else:
            return None

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

        if ATTR_TEMPERATURE in kwargs:
            await self.async_set_temperature_internal(
                self._climate.room_setpoint_heat, kwargs[ATTR_TEMPERATURE]
            )


class NibeClimateSupply(NibeClimate):
    """Climate entity for supply temperature."""

    def __init__(self, system: NibeSystem, climate: ClimateSystem):
        """Init."""

        parameters = {
            climate.supply_temp,
            climate.calc_supply_temp_heat,
            climate.calc_supply_temp_cool,
            climate.offset_heat,
            climate.offset_cool,
            climate.external_adjustment_active,
        }

        super().__init__(system, climate, parameters)

        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}_supply".format(DOMAIN_NIBE, system.system_id, str(climate.name))
        )
        self._attr_name = "{} Supply".format(self._climate.name)
        self._attr_unique_id = "{}_{}".format(super().unique_id, "supply")
        self._attr_max_temp = 50.0
        self._attr_min_temp = 5.0
        self._attr_target_temperature_step = 1.0

    @property
    def available(self):
        """Is entity available."""
        return self.get_value(self._climate.supply_temp) is not None

    @property
    def temperature_unit(self):
        """Return used temperature unit."""
        return self.get_unit(self._climate.supply_temp, TEMP_CELSIUS)

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self.get_float(self._climate.supply_temp)

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT:
            return self.get_float(self._climate.calc_supply_temp_heat)
        elif self._attr_hvac_mode == HVAC_MODE_COOL:
            return self.get_float(self._climate.calc_supply_temp_cool)
        else:
            return None

    @property
    def target_temperature_low(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.calc_supply_temp_heat)
        else:
            return None

    @property
    def target_temperature_high(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            return self.get_float(self._climate.calc_supply_temp_cool)
        else:
            return None

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

        if ATTR_TEMPERATURE in kwargs:
            if self._attr_hvac_mode == HVAC_MODE_HEAT:
                await set_temperature(
                    self._climate.calc_supply_temp_heat,
                    self._climate.offset_heat,
                    kwargs[ATTR_TEMPERATURE],
                )
            elif self._attr_hvac_mode == HVAC_MODE_COOL:
                await set_temperature(
                    self._climate.calc_supply_temp_cool,
                    self._climate.offset_cool,
                    kwargs[ATTR_TEMPERATURE],
                )

    @property
    def extra_state_attributes(self):
        """Return extra state."""
        data = super().extra_state_attributes
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
        system: NibeSystem,
        external_id: int,
        name: str,
        current_temperature_id: str,
        valve_position_id: str,
        systems: list[int],
    ):
        """Init."""
        self._attr_name = name
        self._uplink = system.uplink
        self._system_id = system.system_id
        self._external_id = external_id
        self._attr_hvac_mode = HVAC_MODE_OFF
        self._attr_hvac_modes = [HVAC_MODE_OFF, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO]
        self._attr_unique_id = "{}_{}_thermostat_{}".format(
            DOMAIN_NIBE, self._system_id, self._external_id
        )
        self._attr_hvac_action = None
        self._attr_supported_features = SUPPORT_TARGET_TEMPERATURE
        self._attr_device_info = {
            "identifiers": {(DOMAIN_NIBE, self._system_id)},
        }
        self._attr_target_temperature_step = 0.5
        self._current_temperature_id = current_temperature_id
        self._current_temperature: float | None = None
        self._attr_temperature_unit = TEMP_CELSIUS
        self._attr_should_poll = False
        self._valve_position_id = valve_position_id
        self._valve_position: float | None = None
        self._systems = systems
        self._target_temperature = DEFAULT_THERMOSTAT_TEMPERATURE

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()
        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            self._target_temperature = old_state.attributes.get(
                ATTR_TARGET_TEMPERATURE, DEFAULT_THERMOSTAT_TEMPERATURE
            )
            if old_state.state:
                self._attr_hvac_mode = old_state.state

        def track_entity_id(
            tracked_entity_id, update_fun: Callable[[State | None], None]
        ):
            if tracked_entity_id:

                async def changed(entity_id: str, old_state: State, new_state: State):
                    update_fun(new_state)
                    await self._async_publish()
                    await self.async_update_ha_state()

                update_fun(self.hass.states.get(tracked_entity_id))

                self.async_on_remove(
                    async_track_state_change(self.hass, tracked_entity_id, changed)
                )

        track_entity_id(self._current_temperature_id, self._update_current_temperature)
        track_entity_id(self._valve_position_id, self._update_valve_position)

        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_publish, timedelta(minutes=15)
            )
        )

    @property
    def extra_state_attributes(self):
        """Return extra state."""
        data = OrderedDict()
        data[ATTR_VALVE_POSITION] = self._valve_position
        data[ATTR_TARGET_TEMPERATURE] = self._target_temperature
        return data

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return target temperature."""
        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            return self._target_temperature
        else:
            return None

    def _update_current_temperature(self, state: State | None):
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

    def _update_valve_position(self, state: State | None):
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

    async def async_set_hvac_mode(self, hvac_mode: str):
        """Set operation mode."""
        if hvac_mode in self._attr_hvac_modes:
            self._attr_hvac_mode = hvac_mode
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
        self.hass.add_job(self._async_publish())
        await self.async_update_ha_state()

    async def _async_publish(self, time=None):
        def scaled(value, multi=10):
            if value is None:
                return None
            else:
                return round(value * multi)

        if self._attr_hvac_mode == HVAC_MODE_HEAT_COOL:
            actual = scaled(self._current_temperature)
            target = scaled(self._target_temperature)
            valve = scaled(self._valve_position, 1)
            systems = self._systems
        elif self._attr_hvac_mode == HVAC_MODE_AUTO:
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
            "name": self._attr_name,
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
