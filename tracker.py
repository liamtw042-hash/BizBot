"""Track processed businesses in a CSV file."""

import csv
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

FIELDNAMES = ["business_name", "place_id", "email", "website_link", "website_file", "date_sent", "replied"]
DEFAULT_CSV = "tracker.csv"


def _load(csv_path: str) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save(rows: list[dict], csv_path: str) -> None:
    path = Path(csv_path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def already_processed(place_id: str, csv_path: str = DEFAULT_CSV) -> bool:
    """Return True if we have already processed this business."""
    rows = _load(csv_path)
    return any(r["place_id"] == place_id for r in rows)


def record_business(
    business: dict,
    website_file: str,
    website_url: str,
    email_sent: bool,
    csv_path: str = DEFAULT_CSV,
) -> None:
    """Append a business record to the tracker CSV."""
    rows = _load(csv_path)
    rows.append({
        "business_name": business.get("name", ""),
        "place_id": business.get("place_id", ""),
        "email": business.get("email", ""),
        "website_link": website_url if email_sent else "",
        "website_file": website_file,
        "date_sent": date.today().isoformat() if email_sent else "",
        "replied": "no",
    })
    _save(rows, csv_path)
    logger.info(f"Recorded {business['name']} in {csv_path}")


def mark_replied(business_name: str, csv_path: str = DEFAULT_CSV) -> bool:
    """Mark a business as having replied. Returns True if found."""
    rows = _load(csv_path)
    found = False
    for row in rows:
        if row["business_name"].lower() == business_name.lower():
            row["replied"] = "yes"
            found = True
    if found:
        _save(rows, csv_path)
    return found


def get_stats(csv_path: str = DEFAULT_CSV) -> dict:
    """Return a summary dict of tracker stats."""
    rows = _load(csv_path)
    total = len(rows)
    sent = sum(1 for r in rows if r.get("date_sent"))
    replied = sum(1 for r in rows if r.get("replied") == "yes")
    return {"total": total, "emails_sent": sent, "replied": replied}
