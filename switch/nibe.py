import logging

from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.switch import (
    SwitchDevice,
    ENTITY_ID_FORMAT
)
from ..nibe.entity import NibeParameterEntity
from ..nibe.const import (
    DATA_NIBE
)

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)


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
        parameter = system.switches
        for parameter_id, config in parameter.items():
            data = config.get('data')
            if data is None:
                update = True

            entities.append(
                NibeSwitch(
                    uplink,
                    system.system_id,
                    parameter_id,
                    entry,
                    data = data,
                    groups = config.get('groups', [])
                )
            )

    async_add_entities(entities, update)


class NibeSwitch(NibeParameterEntity, SwitchDevice):
    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 entry,
                 data,
                 groups):
        super(NibeSwitch, self).__init__(
            uplink,
            system_id,
            parameter_id,
            data,
            groups,
            ENTITY_ID_FORMAT)

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
