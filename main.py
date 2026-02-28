# Pin definitions for relay outputs
OUT_PIN_1 = 23
OUT_PIN_2 = 22
OUT_PIN_3 = 21
OUT_PIN_4 = 19

import machine
from time import sleep
import socket

# Configure relay pins as output
relay_pins = [
    machine.Pin(OUT_PIN_1, machine.Pin.OUT),
    machine.Pin(OUT_PIN_2, machine.Pin.OUT),
    machine.Pin(OUT_PIN_3, machine.Pin.OUT),
    machine.Pin(OUT_PIN_4, machine.Pin.OUT),
]

# Status modes
MODE_BYPASS = "bypass"
MODE_OVERRIDE = "override"

current_mode = MODE_BYPASS


def set_relay(pin_index, value):
    """Set a relay pin to a value (0 or 1)"""
    relay_pins[pin_index].value(value)


def set_all_relays(values):
    """Set all relays at once. values is a list of 4 values (0 or 1)"""
    for i, val in enumerate(values):
        relay_pins[i].value(val)


def bypass_to_override():
    """Transition from bypass to override: first outputs 1 and 2, then 3 and 4"""
    # Step 1: Set outputs 1 and 2 to 1
    set_relay(0, 1)
    set_relay(1, 1)
    sleep(0.2)  # Wait 200ms
    # Step 2: Set outputs 3 and 4 to 1
    set_relay(2, 1)
    set_relay(3, 1)


def override_to_bypass():
    """Transition from override to bypass: first outputs 3 and 4, then 1 and 2"""
    # Step 1: Set outputs 3 and 4 to 0
    set_relay(2, 0)
    set_relay(3, 0)
    sleep(0.2)  # Wait 200ms
    # Step 2: Set outputs 1 and 2 to 0
    set_relay(0, 0)
    set_relay(1, 0)


def set_mode(mode):
    """Set the system mode with proper transition dance"""
    global current_mode
    
    if mode == current_mode:
        return
    
    if mode == MODE_OVERRIDE and current_mode == MODE_BYPASS:
        bypass_to_override()
    elif mode == MODE_BYPASS and current_mode == MODE_OVERRIDE:
        override_to_bypass()
    
    current_mode = mode


def get_status():
    """Get the current status string"""
    global current_mode
    return current_mode


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
        .buttons { display: flex; gap: 10px; justify-content: center; }
        button { padding: 15px 30px; font-size: 16px; cursor: pointer; border: none; border-radius: 5px; }
        #btn-bypass { background-color: #4CAF50; color: white; }
        #btn-override { background-color: #2196F3; color: white; }
    </style>
</head>
<body>
    <h1>HVAC Controller</h1>
    <div class="status-container">
        <input type="text" id="status-display" readonly placeholder="Loading...">
    </div>
    <div class="buttons">
        <button id="btn-bypass">Bypass</button>
        <button id="btn-override">Override</button>
    </div>
    
    <script>
        function updateStatus() {
            fetch('/status')
                .then(response => response.text())
                .then(text => document.getElementById('status-display').value = text)
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
        document.getElementById('btn-override').onclick = () => setMode('override');
    </script>
</body>
</html>"""


def http_server():
    """Start the HTTP server on port 11337"""
    addr = socket.getaddrinfo('0.0.0.0', 11337)[0][-1]
    sock = socket.socket()
    sock.bind(addr)
    sock.listen(5)
    
    print("HTTP server listening on port 11337")
    
    while True:
        conn, client_addr = sock.accept()
        try:
            request = conn.recv(1024)
            request_str = request.decode('utf-8', errors='ignore')
            
            # Parse the request
            lines = request_str.split('\r\n')
            if not lines:
                conn.close()
                continue
            
            method, path, *_ = lines[0].split(' ')
            
            if path == '/' and method == 'GET':
                # Serve the HTML page
                response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}".format(len(HTML_PAGE), HTML_PAGE)
                conn.send(response.encode('utf-8'))
            
            elif path == '/mode' and method == 'POST':
                # Handle mode change
                body = request_str.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request_str else ''
                mode = body.strip() if body else ''
                
                if mode in [MODE_BYPASS, MODE_OVERRIDE]:
                    set_mode(mode)
                    response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
                else:
                    response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\nContent-Length: 11\r\nConnection: close\r\n\r\nInvalid mode"
                conn.send(response.encode('utf-8'))
            
            elif path == '/status' and method == 'GET':
                # Return current status
                status = get_status()
                response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}".format(len(status), status)
                conn.send(response.encode('utf-8'))
            
            else:
                # Not found
                response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found"
                conn.send(response.encode('utf-8'))
        
        except Exception as e:
            print("Error:", e)
        finally:
            conn.close()


def init_bypass():
    """Initialize system in bypass mode on boot"""
    set_all_relays([0, 0, 0, 0])


# Initialize and run
init_bypass()
http_server()
