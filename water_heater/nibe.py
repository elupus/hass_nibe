import logging
import asyncio
from collections import OrderedDict

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.water_heater import (
    WaterHeaterDevice,
    STATE_HEAT_PUMP,
    STATE_ECO,
    STATE_HIGH_DEMAND,
    STATE_OFF,
    ENTITY_ID_FORMAT
)
from homeassistant.const import (ATTR_TEMPERATURE)
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
        'stop': 'start_temperature_water_normal',
    },
    'luxuary': {
        'state': STATE_HIGH_DEMAND,
        'start': 'start_temperature_water_luxary',
        'stop': 'start_temperature_water_luxary',
    }
}

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
                 parameter_id,
                 groups):
        super().__init__(
            uplink,
            system_id,
            groups)

        self._name = "Hot Water"
        self._current = None
        self._current_id = parameter_id
        self._current_operation = None
        self._attributes = OrderedDict()
        self._select = OrderedDict()
        self._select['hot_water_charging'] = parameter_id
        self._select['hot_water_top'] = 40013
        self._select['hot_water_comfort_mode'] = 47041
        self._select['hot_water_production'] = 47387
        self._select['periodic_hot_water'] = 47050
        self._select['stop_temperature_water_normal'] = 47048
        self._select['start_temperature_water_normal'] = 47048
        self._select['stop_temperature_water_luxary'] = 47047
        self._select['start_temperature_water_luxary'] = 47043
        self._select['stop_temperature_water_economy'] = 47049
        self._select['start_temperature_water_economy'] = 47045
        self._select['total_hot_water_compressor_time'] = 43424

        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}'.format(
                DOMAIN_NIBE,
                system_id,
                parameter_id,
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
        if self._current:
            return self._current['unit']
        else:
            return None

    @property
    def state_attributes(self):
        data = super().state_attributes
        data.update(self._attributes)
        return data

    @property
    def available(self):
        return self.get_value(self._current) is not None

    @property
    def supported_features(self):
        return 0

    @property
    def current_temperature(self):
        return self.get_value(self._current)

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

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

        data = OrderedDict()

        async def fill(key, parameter_id):
            if parameter_id is None:
                data[key] = None
            else:
                data[key] = await get_parameter(parameter_id)

        await asyncio.gather(
            *[
                fill(key, parameter_id)
                for key, parameter_id in self._select.items()
            ],
        )

        _LOGGER.debug("Update water heater {}: {}".format(self.name, data))

        self._data = data

        for key, value in data.items():
            if value:
                self._attributes[key] = value['value']
            else:
                self._attributes[key] = None

        mode = data['hot_water_comfort_mode']
        if mode['value'] in NIBE_STATE_TO_HA:
            conf = NIBE_STATE_TO_HA[mode['value']]
            self._current_operation = conf['state']
            self._attributes['target_temp_low'] = \
                self.get_value(data[conf['start']])
            self._attributes['target_temp_high'] = \
                self.get_value(data[conf['stop']])
        else:
            self._current_operation = STATE_OFF
            self._attributes['target_temp_low'] = None
            self._attributes['target_temp_high'] = None

        self._current = data['hot_water_charging']
