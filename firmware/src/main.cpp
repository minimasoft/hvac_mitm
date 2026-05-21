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
            "<!DOCTYPE html><html><body><h1>HVAC Controller</h1><p>UI coming in S04</p></body></html>");
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
    server.handleClient();
}