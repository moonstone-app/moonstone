# -*- coding: UTF-8 -*-
"""Moonstone Service SDK — helper library for background services.

Usage in your service.py:

    from moonstone_sdk import MoonstoneAPI, load_config
    api = MoonstoneAPI()              # auto-reads env vars
    config = load_config()            # reads _data/_config.json

    # Create / append to pages
    api.create_page('Services:Notes', '====== Notes ======\nHello!')
    api.append('Services:Notes', '\nNew line from service')

    # Read pages
    page = api.get_page('Home')
    print(page['content'])

    # Search
    results = api.search('todo')
    for r in results:
        print(r['name'])

    # Tags
    api.add_tag('Home', 'automated')

    # Attachments
    with open('photo.jpg', 'rb') as f:
        api.upload_attachment('Home', 'photo.jpg', f.read())

Environment variables (set automatically by ServiceManager):
    MOONSTONE_API_URL       — e.g. http://localhost:8090/api
    MOONSTONE_AUTH_TOKEN     — auth token (if configured)
    MOONSTONE_SERVICE_NAME   — service directory name
    MOONSTONE_SERVICE_DATA_DIR — path to _data/ directory
    MOONSTONE_WS_URL         — WebSocket URL (optional)
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger("moonstone.service")


class MoonstoneAPIError(Exception):
    """Raised when an API call fails."""

    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class MoonstoneAPI:
    """HTTP client for the Moonstone REST API.

    All methods are synchronous and raise MoonstoneAPIError on failure.
    """

    def __init__(self, base_url=None, auth_token=None, timeout=15):
        self.base_url = (
            base_url
            or os.environ.get("MOONSTONE_API_URL")
            or os.environ.get("MOONSTONE_API_URL", "http://localhost:8090/api")
        ).rstrip("/")
        self.auth_token = (
            auth_token
            or os.environ.get("MOONSTONE_AUTH_TOKEN")
            or os.environ.get("MOONSTONE_AUTH_TOKEN", "")
        )
        self.timeout = timeout
        self.service_name = os.environ.get("MOONSTONE_SERVICE_NAME") or os.environ.get(
            "MOONSTONE_SERVICE_NAME", "unknown"
        )

    def _request(self, method, path, data=None, timeout=None):
        """Make an HTTP request to the API."""
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["X-Auth-Token"] = self.auth_token

        body = None
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout or self.timeout)
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw}
            raise MoonstoneAPIError(
                "API error %d: %s" % (e.code, body.get("error", raw[:200])),
                status=e.code,
                body=body,
            )
        except urllib.error.URLError as e:
            raise MoonstoneAPIError("Connection failed: %s" % str(e.reason))

    def get(self, path, **params):
        if params:
            qs = urllib.parse.urlencode(params)
            path = "%s?%s" % (path, qs)
        return self._request("GET", path)

    def post(self, path, data=None):
        return self._request("POST", path, data)

    def put(self, path, data=None):
        return self._request("PUT", path, data)

    def delete(self, path):
        return self._request("DELETE", path)

    # ---- Convenience methods ----

    def get_page(self, page_path, format="wiki"):
        """Get page content."""
        safe = page_path.replace(":", "/")
        return self.get("page/%s" % safe, format=format)

    def save_page(self, page_path, content, format="wiki"):
        """Save (overwrite) page content."""
        safe = page_path.replace(":", "/")
        return self.put("page/%s" % safe, {"content": content, "format": format})

    def create_page(self, page_path, content="", format="wiki"):
        """Create a new page."""
        safe = page_path.replace(":", "/")
        return self.post("page/%s" % safe, {"content": content, "format": format})

    def append(self, page_path, content, format="wiki"):
        """Append content to an existing page."""
        safe = page_path.replace(":", "/")
        return self.post(
            "page/%s/append" % safe, {"content": content, "format": format}
        )

    def upload_attachment(self, page_path, filename, raw_bytes):
        """Upload raw bytes as an attachment to a page."""
        safe_path = page_path.replace(":", "/")
        safe_file = urllib.parse.quote(filename, safe="")
        path = "attachment/%s?filename=%s" % (safe_path, safe_file)
        
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        headers = {"Content-Type": "application/octet-stream"}
        if self.auth_token:
            headers["X-Auth-Token"] = self.auth_token

        req = urllib.request.Request(url, data=raw_bytes, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw}
            raise MoonstoneAPIError(
                "API error %d: %s" % (e.code, body.get("error", raw[:200])),
                status=e.code,
                body=body,
            )
        except urllib.error.URLError as e:
            raise MoonstoneAPIError("Connection failed: %s" % str(e.reason))

    def delete_page(self, page_path):
        """Delete a page."""
        safe = page_path.replace(":", "/")
        return self.delete("page/%s" % safe)

    def search(self, query):
        """Search pages. Returns list of results."""
        result = self.get("search", q=query)
        return result.get("results", [])

    def list_pages(self, namespace=None):
        """List pages in a namespace."""
        params = {}
        if namespace:
            params["namespace"] = namespace
        result = self.get("pages", **params)
        return result.get("pages", [])

    def list_tags(self):
        """List all tags."""
        result = self.get("tags")
        return result.get("tags", [])

    def add_tag(self, page_path, tag):
        """Add a tag to a page."""
        safe = page_path.replace(":", "/")
        return self.post("page/%s/tags" % safe, {"tag": tag})

    def emit_event(self, event_type, data=None):
        """Emit a custom SSE event."""
        return self.post("emit", {"event": event_type, "data": data or {}})

    def get_notebook_info(self):
        """Get notebook metadata."""
        return self.get("notebook")

    def navigate(self, page_path):
        """Request Moonstone to open a page."""
        return self.post("navigate", {"page": page_path})

    def wait_for_api(self, max_wait=30, interval=1):
        """Wait until the API is reachable. Useful at service startup."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                self.get("notebook")
                return True
            except MoonstoneAPIError:
                time.sleep(interval)
        return False


# Backward compatibility alias (dev-bundle historically used MoonstoneSDK)
MoonstoneSDK = MoonstoneAPI


def load_config():
    """Load service configuration from _data/_config.json.

    Returns a dict (empty if no config file exists).
    """
    data_dir = os.environ.get("MOONSTONE_SERVICE_DATA_DIR") or os.environ.get(
        "MOONSTONE_SERVICE_DATA_DIR", "_data"
    )
    config_file = os.path.join(data_dir, "_config.json")
    if os.path.isfile(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(key, value):
    """Persist a key-value pair in _data/ for service state."""
    data_dir = os.environ.get("MOONSTONE_SERVICE_DATA_DIR") or os.environ.get(
        "MOONSTONE_SERVICE_DATA_DIR", "_data"
    )
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, "%s.json" % key)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def load_state(key, default=None):
    """Load a persisted state value."""
    data_dir = os.environ.get("MOONSTONE_SERVICE_DATA_DIR") or os.environ.get(
        "MOONSTONE_SERVICE_DATA_DIR", "_data"
    )
    filepath = os.path.join(data_dir, "%s.json" % key)
    if os.path.isfile(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def setup_logging(level=logging.INFO):
    """Configure logging with a clean format for service output."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
