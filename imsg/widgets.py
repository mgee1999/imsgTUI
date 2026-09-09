from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from typing import Callable

from rich.table import Table
from rich.text import Text
from textual import work
from textual.color import Color
from textual.binding import Binding
from textual.message import Message as TMessage
from textual.widget import Widget
from textual.widgets import ListItem, Static

from . import media, theme
from .contacts import Contacts, Person
from .db import Attachment, Chat, Message


# ------------------------------------------------------------------ helpers
def fmt_phone(h: str) -> str:
    if not h or "@" in h:
        return h
    d = re.sub(r"\D", "", h)
    if len(d) == 11 and d.startswith("1"):
        return f"({d[1:4]}) {d[4:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return h


def fmt_clock(ts: float) -> str:
    return time.strftime("%-I:%M %p", time.localtime(ts))


def _days_ago(ts: float) -> int:
    lt = time.localtime(ts)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    now = time.localtime()
    today = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(round((today - midnight) / 86400))


def fmt_list_time(ts: float) -> str:
    if not ts:
        return ""
    d = _days_ago(ts)
    if d == 0:
        return fmt_clock(ts)
    if d == 1:
        return "Yesterday"
    if d < 7:
        return time.strftime("%a", time.localtime(ts))
    return time.strftime("%-m/%-d/%y", time.localtime(ts))


def fmt_day(ts: float) -> str:
    d = _days_ago(ts)
    if d == 0:
        return "Today"
    if d == 1:
        return "Yesterday"
    if d < 7:
        return time.strftime("%A", time.localtime(ts))
    fmt = "%A, %B %-d" if d < 365 else "%B %-d, %Y"
    return time.strftime(fmt, time.localtime(ts))


@dataclass
class Ctx:
    """What the widgets need from the app."""
    contacts: Contacts
    image_cls: type | None
    cell_aspect: float          # cell width / cell height in px
    name_of: Callable[[str], str]
    color_of: Callable[[str], str]


# ------------------------------------------------------------------- avatar
class Avatar(Widget):
    DEFAULT_CSS = """
    Avatar { width: 4; height: 2; margin: 0 1 0 0; }
    Avatar > * { width: 4; height: 2; }
    Avatar > Static { text-align: center; content-align: center middle; text-style: bold; color: #0b0b0d; }
    """

    def __init__(self, label: str, color: str, photo: bytes | None, image_cls: type | None, **kw) -> None:
        super().__init__(**kw)
        self.label = (label or "?")[:2]
        self.color = color
        self.photo = photo
        self.image_cls = image_cls

    def compose(self):
        if self.photo and self.image_cls is not None:
            im = media.avatar_image(self.photo, 96)
            if im is not None:
                yield self.image_cls(im)
                return
        s = Static(Text(self.label, style="bold"))
        s.styles.background = self.color
        yield s


# ---------------------------------------------------------------- chat list
class RowText(Widget):
    DEFAULT_CSS = "RowText { width: 1fr; height: 2; }"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.title = ""
        self.color = theme.GRAY
        self.unread = 0
        self.service = ""
        self.ts = 0.0
        self.preview = ""
        self.from_me = False

    def set(self, name: str, color: str, unread: int, service: str, ts: float, preview: str, from_me: bool) -> None:
        self.title, self.color, self.unread, self.service = name, color, unread, service
        self.ts, self.preview, self.from_me = ts, preview, from_me
        self.refresh()

    def render(self):
        svc = theme.service_color(self.service)
        grid = Table.grid(expand=True, padding=(0, 1, 0, 0))
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True)
        name = Text()
        if self.unread:
            name.append("● ", style=svc)
        name.append(self.title, style=f"bold {self.color}" if self.unread else self.color)
        grid.add_row(name, Text(fmt_list_time(self.ts), style=theme.DIM if not self.unread else svc))
        prev = Text(no_wrap=True)
        if self.from_me:
            prev.append("You: ", style=theme.DIM)
        prev.append(self.preview.replace("\n", " "), style=theme.WHITE if self.unread else theme.GRAY)
        badge = Text(f" {self.unread} ", style=f"bold #0b0b0d on {svc}") if self.unread else Text("")
        grid.add_row(prev, badge)
        return grid


