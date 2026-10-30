# URTM041 extended FTMS telemetry

## Device-reported steps

The app uses notifications on `fff1` and requests the stream by writing
`02 51 0b 03` to `fff2`. This is a telemetry subscription, not an FTMS motor
command. Subscribe before requesting; request again after 30 seconds without
step telemetry because a device reset can stop the proprietary stream.
Missing optional characteristics or a failed request leave steps unavailable
without disabling FTMS readings and controls.

### Reporting modes on the US URTM041

Activating the proprietary stream can stop FTMS notifications. FTMS control can
switch it back. Do not assume both channels continue streaming concurrently.
The US range `600083022000` identifies the verified imperial profile. Its full
proprietary frames also provide speed (word at 3–4, tenths of mph), distance
(7–8, hundredths of a mile), calories (9–10, tenths of kcal), and elapsed seconds.
These refresh the existing session sensors alongside steps. Other ranges retain
step-only decoding until their units are verified; HA display units never select
the wire conversion.

For continuity with existing FTMS accounting, convert with exact integer
arithmetic and truncate speed to hundredths of km/h, distance to tens of meters,
and calories to whole kcal. An empty-belt paused capture
`02510a0000b30107007e0000000003b80b0603` agrees with FTMS
`842500006e00000c0000000000b301000000`: 435 seconds, 110 meters, 12 kcal,
zero speed and zero steps. This verifies cross-channel units and stationary
telemetry, not physical step accuracy. Short status frames never synthesize speed.

[Walker's iOS packet-capture findings](https://github.com/apanloco/walker/blob/main/CLAUDE.md)
independently document mode switching. Existing FTMS commands retain their
acknowledgments and safety gates; proprietary motor commands are not introduced.
Integration diagnostics expose only the last valid packet for each channel,
measurement values and their ages, without device identifiers or credentials.

Published 19-byte frames begin `02 51` and end `03`. Session steps are the
little-endian word at offsets 11–12 and elapsed seconds at 5–6. For example,
`0251030e007c0003002c007e0000000000d703` reports 126 steps and 124 seconds;
`02510a00004a010b008200760100000000f603` retains 374 steps while paused.
Short control/status responses are rejected. Byte 17 remains opaque: neither
an invented checksum nor the unknown FTMS extension is used to infer steps.

Total steps restore their count and last session steps/seconds together.
Equal readings add zero. A lower steps or elapsed counter identifies a reset;
the first new-session reading is added even if its zero packet was missed.
Reconnecting to the same counter adds only its difference. A whole session
completed/reset offline cannot be recovered, and counters alone cannot identify
every unseen reset. Device 16-bit counter rollover is not yet hardware validated.
This uses the wire-layout observations linked below, not copied implementation.

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
