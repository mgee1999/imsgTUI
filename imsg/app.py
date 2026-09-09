from __future__ import annotations

import os
import sys
import threading
import time

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, ListView, Static

from . import config, media, theme
from .contacts import Contacts
from .db import Chat, Message, Store
from .send import SendError, send_file, send_text
from .contacts import norm_handle
from .widgets import (AttachmentWidget, Avatar, ChatRow, Ctx, Divider, MessageRow, NewDivider, OpenAttachment,
                      Tile, TileSelected, ViewAttachment, fmt_clock, fmt_day, fmt_phone)

PAGE = 80


def pick_image_class(mode: str = "auto"):
    if mode == "off":
        return None
    from textual_image.widget import AutoImage, HalfcellImage, TGPImage, UnicodeImage
    if mode == "halfcell":
        return HalfcellImage
    if mode == "unicode":
        return UnicodeImage
    if mode == "tgp":
        return TGPImage
    if not sys.stdout.isatty():
        return HalfcellImage
    term = (os.environ.get("TERM_PROGRAM", "") + " " + os.environ.get("TERM", "")).lower()
    if "ghostty" in term or "kitty" in term:
        return TGPImage
    return AutoImage


def cell_aspect() -> float:
    try:
        from textual_image._terminal import get_cell_size
        cs = get_cell_size()
        if cs.width and cs.height:
            return cs.width / cs.height
    except Exception:
        pass
    return 0.45


# ------------------------------------------------------------------ screens
class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,q,question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("imsg — keys\n\n", style=f"bold {theme.YELLOW}")
        rows = [
            ("↑/↓  j/k", "move through chats (or scroll messages)"),
            ("Enter", "open chat → start typing"),
            ("Esc", "back to the chat list"),
            ("Tab / ⇧Tab", "cycle: list → messages → composer"),
            ("Ctrl+N / Ctrl+P", "next / previous chat (works while typing)"),
            ("u", "jump to next unread chat"),
            ("/", "search chats"),
            ("[", "load older messages"),
            ("g / G", "top / bottom of the conversation"),
            ("Tab inside messages", "focus attachments"),
            ("Enter on attachment", "view image / play video in the terminal (mpv)"),
            ("o on attachment", "open with the default Mac app"),
            ("a", "focus the latest attachment in this chat"),
            ("m", "open this chat in Messages.app"),
            ("r", "refresh"),
            ("?", "this help"),
            ("q / Ctrl+C", "quit"),
            ("", ""),
            ("/attach <path>", "type in the composer to send a file"),
        ]
        for k, d in rows:
            t.append(f"{k:>22}  ", style=f"bold {theme.ORANGE}")
            t.append(d + "\n", style=theme.WHITE)
        t.append("\ncolors: ", style=theme.DIM)
        t.append("contact ", style=theme.ORANGE); t.append("unsaved number ", style=theme.RED)
        t.append("group ", style=theme.PURPLE); t.append("iMessage ", style=theme.BLUE); t.append("SMS/RCS", style=theme.GREEN)
        yield Static(t, id="help")


class ViewerScreen(ModalScreen):
    BINDINGS = [
        Binding("escape,q,enter", "dismiss", "Close"),
        Binding("o", "open", "Open in app"),
    ]

    def __init__(self, path: str, caption: str, image_cls, aspect: float) -> None:
        super().__init__()
        self.path = path
        self.caption = caption
        self.image_cls = image_cls
        self.aspect = aspect

    def compose(self) -> ComposeResult:
        with Vertical(id="viewer"):
            im = media.load_image(self.path, 2048)
            if im is None or self.image_cls is None:
                yield Static("can't display this image — press o to open it", id="viewer_fallback")
            else:
                w, h = im.size
                cols = max(20, self.app.size.width - 4)
                rows = max(6, self.app.size.height - 3)
                # fit inside the screen keeping aspect
                fit_rows = round(cols * self.aspect * h / w)
                if fit_rows > rows:
                    cols = max(4, round(rows / (self.aspect * h / w)))
                else:
                    rows = max(2, fit_rows)
                img = self.image_cls(im)
                img.styles.width = cols
                img.styles.height = rows
                yield img
            yield Static(Text(f"{self.caption}    [Esc] close   [o] open in app"), id="viewer_caption")

    def action_open(self) -> None:
        media.open_external(self.path)


