import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import PlatformNotReady
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


async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):

    if (discovery_info):
        entries = [PLATFORM_SCHEMA(x) for x in discovery_info]
    else:
        entries = [config]

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    sensors = []
    for entry in entries:

        object_id = entry.get(CONF_OBJECTID)
        if object_id:
            if object_id in discovered_entities:
                continue
            discovered_entities.add(object_id)

        sensors.append(
            NibeSwitch(
                hass.data[DATA_NIBE]['uplink'],
                entry.get(CONF_SYSTEM),
                entry.get(CONF_PARAMETER),
                object_id=object_id,
                data=entry.get(CONF_DATA),
                name=entry.get(CONF_NAME)
            )
        )

    async_add_devices(sensors)


class NibeSwitch(NibeParameterEntity, SwitchDevice):
    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 name=None,
                 object_id=None,
                 data=None):
        super(NibeSwitch, self).__init__(uplink, system_id, parameter_id)
        self._name = name
        self._unit = None
        self._icon = None

        self.parse_data(data)
        if object_id:  # Forced id on discovery
            self.entity_id = ENTITY_ID_FORMAT.format(object_id)

    @property
    def icon(self):
        return self._icon

    @property
    def is_on(self):
        if self._data:
            return self._data['rawValue'] == "1"
        else:
            return None

    async def async_turn_on(self, **kwargs):
        await self._uplink.put_parameter(self._system_id,
                                         self._parameter_id,
                                         '1')

    async def async_turn_off(self, **kwargs):
        await self._uplink.put_parameter(self._system_id,
                                         self._parameter_id,
                                         '0')
