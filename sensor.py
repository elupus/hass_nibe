"""Sensors for nibe."""
from __future__ import annotations

import logging
from collections import defaultdict

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import NibeData
from .const import CONF_SENSORS, DATA_NIBE_ENTRIES
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


def gen_dict():
    """Generate a default dict."""
    return {"device_info": None, "data": None}


async def async_load(data: NibeData):
    """Load the sensors."""
    uplink = data.uplink
    systems = data.systems

    sensors: dict[tuple[int, int], dict] = defaultdict(gen_dict)

    async def load_sensor(system_id, sensor_id):
        sensors.setdefault((system_id, sensor_id), gen_dict())

    async def load_categories(system_id, unit_id):
        data = await uplink.get_categories(system_id, True, unit_id)

        for category in data:
            device_info = {
                "identifiers": {
                    (
                        DOMAIN_NIBE,
                        system_id,
                        "categories",
                        unit_id,
                        category["categoryId"],
                    )
                },
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

        for unit_id in system.units.keys():
            await load_categories(system.system_id, unit_id)

    return sensors


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]
    uplink = data.uplink
    sensors = await async_load(data)
    entites_update = []
    entites_done = []

    for (system_id, parameter_id), config in sensors.items():
        if parameter_id == 0:
            continue

        entity = NibeSensor(
            uplink,
            system_id,
            parameter_id,
            data=config["data"],
            device_info=config["device_info"],
        )
        if config["data"]:
            entites_done.append(entity)
        else:
            entites_update.append(entity)

    async_add_entities(entites_update, True)
    async_add_entities(entites_done, False)


class NibeSensor(NibeParameterEntity, SensorEntity):
    """Nibe Sensor."""

    def __init__(self, uplink, system_id, parameter_id, data, device_info):
        """Init."""
        super(NibeSensor, self).__init__(
            uplink, system_id, parameter_id, data, ENTITY_ID_FORMAT
        )
        self._device_info = device_info

    @property
    def state_class(self):
        """Return state class of unit."""
        if self._unit:
            return STATE_CLASS_MEASUREMENT
        else:
            return None

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
