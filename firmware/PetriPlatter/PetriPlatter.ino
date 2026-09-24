/*
 * PetriPlatter — ESP32 + TMC2209 firmware for rotating a petri dish during streaking.
 *
 * Chain:  Robot -> platter.exe (Python) -> USB Serial -> ESP32 -> TMC2209 -> NEMA17 -> dish
 *         GUI (platter_gui) writes programs into the ESP32 flash; the robot runs them by slot.
 *
 * Libraries (Arduino Library Manager):
 *   - TMCStepper   by teemuatlut
 *   - AccelStepper by Mike McCauley
 * Board: "XIAO_ESP32C3" (Seeed XIAO ESP32-C3, esp32 core by Espressif)
 *   Tools -> USB CDC On Boot: "Enabled"   (the USB-C port is the chip's own USB = Serial)
 *
 * Protocol (USB, 115200, lines end with '\n'). Every command gets exactly one reply line,
 * starting with "OK" or "ERR <reason>".
 *
 *   PING                     -> OK PONG
 *   INFO                     -> OK SLOTS=20 MAX_STEPS=32 MIN_RPM=0.1 MAX_RPM=120 MAX_DEG=36000 MAX_WAIT_MS=600000 ACCEL=1
 *   DIAG                     -> OK A0=<bytes>/0x<ver> A1=... A2=... A3=...   (driver UART wiring test)
 *                               per driver address: bytes received for one read request.
 *                               0 = nothing on the line (XIAO<->USART wiring), 4 = only our own echo
 *                               (driver silent: no 24V / wrong pin), 12 = driver answered (ver 0x21).
 *   STATUS                   -> OK EN=<0|1> BUSY=<0|1> STEP=<i>/<n> POS=<deg> DRV=<0xNN> CUR=<mA> UP=<s> URX=<n>
 *                               UP = seconds since boot; if it drops, the controller was reset.
 *                               URX = times the driver UART froze and was restarted (should stay 0).
 *   EN | DIS                 -> OK            (hold / release the dish)
 *   ZERO                     -> OK            (current position = 0 deg)
 *   ROT <deg> <rpm>          -> OK            (after the motion ends)
 *   RUN <slot>               -> OK            (after the whole program ends)
 *   STOP                     -> OK when idle. While busy it sends NO reply of its own:
 *                               the running ROT/RUN answers "ERR STOPPED" instead.
 *
 *   Program storage (slots 1..20, kept in flash across power cycles):
 *   PLIST                    -> OK 1=Streak A,3=Quadrants        (empty: "OK")
 *   PGET <slot>              -> OK <program>
 *   PSET <slot> <program>    -> OK
 *   PDEL <slot>              -> OK
 *
 *   <program> = <name>|<step>|<step>|...
 *   <step>    = ROT <deg> <rpm>      negative deg = other direction (holds the dish on its own)
 *             | WAIT <ms>
 *             | HOLD                 energise the motor: the dish is locked
 *             | RELEASE              de-energise: the dish turns freely by hand
 *   <name>    = 1..24 chars, no '|' ',' '='
 *   Example:  PSET 1 Streak A|HOLD|ROT 360 20|WAIT 1500|ROT -180 10|RELEASE
 */

#include <TMCStepper.h>
#include <AccelStepper.h>
#include <Preferences.h>

// ---------------- Pins: XIAO ESP32-C3 (see Motor_Driver_Design_Notes.md, section 5) ----------------
// Strapping pins D0 (GPIO2), D8 (GPIO8), D9 (GPIO9 = BOOT button) are left unused.
// D6/D7 (GPIO21/20) are left free too: the ROM prints its boot log on GPIO21.
constexpr uint8_t PIN_EN      = 3;    // D1  LOW = driver active, 10k pull-up keeps it OFF on boot
constexpr uint8_t PIN_STEP    = 4;    // D2
constexpr uint8_t PIN_DIR     = 5;    // D3
constexpr uint8_t PIN_UART_TX = 6;    // D4  via 1k to USART
constexpr uint8_t PIN_UART_RX = 7;    // D5  direct to USART

