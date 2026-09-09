#!/bin/zsh
# One-shot setup: venv + deps + launcher on PATH. Re-runnable.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p ~/.local/bin
ln -sf "$HERE/bin/imsg" ~/.local/bin/imsg
command -v mpv >/dev/null || echo "tip: brew install mpv   # for in-terminal video playback"
command -v ffmpeg >/dev/null || echo "tip: brew install ffmpeg   # for video thumbnails"
echo "installed: ~/.local/bin/imsg  (make sure ~/.local/bin is on your PATH)"
echo "grant your terminal Full Disk Access (System Settings → Privacy & Security) so chat.db is readable"
