# imsgTUI — the long README

Features, how it works, and everything needed to run it on another Mac.
The short version is in [README.md](README.md).

---

## Features

**Chat list (left pane)**
- Every conversation, newest first, with a square contact photo (or colored initials), name, last message, time, and an unread badge.
- Color code: saved contacts **orange**, unsaved numbers/emails **red**, group chats **purple**. Unread rows are bold with a lighter background and a dot + badge in the service color (**blue** iMessage, **green** SMS/RCS).
- `/` searches by name, number, participant, or last-message text.

**Top strip**
- Eight tiles showing your most active chats (message count over the last 14 days): photo + first name + "N new" or the last time.
- Gray until a message arrives, then the border turns light blue and the tile pulses until read.
- `1`–`8` or a click jumps to that chat. Pin people to the front in the config file.

**Conversation (right pane)**
- Bubbles like Messages.app: yours in blue (iMessage) or green (SMS/RCS) on the right, theirs in gray on the left, time inside each bubble, day dividers, a `── new messages ──` line where the unread ones start.
- Group chats show the sender's name (orange/red) above each incoming bubble.
- Reactions (❤️ 👍 👎 😂 ‼️ ❓ and custom emoji) listed under the message with who sent them.
- Replies show a `↩` quote of the original. Edited messages get `(edited)`; unsent ones say so.
- Delivery status under your last message: `Sent` / `Delivered` / `Read 4:34 PM` / `Not Delivered`.
- Group events (renamed, added, removed, left) as dim centered lines.
- `[` loads the previous 80 messages while keeping your scroll position.

**Attachments**
- Photos (JPEG, PNG, HEIC, GIF, WebP) and video first-frames render inline at up to ~40 columns wide.
- `Enter` on a photo opens a full-screen viewer. `Enter` on a video or voice memo plays it in the terminal with mpv (`q` to stop). PDFs open in Quick Look. `o` opens anything in its default Mac app.
- Files, contacts (vCard), Apple Cash, GamePigeon, polls, Find My, links: shown with an icon and label.
- `Tab` inside the conversation walks through attachments; `a` jumps to the newest one.

**Sending**
- `Enter` in the composer sends to the current chat through Messages.app (1:1 and groups).
- `/attach ~/path/to/file` sends a file.
- `imsg send "Name" "text"` from any shell; a raw number starts a new conversation.

**Live**
- New messages appear in under half a second without rebuilding the view. Read receipts, reactions, and edits update in place. A toast + bell for messages in other chats (`--quiet` to silence).

**CLI**
```
imsg                         # TUI
imsg unread                  # unread digest to stdout (colored)
imsg chats [--limit N]       # recent chats
imsg send <name|number|guid> <text…>
imsg --images halfcell       # force a fallback image renderer
imsg --quiet                 # no toasts/bell
```

---

## How it works

```
 Messages.app ──writes──▶ ~/Library/Messages/chat.db (+ -wal)
                                     │
                    stat() every 0.4 s│ (mtime changed?)
                                     ▼
                       imsg/db.py  Store (sqlite, mode=ro)
                      ┌──────────────┼──────────────┐
                 chats()        messages(chat)   top_chats()
                      │               │               │
                      ▼               ▼               ▼
              ChatRow widgets   MessageRow/Bubble   Tile strip
                      │         AttachmentWidget
                      │               │ thumbnails (PIL / ffmpeg) → ~/.cache/imsg/thumbs
                      ▼               ▼
                 Textual app (imsg/app.py) ── Kitty graphics via textual-image ──▶ Ghostty
                      │
            Enter in composer ──▶ imsg/send.py ──osascript──▶ Messages.app ──▶ sends
```

**Reading messages.** `chat.db` is opened read-only. The WAL is still read, so rows Messages.app just wrote are visible immediately. Nothing is ever written to the database, and nothing is marked read.

**Detecting changes.** Instead of polling the database, the app `stat()`s `chat.db` and `chat.db-wal` every 0.4 s and only re-queries when an mtime or size changed. Idle cost is two `stat` calls.

**The chat list query.** One `GROUP BY chat_id` over `chat_message_join` (which carries `message_date`) gives the newest message per chat; then one query each for the chat rows, the last-message rows, per-chat unread counts, and participants. ~25 ms for 250 chats on a 530k-message database. Duplicate chat rows for the same person (old SMS + iMessage rows) are merged.