// ---------------- Motor / driver ----------------
constexpr float    R_SENSE        = 0.11f;   // R110 on the board — verify
constexpr uint8_t  DRIVER_ADDR    = 0b00;    // MS1 = MS2 = GND
constexpr uint16_t RUN_CURRENT_MA = 560;     // 80% of 0.7 A rms
constexpr float    HOLD_MULT      = 0.5f;    // hold current = 50% of run current
constexpr uint16_t MICROSTEPS     = 16;
constexpr long     FULL_STEPS     = 200;
constexpr long     STEPS_PER_REV  = FULL_STEPS * MICROSTEPS;   // 3200
constexpr bool     INVERT_DIR     = false;   // flip if the dish turns the wrong way

// ---------------- Limits ----------------
constexpr float    MIN_RPM      = 0.1f;
constexpr float    MAX_RPM      = 120.0f;
constexpr float    MAX_DEG      = 36000.0f;   // 100 revolutions per step
constexpr uint32_t MAX_WAIT_MS  = 600000;     // 10 minutes per step
constexpr float    ACCEL_REV_S2 = 1.0f;       // gentle ramp so the agar/dish doesn't slip
constexpr int      NUM_SLOTS    = 20;
constexpr int      MAX_STEPS    = 32;
constexpr size_t   MAX_NAME     = 24;
constexpr size_t   CMD_LINE_MAX     = 1024;

// ---------------- Types ----------------
enum StepKind : uint8_t { STEP_ROT, STEP_WAIT, STEP_HOLD, STEP_RELEASE };

struct Step {
  StepKind kind;
  float    deg;   // ROT
  float    rpm;   // ROT
  uint32_t ms;    // WAIT
};

enum Phase { IDLE, MOVING, WAITING };

// ---------------- Globals ----------------
HardwareSerial& DriverSerial = Serial1;   // the C3 has UART0 and UART1 only
TMC2209Stepper driver(&DriverSerial, R_SENSE, DRIVER_ADDR);
AccelStepper   stepper(AccelStepper::DRIVER, PIN_STEP, PIN_DIR);
Preferences    store;

bool     motorEnabled    = false;
uint8_t  driverVersion   = 0;
uint16_t driverCurrentMa = 0;
bool     driverConfigured = false;
uint16_t uartRecoveries   = 0;   // UART to the driver froze and a restart brought it back

// program runner
Step     prog[MAX_STEPS];
int      progLen = 0;
int      progIdx = 0;
Phase    phase   = IDLE;
uint32_t waitStart = 0;
uint32_t waitMs    = 0;
bool     stopRequested = false;

char   lineBuf[CMD_LINE_MAX];
size_t lineLen = 0;
bool   lineOverflow = false;   // discard the rest of an over-long line

// ------------------------------------------------------------------------------------
// Helpers

void reply(const char* msg) {
  Serial.println(msg);
}

void replyErr(const char* reason) {
  Serial.print("ERR ");
  Serial.println(reason);
}

void setMotorEnabled(bool on) {
  digitalWrite(PIN_EN, on ? LOW : HIGH);
  motorEnabled = on;
}

float rpmToStepsPerSec(float rpm) {
  return rpm * STEPS_PER_REV / 60.0f;
}

float positionDeg() {
  return stepper.currentPosition() * 360.0f / STEPS_PER_REV;
}

// ------------------------------------------------------------------------------------
// Driver. The TMC2209 logic runs from VM (24V): with only USB/3.3V it does not answer, and
// every time VM comes back it restarts with default settings (current from the potentiometer!).
// So the driver is checked, and re-configured if needed, before anything energises the motor.

void configureDriver() {
  driver.pdn_disable(true);        // PDN pin is used for UART
  driver.I_scale_analog(false);    // ignore the VREF potentiometer, current set in software
  driver.mstep_reg_select(true);   // microsteps from register, not MS1/MS2
  driver.toff(4);
  driver.blank_time(24);
  driver.rms_current(RUN_CURRENT_MA, HOLD_MULT);
  driver.microsteps(MICROSTEPS);
  driver.intpol(true);             // 256 interpolation
  driver.en_spreadCycle(false);    // StealthChop: quiet and smooth at low speed
  driver.pwm_autoscale(true);
  driver.pwm_autograd(true);
  driver.TPOWERDOWN(20);           // ~0.4 s after the last step -> drop to hold current
  driver.GSTAT(0b111);             // clear the "reset" flag, so a later power cycle is detected

  driverCurrentMa = driver.rms_current();
  driverConfigured = true;
}

