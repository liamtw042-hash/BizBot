#!/usr/bin/env python3
"""Instagram outreach tool — finds and DMs target accounts via raw HTTP."""

import argparse
import os
import sys

import yaml
from dotenv import load_dotenv

from session import IGClient
from finder import AccountFinder
from messenger import Messenger
from tracker import OutreachTracker


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def authenticate(config: dict) -> IGClient:
    load_dotenv()
    username = os.getenv("IG_USERNAME") or config["instagram"].get("username", "")
    password = os.getenv("IG_PASSWORD") or config["instagram"].get("password", "")
    if not username or not password:
        sys.exit("Error: set IG_USERNAME and IG_PASSWORD in your .env file.")

    session_file = f"session_{username}.json"
    client = IGClient(session_file=session_file)

    if client.load_session():
        print(f"Loaded saved session for @{client.username}...")
        if client.verify_session():
            print("Session valid, skipping login.")
            return client
        print("Session expired, logging in again...")

    print(f"Logging in as @{username}...")
    client.login(username, password)
    print("Login successful.")
    return client


def last_post_date(client: IGClient, user: dict) -> str:
    try:
        from finder import AccountFinder
        uid = str(user["pk"])
        resp = client.get(f"/feed/user/{uid}/", params={"count": 1})
        items = resp.json().get("items", [])
        if items:
            from datetime import datetime, timezone
            ts = items[0].get("taken_at")
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return "unknown"


def run(args):
    config = load_config(args.config)
    daily_limit = args.limit or config["outreach"]["daily_limit"]

    tcfg = config["tracking"]
    tracker = OutreachTracker(tcfg["csv_file"], tcfg["sent_file"])

    already_today = tracker.sent_today()
    remaining = daily_limit - already_today
    if remaining <= 0:
        print(f"Daily limit of {daily_limit} DMs already reached. Try again tomorrow.")
        return
    print(f"Daily limit: {daily_limit} | Sent today: {already_today} | Remaining: {remaining}")

    client = authenticate(config)
    finder = AccountFinder(client, config)
    messenger = Messenger(client, config)

    extra_tags = []
    if args.niche:
        extra_tags.append(args.niche.lower().replace(" ", ""))
    if args.location:
        extra_tags.append(args.location.lower().replace(" ", "").replace(",", ""))

    sent_this_run = 0
    print(f"\nStarting outreach — niche: {args.niche!r}, location: {args.location!r}")
    print("-" * 60)

    for user, reason, qualifies in finder.find_via_hashtags(extra_tags):
        if sent_this_run >= remaining:
            print(f"\nReached daily limit ({daily_limit}). Stopping.")
            break

        username = user.get("username", "")

        if tracker.already_messaged(username):
            print(f"  Skip @{username} — already messaged")
            continue

        if not qualifies:
            print(f"  Skip @{username} — {reason}")
            tracker.log_skipped(username, reason)
            continue

        followers = user.get("follower_count", "?")
        print(f"  Target: @{username} ({followers} followers) — {reason}")

        last_date = last_post_date(client, user)

        success = messenger.send_dm(user, dry_run=args.dry_run)
        if success:
            tracker.log_sent(user, last_post_date=last_date, notes=reason)
            sent_this_run += 1
            print(f"  Sent DM #{sent_this_run} to @{username}")
            if sent_this_run < remaining:
                messenger.wait_between_dms()

    print(f"\nDone. Sent {sent_this_run} DMs this run.")
    print(f"Log saved to: {tcfg['csv_file']}")


def main():
    parser = argparse.ArgumentParser(description="Instagram outreach tool")
    parser.add_argument("--niche", default="skincare")
    parser.add_argument("--location", default="Newcastle NSW")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Find targets but don't send DMs")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
