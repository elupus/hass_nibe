import logging

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.binary_sensor import (
    BinarySensorDevice,
    ENTITY_ID_FORMAT
)
from ..nibe.entity import NibeParameterEntity
from ..nibe.const import (
    DATA_NIBE,
    CONF_BINARY_SENSORS,
)

DEPENDENCIES = ['nibe']
PARALLEL_UPDATES = 0
_LOGGER      = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink  = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    entities = []
    for system in systems.values():
        for parameter_id in system.config[CONF_BINARY_SENSORS]:
            entities.append(
                NibeBinarySensor(
                    uplink,
                    system.system_id,
                    parameter_id,
                    entry
                )
            )

    async_add_entities(entities, True)


class NibeBinarySensor(NibeParameterEntity, BinarySensorDevice):
    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 entry):
        super(NibeBinarySensor, self).__init__(
            uplink,
            system_id,
            parameter_id,
            None,
            [],
            ENTITY_ID_FORMAT)

    @property
    def is_on(self):
        data = self._parameters[self._parameter_id]
        if data:
            return data['rawValue'] == "1"
        else:
            return None
