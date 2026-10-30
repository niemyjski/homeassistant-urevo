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