class ChatRow(ListItem):
    DEFAULT_CSS = """
    ChatRow { layout: horizontal; height: 2; padding: 0 1; background: transparent; }
    ChatRow.unread { background: #1a1a1e; }
    ChatRow.-highlight { background: #26262b; }
    ChatRow:focus-within { background: #26262b; }
    """

    def __init__(self, chat: Chat, ctx: Ctx, **kw) -> None:
        super().__init__(**kw)
        self.chat = chat
        self.ctx = ctx
        self._avatar: Avatar | None = None

    @property
    def key(self) -> str:
        return self.chat.guid or str(self.chat.rowid)

    @property
    def signature(self) -> tuple:
        c = self.chat
        return (c.last_rowid, c.unread, round(c.last_ts), c.last_preview)

    def _identity(self) -> tuple[str, str, str, bytes | None]:
        c = self.chat
        if c.is_group:
            name = c.display_name or ", ".join(self.ctx.name_of(p).split(" ")[0] for p in c.participants[:3])
            if not c.display_name and len(c.participants) > 3:
                name += f" +{len(c.participants) - 3}"
            return name or "Group", theme.PURPLE, "👥", None
        p = self.ctx.contacts.lookup(c.handle)
        if p:
            return p.name, theme.ORANGE, p.initials, p.photo
        return fmt_phone(c.handle), theme.RED, "#", None

    def compose(self):
        name, color, initials, photo = self._identity()
        self._avatar = Avatar(initials, theme.avatar_color(name) if color != theme.RED else theme.RED, photo, self.ctx.image_cls)
        yield self._avatar
        rt = RowText()
        yield rt
        self._apply(rt, name, color)

    def _apply(self, rt: RowText, name: str, color: str) -> None:
        c = self.chat
        rt.set(name, color, c.unread, c.service, c.last_ts, c.last_preview, c.last_from_me)
        self.set_class(bool(c.unread), "unread")

    def update(self, chat: Chat) -> None:
        self.chat = chat
        name, color, _, _ = self._identity()
        try:
            self._apply(self.query_one(RowText), name, color)
        except Exception:
            pass


# ------------------------------------------------------------ conversation
class Divider(Static):
    DEFAULT_CSS = "Divider { width: 100%; height: 1; text-align: center; color: #636366; margin: 0 0 1 0; }"


class NewDivider(Static):
    DEFAULT_CSS = "NewDivider { width: 100%; height: 1; text-align: center; margin: 0 0 1 0; }"


class Bubble(Static):
    DEFAULT_CSS = """
    Bubble { width: auto; max-width: 78%; height: auto; padding: 0 1; }
    Bubble.them { background: #2c2c2e; color: #f2f2f7; }
    Bubble.me.imessage { background: #0a84ff; color: #ffffff; }
    Bubble.me.sms { background: #1f8a3d; color: #ffffff; }
    Bubble.retracted { background: transparent; color: #636366; text-style: italic; border: round #3a3a3c; }
    Bubble.sticker { background: transparent; }
    """


class ViewAttachment(TMessage):
    def __init__(self, attachment: Attachment, message: Message) -> None:
        super().__init__()
        self.attachment = attachment
        self.message = message


class OpenAttachment(TMessage):
    def __init__(self, attachment: Attachment) -> None:
        super().__init__()
        self.attachment = attachment


class AttachmentWidget(Widget, can_focus=True):
    BINDINGS = [
        Binding("enter", "view", "View / play", show=False),
        Binding("o", "open", "Open in app", show=False),
    ]
    DEFAULT_CSS = """
    AttachmentWidget { width: auto; height: auto; max-width: 78%; layout: vertical; }
    AttachmentWidget:focus { background: #1c1c20; }
    AttachmentWidget:focus > .caption { color: #ffd60a; }
    AttachmentWidget > .caption { width: auto; height: 1; color: #8e8e93; padding: 0 1; }
    AttachmentWidget > .file { width: auto; height: auto; padding: 0 1; color: #f2f2f7; background: #2c2c2e; }
    AttachmentWidget > .placeholder { width: 24; height: 3; color: #636366; content-align: center middle; background: #1c1c20; }
    """

    def __init__(self, att: Attachment, msg: Message, ctx: Ctx, max_cols: int = 40, **kw) -> None:
        super().__init__(**kw)
        self.att = att
        self.msg = msg
        self.ctx = ctx
        self.max_cols = max_cols
        self._img_widget = None

    def compose(self):
        a = self.att
        when = fmt_clock(self.msg.ts)
        if a.kind in ("image", "video") and a.exists and self.ctx.image_cls is not None:
            yield Static("⏳", classes="placeholder")
            if a.kind == "video":
                cap = f"▶ Video {media.fmt_duration(media.video_duration(a.path))} · {a.human_size()} · {when}"
            else:
                cap = f"{a.icon} {a.name} · {a.human_size()} · {when}"
            yield Static(Text(cap), classes="caption")
        else:
            label = f"{a.icon} {a.name or a.kind}"
            if a.kind == "audio":
                label = f"🎤 Voice message {media.fmt_duration(media.video_duration(a.path))}" if a.exists else "🎤 Voice message"
            if not a.exists:
                label += "  (not downloaded)"
            t = Text(label)
            t.append(f"  {a.human_size()}" if a.size else "", style=theme.DIM)
            t.append(f"  {when}", style=theme.DIM)
            yield Static(t, classes="file")

    def on_mount(self) -> None:
        if self.att.kind in ("image", "video") and self.att.exists and self.ctx.image_cls is not None:
            self._load_thumb()

    @work(thread=True, group="thumbs")
    def _load_thumb(self) -> None:
        im = media.thumbnail(self.att.path, str(self.att.rowid), 640, self.att.kind)
        self.app.call_from_thread(self._show, im)

    def _show(self, im) -> None:
        try:
            ph = self.query_one(".placeholder")
        except Exception:
            return
        if im is None:
            ph.update("⚠ can't decode")
            return
        w, h = im.size
        cols = min(self.max_cols, max(12, int(self.screen.size.width * 0.35)))
        rows = max(2, round(cols * self.ctx.cell_aspect * h / w))
        max_rows = max(6, int(self.screen.size.height * 0.45))
        if rows > max_rows:
            rows = max_rows
            cols = max(6, round(rows / (self.ctx.cell_aspect * h / w)))
        if self.att.is_sticker:
            cols, rows = min(cols, 12), min(rows, 6)
        img = self.ctx.image_cls(im)
        img.styles.width = cols
        img.styles.height = rows
        self._img_widget = img
        self.mount(img, before=ph)
        ph.remove()

    def action_view(self) -> None:
        self.post_message(ViewAttachment(self.att, self.msg))

    def action_open(self) -> None:
        self.post_message(OpenAttachment(self.att))

    def on_click(self) -> None:
        self.focus()
        self.action_view()


