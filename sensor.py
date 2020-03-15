"""Sensors for nibe."""

import logging
from collections import defaultdict

from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_CATEGORIES,
    CONF_SENSORS,
    CONF_UNIT,
    CONF_UNITS,
    DATA_NIBE,
)
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


def gen_dict():
    """Generate a default dict."""
    return {"device_info": None, "data": None}


async def async_load(hass, uplink):
    """Load the sensors."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    systems = hass.data[DATA_NIBE].systems

    sensors = defaultdict(gen_dict)

    async def load_sensor(system_id, sensor_id):
        sensors.setdefault((system_id, sensor_id), gen_dict())

    async def load_categories(system_id, unit_id):
        data = await uplink.get_categories(system_id, True, unit_id)

        for category in data:
            device_info = {
                "identifiers": {(DOMAIN_NIBE, system_id, "categories", unit_id, category["categoryId"])},
                "via_device": (DOMAIN_NIBE, system_id),
                "name": f"Category: {category['name']}",
                "model": "System Category",
                "manufacturer": "NIBE Energy Systems",
            }
            for x in category["parameters"]:
                entry = sensors[(system_id, x["parameterId"])]
                entry["data"] = x
                entry["device_info"] = device_info

    for system in systems.values():
        for sensor_id in system.config[CONF_SENSORS]:
            await load_sensor(system.system_id, sensor_id)

        for unit in system.config[CONF_UNITS]:
            if unit[CONF_CATEGORIES]:
                await load_categories(system.system_id, unit[CONF_UNIT])

    return sensors


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the device based on a config entry."""
    uplink = hass.data[DATA_NIBE].uplink
    sensors = await async_load(hass, uplink)
    entites_update = []
    entites_done = []

    for (system_id, parameter_id), config in sensors.items():
        if parameter_id == 0:
            continue

        entity = NibeSensor(
            uplink,
            system_id,
            parameter_id,
            entry,
            data=config["data"],
            device_info=config["device_info"],
        )
        if config["data"]:
            entites_done.append(entity)
        else:
            entites_update.append(entity)

    async_add_entities(entites_update, True)
    async_add_entities(entites_done, False)


class NibeSensor(NibeParameterEntity, Entity):
    """Nibe Sensor."""

    def __init__(self, uplink, system_id, parameter_id, entry, data, device_info):
        """Init."""
        super(NibeSensor, self).__init__(
            uplink, system_id, parameter_id, data, ENTITY_ID_FORMAT
        )
        self._device_info = device_info

    @property
    def device_info(self):
        """Return device identifier."""
        if self._device_info:
            return self._device_info
        return super().device_info

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value
