import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import (
    async_generate_entity_id
)
from homeassistant.components.switch import (
    PLATFORM_SCHEMA,
    ENTITY_ID_FORMAT,
    SwitchDevice,
)
from homeassistant.const import (
    CONF_NAME
)
from ..nibe import (
    CONF_OBJECTID,
    CONF_SYSTEM,
    CONF_PARAMETER,
    CONF_DATA,
    UNIT_ICON,
    NibeParameterEntity,
)

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)

DATA_NIBE      = 'nibe'

PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SYSTEM)   : cv.positive_int,
    vol.Required(CONF_PARAMETER): cv.positive_int,
    vol.Optional(CONF_NAME)     : cv.string,
    vol.Optional(CONF_OBJECTID) : cv.string,
    vol.Optional(CONF_DATA)     : vol.Any(None, dict),
})

discovered_entities = set()


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):

    if (discovery_info):
        entries = [PLATFORM_SCHEMA(x) for x in discovery_info]
    else:
        entries = [config]

    sensors = []
    for entry in entries:

        object_id = entry.get(CONF_OBJECTID)
        if object_id:
            if object_id in discovered_entities:
                continue
            discovered_entities.add(object_id)

        sensors.append(
            NibeSwitch(
                hass,
                entry.get(CONF_SYSTEM),
                entry.get(CONF_PARAMETER),
                object_id = object_id,
                data      = entry.get(CONF_DATA),
                name      = entry.get(CONF_NAME)
            )
        )

    async_add_devices(sensors)


class NibeSwitch(NibeParameterEntity, SwitchDevice):
    def __init__(self, hass, system_id, parameter_id, name = None, object_id = None, data = None):
        super(NibeSwitch, self).__init__(system_id, parameter_id)
        self._name         = name
        self._unit         = None
        self._icon         = None
        self._uplink       = hass.data[DATA_NIBE]['uplink']

        self.parse_data(data)

        if not object_id:
            object_id = 'nibe_{}_{}'.format(system_id, parameter_id)

        self.entity_id     = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            object_id,
            hass=hass
        )

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state == "1"

    async def async_turn_on(self, **kwargs):
        await self._uplink.put_parameter(self._system_id, self._parameter_id, '1')

    async def async_turn_off(self, **kwargs):
        await self._uplink.put_parameter(self._system_id, self._parameter_id, '0')

    @property
    def icon(self):
        return self._icon

    @property
    def should_poll(self):
        return True

    @property
    def device_state_attributes(self):
        if self._data:
            return {
                'designation'  : self._data['designation'],
                'parameter_id' : self._data['parameterId'],
                'display_value': self._data['displayValue'],
                'raw_value'    : self._data['rawValue'],
                'display_unit' : self._data['unit'],
            }
        else:
            return {}

    @property
    def available(self):
        if self._state is None:
            return False
        else:
            return True

    def parse_data(self, data):
        if data:
            if self._name is None:
                self._name = data['title']
            self._icon  = UNIT_ICON.get(data['unit'], None)
            self._state = data['rawValue']
            self._data  = data

        else:
            self._data  = None
            self._state = None

    async def async_update(self):
        self.parse_data(await self.hass.data[DATA_NIBE]['uplink'].get_parameter(self._system_id, self._parameter_id))

