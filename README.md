# imsgTUI
Terminal Interface for iMessage on macOS 
Designed to help with the amount of terminal windows open, that I know we would all rather reply there when you are in Codex, or Claude CLI


Ever since I was a kid messing with Mac OS 10.4 Tiger on the school computer lab, I always wanted to have a way 
to send messages through the terminal to everyone else around me. 

Nowadays, LAN networks with a bunch of people all working on the same network with the same configurations and 
the same machine is rare, unless you are the system administrator, it's really not possible to set up. 

So this project was to integrate what i use on a daily basis into something that i can run my whole messaging 
through a TUI interface, that works with Ghostty Terminal and Kitty protocol for Image and video rendering. 

Imports and mimics contact photos on the TUI


This was partially vibe coded in full transparency, however I did go through and check source, functions and 
code. 

I would love to encourage more development for the project and additional commits or any changes that people wish 
to see as many of these small Apple specific programs end up becoming extremely useful. 

I will be developing and adding more to the project until something better comes along. 
I am a single dev. Working full time not in the tech field. So my commits will be sporadic

---

## What it is

A Messages client that lives in your terminal. Reads your Mac's `chat.db`
directly (read-only, live), pulls names and square contact photos from
Contacts, renders photos and video thumbnails inline over the Kitty graphics
protocol, plays video in-terminal with mpv, and sends through Messages.app.
Built for [Ghostty](https://ghostty.org); works in kitty and WezTerm too.




<img width="1700" height="335" alt="Screenshot 2026-09-10 at 1 43 40 PM" src="https://github.com/user-attachments/assets/29311718-f754-4b4d-8323-395cfb7ff85a" />

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
│                               │  🖼 IMG_0042.heic · 2.8MB · 4:40 PM          │
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
