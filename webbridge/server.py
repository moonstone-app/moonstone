# -*- coding: UTF-8 -*-

"""HTTP Server and WSGI application for WebBridge.

Provides a threaded HTTP server that routes requests to:
- /api/* — REST API endpoints (NotebookAPI)
- /apps/* — static files for web applets
- /events — SSE (Server-Sent Events) stream
- / — dashboard page
"""

import json
import logging
import urllib.parse
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

from moonstone.webbridge.api import NotebookAPI
from moonstone.webbridge.applets import AppletManager
from moonstone.webbridge.openapi import get_openapi_spec, get_swagger_ui_html
from moonstone.webbridge.endpoints import router

logger = logging.getLogger("moonstone.webbridge")


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    """A threaded WSGI server to handle multiple requests concurrently.
    This is important for SSE connections which are long-lived.
    """

    daemon_threads = True
    allow_reuse_address = True


class QuietRequestHandler(WSGIRequestHandler):
    """Request handler that suppresses default stderr logging."""

    def log_message(self, format, *args):
        logger.debug("HTTP %s", format % args)

    def handle_error(self, request, client_address):
        """Suppress TimeoutError and BrokenPipeError caused by SSE client disconnects."""
        import sys

        exc_type, exc_value, exc_traceback = sys.exc_info()
        if isinstance(exc_value, (TimeoutError, BrokenPipeError, ConnectionResetError)):
            logger.debug("Client %s disconnected: %r", client_address, exc_value)
            return
        super().handle_error(request, client_address)