// true = driver answers and holds our settings. Talks over UART (a few ms): call only when idle.
void startDriverSerial() {
  DriverSerial.begin(115200, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);
}

bool ensureDriver() {
  driverVersion = driver.version();
  if (driverVersion != 0x21) {
    // The C3's receiver on this line has been seen to stop receiving altogether (not even its
    // own echo) while the motor was held, until the controller was reset. Restarting just the
    // UART brings it back; count it only when that is what fixed it, not when the 24V is off.
    DriverSerial.end();
    startDriverSerial();
    driverVersion = driver.version();
    if (driverVersion == 0x21) uartRecoveries++;
  }
  if (driverVersion != 0x21) {
    driverConfigured = false;
    return false;
  }
  // GSTAT bit0 = the driver restarted (VM came back), bit1 = it shut its outputs down
  // (overtemperature / short, e.g. when VM rises while ENN is already low). Both are latched:
  // the outputs stay off until ENN is toggled, so reconfigure with ENN high, then restore it.
  if (!driverConfigured || (driver.GSTAT() & 0x03)) {
    digitalWrite(PIN_EN, HIGH);
    configureDriver();
    delay(2);
    digitalWrite(PIN_EN, motorEnabled ? LOW : HIGH);
  }
  return true;
}

void toUpper(char* s) {
  for (; *s; ++s) *s = toupper(*s);
}

// Returns true if s was a valid float and writes it to out.
bool parseFloat(const char* s, float& out) {
  if (!s || !*s) return false;
  char* end;
  out = strtof(s, &end);
  return *end == '\0' && isfinite(out);
}

// Returns slot 1..NUM_SLOTS, or 0 if invalid.
int parseSlot(const char* s) {
  float f;
  if (!parseFloat(s, f) || f != floorf(f) || f < 1 || f > NUM_SLOTS) return 0;
  return (int)f;
}

void slotKey(int slot, char* key) {
  snprintf(key, 8, "p%d", slot);
}

// ------------------------------------------------------------------------------------
// Program parsing. All parsers return nullptr on success or an error reason.

const char* parseStep(char* s, Step& st) {
  char* save;
  char* kind  = strtok_r(s, " ", &save);
  char* a     = strtok_r(nullptr, " ", &save);
  char* b     = strtok_r(nullptr, " ", &save);
  char* extra = strtok_r(nullptr, " ", &save);
  if (!kind) return "BAD_STEP";
  toUpper(kind);

  if (!strcmp(kind, "ROT")) {
    float deg, rpm;
    if (!parseFloat(a, deg) || !parseFloat(b, rpm) || extra) return "BAD_ARGS";
    if (fabsf(deg) > MAX_DEG)           return "DEG_RANGE";
    if (rpm < MIN_RPM || rpm > MAX_RPM) return "RPM_RANGE";
    st = {STEP_ROT, deg, rpm, 0};
    return nullptr;
  }
  if (!strcmp(kind, "WAIT")) {
    float ms;
    if (!parseFloat(a, ms) || b) return "BAD_ARGS";
    if (ms < 0 || ms > MAX_WAIT_MS) return "WAIT_RANGE";
    st = {STEP_WAIT, 0, 0, (uint32_t)ms};
    return nullptr;
  }
  if (!strcmp(kind, "HOLD") || !strcmp(kind, "RELEASE")) {
    if (a) return "BAD_ARGS";
    st = {kind[0] == 'H' ? STEP_HOLD : STEP_RELEASE, 0, 0, 0};
    return nullptr;
  }
  return "BAD_STEP";
}

// text = "<name>|<step>|<step>..." (modified in place). name must hold MAX_NAME+1 chars.
const char* parseProgram(char* text, char* name, Step* steps, int& n) {
  char* save;
  char* nm = strtok_r(text, "|", &save);
  if (!nm) return "BAD_NAME";
  size_t len = strlen(nm);
  if (len == 0 || len > MAX_NAME || strpbrk(nm, ",=")) return "BAD_NAME";
  strcpy(name, nm);

  n = 0;
  for (char* s = strtok_r(nullptr, "|", &save); s; s = strtok_r(nullptr, "|", &save)) {
    if (n >= MAX_STEPS) return "TOO_MANY_STEPS";
    const char* err = parseStep(s, steps[n]);
    if (err) return err;
    n++;
  }
  return n ? nullptr : "NO_STEPS";
}

