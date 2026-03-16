"""Constants for the WAPDA Monitor integration."""

DOMAIN = "wapda_monitor"
MANUFACTURER = "@uppaljs"

CONF_REFERENCE = "reference"
CONF_SCAN_INTERVAL_LOAD = "scan_interval_load"
CONF_SCAN_INTERVAL_BILL = "scan_interval_bill"
CONF_SCAN_INTERVAL_SCHEDULE = "scan_interval_schedule"

# Default polling intervals (seconds)
DEFAULT_SCAN_INTERVAL_LOAD = 300       # 5 minutes  — real-time feeder data
DEFAULT_SCAN_INTERVAL_BILL = 43200     # 12 hours   — billing rarely changes
DEFAULT_SCAN_INTERVAL_SCHEDULE = 900   # 15 minutes — outage schedule

# Coordinator data keys
DATA_LOAD = "load"
DATA_USER = "user"
DATA_BILL = "bill"
DATA_SCHEDULE = "schedule"

PLATFORMS: list[str] = ["sensor", "binary_sensor"]
