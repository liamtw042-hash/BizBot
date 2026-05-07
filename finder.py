"""Find local businesses missing a website using Google Maps Places API."""

import requests
import time
import logging

logger = logging.getLogger(__name__)

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode_city(city: str, api_key: str) -> tuple[float, float]:
    """Convert a city name to lat/lng coordinates."""
    resp = requests.get(GEOCODE_URL, params={"address": city, "key": api_key}, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Could not geocode city: {city}")
    loc = results[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def _has_real_website(place_details: dict) -> bool:
    """Return True if the business appears to have a real standalone website."""
    website = place_details.get("website", "")
    if not website:
        return False
    skip_domains = (
        "facebook.com", "instagram.com", "twitter.com", "yelp.com",
        "tripadvisor.com", "yellowpages.com", "zomato.com", "ubereats.com",
        "doordash.com", "google.com", "maps.google.com",
    )
    return not any(d in website.lower() for d in skip_domains)


def get_place_details(place_id: str, api_key: str) -> dict:
    """Fetch full details for a place."""
    fields = "name,formatted_address,formatted_phone_number,website,email,opening_hours,types,rating"
    resp = requests.get(
        PLACES_DETAILS_URL,
        params={"place_id": place_id, "fields": fields, "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def search_businesses(city: str, category: str, api_key: str, radius: int = 5000, max_results: int = 20) -> list[dict]:
    """
    Search for businesses in a city of a given category.
    Returns a list of businesses that appear to lack a real website.
    """
    lat, lng = geocode_city(city, api_key)
    logger.info(f"Searching '{category}' near {city} ({lat}, {lng})")

    businesses = []
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": category,
        "key": api_key,
    }
    next_page_token = None

    while len(businesses) < max_results:
        if next_page_token:
            params = {"pagetoken": next_page_token, "key": api_key}
            time.sleep(2)  # Google requires a short delay before using page tokens

        resp = requests.get(PLACES_NEARBY_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Places API returned status: {data.get('status')}")
            break

        for place in data.get("results", []):
            if len(businesses) >= max_results:
                break

            place_id = place["place_id"]
            try:
                details = get_place_details(place_id, api_key)
            except Exception as e:
                logger.warning(f"Could not fetch details for {place.get('name')}: {e}")
                continue

            if _has_real_website(details):
                logger.debug(f"Skipping {details.get('name')} — has website")
                continue

            business = {
                "place_id": place_id,
                "name": details.get("name", place.get("name", "")),
                "address": details.get("formatted_address", ""),
                "phone": details.get("formatted_phone_number", ""),
                "email": details.get("email", ""),
                "website": details.get("website", ""),
                "category": category,
                "city": city,
                "rating": details.get("rating", ""),
            }
            businesses.append(business)
            logger.info(f"Found: {business['name']} — no website")

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

    return businesses


def find_businesses(config: dict) -> list[dict]:
    """Main entry point: search all configured categories and return combined results."""
    api_key = config["google_maps_api_key"]
    city = config.get("target_city", config.get("default_city", ""))
    radius = config.get("search_radius_meters", 5000)
    max_results = config.get("max_results_per_search", 20)
    categories = config.get("search_categories", ["restaurant"])

    all_businesses = []
    seen_ids = set()

    for category in categories:
        try:
            results = search_businesses(city, category, api_key, radius, max_results)
            for b in results:
                if b["place_id"] not in seen_ids:
                    seen_ids.add(b["place_id"])
                    all_businesses.append(b)
        except Exception as e:
            logger.error(f"Error searching category '{category}': {e}")

    logger.info(f"Total businesses found without websites: {len(all_businesses)}")
    return all_businesses
