#!/usr/bin/env python3
"""BizBot — find businesses without websites, build them one, and send a cold email."""

import argparse
import logging
import sys
from pathlib import Path

import yaml

import finder
import generator
import emailer
import tracker
import hosting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_config(config: dict) -> None:
    required = ["google_maps_api_key", "claude_api_key"]
    missing = [k for k in required if not config.get(k) or config[k].startswith("YOUR_")]
    if missing:
        logger.error(f"Please set the following keys in config.yaml: {', '.join(missing)}")
        sys.exit(1)


def run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    validate_config(config)

    # Override city if provided on CLI
    if args.city:
        config["target_city"] = args.city
    elif not config.get("target_city") and not config.get("default_city"):
        logger.error("No city specified. Use --city or set default_city in config.yaml")
        sys.exit(1)

    city = config.get("target_city") or config.get("default_city")
    logger.info(f"=== BizBot starting for: {city} ===")

    # --- Step 1: Find businesses ---
    if args.skip_find:
        logger.info("Skipping business discovery (--skip-find)")
        businesses = []
    else:
        logger.info("Searching for businesses without websites...")
        businesses = finder.find_businesses(config)
        if not businesses:
            logger.warning("No businesses found — check your Google Maps API key and city name")
            return

    # --- Set up hosting ---
    base_url = ""
    if config.get("hosting_mode") == "netlify":
        logger.info("Will deploy to Netlify after generating all websites")
    else:
        port = config.get("local_server_port", 8080)
        base_url = hosting.start_local_server(directory="websites", port=port)
        logger.info(f"Local server running at {base_url}")

    # --- Process each business ---
    processed = 0
    for business in businesses:
        name = business.get("name", "Unknown")
        place_id = business.get("place_id", "")

        if tracker.already_processed(place_id):
            logger.info(f"Skipping {name} — already processed")
            continue

        logger.info(f"\n--- Processing: {name} ---")

        # Step 2: Generate website
        try:
            logger.info(f"Generating website for {name}...")
            html = generator.generate_website(business, config)
            html_path = generator.save_website(business, html, output_dir="websites")
        except Exception as e:
            logger.error(f"Failed to generate website for {name}: {e}")
            continue

        # Determine website URL
        if config.get("hosting_mode") == "netlify":
            website_url = ""  # Will be filled after bulk deploy
        else:
            website_url = hosting.local_url_for(base_url, html_path)

        # Step 3: Send email (if email available and not dry-run)
        email_sent = False
        if args.dry_run:
            logger.info(f"[DRY RUN] Would send email to {name} at {business.get('email', 'no email')}")
        elif not business.get("email"):
            logger.info(f"No email address for {name} — skipping email")
        else:
            try:
                email_sent = emailer.send_email(business, website_url, config)
            except Exception as e:
                logger.error(f"Email failed for {name}: {e}")

        # Step 4: Track
        tracker.record_business(
            business=business,
            website_file=html_path,
            website_url=website_url,
            email_sent=email_sent,
        )

        processed += 1
        logger.info(f"Done: {name} → {html_path}")

    # Bulk Netlify deploy after all websites generated
    if config.get("hosting_mode") == "netlify" and processed > 0:
        try:
            logger.info("Deploying to Netlify...")
            deploy_url = hosting.deploy_to_netlify()
            logger.info(f"Netlify deploy URL: {deploy_url}")
        except RuntimeError as e:
            logger.error(str(e))

    # Summary
    stats = tracker.get_stats()
    logger.info(
        f"\n=== Done === processed {processed} new businesses | "
        f"total tracked: {stats['total']} | "
        f"emails sent: {stats['emails_sent']} | "
        f"replied: {stats['replied']}"
    )

    if config.get("hosting_mode") != "netlify" and processed > 0:
        logger.info(f"\nWebsites available at {base_url}")
        logger.info("Press Ctrl+C to stop the local server")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            hosting.stop_local_server()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BizBot — find local businesses without websites and build them one"
    )
    parser.add_argument("--city", help='Target city/suburb (e.g. "Newcastle NSW")')
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate websites but do not send emails",
    )
    parser.add_argument(
        "--skip-find",
        action="store_true",
        help="Skip business discovery (useful for re-running generation on existing data)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print tracker stats and exit",
    )
    args = parser.parse_args()

    if args.stats:
        stats = tracker.get_stats()
        print(f"Total tracked: {stats['total']}")
        print(f"Emails sent:   {stats['emails_sent']}")
        print(f"Replied:       {stats['replied']}")
        return

    run(args)


if __name__ == "__main__":
    main()
