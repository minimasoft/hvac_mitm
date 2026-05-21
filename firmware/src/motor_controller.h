#ifndef MOTOR_CONTROLLER_H
#define MOTOR_CONTROLLER_H

// ============================================================
// Pin Definitions
// ============================================================

// Relay output pins
#define RELAY_1  12
#define RELAY_2  13
#define RELAY_3  14
#define RELAY_4  15

// BTS7960 IBT-2 H-bridge motor controller pins
#define RPWM     21  // Forward PWM
#define LPWM     17  // Reverse PWM (held 0 for forward-only)
#define R_EN     18  // Right enable (held high)
#define L_EN     16  // Left enable (held high)

// ============================================================
// Mode String Constants
// ============================================================

#define MODE_BYPASS      "bypass"
#define MODE_30           "30%"
#define MODE_50           "50%"
#define MODE_70           "70%"
#define MODE_AUTO_SAVE    "auto-power-save"

extern const char* VALID_MODES[5];

// ============================================================
// PWM Duty Values (16-bit, 0-65535)
// ============================================================

#define PWM_30_DUTY   19660   // 30% of 65535
#define PWM_50_DUTY   32767   // 50% of 65535
#define PWM_70_DUTY   45874   // 70% of 65535

#define RELAY_DANCE_DELAY_MS  200

// ============================================================
// Auto Power-Save / Auto-Restart Timer Thresholds
// ============================================================

#define AUTO_POWER_SAVE_THRESHOLD_MS  28800000UL  // 8 hours
#define AUTO_RESTART_THRESHOLD_MS    86400000UL  // 24 hours

// ============================================================
// Global State
// ============================================================

extern const char* current_mode;
extern unsigned long last_mode_change_ms;
extern unsigned long boot_ms;

// ============================================================
// Function Declarations
// ============================================================

void init_bypass();
void set_mode(const char* mode);
const char* get_status();
void set_pwm(const char* level);
int  powered_level(const char* mode);

void bypass_to_powered();
void powered_to_bypass();

void set_relay(int index, int value);
void set_all_relays(int v0, int v1, int v2, int v3);

// ============================================================
// Timer Handlers (called from main.cpp loop())
// ============================================================

void handle_auto_power_save();
void handle_auto_restart();

#endif // MOTOR_CONTROLLER_H