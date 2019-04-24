"""FAN for nibe."""

import asyncio
import logging
from typing import List

from homeassistant.components.fan import (
    ENTITY_ID_FORMAT,
    SUPPORT_SET_SPEED,
    SPEED_OFF,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_HIGH,
    FanEntity)
from homeassistant.exceptions import PlatformNotReady

from . import NibeSystem
from .const import (CONF_FANS, DATA_NIBE, DOMAIN as DOMAIN_NIBE)
from .entity import NibeEntity

DEPENDENCIES = ['nibe']
PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)
SPEED_NORMAL = 'normal'
SPEED_BOOST = 'boost'

_SPEED_MAP = {
    SPEED_NORMAL: 'exhaust_speed_normal',
    SPEED_OFF: 'exhaust_speed_1',
    SPEED_LOW: 'exhaust_speed_2',
    SPEED_MEDIUM: 'exhaust_speed_3',
    SPEED_HIGH: 'exhaust_speed_4',
}


async def _is_ventilation_active(uplink, system, climate):
    if not system.config[CONF_FANS]:
        return False

    return True


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""
    from nibeuplink import (  # noqa
        PARAM_VENTILATION_SYSTEMS,
        VentilationSystem,
        Uplink)

    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE]['uplink']  # type: Uplink
    systems = hass.data[DATA_NIBE]['systems']  # type: List[NibeSystem]

    entities = []

    async def add_active(system: NibeSystem, ventilation: VentilationSystem):
        if await _is_ventilation_active(uplink, system, ventilation):
            entities.append(
                NibeFan(
                    uplink,
                    system.system_id,
                    ventilation
                )
            )

    await asyncio.gather(*[
        add_active(system, climate)
        for climate in PARAM_VENTILATION_SYSTEMS.values()
        for system in systems.values()
    ])

    async_add_entities(entities, True)


class NibeFan(NibeEntity, FanEntity):
    """Nibe Sensor."""

    def __init__(self,
                 uplink,
                 system_id,
                 ventilation):
        """Init."""
        super().__init__(
            uplink,
            system_id,
            [])

        self._ventilation = ventilation
        self.entity_id = ENTITY_ID_FORMAT.format(
            '{}_{}_{}'.format(
                DOMAIN_NIBE,
                system_id,
                str(ventilation.name).lower()
            )
        )

        self.get_parameters([
            ventilation.fan_speed,
            ventilation.ventilation_boost,
            ventilation.extract_air,
            ventilation.exhaust_speed_normal,
            ventilation.exhaust_air,
            ventilation.exhaust_speed_1,
            ventilation.exhaust_speed_2,
            ventilation.exhaust_speed_3,
            ventilation.exhaust_speed_4,
        ])

    @property
    def name(self):
        """Return name of entity."""
        return self._ventilation.name

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return self.get_value(self._ventilation.fan_speed) is not None

    @property
    def state(self) -> str:
        """Return current fan state."""
        return self.get_value(self._ventilation.fan_speed)

    @property
    def speed(self) -> str:
        """Return the current speed."""
        fan_speed = self.get_value(self._ventilation.fan_speed)
        if fan_speed is None:
            return None

        boost = self.get_raw(self._ventilation.ventilation_boost)
        if boost:
            return SPEED_BOOST

        for key, value in _SPEED_MAP.items():
            speed = self.get_value(getattr(self._ventilation, value))
            if speed is None:
                continue
            if fan_speed == speed:
                return key
        return None

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        speeds = list(_SPEED_MAP.keys())
        speeds.append(SPEED_BOOST)
        return speeds

    @property
    def state_attributes(self) -> dict:
        """Return optional state attributes.

        Overide base class state_attibutes to support device specific.
        """
        data = super().state_attributes
        data.update(self.device_state_attributes)
        return data

    @property
    def device_state_attributes(self):
        """Return extra state."""
        data = {}
        data['fan_speed'] = \
            self.get_value(self._ventilation.fan_speed)
        data['fan_speed_raw'] = \
            self.get_raw(self._ventilation.fan_speed)
        data['extract_air'] = \
            self.get_value(self._ventilation.extract_air)
        data['exhaust_air'] = \
            self.get_value(self._ventilation.exhaust_air)
        data['ventilation_boost'] = \
            self.get_value(self._ventilation.ventilation_boost)
        data['ventilation_boost_raw'] = \
            self.get_raw(self._ventilation.ventilation_boost)
        return data

    async def async_set_speed(self, speed: str):
        """Set the speed of the fan."""
        if speed == SPEED_BOOST:
            await self._uplink.put_parameter(
                self._system_id,
                self._ventilation.ventilation_boost,
                1)
        elif speed in _SPEED_MAP.keys():
            """Boost should be off."""
            await self._uplink.put_parameter(
                self._system_id,
                self._ventilation.ventilation_boost,
                0)

        else:
            _LOGGER.error("Unsupported speed %s", speed)
            return False

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_SET_SPEED

    @property
    def unique_id(self):
        """Return a unique identifier for a this parameter."""
        return "{}_{}".format(self._system_id, self._ventilation.fan_speed)
