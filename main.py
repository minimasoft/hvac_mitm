# Pin definitions for relay outputs
OUT_PIN_1 = 12
OUT_PIN_2 = 13
OUT_PIN_3 = 14
OUT_PIN_4 = 15

import machine
from time import sleep, time
import socket
import _thread

# Configure relay pins as output
relay_pins = [
    machine.Pin(OUT_PIN_1, machine.Pin.OUT),
    machine.Pin(OUT_PIN_2, machine.Pin.OUT),
    machine.Pin(OUT_PIN_3, machine.Pin.OUT),
    machine.Pin(OUT_PIN_4, machine.Pin.OUT),
]

# BTS7960 IBT-2 H-bridge motor controller pins
RPWM_PIN = 21  # Forward PWM
LPWM_PIN = 17  # Reverse PWM (held 0 for forward-only)
R_EN_PIN = 18  # Right enable (held high)
L_EN_PIN = 16  # Left enable (held high)

# BTS7960 PWM channels
pwm_rpwm = machine.PWM(machine.Pin(RPWM_PIN), freq=1000, duty_u16=0)
pwm_lpw = machine.PWM(machine.Pin(LPWM_PIN), freq=1000, duty_u16=0)

# BTS7960 enable pins (held high for forward-only operation)
en_r = machine.Pin(R_EN_PIN, machine.Pin.OUT)
en_l = machine.Pin(L_EN_PIN, machine.Pin.OUT)
en_r.value(1)
en_l.value(1)

# Status modes
MODE_BYPASS = "bypass"
MODE_30 = "30%"
MODE_50 = "50%"
MODE_70 = "70%"
MODE_AUTO_SAVE = "auto-power-save"

VALID_MODES = [MODE_BYPASS, MODE_30, MODE_50, MODE_70, MODE_AUTO_SAVE]

# Power level to PWM duty_u16 mapping (0-65535 scale)
POWER_LEVELS = {
    MODE_30: 19660,    # 30% of 65535
    MODE_50: 32767,    # 50% of 65535
    MODE_70: 45874,    # 70% of 65535
}

# Relay dance delay in seconds
RELAY_DANCE_DELAY = 0.2

# Auto-power-save timer constants
TIMER_INTERVAL_SEC = 60
TIMER_THRESHOLD_HOURS = 8

# Auto-restart timer constants
TIMER_INTERVAL_24H = 86400  # 24 hours in seconds

_last_mode_change = time()
_mode_lock = _thread.allocate_lock()
_relay_dance_in_progress = False

current_mode = MODE_BYPASS


def set_relay(pin_index, value):
    """Set a relay pin to a value (0 or 1)"""
    relay_pins[pin_index].value(value)


def set_all_relays(values):
    """Set all relays at once. values is a list of 4 values (0 or 1)"""
    for i, val in enumerate(values):
        relay_pins[i].value(val)


def bypass_to_powered():
    """Transition from bypass to any powered mode: first outputs 1 and 2, then 3 and 4"""
    global _relay_dance_in_progress
    _relay_dance_in_progress = True
    print("to powered")
    # Step 1: Set outputs 1 and 2 to 1
    set_relay(0, 1)
    set_relay(1, 1)
    sleep(RELAY_DANCE_DELAY)  # Wait 200ms
    # Step 2: Set outputs 3 and 4 to 1
    set_relay(2, 1)
    set_relay(3, 1)
    print("in powered")
    _relay_dance_in_progress = False


def powered_to_bypass():
    """Transition from any powered mode to bypass: first outputs 3 and 4, then 1 and 2"""
    global _relay_dance_in_progress
    _relay_dance_in_progress = True
    print("to bypass")
    # Step 1: Set outputs 3 and 4 to 0
    set_relay(2, 0)
    set_relay(3, 0)
    sleep(RELAY_DANCE_DELAY)  # Wait 200ms
    # Step 2: Set outputs 1 and 2 to 0
    set_relay(0, 0)
    set_relay(1, 0)
    print("in bypass")
    _relay_dance_in_progress = False


def powered_level(mode):
    """Return the power level (30, 50, 70) for a powered mode, or None for bypass/auto-save"""
    if mode in POWER_LEVELS:
        return int(mode.rstrip('%'))
    return None


def set_pwm(level):
    """Set BTS7960 differential PWM: RPWM at duty cycle, LPWM at 0"""
    if level in POWER_LEVELS:
        duty = POWER_LEVELS[level]
        pwm_rpwm.duty_u16(duty)
        pwm_lpw.duty_u16(0)
    else:
        # Bypass or auto-power-save (treated as 30% relay-wise, but PWM 0)
        pwm_rpwm.duty_u16(0)
        pwm_lpw.duty_u16(0)


