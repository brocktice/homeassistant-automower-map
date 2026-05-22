"""Constants for the Automower Yard integration."""

from __future__ import annotations

DOMAIN = "automower_yard"

CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
CONF_CUTTING_HEIGHT_UNITS = "cutting_height_units"
CONF_ZONES = "zones_json"

CUTTING_HEIGHT_UNIT_CM = "cm"
CUTTING_HEIGHT_UNIT_IN = "in"

PLATFORMS = ["binary_sensor", "camera", "device_tracker", "sensor", "switch"]

AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
REST_BASE_URL = "https://api.amc.husqvarna.dev/v1"
WS_URL = "wss://ws.openapi.husqvarna.dev/v1"

DEFAULT_ZONES = "[]"

ATTR_MOWER_ID = "mower_id"
ATTR_MODEL = "model"
ATTR_SERIAL_NUMBER = "serial_number"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_YARD_ZONE = "yard_zone"
ATTR_YARD_ZONES = "yard_zones"
ATTR_ACTIVITY = "activity"
ATTR_STATE = "state"
ATTR_ERROR_CODE = "error_code"
ATTR_WEBSOCKET_CONNECTED = "websocket_connected"
ATTR_LAST_WEBSOCKET_EVENT = "last_websocket_event"
ATTR_LAST_POSITION_EVENT = "last_position_event"
ATTR_HEATMAP_SAMPLE_COUNT = "heatmap_sample_count"
ATTR_HEATMAP_MAX_AGE_DAYS = "heatmap_max_age_days"
