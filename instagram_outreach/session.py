"""Raw HTTP session against Instagram's private mobile API."""

import json
import os
import time
import uuid
from pathlib import Path

import requests

_APP_ID = "936619743392459"
_USER_AGENT = (
    "Instagram 275.0.0.27.98 Android "
    "(33/13; 420dpi; 1080x2340; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)"
)


class IGClient:
    API = "https://i.instagram.com/api/v1"

    def __init__(self, session_file: str | None = None):
        self.session = requests.Session()
        self.session_file = session_file
        self.device_id = "android-" + uuid.uuid4().hex[:16]
        self.user_id: str | None = None
        self.username: str | None = None

        self.session.headers.update({
            "User-Agent": _USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Accept-Encoding": "gzip, deflate",
            "X-IG-App-ID": _APP_ID,
            "X-IG-Capabilities": "3brTvw==",
            "X-IG-Connection-Type": "WIFI",
            "X-FB-HTTP-Engine": "Liger",
        })

    # ------------------------------------------------------------------ auth

    def _csrf(self) -> str:
        return self.session.cookies.get("csrftoken", "")

    def load_session(self) -> bool:
        if not self.session_file or not os.path.exists(self.session_file):
            return False
        try:
            data = json.loads(Path(self.session_file).read_text())
            self.session.cookies.update(data["cookies"])
            self.user_id = data["user_id"]
            self.username = data["username"]
            return True
        except Exception:
            return False

    def save_session(self):
        if not self.session_file:
            return
        Path(self.session_file).write_text(json.dumps({
            "cookies": dict(self.session.cookies),
            "user_id": self.user_id,
            "username": self.username,
        }))

    def verify_session(self) -> bool:
        """Check if the saved session is still valid."""
        try:
            resp = self.get("/accounts/current_user/", params={"edit": "true"})
            return resp.status_code == 200 and resp.json().get("status") == "ok"
        except Exception:
            return False

    def login(self, username: str, password: str) -> bool:
        # Seed CSRF cookie
        self.session.get(
            f"{self.API}/si/fetch_headers/",
            params={"challenge_type": "signup"},
        )
        ts = int(time.time())
        resp = self.session.post(
            f"{self.API}/accounts/login/",
            data={
                "username": username,
                "enc_password": f"#PWD_INSTAGRAM:0:{ts}:{password}",
                "device_id": self.device_id,
                "login_attempt_count": "0",
            },
            headers={"X-CSRFToken": self._csrf()},
        )
        body = resp.json()
        if body.get("status") == "ok" and "logged_in_user" in body:
            self.user_id = str(body["logged_in_user"]["pk"])
            self.username = username
            self.save_session()
            return True
        reason = body.get("message") or body.get("error_type") or "unknown"
        raise RuntimeError(f"Login failed: {reason}")

    # --------------------------------------------------------------- helpers

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(f"{self.API}{path}", **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(
            f"{self.API}{path}",
            headers={"X-CSRFToken": self._csrf()},
            **kwargs,
        )
