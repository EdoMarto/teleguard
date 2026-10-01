"""Derive a user's Telegram datacenter from their profile-photo file_id.

The Bot API does not expose a user's datacenter directly, but the `dc_id` is
encoded inside the file_id of any file they own (such as a profile photo). The
file_id is a URL-safe base64 string, zero-run-length encoded; once decoded, the
second little-endian int32 is the datacenter id (1..5).

This is a weak signal — the datacenter only reflects where the account was
registered, not whether it is a bot — so use it as a low-weight hint, never as a
reason to ban on its own.
"""

from __future__ import annotations

import base64
import struct


def _b64_decode(value: str) -> bytes:
    value = value.replace("-", "+").replace("_", "/")
    value += "=" * (-len(value) % 4)
    return base64.b64decode(value)


def _rle_decode(data: bytes) -> bytes:
    """Expand Telegram's zero run-length encoding (a 0x00 byte, then a count)."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0 and i + 1 < len(data):
            out.extend(b"\x00" * data[i + 1])
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def datacenter_from_file_id(file_id: str) -> int | None:
    """Return the datacenter id (1..5) encoded in a file_id, or None if unknown."""
    try:
        decoded = _rle_decode(_b64_decode(file_id))
        if len(decoded) < 8:
            return None
        _file_type, dc_id = struct.unpack("<ii", decoded[:8])
        return dc_id if 1 <= dc_id <= 5 else None
    except Exception:
        return None
