"""Read-only access to ~/Library/Messages/chat.db.

Everything here is `mode=ro`; the WAL is still read so new rows show up within
milliseconds of Messages.app writing them. Nothing is ever written or marked read.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass, field

from .typedstream import decode_attributed_body

APPLE_EPOCH = 978307200
DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")

TAPBACKS = {2000: "❤️", 2001: "👍", 2002: "👎", 2003: "😂", 2004: "‼️", 2005: "❓"}
BALLOONS = {
    "com.apple.messages.URLBalloonProvider": "",
    "com.gamerdelights.gamepigeon.ext": "GamePigeon",
    "com.apple.PassbookUIService.PeerPaymentMessagesExtension": "Apple Cash",
    "com.apple.messages.Polls": "Poll",
    "com.apple.findmy.FindMyMessagesApp": "Find My",
    "com.apple.mobileslideshow.PhotosMessagesApp": "Photos",
    "com.apple.DigitalTouchBalloonProvider": "Digital Touch",
    "com.apple.Handwriting.HandwritingProvider": "Handwriting",
    "com.apple.messages.MSMessageExtensionBalloonPlugin:0000000000:com.apple.Music": "Music",
}
OBJ = "￼"  # U+FFFC marks an inline attachment


def apple_ts(v) -> float:
    if not v:
        return 0.0
    v = float(v)
    if v > 1e11:
        v /= 1e9
    return v + APPLE_EPOCH


def to_apple(unix: float) -> int:
    return int((unix - APPLE_EPOCH) * 1e9)


@dataclass
class Attachment:
    rowid: int
    path: str
    mime: str
    uti: str
    name: str
    size: int
    is_sticker: bool = False
    hidden: bool = False

    @property
    def exists(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    @property
    def kind(self) -> str:
        m, u, n = (self.mime or "").lower(), (self.uti or "").lower(), (self.name or "").lower()
        if m.startswith("image/") or u in ("public.heic", "public.png", "public.jpeg") or n.endswith((".heic", ".jpg", ".jpeg", ".png", ".gif", ".webp")):
            return "image"
        if m.startswith("video/") or "movie" in u or "mpeg-4" in u or n.endswith((".mov", ".mp4", ".m4v")):
            return "video"
        if m.startswith("audio/") or "audio" in u or n.endswith((".caf", ".m4a", ".mp3", ".amr")):
            return "audio"
        if m == "application/pdf" or u == "com.adobe.pdf":
            return "pdf"
        if m == "text/vcard" or "vcard" in u:
            return "contact"
        if n.endswith(".pluginpayloadattachment"):
            return "payload"
        return "file"

    @property
    def icon(self) -> str:
        return {"image": "🖼", "video": "🎬", "audio": "🎤", "pdf": "📄", "contact": "👤", "payload": "🔗"}.get(self.kind, "📎")

    def human_size(self) -> str:
        s = self.size or 0
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024 or unit == "GB":
                return f"{s:.0f}{unit}" if unit == "B" else f"{s:.1f}{unit}"
            s /= 1024
        return ""


@dataclass
class Message:
    rowid: int
    guid: str
    ts: float
    from_me: bool
    handle: str
    service: str
    text: str
    is_read: bool
    is_sent: bool
    is_delivered: bool
    date_read: float
    date_delivered: float
    item_type: int
    group_title: str
    group_action_type: int
    other_handle: str
    error: int
    edited: bool
    retracted: bool
    reply_to_guid: str
    balloon: str
    is_audio: bool
    has_attachments: bool
    attachments: list[Attachment] = field(default_factory=list)
    reactions: dict[str, list[str]] = field(default_factory=dict)  # emoji -> [handle|"me"]

    @property
    def is_system(self) -> bool:
        return self.item_type != 0

    @property
    def status(self) -> str:
        """Delivery status for outgoing messages."""
        if not self.from_me:
            return ""
        if self.error:
            return "Not Delivered"
        if self.date_read:
            return "Read " + time.strftime("%-I:%M %p", time.localtime(self.date_read))
        if self.is_delivered:
            return "Delivered"
        if self.is_sent:
            return "Sent"
        return "Sending…"

    @property
    def balloon_label(self) -> str:
        if not self.balloon:
            return ""
        for key, label in BALLOONS.items():
            if key in self.balloon:
                return label
        tail = self.balloon.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
        return tail.title() if tail else "App"

    def body_parts(self) -> list[str | Attachment]:
        """Text split around inline attachments, in order."""
        parts: list[str | Attachment] = []
        atts = list(self.attachments)
        chunks = self.text.split(OBJ) if self.text else [""]
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                parts.append(chunk.strip())
            if i < len(chunks) - 1 and atts:
                parts.append(atts.pop(0))
        parts.extend(atts)
        if not parts and self.balloon_label:
            parts.append(f"[{self.balloon_label}]")
        return parts

    def plain(self) -> str:
        t = (self.text or "").replace(OBJ, "").strip()
        if t:
            return t
        if self.attachments:
            a = self.attachments[0]
            n = len(self.attachments)
            return {"image": "📷 Photo", "video": "🎬 Video", "audio": "🎤 Voice message", "pdf": "📄 PDF",
                    "contact": "👤 Contact", "payload": "🔗 Link"}.get(a.kind, f"📎 {a.name}") + (f" (+{n-1})" if n > 1 else "")
        if self.balloon_label:
            return f"[{self.balloon_label}]"
        if self.has_attachments:
            return "📎 Attachment"
        if self.retracted:
            return "Unsent a message"
        return ""


@dataclass
class Chat:
    rowid: int
    guid: str
    identifier: str
    service: str
    display_name: str
    is_group: bool
    participants: list[str]
    last_ts: float
    last_preview: str
    last_from_me: bool
    unread: int
    is_archived: bool
    last_rowid: int
    rowids: list[int] = field(default_factory=list)

    @property
    def handle(self) -> str:
        return "" if self.is_group else self.identifier


def _clean(text: str | None) -> str:
    if not text:
        return ""
    t = text.replace("�", "")
    return re.sub(r"[ \t]+\n", "\n", t).strip("\n")


def _preview_for(row, handle_names) -> str:
    amt = row["associated_message_type"] or 0
    if 2000 <= amt < 3000:
        emoji = TAPBACKS.get(amt) or row["associated_message_emoji"] or "reaction"
        return f"Reacted {emoji} to a message"
    if 3000 <= amt < 4000:
        return "Removed a reaction"
    if row["item_type"]:
        return _system_text(row["item_type"], row["group_action_type"], row["group_title"], None, bool(row["is_from_me"]))
    return ""


def _system_text(item_type: int, action: int, title: str | None, other: str | None, from_me: bool) -> str:
    who = "You" if from_me else "They"
    if item_type == 1:
        return f"{who} {'added' if action == 0 else 'removed'} {other or 'someone'}"
    if item_type == 2:
        return f"{who} named the group “{title}”" if title else f"{who} changed the group name"
    if item_type == 3:
        return f"{who} left the conversation"
    return ""


class Store:
    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._con: sqlite3.Connection | None = None
        self.last_error: str | None = None

    # ----------------------------------------------------------- connection
    def connect(self) -> sqlite3.Connection:
        if self._con is None:
            con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=3, check_same_thread=False)
            con.row_factory = sqlite3.Row
            con.execute("SELECT 1 FROM message LIMIT 1")
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def health(self) -> tuple[bool, str]:
        if not os.path.exists(self.path):
            return False, "chat.db not found — is Messages signed in?"
        try:
            con = self.connect()
            n = con.execute("SELECT COUNT(*) FROM message").fetchone()[0]
            return True, f"{n:,} messages"
        except sqlite3.Error as e:
            msg = str(e)
            if "unable to open" in msg or "authorization denied" in msg or "not authorized" in msg:
                return False, "chat.db unreadable — give your terminal Full Disk Access (System Settings → Privacy & Security)"
            return False, msg

    def fingerprint(self) -> tuple:
        """Cheap change detector: WAL/db mtimes + sizes. Poll this, not the DB."""
        out = []
        for suffix in ("", "-wal"):
            try:
                st = os.stat(self.path + suffix)
                out.append((st.st_mtime_ns, st.st_size))
            except OSError:
                out.append((0, 0))
        return tuple(out)

    def unread_total(self) -> int:
        row = self.connect().execute(
            "SELECT COUNT(*) FROM message WHERE is_read=0 AND is_from_me=0 AND item_type=0 AND associated_message_type=0"
        ).fetchone()
        return int(row[0])

    def top_chats(self, days: int = 14, limit: int = 8) -> list[int]:
        """chat ROWIDs with the most messages in the last `days` days (most active first)."""
        cutoff = to_apple(time.time() - days * 86400)
        rows = self.connect().execute(
            "SELECT chat_id, COUNT(*) AS n FROM chat_message_join WHERE message_date > ? "
            "GROUP BY chat_id ORDER BY n DESC LIMIT ?", (cutoff, limit * 3)).fetchall()
        return [r["chat_id"] for r in rows]

    # ---------------------------------------------------------------- chats
    def chats(self, limit: int = 250) -> list[Chat]:
        con = self.connect()
        latest = con.execute(
            "SELECT chat_id, MAX(message_date) AS d, message_id FROM chat_message_join "
            "GROUP BY chat_id ORDER BY d DESC LIMIT ?", (limit * 2,)
        ).fetchall()
        if not latest:
            return []
        chat_ids = [r["chat_id"] for r in latest]
        last_mid = {r["chat_id"]: r["message_id"] for r in latest}
        q = ",".join("?" * len(chat_ids))
        chat_rows = {r["ROWID"]: r for r in con.execute(
            f"SELECT ROWID, guid, chat_identifier, service_name, display_name, style, is_archived "
            f"FROM chat WHERE ROWID IN ({q})", chat_ids)}
        mids = list(last_mid.values())
        qm = ",".join("?" * len(mids))
        msg_rows = {r["ROWID"]: r for r in con.execute(
            f"SELECT ROWID, date, text, attributedBody, is_from_me, cache_has_attachments, item_type, "
            f"associated_message_type, associated_message_emoji, group_action_type, group_title, balloon_bundle_id "
            f"FROM message WHERE ROWID IN ({qm})", mids)}
        # no IN(...) here on purpose: the planner then drops the is_read index (224 ms vs 2 ms)
        unread = {r["chat_id"]: r["n"] for r in con.execute(
            "SELECT cmj.chat_id, COUNT(*) AS n FROM message m JOIN chat_message_join cmj ON cmj.message_id=m.ROWID "
            "WHERE m.is_read=0 AND m.is_from_me=0 AND m.item_type=0 AND m.associated_message_type=0 "
            "GROUP BY cmj.chat_id")}
        parts: dict[int, list[str]] = {}
        for r in con.execute(
            f"SELECT chj.chat_id, h.id FROM chat_handle_join chj JOIN handle h ON h.ROWID=chj.handle_id "
            f"WHERE chj.chat_id IN ({q})", chat_ids):
            parts.setdefault(r["chat_id"], []).append(r["id"])

        merged: dict[str, Chat] = {}
        for r in latest:
            c = chat_rows.get(r["chat_id"])
            if c is None:
                continue
            m = msg_rows.get(r["message_id"])
            ident = c["chat_identifier"] or ""
            is_group = (c["style"] == 43) or ident.startswith("chat") or (";+;" in (c["guid"] or ""))
            ts = apple_ts(m["date"]) if m else apple_ts(r["d"])
            preview, from_me = "", False
            if m:
                from_me = bool(m["is_from_me"])
                preview = _preview_for(m, None)
                if not preview:
                    text = _clean(m["text"] or decode_attributed_body(m["attributedBody"]))
                    tmp = Message(rowid=m["ROWID"], guid="", ts=ts, from_me=from_me, handle="", service="", text=text,
                                  is_read=True, is_sent=True, is_delivered=True, date_read=0, date_delivered=0,
                                  item_type=0, group_title="", group_action_type=0, other_handle="", error=0,
                                  edited=False, retracted=False, reply_to_guid="", balloon=m["balloon_bundle_id"] or "",
                                  is_audio=False, has_attachments=bool(m["cache_has_attachments"]))
                    preview = tmp.plain()
            key = ident.lower() if not is_group else (c["guid"] or str(c["ROWID"]))
            cur = merged.get(key)
            plist = parts.get(c["ROWID"], [])
            if cur is None:
                merged[key] = Chat(
                    rowid=c["ROWID"], guid=c["guid"] or "", identifier=ident, service=c["service_name"] or "",
                    display_name=(c["display_name"] or "").strip(), is_group=is_group,
                    participants=plist or ([ident] if ident and not is_group else []),
                    last_ts=ts, last_preview=preview, last_from_me=from_me,
                    unread=int(unread.get(c["ROWID"], 0)), is_archived=bool(c["is_archived"]),
                    last_rowid=r["message_id"], rowids=[c["ROWID"]],
                )
            else:  # older duplicate chat row for the same person: fold it in
                cur.rowids.append(c["ROWID"])
                cur.unread += int(unread.get(c["ROWID"], 0))
                for p in plist:
                    if p not in cur.participants:
                        cur.participants.append(p)
        chats = sorted(merged.values(), key=lambda c: c.last_ts, reverse=True)
        return chats[:limit]

    # ------------------------------------------------------------- messages
    def messages(self, chat: Chat, limit: int = 80, before_ts: float | None = None
                 ) -> tuple[list[Message], dict[str, dict[str, list[str]]]]:
        """Newest `limit` rows of the chat (oldest first). Tapback rows are folded into
        `reactions`; reactions whose target isn't in this page are returned separately
        (keyed by target guid) so the caller can attach them to already-loaded messages."""
        con = self.connect()
        q = ",".join("?" * len(chat.rowids))
        args: list = list(chat.rowids)
        where = f"cmj.chat_id IN ({q})"
        if before_ts:
            where += " AND m.date < ?"
            args.append(to_apple(before_ts))
        args.append(limit)
        rows = con.execute(
            f"""SELECT m.ROWID, m.guid, m.date, m.date_read, m.date_delivered, m.is_from_me, m.is_read, m.is_sent,
                       m.is_delivered, m.text, m.attributedBody, m.cache_has_attachments, m.service, m.item_type,
                       m.group_title, m.group_action_type, m.other_handle, m.associated_message_type,
                       m.associated_message_guid, m.associated_message_emoji, m.error, m.date_edited,
                       m.date_retracted, m.thread_originator_guid, m.balloon_bundle_id, m.is_audio_message,
                       h.id AS handle
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                WHERE {where}
                ORDER BY m.date DESC LIMIT ?""", args).fetchall()
        msgs: list[Message] = []
        reactions: dict[str, dict[str, list[str]]] = {}
        removals: dict[str, list[tuple[str, str]]] = {}
        other_ids: set[int] = set()
        for r in rows:
            amt = r["associated_message_type"] or 0
            if 2000 <= amt < 4000:
                target = (r["associated_message_guid"] or "")
                target = target.split("/", 1)[-1] if "/" in target else target.replace("bp:", "")
                emoji = TAPBACKS.get(amt % 1000 + 2000) or r["associated_message_emoji"] or "🙂"
                who = "me" if r["is_from_me"] else (r["handle"] or "?")
                if amt < 3000:
                    reactions.setdefault(target, {}).setdefault(emoji, []).append(who)
                else:
                    removals.setdefault(target, []).append((emoji, who))
                continue
            if amt not in (0, 1000):
                continue
            if r["item_type"] in (4, 5, 6):
                continue
            if r["other_handle"]:
                other_ids.add(r["other_handle"])
            msgs.append(Message(
                rowid=r["ROWID"], guid=r["guid"] or "", ts=apple_ts(r["date"]), from_me=bool(r["is_from_me"]),
                handle=r["handle"] or "", service=r["service"] or "", text=_clean(r["text"] or decode_attributed_body(r["attributedBody"])),
                is_read=bool(r["is_read"]), is_sent=bool(r["is_sent"]), is_delivered=bool(r["is_delivered"]),
                date_read=apple_ts(r["date_read"]), date_delivered=apple_ts(r["date_delivered"]),
                item_type=r["item_type"] or 0, group_title=r["group_title"] or "", group_action_type=r["group_action_type"] or 0,
                other_handle=str(r["other_handle"] or ""), error=r["error"] or 0, edited=bool(r["date_edited"]),
                retracted=bool(r["date_retracted"]), reply_to_guid=r["thread_originator_guid"] or "",
                balloon=r["balloon_bundle_id"] or "", is_audio=bool(r["is_audio_message"]),
                has_attachments=bool(r["cache_has_attachments"]),
            ))
        for target, rems in removals.items():
            for emoji, who in rems:
                lst = reactions.get(target, {}).get(emoji)
                if lst and who in lst:
                    lst.remove(who)
        # resolve "other_handle" (participant add/remove target) rowids -> handles
        if other_ids:
            qo = ",".join("?" * len(other_ids))
            hmap = {str(r["ROWID"]): r["id"] for r in con.execute(f"SELECT ROWID, id FROM handle WHERE ROWID IN ({qo})", list(other_ids))}
            for m in msgs:
                if m.other_handle:
                    m.other_handle = hmap.get(m.other_handle, m.other_handle)
        # attachments
        need = [m.rowid for m in msgs if m.has_attachments]
        if need:
            qa = ",".join("?" * len(need))
            by_msg: dict[int, list[Attachment]] = {}
            for r in con.execute(
                f"""SELECT maj.message_id, a.ROWID, a.filename, a.mime_type, a.uti, a.transfer_name, a.total_bytes,
                           a.is_sticker, a.hide_attachment
                    FROM message_attachment_join maj JOIN attachment a ON a.ROWID = maj.attachment_id
                    WHERE maj.message_id IN ({qa}) ORDER BY a.ROWID""", need):
                fn = r["filename"] or ""
                path = os.path.expanduser(fn) if fn else ""
                by_msg.setdefault(r["message_id"], []).append(Attachment(
                    rowid=r["ROWID"], path=path, mime=r["mime_type"] or "", uti=r["uti"] or "",
                    name=r["transfer_name"] or os.path.basename(fn), size=r["total_bytes"] or 0,
                    is_sticker=bool(r["is_sticker"]), hidden=bool(r["hide_attachment"])))
            for m in msgs:
                m.attachments = [a for a in by_msg.get(m.rowid, []) if a.kind != "payload" or not m.text]
        in_page = {m.guid for m in msgs}
        for m in msgs:
            if m.guid in reactions:
                m.reactions = {e: w for e, w in reactions[m.guid].items() if w}
        orphans = {g: {e: w for e, w in rx.items() if w} for g, rx in reactions.items() if g not in in_page}
        msgs.reverse()
        return msgs, orphans

    def system_line(self, m: Message, name_of) -> str:
        who = "You" if m.from_me else name_of(m.handle)
        other = name_of(m.other_handle) if m.other_handle else ""
        if m.item_type == 1:
            return f"{who} {'added' if m.group_action_type == 0 else 'removed'} {other or 'someone'}"
        if m.item_type == 2:
            return f"{who} named the conversation “{m.group_title}”" if m.group_title else f"{who} changed the group name"
        if m.item_type == 3:
            return f"{who} left the conversation"
        return m.text or ""
