#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <LittleFS.h>
#include "motor_controller.h"

// ============================================================
// WiFi Configuration Constants
// ============================================================
#define WIFI_RETRY_INTERVAL_MS  300000  // 5 minutes between reconnect attempts
#define WIFI_CONNECT_TIMEOUT_S  20      // seconds to wait for connection

// ============================================================
// WiFi Module-Level State
// ============================================================
static String wifi_ssid = "";
static bool   wifi_enabled = false;
static unsigned long last_wifi_check_ms = 0;

// ============================================================
// HTTP Server State
// ============================================================
WebServer server(11337);

// ============================================================
// WiFi Initialization
// ============================================================
void init_wifi() {
    // Attempt to mount LittleFS to read credential files
    if (!LittleFS.begin()) {
        Serial.println("WiFi: LittleFS mount failed, skipping WiFi");
        return;
    }

    // Read SSID from /.ssid file
    File ssid_file = LittleFS.open("/.ssid", "r");
    if (!ssid_file) {
        Serial.println("WiFi: .ssid file not found, skipping WiFi connection");
        LittleFS.end();
        return;
    }

    wifi_ssid = ssid_file.readStringUntil('\n');
    wifi_ssid.trim();
    ssid_file.close();

    // Read PSK from /.psk (optional — open network if file is missing)
    String wifi_psk = "";
    File psk_file = LittleFS.open("/.psk", "r");
    if (psk_file) {
        wifi_psk = psk_file.readStringUntil('\n');
        wifi_psk.trim();
        psk_file.close();
    }

    LittleFS.end();

    // Begin WiFi connection
    Serial.print("WiFi: Connecting to ");
    Serial.println(wifi_ssid);

    const char* psk_c_str = wifi_psk.length() > 0 ? wifi_psk.c_str() : NULL;
    WiFi.begin(wifi_ssid.c_str(), psk_c_str);

    // Non-blocking poll loop: up to WIFI_CONNECT_TIMEOUT_S seconds
    int attempts = 0;
    while (attempts < WIFI_CONNECT_TIMEOUT_S && WiFi.status() != WL_CONNECTED) {
        delay(1000);
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        wifi_enabled = true;
        Serial.print("WiFi: Connected, IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("WiFi: Connection failed");
    }
}

// ============================================================
// WiFi Periodic Handler (called from loop)
// ============================================================
void handle_wifi() {
    unsigned long now = millis();
    if (now - last_wifi_check_ms < WIFI_RETRY_INTERVAL_MS) {
        return;
    }
    last_wifi_check_ms = now;

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi: Connection lost, attempting to reconnect...");
        WiFi.reconnect();
    }
}

// ============================================================
// HTTP Server Handler Functions
// ============================================================

static void add_security_headers() {
    server.sendHeader("Cache-Control", "no-cache, no-store");
    server.sendHeader("X-Content-Type-Options", "nosniff");
}

static void handle_root() {
    try {
        Serial.println("[GET /]");
        add_security_headers();
        server.send(200, "text/html",
            R"rawliteral(<!DOCTYPE html>
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

        setInterval(updateStatus, 2222);
        updateStatus();

        document.getElementById('btn-bypass').onclick = () => setMode('bypass');
        document.getElementById('btn-30').onclick = () => setMode('30%');
        document.getElementById('btn-50').onclick = () => setMode('50%');
        document.getElementById('btn-70').onclick = () => setMode('70%');
        document.getElementById('btn-auto').onclick = () => setMode('auto-power-save');
    </script>
</body>
</html> )rawliteral");
    } catch (const std::exception& e) {
        Serial.print("[error: ");
        Serial.print(e.what());
        Serial.println("]");
        server.send(500, "text/plain", "Internal Server Error");
    }
}

static void handle_mode_post() {
    try {
        Serial.println("[POST /mode]");
        if (!server.hasArg("plain")) {
            server.send(400, "text/plain", "Missing mode");
            return;
        }

        String body = server.arg("plain");
        body.trim();

        if (body.length() == 0) {
            server.send(400, "text/plain", "Missing mode");
            return;
        }

        const char* raw = body.c_str();

        // Validate against known modes
        bool valid = false;
        for (int i = 0; i < 5; i++) {
            if (strcmp(raw, VALID_MODES[i]) == 0) {
                valid = true;
                break;
            }
        }

        if (!valid) {
            Serial.print("[POST /mode -> invalid: ");
            Serial.print(raw);
            Serial.println("]");
            server.send(400, "text/plain", "Invalid mode: " + String(raw));
            return;
        }

        set_mode(raw);

        Serial.print("[POST /mode -> ");
        Serial.print(raw);
        Serial.println("]");
        server.send(200, "text/plain", "OK");
    } catch (const std::exception& e) {
        Serial.print("[error: ");
        Serial.print(e.what());
        Serial.println("]");
        server.send(500, "text/plain", "Internal Server Error");
    }
}

static void handle_status_get() {
    try {
        Serial.println("[GET /status]");
        const char* status = get_status();
        server.send(200, "text/plain", String(status));
    } catch (const std::exception& e) {
        Serial.print("[error: ");
        Serial.print(e.what());
        Serial.println("]");
        server.send(500, "text/plain", "Internal Server Error");
    }
}

static void handle_not_found() {
    try {
        String method = server.method() == HTTP_GET ? "GET" : "POST";
        Serial.print("[");
        Serial.print(method);
        Serial.print(" ");
        Serial.print(server.uri());
        Serial.println(" -> 404]");
        server.send(404, "text/plain", "Not Found");
    } catch (const std::exception& e) {
        Serial.print("[error: ");
        Serial.print(e.what());
        Serial.println("]");
        server.send(500, "text/plain", "Internal Server Error");
    }
}

// ============================================================
// HTTP Server Initialization
// ============================================================

void init_http_server() {
    server.on("/", HTTP_GET, handle_root);
    server.on("/mode", HTTP_POST, handle_mode_post);
    server.on("/status", HTTP_GET, handle_status_get);
    server.onNotFound(handle_not_found);
    server.begin();
    Serial.println("HTTP server listening on port 11337");
}

// ============================================================
// Setup
// ============================================================
void setup() {
    Serial.begin(115200);
    delay(100);
    boot_ms = millis();
    init_bypass();
    init_wifi();
    init_http_server();
    Serial.println("HVAC controller started");
}

// ============================================================
// Main Loop
// ============================================================
void loop() {
    handle_wifi();
    handle_auto_power_save();
    handle_auto_restart();
    server.handleClient();
}