// Canonical text form, so what PGET returns is always parseable.
void formatProgram(const char* name, const Step* steps, int n, char* out, size_t size) {
  size_t pos = snprintf(out, size, "%s", name);
  for (int i = 0; i < n && pos < size; ++i) {
    switch (steps[i].kind) {
      case STEP_ROT:
        pos += snprintf(out + pos, size - pos, "|ROT %g %g", steps[i].deg, steps[i].rpm);
        break;
      case STEP_WAIT:
        pos += snprintf(out + pos, size - pos, "|WAIT %lu", (unsigned long)steps[i].ms);
        break;
      case STEP_HOLD:
        pos += snprintf(out + pos, size - pos, "|HOLD");
        break;
      case STEP_RELEASE:
        pos += snprintf(out + pos, size - pos, "|RELEASE");
        break;
    }
  }
}

// ------------------------------------------------------------------------------------
// Program runner (a single ROT is just a one-step program)

void finishProgram(const char* msg) {
  phase = IDLE;
  progLen = 0;
  stopRequested = false;
  reply(msg);
}

void startStep() {
  while (progIdx < progLen) {
    const Step& st = prog[progIdx];
    if (st.kind == STEP_HOLD || st.kind == STEP_RELEASE) {
      setMotorEnabled(st.kind == STEP_HOLD);
      progIdx++;
      continue;
    }
    if (st.kind == STEP_WAIT) {
      if (st.ms == 0) { progIdx++; continue; }
      waitStart = millis();
      waitMs = st.ms;
      phase = WAITING;
      return;
    }
    long steps = lroundf(st.deg * STEPS_PER_REV / 360.0f);
    if (steps == 0) { progIdx++; continue; }
    if (!motorEnabled) {   // a rotation always runs energised, even after a RELEASE step
      setMotorEnabled(true);
      delay(5);
    }
    stepper.setMaxSpeed(rpmToStepsPerSec(st.rpm));
    stepper.setAcceleration(ACCEL_REV_S2 * STEPS_PER_REV);
    stepper.move(steps);
    phase = MOVING;
    return;
  }
  finishProgram("OK");
}

void startProgram() {
  if (!ensureDriver()) { progLen = 0; replyErr("DRIVER"); return; }
  progIdx = 0;
  stopRequested = false;
  startStep();
}

void serviceProgram(bool moving) {
  if (phase == MOVING && !moving) {
    if (stopRequested) { finishProgram("ERR STOPPED"); return; }
    progIdx++;
    startStep();
  } else if (phase == WAITING && millis() - waitStart >= waitMs) {
    progIdx++;
    startStep();
  }
}

// ------------------------------------------------------------------------------------
// Commands

void cmdStop() {
  if (phase == IDLE)    { reply("OK"); return; }
  if (phase == WAITING) { finishProgram("ERR STOPPED"); return; }
  stopRequested = true;   // decelerate; serviceProgram() sends "ERR STOPPED"
  stepper.stop();
}

void cmdStatus() {
  if (phase == IDLE) ensureDriver();   // live check; skipped while moving to keep steps smooth
  char buf[128];
  snprintf(buf, sizeof(buf), "OK EN=%d BUSY=%d STEP=%d/%d POS=%.2f DRV=0x%02X CUR=%u UP=%lu URX=%u",
           motorEnabled ? 1 : 0, phase != IDLE ? 1 : 0, progLen ? progIdx + 1 : 0, progLen,
           positionDeg(), driverVersion, (unsigned)driverCurrentMa, (unsigned long)(millis() / 1000), (unsigned)uartRecoveries);
  reply(buf);
}

