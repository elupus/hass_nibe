"""Sensors for nibe."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_CURRENT_MILLIAMPERE,
    ELECTRIC_POTENTIAL_MILLIVOLT,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
    ENERGY_WATT_HOUR,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    TEMP_KELVIN,
    TIME_HOURS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.dt import parse_datetime
from nibeuplink.typing import CategoryType, ParameterId, SystemUnit

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
        device_info = DeviceInfo(
            configuration_url=f"https://nibeuplink.com/System/{system.system_id}",
            identifiers={
                (
                    DOMAIN_NIBE,
                    system.system_id,
                    "categories",
                    unit["systemUnitId"],
                    category["categoryId"],
                )
            },
            via_device=(DOMAIN_NIBE, system.system_id),
            name=f"{system.system['name']} - {system.system_id} : {unit['name']} : {category['name']}",
            model=f"{unit['product']} : {category['name']}",
            manufacturer="NIBE Energy Systems",
        )
        entities = []
        for parameter in category["parameters"]:
            if not once(system.system_id, parameter["parameterId"]):
                continue

            system.set_parameter(parameter["parameterId"], parameter)
            entities.append(
                NibeSensor(
                    system,
                    parameter["parameterId"],
                    device_info,
                    PARAMETER_SENSORS_LOOKUP.get(str(parameter["parameterId"])),
                )
            )

        async_add_entities(entities)

    def add_sensors(system: NibeSystem):
        async_add_entities(
            [
                NibeSensor(
                    system,
                    sensor_id,
                    DeviceInfo(identifiers={(DOMAIN_NIBE, system.system_id)}),
                    PARAMETER_SENSORS_LOOKUP.get(str(sensor_id)),
                )
                for sensor_id in system.config[CONF_SENSORS]
                if once(system.system_id, sensor_id)
            ],
            True,
        )

        async_add_entities(
            [NibeSystemSensor(system, description) for description in SYSTEM_SENSORS]
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


@dataclass
class NibeSensorEntityDescription(SensorEntityDescription):
    """Description of a nibe system sensor."""


PARAMETER_SENSORS = (
    NibeSensorEntityDescription(
        key="43424",
        device_class=SensorDeviceClass.DURATION,
        name="compressor operating time hot water",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=TIME_HOURS,
        icon="mdi:clock",
    ),
    NibeSensorEntityDescription(
        key="43420",
        device_class=SensorDeviceClass.DURATION,
        name="compressor operating time",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=TIME_HOURS,
        icon="mdi:clock",
    ),
    NibeSensorEntityDescription(
        key="43416",
        name="compressor starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NibeSensorEntityDescription(
        key="47407",
        name="AUX5",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47408",
        name="AUX4",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47409",
        name="AUX3",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47410",
        name="AUX2",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47411",
        name="AUX1",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47412",
        name="X7",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="48745",
        name="country",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47212",
        name="set max electrical add.",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="47214",
        device_class=SensorDeviceClass.CURRENT,
        name="fuse size",
        entity_category=EntityCategory.CONFIG,
    ),
    NibeSensorEntityDescription(
        key="43122",
        device_class=SensorDeviceClass.FREQUENCY,
        name="allowed compr. freq. min",
        entity_category=EntityCategory.CONFIG,
    ),
)
PARAMETER_SENSORS_LOOKUP = {x.key: x for x in PARAMETER_SENSORS}


class NibeSensor(NibeParameterEntity, SensorEntity):
    """Nibe Sensor."""

    entity_description: NibeSystemSensorEntityDescription

    def __init__(
        self,
        system: NibeSystem,
        parameter_id: ParameterId,
        device_info: dict,
        entity_description: NibeSensorEntityDescription | None,
    ):
        """Init."""
        super().__init__(system, parameter_id, ENTITY_ID_FORMAT)
        self._attr_device_info = device_info
        if entity_description:
            self.entity_description = entity_description

    @property
    def device_class(self) -> str | None:
        """Try to deduce a device class."""
        if data := super().device_class:
            return data

        unit = self.native_unit_of_measurement
        if unit in {TEMP_CELSIUS, TEMP_FAHRENHEIT, TEMP_KELVIN}:
            return SensorDeviceClass.TEMPERATURE
        elif unit in {ELECTRIC_CURRENT_AMPERE, ELECTRIC_CURRENT_MILLIAMPERE}:
            return SensorDeviceClass.CURRENT
        elif unit in {ELECTRIC_POTENTIAL_VOLT, ELECTRIC_POTENTIAL_MILLIVOLT}:
            return SensorDeviceClass.VOLTAGE
        elif unit in {ENERGY_WATT_HOUR, ENERGY_KILO_WATT_HOUR, ENERGY_MEGA_WATT_HOUR}:
            return SensorDeviceClass.ENERGY

        return None

    @property
    def state_class(self):
        """Return state class of unit."""
        if data := super().state_class:
            return data

        if self.native_unit_of_measurement:
            return SensorStateClass.MEASUREMENT
        else:
            return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of the sensor."""
        return self.get_unit(self._parameter_id)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._value


@dataclass
class NibeSystemSensorEntityDescription(SensorEntityDescription):
    """Description of a nibe system sensor."""

    state_fn: Callable[[NibeSystem], StateType] = lambda x: None


SYSTEM_SENSORS: tuple[NibeSystemSensorEntityDescription, ...] = (
    NibeSystemSensorEntityDescription(
        key="lastActivityDate",
        name="last activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_fn=lambda x: parse_datetime(x.system["lastActivityDate"]),
    ),
    NibeSystemSensorEntityDescription(
        key="connectionStatus",
        name="connection status",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_fn=lambda x: x.system["connectionStatus"],
    ),
    NibeSystemSensorEntityDescription(
        key="hasAlarmed",
        name="has alarmed",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_fn=lambda x: str(x.system["hasAlarmed"]),
    ),
    NibeSystemSensorEntityDescription(
        key="software",
        name="software version",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_fn=lambda x: str(x.software["current"]["name"]) if x.software else None,
    ),
)


class NibeSystemSensor(CoordinatorEntity[NibeSystem], SensorEntity):
    """Generic system sensor."""

    entity_description: NibeSystemSensorEntityDescription

    def __init__(
        self,
        system: NibeSystem,
        description: NibeSystemSensorEntityDescription,
    ):
        """Initialize sensor."""
        super().__init__(system)
        self.entity_description = description
        self._system = system
        self._attr_device_info = {"identifiers": {(DOMAIN_NIBE, system.system_id)}}
        self._attr_unique_id = "{}_system_{}".format(
            system.system_id, description.key.lower()
        )

    @property
    def native_value(self) -> StateType:
        """Get the state data from system class."""
        return self.entity_description.state_fn(self._system)
