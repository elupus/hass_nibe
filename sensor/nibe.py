import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import (Entity, async_generate_entity_id)
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    ENTITY_ID_FORMAT,
)
from homeassistant.const import (CONF_NAME)
from ..nibe import (
    CONF_OBJECTID,
    CONF_SYSTEM,
    CONF_PARAMETER,
    CONF_DATA
)

UNIT_ICON = {
    'A' : 'mdi:power-plug',
    'Hz': 'mdi:update',
    'h' : 'mdi:clock',
}

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
            discovered_entities.update(object_id)

        sensors.append(
            NibeSensor(
                hass,
                entry.get(CONF_SYSTEM),
                entry.get(CONF_PARAMETER),
                object_id = object_id,
                data      = entry.get(CONF_DATA),
                name      = entry.get(CONF_NAME)
            )
        )

    async_add_devices(sensors)


class NibeSensor(Entity):
    def __init__(self, hass, system_id, parameter_id, name = None, object_id = None, data = None):
        """Initialize the Nibe sensor."""
        self._system_id    = system_id
        self._parameter_id = parameter_id
        self._name         = name
        self._unit         = None
        self._icon         = None

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
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        return self._icon

    @property
    def should_poll(self):
        return True

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
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
        """Return True if entity is available."""
        if self._state is None:
            return False
        else:
            return True

    @property
    def unique_id(self):
        return "nibe_{}_{}".format(self._system_id, self._parameter_id)

    def parse_data(self, data):
        if data:
            if self._name is None:
                self._name = data['title']
            self._icon  = UNIT_ICON.get(data['unit'], None)
            self._unit  = data['unit']
            self._state = data['value']
            self._data  = data

        else:
            self._data  = None
            self._state = None

    async def async_update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        self.parse_data(await self.hass.data[DATA_NIBE]['uplink'].get_parameter(self._system_id, self._parameter_id))
