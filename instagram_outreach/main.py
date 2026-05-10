#!/usr/bin/env python3
"""Instagram outreach tool — finds and DMs target accounts."""

import argparse
import os
import sys
from datetime import datetime

import yaml
from dotenv import load_dotenv
from instagrapi import Client

from finder import AccountFinder
from messenger import Messenger
from tracker import OutreachTracker


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def login(config: dict) -> Client:
    load_dotenv()
    username = os.getenv("IG_USERNAME") or config["instagram"].get("username")
    password = os.getenv("IG_PASSWORD") or config["instagram"].get("password")
    if not username or not password:
        sys.exit("Error: set IG_USERNAME and IG_PASSWORD in your .env file.")

    client = Client()
    client.delay_range = [1, 3]
    session_file = f"session_{username}.json"
    if os.path.exists(session_file):
        try:
            client.load_settings(session_file)
            client.login(username, password)
            print(f"Logged in as @{username} (reused session)")
            return client
        except Exception:
            pass

    print(f"Logging in as @{username}...")
    client.login(username, password)
    client.dump_settings(session_file)
    print("Login successful.")
    return client


def run(args):
    config = load_config(args.config)
    daily_limit = args.limit or config["outreach"]["daily_limit"]

    tracking_cfg = config["tracking"]
    tracker = OutreachTracker(tracking_cfg["csv_file"], tracking_cfg["sent_file"])

    already_sent_today = tracker.sent_today()
    remaining = daily_limit - already_sent_today
    if remaining <= 0:
        print(f"Daily limit of {daily_limit} DMs already reached. Try again tomorrow.")
        return

    print(f"Daily limit: {daily_limit} | Already sent today: {already_sent_today} | Remaining: {remaining}")

    client = login(config)
    finder = AccountFinder(client, config)
    messenger = Messenger(client, config)

    extra_tags = []
    if args.niche:
        extra_tags.append(args.niche.lower().replace(" ", ""))
    if args.location:
        slug = args.location.lower().replace(" ", "").replace(",", "")
        extra_tags.append(slug)

    sent_this_run = 0
    print(f"\nStarting outreach — niche: {args.niche!r}, location: {args.location!r}")
    print("-" * 60)

    for user, reason, qualifies in finder.find_via_hashtags(extra_tags):
        if sent_this_run >= remaining:
            print(f"\nReached daily limit ({daily_limit}). Stopping.")
            break

        if tracker.already_messaged(user.username):
            print(f"  Skip @{user.username} — already messaged")
            continue

        if not qualifies:
            print(f"  Skip @{user.username} — {reason}")
            tracker.log_skipped(user.username, reason)
            continue

        print(f"  Target: @{user.username} ({user.follower_count} followers) — {reason}")

        last_posts = None
        try:
            medias = client.user_medias(user.pk, amount=1)
            last_posts = medias[0].taken_at.strftime("%Y-%m-%d") if medias else "never"
        except Exception:
            last_posts = "unknown"

        success = messenger.send_dm(user, dry_run=args.dry_run)
        if success:
            tracker.log_sent(
                username=user.username,
                full_name=user.full_name or "",
                followers=user.follower_count,
                following=user.following_count,
                last_post_date=last_posts,
                notes=reason,
            )
            sent_this_run += 1
            print(f"  Sent DM #{sent_this_run} to @{user.username}")
            if sent_this_run < remaining:
                messenger.wait_between_dms()

    print(f"\nDone. Sent {sent_this_run} DMs this run.")
    print(f"Log saved to: {tracking_cfg['csv_file']}")


def main():
    parser = argparse.ArgumentParser(description="Instagram outreach tool")
    parser.add_argument("--niche", default="skincare", help="Target niche (e.g. skincare)")
    parser.add_argument("--location", default="Newcastle NSW", help="Target location")
    parser.add_argument("--limit", type=int, default=None, help="Override daily DM limit")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Find targets but don't send DMs")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