class MessageRow(Widget):
    DEFAULT_CSS = """
    MessageRow { width: 100%; height: auto; layout: vertical; margin: 0 0 1 0; }
    MessageRow.me { align-horizontal: right; }
    MessageRow > .sender { width: auto; height: 1; padding: 0 1; }
    MessageRow > .reply { width: auto; height: 1; padding: 0 1; color: #636366; text-style: italic; }
    MessageRow > .reactions { width: auto; height: 1; padding: 0 1; color: #8e8e93; }
    MessageRow > .status { width: auto; height: 1; padding: 0 1; color: #636366; }
    MessageRow > .status.failed { color: #ff453a; }
    MessageRow > .system { width: 100%; height: auto; text-align: center; color: #636366; text-style: italic; }
    MessageRow > .edited { width: auto; height: 1; padding: 0 1; color: #636366; }
    """

    def __init__(self, msg: Message, ctx: Ctx, is_group: bool, show_status: bool, reply_preview: str = "", **kw) -> None:
        super().__init__(**kw)
        self.msg = msg
        self.ctx = ctx
        self.is_group = is_group
        self.show_status = show_status
        self.reply_preview = reply_preview
        self.set_class(msg.from_me, "me")

    @property
    def signature(self) -> tuple:
        m = self.msg
        return (m.rowid, m.text, tuple((k, tuple(v)) for k, v in m.reactions.items()), m.status if self.show_status else "",
                m.edited, m.retracted, len(m.attachments))

    def compose(self):
        m = self.msg
        if m.is_system:
            yield Static(Text(system_line(m, self.ctx.name_of)), classes="system")
            return
        svc = "imessage" if (m.service or "").lower() == "imessage" else "sms"
        side = "me" if m.from_me else "them"
        if not m.from_me and self.is_group:
            yield Static(Text(self.ctx.name_of(m.handle), style=self.ctx.color_of(m.handle)), classes="sender")
        if m.reply_to_guid and self.reply_preview:
            yield Static(Text(f"↩ {self.reply_preview[:70]}"), classes="reply")
        parts = m.body_parts()
        if m.retracted and not parts:
            yield Bubble(Text("Unsent a message"), classes="bubble retracted")
        when = fmt_clock(m.ts)
        for i, part in enumerate(parts):
            if isinstance(part, str):
                t = Text(part)
                if m.edited:
                    t.append("  (edited)", style="italic " + ("#cfe3ff" if m.from_me else theme.DIM))
                t.append(f"  {when}", style=("#cfe3ff" if m.from_me and svc == "imessage" else "#d6f2dc" if m.from_me else theme.DIM))
                yield Bubble(t, classes=f"bubble {side} {svc}")
            else:
                yield AttachmentWidget(part, m, self.ctx)
        if not parts and not m.retracted:
            yield Bubble(Text(m.plain() or "…", style="italic"), classes=f"bubble {side} {svc}")
        if m.reactions:
            t = Text()
            for emoji, whos in m.reactions.items():
                names = ", ".join("You" if w == "me" else self.ctx.name_of(w).split(" ")[0] for w in whos)
                t.append(f"{emoji} ", style="bold")
                t.append(names + "   ", style=theme.GRAY)
            yield Static(t, classes="reactions")
        if self.show_status and m.from_me and m.status:
            s = Static(Text(m.status), classes="status")
            if m.status == "Not Delivered":
                s.add_class("failed")
            yield s

    def update(self, msg: Message, show_status: bool) -> None:
        self.msg = msg
        self.show_status = show_status
        self.set_class(msg.from_me, "me")
        self.call_later(self.recompose)


