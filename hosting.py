"""Host generated websites — local HTTP server or Netlify."""

import http.server
import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_server_thread: threading.Thread | None = None
_httpd = None


# ---------------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------------

def start_local_server(directory: str = "websites", port: int = 8080) -> str:
    """Start a local HTTP server serving the websites directory (background thread)."""
    global _httpd, _server_thread

    abs_dir = str(Path(directory).resolve())
    os.makedirs(abs_dir, exist_ok=True)

    handler = _make_handler(abs_dir)

    import socketserver
    _httpd = socketserver.TCPServer(("", port), handler)
    _server_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
    _server_thread.start()

    base_url = f"http://localhost:{port}"
    logger.info(f"Local server started: {base_url}")
    return base_url


def _make_handler(directory: str):
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):  # silence request logs
            pass

    return _Handler


def stop_local_server() -> None:
    global _httpd
    if _httpd:
        _httpd.shutdown()
        _httpd = None
        logger.info("Local server stopped")


def local_url_for(base_url: str, html_filepath: str) -> str:
    """Return a URL for a specific HTML file given the server base URL."""
    filename = Path(html_filepath).name
    return f"{base_url}/{filename}"


# ---------------------------------------------------------------------------
# Netlify (via CLI)
# ---------------------------------------------------------------------------

def deploy_to_netlify(websites_dir: str = "websites", site_name: str | None = None) -> str:
    """
    Deploy the websites directory to Netlify using the Netlify CLI.
    Returns the live URL on success.

    Requires `netlify` CLI to be installed and authenticated.
    """
    cmd = ["netlify", "deploy", "--dir", websites_dir, "--prod"]
    if site_name:
        cmd += ["--site", site_name]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Parse deploy URL from netlify output
        for line in result.stdout.splitlines():
            if "Website URL" in line or "Live URL" in line or "https://" in line:
                parts = line.split()
                for part in parts:
                    if part.startswith("https://"):
                        logger.info(f"Netlify deploy URL: {part}")
                        return part
        raise ValueError(f"Could not parse Netlify URL from output:\n{result.stdout}")
    except FileNotFoundError:
        raise RuntimeError(
            "Netlify CLI not found. Install with: npm install -g netlify-cli\n"
            "Then authenticate with: netlify login"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Netlify deploy failed:\n{e.stderr}")