**Message text.** Since macOS Ventura most rows have `text = NULL` and the text lives in `attributedBody`, a legacy NSArchiver "typedstream" blob. `typedstream.py` finds the `NSString` class marker, skips to the `+` byte that precedes the length, decodes the typedstream integer (1 byte, or `0x81` + u16, or `0x82` + u32), and reads that many UTF‑8 bytes. U+FFFC in the text marks where each inline attachment goes.

**Tapbacks, edits, system rows.** Reactions are separate rows with `associated_message_type` 2000–2005 (add), 3000–3005 (remove), 2006/3006 (custom emoji) pointing at the target via `associated_message_guid` (`p:0/GUID` or `bp:GUID`). They're folded onto the target message; if the target is on an older page, the reaction is kept and applied when that page loads. `item_type` 1/2/3 are participant-added-or-removed / renamed / left; 4/5/6 carry no text and are hidden. `date_edited` and `date_retracted` drive the edited/unsent labels.

**Delivery status.** For your last outgoing message: `error` → Not Delivered; `date_read` → Read + time; `is_delivered` → Delivered; `is_sent` → Sent.

**Contacts.** Names and photos come straight from the AddressBook SQLite files (`~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`), so no Contacts permission prompt — Full Disk Access covers it. Phone numbers are matched on their last 10 digits, emails lowercased. Photo blobs (`ZTHUMBNAILIMAGEDATA` / `ZIMAGEDATA`) carry a one-byte prefix: `0x01` + JPEG/PNG bytes; `0x02` + UUID is a remote reference with no local bytes and is skipped. Decoded avatars are cached in memory.

