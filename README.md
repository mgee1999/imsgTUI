# imsg — iMessage in your terminal

A fast TUI for Messages, built for Ghostty. Reads `~/Library/Messages/chat.db`
directly (read-only, WAL included, so new messages show up in well under a
second), resolves names + square contact photos from Contacts, renders photos
and video thumbnails inline with the Kitty graphics protocol, plays video
in-terminal with mpv, and sends through Messages.app.

```
imsg            # the TUI
imsg unread     # print unread messages and exit
imsg chats      # print recent chats and exit  (--limit N)
imsg send "Alex" "on my way"        # by contact name, number, group name or chat guid
```

## Top strip

Eight tiles across the top: contact photo + name for your most active chats
(ranked by message count over the last 14 days). A tile is gray until a message
comes in, then its border turns light blue and the box pulses until you've read
it. Press `1`–`8` or click a tile to jump to that chat; the current one has a
white border.

Pin chats to the front, or change the count/window, in `~/.config/imsg/config.json`:

```json
{ "pinned": ["Alex", "+15550100142"], "top_count": 8, "top_days": 14 }
```

`IMSG_NO_PULSE=1` turns the pulsing off.

## Colors

| Thing | Color |
|---|---|
| Saved contact | orange |
| Unsaved number / email | red |
| Group chat | purple |
| iMessage (unread dot, badge, your bubbles) | blue |
| SMS / RCS | green |
| Unread row | bold name, lighter background, count badge |

## Keys

| Key | Does |
|---|---|
| `↑/↓` `j/k` | move through chats (preview loads as you move) / scroll messages |
| `Enter` | open chat and focus the composer |
| `Esc` | back to the chat list |
| `Tab` / `⇧Tab` | cycle list → messages → composer (Tab inside messages walks attachments) |
| `Ctrl+N` / `Ctrl+P` | next / previous chat, even while typing |
| `1`–`8` | jump to that top-strip tile |
| `u` | next unread chat |
| `/` | search chats (name, number, participant, last message) |
| `[` | load older messages |
| `g` / `G` | top / bottom of the conversation |
| `a` | focus the newest attachment in this chat |
| `Enter` on attachment | image → full-screen viewer · video/voice → mpv in the terminal · PDF → Quick Look |
| `o` on attachment | open with the default Mac app |
| `m` | open this chat in Messages.app |
| `r` | refresh · `?` help · `q` quit |

Composer: `Enter` sends. `/attach ~/Desktop/pic.jpg` sends a file.

## Layout

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

Reactions show under the message (`❤️ Alex  😂 You`), replies show a `↩` quote,
edits get `(edited)`, unsent messages show as such, and the last thing you sent
shows `Sent / Delivered / Read 4:34 PM / Not Delivered`. A `── new messages ──`
line marks where the unread ones start.

## Setup

```
git clone <this repo> ~/Open\ Source/imsg-tui
cd ~/Open\ Source/imsg-tui && ./install.sh     # venv + deps + ~/.local/bin/imsg
brew install mpv ffmpeg                         # in-terminal video + video thumbnails
```

Requires macOS with Messages signed in, Python 3.11+, and a terminal that speaks the
Kitty graphics protocol for inline images (Ghostty, kitty, WezTerm).

Permissions the **terminal app** needs (System Settings → Privacy & Security):

- **Full Disk Access** — to read chat.db and the Contacts database.
- **Automation → Messages** — to send. macOS asks the first time you send.

If chat.db can't be read the top bar says so in red.

## Images / video

- In Ghostty (and kitty) images use the Kitty graphics protocol with Unicode
  placeholders, so thumbnails scroll with the conversation. Anything else falls
  back to half-block art. Force a mode with `imsg --images tgp|halfcell|unicode|off`.
- Video plays with `mpv --vo=kitty`. It's software-decoded and pushed through the
  tty, so it's fine for phone clips at terminal size. If it stutters try
  `IMSG_VIDEO_SHM=1 imsg` (shared-memory transfer, faster where the terminal
  supports it). Extra mpv flags: `IMSG_MPV_ARGS="--vo-kitty-cols=80"`.
- Thumbnails are cached in `~/.cache/imsg/thumbs/` (HEIC decode is ~300 ms, cached
  ones load in ~5 ms).

## How it works

| File | Role |
|---|---|
| `imsg/db.py` | chat.db reader: chat list (one query per table, ~25 ms for 250 chats), per-chat messages, attachments, tapbacks folded into reactions, delivery status |
| `imsg/typedstream.py` | pulls the text out of `attributedBody` (since Ventura ~70% of rows have `text = NULL`) |
| `imsg/contacts.py` | AddressBook sqlite → name, initials, photo (thumbnail blob has a 1-byte prefix: `0x01` + JPEG/PNG; `0x02` = remote ref, skipped) |
| `imsg/send.py` | AppleScript: the chat.db `guid` **is** the AppleScript `chat id`, so 1:1 and group sends both work |
| `imsg/media.py` | thumbnails (PIL / ffmpeg first frame), avatar crops, mpv command |
| `imsg/widgets.py` | chat rows, bubbles, attachment widget (lazy thumbnail load), avatars |
| `imsg/app.py` | the Textual app; polls chat.db + WAL mtimes every 0.4 s and refreshes only when they change; one 8 Hz timer drives the tile pulse |
| `imsg/config.py` | `~/.config/imsg/config.json` (pinned tiles, tile count, activity window) |

Live updates: the app never queries on a timer — it `stat`s `chat.db` / `chat.db-wal`
and only re-reads when Messages.app has written. New messages append without
rebuilding the view; status/reaction changes update in place.

## Limitations

- Can't mark messages read (chat.db is never written; Messages has no scripting for it). Unread state is whatever Messages/iPhone say.
- New conversations: use `imsg send "+15550100142" "hi"` (goes through Messages.app), then the chat appears in the TUI.
- Attachments not downloaded to this Mac show as `(not downloaded)`.
- Single-line composer (no Shift+Enter newlines).
- Not tested under tmux (Kitty graphics needs `allow-passthrough on`).

## Dev

```
cd ~/Open\ Source/imsg-tui
.venv/bin/python -m imsg                # run from source
.venv/bin/python -m imsg --images halfcell   # if images look wrong
```
Headless pilot tests used during development live in the session scratchpad; the
app runs fine under `App.run_test()` for smoke checks.
