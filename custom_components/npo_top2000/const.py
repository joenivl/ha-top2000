"""Constants for the NPO Radio 2 Top 2000 integration."""
from datetime import timedelta

DOMAIN = "npo_top2000"

# Configuration
CONF_UPCOMING_COUNT = "upcoming_count"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ENABLE_NOTIFICATIONS = "enable_notifications"
CONF_NOTIFICATION_TARGETS = "notification_targets"  # List of notify services
CONF_NOTIFY_CURRENT_SONG = "notify_current_song"
CONF_NOTIFY_UPCOMING_SONG = "notify_upcoming_song"
CONF_UPCOMING_NOTIFY_POSITIONS = "upcoming_notify_positions"  # Which positions to notify (e.g., [1, 2, 3])

# Defaults
DEFAULT_UPCOMING_COUNT = 10
DEFAULT_UPDATE_INTERVAL = 30  # seconds
DEFAULT_ENABLE_NOTIFICATIONS = True
DEFAULT_NOTIFICATION_TARGETS = ["persistent_notification"]  # Default to persistent notification
DEFAULT_NOTIFY_CURRENT_SONG = True
DEFAULT_NOTIFY_UPCOMING_SONG = False
DEFAULT_UPCOMING_NOTIFY_POSITIONS = [1, 2, 3]  # Notify for next 3 upcoming songs

# Update intervals
MIN_UPDATE_INTERVAL = 15  # seconds
MAX_UPDATE_INTERVAL = 120  # seconds
SCAN_INTERVAL = timedelta(seconds=DEFAULT_UPDATE_INTERVAL)

# Database
DB_NAME = "top2000.db"
CACHE_DURATION_HOURS = 24  # Cover art cache duration

# NPO Radio 2 URLs
NPO_LIVE_URL = "https://www.nporadio2.nl/live"
NPO_STREAM_URL = "https://icecast.omroep.nl/radio2-bb-mp3"
FALLBACK_URL = "https://onlineradiobox.com/nl/radio2/"

# MusicBrainz
MUSICBRAINZ_APP_NAME = "NPO-Top2000-HA-Integration"
MUSICBRAINZ_VERSION = "0.1.0"
MUSICBRAINZ_CONTACT = "https://github.com/joeni/ha-top2000"

# Sensor names
SENSOR_CURRENT_SONG = "current_song"
SENSOR_UPCOMING_SONGS = "upcoming_songs"

# Attributes
ATTR_POSITION = "position"
ATTR_ARTIST = "artist"
ATTR_TITLE = "title"
ATTR_YEAR = "year"
ATTR_FUN_FACT_1 = "fun_fact_1"
ATTR_FUN_FACT_2 = "fun_fact_2"
ATTR_FUN_FACT_3 = "fun_fact_3"
ATTR_COVER_ART_URL = "cover_art_url"
ATTR_DETECTED_AT = "detected_at"
ATTR_NPO_METADATA = "npo_metadata"
ATTR_SONGS = "songs"
ATTR_COUNT = "count"
ATTR_CURRENT_POSITION = "current_position"

# Notification
NOTIFICATION_TITLE = "NPO Radio 2 Top 2000"
NOTIFICATION_ID = "npo_top2000_notification"

# Notification rule types
RULE_TYPE_ARTIST = "artist"
RULE_TYPE_TITLE = "title"
RULE_TYPE_POSITION_RANGE = "position_range"

# Fuzzy matching
FUZZY_MATCH_THRESHOLD = 85  # 0-100, higher = stricter matching

# HTTP
HTTP_TIMEOUT_CONNECT = 10  # seconds
HTTP_TIMEOUT_READ = 30  # seconds
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