// TMC2209 UART CRC-8 (polynomial 0x07, bits LSB first), from the datasheet.
uint8_t tmcCrc(const uint8_t* data, int len) {
  uint8_t crc = 0;
  for (int i = 0; i < len; ++i) {
    uint8_t b = data[i];
    for (int j = 0; j < 8; ++j) {
      crc = ((crc >> 7) ^ (b & 0x01)) ? (crc << 1) ^ 0x07 : (crc << 1);
      b >>= 1;
    }
  }
  return crc;
}

// Raw read of IOIN (reg 0x06) at every address, bypassing TMCStepper, to see what is on the wire.
void cmdDiag() {
  char buf[128];
  size_t pos = snprintf(buf, sizeof(buf), "OK");
  for (uint8_t addr = 0; addr < 4; ++addr) {
    while (DriverSerial.available()) DriverSerial.read();
    uint8_t req[4] = {0x05, addr, 0x06, 0};
    req[3] = tmcCrc(req, 3);
    DriverSerial.write(req, sizeof(req));
    DriverSerial.flush();

    uint8_t rx[16];
    int n = 0;
    uint32_t t0 = millis();
    while (millis() - t0 < 20 && n < (int)sizeof(rx)) {
      if (DriverSerial.available()) rx[n++] = DriverSerial.read();
    }
    // reply = sync, 0xFF, reg, 4 data bytes (MSB first), crc; the version is the top byte
    uint8_t ver = n >= 12 ? rx[7] : 0;
    pos += snprintf(buf + pos, sizeof(buf) - pos, " A%u=%d/0x%02X", addr, n, ver);
  }
  // What the driver itself reports: pin levels it sees (IOIN bit0 = ENN, bit7 = STEP, bit9 = DIR),
  // latched errors (GSTAT: 1 reset, 2 drv_err, 4 uv_cp) and DRV_STATUS (overtemp / short / open load).
  if (driver.version() == 0x21) {
    pos += snprintf(buf + pos, sizeof(buf) - pos, " IOIN=0x%08lX GSTAT=0x%02X DRV_STATUS=0x%08lX",
                    (unsigned long)driver.IOIN(), (unsigned)driver.GSTAT(),
                    (unsigned long)driver.DRV_STATUS());
  }
  reply(buf);
}

void cmdInfo() {
  char buf[160];
  snprintf(buf, sizeof(buf),
           "OK SLOTS=%d MAX_STEPS=%d MIN_RPM=%g MAX_RPM=%g MAX_DEG=%g MAX_WAIT_MS=%lu ACCEL=%g",
           NUM_SLOTS, MAX_STEPS, MIN_RPM, MAX_RPM, MAX_DEG, (unsigned long)MAX_WAIT_MS, ACCEL_REV_S2);
  reply(buf);
}

void cmdRotate(const char* args) {
  // reuse the step parser, which expects "ROT <deg> <rpm>"
  static char stepText[64];
  snprintf(stepText, sizeof(stepText), "ROT %s", args ? args : "");
  const char* err = parseStep(stepText, prog[0]);
  if (err) { replyErr(err); return; }
  progLen = 1;
  startProgram();
}

void cmdList() {
  static char buf[CMD_LINE_MAX];
  size_t pos = snprintf(buf, sizeof(buf), "OK");
  bool first = true;
  char key[8];
  for (int slot = 1; slot <= NUM_SLOTS; ++slot) {
    slotKey(slot, key);
    if (!store.isKey(key)) continue;
    String text = store.getString(key, "");
    int bar = text.indexOf('|');
    String name = bar >= 0 ? text.substring(0, bar) : text;
    pos += snprintf(buf + pos, sizeof(buf) - pos, "%s%d=%s", first ? " " : ",", slot, name.c_str());
    first = false;
  }
  reply(buf);
}

void cmdGet(char* args) {
  int slot = parseSlot(args);
  if (!slot) { replyErr("BAD_SLOT"); return; }
  char key[8];
  slotKey(slot, key);
  if (!store.isKey(key)) { replyErr("EMPTY_SLOT"); return; }
  String text = store.getString(key, "");
  Serial.print("OK ");
  Serial.println(text);
}

