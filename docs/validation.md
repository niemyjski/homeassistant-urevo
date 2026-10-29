# Validation status

## Automated scope

Tests cover synthetic FTMS field ordering, malformed/truncated packets, bounded
speed commands, disabled controls, one-action/expired arms, fresh telemetry, competing
commands, rejection, cancellation, disconnects, stale callbacks, unload during setup,
option changes during Request Control, and conservative installation/rollback.
Real Home Assistant API tests run against 2026.10.4 without a Bluetooth connection.
CI results are available in the repository Actions tab.

## Physical acceptance remains outstanding

No physical workout, integration-to-pad Bluetooth session, or motor-control test is
claimed for this repository. Discovery of `URTM041` does not prove FTMS support or
measurement accuracy. Automated success must not be described as hardware validation.

An owner may perform a separately authorized, attended session with the physical
remote accessible. Begin with controls disabled:

- Confirm discovery, successful connection, and idle speed against the console.
- Compare each supported measurement during a workout started with the physical remote.
- Verify session resets, absent optional fields, stale-field unavailability, disconnect,
  power-cycle reconnection, and cleanup after entry unload.
- Only after telemetry is verified, decide separately whether to test opt-in controls.
  Verify stored-speed Start behavior before attempting it. Never assume the command
  cap constrains starting speed, and never test emergency stopping over Bluetooth.

Record model/firmware, software revision, observations, and failures with all identifiers
redacted. Do not attach raw home configuration, private receipts, or full BLE captures.
