import base64
import struct

from teleguard.antiflood import FloodTracker
from teleguard.fileid import datacenter_from_file_id
from teleguard.risk import Profile, RiskConfig, is_suspicious, score
from teleguard.spam import SpamConfig, is_spam


# -- risk ---------------------------------------------------------------------

def test_clean_profile_is_low_risk():
    p = Profile(1, "Marco", "Rossi", username="marco_rossi", has_photo=True)
    points, _ = score(p)
    assert points == 0
    assert not is_suspicious(p)


def test_spammy_profile_is_flagged():
    p = Profile(2, "FREE CRYPTO t.me/scam", username=None, has_photo=False)
    points, reasons = score(p)
    assert is_suspicious(p)
    assert "no profile photo" in reasons and "spam keyword in name" in reasons


def test_premium_reduces_score():
    base = Profile(3, "No Photo Guy", has_photo=False)
    premium = Profile(3, "No Photo Guy", has_photo=False, is_premium=True)
    assert score(premium)[0] < score(base)[0]


def test_suspicious_datacenter_adds_a_point():
    cfg = RiskConfig(suspicious_datacenters={5})
    p = Profile(4, "Tizio", username="tizio", has_photo=True, datacenter=5)
    assert "registered in DC5" in score(p, cfg)[1]


# -- spam ---------------------------------------------------------------------

def test_link_from_new_user_is_spam():
    spammy, _ = is_spam("guarda qui https://x.it", message_count=0)
    assert spammy


def test_link_from_trusted_user_is_allowed():
    spammy, _ = is_spam("guarda qui https://x.it", message_count=10)
    assert not spammy


def test_spam_phrase_always_blocked():
    spammy, reason = is_spam("earn money fast!", message_count=99)
    assert spammy and reason == "spam phrase"


# -- antiflood ----------------------------------------------------------------

def test_flood_tracker_trips_over_the_limit():
    f = FloodTracker(max_messages=3, per_seconds=5)
    assert [f.is_flooding(1, t) for t in (0, 0.1, 0.2, 0.3)] == [False, False, False, True]


def test_flood_tracker_forgets_old_messages():
    f = FloodTracker(max_messages=2, per_seconds=5)
    f.is_flooding(1, 0.0)
    f.is_flooding(1, 0.1)
    assert f.is_flooding(1, 100.0) is False  # window moved on


# -- fileid -------------------------------------------------------------------

def _rle_encode(data: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for b in data:
        if b == 0:
            zeros += 1
            continue
        if zeros:
            out += bytes([0, zeros])
            zeros = 0
        out.append(b)
    if zeros:
        out += bytes([0, zeros])
    return bytes(out)


def test_datacenter_round_trip():
    # Craft a payload shaped like a real file_id: (file_type, dc_id, ...).
    payload = struct.pack("<ii", 2, 4) + b"\x00\x00\x00rest"
    file_id = base64.urlsafe_b64encode(_rle_encode(payload)).decode().rstrip("=")
    assert datacenter_from_file_id(file_id) == 4


def test_datacenter_handles_garbage():
    assert datacenter_from_file_id("not-a-real-file-id") is None