void cmdSet(char* args) {
  if (!args) { replyErr("BAD_SLOT"); return; }
  char* save;
  char* sSlot = strtok_r(args, " ", &save);
  char* body  = strtok_r(nullptr, "", &save);
  int slot = parseSlot(sSlot);
  if (!slot) { replyErr("BAD_SLOT"); return; }
  if (!body) { replyErr("NO_STEPS"); return; }

  static Step steps[MAX_STEPS];
  static char canon[CMD_LINE_MAX];
  char name[MAX_NAME + 1];
  int n;
  const char* err = parseProgram(body, name, steps, n);
  if (err) { replyErr(err); return; }

  formatProgram(name, steps, n, canon, sizeof(canon));
  char key[8];
  slotKey(slot, key);
  if (store.putString(key, canon) == 0) { replyErr("FLASH"); return; }
  reply("OK");
}

void cmdDelete(char* args) {
  int slot = parseSlot(args);
  if (!slot) { replyErr("BAD_SLOT"); return; }
  char key[8];
  slotKey(slot, key);
  if (store.isKey(key)) store.remove(key);
  reply("OK");
}

void cmdRun(char* args) {
  int slot = parseSlot(args);
  if (!slot) { replyErr("BAD_SLOT"); return; }
  char key[8];
  slotKey(slot, key);
  if (!store.isKey(key)) { replyErr("EMPTY_SLOT"); return; }

  static char text[CMD_LINE_MAX];
  store.getString(key, text, sizeof(text));
  char name[MAX_NAME + 1];
  const char* err = parseProgram(text, name, prog, progLen);
  if (err) { progLen = 0; replyErr(err); return; }
  startProgram();
}

void handleLine(char* line) {
  char* save;
  char* cmd  = strtok_r(line, " ", &save);
  char* rest = strtok_r(nullptr, "", &save);
  if (!cmd) return;
  toUpper(cmd);

  if      (!strcmp(cmd, "PING"))   reply("OK PONG");
  else if (!strcmp(cmd, "STATUS")) cmdStatus();
  else if (!strcmp(cmd, "INFO"))   cmdInfo();
  else if (!strcmp(cmd, "DIAG") && phase == IDLE) cmdDiag();
  else if (!strcmp(cmd, "STOP"))   cmdStop();
  else if (phase != IDLE)          replyErr("BUSY");
  else if (!strcmp(cmd, "ROT"))    cmdRotate(rest);
  else if (!strcmp(cmd, "RUN"))    cmdRun(rest);
  else if (!strcmp(cmd, "PLIST"))  cmdList();
  else if (!strcmp(cmd, "PGET"))   cmdGet(rest);
  else if (!strcmp(cmd, "PSET"))   cmdSet(rest);
  else if (!strcmp(cmd, "PDEL"))   cmdDelete(rest);
  else if (!strcmp(cmd, "EN")) {
    if (!ensureDriver()) { replyErr("DRIVER"); return; }
    setMotorEnabled(true);
    reply("OK");
  }
  else if (!strcmp(cmd, "DIS"))    { setMotorEnabled(false); reply("OK"); }
  else if (!strcmp(cmd, "ZERO"))   { stepper.setCurrentPosition(0); reply("OK"); }
  else                             replyErr("UNKNOWN_CMD");
}

void pollSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = '\0';
      if (lineOverflow)  replyErr("LINE_TOO_LONG");
      else if (lineLen)  handleLine(lineBuf);
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineOverflow = true;
    }
  }
}

// ------------------------------------------------------------------------------------

void setup() {
  // Keep the motor OFF before anything else (the pull-up already does this in hardware)
  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);

  Serial.setRxBufferSize(CMD_LINE_MAX);   // a PSET line can be longer than the default 256 bytes
  Serial.begin(115200);
  store.begin("progs", false);

  stepper.setPinsInverted(INVERT_DIR, false, false);
  stepper.setMinPulseWidth(2);

  startDriverSerial();
  driver.begin();
  bool ok = ensureDriver();   // "NOT FOUND" is normal if the 24V is not on yet
  // Informational only; the PC ignores lines that aren't OK/ERR replies.
  Serial.printf("# PetriPlatter ready, driver %s (0x%02X)\n", ok ? "OK" : "NOT FOUND (24V off?)", driverVersion);
}

void loop() {
  pollSerial();

  // run() returns true while steps remain; call it as often as possible
  bool moving = stepper.run();
  serviceProgram(moving);
}
