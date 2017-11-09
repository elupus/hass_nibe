import logging
import asyncio

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

DEPENDENCIES = ['nibe']
_LOGGER      = logging.getLogger(__name__)

CONF_SYSTEM    = 'system'
CONF_PARAMETER = 'parameter'

PLATFORM_SCHEMA = vol.Schema({
        vol.Required(CONF_SYSTEM): cv.string,
        vol.Required(CONF_PARAMETER): cv.string,
    }, extra=vol.ALLOW_EXTRA)

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):

    sensors = None
    if (discovery_info):
        sensors = [ hass.components.nibe.NibeSensor(hass, parameter['system_id'], parameter['parameter_id']) for parameter in discovery_info ]
    else:
        sensors = [ hass.components.nibe.NibeSensor(hass, config.get(CONF_SYSTEM), config.get(CONF_PARAMETER)) ]

    async_add_devices(sensors, True)