**Images in the terminal.** [textual-image](https://github.com/lnqs/textual-image) transmits each image once with the Kitty graphics protocol and draws it with Unicode placeholder cells, so images scroll and clip like text. The protocol probe and cell-pixel-size lookup happen *before* Textual takes over the terminal (they need to read a terminal reply from stdin). Terminals without the protocol get half-block art.

**Thumbnails.** HEIC decodes through pillow-heif (~300 ms for a 12 MP photo), JPEGs use PIL draft mode, videos get their first frame via `ffmpeg -ss 0.5 -frames:v 1`. Results are cached as PNG/JPEG in `~/.cache/imsg/thumbs/` keyed by attachment id + size + mtime, so a chat you've opened before renders its images in a few milliseconds. Loading runs in worker threads; the UI shows a placeholder until each one lands.

**Video.** mpv with `--vo=kitty` inside Textual's `App.suspend()`: the TUI hands the terminal to mpv, mpv draws frames with the same graphics protocol, and the TUI redraws when mpv exits. `IMSG_VIDEO_SHM=1` switches mpv to shared-memory transfer (faster where the terminal supports it); `IMSG_MPV_ARGS` passes extra flags.

**Sending.** AppleScript: `tell application "Messages" to send <text> to chat id <guid>`. The `guid` column in chat.db (`any;-;+15550100142` for 1:1, `any;+;<groupid>` for groups) is exactly the AppleScript chat id, so no lookup is needed and group sends work. Text is passed as an argv item, never interpolated into the script.

**Live updates without flicker.** When the database changes, the current chat's window is re-read and diffed against what's on screen: new rows are appended (and the view scrolls only if you were already at the bottom), rows whose reactions/status/text changed are recomposed in place, and nothing else is touched. The chat list reorders existing row widgets instead of rebuilding them.

**The pulse.** One 8 Hz app timer blends each unread tile's background along a sine between two blues and repaints the tile's children (Textual caches child renders, so their text cells would otherwise keep the old color).

---

## Replicating this on another Mac

**Hardware / OS**
- Any Mac signed in to iMessage in Messages.app (that's where chat.db comes from). Tested on macOS 26 with a 530k-message database; the schema it relies on has been stable since Ventura.

**Apps**
| App | Why | Install |
|---|---|---|
| [Ghostty](https://ghostty.org) (or kitty / WezTerm) | terminal with the Kitty graphics protocol for inline images and video | `brew install --cask ghostty` |
| [Homebrew](https://brew.sh) | package manager for the rest | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| Python 3.11+ | runtime | `brew install python` |
| [mpv](https://mpv.io) | in-terminal video/audio playback | `brew install mpv` |
| [ffmpeg](https://ffmpeg.org) | video thumbnails and durations | `brew install ffmpeg` |
| git | to clone | ships with Xcode CLT: `xcode-select --install` |

Python packages (installed into the project's own venv by `install.sh`): `textual`, `textual-image`, `pillow`, `pillow-heif`.

**Install**
```
git clone https://github.com/mgee1999/imsgTUI.git ~/Open\ Source/imsg-tui
cd ~/Open\ Source/imsg-tui
./install.sh            # creates .venv, installs deps, links ~/.local/bin/imsg
```
Make sure `~/.local/bin` is on your `PATH` (add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` if not).

**Permissions** (System Settings → Privacy & Security)
1. **Full Disk Access → your terminal app** (Ghostty). Without it chat.db and the Contacts database are unreadable; the top bar tells you in red.
2. **Automation → your terminal → Messages**. macOS prompts the first time you send.

Nothing else: no Contacts permission (photos come from the AddressBook file), no Accessibility.

**First run**
```
imsg
```
If images look like colored blocks instead of photos, the terminal isn't advertising the graphics protocol — try `imsg --images tgp` in Ghostty/kitty, or accept `--images halfcell` elsewhere. Under tmux add `set -g allow-passthrough on`.

**Optional config** — `~/.config/imsg/config.json`
```json
{
  "pinned": ["Alex", "+15550100142"],
  "top_count": 8,
  "top_days": 14
}
```

**Environment variables**
| Var | Effect |
|---|---|
| `IMSG_NO_PULSE=1` | tiles don't pulse |
| `IMSG_VIDEO_SHM=1` | mpv shared-memory transfer |
| `IMSG_MPV_ARGS="…"` | extra mpv flags |

---

## Keys

| Key | Does |
|---|---|
| `↑/↓` `j/k` | move through chats / scroll messages |
| `Enter` | open chat and focus the composer |
| `Esc` | back to the chat list |
| `Tab` / `⇧Tab` | cycle list → messages → composer; inside messages, walks attachments |
| `1`–`8` | jump to a top-strip tile |
| `Ctrl+N` / `Ctrl+P` | next / previous chat, even while typing |
| `u` | next unread chat |
| `/` | search chats |
| `[` | load older messages |
| `g` / `G` | top / bottom of the conversation |
| `a` | focus the newest attachment |
| `Enter` on attachment | view image / play video or audio / Quick Look PDF |
| `o` on attachment | open with the default Mac app |
| `m` | open this chat in Messages.app |
| `r` | refresh · `?` help · `q` quit |

---

## Layout of the code

| File | Role |
|---|---|
| `imsg/db.py` | `Store`: chat list, per-chat messages, attachments, reactions, top chats, change fingerprint |
| `imsg/typedstream.py` | `attributedBody` → text |
| `imsg/contacts.py` | AddressBook → `Person(name, initials, photo)` |
| `imsg/send.py` | AppleScript send (text, file, new conversation) |
| `imsg/media.py` | thumbnails, avatar crops, mpv/open/Quick Look |
| `imsg/widgets.py` | `ChatRow`, `Tile`, `MessageRow`, `Bubble`, `AttachmentWidget`, `Avatar` |
| `imsg/app.py` | the Textual `App`: layout, polling, diffing, keys, screens (viewer, help) |
| `imsg/app.tcss` | stylesheet |
| `imsg/config.py` | user config |
| `imsg/cli.py` | argparse entry: TUI + `unread` / `chats` / `send` |
| `bin/imsg` | launcher (runs the venv's Python) |
| `install.sh` | venv + deps + launcher symlink |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Red "chat.db unreadable" in the top bar | Full Disk Access for the terminal app, then restart the terminal |
| Names show as numbers | same permission (Contacts DB lives under `~/Library`), or the number isn't in Contacts |
| Images are colored blocks | terminal lacks the Kitty graphics protocol; use Ghostty/kitty or `--images halfcell` |
| Send fails with "Not authorized" | System Settings → Privacy & Security → Automation → allow your terminal to control Messages |
| Video doesn't play | `brew install mpv`; if it's slow try `IMSG_VIDEO_SHM=1`; `o` opens QuickTime instead |
| Attachment says "(not downloaded)" | it exists only on your phone; open it once in Messages.app to download |

---

## Limitations / roadmap

- No mark-as-read (chat.db is never written and Messages has no scripting for it).
- Single-line composer (no Shift+Enter). Multi-line `TextArea` is a natural next step.
- No sending of tapbacks, no typing indicators (not exposed by Messages).
- Ideas: message search within a chat, notification center integration, Linux/remote mode over SSH with a synced chat.db, image paste-to-send.

## License

GPL-2.0-or-later — see [LICENSE](LICENSE) and [COPYING](COPYING).
