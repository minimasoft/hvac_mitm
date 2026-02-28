# boot.py - System initialization on boot
import network
import time
import _thread

WIFI_RETRY_INTERVAL_MS = 300000  # 5 minutes


def connect_wifi():
    """Attempt to connect to WiFi using credentials from files."""
    try:
        with open('.ssid', 'r') as f:
            ssid = f.read().strip()
    except OSError:
        print("WiFi: .ssid file not found, skipping WiFi connection")
        return None

    psk = None
    try:
        with open('.psk', 'r') as f:
            psk = f.read().strip()
    except OSError:
        pass

    print(f"WiFi: Connecting to {ssid}...")

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if psk is not None:
        wlan.connect(ssid, psk)
    else:
        wlan.connect(ssid)

    # Wait for connection
    timeout = 20  # 20 seconds timeout
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1

    if wlan.isconnected():
        print(f"WiFi: Connected, IP: {wlan.ifconfig()[0]}")
        return wlan
    else:
        print("WiFi: Connection failed")
        return None


def wifi_keepalive(wlan):
    """Keep WiFi connected, attempting reconnection every 5 minutes."""
    while True:
        # If already connected, wait for disconnection
        if wlan and wlan.isconnected():
            while wlan.isconnected():
                time.sleep(WIFI_RETRY_INTERVAL_MS / 1000)
            print("WiFi: Connection lost, attempting to reconnect...")
        else:
            # No initial connection or reconnection failed, retry after interval
            time.sleep(WIFI_RETRY_INTERVAL_MS / 1000)

        # Attempt to reconnect
        wlan = connect_wifi()


# Try to connect to WiFi in a background thread
wifi_thread = None


def start_wifi():
    global wifi_thread
    wlan = connect_wifi()

    if wlan:
        # Start keepalive thread only if connection succeeded or we want to retry
        try:
            wifi_thread = _thread.start_new_thread(wifi_keepalive, (wlan,))
        except Exception as e:
            print("WiFi: Failed to start keepalive thread:", e)


start_wifi()
import main

