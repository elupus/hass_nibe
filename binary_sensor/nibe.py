import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    ENTITY_ID_FORMAT,
    BinarySensorDevice,
)
from homeassistant.const import (
    CONF_NAME
)
from ..nibe import (
    CONF_OBJECTID,
    CONF_SYSTEM,
    CONF_PARAMETER,
    CONF_DATA,
    DATA_NIBE,
)
from ..nibe.entity import NibeParameterEntity


DEPENDENCIES = ['nibe']
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SYSTEM): cv.positive_int,
    vol.Required(CONF_PARAMETER): cv.positive_int,
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_OBJECTID): cv.string,
    vol.Optional(CONF_DATA): vol.Any(None, dict),
})


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
    update = False
    for entry in entries:
        sensors.append(
            NibeBinarySensor(
                hass.data[DATA_NIBE]['uplink'],
                entry.get(CONF_SYSTEM),
                entry.get(CONF_PARAMETER),
                object_id=entry.get(CONF_OBJECTID),
                data=entry.get(CONF_DATA),
                name=entry.get(CONF_NAME)
            )
        )
        if entry.get(CONF_DATA) is None:
            update = True

    async_add_devices(sensors, update)


class NibeBinarySensor(NibeParameterEntity, BinarySensorDevice):
    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 name=None,
                 object_id=None,
                 data=None):
        super().__init__(uplink, system_id, parameter_id)
        self._name = name

        self.parse_data(data)
        if object_id:  # Forced id on discovery
            self.entity_id = ENTITY_ID_FORMAT.format(object_id)

    @property
    def is_on(self):
        if self._data:
            return self._data['rawValue'] == "1"
        else:
            return None
