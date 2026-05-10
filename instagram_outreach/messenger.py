"""DM sending against Instagram's direct_v2 API."""

import random
import time
import uuid

from finder import DM_TEMPLATE
from session import IGClient


class Messenger:
    def __init__(self, client: IGClient, config: dict):
        self.client = client
        self.delay_min = config["outreach"]["delay_min_seconds"]
        self.delay_max = config["outreach"]["delay_max_seconds"]

    def _build_message(self, user: dict) -> str:
        full_name = (user.get("full_name") or "").strip()
        name = full_name.split()[0] if full_name else user.get("username", "there")
        return DM_TEMPLATE.format(name=name)

    def send_dm(self, user: dict, dry_run: bool = False) -> bool:
        message = self._build_message(user)
        if dry_run:
            print(f"  [DRY RUN] Would DM @{user.get('username')}:\n{message[:80]}...")
            return True

        uid = str(user["pk"])
        try:
            resp = self.client.post(
                "/direct_v2/threads/broadcast/text/",
                data={
                    "recipient_users": f"[[{uid}]]",
                    "client_context": uuid.uuid4().hex,
                    "text": message,
                    "device_id": self.client.device_id,
                },
            )
            body = resp.json()
            if body.get("status") == "ok":
                return True
            print(f"  DM rejected: {body.get('message', 'unknown error')}")
            return False
        except Exception as e:
            print(f"  DM error: {e}")
            return False

    def wait_between_dms(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        print(f"  Waiting {delay:.0f}s before next DM...")
        time.sleep(delay)