def system_line(m: Message, name_of) -> str:
    who = "You" if m.from_me else name_of(m.handle)
    other = name_of(m.other_handle) if m.other_handle else ""
    if m.item_type == 1:
        return f"{who} {'added' if m.group_action_type == 0 else 'removed'} {other or 'someone'}"
    if m.item_type == 2:
        return f"{who} named the conversation “{m.group_title}”" if m.group_title else f"{who} changed the group name"
    if m.item_type == 3:
        return f"{who} left the conversation"
    return m.text or "·"


# ------------------------------------------------------------------- tiles
class TileSelected(TMessage):
    def __init__(self, chat: Chat) -> None:
        super().__init__()
        self.chat = chat


class TileText(Widget):
    DEFAULT_CSS = "TileText { width: 1fr; height: 2; }"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.title = ""
        self.color = theme.GRAY
        self.unread = 0
        self.ts = 0.0
        self.service = ""

    def set(self, title: str, color: str, unread: int, ts: float, service: str) -> None:
        self.title, self.color, self.unread, self.ts, self.service = title, color, unread, ts, service
        self.refresh()

    def render(self):
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append(self.title, style=f"bold {self.color}")
        t.append("\n")
        if self.unread:
            t.append(f"{self.unread} new", style=f"bold {theme.WHITE}")
        else:
            t.append(fmt_list_time(self.ts), style=theme.DIM)
        return t


class Tile(Widget):
    """One box in the top strip: photo + name. Gray normally, pulsing blue while unread."""

    DEFAULT_CSS = """
    Tile { width: 1fr; height: 4; border: round #3a3a3c; background: #141416; padding: 0 0 0 1;
           layout: horizontal; border-title-color: #636366; border-title-align: left; }
    Tile:hover { border: round #8e8e93; }
    Tile.current { border: round #f2f2f7; border-title-color: #f2f2f7; }
    Tile.unread { border: round #64d2ff; border-title-color: #64d2ff; }
    Tile.unread.current { border: round #ffffff; }
    Tile > Avatar { margin: 0 1 0 0; }
    """
    BASE = Color.parse("#141416")
    LO = Color.parse("#163b5e")
    HI = Color.parse("#2f86d1")

    def __init__(self, chat: Chat, ctx: Ctx, slot: int, **kw) -> None:
        super().__init__(**kw)
        self.chat = chat
        self.ctx = ctx
        self.slot = slot
        self._pulsing = False
        self._phase = False
        self.border_title = str(slot)

    @property
    def key(self) -> str:
        return self.chat.guid or str(self.chat.rowid)

    def _identity(self) -> tuple[str, str, str, bytes | None]:
        c = self.chat
        if c.is_group:
            name = c.display_name or ", ".join(self.ctx.name_of(p).split(" ")[0] for p in c.participants[:2])
            return name or "Group", theme.PURPLE, "👥", None
        p = self.ctx.contacts.lookup(c.handle)
        if p:
            short = p.first if p.first and p.last else p.name
            return short, theme.ORANGE, p.initials, p.photo
        return fmt_phone(c.handle), theme.RED, "#", None

    def compose(self):
        name, color, initials, photo = self._identity()
        yield Avatar(initials, theme.avatar_color(name) if color != theme.RED else theme.RED, photo, self.ctx.image_cls)
        tt = TileText()
        yield tt
        tt.set(name, color, self.chat.unread, self.chat.last_ts, self.chat.service)

    def on_mount(self) -> None:
        self._sync_unread()

    def update(self, chat: Chat) -> None:
        self.chat = chat
        name, color, _, _ = self._identity()
        try:
            self.query_one(TileText).set(name, color, chat.unread, chat.last_ts, chat.service)
        except Exception:
            pass
        self._sync_unread()

    def _sync_unread(self) -> None:
        unread = bool(self.chat.unread)
        self.set_class(unread, "unread")
        if unread and not self._pulsing:
            self._pulsing = True
        elif not unread and self._pulsing:
            self._pulsing = False
            self.styles.background = self.BASE

    def pulse_tick(self, t: float) -> None:
        """Called by the app's pulse timer (~8 Hz). Blends gray→blue→gray on a 1.6 s cycle."""
        if not self._pulsing:
            return
        k = (math.sin(t * math.pi / 0.8) + 1) / 2
        self.styles.background = self.LO.blend(self.HI, k)
        # children cache their render (text cells keep the old bg) — repaint them with the new color
        for child in self.children:
            child.refresh()

    def on_click(self) -> None:
        self.post_message(TileSelected(self.chat))
