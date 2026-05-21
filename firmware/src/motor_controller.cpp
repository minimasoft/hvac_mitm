#include "motor_controller.h"
#include <Arduino.h>

// ============================================================
// Relay Pin Array
// ============================================================
static const int relay_pins[4] = { RELAY_1, RELAY_2, RELAY_3, RELAY_4 };

// ============================================================
// Valid modes array
// ============================================================
const char* VALID_MODES[5] = {
    MODE_BYPASS, MODE_30, MODE_50, MODE_70, MODE_AUTO_SAVE
};

// ============================================================
// Global State
// ============================================================
const char* current_mode = MODE_BYPASS;
unsigned long last_mode_change_ms = 0;

// ============================================================
// GPIO Helpers
// ============================================================

void set_relay(int index, int value) {
    if (index >= 0 && index < 4) {
        digitalWrite(relay_pins[index], value ? HIGH : LOW);
    }
}

void set_all_relays(int v0, int v1, int v2, int v3) {
    digitalWrite(RELAY_1, v0 ? HIGH : LOW);
    digitalWrite(RELAY_2, v1 ? HIGH : LOW);
    digitalWrite(RELAY_3, v2 ? HIGH : LOW);
    digitalWrite(RELAY_4, v3 ? HIGH : LOW);
}

// ============================================================
// Relay Dance Sequences
// ============================================================

void bypass_to_powered() {
    Serial.println("to powered");
    // Step 1: Set outputs 1 and 2 to 1
    set_relay(0, 1);
    set_relay(1, 1);
    delay(RELAY_DANCE_DELAY_MS);
    // Step 2: Set outputs 3 and 4 to 1
    set_relay(2, 1);
    set_relay(3, 1);
    Serial.println("in powered");
}

void powered_to_bypass() {
    Serial.println("to bypass");
    // Step 1: Set outputs 3 and 4 to 0
    set_relay(2, 0);
    set_relay(3, 0);
    delay(RELAY_DANCE_DELAY_MS);
    // Step 2: Set outputs 1 and 2 to 0
    set_relay(0, 0);
    set_relay(1, 0);
    Serial.println("in bypass");
}

// ============================================================
// PWM Control
// ============================================================

void set_pwm(const char* level) {
    int duty = 0;
    if (level == MODE_30)       duty = PWM_30_DUTY;
    else if (level == MODE_50)  duty = PWM_50_DUTY;
    else if (level == MODE_70)  duty = PWM_70_DUTY;

    // Differential PWM: RPWM at duty cycle, LPWM at 0
    ledcWrite(0, duty);   // Channel 0 = RPWM
    ledcWrite(1, 0);      // Channel 1 = LPWM (held at 0)
}

// ============================================================
// Mode Helpers
// ============================================================

int powered_level(const char* mode) {
    if (mode == MODE_30) return 30;
    if (mode == MODE_50) return 50;
    if (mode == MODE_70) return 70;
    return 0;  // bypass or auto-power-save
}

// ============================================================
// Mode Transitions
// ============================================================

void set_mode(const char* mode) {
    if (mode == current_mode) {
        return;
    }

    bool is_current_powered = (current_mode == MODE_AUTO_SAVE ||
                                powered_level(current_mode) > 0);
    bool is_new_powered = (powered_level(mode) > 0);

    if (mode == MODE_BYPASS && is_current_powered) {
        // Powered -> bypass: dance then stop PWM
        powered_to_bypass();
        set_pwm(MODE_BYPASS);
    } else if (is_new_powered && current_mode == MODE_BYPASS) {
        // Bypass -> powered: dance then set PWM
        bypass_to_powered();
        set_pwm(mode);
    } else if (is_current_powered && is_new_powered) {
        // Powered -> powered: only change PWM
        set_pwm(mode);
    } else if (mode == MODE_AUTO_SAVE) {
        // auto-power-save behaves like 30% for relay/PWM
        if (current_mode == MODE_BYPASS) {
            bypass_to_powered();
        }
        set_pwm(MODE_30);
    }

    current_mode = mode;
    last_mode_change_ms = millis();
}

const char* get_status() {
    return current_mode;
}

// ============================================================
// Initialization
// ============================================================

void init_bypass() {
    // CRITICAL: Relays must be OFF before any PWM init
    set_all_relays(0, 0, 0, 0);

    // Configure relay pins
    for (int i = 0; i < 4; i++) {
        pinMode(relay_pins[i], OUTPUT);
    }

    // Configure BTS7960 enable pins (held HIGH for forward-only)
    pinMode(R_EN, OUTPUT);
    pinMode(L_EN, OUTPUT);
    digitalWrite(R_EN, HIGH);
    digitalWrite(L_EN, HIGH);

    // Configure PWM channels: 1000Hz, 16-bit resolution
    // Channel 0 = RPWM (GPIO 21), Channel 1 = LPWM (GPIO 17)
    ledcSetup(0, 1000, 16);
    ledcAttachPin(RPWM, 0);
    ledcSetup(1, 1000, 16);
    ledcAttachPin(LPWM, 1);

    // Ensure PWM is 0 in bypass
    ledcWrite(0, 0);
    ledcWrite(1, 0);

    current_mode = MODE_BYPASS;
    last_mode_change_ms = millis();
}