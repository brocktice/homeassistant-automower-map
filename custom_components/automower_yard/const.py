"""Constants for the Robot Mower Yard prototype."""

from __future__ import annotations

DOMAIN = "automower_yard"

HUSQVARNA_AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
HUSQVARNA_REST_BASE_URL = "https://api.amc.husqvarna.dev/v1"
HUSQVARNA_WS_URL = "wss://ws.openapi.husqvarna.dev/v1"
NAVIMOW_AUTHORIZE_URL = "https://navimow-h5-fra.willand.com/smartHome/login?channel=homeassistant"
NAVIMOW_TOKEN_URL = "https://navimow-fra.ninebot.com/openapi/oauth/getAccessToken"
NAVIMOW_CLIENT_ID = "homeassistant"
NAVIMOW_CLIENT_SECRET = "57056e15-722e-42be-bbaa-b0cbfb208a52"
NAVIMOW_API_BASE_URL = "https://navimow-fra.ninebot.com"
NAVIMOW_MQTT_BROKER = "mqtt.navimow.com"
NAVIMOW_MQTT_PORT = 1883
NAVIMOW_UPDATE_INTERVAL = 30
NAVIMOW_MQTT_STALE_SECONDS = 300
NAVIMOW_HTTP_FALLBACK_MIN_INTERVAL = 3600

CONF_ENTRY_KIND = "entry_kind"
CONF_PROVIDER_TYPE = "provider_type"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_MOWER_NAME = "mower_name"
CONF_STATUS_ENTITY = "status_entity"
CONF_BATTERY_ENTITY = "battery_entity"
CONF_BASE_STATION_LATITUDE = "base_station_latitude"
CONF_BASE_STATION_LONGITUDE = "base_station_longitude"
CONF_POSITION_OFFSET_NORTH_M = "position_offset_north_m"
CONF_POSITION_OFFSET_EAST_M = "position_offset_east_m"
CONF_PROBLEM_ENTITY = "problem_entity"
CONF_TRACKER_ENTITY = "tracker_entity"
CONF_YARD_ENTRY_ID = "yard_entry_id"
CONF_YARD_NAME = "yard_name"
CONF_ZONES = "zones_json"
CONF_CUTTING_HEIGHT_UNITS = "cutting_height_units"

CUTTING_HEIGHT_UNIT_CM = "cm"
CUTTING_HEIGHT_UNIT_IN = "in"

ENTRY_KIND_YARD = "yard"
ENTRY_KIND_PROVIDER = "provider"

PROVIDER_MOCK = "mock"
PROVIDER_ENTITY = "entity"
PROVIDER_HUSQVARNA = "husqvarna"
PROVIDER_NAVIMOW = "navimow"

DEFAULT_ZONES = "[]"

PLATFORMS = ["binary_sensor", "camera", "device_tracker", "lawn_mower", "sensor", "switch"]

ATTR_PROVIDER = "provider"
ATTR_PROVIDER_MOWER_ID = "provider_mower_id"
ATTR_YARD_ENTRY_ID = "yard_entry_id"
ATTR_HEATMAP_SAMPLE_COUNT = "heatmap_sample_count"
ATTR_HEATMAP_MAX_AGE_DAYS = "heatmap_max_age_days"
