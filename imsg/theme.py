"""Colors. Apple system palette so it reads like Messages.app."""
ORANGE = "#ff9f0a"      # saved contacts
RED = "#ff453a"         # unsaved numbers / emails
PURPLE = "#bf5af2"      # group chats
BLUE = "#0a84ff"        # iMessage
GREEN = "#30d158"       # SMS / RCS
GREEN_BUBBLE = "#1f8a3d"
GRAY = "#8e8e93"
DIM = "#636366"
WHITE = "#f2f2f7"
YELLOW = "#ffd60a"
BUBBLE_IN = "#2c2c2e"
BG = "#0b0b0d"
PANEL = "#141416"
ROW_UNREAD = "#1a1a1e"
AVATAR_PALETTE = ["#5e5ce6", "#ff375f", "#ff9f0a", "#30d158", "#64d2ff", "#bf5af2", "#ffd60a", "#ac8e68", "#ff6961", "#0a84ff"]


def service_color(service: str) -> str:
    return BLUE if (service or "").lower() == "imessage" else GREEN


def avatar_color(key: str) -> str:
    return AVATAR_PALETTE[sum(map(ord, key or "?")) % len(AVATAR_PALETTE)]