class WebBridgeApp:
    """WSGI application that routes requests to appropriate handlers."""

    def __init__(self, notebook, app, auth_token=None, event_manager=None, port=8090):
        self.notebook = notebook
        self.app = app
        self.auth_token = auth_token
        self.event_manager = event_manager
        self.port = port
        self.applet_manager = AppletManager(app.applets_dir)

        # Initialize ServiceManager
        self.service_manager = None
        try:
            from moonstone.webbridge.services import ServiceManager

            services_dir = self._get_services_dir(app)
            api_url = "http://localhost:%d/api" % port
            self.service_manager = ServiceManager(
                services_dir=services_dir,
                api_url=api_url,
                auth_token=auth_token,
                ws_url=None,  # set later when WS is started
            )
            if event_manager:
                self.service_manager.set_event_manager(event_manager)
            self.service_manager.start_health_monitor()
            self.service_manager.auto_start_services()
            logger.info("ServiceManager initialized: %s", services_dir)
        except Exception:
            logger.debug("ServiceManager not available", exc_info=True)

        self.api = NotebookAPI(
            notebook, app, event_manager, self.applet_manager, self.service_manager
        )

    @staticmethod
    def _get_services_dir(app):
        """Determine the services directory path."""
        import os

        # Services directory is independent of applets directory
        if hasattr(app, "services_dir") and app.services_dir:
            services_dir = app.services_dir
        else:
            xdg_data = os.environ.get(
                "XDG_DATA_HOME",
                os.path.join(os.path.expanduser("~"), ".local", "share"),
            )
            services_dir = os.path.join(xdg_data, "moonstone", "services")
        os.makedirs(services_dir, exist_ok=True)
        return services_dir

    def __call__(self, environ, start_response):
        """WSGI entry point."""
        try:
            return self._handle_request(environ, start_response)
        except Exception as e:
            logger.exception("Unhandled error in request handler")
            return self._error_response(start_response, 500, "Internal Server Error")

    def _handle_request(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")

        # WSGI (PEP 3333) decodes PATH_INFO as latin-1, but browsers
        # send percent-encoded UTF-8.  Re-encode → decode as UTF-8 so
        # non-ASCII page names (Russian, CJK, …) work correctly.
        try:
            path = path.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass  # already valid UTF-8 or pure ASCII — leave as-is

        query_string = environ.get("QUERY_STRING", "")
        params = urllib.parse.parse_qs(query_string)

        # CORS headers for all responses
        cors_headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token"),
            ("Access-Control-Max-Age", "3600"),
        ]

        # Handle CORS preflight
        if method == "OPTIONS":
            start_response("204 No Content", cors_headers)
            return [b""]

        # Authentication check
        if self.auth_token:
            token = environ.get("HTTP_X_AUTH_TOKEN", "")
            if token != self.auth_token:
                # Also check query param for SSE (EventSource can't set headers)
                token_param = params.get("token", [""])[0]
                if token_param != self.auth_token:
                    return self._error_response(
                        start_response, 401, "Unauthorized", cors_headers
                    )

        # Route request
        if path == "/" or path == "/index.html":
            return self._serve_dashboard(start_response, cors_headers)
        elif path == "/workspace" or path == "/workspace/":
            return self._serve_workspace(start_response, cors_headers)
        elif path.startswith("/api/"):
            return self._handle_api(
                method, path, params, environ, start_response, cors_headers
            )
        elif path == "/events":
            return self._handle_sse(environ, start_response, cors_headers)
        elif path.startswith("/apps/_lib/"):
            return self._serve_static_lib(path[10:], start_response, cors_headers)
        elif path.startswith("/apps/"):
            return self._serve_applet(path[6:], start_response, cors_headers)
        elif path.startswith("/static/"):
            return self._serve_static_lib(path[8:], start_response, cors_headers)
        else:
            return self._error_response(start_response, 404, "Not Found", cors_headers)

    def _handle_api(self, method, path, params, environ, start_response, cors_headers):
        """Route API requests using the APIRouter."""
        unquoted_path = urllib.parse.unquote(path)
        
        # Delegate to the router
        result = router.dispatch(self, method, unquoted_path, params, environ, start_response, cors_headers)
        if result is not None:
            return result
            
        return self._json_response(
            start_response,
            404,
            {"error": "Unknown API endpoint: %s %s" % (method, path)},
            cors_headers,
        )

    def _handle_sse(self, environ, start_response, cors_headers):
        """Handle Server-Sent Events connection."""
        if not self.event_manager:
            return self._error_response(
                start_response, 503, "SSE not available", cors_headers
            )

        # Parse subscribe filter from query string
        query_string = environ.get("QUERY_STRING", "")
        params = urllib.parse.parse_qs(query_string)
        subscribe_str = params.get("subscribe", [None])[0]
        subscribe = set(subscribe_str.split(",")) if subscribe_str else None

        headers = cors_headers + [
            ("Content-Type", "text/event-stream"),
            ("Cache-Control", "no-cache"),
            ("X-Accel-Buffering", "no"),
        ]
        start_response("200 OK", headers)

        client_queue = self.event_manager.add_client()
        try:
            for event_str in self.event_manager.generate_events(
                client_queue, subscribe=subscribe
            ):
                yield event_str.encode("utf-8")
        except (GeneratorExit, BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.event_manager.remove_client(client_queue)

    def _serve_dashboard(self, start_response, cors_headers):
        """Serve the main dashboard page."""
        result = self.applet_manager.serve_static("index.html")
        if result:
            content, content_type = result
            headers = cors_headers + [
                ("Content-Type", content_type),
                ("Content-Length", str(len(content))),
            ]
            start_response("200 OK", headers)
            return [content]
        else:
            # Fallback: generate a simple dashboard
            return self._serve_generated_dashboard(start_response, cors_headers)

    def _serve_generated_dashboard(self, start_response, cors_headers):
        """Generate a polished dashboard page listing available applets."""
        self.applet_manager.refresh()
        applets = self.applet_manager.list_applets()
        applets_json = json.dumps(applets, ensure_ascii=False)

        html = _DASHBOARD_TEMPLATE.replace("/*APPLETS_DATA*/", applets_json)
        content = html.encode("utf-8")
        headers = cors_headers + [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(content))),
        ]
        start_response("200 OK", headers)
        return [content]

    def _serve_workspace(self, start_response, cors_headers):
        """Serve the built-in Workspace (tiling window manager) page."""
        result = self.applet_manager.serve_static("workspace.html")
        if result is None:
            return self._error_response(
                start_response, 404, "Workspace not found", cors_headers
            )
        content, content_type = result
        headers = cors_headers + [
            ("Content-Type", content_type),
            ("Content-Length", str(len(content))),
        ]
        start_response("200 OK", headers)
        return [content]

    def _serve_applet(self, path, start_response, cors_headers):
        """Serve files from an applet directory."""
        parts = path.split("/", 1)
        applet_name = parts[0]
        file_path = parts[1] if len(parts) > 1 else "index.html"
        if not file_path or file_path.endswith("/"):
            file_path += "index.html"

        result = self.applet_manager.serve_file(applet_name, file_path)
        if result is None:
            return self._error_response(
                start_response, 404, "File not found", cors_headers
            )

        content, content_type = result
        headers = cors_headers + [
            ("Content-Type", content_type),
            ("Content-Length", str(len(content))),
        ]
        start_response("200 OK", headers)
        return [content]

    def _serve_static_lib(self, path, start_response, cors_headers):
        """Serve files from the bundled static directory."""
        result = self.applet_manager.serve_static(path)
        if result is None:
            return self._error_response(
                start_response, 404, "Static file not found", cors_headers
            )

        content, content_type = result
        headers = cors_headers + [
            ("Content-Type", content_type),
            ("Content-Length", str(len(content))),
        ]
        start_response("200 OK", headers)
        return [content]

    def _serve_dev_bundle(self, start_response, cors_headers):
        """Serve a developer bundle: all files needed to build applets and services,
        combined into a single text document with explanations."""
        import os

        static_dir = self.applet_manager.get_static_dir()
        webbridge_dir = os.path.dirname(os.path.abspath(__file__))

        # Collect files
        files = {}
        file_list = [
            (
                os.path.join(static_dir, "moonstone-bridge.js"),
                "moonstone-bridge.js",
                "js",
            ),
            (os.path.join(static_dir, "moonstone.css"), "moonstone.css", "css"),
            (
                os.path.join(webbridge_dir, "moonstone_sdk.py"),
                "moonstone_sdk.py",
                "python",
            ),
        ]
        for fpath, fname, lang in file_list:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    files[fname] = (f.read(), lang)
            except OSError:
                files[fname] = ("# File not found: " + fpath, lang)

        # OpenAPI spec (generated dynamically)
        spec = get_openapi_spec(self.port)
        files["openapi.json"] = (json.dumps(spec, indent=2, ensure_ascii=False), "json")

        # Build the bundle document
        parts = []
        parts.append("# Moonstone Developer Bundle")
        parts.append("")
        parts.append(
            "This document contains everything needed to develop **applets** (web UIs) and"
        )
        parts.append(
            "**services** (background Python daemons) for Moonstone — a headless PKM server"
        )
        parts.append(
            "that turns a folder of notes into a programmable platform with 60+ REST endpoints."
        )
        parts.append("")
        parts.append("## How to use this bundle")
        parts.append("")
        parts.append(
            "Give this entire document to an AI (ChatGPT, Claude, etc.) along with your request,"
        )
        parts.append(
            'for example: "Build me a kanban board applet" or "Build me an RSS feed service".'
        )
        parts.append(
            "The AI will have full context about the API, the JS bridge, the CSS theme, and the SDK."
        )
        parts.append("")
        parts.append("## Two types of extensions")
        parts.append("")
        parts.append("### Applets (Web UIs)")
        parts.append("")
        parts.append(
            "An applet is a folder with an `index.html` file, served as a standalone HTML page by the Moonstone server."
        )
        parts.append(
            "It communicates with Moonstone exclusively via the REST API (`/api/*`) and SSE (`/events`)."
        )
        parts.append(
            "No build step. No npm. No framework required. Just HTML + JS + CSS."
        )
        parts.append("")
        parts.append("**Directory structure:**")
        parts.append("```")
        parts.append("my-applet/")
        parts.append("  index.html        # Entry point (required)")
        parts.append("  manifest.json     # Metadata (required)")
        parts.append("  style.css         # Your styles (optional)")
        parts.append("  app.js            # Your logic (optional)")
        parts.append("```")
        parts.append("")
        parts.append("**Example applet manifest.json:**")
        parts.append("```json")
        parts.append(
            json.dumps(
                {
                    "name": "My Applet",
                    "icon": "📊",
                    "description": "Short description of what this applet does",
                    "version": "1.0.0",
                    "author": "Your Name",
                    "min_api": "2.4",
                },
                indent=2,
            )
        )
        parts.append("```")
        parts.append("")
        parts.append("**Key applet patterns:**")
        parts.append(
            '- Include `<link rel="stylesheet" href="/static/moonstone.css">` for theme support'
        )
        parts.append(
            '- Include `<script src="/static/moonstone-bridge.js"></script>` for the JS helper library'
        )
        parts.append(
            "- Use `MoonstoneBridge` class from the bridge for convenient API calls"
        )
        parts.append('- Use `fetch("/api/...")` for direct REST calls')
        parts.append('- Use `EventSource("/events")` for real-time updates via SSE')
        parts.append(
            "- Use `/api/store/<applet-name>/<key>` for applet settings, caches, and internal JSON state (not for notebook content — use pages for that)"
        )
        parts.append(
            "- Applets are plain HTML pages with no filesystem access — they only communicate via REST API"
        )
        parts.append(
            "- Install location: `~/.local/share/moonstone/webapps/<applet-name>/`"
        )
        parts.append("")
        parts.append("**Step-by-step: creating an applet manually:**")
        parts.append("")
        parts.append(
            "1. Create a folder in `~/.local/share/moonstone/webapps/my-applet/`"
        )
        parts.append(
            "2. Create `manifest.json` with name, icon, description, version, author"
        )
        parts.append(
            "3. Create `index.html` — this is the entry point served at `/apps/my-applet/`"
        )
        parts.append(
            '4. In your HTML, link the shared CSS: `<link rel="stylesheet" href="/static/moonstone.css">`'
        )
        parts.append(
            '5. In your HTML, load the bridge: `<script src="/static/moonstone-bridge.js"></script>`'
        )
        parts.append("6. Use the API in your JS: `const api = new MoonstoneBridge();`")
        parts.append("7. Fetch pages: `const pages = await api.listPages();`")
        parts.append(
            '8. Save notebook data: `await api.savePage("MyApplet:Data", content);` — use `/api/store/…` only for settings and UI state'
        )
        parts.append(
            '9. Listen for changes: `const sse = new EventSource("/events"); sse.addEventListener("page-saved", e => { ... });`'
        )
        parts.append(
            "10. Refresh dashboard — your applet appears. Open `/apps/my-applet/` to use it."
        )
        parts.append("")
        parts.append("**Minimal applet index.html example:**")
        parts.append("```html")
        parts.append("<!DOCTYPE html>")
        parts.append('<html lang="en" data-theme="dark">')
        parts.append("<head>")
        parts.append('  <meta charset="utf-8">')
        parts.append("  <title>My Applet</title>")
        parts.append('  <link rel="stylesheet" href="/static/moonstone.css">')
        parts.append('  <script src="/static/moonstone-bridge.js"></script>')
        parts.append("</head>")
        parts.append("<body>")
        parts.append('  <div class="ms-container">')
        parts.append("    <h1>My Applet</h1>")
        parts.append('    <div id="content">Loading...</div>')
        parts.append("  </div>")
        parts.append("  <script>")
        parts.append("    const api = new MoonstoneBridge();")
        parts.append("    async function init() {")
        parts.append("      const pages = await api.listPages();")
        parts.append('      document.getElementById("content").textContent =')
        parts.append('        pages.length + " pages found";')
        parts.append("    }")
        parts.append("    init();")
        parts.append("  </script>")
        parts.append("</body>")
        parts.append("</html>")
        parts.append("```")
        parts.append("")
        parts.append("**Common API calls for applets:**")
        parts.append("- `GET /api/pages` — list all pages")
        parts.append("- `GET /api/page/PageName` — get page content")
        parts.append('- `PUT /api/page/PageName` — save page `{"content":"..."}`')
        parts.append(
            '- `PATCH /api/page/PageName` — partial update `{"operations":[{"op":"replace","search":"old text","replace":"new text"}]}`'
        )
        parts.append("- `GET /api/search?q=term&snippets=true` — full-text search")
        parts.append("- `GET /api/tags` — list all tags")
        parts.append("- `GET /api/graph` — page link graph (nodes + edges)")
        parts.append("- `GET /api/analysis/orphans` — find unlinked pages")
        parts.append("- `GET /api/store/my-applet/key` — read saved state")
        parts.append('- `PUT /api/store/my-applet/key` — save state `{"value": ...}`')
        parts.append(
            '- `EventSource("/events")` — real-time events: page-saved, page-deleted, page-moved'
        )
        parts.append("")
        parts.append("**SSE events you can listen for:**")
        parts.append(
            'These are raw SSE event types emitted by the server. Use `sse.addEventListener("page-saved", …)` directly, or the bridge convenience methods like `api.onPageSaved(cb)`.'
        )
        parts.append("")
        parts.append("- `page-saved` — a page was created or updated")
        parts.append("- `page-changed` — a page file changed on disk (external editor)")
        parts.append("- `page-deleted` — a page was deleted")
        parts.append("- `page-moved` — a page was moved/renamed")
        parts.append("- `store-changed` — a KV store value was updated")
        parts.append("")
        parts.append("### Storage model for applets")
        parts.append("")
        parts.append(
            "Moonstone is a PKMS built around plain-text pages. Applets have two storage mechanisms:"
        )
        parts.append("")
        parts.append("**1. Pages (`/api/page/...`) — default for user-visible data**")
        parts.append(
            "Use normal Moonstone pages when the data is part of the notebook."
        )
        parts.append(
            "Data stored in pages is: human-readable, searchable, visible in the graph/tags,"
        )
        parts.append("exportable, and editable as plain text files.")
        parts.append(
            "Examples: habit trackers, kanban boards, reading lists, flashcards, journals."
        )
        parts.append("")
        parts.append(
            "**2. KV Store (`/api/store/<applet>/<key>`) — only for applet-internal state**"
        )
        parts.append(
            "Use KV store only for small JSON values internal to the applet, not for notebook content."
        )
        parts.append(
            "Good uses: UI preferences, selected filters, cached layout, last opened tab, sync cursors."
        )
        parts.append(
            "Bad use: storing all user data (habits, cards, entries) only in KV store."
        )
        parts.append("")
        parts.append(
            "**Important:** The KV store is not a substitute for notebook pages."
        )
        parts.append(
            "It exists for extension state, not as the primary storage layer for PKMS content."
        )
        parts.append("")
        parts.append("**Rule of thumb:**")
        parts.append(
            "- If the user would expect to see/edit it as a note → store in a page"
        )
        parts.append("- If it is applet config or technical state → store in KV")
        parts.append(
            "- For AI-generated applets: prefer page-backed storage unless the request"
        )
        parts.append("  is explicitly about settings, cache, or transient UI state")
        parts.append("")
        parts.append(
            "When generating applets that store user data in Pages, **NEVER** save data"
        )
        parts.append(
            "as JSON strings or JSON code blocks inside the Markdown file. Applet must parse and"
        )
        parts.append(
            "serialize data using native Markdown structures (task lists, tables, headings,"
        )
        parts.append(
            "links etc.) so the user can natively read and edit the file in any Markdown editor"
        )
        parts.append("")
        parts.append("BAD (Do not do this):")
        parts.append("```json")
        parts.append('{"habits": {"2026-03-03": ["test"]}}')
        parts.append("```")
        parts.append("")
        parts.append("GOOD (Do this):")
        parts.append("### 2026-03-03")
        parts.append("- [x] First")
        parts.append("- [ ] Second")
        parts.append("")
        parts.append(
            "Since applets do not use npm/build steps, you must write simple custom JavaScript"
        )
        parts.append(
            "logic (using regex or string manipulation) inside the applet to parse the native"
        )
        parts.append(
            "Markdown content string into a JS object on load, and serialize the JS object back into a"
        )
        parts.append("formatted Markdown string on save")
        parts.append("")
        parts.append("### Services (Background Python Daemons)")
        parts.append("")
        parts.append("A service is a folder with a Python entry script and a manifest.")
        parts.append(
            "Services run as managed background processes with lifecycle: start/stop/restart,"
        )
        parts.append("health monitoring, isolated venvs, and logging.")
        parts.append("")
        parts.append("**Directory structure:**")
        parts.append("```")
        parts.append("my-service/")
        parts.append("  service.py        # Entry point (required)")
        parts.append('  manifest.json     # Metadata with type:"service" (required)')
        parts.append("  requirements.txt  # Python dependencies (optional)")
        parts.append("```")
        parts.append("")
        parts.append("**Example service manifest.json:**")
        parts.append("```json")
        parts.append(
            json.dumps(
                {
                    "type": "service",
                    "name": "My Service",
                    "id": "my-service",
                    "description": "Short description of what this service does",
                    "version": "0.1.0",
                    "author": "Your Name",
                    "icon": "⚡",
                    "entry": "service.py",
                    "auto_start": False,
                    "preferences": [
                        {
                            "key": "api_key",
                            "label": "API Key",
                            "type": "string",
                            "description": "Your API key",
                            "required": True,
                        },
                        {
                            "key": "enabled",
                            "label": "Enabled",
                            "type": "boolean",
                            "description": "Enable this feature",
                            "default": True,
                        },
                    ],
                },
                indent=2,
            )
        )
        parts.append("```")
        parts.append("")
        parts.append("**Key service patterns:**")
        parts.append(
            "- Import `moonstone_sdk` (bundled, no install needed) for API access"
        )
        parts.append(
            "- `preferences` in manifest define config UI shown on the dashboard"
        )
        parts.append(
            "- Config is stored in `_data/_config.json` (managed by dashboard config UI)"
        )
        parts.append(
            "- Use `MoonstoneAPI(api_url, auth_token)` from the SDK for API calls"
        )
        parts.append(
            "- Services get `MOONSTONE_API_URL` and `MOONSTONE_AUTH_TOKEN` env vars"
        )
        parts.append(
            "- Install location: `~/.local/share/moonstone/services/<service-name>/`"
        )
        parts.append(
            "- **Canonical identifier = directory name.** `manifest.name` is display label, `manifest.id` is optional metadata."
        )
        parts.append("- Managed lifecycle: start/stop/restart from dashboard or API")
        parts.append(
            "- Isolated venv: if `requirements.txt` exists, deps are auto-installed"
        )
        parts.append("- Logs available via `GET /api/services/<name>/logs?tail=100`")
        parts.append("")
        parts.append("**Step-by-step: creating a service manually:**")
        parts.append("")
        parts.append(
            "1. Create a folder in `~/.local/share/moonstone/services/my-service/`"
        )
        parts.append(
            '2. Create `manifest.json` with `"type": "service"`, name, id, entry, icon, etc.'
        )
        parts.append("3. Create `service.py` — this is the entry point")
        parts.append("4. (Optional) Create `requirements.txt` for pip dependencies")
        parts.append(
            "5. In `service.py`, read env vars: `MOONSTONE_API_URL`, `MOONSTONE_AUTH_TOKEN`"
        )
        parts.append("6. Use `moonstone_sdk.MoonstoneAPI(url, token)` to call the API")
        parts.append("7. Implement your logic (loop, scheduler, bot, etc.)")
        parts.append("8. Handle `SIGTERM` for graceful shutdown")
        parts.append("9. Refresh dashboard — your service appears. Click ▶ to start.")
        parts.append("")
        parts.append("**Minimal service.py example:**")
        parts.append("```python")
        parts.append("#!/usr/bin/env python3")
        parts.append('"""Example Moonstone service — creates a daily note page."""')
        parts.append("import os, time, signal, sys, json")
        parts.append("from datetime import date")
        parts.append("")
        parts.append("# Read connection info from environment")
        parts.append(
            'API_URL = os.environ.get("MOONSTONE_API_URL", "http://localhost:8090/api")'
        )
        parts.append('AUTH_TOKEN = os.environ.get("MOONSTONE_AUTH_TOKEN", "")')
        parts.append("")
        parts.append("# Optional: use bundled SDK")
        parts.append("try:")
        parts.append("    from moonstone_sdk import MoonstoneAPI")
        parts.append("    sdk = MoonstoneAPI(API_URL, AUTH_TOKEN)")
        parts.append("except ImportError:")
        parts.append("    sdk = None  # fallback to raw requests")
        parts.append("")
        parts.append(
            "# Read config (managed by dashboard, stored in _data/_config.json)"
        )
        parts.append("from moonstone_sdk import load_config")
        parts.append("config = load_config()  # reads _data/_config.json automatically")
        parts.append("")
        parts.append("running = True")
        parts.append("def on_signal(sig, frame):")
        parts.append("    global running")
        parts.append("    running = False")
        parts.append("signal.signal(signal.SIGTERM, on_signal)")
        parts.append("signal.signal(signal.SIGINT, on_signal)")
        parts.append("")
        parts.append('print("Daily Notes service started")')
        parts.append("while running:")
        parts.append("    today = date.today().isoformat()")
        parts.append('    page_name = f"Journal:{today}"')
        parts.append("    if sdk:")
        parts.append("        existing = sdk.get_page(page_name)")
        parts.append("        if not existing:")
        parts.append('            sdk.create_page(page_name, f"# {today}\\n\\n")')
        parts.append('            print(f"Created {page_name}")')
        parts.append("    time.sleep(3600)  # check every hour")
        parts.append('print("Service stopped")')
        parts.append("```")
        parts.append("")
        parts.append("**Service management API:**")
        parts.append("- `GET /api/services` — list all services with status")
        parts.append("- `POST /api/services/<name>/start` — start a service")
        parts.append("- `POST /api/services/<name>/stop` — stop a service")
        parts.append("- `POST /api/services/<name>/restart` — restart a service")
        parts.append("- `GET /api/services/<name>/logs?tail=100` — read recent logs")
        parts.append(
            "- `GET /api/services/<name>/config` — read config + preferences schema"
        )
        parts.append("- `PUT /api/services/<name>/config` — save config values")
        parts.append("")
        parts.append("## Files included below")
        parts.append("")
        parts.append("| File | Purpose |")
        parts.append("|------|---------|")
        parts.append(
            "| `openapi.json` | Full OpenAPI 3.0 spec — all 60+ endpoints with schemas |"
        )
        parts.append(
            "| `moonstone-bridge.js` | JS helper library for applets (MoonstoneBridge class, SSE, themes) |"
        )
        parts.append(
            "| `moonstone.css` | CSS theme with dark/light mode, variables, components |"
        )
        parts.append(
            "| `moonstone_sdk.py` | Python SDK for services (API client, config, logging) |"
        )
        parts.append("")

        # Source tree
        parts.append("## Source Tree")
        parts.append("")
        parts.append("```txt")
        for fname in [
            "openapi.json",
            "moonstone-bridge.js",
            "moonstone.css",
            "moonstone_sdk.py",
        ]:
            parts.append("├── " + fname)
        parts.append("```")
        parts.append("")

        # File contents
        file_order = [
            "openapi.json",
            "moonstone-bridge.js",
            "moonstone.css",
            "moonstone_sdk.py",
        ]
        for fname in file_order:
            content, lang = files.get(fname, ("", "txt"))
            parts.append("---")
            parts.append("")
            parts.append("`%s`:" % fname)
            parts.append("")
            parts.append("```%s" % lang)
            parts.append(content)
            parts.append("```")
            parts.append("")

        text = "\n".join(parts)
        content_bytes = text.encode("utf-8")
        headers = cors_headers + [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(content_bytes))),
            ("Content-Disposition", 'attachment; filename="moonstone-dev-bundle.txt"'),
        ]
        start_response("200 OK", headers)
        return [content_bytes]

    # ---- Helpers ----

    def _read_request_body(self, environ):
        """Read and decode the request body as UTF-8 string."""
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length > 0:
            return environ["wsgi.input"].read(content_length).decode("utf-8")
        return ""

    def _read_request_body_raw(self, environ):
        """Read the request body as raw bytes."""
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length > 0:
            return environ["wsgi.input"].read(content_length)
        return b""

    def _json_response(
        self, start_response, status_code, body, cors_headers=None, extra_headers=None
    ):
        """Send a JSON response."""
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = list(cors_headers or [])
        headers.append(("Content-Type", "application/json; charset=utf-8"))
        headers.append(("Content-Length", str(len(content))))
        headers.append(
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        )
        if extra_headers:
            if isinstance(extra_headers, dict):
                headers.extend(extra_headers.items())
            else:
                headers.extend(extra_headers)
        start_response(self._status_string(status_code), headers)
        return [content]

    def _error_response(self, start_response, status_code, message, cors_headers=None):
        """Send an error response."""
        return self._json_response(
            start_response, status_code, {"error": message}, cors_headers
        )

    @staticmethod
    def _status_string(code):
        """Convert status code to WSGI status string."""
        status_map = {
            200: "200 OK",
            204: "204 No Content",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            403: "403 Forbidden",
            404: "404 Not Found",
            409: "409 Conflict",
            500: "500 Internal Server Error",
            503: "503 Service Unavailable",
            504: "504 Gateway Timeout",
        }
        return status_map.get(code, "%d Unknown" % code)


# ---------------------------------------------------------------------------
# Dashboard HTML template (module-level to keep the class clean)
# The placeholder /*APPLETS_DATA*/ is replaced at runtime with JSON.
# Using triple double-quotes to avoid single-quote escaping issues in JS.
# ---------------------------------------------------------------------------
_DASHBOARD_TEMPLATE = """\
<!DOCTYPE html>

"""


def create_server(
    notebook,
    app,
    port=8090,
    auth_token=None,
    event_manager=None,
    bind_address="localhost",
):
    """Create the WebBridge HTTP server.

    @param notebook: the Moonstone Notebook instance
    @param app: the Moonstone AppContext instance
    @param port: HTTP port to listen on
    @param auth_token: optional authentication token
    @param event_manager: optional EventManager for SSE
    @param bind_address: address to bind to ('localhost' or '0.0.0.0')
    @returns: a ThreadedWSGIServer instance
    """
    app = WebBridgeApp(
        notebook=notebook,
        app=app,
        auth_token=auth_token,
        event_manager=event_manager,
        port=port,
    )

    server = ThreadedWSGIServer((bind_address, port), QuietRequestHandler)
    server.set_app(app)

    logger.info("WebBridge server created on %s:%d", bind_address, port)
    return server
