"""
Find email addresses for businesses by:
1. Googling their name + location
2. Visiting the top results (their site, Facebook, etc.)
3. Extracting emails via regex
"""

import csv
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

JUNK_EMAIL_DOMAINS = {
    "sentry.io", "example.com", "wixpress.com", "squarespace.com",
    "shopify.com", "wordpress.com", "googletagmanager.com", "schemas.org",
    "w3.org", "amazonaws.com", "cloudflare.com", "domain.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 8) -> str | None:
    """Fetch a URL and return text, or None on error."""
    try:
        resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"GET {url} failed: {e}")
        return None


def _extract_emails(html: str) -> list[str]:
    """Pull all email-looking strings from HTML, filtering junk."""
    # Also check plaintext version
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")
    raw = set(EMAIL_RE.findall(html)) | set(EMAIL_RE.findall(text))
    clean = []
    for email in raw:
        domain = email.split("@")[-1].lower()
        if domain in JUNK_EMAIL_DOMAINS:
            continue
        if any(domain.endswith(j) for j in JUNK_EMAIL_DOMAINS):
            continue
        if len(email) > 80:
            continue
        clean.append(email.lower())
    return clean


def _google_search_urls(query: str, num: int = 5) -> list[str]:
    """
    Scrape Google for the top `num` organic result URLs for a query.
    Returns a list of URLs (may be empty if Google blocks us).
    """
    search_url = "https://www.google.com/search"
    params = {"q": query, "num": num, "hl": "en"}
    html = _get(search_url + "?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()))
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"]
        # Google wraps results in /url?q=...
        if href.startswith("/url?q="):
            url = href[7:].split("&")[0]
            parsed = urlparse(url)
            if parsed.scheme in ("http", "https") and "google." not in parsed.netloc:
                urls.append(url)
        elif href.startswith("http") and "google." not in urlparse(href).netloc:
            if href not in urls:
                urls.append(href)
        if len(urls) >= num:
            break
    return urls


def _facebook_email(fb_url: str) -> list[str]:
    """Try to get emails from a Facebook page (mobile version is more scrapeable)."""
    # Convert to mobile URL
    parsed = urlparse(fb_url)
    mobile_url = fb_url.replace("www.facebook.com", "m.facebook.com")
    html = _get(mobile_url)
    if html:
        return _extract_emails(html)
    return []


def _contact_page_emails(base_url: str) -> list[str]:
    """Try common contact page paths on a given base URL."""
    common_paths = ["/contact", "/contact-us", "/about", "/about-us", "/enquiry", "/reach-us"]
    emails = []
    for path in common_paths:
        url = urljoin(base_url, path)
        html = _get(url)
        if html:
            found = _extract_emails(html)
            emails.extend(found)
            if emails:
                break
        time.sleep(0.5)
    return emails


def find_email_for_business(business: dict) -> str:
    """
    Search for an email address for a single business.
    Returns the best email found, or empty string.
    """
    name = business.get("name", "")
    city = business.get("city", "")
    phone = business.get("phone", "")

    query = f'"{name}" {city} contact email'
    logger.info(f"Searching for email: {name}")

    # 1. Google search
    urls = _google_search_urls(query, num=5)
    time.sleep(random.uniform(2, 4))  # be polite to Google

    all_emails: list[str] = []

    for url in urls:
        parsed = urlparse(url)

        # Handle Facebook separately
        if "facebook.com" in parsed.netloc:
            found = _facebook_email(url)
        else:
            html = _get(url)
            found = _extract_emails(html) if html else []

            # If the page itself had no email, try its /contact subpage
            if not found and parsed.path in ("", "/", ""):
                found = _contact_page_emails(url)

        all_emails.extend(found)
        if all_emails:
            break
        time.sleep(random.uniform(1, 2))

    # 2. If still nothing, try Googling phone number to find their site
    if not all_emails and phone:
        phone_query = f'"{phone}" contact email'
        urls2 = _google_search_urls(phone_query, num=3)
        time.sleep(random.uniform(2, 3))
        for url in urls2:
            html = _get(url)
            if html:
                all_emails.extend(_extract_emails(html))
            if all_emails:
                break
            time.sleep(1)

    # Deduplicate and prefer non-generic addresses
    seen = []
    generic_prefixes = ("info@", "hello@", "admin@", "contact@", "support@", "mail@")
    specific = [e for e in all_emails if not any(e.startswith(p) for p in generic_prefixes)]
    generic = [e for e in all_emails if any(e.startswith(p) for p in generic_prefixes)]

    for e in specific + generic:
        if e not in seen:
            seen.append(e)

    result = seen[0] if seen else ""
    if result:
        logger.info(f"Found email for {name}: {result}")
    else:
        logger.info(f"No email found for {name}")
    return result


# ---------------------------------------------------------------------------
# CSV update
# ---------------------------------------------------------------------------

def update_tracker_emails(csv_path: str = "tracker.csv") -> int:
    """
    Scan tracker.csv for rows with no email, search for one, and update in-place.
    Returns count of emails newly found.
    """
    path = Path(csv_path)
    if not path.exists():
        logger.warning(f"Tracker not found: {csv_path}")
        return 0

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    fieldnames = rows[0].keys() if rows else []

    found_count = 0
    for row in rows:
        if row.get("email"):
            continue  # already have one

        business = {
            "name": row["business_name"],
            "city": "Newcastle NSW",
            "phone": "",
        }
        email = find_email_for_business(business)
        if email:
            row["email"] = email
            found_count += 1

        # Save after each attempt so progress isn't lost
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(fieldnames))
            writer.writeheader()
            writer.writerows(rows)

        time.sleep(random.uniform(1, 2))

    logger.info(f"Email search complete — found {found_count} new emails")
    return found_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    count = update_tracker_emails()
    print(f"\nDone — {count} emails found and saved to tracker.csv")
