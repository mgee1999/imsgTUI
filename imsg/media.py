"""Images, thumbnails, avatars and video playback for the terminal."""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
from functools import lru_cache

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pass

CACHE_DIR = os.path.expanduser("~/.cache/imsg/thumbs")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(key: str, ext: str = "jpg") -> str:
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest()[:20] + "." + ext)


def load_image(path: str, max_px: int = 1024) -> Image.Image | None:
    try:
        im = Image.open(path)
        if im.format == "JPEG":
            im.draft("RGB", (max_px, max_px))
        im = ImageOps.exif_transpose(im)
        if getattr(im, "is_animated", False):
            im.seek(0)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        return im
    except Exception:
        return None


def thumbnail(path: str, key: str, max_px: int = 640, kind: str = "image") -> Image.Image | None:
    """Downscaled preview, cached on disk. Video → first frame via ffmpeg."""
    if not path or not os.path.exists(path):
        return None
    cp = _cache_path(f"{key}:{max_px}:{os.path.getmtime(path)}", "png" if kind == "image" else "jpg")
    if os.path.exists(cp):
        try:
            return Image.open(cp).convert("RGBA")
        except Exception:
            pass
    im: Image.Image | None = None
    if kind == "image":
        im = load_image(path, max_px)
        if im is not None:
            try:
                im.save(cp, "PNG", optimize=False)
            except Exception:
                pass
    elif kind == "video" and shutil.which("ffmpeg"):
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", path, "-frames:v", "1",
                            "-vf", f"scale='min({max_px},iw)':-2", cp], capture_output=True, timeout=20)
            if os.path.exists(cp):
                im = Image.open(cp).convert("RGBA")
        except Exception:
            im = None
    return im


@lru_cache(maxsize=512)
def video_duration(path: str) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return float(out or 0)
    except Exception:
        return 0.0


def fmt_duration(sec: float) -> str:
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


@lru_cache(maxsize=1024)
def avatar_image(photo: bytes, px: int = 128) -> Image.Image | None:
    try:
        im = Image.open(io.BytesIO(photo))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = ImageOps.fit(im, (px, px), Image.Resampling.LANCZOS)
        return im
    except Exception:
        return None


# ----------------------------------------------------------------- playback
def mpv_command(path: str, audio_only: bool = False) -> list[str] | None:
    mpv = shutil.which("mpv")
    if not mpv:
        return None
    cmd = [mpv, "--really-quiet", "--keep-open=no", "--osd-level=1", "--osd-duration=1500", "--term-osd-bar=yes",
           "--msg-level=all=error", "--input-default-bindings=yes", path]
    if audio_only:
        cmd.insert(1, "--vo=null")
        cmd.insert(1, "--term-osd=force")
    else:
        cmd.insert(1, "--vo=kitty")
        cmd.insert(2, "--vo-kitty-use-shm=" + ("yes" if os.environ.get("IMSG_VIDEO_SHM") == "1" else "no"))
        cmd.insert(3, "--profile=fast")
        extra = os.environ.get("IMSG_MPV_ARGS")
        if extra:
            cmd[3:3] = extra.split()
    return cmd


def play_media(path: str, audio_only: bool = False) -> int:
    """Blocking. Call inside App.suspend()."""
    cmd = mpv_command(path, audio_only)
    if cmd is None:
        if audio_only:
            return subprocess.run(["afplay", path]).returncode
        return open_external(path)
    return subprocess.run(cmd).returncode


def open_external(path: str) -> int:
    return subprocess.run(["open", path]).returncode


def quicklook(path: str) -> None:
    subprocess.Popen(["qlmanage", "-p", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
