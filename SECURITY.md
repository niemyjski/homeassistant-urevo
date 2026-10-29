# Security and physical safety

This experimental integration reads untrusted Bluetooth data and offers optional
motor controls. The latest default-branch revision is the supported development
version; no stable hardware-validated release is claimed.

## Report a vulnerability

Use GitHub's private **Report a vulnerability** option in this repository's Security
tab when available. If it is unavailable, open an issue requesting a private contact
channel without exploit details, device identifiers, or logs. Do not publish credentials,
full Home Assistant diagnostics, Bluetooth addresses, or unsafe reproduction procedures.
An acknowledgment or repair timeline is not guaranteed.

## Boundaries

- Setup reads FTMS capabilities and subscribes to notifications. It does not request
  control or start, stop, reset, or change the belt speed.
- Controls require both integration opt-in and explicit entity enablement. Start and
  speed changes also require one-use, expiring authorization and fresh speed data.
- Commands and connection setup have deadlines. A failed or cancelled command clears
  authorization and disconnects. Motor commands are not replayed after reconnect.
- Old-client callbacks cannot refresh telemetry or complete a new client's command.
  Malformed packets do not refresh timestamps. Each field expires independently.
- There are no cloud credentials, outbound HTTP uploads, shell commands, or firmware
  changes in the component. Home Assistant stores the selected Bluetooth address.
- Local Bluetooth names and addresses can be spoofed. These checks reduce accidental
  operation; they do not authenticate the physical treadmill or make it safety-rated.

Bluetooth Stop is not an emergency stop. Start can resume a stored speed outside the
configured speed-change cap. Physical workout accuracy, compatibility, and behavior
remain unverified; keep the remote accessible and do not operate unattended.
