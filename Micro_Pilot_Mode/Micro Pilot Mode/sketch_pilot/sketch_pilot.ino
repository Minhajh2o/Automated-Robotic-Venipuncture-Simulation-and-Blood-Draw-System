/*
  ============================================================
  VENIPUNCTURE ROBOT - 3 AXIS STEPPER CONTROLLER
  ============================================================
  Hardware: Arduino UNO, CNC Shield V3, 3x DRV8825, NEMA 17HS8401
  Microstepping: 1/8 (Set via jumpers on CNC shield)
  Mechanics: 8mm rod, 1.25mm pitch (lead)
  ============================================================
*/

const uint8_t MICROSTEPS = 8;
const uint16_t FULL_STEPS_PER_REV = 200;
const float SCREW_LEAD_MM = 1.25;

const uint32_t MICROSTEPS_PER_REV = (uint32_t)FULL_STEPS_PER_REV * MICROSTEPS;
const float MICROSTEPS_PER_MM = (float)MICROSTEPS_PER_REV / SCREW_LEAD_MM;

// PIN DEFINITIONS (CNC Shield V3)
const uint8_t X_STEP_PIN = 2;
const uint8_t X_DIR_PIN  = 5;
const uint8_t Y_STEP_PIN = 3;
const uint8_t Y_DIR_PIN  = 6;
const uint8_t Z_STEP_PIN = 4;
const uint8_t Z_DIR_PIN  = 7;
const uint8_t ENABLE_PIN = 8;

const uint8_t STEP_PIN[3] = { X_STEP_PIN, Y_STEP_PIN, Z_STEP_PIN };
const uint8_t DIR_PIN[3] = { X_DIR_PIN, Y_DIR_PIN, Z_DIR_PIN };

// ============================================================
// INCREASED SPEED LIMITS
// ============================================================
uint16_t MAX_SPEED[3] = {
  24000,   // X - Doubled from 12000
  24000,   // Y - Doubled from 12000
  5000     // Z - Doubled from 2500
};

const uint16_t XY_MAX_SPEED = 24000;
const uint16_t Z_MAX_SPEED  = 5000;
const uint16_t MIN_SPEED = 5;

// ============================================================
// STEP TIMING (LOWERED TO ALLOW FASTER PULSES)
// ============================================================
const uint16_t MIN_INTERVAL_US = 20; // Reduced from 83 to allow faster top speeds
const uint8_t STEP_HIGH_US = 3;

const unsigned long COMMAND_TIMEOUT_MS = 250;
const long Z_LIMIT_MICROSTEPS = 200000;

long positionSteps[3] = { 0, 0, 0 };
int8_t direction[3] = { 0, 0, 0 };
unsigned long nextStepUs[3] = { 0, 0, 0 };

unsigned long lastCommandMs = 0;
bool stopLatched = true;
bool driverEnabled = false;

char rxBuffer[64];
uint8_t rxLength = 0;

void stopMotion() {
  direction[0] = 0;
  direction[1] = 0;
  direction[2] = 0;
}

void enableDrivers() {
  digitalWrite(ENABLE_PIN, LOW);
  driverEnabled = true;
}

void disableDrivers() {
  digitalWrite(ENABLE_PIN, HIGH);
  driverEnabled = false;
}

void emergencyStop() {
  stopMotion();
  stopLatched = true;
  disableDrivers();
  Serial.println(F("STOPPED"));
}

void printStatus() {
  Serial.print(F("POS,"));
  Serial.print(positionSteps[0]);
  Serial.print(',');
  Serial.print(positionSteps[1]);
  Serial.print(',');
  Serial.println(positionSteps[2]);
}

void printConfig() {
  Serial.println(F("CONFIG"));
  Serial.print(F("MICROSTEPPING,1/")); Serial.println(MICROSTEPS);
  Serial.print(F("FULL_STEPS_REV,")); Serial.println(FULL_STEPS_PER_REV);
  Serial.print(F("MICROSTEPS_REV,")); Serial.println(MICROSTEPS_PER_REV);
  Serial.print(F("SCREW_LEAD_MM,")); Serial.println(SCREW_LEAD_MM, 4);
  Serial.print(F("MICROSTEPS_MM,")); Serial.println(MICROSTEPS_PER_MM, 2);
  Serial.print(F("X_SPEED,")); Serial.println(MAX_SPEED[0]);
  Serial.print(F("Y_SPEED,")); Serial.println(MAX_SPEED[1]);
  Serial.print(F("Z_SPEED,")); Serial.println(MAX_SPEED[2]);
  Serial.print(F("Z_LIMIT_MICROSTEPS,")); Serial.println(Z_LIMIT_MICROSTEPS);
}

bool parseDirection(const char *text, int8_t &value) {
  if (strcmp(text, "1") == 0) { value = 1; return true; }
  if (strcmp(text, "0") == 0) { value = 0; return true; }
  if (strcmp(text, "-1") == 0) { value = -1; return true; }
  return false;
}

