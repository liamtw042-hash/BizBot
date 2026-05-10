import csv
import os
from datetime import datetime


class OutreachTracker:
    def __init__(self, csv_file: str, sent_file: str):
        self.csv_file = csv_file
        self.sent_file = sent_file
        self._ensure_csv()
        self.sent_accounts = self._load_sent()

    def _ensure_csv(self):
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "username", "full_name", "followers", "following",
                    "last_post_date", "dm_sent_at", "status", "notes",
                ])

    def _load_sent(self) -> set:
        if not os.path.exists(self.sent_file):
            return set()
        with open(self.sent_file) as f:
            return {line.strip() for line in f if line.strip()}

    def already_messaged(self, username: str) -> bool:
        return username in self.sent_accounts

    def log_sent(self, user: dict, last_post_date: str, notes: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        username = user.get("username", "")
        with open(self.csv_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                username,
                user.get("full_name", ""),
                user.get("follower_count", ""),
                user.get("following_count", ""),
                last_post_date,
                now,
                "sent",
                notes,
            ])
        with open(self.sent_file, "a") as f:
            f.write(username + "\n")
        self.sent_accounts.add(username)

    def log_skipped(self, username: str, reason: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.csv_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([username, "", "", "", "", now, "skipped", reason])

    def sent_today(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        count = 0
        if not os.path.exists(self.csv_file):
            return 0
        with open(self.csv_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"] == "sent" and row["dm_sent_at"].startswith(today):
                    count += 1
        return count
