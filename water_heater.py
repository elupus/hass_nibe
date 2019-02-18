import logging
import asyncio
import aiohttp
from collections import OrderedDict
from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.water_heater import (
    WaterHeaterDevice,
    STATE_HEAT_PUMP,
    STATE_ECO,
    STATE_HIGH_DEMAND,
    STATE_OFF,
    ENTITY_ID_FORMAT,
    SUPPORT_OPERATION_MODE
)
from ..nibe.const import (
    DOMAIN as DOMAIN_NIBE,
    DATA_NIBE,
    CONF_WATER_HEATERS,
)
from ..nibe.entity import NibeEntity

DEPENDENCIES = ['nibe']
_LOGGER = logging.getLogger(__name__)


NIBE_STATE_TO_HA = {
    'economy': {
        'state': STATE_ECO,
        'start': 'start_temperature_water_economy',
        'stop': 'stop_temperature_water_economy',
    },
    'normal' : {
        'state': STATE_HEAT_PUMP,
        'start': 'start_temperature_water_normal',
        'stop': 'stop_temperature_water_normal',
    },
    'luxuary': {
        'state': STATE_HIGH_DEMAND,
        'start': 'start_temperature_water_luxary',
        'stop': 'stop_temperature_water_luxary',
    }
}

HA_STATE_TO_NIBE = {v['state']: k for k, v in NIBE_STATE_TO_HA.items()}


async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):
    """Old setyp, not used"""
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    entities = []

    from nibeuplink import (PARAM_HOTWATER_SYSTEMS)

    async def is_active(system, hwsys):
        if CONF_WATER_HEATERS not in system.config:
            return False

        available = await uplink.get_parameter(
            system.system_id,
            hwsys.hot_water_production)
        if available and available['rawValue']:
            return True
        return False

    async def add_active(system, hwsys):
        if await is_active(system, hwsys):
            entities.append(
                NibeWaterHeater(
                    uplink,
                    system.system_id,
                    hwsys,
                )
            )

    await asyncio.gather(*[
        add_active(system, hwsys)
        for hwsys in PARAM_HOTWATER_SYSTEMS.values()
        for system in systems.values()
    ])

    async_add_entities(entities, True)


class NibeWaterHeater(NibeEntity, WaterHeaterDevice):
    def __init__(self,
                 uplink,
                 system_id: int,
                 hwsys):
        super().__init__(
            uplink,
            system_id,
            [])

        self._name = hwsys.name
        self._current_operation = None
        self._data = OrderedDict()
        self._hwsys = hwsys

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}'.format(
                DOMAIN_NIBE,
                self.unique_id
            )
        )

    @property
    def name(self):
        return self._name

    @property
    def temperature_unit(self):
        if 'current_temperature' in self._data:
            return self._data['current_temperature']['unit']
        else:
            return None

    @property
    def device_state_attributes(self):
        data = {}
        for key, value in self._data.items():
            if value:
                data[key] = value['value']
            else:
                data[key] = None
        return data

    @property
    def available(self):
        if 'current_temperature' in self._data:
            value = self.get_value(self._data['current_temperature'])
            return value is not None
        else:
            return False

    @property
    def supported_features(self):
        return SUPPORT_OPERATION_MODE

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def current_temperature(self):
        """Returrn current temperature."""
        return self.get_value(self._data['current_temperature'])

    @property
    def target_temperature_high(self):
        return self.get_value(self._data['target_temp_high'])

    @property
    def target_temperature_low(self):
        return self.get_value(self._data['target_temp_low'])

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return [x['state'] for x in NIBE_STATE_TO_HA.values()]

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        if operation_mode not in HA_STATE_TO_NIBE:
            _LOGGER.error("Operation mode %s not supported", operation_mode)
            return

        try:
            await self._uplink.put_parameter(
                self._system_id,
                self._hwsys.hot_water_comfort_mode,
                HA_STATE_TO_NIBE[operation_mode])
        except aiohttp.client_exceptions.ClientResponseError as e:
            _LOGGER.error("Error trying to set mode %s", str(e))

    @property
    def unique_id(self):
        return "{}_{}".format(self._system_id,
                              self._hwsys.hot_water_charging)

    async def async_update(self):

        _LOGGER.debug("Update water heater {}".format(self.name))

        async def fill(key, src=None):
            if src is None:
                src = key
            parameter_id = getattr(self._hwsys, src, None)
            if parameter_id is None:
                self._data[key] = None
            else:
                self._data[key] = await self._uplink.get_parameter(
                    self._system_id,
                    parameter_id)

        await asyncio.gather(
            fill('current_temperature', 'hot_water_charging'),
            fill('hot_water_comfort_mode'),
            fill('hot_water_top'),
        )

        mode = self._data['hot_water_comfort_mode']
        if mode['value'] in NIBE_STATE_TO_HA:
            conf = NIBE_STATE_TO_HA[mode['value']]
        else:
            conf = None

        if conf:
            if self._current_operation != conf['state']:
                self._current_operation = conf['state']
                _LOGGER.debug("Operation mode change {}".format(conf['state']))

                await asyncio.gather(
                    fill('target_temp_low', conf['start']),
                    fill('target_temp_high', conf['stop'])
                )
        else:
            self._current_operation = STATE_OFF
            self._data['target_temp_low'] = None
            self._data['target_temp_high'] = None

        _LOGGER.debug("Update water heater {}".format(self._data))
