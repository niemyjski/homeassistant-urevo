"""Bluetooth SIG FTMS treadmill data and bounded speed commands."""

import math
import struct

BASE = "-0000-1000-8000-00805f9b34fb"
DATA = "00002acd" + BASE
FEATURE = "00002acc" + BASE
SPEED_RANGE = "00002ad4" + BASE
CONTROL = "00002ad9" + BASE
STATUS = "00002ada" + BASE


def decode_treadmill(data: bytes) -> dict[str, float]:
    """Reject malformed frames; optional fields retain their SIG wire order."""
    if len(data) < 2:
        raise ValueError("Missing FTMS flags")
    flags = int.from_bytes(data[:2], "little")
    if flags & 0xE000:
        raise ValueError("Unsupported FTMS flags")
    offset = 2
    result = {}

    def read(size: int, signed: bool = False) -> int:
        nonlocal offset
        if offset + size > len(data):
            raise ValueError("Truncated FTMS frame")
        value = int.from_bytes(data[offset : offset + size], "little", signed=signed)
        offset += size
        return value

    if not flags & 1:
        result["speed"] = read(2) / 100
    fields = (
        (1, (("average_speed", 2, 100, False),)),
        (2, (("distance", 3, 1, False),)),
        (3, (("inclination", 2, 10, True), ("ramp_angle", 2, 10, True))),
        (4, (("elevation_gain", 2, 10, False), ("elevation_loss", 2, 10, False))),
        (5, (("pace", 1, 10, False),)),
        (6, (("average_pace", 1, 10, False),)),
        (
            7,
            (
                ("calories", 2, 1, False),
                ("calories_per_hour", 2, 1, False),
                ("calories_per_minute", 1, 1, False),
            ),
        ),
        (8, (("heart_rate", 1, 1, False),)),
        (9, (("metabolic_equivalent", 1, 10, False),)),
        (10, (("elapsed", 2, 1, False),)),
        (11, (("remaining", 2, 1, False),)),
        (12, (("force", 2, 1, True), ("power", 2, 1, True))),
    )
    for bit, group in fields:
        if flags & (1 << bit):
            for name, size, divisor, signed in group:
                result[name] = read(size, signed) / divisor
    if offset != len(data):
        raise ValueError("Unexpected trailing FTMS data")
    return result


def decode_urtm041(data: bytes) -> dict[str, float]:
    """Decode standard FTMS or the captured URTM041 18-byte telemetry profile.

    This model adds bit 13 and three trailing vendor bytes to the standard
    speed/distance/energy/heart-rate/elapsed layout. Their meaning is not
    established, so they are deliberately not exposed as measurements.
    """
    if data[:2] == b"\x84\x25":
        if len(data) != 18:
            raise ValueError("Invalid URTM041 extended frame length")
        return decode_treadmill(b"\x84\x05" + data[2:15])
    return decode_treadmill(data)


def speed_command(
    speed: float, limits: tuple[float, float, float], cap: float
) -> bytes:
    minimum, maximum, step = limits
    if any(
        isinstance(value, bool) or not math.isfinite(value)
        for value in (speed, minimum, maximum, step, cap)
    ):
        raise ValueError("Speed and limits must be finite numbers")
    if not 0 <= minimum < maximum <= 6.5 or step <= 0 or step > maximum - minimum:
        raise ValueError("Invalid treadmill speed range")
    if not math.isfinite(speed) or not minimum <= speed <= min(maximum, cap):
        raise ValueError("Speed outside configured walking limit")
    if abs((speed - minimum) / step - round((speed - minimum) / step)) > 0.001:
        raise ValueError("Speed does not match treadmill increments")
    return b"\x02" + struct.pack("<H", round(speed * 100))
