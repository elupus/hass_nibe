import attr
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
    DATA_NIBE
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

    for system in systems.values():
        for heater, config in system.water_heaters.items():
            entities.append(
                NibeWaterHeater(
                    uplink,
                    system.system_id,
                    heater,
                    config.get('groups')
                )
            )

    async_add_entities(entities, True)


class NibeWaterHeater(NibeEntity, WaterHeaterDevice):
    def __init__(self,
                 uplink,
                 system_id: int,
                 hwsys,
                 groups):
        super().__init__(
            uplink,
            system_id,
            groups)

        from nibeuplink import PARAM_HOTWATER_SYSTEMS

        sys = PARAM_HOTWATER_SYSTEMS[hwsys]

        self._name = sys.name
        self._current = None
        self._current_id = sys.hot_water_charging
        self._current_operation = None
        self._data = OrderedDict()
        self._select = OrderedDict()
        self._hwsys = sys

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}'.format(
                DOMAIN_NIBE,
                system_id,
                self._current_id,
            )
        )

    @property
    def name(self):
        return self._name

    @property
    def device_info(self):
        systems = self.hass.data[DATA_NIBE]['systems']
        return systems[self._system_id].device_info

    @property
    def temperature_unit(self):
        if 'hot_water_charging' in self._data:
            return self._data['hot_water_charging']['unit']
        else:
            return None

    @property
    def state_attributes(self):
        data = super().state_attributes
        for key, value in self._data.items():
            if value:
                data[key] = value['value']
            else:
                data[key] = None
        return data

    @property
    def available(self):
        if 'hot_water_charging' in self._data:
            return self.get_value(self._data['hot_water_charging']) is not None
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
    def current_temperature(self):
        """Return the current temperature."""
        return self._data['hot_water_charging']

    @property
    def unique_id(self):
        return "{}_{}".format(self._system_id,
                              self._current_id)

    async def async_update(self):

        _LOGGER.debug("Update water heater {}".format(self.name))

        async def get_parameter(parameter_id):
            if parameter_id:
                return await self._uplink.get_parameter(self._system_id,
                                                        parameter_id)
            else:
                return None

        parameters = attr.asdict(self._hwsys)

        async def fill(key, src=None):
            if src is None:
                src = key
            if parameters[src] is None:
                self._data[key] = None
            else:
                self._data[key] = await get_parameter(parameters[src])

        await asyncio.gather(
            fill('hot_water_charging'),
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
