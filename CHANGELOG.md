# Changelog

## 0.1.4 — 2026-10-30

- Add debug-only FTMS capability, acknowledgment, and command-failure logging
  to distinguish protocol rejection from transport failure during attended tests.
  Command behavior and safety checks are unchanged.

## 0.1.3 — 2026-10-30

- Decode the URTM041's captured 18-byte `0x2584` telemetry profile instead of
  discarding it as an unsupported FTMS extension. Retain strict length and flag
  validation; leave the three vendor bytes uninterpreted.
- Preserve all motor-control safety checks and disabled-by-default controls.

## 0.1.2 — Unreleased

- Package the experimental UREVO Local integration as a standalone HACS custom repository.
- Use generic device titles, synthetic test addresses, and English translations.
- Add CI, contribution/security guidance, MIT licensing, and installation documentation.
- Keep unverified session totals out of long-term statistics.
- Validate submitted options and recheck control permission and speed limits after
  Request Control completes.

## 0.1.1 — Development baseline

- FTMS telemetry and opt-in, explicitly armed manual controls.
- Per-field expiry, connection/cancellation cleanup, stale-client rejection, bounded
  speed commands, and receipt-based upgrades with rollback on failed directory swap.

These versions do not establish physical workout or motor-control compatibility.