def set_mode(mode):
    """Set the system mode with proper transition dance"""
    global current_mode
    global _last_mode_change

    if mode == current_mode:
        return

    with _mode_lock:
        is_auto_save = current_mode == MODE_AUTO_SAVE
        is_current_powered = is_auto_save or powered_level(current_mode) is not None
        is_new_powered = powered_level(mode) is not None

        if mode == MODE_BYPASS and is_current_powered:
            # Powered → bypass: dance then stop PWM
            powered_to_bypass()
            set_pwm(MODE_BYPASS)
        elif is_new_powered and current_mode == MODE_BYPASS:
            # Bypass → powered: dance then set PWM
            bypass_to_powered()
            set_pwm(mode)
        elif is_current_powered and is_new_powered:
            # Powered → powered: only change PWM
            set_pwm(mode)
        elif mode == MODE_AUTO_SAVE:
            # auto-power-save behaves like 30% for relay/PWM
            if current_mode == MODE_BYPASS:
                bypass_to_powered()
            set_pwm(MODE_30)

        current_mode = mode
        _last_mode_change = time()


def get_status():
    """Get the current status string"""
    global current_mode
    with _mode_lock:
        return current_mode


def auto_power_save_timer():
    """Background thread: check every 60s if at 50%/70% for 8+ hours, auto-drop to 30%"""
    while True:
        try:
            sleep(TIMER_INTERVAL_SEC)
            with _mode_lock:
                if current_mode in (MODE_50, MODE_70):
                    elapsed = time() - _last_mode_change
                    threshold = TIMER_THRESHOLD_HOURS * 3600
                    if elapsed >= threshold:
                        print(f"Auto-power-save: {current_mode} for {elapsed:.0f}s, dropping to 30%")
                        set_mode(MODE_30)
        except Exception as e:
            print(f"Timer error: {e}")
            sleep(TIMER_INTERVAL_SEC)


def auto_restart_timer():
    """Background thread: reboot every 24h if in bypass and not mid-dance"""
    while True:
        try:
            sleep(TIMER_INTERVAL_SEC)
            with _mode_lock:
                if (get_status() == MODE_BYPASS
                        and not _relay_dance_in_progress
                        and time() >= TIMER_INTERVAL_24H):
                    print(f"Auto-restart: {int(time())}s since boot, rebooting")
                    machine.reset()
        except Exception as e:
            print(f"Restart timer error: {e}")
            sleep(TIMER_INTERVAL_SEC)


