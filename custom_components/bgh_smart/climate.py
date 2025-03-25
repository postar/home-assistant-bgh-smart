"""BGH Smart integration."""

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

# Manejo de compatibilidad para UnitOfTemperature (Home Assistant 2022.10+)
try:
    from homeassistant.components.sensor import UnitOfTemperature
except ImportError:
    from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT
    UnitOfTemperature = type(
        'UnitOfTemperature',
        (),
        {
            'CELSIUS': TEMP_CELSIUS,
            'FAHRENHEIT': TEMP_FAHRENHEIT,
        },
    )

try:
    from homeassistant.components.climate import (
        ClimateEntity,
        PLATFORM_SCHEMA,
        ClimateEntityFeature,
        HVACMode,
    )
except ImportError:
    from homeassistant.components.climate import (
        ClimateDevice as ClimateEntity,
        PLATFORM_SCHEMA,
        ClimateEntityFeature,
    )
    from homeassistant.components.climate.const import (
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_FAN_ONLY,
        HVAC_MODE_DRY,
        HVAC_MODE_AUTO,
        HVAC_MODE_OFF,
    )
    HVACMode = type(
        'HVACMode',
        (),
        {
            'HEAT': HVAC_MODE_HEAT,
            'COOL': HVAC_MODE_COOL,
            'FAN_ONLY': HVAC_MODE_FAN_ONLY,
            'DRY': HVAC_MODE_DRY,
            'AUTO': HVAC_MODE_AUTO,
            'OFF': HVAC_MODE_OFF,
        },
    )

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_STATE,
    ATTR_TEMPERATURE,
    CONF_USERNAME,
    CONF_PASSWORD,
    STATE_ON,
    STATE_OFF,
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

FAN_AUTO = 'auto'
FAN_LOW = 'low'
FAN_MEDIUM = 'mid'
FAN_HIGH = 'high'

MAP_MODE_ID = {
    0: HVACMode.OFF,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    254: HVACMode.AUTO,
}

MAP_FAN_MODE_ID = {
    1: FAN_LOW,
    2: FAN_MEDIUM,
    3: FAN_HIGH,
    254: FAN_AUTO,
}

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the BGH Smart platform."""
    import pybgh

    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]

    client = pybgh.BghClient(username, password)

    if not client.token:
        _LOGGER.error("Could not connect to BGH Smart cloud")
        return

    devices = []
    for home in client.get_homes():
        home_devices = client.get_devices(home['HomeID'])
        for _device_id, device in home_devices.items():
            devices.append(device)

    add_entities(BghHVAC(device, client) for device in devices)

class BghHVAC(ClimateEntity):
    """Representation of a BGH Smart HVAC."""

    def __init__(self, device, client):
        """Initialize a BGH Smart HVAC."""
        self._device = device
        self._client = client

        self._device_name = self._device['device_name']
        self._device_id = self._device['device_id']
        self._home_id = self._device['device_data']['HomeID']
        self._min_temp = None
        self._max_temp = None
        self._current_temperature = None
        self._target_temperature = None
        self._mode = STATE_UNKNOWN
        self._fan_speed = FAN_AUTO

        self._parse_data()

        self._hvac_modes = [
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.OFF,
        ]
        self._fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._support = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )

    def _parse_data(self):
        """Parse the data in self._device"""
        self._min_temp = 17
        self._max_temp = 30

        if self._device['raw_data']:
            self._current_temperature = self._device['data']['temperature']
            self._target_temperature = self._device['data']['target_temperature']
            self._mode = MAP_MODE_ID[self._device['data']['mode_id']]
            self._fan_speed = MAP_FAN_MODE_ID[self._device['data']['fan_speed']]

    def update(self):
        """Fetch new state data for this HVAC."""
        self._device = self._client.get_status(self._home_id, self._device_id)
        self._parse_data()

    @property
    def name(self):
        """Return the display name of this HVAC."""
        return self._device_name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS  # Usa el nuevo enum

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        return self._mode

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_modes

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        return self._fan_speed

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return self._fan_modes

    def set_mode(self):
        """Push the settings to the unit."""
        self._client.set_mode(
            self._device_id,
            self._mode,
            self._target_temperature,
            self._fan_speed,
        )

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        operation_mode = kwargs.get("hvac_mode")

        if temperature:
            self._target_temperature = temperature

        if operation_mode:
            self._mode = operation_mode

        self.set_mode()

    def set_hvac_mode(self, operation_mode):
        """Set new target operation mode."""
        self._mode = operation_mode
        self.set_mode()

    def set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        self._fan_speed = fan_mode
        self.set_mode()
