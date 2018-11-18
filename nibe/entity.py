import logging
from homeassistant.helpers.entity import Entity
from homeassistant.components.group import (
    ATTR_ADD_ENTITIES, ATTR_OBJECT_ID,
    DOMAIN as DOMAIN_GROUP, SERVICE_SET)

from .const import (
    DOMAIN as DOMAIN_NIBE,
)

_LOGGER = logging.getLogger(__name__)

UNIT_ICON = {
    'A': 'mdi:power-plug',
    'Hz': 'mdi:update',
    'h': 'mdi:clock',
}


class NibeEntity(Entity):
    """Base class for all nibe sytem entities"""

    def __init__(self, uplink, system_id, groups):
        """Initialize base class"""
        super().__init__()
        self._uplink = uplink
        self._system_id = system_id
        self._groups = groups

    def get_value(self, data, default=None):
        if data is None or data['value'] is None:
            return default
        else:
            return float(data['value'])

    def get_scale(self, data):
        if data is None or data['value'] is None:
            return 1.0
        else:
            return float(data['rawValue']) / float(data['value'])

    async def async_added_to_hass(self):
        """Once registed ad this entity to member groups"""
        for group in self._groups:
            _LOGGER.debug("Adding entity {} to group {}".format(
                self.entity_id,
                group))
            self.hass.async_add_job(
                self.hass.services.async_call(
                    DOMAIN_GROUP, SERVICE_SET, {
                        ATTR_OBJECT_ID: group,
                        ATTR_ADD_ENTITIES: [self.entity_id]
                    }
                )
            )


class NibeParameterEntity(NibeEntity):
    """Base class with common attributes for parameter entities"""

    def __init__(self,
                 uplink,
                 system_id,
                 parameter_id,
                 data=None,
                 groups=[],
                 entity_id_format=None
                 ):
        """Initialize base class for parameters"""
        super().__init__(uplink, system_id, groups)
        self._parameter_id = parameter_id
        self._name = None
        self._unit = None
        self._icon = None
        self._value = None
        self.parse_data(data)

        if entity_id_format:
            self.entity_id = entity_id_format.format(
                '{}_{}_{}'.format(
                    DOMAIN_NIBE,
                    system_id,
                    str(parameter_id)
                )
            )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique identifier for a this parameter"""
        return "{}_{}".format(self._system_id, self._parameter_id)

    @property
    def should_poll(self):
        """Indicate that we need to poll data"""
        return True

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self._data:
            return {
                'designation': self._data['designation'],
                'parameter_id': self._data['parameterId'],
                'display_value': self._data['displayValue'],
                'raw_value': self._data['rawValue'],
                'display_unit': self._data['unit'],
            }
        else:
            return {}

    @property
    def available(self):
        """Return True if entity is available."""
        if self._value is None:
            return False
        else:
            return True

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return a calculated icon for this data if known"""
        return self._icon

    def parse_data(self, data):
        """Parse dat to update internal variables"""
        if data:
            if self._name is None:
                self._name = data['title']
            self._icon = UNIT_ICON.get(data['unit'], None)
            self._unit = data['unit']
            self._value = data['value']
            self._data = data
        else:
            self._value = None
            self._data = None

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            data = await self._uplink.get_parameter(self._system_id,
                                                    self._parameter_id)
            self.parse_data(data)
        except BaseException:
            self.parse_data(None)
            raise
