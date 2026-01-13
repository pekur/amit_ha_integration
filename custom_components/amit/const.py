"""Constants for AMiT integration."""

DOMAIN = "amit"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_STATION_ADDR = "station_addr"
CONF_CLIENT_ADDR = "client_addr"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_VARIABLES = "variables"

# Defaults
DEFAULT_PORT = 59
DEFAULT_STATION_ADDR = 4
DEFAULT_CLIENT_ADDR = 31
DEFAULT_PASSWORD = 0
DEFAULT_SCAN_INTERVAL = 30

# Services
SERVICE_WRITE_VARIABLE = "write_variable"
SERVICE_RELOAD_VARIABLES = "reload_variables"

# Platforms
PLATFORMS = ["sensor", "number", "binary_sensor", "switch"]

# Variable categories for UI grouping
CATEGORY_TEMPERATURE = "temperature"
CATEGORY_SETPOINT = "setpoint"
CATEGORY_STATE = "state"
CATEGORY_CONTROL = "control"
CATEGORY_OTHER = "other"

# Prefixes for automatic categorization
TEMPERATURE_PREFIXES = (
    "TE", "T", "Teoko", "Trek", "TTUV", "TPRIV", "TVENK", "pokoj", "koupl"
)
SETPOINT_PREFIXES = (
    "Zad", "Komf", "Utl", "komf", "utl", "ZADANA", "Hmax", "Hmin"
)
STATE_PREFIXES = (
    "Stav", "Por", "ALARM", "status", "Rez", "RV", "Zap", "HAVARIE"
)
CONTROL_PREFIXES = (
    "AUT", "RUC", "Povol", "Blok", "zapni", "Cir", "Rek"
)
