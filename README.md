# UREVO Local for Home Assistant

[![CI](https://github.com/niemyjski/homeassistant-urevo/actions/workflows/ci.yml/badge.svg)](https://github.com/niemyjski/homeassistant-urevo/actions/workflows/ci.yml)

Experimental local Bluetooth integration for UREVO walking pads advertising
`URTM041` and exposing the Bluetooth Fitness Machine Service (FTMS). Uses Home
Assistant Bluetooth adapters or connectable ESPHome Bluetooth proxies. No cloud
account, phone application, MQTT broker, or additional bridge is required.

**Physical workout compatibility is unverified.** Automated tests exercise
synthetic packets, simulated Bluetooth transport, and real Home Assistant APIs.
They do not establish that telemetry or motor controls work on a physical pad.
Other UREVO models are not supported. This project is not affiliated with UREVO.

## What it exposes

| Entity | Meaning | Default |
| --- | --- | --- |
| Speed | Reported belt speed, km/h | Enabled |
| Session distance | Reported workout distance, meters | Enabled |
| Session time | Reported elapsed workout time, seconds | Enabled |
| Session calories | Reported workout energy, kcal | Enabled |
| Start, Stop, Pause | Manual FTMS commands | Disabled |
| Target speed | Explicit speed command; no stored target is reported | Disabled |
| Arm next control | One-action authorization for Start or speed changes | Disabled |

Each telemetry field becomes unavailable after 30 seconds without its own update
or on disconnect. Missing values are never replaced with zero. Session totals do
not contribute to long-term statistics until device reset semantics are verified.
There is no step counter, historical workout import, or UREVO app synchronization.

## Installation

Requires Home Assistant **2026.10.4 or newer**; 2026.10.4 is the tested API baseline.
Newer versions have not necessarily been tested. Enable the Bluetooth integration
and ensure an adapter or proxy can make active Bluetooth connections.

### HACS custom repository

Add `https://github.com/niemyjski/homeassistant-urevo` as an **Integration** in
HACS custom repositories, then download **UREVO Local**. This project is not in
the default HACS catalog. Without releases, HACS uses the default branch.

### Manual installation

Copy the entire `custom_components/urevo_local` directory, including translations,
into your Home Assistant `custom_components` directory. Back up any existing copy
before replacing it. Alternatively, the optional
[receipt-based installer](docs/installation.md) supports dry runs and verified upgrades.
Choose one installation method; do not combine HACS management with installer upgrades.

After installation, restart Home Assistant when convenient, then confirm Bluetooth
discovery or select **Settings → Devices & services → Add integration → UREVO Local**.
Power on the pad without starting its belt and close the phone app if discovery or
connection fails. Setup subscribes to telemetry and never writes motor commands.

## Controls and safety

Leave controls disabled until telemetry has been compared with the physical console.
To opt in, enable **Allow manual controls** in integration options, then explicitly
enable the desired control entities and **Arm next control** in their entity settings.

- Start and speed changes require fresh speed telemetry and a new arm. Arming expires
  after 60 seconds, one accepted action, a disconnect, or a relevant machine-status change.
- Start requires a reported stationary belt. **Start may resume the pad's stored speed;
  the configured speed-change cap cannot constrain that starting speed.**
- Speed changes require a running belt and a device-reported speed range/increment.
  The default commanded-speed cap is **1.6 km/h**, configurable from 0.5 to 6.4 km/h.
- Stop and Pause do not require arming or fresh telemetry, but do require enabled
  controls and a working connection. They are **not emergency stops**.
- Motor commands are never retried or queued. A timeout may mean a command was applied
  without acknowledgment; check the physical pad and remote before doing anything else.

Remain beside the pad with its physical remote and safety mechanisms accessible.
Do not automate Start or speed changes, operate it unattended, or rely on Bluetooth
for emergency stopping. See the [hardware validation checklist](docs/validation.md)
for the outstanding acceptance work.

## Troubleshooting and removal

Unavailable sensors can mean a missing optional field, stale packets, another app
holding the connection, or an out-of-range proxy. Keep the phone app disconnected,
check Home Assistant Bluetooth diagnostics, and verify the model advertises `URTM041`.
Only a fresh measurement makes a sensor available; discovery alone proves nothing.

To remove, delete the integration entry in Devices & services, uninstall it through
your chosen installation method, and restart when convenient. No automations or
dashboards are installed. For rollback, restore your component backup and restart;
receipt-based upgrades preserve the previous files and receipt.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for isolated setup, tests, and change guidelines,
[SECURITY.md](SECURITY.md) for reporting and trust boundaries, and
[CHANGELOG.md](CHANGELOG.md) for changes. Licensed under [MIT](LICENSE).