void processLine(char *line) {
  if (strcmp(line, "STOP") == 0) {
    emergencyStop();
    return;
  }
  if (strcmp(line, "RESET") == 0) {
    stopMotion();
    stopLatched = false;
    lastCommandMs = millis();
    enableDrivers();
    Serial.println(F("RESET_OK"));
    return;
  }
  if (strcmp(line, "STATUS") == 0) {
    printStatus();
    return;
  }
  if (strcmp(line, "CONFIG") == 0) {
    printConfig();
    return;
  }

  if (strncmp(line, "S,", 2) == 0) {
    char *savePtr;
    char *token = strtok_r(line + 2, ",", &savePtr);
    uint16_t requested[3];
    uint8_t count = 0;

    while (token != NULL && count < 3) {
      char *endPtr;
      long value = strtol(token, &endPtr, 10);
      if (*token == '\0' || *endPtr != '\0') {
        Serial.println(F("ERR,SPEED"));
        return;
      }
      if (count < 2) {
        if (value < MIN_SPEED || value > XY_MAX_SPEED) {
          Serial.println(F("ERR,XY_SPEED"));
          return;
        }
      } else {
        if (value < MIN_SPEED || value > Z_MAX_SPEED) {
          Serial.println(F("ERR,Z_SPEED"));
          return;
        }
      }
      requested[count] = (uint16_t)value;
      count++;
      token = strtok_r(NULL, ",", &savePtr);
    }
    if (count != 3 || token != NULL) {
      Serial.println(F("ERR,SPEED_FORMAT"));
      return;
    }
    for (uint8_t axis = 0; axis < 3; axis++) {
      MAX_SPEED[axis] = requested[axis];
    }
    Serial.println(F("SPEED_OK"));
    return;
  }

  if (strncmp(line, "M,", 2) == 0) {
    char *savePtr;
    char *token = strtok_r(line + 2, ",", &savePtr);
    int8_t requested[3];
    uint8_t count = 0;

    while (token != NULL && count < 3) {
      if (!parseDirection(token, requested[count])) {
        Serial.println(F("ERR,DIRECTION"));
        return;
      }
      count++;
      token = strtok_r(NULL, ",", &savePtr);
    }
    if (count != 3 || token != NULL) {
      Serial.println(F("ERR,MOTION_FORMAT"));
      return;
    }
    lastCommandMs = millis();

    if (stopLatched) {
      stopMotion();
      return;
    }
    if (!driverEnabled) {
      enableDrivers();
    }
    if (requested[2] > 0 && positionSteps[2] >= Z_LIMIT_MICROSTEPS) {
      requested[2] = 0;
    }
    if (requested[2] < 0 && positionSteps[2] <= -Z_LIMIT_MICROSTEPS) {
      requested[2] = 0;
    }

    for (uint8_t axis = 0; axis < 3; axis++) {
      if (requested[axis] != direction[axis]) {
        direction[axis] = requested[axis];
        nextStepUs[axis] = micros();
      }
    }
    return;
  }
  Serial.println(F("ERR,UNKNOWN_COMMAND"));
}

void readSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuffer[rxLength] = '\0';
      if (rxLength > 0) processLine(rxBuffer);
      rxLength = 0;
    } else {
      if (rxLength < sizeof(rxBuffer) - 1) {
        rxBuffer[rxLength++] = c;
      } else {
        rxLength = 0;
        emergencyStop();
        Serial.println(F("ERR,LINE_TOO_LONG"));
      }
    }
  }
}

void updateAxis(uint8_t axis, unsigned long nowUs) {
  if (direction[axis] == 0 || stopLatched) return;

  if (axis == 2) {
    if (direction[axis] > 0 && positionSteps[axis] >= Z_LIMIT_MICROSTEPS) {
      direction[axis] = 0;
      return;
    }
    if (direction[axis] < 0 && positionSteps[axis] <= -Z_LIMIT_MICROSTEPS) {
      direction[axis] = 0;
      return;
    }
  }

  uint16_t speed = MAX_SPEED[axis];
  unsigned long interval = 1000000UL / speed;
  if (interval < MIN_INTERVAL_US) interval = MIN_INTERVAL_US;

  if ((long)(nowUs - nextStepUs[axis]) >= 0) {
    digitalWrite(DIR_PIN[axis], direction[axis] > 0 ? HIGH : LOW);
    digitalWrite(STEP_PIN[axis], HIGH);
    delayMicroseconds(STEP_HIGH_US);
    digitalWrite(STEP_PIN[axis], LOW);
    
    positionSteps[axis] += direction[axis];
    nextStepUs[axis] = nowUs + interval;
  }
}

void setup() {
  for (uint8_t axis = 0; axis < 3; axis++) {
    pinMode(STEP_PIN[axis], OUTPUT);
    pinMode(DIR_PIN[axis], OUTPUT);
    digitalWrite(STEP_PIN[axis], LOW);
    digitalWrite(DIR_PIN[axis], LOW);
  }
  pinMode(ENABLE_PIN, OUTPUT);
  disableDrivers();

  Serial.begin(115200);
  Serial.setTimeout(10);
  lastCommandMs = millis();

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("VENIPUNCTURE CONTROLLER - 1/8 MICROSTEP"));
  Serial.println(F("=============================="));
  Serial.println(F("READY"));
}

void loop() {
  readSerial();

  if (!stopLatched && millis() - lastCommandMs > COMMAND_TIMEOUT_MS) {
    stopMotion();
    disableDrivers();
  }

  if (!stopLatched && driverEnabled) {
    unsigned long nowUs = micros();
    updateAxis(0, nowUs);
    updateAxis(1, nowUs);
    updateAxis(2, nowUs);
  }
}