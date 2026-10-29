# Changelog

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
