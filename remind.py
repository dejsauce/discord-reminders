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
START_REMINDER = os.environ.get("START_REMINDER", "on") == "on"
MENTION = os.environ.get("MENTION", "@everyone")
DRY_RUN = os.environ.get("DRY_RUN") == "1"

SENT_FILE = Path(__file__).with_name("sent.json")
SCHEDULED, ACTIVE = 1, 2
START_EARLY = timedelta(minutes=5)   # "starting now" can go out up to 5 min early
START_GRACE = timedelta(minutes=30)  # ...and is skipped if the bot is 30+ min late


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


def build_message(event, start, starting_now):
    ts = int(start.timestamp())
    if starting_now:
        lines = [f"{MENTION} 🚨 **{event['name']}** is starting now!"]
    else:
        lines = [
            f"{MENTION} ⏰ **Reminder: {event['name']}** is tonight!",
            f"🕒 Starts <t:{ts}:t> (<t:{ts}:R>)",
        ]
    loc = where(event)
    if loc:
        lines.append(f"📍 {loc}")
    lines.append(f"🔗 https://discord.com/events/{GUILD_ID}/{event['id']}")
    return "\n".join(lines)


def send(event, start, starting_now):
    msg = build_message(event, start, starting_now)
    kind = "start" if starting_now else "early"
    print(f"Sending {kind} reminder for '{event['name']}' (starts {start.isoformat()})")
    if DRY_RUN:
        print(msg)
    else:
        discord("POST", f"/channels/{CHANNEL_ID}/messages", {
            "content": msg,
            "allowed_mentions": {"parse": ["everyone", "roles"]},
        })


def main():
    now = datetime.now(timezone.utc)
    sent = load_sent()
    events = discord("GET", f"/guilds/{GUILD_ID}/scheduled-events")

    for event in events:
        status = event.get("status")
        if status not in (SCHEDULED, ACTIVE):
            continue
        start = datetime.fromisoformat(event["scheduled_start_time"].replace("Z", "+00:00"))
        key = f"{event['id']}@{event['scheduled_start_time']}"

        # Early reminder: from LEAD_MINUTES before until shortly before the start
        early_key = key
        if (status == SCHEDULED and early_key not in sent
                and start - timedelta(minutes=LEAD_MINUTES) <= now < start - START_EARLY):
            send(event, start, starting_now=False)
            sent[early_key] = now.isoformat()

        # Start reminder: right around the start time
        start_key = key + "@start"
        if (START_REMINDER and start_key not in sent
                and start - START_EARLY <= now < start + START_GRACE):
            send(event, start, starting_now=True)
            sent[start_key] = now.isoformat()

    cutoff = now - timedelta(days=30)
    sent = {k: v for k, v in sent.items() if datetime.fromisoformat(v) > cutoff}
    SENT_FILE.write_text(json.dumps(sent, indent=2) + "\n")


if __name__ == "__main__":
    main()
