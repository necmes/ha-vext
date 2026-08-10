"""Constants for the Vext integration."""
from datetime import timedelta

DOMAIN = "vext"
VERSION = "1.0.0"

# Vext cloud endpoint used by the integration.
BASE_URL = "https://gbpkzqwffgubmmyoabqp.supabase.co"
# App client key (public value shipped with the Vext app).
APIKEY = "sb_publishable_cRKV08I8Z2akCmnotZorxQ_OJSO-rMP"

# Distinctive User-Agent so the service can identify this client in its logs.
USER_AGENT = f"HomeAssistant-Vext/{VERSION} (+https://github.com/necmes/ha-vext)"

# Polling. The service has no public API, so stay gentle: one poll per two
# minutes by default, never faster than MIN_SCAN_INTERVAL, and back off
# exponentially up to MAX_BACKOFF_INTERVAL while the service is unhappy.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=120)
MIN_SCAN_INTERVAL = timedelta(seconds=60)
MAX_BACKOFF_INTERVAL = timedelta(minutes=30)
BACKOFF_FACTOR = 2.0

# Coalesce bursts of writes (e.g. dragging a slider) into a single refresh.
REFRESH_DEBOUNCE = 5.0

REQUEST_TIMEOUT = 20

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

MANUFACTURER = "Vext"
MODEL = "Cabinet 2.0"

# writable settings fields on cabinet_settings
FIELD_BRIGHTNESS = "desired_brightness_pct"
FIELD_FOG_MOISTURE = "fog_duration_adjust_pct"
FIELD_FOG_RHYTHM = "cycle_length_adjust_pct"
FIELD_LIGHTS_ON = "lights_on_time"
FIELD_LIGHTS_OFF = "lights_off_time"
