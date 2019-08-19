"""Sensors for nibe."""

import asyncio
import logging
from collections import defaultdict
from typing import List

from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.core import split_entity_id
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_CATEGORIES,
    CONF_SENSORS,
    CONF_STATUSES,
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
    return {"groups": [], "data": None}


async def async_load(hass, uplink):
    """Load the sensors."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    systems = hass.data[DATA_NIBE].systems

    sensors = defaultdict(gen_dict)
    group = hass.components.group

    async def load_parameter_group(
        name: str, system_id: int, object_id: str, parameters: List[dict]
    ):

        entity = await group.Group.async_create_group(
            hass,
            name=name,
            control=False,
            object_id="{}_{}_{}".format(DOMAIN_NIBE, system_id, object_id),
        )

        _, group_id = split_entity_id(entity.entity_id)

        for x in parameters:
            entry = sensors[(system_id, x["parameterId"])]
            entry["data"] = x
            entry["groups"].append(group_id)
            _LOGGER.debug("Entry {}".format(entry))

    async def load_sensor(system_id, sensor_id):
        sensors.setdefault((system_id, sensor_id), gen_dict())

    async def load_categories(system_id, unit_id):
        data = await uplink.get_categories(system_id, True, unit_id)
        tasks = [
            load_parameter_group(
                x["name"],
                system_id,
                "{}_{}".format(unit_id, x["categoryId"]),
                x["parameters"],
            )
            for x in data
        ]
        await asyncio.gather(*tasks)

    async def load_statuses(system_id, unit_id):
        data = await uplink.get_unit_status(system_id, unit_id)
        tasks = [
            load_parameter_group(
                x["title"],
                system_id,
                "{}_{}".format(unit_id, x["title"]),
                x["parameters"],
            )
            for x in data
        ]
        await asyncio.gather(*tasks)

    for system in systems.values():
        for sensor_id in system.config[CONF_SENSORS]:
            await load_sensor(system.system_id, sensor_id)

        for unit in system.config[CONF_UNITS]:
            if unit[CONF_CATEGORIES]:
                await load_categories(system.system_id, unit[CONF_UNIT])

            if unit[CONF_STATUSES]:
                await load_statuses(system.system_id, unit[CONF_UNIT])
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
            groups=config.get("groups", []),
        )
        if config["data"]:
            entites_done.append(entity)
        else:
            entites_update.append(entity)

    async_add_entities(entites_update, True)
    async_add_entities(entites_done, False)


class NibeSensor(NibeParameterEntity, Entity):
    """Nibe Sensor."""

    def __init__(self, uplink, system_id, parameter_id, entry, data, groups):
        """Init."""
        super(NibeSensor, self).__init__(
            uplink, system_id, parameter_id, data, groups, ENTITY_ID_FORMAT
        )

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value
