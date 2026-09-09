"""Extract the plain text out of a `message.attributedBody` blob.

Since macOS Ventura most rows have `text = NULL`; the string lives inside a legacy
NSArchiver "typedstream" of an NSAttributedString. We don't parse the whole
stream — we locate the NSString class marker, skip to the `+` byte that precedes
the length, decode the typedstream integer, and read that many UTF-8 bytes.
"""
from __future__ import annotations


def decode_attributed_body(blob: bytes | None) -> str | None:
    if not blob:
        return None
    i = blob.find(b"NSString")
    if i == -1:
        return None
    p = i + len("NSString")
    j = blob.find(b"+", p, p + 24)
    if j == -1:
        return None
    p = j + 1
    if p >= len(blob):
        return None
    b0 = blob[p]
    if b0 == 0x81:
        n = int.from_bytes(blob[p + 1:p + 3], "little")
        p += 3
    elif b0 == 0x82:
        n = int.from_bytes(blob[p + 1:p + 5], "little")
        p += 5
    else:
        n = b0
        p += 1
    return blob[p:p + n].decode("utf-8", errors="replace")
