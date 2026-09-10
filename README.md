<!-- your intro goes above this line; keep it -->

## What it is

A Messages client that lives in your terminal. Reads your Mac's `chat.db`
directly (read-only, live), pulls names and square contact photos from
Contacts, renders photos and video thumbnails inline over the Kitty graphics
protocol, plays video in-terminal with mpv, and sends through Messages.app.
Built for [Ghostty](https://ghostty.org); works in kitty and WezTerm too.

```
┌ imsg  3 unread  250 chats ────────────────────────────────────────────────┐
│ ╭1────────╮ ╭2────────╮ ╭3────────╮ ╭4────────╮ ╭5────────╮ ╭6────────╮  │
│ │[🖼] Alex │ │[SP] Sam  │ │[🖼] Mom  │ │[👥] Crew │ │[#] (555) │ │[🖼] Jo   │  │
│ │  1 new   │ │  4:20 PM │ │ Yesterday│ │  2 new   │ │  Mon     │ │  Sun     │  │
│ ╰──────────╯ ╰──────────╯ ╰──────────╯ ╰──────────╯ ╰──────────╯ ╰──────────╯  │
│ [🖼] ● Alex Rivera     4:53 PM │ [🖼] Alex Rivera  iMessage  1 unread        │
│      see you soon           1 │      (555) 010-0142                          │
│ [SP] Sam Park         3:23 PM │ ─────────────── Today ───────────────        │
│      [Apple Cash]           3 │  hey are you coming  4:31 PM                 │
│ [#]  (555) 010-0199   4:20 PM │                          yes on my way 4:33 PM│
│      You: I called…           │                                Read 4:34 PM  │
│ …                             │  [photo thumbnail]                           │
│                               │  🖼 IMG_5511.heic · 2.8MB · 4:40 PM          │
│                               ├──────────────────────────────────────────────┤
│                               │ iMessage to Alex Rivera…                      │
└ q Quit  / Search  u Next unread  ? Help ──────────────────────────────────┘
```

- **Chat list** with photos, previews, times, unread badges. Contacts **orange**, unsaved numbers **red**, groups **purple**, iMessage **blue**, SMS/RCS **green**.
- **Top strip** of your 8 most active chats; a tile pulses light blue until you've read the new message. `1`–`8` jumps.
- **Bubbles** with inline times, day dividers, reactions, replies, edited/unsent, Sent/Delivered/Read.
- **Attachments**: inline photos and video frames, full-screen viewer, in-terminal video, open-in-app.
- **Live**: new messages land in under half a second; nothing is ever written to chat.db.
- **CLI**: `imsg unread`, `imsg chats`, `imsg send "Name" "text"`.

## Quick start

```
git clone https://github.com/mgee1999/imsgTUI.git ~/Open\ Source/imsg-tui
cd ~/Open\ Source/imsg-tui && ./install.sh      # venv + deps + ~/.local/bin/imsg
brew install mpv ffmpeg                           # video playback + thumbnails
imsg
```

Give your terminal app **Full Disk Access** (System Settings → Privacy &
Security) so chat.db is readable; allow **Automation → Messages** the first
time you send. Full requirements, internals, keys, config, and troubleshooting:
**[README2.md](README2.md)**.

## Keys (the ones you'll use most)

| | |
|---|---|
| `j/k` `↑/↓` | move through chats |
| `Enter` | open chat, start typing · `Esc` back |
| `1`–`8` | jump to a top-strip tile |
| `u` | next unread · `/` search · `[` older |
| `Enter` / `o` on an attachment | view or play in the terminal / open in a Mac app |
| `?` | all keys |

## License

GPL-2.0-or-later. See [LICENSE](LICENSE) and [COPYING](COPYING).
