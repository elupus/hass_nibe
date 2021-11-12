"""Sensors for nibe."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEVICE_CLASS_TIMESTAMP, ENTITY_CATEGORY_DIAGNOSTIC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from nibeuplink.typing import CategoryType, SystemUnit

from . import NibeData, NibeSystem
from .const import CONF_SENSORS, DATA_NIBE_ENTRIES
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]
    uplink = data.uplink

    done: set[tuple[int, int]] = set()

    def once(system_id: int, parameter_id: int):
        nonlocal done
        key = (system_id, parameter_id)
        if key in done:
            return False
        done.add(key)
        return True

    def add_category(system: NibeSystem, category: CategoryType, unit: SystemUnit):
        device_info = {
            "identifiers": {
                (
                    DOMAIN_NIBE,
                    system.system_id,
                    "categories",
                    unit["systemUnitId"],
                    category["categoryId"],
                )
            },
            "via_device": (DOMAIN_NIBE, system.system_id),
            "name": f"{system.device_info['name']} : {unit['name']} : {category['name']}",
            "model": f"{unit['product']} : {category['name']}",
            "manufacturer": system.device_info["manufacturer"],
        }

        async_add_entities(
            [
                NibeSensor(
                    uplink,
                    system.system_id,
                    parameter["parameterId"],
                    data=parameter,
                    device_info=device_info,
                )
                for parameter in category["parameters"]
                if once(system.system_id, parameter["parameterId"])
            ]
        )

    def add_sensors(system: NibeSystem):
        async_add_entities(
            [
                NibeSensor(
                    uplink,
                    system.system_id,
                    sensor_id,
                    device_info=system.device_info,
                )
                for sensor_id in system.config[CONF_SENSORS]
                if once(system.system_id, sensor_id)
            ],
            True,
        )

        async_add_entities(
            [
                NibeSystemSensor(system.coordinator, system, description)
                for description in SYSTEM_SENSORS
            ]
        )

    async def load_system(system: NibeSystem):
        units = await uplink.get_units(system.system_id)
        for unit in units:
            categories = await uplink.get_categories(
                system.system_id, True, unit["systemUnitId"]
            )
            for category in categories:
                add_category(system, category, unit)
        add_sensors(system)

    for system in data.systems.values():
        await load_system(system)


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


@dataclass
class NibeSystemSensorEntityDescription(SensorEntityDescription):
    """Description of a nibe system sensor."""

    state_fn: Callable[[NibeSystem], StateType] = lambda x: None


SYSTEM_SENSORS: tuple[NibeSystemSensorEntityDescription] = (
    NibeSystemSensorEntityDescription(
        key="lastActivityDate",
        name="Last Activity",
        device_class=DEVICE_CLASS_TIMESTAMP,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        state_fn=lambda x: x.system["lastActivityDate"],
    ),
    NibeSystemSensorEntityDescription(
        key="connectionStatus",
        name="Connection Status",
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        state_fn=lambda x: x.system["connectionStatus"],
    ),
)


class NibeSystemSensor(CoordinatorEntity[None], SensorEntity):
    """Generic system sensor."""

    entity_description: NibeSystemSensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        system: NibeSystem,
        description: NibeSystemSensorEntityDescription,
    ):
        """Initialize sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._system = system
        self._attr_device_info = self._system.device_info
        self._attr_unique_id = "{}_system_{}".format(
            self._system.system_id, self.entity_description.key.lower()
        )

    @property
    def state(self) -> StateType:
        """Get the state data from system class."""
        return self.entity_description.state_fn(self._system)