# HTML page for root endpoint
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>HVAC Controller</title>
    <style>
        body { font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; }
        h1 { text-align: center; }
        .status-container { text-align: center; margin-bottom: 20px; }
        input[type="text"] { width: 80%; padding: 10px; font-size: 16px; text-align: center; }
        .buttons { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
        button { padding: 12px 18px; font-size: 14px; cursor: pointer; border: none; border-radius: 5px; }
        button.active { outline: 3px solid #333; outline-offset: 2px; font-weight: bold; }
        #btn-bypass { background-color: #4CAF50; color: white; }
        #btn-30 { background-color: #FF9800; color: white; }
        #btn-50 { background-color: #2196F3; color: white; }
        #btn-70 { background-color: #f44336; color: white; }
        #btn-auto { background-color: #9C27B0; color: white; }
    </style>
</head>
<body>
    <h1>HVAC Controller</h1>
    <div class="status-container">
        <input type="text" id="status-display" readonly placeholder="Loading...">
    </div>
    <div class="buttons">
        <button id="btn-bypass">Bypass</button>
        <button id="btn-30">30%</button>
        <button id="btn-50">50%</button>
        <button id="btn-70">70%</button>
        <button id="btn-auto">Auto Save</button>
    </div>

    <script>
        function updateStatus() {
            fetch('/status')
                .then(response => response.text())
                .then(text => {
                    document.getElementById('status-display').value = text;
                    // Highlight active button
                    document.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                    var modeToBtnId = {
                        'bypass': 'btn-bypass',
                        '30%': 'btn-30',
                        '50%': 'btn-50',
                        '70%': 'btn-70',
                        'auto-power-save': 'btn-auto'
                    };
                    var btn = document.getElementById(modeToBtnId[text]);
                    if (btn) btn.classList.add('active');
                })
                .catch(err => console.error('Error:', err));
        }

        function setMode(mode) {
            fetch('/mode', {
                method: 'POST',
                body: mode
            })
            .then(() => updateStatus())
            .catch(err => console.error('Error:', err));
        }

        setInterval(updateStatus, 1000);
        updateStatus();

        document.getElementById('btn-bypass').onclick = () => setMode('bypass');
        document.getElementById('btn-30').onclick = () => setMode('30%');
        document.getElementById('btn-50').onclick = () => setMode('50%');
        document.getElementById('btn-70').onclick = () => setMode('70%');
        document.getElementById('btn-auto').onclick = () => setMode('auto-power-save');
    </script>
</body>
</html>"""


def response_200(body, content_type='text/plain', connection_mode='close'):
    """Build a 200 OK response with security headers."""
    headers = "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nCache-Control: no-cache, no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Length: {}\r\nConnection: {}\r\n\r\n".format(content_type, len(body.encode('utf-8')), connection_mode)
    return headers + body


def response_400(body, connection_mode='close'):
    """Build a 400 Bad Request response with security headers."""
    headers = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\nCache-Control: no-cache, no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Length: {}\r\nConnection: {}\r\n\r\n".format(len(body.encode('utf-8')), connection_mode)
    return headers + body


def response_404(body, connection_mode='close'):
    """Build a 404 Not Found response with security headers."""
    headers = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nCache-Control: no-cache, no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Length: {}\r\nConnection: {}\r\n\r\n".format(len(body.encode('utf-8')), connection_mode)
    return headers + body


def recv_loop(conn):
    """Read from socket until \\r\\n\\r\\n is found, handling fragmented TCP packets."""
    buf = bytearray()
    while b'\r\n\r\n' not in buf:
        try:
            data = conn.recv(2048)
            if not data:
                break
            buf.extend(data)
        except OSError:
            break
    return bytes(buf)


def http_server():
    """Start the HTTP server on port 11337"""
    addr = socket.getaddrinfo('0.0.0.0', 11337)[0][-1]
    sock = socket.socket()
    sock.bind(addr)
    sock.listen(5)

    print("HTTP server listening on port 11337")

    try:
        while True:
            conn, client_addr = sock.accept()
            conn.settimeout(5.0)
            try:
                request = recv_loop(conn)
                request_str = request.decode('utf-8')

                # Parse the request
                lines = request_str.split('\r\n')
                if not lines:
                    conn.close()
                    continue

                # Guard against malformed request lines (need at least method + path)
                if len(lines) == 0 or len(lines[0].split(' ')) < 2:
                    response = response_400("Bad request line")
                    conn.send(response.encode('utf-8'))
                    continue

                method, path, *_ = lines[0].split(' ')
                print(f"[{method} {path}]")

                if path == '/' and method == 'GET':
                    # Serve the HTML page
                    response = response_200(HTML_PAGE, 'text/html')
                    conn.send(response.encode('utf-8'))

                elif path == '/mode' and method == 'POST':
                    # Handle mode change
                    body = request_str.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request_str else ''
                    mode = body.strip() if body else ''

                    if mode in VALID_MODES:
                        set_mode(mode)
                        print(f"[POST /mode -> {mode}]")
                        response = response_200("OK")
                    else:
                        print(f"[POST /mode -> invalid: {mode}]")
                        response = response_400("Invalid mode: {}".format(mode))
                    conn.send(response.encode('utf-8'))

                elif path == '/status' and method == 'GET':
                    # Return current status
                    status = get_status()
                    response = response_200(status)
                    conn.send(response.encode('utf-8'))

                else:
                    # Not found
                    print(f"[{method} {path} -> 404]")
                    response = response_404("Not Found")
                    conn.send(response.encode('utf-8'))

            except Exception as e:
                print(f"[error: {e}]")
            finally:
                conn.close()
    except KeyboardInterrupt:
        print("Server stopped")
    except Exception as e:
        print(f"[error: {e}]")


def init_bypass():
    """Initialize system in bypass mode on boot"""
    set_all_relays([0, 0, 0, 0])
    set_pwm(MODE_BYPASS)


def start_timer():
    """Start the auto-power-save background timer thread"""
    try:
        _thread.start_new_thread(auto_power_save_timer, ())
        print("Auto-power-save timer started")
    except Exception as e:
        print(f"Failed to start timer: {e}")


def start_auto_restart():
    """Start the auto-restart background timer thread"""
    try:
        _thread.start_new_thread(auto_restart_timer, ())
        print("Auto-restart timer started")
    except Exception as e:
        print(f"Failed to start auto-restart timer: {e}")


# Initialize and run
init_bypass()
start_timer()
start_auto_restart()
http_server()
