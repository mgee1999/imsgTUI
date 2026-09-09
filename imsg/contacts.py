"""Contact resolution: phone/email -> display name + square photo.

Reads every AddressBook sqlite under ~/Library/Application Support/AddressBook
(read-only, Full Disk Access required — same permission chat.db needs).
Photos come from ZTHUMBNAILIMAGEDATA / ZIMAGEDATA; those blobs carry a one-byte
prefix: 0x01 + JPEG/PNG bytes, or 0x02 + a UUID reference (no local bytes → skipped).
"""
from __future__ import annotations

import glob
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field

AB_MAIN = "~/Library/Application Support/AddressBook/AddressBook-v22.abcddb"
AB_GLOB = "~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb"


@dataclass
class Person:
    name: str
    first: str = ""
    last: str = ""
    org: str = ""
    photo: bytes | None = None
    handles: list[str] = field(default_factory=list)

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first, self.last) if p]
        if parts:
            return "".join(p[0] for p in parts[:2]).upper()
        return (self.name[:2] if self.name else "?").upper()


def norm_handle(h: str) -> str:
    """Normalize a phone/email so chat.db handles and AddressBook entries meet."""
    h = (h or "").strip().lower()
    if not h:
        return ""
    if "@" in h:
        return h
    d = re.sub(r"\D", "", h)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d[-10:] if len(d) >= 10 else d


def _strip_prefix(b: bytes | None) -> bytes | None:
    if not b or len(b) < 8:
        return None
    if b[0] == 0x01:
        return b[1:]
    if b[:2] in (b"\xff\xd8", b"\x89P"):
        return b
    return None  # 0x02 = external reference, nothing local to show


class Contacts:
    def __init__(self) -> None:
        self._by_handle: dict[str, Person] = {}
        self._loaded_at = 0.0
        self._sig: tuple = ()
        self.last_error: str | None = None
        self.load()

    # ------------------------------------------------------------------ public
    def lookup(self, handle: str) -> Person | None:
        if not handle:
            return None
        self._maybe_reload()
        return self._by_handle.get(norm_handle(handle))

    def name(self, handle: str) -> str | None:
        p = self.lookup(handle)
        return p.name if p else None

    def photo(self, handle: str) -> bytes | None:
        p = self.lookup(handle)
        return p.photo if p else None

    def __len__(self) -> int:
        return len(self._by_handle)

    # ---------------------------------------------------------------- loading
    def _paths(self) -> list[str]:
        paths = glob.glob(os.path.expanduser(AB_GLOB))
        main = os.path.expanduser(AB_MAIN)
        if os.path.exists(main):
            paths.append(main)
        return paths

    def _maybe_reload(self) -> None:
        if time.time() - self._loaded_at < 300:
            return
        sig = tuple(int(os.stat(p).st_mtime) for p in self._paths() if os.path.exists(p))
        if sig != self._sig:
            self.load()
        else:
            self._loaded_at = time.time()

    def load(self) -> None:
        self._loaded_at = time.time()
        by_handle: dict[str, Person] = {}
        sig = []
        for db in self._paths():
            try:
                sig.append(int(os.stat(db).st_mtime))
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
                con.row_factory = sqlite3.Row
                people: dict[int, Person] = {}
                for r in con.execute(
                    "SELECT Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION, ZNICKNAME, "
                    "ZTHUMBNAILIMAGEDATA, ZIMAGEDATA FROM ZABCDRECORD"
                ):
                    first = (r["ZFIRSTNAME"] or "").strip()
                    last = (r["ZLASTNAME"] or "").strip()
                    org = (r["ZORGANIZATION"] or "").strip()
                    nick = (r["ZNICKNAME"] or "").strip()
                    name = " ".join(x for x in (first, last) if x) or nick or org
                    if not name:
                        continue
                    photo = _strip_prefix(r["ZTHUMBNAILIMAGEDATA"]) or _strip_prefix(r["ZIMAGEDATA"])
                    people[r["Z_PK"]] = Person(name=name, first=first or name, last=last, org=org, photo=photo)
                for r in con.execute("SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER"):
                    self._add(by_handle, people.get(r["ZOWNER"]), norm_handle(r["ZFULLNUMBER"] or ""))
                for r in con.execute("SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS"):
                    self._add(by_handle, people.get(r["ZOWNER"]), norm_handle(r["ZADDRESS"] or ""))
                con.close()
            except sqlite3.Error as e:
                self.last_error = f"{os.path.basename(os.path.dirname(db))[:8]}: {e}"
        self._by_handle = by_handle
        self._sig = tuple(sig)

    @staticmethod
    def _add(m: dict[str, Person], p: Person | None, key: str) -> None:
        if not p or not key:
            return
        cur = m.get(key)
        if cur is None or (cur.photo is None and p.photo is not None):
            m[key] = p
        if key not in p.handles:
            p.handles.append(key)
