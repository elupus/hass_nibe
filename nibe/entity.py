import logging
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

UNIT_ICON = {
    'A': 'mdi:power-plug',
    'Hz': 'mdi:update',
    'h': 'mdi:clock',
}


class NibeEntity(Entity):
    """Base class for all nibe sytem entities"""

    def __init__(self, uplink, system_id):
        """Initialize base class"""
        super().__init__()
        self._uplink = uplink
        self._system_id = system_id


class NibeParameterEntity(NibeEntity):
    """Base class with common attributes for parameter entities"""

    def __init__(self, uplink, system_id, parameter_id):
        """Initialize base class for parameters"""
        super().__init__(uplink, system_id)
        self._parameter_id = parameter_id
        self._name = None
        self._unit = None
        self._icon = None
        self._value = None
        self._data = None

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
