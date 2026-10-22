import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://discord.com/api/v10"
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
LEAD_MINUTES = int(os.environ.get("LEAD_MINUTES", "120"))
MENTION = os.environ.get("MENTION", "@everyone")
DRY_RUN = os.environ.get("DRY_RUN") == "1"

SENT_FILE = Path(__file__).with_name("sent.json")
SCHEDULED = 1


def discord(method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bot {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com, 1.0) event-reminder",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"Discord API error {e.code} on {path}: {e.read().decode()}")


def load_sent():
    try:
        return json.loads(SENT_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def where(event):
    if event.get("channel_id"):
        return f"<#{event['channel_id']}>"
    loc = (event.get("entity_metadata") or {}).get("location")
    return loc or None


def build_message(event, start):
    ts = int(start.timestamp())
    lines = [
        f"{MENTION} ⏰ **Reminder: {event['name']}** is tonight!",
        f"🕒 Starts <t:{ts}:t> (<t:{ts}:R>)",
    ]
    loc = where(event)
    if loc:
        lines.append(f"📍 {loc}")
    lines.append(f"🔗 https://discord.com/events/{GUILD_ID}/{event['id']}")
    return "\n".join(lines)


def main():
    now = datetime.now(timezone.utc)
    sent = load_sent()
    events = discord("GET", f"/guilds/{GUILD_ID}/scheduled-events")

    for event in events:
        if event.get("status") != SCHEDULED:
            continue
        start = datetime.fromisoformat(event["scheduled_start_time"].replace("Z", "+00:00"))
        remind_at = start - timedelta(minutes=LEAD_MINUTES)
        key = f"{event['id']}@{event['scheduled_start_time']}"

        if key in sent or not (remind_at <= now < start):
            continue

        msg = build_message(event, start)
        print(f"Reminding for '{event['name']}' (starts {start.isoformat()})")
        if DRY_RUN:
            print(msg)
        else:
            discord("POST", f"/channels/{CHANNEL_ID}/messages", {
                "content": msg,
                "allowed_mentions": {"parse": ["everyone", "roles"]},
            })
        sent[key] = now.isoformat()

    cutoff = now - timedelta(days=30)
    sent = {k: v for k, v in sent.items() if datetime.fromisoformat(v) > cutoff}
    SENT_FILE.write_text(json.dumps(sent, indent=2) + "\n")


if __name__ == "__main__":
    main()
