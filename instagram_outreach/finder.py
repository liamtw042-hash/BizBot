import time
import random
from datetime import datetime, timezone
from typing import Generator
from instagrapi import Client
from instagrapi.types import User


DM_TEMPLATE = """Hey {name} 👋

My name's Liam — I run a small AI marketing agency based in Newcastle.

I came across your page and honestly think there's a real opportunity to grow your brand on TikTok and Instagram without spending a fortune.

I use AI tools to create scroll-stopping content and ads faster and cheaper than any traditional agency. No lock-in contracts.

I'd love to put together 3 free sample posts for your business so you can see exactly what I'd do before committing to anything.

Keen to chat? Just reply here 🙌

Liam
@lw_marketing15"""


class AccountFinder:
    def __init__(self, client: Client, config: dict):
        self.client = client
        self.cfg = config["targeting"]

    def _days_since_last_post(self, user_id: int) -> float | None:
        try:
            medias = self.client.user_medias(user_id, amount=1)
            if not medias:
                return None
            last_post = medias[0].taken_at
            if last_post.tzinfo is None:
                last_post = last_post.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - last_post
            return delta.days
        except Exception:
            return None

    def _engagement_rate(self, user: User) -> float:
        if not user.follower_count or user.follower_count == 0:
            return 0.0
        try:
            medias = self.client.user_medias(user.pk, amount=5)
            if not medias:
                return 0.0
            total_likes = sum(m.like_count or 0 for m in medias)
            total_comments = sum(m.comment_count or 0 for m in medias)
            avg = (total_likes + total_comments) / len(medias)
            return avg / user.follower_count
        except Exception:
            return 0.0

    def _qualifies(self, user: User) -> tuple[bool, str]:
        if user.follower_count > self.cfg["max_followers"]:
            return False, f"too many followers ({user.follower_count})"

        if user.is_private:
            return False, "private account"

        if user.is_business is False and user.account_type not in (None, 1, 2):
            pass  # keep personal accounts — they could be small businesses

        days_inactive = self._days_since_last_post(user.pk)
        if days_inactive is None:
            return False, "no posts found"
        if days_inactive < self.cfg["min_days_inactive"]:
            return False, f"posted {days_inactive}d ago (too recent)"

        engagement = self._engagement_rate(user)
        if engagement > self.cfg["max_engagement_rate"]:
            return False, f"engagement too high ({engagement:.2%})"

        return True, f"inactive {days_inactive}d, engagement {engagement:.2%}"

    def find_via_hashtags(self, extra_hashtags: list[str] | None = None) -> Generator[tuple[User, str], None, None]:
        hashtags = self.cfg["hashtags"] + (extra_hashtags or [])
        seen = set()
        for tag in hashtags:
            print(f"  Searching #{tag}...")
            try:
                medias = self.client.hashtag_medias_recent(tag, amount=50)
            except Exception as e:
                print(f"  Failed to fetch #{tag}: {e}")
                continue

            for media in medias:
                uid = media.user.pk
                if uid in seen:
                    continue
                seen.add(uid)
                time.sleep(random.uniform(1, 3))
                try:
                    user = self.client.user_info(uid)
                except Exception:
                    continue
                qualifies, reason = self._qualifies(user)
                yield user, reason, qualifies
