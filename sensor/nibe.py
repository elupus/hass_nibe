import logging

from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT
)
from ..nibe.const import (
    DATA_NIBE
)
from ..nibe.entity import NibeParameterEntity

DEPENDENCIES = ['nibe']
_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass,
                               config,
                               async_add_devices,
                               discovery_info=None):
    """Old setyp, not used"""
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the device based on a config entry."""

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink  = hass.data[DATA_NIBE]['uplink']
    systems = hass.data[DATA_NIBE]['systems']

    entities = []
    update = False
    for system in systems:
        parameter = system.sensors
        for parameter_id, config in parameter.items():
            data = config.get('data')
            if data is None:
                update = True

            entities.append(
                NibeSensor(
                    uplink,
                    system.system_id,
                    parameter_id,
                    entry,
                    data = data,
                    groups = config.get('groups', [])
                )
            )

    async_add_entities(entities, update)


class NibeSensor(NibeParameterEntity, Entity):
    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 entry,
                 data,
                 groups):
        super(NibeSensor, self).__init__(uplink,
                                         system_id,
                                         parameter_id,
                                         data,
                                         groups,
                                         ENTITY_ID_FORMAT)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value

