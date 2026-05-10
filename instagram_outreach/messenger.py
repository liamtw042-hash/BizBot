import time
import random
from instagrapi import Client
from instagrapi.types import User
from finder import DM_TEMPLATE


class Messenger:
    def __init__(self, client: Client, config: dict):
        self.client = client
        self.delay_min = config["outreach"]["delay_min_seconds"]
        self.delay_max = config["outreach"]["delay_max_seconds"]

    def _build_message(self, user: User) -> str:
        name = user.full_name.split()[0] if user.full_name else user.username
        return DM_TEMPLATE.format(name=name)

    def send_dm(self, user: User, dry_run: bool = False) -> bool:
        message = self._build_message(user)
        if dry_run:
            print(f"  [DRY RUN] Would DM @{user.username}:\n{message[:80]}...")
            return True
        try:
            thread = self.client.direct_send(message, user_ids=[user.pk])
            return thread is not None
        except Exception as e:
            print(f"  Failed to DM @{user.username}: {e}")
            return False

    def wait_between_dms(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        print(f"  Waiting {delay:.0f}s before next DM...")
        time.sleep(delay)
