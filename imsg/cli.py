from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="imsg", description="iMessage in your terminal")
    ap.add_argument("--images", choices=["auto", "tgp", "halfcell", "unicode", "off"], default="auto",
                    help="image protocol (auto: Kitty graphics in Ghostty/kitty)")
    ap.add_argument("--quiet", action="store_true", help="no toast/bell on new messages")
    ap.add_argument("--limit", type=int, default=250, help="how many chats to list")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("unread", help="print unread messages and exit")
    s = sub.add_parser("send", help="send a message: imsg send <name|number|guid> <text…>")
    s.add_argument("to")
    s.add_argument("text", nargs="+")
    sub.add_parser("chats", help="print recent chats and exit").add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    if args.cmd == "unread":
        return cmd_unread()
    if args.cmd == "chats":
        return cmd_chats(args.limit)
    if args.cmd == "send":
        return cmd_send(args.to, " ".join(args.text))
    from .app import run
    run(images=args.images, quiet=args.quiet, limit=args.limit)
    return 0


def _resolve(to: str):
    from .contacts import Contacts, norm_handle
    from .db import Store
    store = Store()
    chats = store.chats(400)
    if ";" in to:
        return next((c for c in chats if c.guid == to), None), None
    contacts = Contacts()
    key = norm_handle(to)
    for c in chats:
        if not c.is_group and norm_handle(c.identifier) == key and key:
            return c, contacts
    lo = to.lower()
    for c in chats:
        if c.is_group and c.display_name and c.display_name.lower() == lo:
            return c, contacts
    for c in chats:
        if not c.is_group:
            p = contacts.lookup(c.handle)
            if p and p.name.lower() == lo:
                return c, contacts
    for c in chats:
        if not c.is_group:
            p = contacts.lookup(c.handle)
            if p and lo in p.name.lower():
                return c, contacts
        elif c.display_name and lo in c.display_name.lower():
            return c, contacts
    return None, contacts


def cmd_send(to: str, text: str) -> int:
    from .send import SendError, send_text, send_to_handle
    chat, _ = _resolve(to)
    try:
        if chat is not None:
            send_text(chat.guid, text)
            print(f"sent to {chat.display_name or chat.identifier}")
        else:
            send_to_handle(to, text)
            print(f"sent to {to} (new conversation)")
    except SendError as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    return 0


def _console():
    from rich.console import Console
    return Console()


def cmd_chats(limit: int) -> int:
    from rich.table import Table
    from rich.text import Text
    from . import theme
    from .contacts import Contacts
    from .db import Store
    from .widgets import fmt_list_time, fmt_phone
    store, contacts = Store(), Contacts()
    ok, msg = store.health()
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    t = Table(box=None, padding=(0, 1), show_header=False)
    for c in store.chats(limit):
        if c.is_group:
            name, color = (c.display_name or "Group"), theme.PURPLE
        else:
            p = contacts.lookup(c.handle)
            name, color = (p.name, theme.ORANGE) if p else (fmt_phone(c.handle), theme.RED)
        dot = Text("●", style=theme.service_color(c.service)) if c.unread else Text(" ")
        t.add_row(dot, Text(name, style=f"bold {color}" if c.unread else color), Text(fmt_list_time(c.last_ts), style=theme.DIM),
                  Text(("You: " if c.last_from_me else "") + c.last_preview[:70].replace("\n", " "), style=theme.GRAY))
    _console().print(t)
    return 0


def cmd_unread() -> int:
    from rich.text import Text
    from . import theme
    from .contacts import Contacts
    from .db import Store
    from .widgets import fmt_clock, fmt_phone
    store, contacts = Store(), Contacts()
    ok, msg = store.health()
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    con = _console()
    total = 0
    for c in store.chats(300):
        if not c.unread:
            continue
        msgs, _ = store.messages(c, 40)
        unread = [m for m in msgs if not m.from_me and not m.is_read and not m.is_system]
        if not unread:
            continue
        total += len(unread)
        if c.is_group:
            name, color = (c.display_name or "Group"), theme.PURPLE
        else:
            p = contacts.lookup(c.handle)
            name, color = (p.name, theme.ORANGE) if p else (fmt_phone(c.handle), theme.RED)
        head = Text(); head.append("● ", style=theme.service_color(c.service)); head.append(name, style=f"bold {color}")
        head.append(f"  {c.service}", style=theme.service_color(c.service))
        con.print(head)
        for m in unread:
            line = Text(f"   {fmt_clock(m.ts)}  ", style=theme.DIM)
            if c.is_group:
                who = contacts.lookup(m.handle)
                line.append((who.name if who else fmt_phone(m.handle)) + ": ", style=theme.ORANGE if who else theme.RED)
            line.append(m.plain(), style=theme.WHITE)
            con.print(line)
    if not total:
        con.print(Text("no unread messages", style=theme.DIM))
    return 0
