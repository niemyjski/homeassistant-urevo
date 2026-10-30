# URTM041 extended FTMS telemetry

The URTM041 can emit exactly 18 bytes with little-endian flags `0x2584`.
Its standard prefix contains speed (0.01 km/h), distance (meters), expended
energy, heart rate, and elapsed seconds. The final three vendor bytes are
accepted only for this exact profile and are not exposed or used for controls.

Evidence: [TreadSpan's URTM041/E1L capture and notes](https://github.com/blak3r/treadspan/blob/main/arduino/src/TreadmillDeviceUrevoProtocol.h)
and [protocol observations](https://github.com/blak3r/treadspan/blob/main/protocol-analysis/urevo-E1L/README.md).
The published nonzero frame `842501015e01001400000000008b01fa0000` contains
2.57 km/h, 350 m, 20 kcal, and 395 seconds. Its raw speed 257 agrees with the
reported 1.6 mph console setting after conversion. The regression fixture uses
this wire-format fact; no third-party implementation code is copied.

A physical idle pad was observed sending the same flags and length with zero
measurements. This establishes packet reception and decoding, not accuracy of
every workout field or acceptance of motor commands. Standard FTMS parsing
remains strict, and unknown extended layouts remain rejected. Missing or stale
data is never converted to a stopped belt.

## Control transport and speed range

TreadSpan's `urevo-with-kinomap.pcapng` capture shows ATT Write Commands
(`0x52`) on control handle `0x0027`, followed by FTMS notifications such as
`800001`, `800701`, and `800801`. A physical URTM041 rejected ATT Write Requests
with `Write not permitted` during Request Control. Select write-without-response
when the characteristic advertises it; never retry a failed write in another
mode. The FTMS acknowledgment remains mandatory before the next command.

The observed range bytes `600083022000` decode to 0.96–6.43 km/h in 0.32 km/h
increments. Range validation allows up to 6.5 km/h to accommodate this converted
imperial range; the configured speed-command cap (default 1.6 km/h, maximum
6.4 km/h) still limits every commanded target independently.
