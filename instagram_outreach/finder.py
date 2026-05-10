"""Account discovery and qualification using raw Instagram API responses."""

import random
import time
from datetime import datetime, timezone
from typing import Generator

from session import IGClient

DM_TEMPLATE = """Hey {name} \U0001f44b

My name's Liam — I run a small AI marketing agency based in Newcastle.

I came across your page and honestly think there's a real opportunity to grow your brand on TikTok and Instagram without spending a fortune.

I use AI tools to create scroll-stopping content and ads faster and cheaper than any traditional agency. No lock-in contracts.

I'd love to put together 3 free sample posts for your business so you can see exactly what I'd do before committing to anything.

Keen to chat? Just reply here \U0001f91c

Liam
@lw_marketing15"""


class AccountFinder:
    def __init__(self, client: IGClient, config: dict):
        self.client = client
        self.cfg = config["targeting"]

    # ---------------------------------------------------------------- API calls

    def _user_info(self, user_id: str) -> dict | None:
        try:
            resp = self.client.get(f"/users/{user_id}/info/")
            if resp.status_code == 200:
                return resp.json().get("user")
        except Exception:
            pass
        return None

    def _user_media(self, user_id: str, count: int = 5) -> list[dict]:
        try:
            resp = self.client.get(f"/feed/user/{user_id}/", params={"count": count})
            if resp.status_code == 200:
                return resp.json().get("items", [])
        except Exception:
            pass
        return []

    # ----------------------------------------------------------- qualification

    def _days_since_last_post(self, user_id: str) -> float | None:
        items = self._user_media(user_id, count=1)
        if not items:
            return None
        ts = items[0].get("taken_at")
        if not ts:
            return None
        last = datetime.fromtimestamp(ts, tz=timezone.utc)
        return (datetime.now(timezone.utc) - last).days

    def _engagement_rate(self, user: dict, user_id: str) -> float:
        followers = user.get("follower_count", 0)
        if not followers:
            return 0.0
        items = self._user_media(user_id, count=5)
        if not items:
            return 0.0
        total = sum(
            (m.get("like_count") or 0) + (m.get("comment_count") or 0)
            for m in items
        )
        return (total / len(items)) / followers

    def _qualifies(self, user: dict) -> tuple[bool, str]:
        followers = user.get("follower_count", 0)
        if followers > self.cfg["max_followers"]:
            return False, f"too many followers ({followers})"
        if user.get("is_private"):
            return False, "private account"

        uid = str(user["pk"])
        days = self._days_since_last_post(uid)
        if days is None:
            return False, "no posts found"
        if days < self.cfg["min_days_inactive"]:
            return False, f"posted {days}d ago (too recent)"

        engagement = self._engagement_rate(user, uid)
        if engagement > self.cfg["max_engagement_rate"]:
            return False, f"engagement too high ({engagement:.2%})"

        return True, f"inactive {days}d, engagement {engagement:.2%}"

    # --------------------------------------------------------- hashtag search

    def _fetch_hashtag_items(self, tag: str) -> list[dict]:
        """Fetch recent media items for a hashtag. Tries sections endpoint first."""
        # Try the sections endpoint (newer API)
        try:
            resp = self.client.post(
                f"/tags/{tag}/sections/",
                data={"tab": "recent", "count": "50"},
            )
            if resp.status_code == 200:
                body = resp.json()
                items = []
                for section in body.get("sections", []):
                    layout = section.get("layout_content", {})
                    for val in layout.values():
                        if isinstance(val, list):
                            for entry in val:
                                media = entry.get("media") or entry
                                if media.get("user"):
                                    items.append(media)
                if items:
                    return items
        except Exception:
            pass

        # Fall back to feed/tag endpoint
        try:
            resp = self.client.get(f"/feed/tag/{tag}/", params={"count": "50"})
            if resp.status_code == 200:
                body = resp.json()
                return body.get("items", [])
        except Exception:
            pass

        return []

    def find_via_hashtags(
        self, extra_hashtags: list[str] | None = None
    ) -> Generator[tuple[dict, str, bool], None, None]:
        hashtags = self.cfg["hashtags"] + (extra_hashtags or [])
        seen: set[str] = set()

        for tag in hashtags:
            print(f"  Searching #{tag}...")
            items = self._fetch_hashtag_items(tag)
            if not items:
                print(f"  No results for #{tag}")
                continue

            for media in items:
                user_basic = media.get("user") or {}
                uid = str(user_basic.get("pk", ""))
                if not uid or uid in seen:
                    continue
                seen.add(uid)

                time.sleep(random.uniform(1, 3))

                user = self._user_info(uid)
                if not user:
                    continue

                qualifies, reason = self._qualifies(user)
                yield user, reason, qualifies