# ---------------------------------------------------------------- the app
class ImsgApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "imsg"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("slash", "search", "Search"),
        Binding("u", "next_unread", "Next unread"),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("escape", "back", "Back", show=False),
        Binding("left_square_bracket", "older", "Older", show=False),
        Binding("ctrl+n", "next_chat", "Next chat", show=False, priority=True),
        Binding("ctrl+p", "prev_chat", "Prev chat", show=False, priority=True),
        Binding("a", "focus_attachment", "Attachment", show=False),
        Binding("m", "open_in_messages", "Messages.app", show=False),
        Binding("g", "scroll_top", show=False),
        Binding("G", "scroll_bottom", show=False),
    ] + [Binding(str(n), f"tile({n})", show=False) for n in range(1, 10)]

    def __init__(self, images: str = "auto", quiet: bool = False, limit: int = 250,
                 image_cls=None, aspect: float | None = None) -> None:
        super().__init__()
        self.images_mode = images
        self._image_cls = image_cls
        self._aspect = aspect
        self.quiet = quiet
        self.limit = limit
        self.store = Store()
        self.contacts: Contacts | None = None
        self.ctx: Ctx | None = None
        self.chats: list[Chat] = []
        self.rows: dict[str, ChatRow] = {}
        self.current: Chat | None = None
        self.messages: list[Message] = []
        self.guid_index: dict[str, Message] = {}
        self._fp = None
        self._lock = threading.Lock()
        self._filter = ""
        self._select_timer = None
        self._last_max_rowid = 0
        self._loading = False
        self._rebuilding = False
        self._header_guid: str | None = None
        self.cfg = config.load()
        self.tiles: list[Tile] = []

    # ----------------------------------------------------------- compose
    def compose(self) -> ComposeResult:
        yield Static("", id="topbar")
        yield Horizontal(id="tiles")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Input(placeholder="/ search chats", id="search")
                yield ListView(id="chats")
            with Vertical(id="right"):
                with Horizontal(id="convhead"):
                    yield Static("", id="convtitle")
                yield VerticalScroll(id="messages")
                yield Input(placeholder="Message…", id="composer")
        yield Footer()

    def on_mount(self) -> None:
        ok, msg = self.store.health()
        if not ok:
            self.query_one("#topbar", Static).update(Text(f" imsg   {msg}", style=theme.RED))
            self.notify(msg, title="Can't read chat.db", severity="error", timeout=30)
            return
        self.contacts = Contacts()
        # image class + cell size are resolved BEFORE App.run() (see run()): textual-image
        # queries the terminal for them, which can't happen once Textual owns stdin.
        image_cls = self._image_cls if self._image_cls is not None or self.images_mode == "off" else pick_image_class(self.images_mode)
        self.ctx = Ctx(contacts=self.contacts, image_cls=image_cls,
                       cell_aspect=self._aspect or 0.45, name_of=self.name_of, color_of=self.color_of)
        self.query_one("#chats", ListView).focus()
        self._initial_load()
        self.set_interval(0.4, self._poll)
        if os.environ.get("IMSG_NO_PULSE") != "1":
            self.set_interval(1 / 8, self._pulse_tiles)

    # ------------------------------------------------------------ naming
    def name_of(self, handle: str) -> str:
        if not handle:
            return "?"
        if handle == "me":
            return "You"
        p = self.contacts.lookup(handle) if self.contacts else None
        return p.name if p else fmt_phone(handle)

    def color_of(self, handle: str) -> str:
        p = self.contacts.lookup(handle) if self.contacts else None
        return theme.ORANGE if p else theme.RED

    def chat_name(self, c: Chat) -> str:
        if c.is_group:
            if c.display_name:
                return c.display_name
            names = [self.name_of(p).split(" ")[0] for p in c.participants[:3]]
            extra = f" +{len(c.participants) - 3}" if len(c.participants) > 3 else ""
            return (", ".join(names) + extra) or "Group"
        return self.name_of(c.handle)

    # ----------------------------------------------------------- loading
    @work(thread=True, exclusive=True, group="load")
    def _initial_load(self) -> None:
        with self._lock:
            chats = self.store.chats(self.limit)
            top = self.store.top_chats(self.cfg["top_days"], self.cfg["top_count"])
            fp = self.store.fingerprint()
        self.call_from_thread(self._apply_chats, chats, fp, True, top)

    async def _apply_chats(self, chats: list[Chat], fp, first: bool, top_ids: list[int] | None = None) -> None:
        self._fp = fp
        prev_by_key = {(c.guid or str(c.rowid)): c for c in self.chats}
        self.chats = chats
        if self.current is not None:
            for c in chats:
                if c.guid == self.current.guid:
                    if c.unread != self.current.unread or c.display_name != self.current.display_name:
                        self._header_text(c)
                    self.current = c
                    break
        await self._render_chat_list(select_first=first)
        await self._render_tiles(self._pick_top(chats, top_ids or []))
        self._update_topbar()
        if not first and not self.quiet:
            for c in chats:
                old = prev_by_key.get(c.guid or str(c.rowid))
                if c.unread and (old is None or c.last_rowid != old.last_rowid) and not c.last_from_me \
                        and (self.current is None or c.guid != self.current.guid):
                    self.notify(c.last_preview[:120] or "New message", title=self.chat_name(c), timeout=6)
                    self.bell()

    # -------------------------------------------------------------- tiles
    def _pick_top(self, chats: list[Chat], top_ids: list[int]) -> list[Chat]:
        n = self.cfg["top_count"]
        out: list[Chat] = []
        seen: set[str] = set()
        for pin in self.cfg["pinned"]:
            key = norm_handle(pin)
            lo = pin.lower()
            for c in chats:
                if c.guid in seen:
                    continue
                hit = (not c.is_group and key and norm_handle(c.identifier) == key) or \
                      (c.is_group and c.display_name.lower() == lo) or \
                      (not c.is_group and self.name_of(c.handle).lower() == lo)
                if hit:
                    out.append(c); seen.add(c.guid)
                    break
        by_rowid = {rid: c for c in chats for rid in c.rowids}
        for rid in top_ids:
            c = by_rowid.get(rid)
            if c is not None and c.guid not in seen:
                out.append(c); seen.add(c.guid)
            if len(out) >= n:
                break
        for c in chats:  # pad with most recent if the activity window was quiet
            if len(out) >= n:
                break
            if c.guid not in seen:
                out.append(c); seen.add(c.guid)
        return out[:n]

    async def _render_tiles(self, top: list[Chat]) -> None:
        strip = self.query_one("#tiles", Horizontal)
        keys = [c.guid or str(c.rowid) for c in top]
        if [t.key for t in self.tiles] == keys:
            for t, c in zip(self.tiles, top):
                if t.chat.unread != c.unread or t.chat.last_rowid != c.last_rowid:
                    t.update(c)
        else:
            await strip.remove_children()
            self.tiles = [Tile(c, self.ctx, i + 1) for i, c in enumerate(top)]
            if self.tiles:
                await strip.mount(*self.tiles)
        strip.display = bool(self.tiles)
        self._mark_current_tile()

    def _pulse_tiles(self) -> None:
        t = time.monotonic()
        for tile in self.tiles:
            if tile._pulsing:
                tile.pulse_tick(t)

    def _mark_current_tile(self) -> None:
        cur = self.current.guid if self.current else None
        for t in self.tiles:
            t.set_class(t.chat.guid == cur, "current")

    @on(TileSelected)
    def _on_tile(self, event: TileSelected) -> None:
        self._jump_to(event.chat)

    def action_tile(self, n: int) -> None:
        if 1 <= n <= len(self.tiles):
            self._jump_to(self.tiles[n - 1].chat)

    def _jump_to(self, chat: Chat) -> None:
        self.select_chat(chat)
        lv = self.query_one("#chats", ListView)
        visible = self._visible_chats()
        for i, c in enumerate(visible):
            if c.guid == chat.guid:
                lv.index = i
                break
        lv.focus()

    def _visible_chats(self) -> list[Chat]:
        if not self._filter:
            return self.chats
        f = self._filter.lower()
        return [c for c in self.chats if f in self.chat_name(c).lower() or f in c.identifier.lower()
                or any(f in p.lower() or f in self.name_of(p).lower() for p in c.participants)
                or f in c.last_preview.lower()]

    async def _render_chat_list(self, select_first: bool = False) -> None:
        lv = self.query_one("#chats", ListView)
        visible = self._visible_chats()
        keys = [c.guid or str(c.rowid) for c in visible]
        current_key = self.current.guid if self.current else None
        existing_rows = [r for r in lv.children if isinstance(r, ChatRow)]
        existing_keys = [r.key for r in existing_rows]
        if existing_keys == keys:
            for c, k in zip(visible, keys):
                row = self.rows[k]
                if row.signature != (c.last_rowid, c.unread, round(c.last_ts), c.last_preview):
                    row.update(c)
            return
        self._rebuilding = True
        try:
            if sorted(existing_keys) == sorted(keys) and len(set(keys)) == len(keys):
                # same chats, new order: move rows instead of rebuilding
                for pos, k in enumerate(keys):
                    row = self.rows[k]
                    if lv.children[pos] is not row:
                        lv.move_child(row, before=pos)
                for c, k in zip(visible, keys):
                    row = self.rows[k]
                    if row.signature != (c.last_rowid, c.unread, round(c.last_ts), c.last_preview):
                        row.update(c)
            else:
                await lv.clear()
                self.rows = {}
                new_rows = [ChatRow(c, self.ctx) for c in visible]
                for r in new_rows:
                    self.rows[r.key] = r
                if new_rows:
                    await lv.extend(new_rows)
            idx = keys.index(current_key) if current_key in keys else (0 if (select_first and keys) else None)
            for r in lv.children:
                if isinstance(r, ChatRow):
                    r.highlighted = False
            lv.index = None
            if idx is not None:
                lv.index = idx
                if self.current is None and select_first:
                    self.select_chat(visible[idx])
        finally:
            self.set_timer(0.2, self._end_rebuild)

    def _end_rebuild(self) -> None:
        self._rebuilding = False

    def _update_topbar(self) -> None:
        unread = sum(c.unread for c in self.chats)
        t = Text(" imsg ", style=f"bold {theme.WHITE}")
        if unread:
            t.append(f" {unread} unread ", style=f"bold #0b0b0d on {theme.BLUE}")
        else:
            t.append(" no unread ", style=theme.DIM)
        t.append(f"   {len(self.chats)} chats", style=theme.DIM)
        t.append("   ?  help", style=theme.DIM)
        if self.contacts is not None and self.contacts.last_error:
            t.append(f"   contacts: {self.contacts.last_error}", style=theme.RED)
        self.query_one("#topbar", Static).update(t)

    # ------------------------------------------------------------ polling
    def _poll(self) -> None:
        if self._fp is None or self._loading:
            return
        fp = self.store.fingerprint()
        if fp != self._fp:
            self._fp = fp
            self._refresh_all()

    @work(thread=True, exclusive=True, group="refresh")
    def _refresh_all(self) -> None:
        with self._lock:
            chats = self.store.chats(self.limit)
            top = self.store.top_chats(self.cfg["top_days"], self.cfg["top_count"])
            fp = self.store.fingerprint()
            cur = self.current
            msgs, orphans = self.store.messages(cur, max(PAGE, len(self.messages))) if cur else ([], {})
        self.call_from_thread(self._apply_chats, chats, fp, False, top)
        if cur is not None:
            self.call_from_thread(self._apply_messages, cur, msgs, orphans, incremental=True)

    # ------------------------------------------------------ conversation
    @on(ListView.Highlighted, "#chats")
    def _on_highlight(self, event: ListView.Highlighted) -> None:
        item = event.item
        if not isinstance(item, ChatRow) or self._rebuilding:
            return
        if self.current is not None and item.chat.guid == self.current.guid:
            return
        if self._select_timer is not None:
            self._select_timer.stop()
        chat = item.chat
        self._select_timer = self.set_timer(0.12, lambda: self.select_chat(chat))

    @on(ListView.Selected, "#chats")
    def _on_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ChatRow):
            self.select_chat(event.item.chat)
            self.query_one("#composer", Input).focus()

    def select_chat(self, chat: Chat) -> None:
        if self.current is not None and chat.guid == self.current.guid and self.messages:
            return
        self.current = chat
        self.messages = []
        self.guid_index = {}
        self._render_header(chat)
        self._mark_current_tile()
        comp = self.query_one("#composer", Input)
        comp.remove_class("imessage", "sms")
        comp.add_class("imessage" if chat.service.lower() == "imessage" else "sms")
        comp.placeholder = f"{chat.service or 'Message'} to {self.chat_name(chat)}…"
        self._load_messages(chat)

    def _render_header(self, chat: Chat) -> None:
        head = self.query_one("#convhead", Horizontal)
        if self._header_guid != chat.guid:
            for a in head.query(Avatar):
                a.remove()
            name = self.chat_name(chat)
            if chat.is_group:
                color, initials, photo = theme.PURPLE, "👥", None
            else:
                p = self.contacts.lookup(chat.handle)
                color = theme.ORANGE if p else theme.RED
                initials, photo = (p.initials if p else "#"), (p.photo if p else None)
            avatar = Avatar(initials, theme.avatar_color(name) if color != theme.RED else theme.RED, photo, self.ctx.image_cls)
            head.mount(avatar, before=0)
            self._header_guid = chat.guid
        self._header_text(chat)

    def _header_text(self, chat: Chat) -> None:
        name = self.chat_name(chat)
        if chat.is_group:
            color = theme.PURPLE
            sub = ", ".join(self.name_of(p) for p in chat.participants)
        else:
            p = self.contacts.lookup(chat.handle)
            color = theme.ORANGE if p else theme.RED
            sub = fmt_phone(chat.handle) if p else ""
        t = Text()
        t.append(name, style=f"bold {color}")
        svc = chat.service or "?"
        t.append(f"  {svc}", style=f"bold {theme.service_color(svc)}")
        if chat.unread:
            t.append(f"  {chat.unread} unread", style=theme.GRAY)
        t.append("\n")
        t.append(sub, style=theme.DIM)
        self.query_one("#convtitle", Static).update(t)

    @work(thread=True, exclusive=True, group="messages")
    def _load_messages(self, chat: Chat) -> None:
        with self._lock:
            msgs, orphans = self.store.messages(chat, PAGE)
        self.call_from_thread(self._apply_messages, chat, msgs, orphans, incremental=False)

    def _apply_messages(self, chat: Chat, msgs: list[Message], orphans: dict, incremental: bool) -> None:
        if self.current is None or chat.guid != self.current.guid:
            return
        for guid, rx in orphans.items():
            if guid in self.guid_index:
                self.guid_index[guid].reactions = rx
        view = self.query_one("#messages", VerticalScroll)
        if incremental and self.messages:
            old_ids = [m.rowid for m in self.messages]
            new_ids = [m.rowid for m in msgs]
            if new_ids[:len(old_ids)] == old_ids or (old_ids and new_ids and set(old_ids) <= set(new_ids)
                                                     and new_ids.index(old_ids[0]) == 0):
                # pure append (plus in-place changes)
                known = {m.rowid: m for m in self.messages}
                at_bottom = view.scroll_y >= view.max_scroll_y - 2
                last_out = self._last_outgoing(msgs)
                rows = {r.msg.rowid: r for r in view.query(MessageRow)}
                added = []
                for m in msgs:
                    self.guid_index[m.guid] = m
                    if m.rowid in known:
                        r = rows.get(m.rowid)
                        if r is not None:
                            show = (m.rowid == last_out)
                            r_sig = r.signature
                            r.msg, r.show_status = m, show
                            if r.signature != r_sig:
                                r.update(m, show)
                    else:
                        added.append(m)
                if added:
                    prev = self.messages[-1] if self.messages else None
                    widgets = []
                    for m in added:
                        if prev is None or fmt_day(prev.ts) != fmt_day(m.ts):
                            widgets.append(Divider(fmt_day(m.ts)))
                        widgets.append(self._row_for(m, chat, m.rowid == last_out))
                        prev = m
                    view.mount(*widgets)
                    if at_bottom:
                        self.call_after_refresh(lambda: view.scroll_end(animate=False))
                self.messages = msgs
                return
        # full (re)build
        self.messages = msgs
        self.guid_index = {m.guid: m for m in msgs}
        view.remove_children()
        widgets = self._build_rows(msgs, chat)
        if widgets:
            view.mount(*widgets)
        else:
            view.mount(Static("No messages yet", id="empty"))
        self.call_after_refresh(lambda: view.scroll_end(animate=False))

    def _last_outgoing(self, msgs: list[Message]) -> int | None:
        for m in reversed(msgs):
            if m.from_me and not m.is_system:
                return m.rowid
        return None

    def _row_for(self, m: Message, chat: Chat, show_status: bool) -> MessageRow:
        reply = ""
        if m.reply_to_guid:
            target = self.guid_index.get(m.reply_to_guid)
            if target is not None:
                reply = ("You: " if target.from_me else self.name_of(target.handle).split(" ")[0] + ": ") + target.plain()
        return MessageRow(m, self.ctx, chat.is_group, show_status, reply)

    def _build_rows(self, msgs: list[Message], chat: Chat) -> list:
        widgets = []
        prev: Message | None = None
        last_out = self._last_outgoing(msgs)
        first_unread = next((m.rowid for m in msgs if not m.from_me and not m.is_read and not m.is_system), None)
        for m in msgs:
            if prev is None or fmt_day(prev.ts) != fmt_day(m.ts):
                widgets.append(Divider(fmt_day(m.ts)))
            if m.rowid == first_unread:
                widgets.append(NewDivider(Text("── new messages ──", style=f"bold {theme.service_color(chat.service)}")))
            widgets.append(self._row_for(m, chat, m.rowid == last_out))
            prev = m
        return widgets

    def action_older(self) -> None:
        if self.current is None or not self.messages or self._loading:
            return
        self._loading = True
        self._load_older(self.current, self.messages[0].ts)

    @work(thread=True, exclusive=True, group="older")
    def _load_older(self, chat: Chat, before_ts: float) -> None:
        with self._lock:
            msgs, orphans = self.store.messages(chat, PAGE, before_ts=before_ts)
        self.call_from_thread(self._prepend, chat, msgs, orphans)

    def _prepend(self, chat: Chat, msgs: list[Message], orphans: dict) -> None:
        self._loading = False
        if self.current is None or chat.guid != self.current.guid:
            return
        if not msgs:
            self.notify("No older messages", timeout=2)
            return
        view = self.query_one("#messages", VerticalScroll)
        for guid, rx in orphans.items():
            if guid in self.guid_index:
                self.guid_index[guid].reactions = rx
        for m in msgs:
            self.guid_index[m.guid] = m
        old_first = self.messages[0]
        widgets = []
        prev = None
        for m in msgs:
            if prev is None or fmt_day(prev.ts) != fmt_day(m.ts):
                widgets.append(Divider(fmt_day(m.ts)))
            widgets.append(self._row_for(m, chat, False))
            prev = m
        if fmt_day(prev.ts) == fmt_day(old_first.ts):
            first_div = next((w for w in view.children if isinstance(w, Divider)), None)
            if first_div is not None:
                first_div.remove()
        self.messages = msgs + self.messages
        anchor = view.children[0] if view.children else None
        view.mount(*widgets, before=0)

        def keep_position() -> None:
            if anchor is not None:
                view.scroll_to_widget(anchor, top=True, animate=False)
        self.call_after_refresh(keep_position)

    # ------------------------------------------------------------ sending
    @on(Input.Submitted, "#composer")
    def _on_send(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self.current is None:
            return
        comp = self.query_one("#composer", Input)
        comp.value = ""
        chat = self.current
        if text.startswith("/attach "):
            path = os.path.expanduser(text[8:].strip().strip("'\""))
            if not os.path.exists(path):
                self.notify(f"No such file: {path}", severity="error")
                comp.value = text
                return
            self._send(chat, path, is_file=True)
        else:
            self._send(chat, text, is_file=False)

    @work(thread=True, group="send")
    def _send(self, chat: Chat, payload: str, is_file: bool) -> None:
        try:
            if is_file:
                send_file(chat.guid, payload)
            else:
                send_text(chat.guid, payload)
        except SendError as e:
            self.call_from_thread(self._send_failed, payload, str(e))
            return
        self.call_from_thread(self._poll_soon)

    def _send_failed(self, payload: str, err: str) -> None:
        self.notify(err, title="Send failed", severity="error", timeout=8)
        comp = self.query_one("#composer", Input)
        if not comp.value:
            comp.value = payload

    def _poll_soon(self) -> None:
        self.set_timer(0.3, self._poll)
        self.set_timer(1.5, self._poll)

    # --------------------------------------------------------- attachments
    @on(ViewAttachment)
    def _view_attachment(self, event: ViewAttachment) -> None:
        a = event.attachment
        if not a.exists:
            self.notify("Attachment isn't downloaded on this Mac", severity="warning")
            return
        if a.kind == "image":
            self.push_screen(ViewerScreen(a.path, f"{a.name} · {a.human_size()} · {fmt_clock(event.message.ts)}",
                                          self.ctx.image_cls, self.ctx.cell_aspect))
        elif a.kind in ("video", "audio"):
            self._play(a.path, a.kind == "audio")
        elif a.kind == "pdf":
            media.quicklook(a.path)
        else:
            media.open_external(a.path)

    def _play(self, path: str, audio_only: bool) -> None:
        with self.suspend():
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            rc = media.play_media(path, audio_only)
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
        self.refresh()
        if rc not in (0, 4):
            self.notify(f"mpv exited with {rc} — press o to open in QuickTime instead", severity="warning")

    @on(OpenAttachment)
    def _open_attachment(self, event: OpenAttachment) -> None:
        if event.attachment.exists:
            media.open_external(event.attachment.path)
        else:
            self.notify("Attachment isn't downloaded on this Mac", severity="warning")

    def action_focus_attachment(self) -> None:
        atts = list(self.query_one("#messages").query(AttachmentWidget))
        if atts:
            atts[-1].focus()
            self.query_one("#messages", VerticalScroll).scroll_to_widget(atts[-1], animate=False)

    # ----------------------------------------------------------- actions
    def action_search(self) -> None:
        self.query_one("#search", Input).focus()

    @on(Input.Changed, "#search")
    async def _on_search(self, event: Input.Changed) -> None:
        self._filter = event.value.strip()
        await self._render_chat_list()

    @on(Input.Submitted, "#search")
    def _on_search_submit(self, event: Input.Submitted) -> None:
        self.query_one("#chats", ListView).focus()

    async def action_back(self) -> None:
        focused = self.focused
        search = self.query_one("#search", Input)
        lv = self.query_one("#chats", ListView)
        if focused is search:
            search.value = ""
            self._filter = ""
            await self._render_chat_list()
            lv.focus()
        elif focused is lv:
            pass
        else:
            lv.focus()

    def action_next_unread(self) -> None:
        visible = self._visible_chats()
        if not visible:
            return
        lv = self.query_one("#chats", ListView)
        start = (lv.index or 0) + 1
        order = list(range(start, len(visible))) + list(range(0, start))
        for i in order:
            if visible[i].unread:
                self.select_chat(visible[i])
                lv.index = i
                lv.focus()
                return
        self.notify("No unread chats", timeout=2)

    def _move_chat(self, delta: int) -> None:
        lv = self.query_one("#chats", ListView)
        visible = self._visible_chats()
        if not visible:
            return
        i = max(0, min(len(visible) - 1, (lv.index or 0) + delta))
        self.select_chat(visible[i])
        lv.index = i

    def action_next_chat(self) -> None:
        self._move_chat(1)

    def action_prev_chat(self) -> None:
        self._move_chat(-1)

    def action_refresh(self) -> None:
        self._fp = None
        self._refresh_all()
        self._fp = self.store.fingerprint()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_open_in_messages(self) -> None:
        if self.current is None:
            return
        target = self.current.identifier if not self.current.is_group else ""
        if target:
            media.open_external(f"imessage://{target}")
        else:
            os.system("open -a Messages")

    def action_scroll_top(self) -> None:
        self.query_one("#messages", VerticalScroll).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self.query_one("#messages", VerticalScroll).scroll_end(animate=False)

    def on_key(self, event) -> None:
        # vim keys in the two lists
        f = self.focused
        if isinstance(f, ListView) and event.key in ("j", "k"):
            f.action_cursor_down() if event.key == "j" else f.action_cursor_up()
            event.stop()
        elif isinstance(f, VerticalScroll) and event.key in ("j", "k"):
            f.scroll_down(animate=False) if event.key == "j" else f.scroll_up(animate=False)
            event.stop()


def run(images: str = "auto", quiet: bool = False, limit: int = 250) -> None:
    # Probe the terminal (graphics protocol + cell pixel size) while it is still in
    # cooked mode; textual-image caches both answers for the rest of the process.
    image_cls = pick_image_class(images)
    aspect = cell_aspect() if image_cls is not None else 0.45
    ImsgApp(images=images, quiet=quiet, limit=limit, image_cls=image_cls, aspect=aspect).run()
