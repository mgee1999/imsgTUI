"""Optional user config at ~/.config/imsg/config.json.

{
  "pinned": ["Alex", "+15551234567"],   # names/numbers forced into the top tiles, in order
  "top_count": 8,                       # how many tiles
  "top_days": 14                        # activity window used to rank the rest
}
"""
from __future__ import annotations

import json
import os

PATH = os.path.expanduser("~/.config/imsg/config.json")
DEFAULTS = {"pinned": [], "top_count": 8, "top_days": 14}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(PATH) as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    cfg["top_count"] = max(1, min(12, int(cfg.get("top_count") or 8)))
    cfg["top_days"] = max(1, int(cfg.get("top_days") or 14))
    cfg["pinned"] = [str(x) for x in (cfg.get("pinned") or [])]
    return cfg
