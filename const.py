"""Constants for nibe uplink."""

ATTR_TARGET_TEMPERATURE = "target_temperature"
ATTR_VALVE_POSITION = "valve_position"

DOMAIN = "nibe"
DATA_NIBE = "nibe"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_REDIRECT_URI = "redirect_uri"
CONF_WRITEACCESS = "writeaccess"
CONF_ACCESS_DATA = "access_data"
CONF_CATEGORIES = "categories"
CONF_SENSORS = "sensors"
CONF_STATUSES = "statuses"
CONF_SYSTEMS = "systems"
CONF_SYSTEM = "system"
CONF_UNITS = "units"
CONF_UNIT = "unit"
CONF_CLIMATES = "climates"
CONF_SWITCHES = "switches"
CONF_BINARY_SENSORS = "binary_sensors"
CONF_CODE = "code"
CONF_WATER_HEATERS = "water_heaters"
CONF_THERMOSTATS = "thermostats"
CONF_CURRENT_TEMPERATURE = "current_temperature"
CONF_VALVE_POSITION = "valve_position"
CONF_CLIMATE_SYSTEMS = "systems"
CONF_FANS = "fans"

AUTH_CALLBACK_URL = "/api/nibe/auth"
AUTH_CALLBACK_NAME = "api:nibe:auth"

CONF_UPLINK_APPLICATION_URL = "https://api.nibeuplink.com/Applications"

SERVICE_SET_SMARTHOME_MODE = "set_smarthome_mode"
SERVICE_SET_PARAMETER = "set_parameter"
SERVICE_GET_PARAMETER = "get_parameter"
SERVICE_SET_THERMOSTAT = "set_thermostat"

SIGNAL_PARAMETERS_UPDATED = "nibe.parameters_updated"
SIGNAL_STATUSES_UPDATED = "nibe.statuses_updated"

SCAN_INTERVAL = 60

DEFAULT_THERMOSTAT_TEMPERATURE = 22
