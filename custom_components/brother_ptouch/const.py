"""Constants."""
DOMAIN = "brother_ptouch"

CONF_TRANSPORT = "transport"
CONF_USB_SERIAL = "serial"
CONF_ADDRESS = "address"
CONF_CHANNEL = "channel"
CONF_URL = "url"
CONF_TOKEN = "token"

TRANSPORT_USB = "usb"
TRANSPORT_BLUETOOTH = "bluetooth"
TRANSPORT_BRIDGE = "bridge"

CONF_ORIENTATION = "orientation"
DEFAULT_ORIENTATION = "normal"

SCAN_INTERVAL_SECONDS = 60

CONF_BATCH_WINDOW = "batch_window"
DEFAULT_BATCH_WINDOW = 3.0   # seconds: print requests inside this window become one strip
