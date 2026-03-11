# -*- coding: UTF-8 -*-

"""WebSocket server for WebBridge.

Provides a pure-Python WebSocket server (RFC 6455) running on a separate
port alongside the HTTP/WSGI server.  Enables bidirectional real-time
communication with web applets: channel-based pub/sub, broadcasting,
and proxied REST API calls over a single persistent connection.

No external dependencies — built entirely on the Python standard library.
"""

import base64
import hashlib
import json
import logging
import os
import socket
import struct
import threading
import time
import urllib.parse
from socketserver import ThreadingTCPServer, StreamRequestHandler

logger = logging.getLogger("moonstone.webbridge")

# RFC 6455 magic GUID for Sec-WebSocket-Accept
_WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Opcodes
OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


# ---- WebSocket Frame helpers ----


def _recv_exact(sock, n):
    """Read exactly n bytes from socket. Raises ConnectionError on EOF."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed")
        buf.extend(chunk)
    return bytes(buf)


def _parse_frame(sock):
    """Read and parse one WebSocket frame from a socket.
    Returns (fin, opcode, payload: bytes) or raises ConnectionError.
    """
    header = _recv_exact(sock, 2)
    fin = (header[0] >> 7) & 1
    opcode = header[0] & 0x0F
    masked = (header[1] >> 7) & 1
    length = header[1] & 0x7F

    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]

    if masked:
        mask_key = _recv_exact(sock, 4)

    payload = _recv_exact(sock, length) if length > 0 else b""

    if masked and length > 0:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return fin, opcode, payload


def _build_frame(opcode, payload, mask=False):
    """Build a WebSocket frame (server → client, unmasked by default).
    Returns bytes.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    frame = bytearray()
    # First byte: FIN + opcode
    frame.append(0x80 | opcode)

    # Second byte: mask flag + length
    length = len(payload)
    mask_bit = 0x80 if mask else 0x00

    if length < 126:
        frame.append(mask_bit | length)
    elif length < 65536:
        frame.append(mask_bit | 126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(mask_bit | 127)
        frame.extend(struct.pack("!Q", length))

    if mask:
        mask_key = os.urandom(4)
        frame.extend(mask_key)
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    frame.extend(payload)
    return bytes(frame)


# ---- WebSocket Connection ----


class WebSocketConnection:
    """Wraps a raw socket providing high-level send/recv for WS frames."""

    def __init__(self, sock, client_id, addr):
        self.sock = sock
        self.client_id = client_id
        self.addr = addr
        self._lock = threading.Lock()
        self._closed = False

    def _send_frame(self, opcode, payload):
        """Send a single frame, thread-safe."""
        if self._closed:
            return
        frame = _build_frame(opcode, payload)
        with self._lock:
            try:
                self.sock.sendall(frame)
            except (OSError, BrokenPipeError):
                self._closed = True

    def send_text(self, text):
        """Send a text frame."""
        self._send_frame(
            OP_TEXT, text.encode("utf-8") if isinstance(text, str) else text
        )

    def send_json(self, obj):
        """Send a JSON-serialized text frame."""
        self.send_text(json.dumps(obj, ensure_ascii=False))

    def send_binary(self, data):
        """Send a binary frame."""
        self._send_frame(OP_BINARY, data)

    def ping(self, data=b""):
        """Send a ping frame."""
        self._send_frame(OP_PING, data)

    def close(self, code=1000, reason=""):
        """Send a close frame and mark connection as closed."""
        if self._closed:
            return
        self._closed = True
        payload = struct.pack("!H", code) + reason.encode("utf-8")
        try:
            frame = _build_frame(OP_CLOSE, payload)
            with self._lock:
                self.sock.sendall(frame)
        except (OSError, BrokenPipeError):
            pass

    def recv(self):
        """Receive one complete message (handles fragmentation).
        Returns (opcode, payload) or raises ConnectionError.
        """
        fragments = bytearray()
        msg_opcode = None

        while True:
            fin, opcode, payload = _parse_frame(self.sock)

            # Control frames can appear between fragmented data frames
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            elif opcode == OP_PONG:
                continue
            elif opcode == OP_CLOSE:
                self._closed = True
                # Echo close frame back
                try:
                    frame = _build_frame(OP_CLOSE, payload)
                    with self._lock:
                        self.sock.sendall(frame)
                except (OSError, BrokenPipeError):
                    pass
                raise ConnectionError("WebSocket closed by peer")

            # Data frames
            if opcode != OP_CONTINUATION:
                msg_opcode = opcode
                fragments = bytearray(payload)
            else:
                fragments.extend(payload)

            if fin:
                if msg_opcode == OP_TEXT:
                    return msg_opcode, fragments.decode("utf-8")
                return msg_opcode, bytes(fragments)

    @property
    def is_closed(self):
        return self._closed


# ---- WebSocket Manager (channels, broadcast) ----


class WebSocketManager:
    """Thread-safe manager for WebSocket connections and channels."""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients = {}  # client_id → WebSocketConnection
        self._channels = {}  # channel → set of client_ids
        self._client_channels = {}  # client_id → set of channels

    def add_client(self, conn):
        """Register a new client connection. Returns client_id."""
        with self._lock:
            self._clients[conn.client_id] = conn
            self._client_channels[conn.client_id] = set()
        logger.debug(
            "WS client connected: %s (total: %d)", conn.client_id, len(self._clients)
        )
        return conn.client_id

    def remove_client(self, client_id):
        """Unregister client and remove from all channels."""
        with self._lock:
            channels = self._client_channels.pop(client_id, set())
            for ch in channels:
                s = self._channels.get(ch)
                if s:
                    s.discard(client_id)
                    if not s:
                        del self._channels[ch]
            self._clients.pop(client_id, None)
        logger.debug(
            "WS client disconnected: %s (total: %d)", client_id, len(self._clients)
        )

    def subscribe(self, client_id, channel):
        """Subscribe a client to a channel."""
        with self._lock:
            if client_id not in self._clients:
                return False
            if channel not in self._channels:
                self._channels[channel] = set()
            self._channels[channel].add(client_id)
            self._client_channels[client_id].add(channel)
        logger.debug("WS %s subscribed to %s", client_id, channel)
        return True

    def unsubscribe(self, client_id, channel):
        """Unsubscribe a client from a channel."""
        with self._lock:
            s = self._channels.get(channel)
            if s:
                s.discard(client_id)
                if not s:
                    del self._channels[channel]
            cc = self._client_channels.get(client_id)
            if cc:
                cc.discard(channel)
        logger.debug("WS %s unsubscribed from %s", client_id, channel)
        return True

    def broadcast(self, channel, message, exclude=None):
        """Send message to all clients in a channel.
        @param channel: channel name
        @param message: dict (will be JSON-serialized)
        @param exclude: client_id to exclude (e.g. sender)
        """
        with self._lock:
            client_ids = list(self._channels.get(channel, []))
            targets = [
                self._clients[cid]
                for cid in client_ids
                if cid != exclude and cid in self._clients
            ]

        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for conn in targets:
            try:
                conn.send_text(text)
            except Exception:
                dead.append(conn.client_id)

        for cid in dead:
            self.remove_client(cid)

    def broadcast_all(self, message):
        """Send message to ALL connected clients."""
        with self._lock:
            targets = list(self._clients.values())

        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for conn in targets:
            try:
                conn.send_text(text)
            except Exception:
                dead.append(conn.client_id)

        for cid in dead:
            self.remove_client(cid)

    def send_to(self, client_id, message):
        """Send message to a specific client."""
        with self._lock:
            conn = self._clients.get(client_id)
        if conn:
            try:
                conn.send_json(message)
            except Exception:
                self.remove_client(client_id)

    def get_channel_clients(self, channel):
        """List client_ids subscribed to a channel."""
        with self._lock:
            return list(self._channels.get(channel, []))

    def get_client_count(self):
        """Total number of connected clients."""
        with self._lock:
            return len(self._clients)

    def get_channels(self):
        """List all active channels with client counts."""
        with self._lock:
            return {ch: len(ids) for ch, ids in self._channels.items()}


# ---- WebSocket Request Handler ----


class WebSocketRequestHandler(StreamRequestHandler):
    """Handles one WebSocket connection: HTTP upgrade then message loop."""

    def handle(self):
        """Main handler: upgrade → authenticate → message loop."""
        try:
            ok, params = self._do_handshake()
            if not ok:
                return

            if not self._authenticate(params):
                self.request.sendall(
                    b"HTTP/1.1 401 Unauthorized\r\n"
                    b"Content-Length: 12\r\n\r\nUnauthorized"
                )
                return

            client_id = "ws_%s_%d_%s" % (
                self.client_address[0],
                self.client_address[1],
                base64.urlsafe_b64encode(os.urandom(6)).decode("ascii"),
            )

            conn = WebSocketConnection(self.request, client_id, self.client_address)
            manager = self.server.ws_manager
            manager.add_client(conn)

            # Send welcome message
            conn.send_json(
                {
                    "event": "connected",
                    "data": {
                        "client_id": client_id,
                        "message": "WebBridge WebSocket connected",
                    },
                }
            )

            try:
                self._message_loop(conn)
            finally:
                manager.remove_client(client_id)
                conn.close()

        except (ConnectionError, OSError):
            pass
        except Exception:
            logger.exception("Error in WebSocket handler")

    def _do_handshake(self):
        """Perform HTTP → WebSocket upgrade handshake.
        Returns (True, query_params) on success, (False, None) on failure.
        """
        # Read HTTP request headers
        headers = {}
        request_line = (
            self.rfile.readline(8192).decode("utf-8", errors="replace").strip()
        )
        if not request_line:
            return False, None

        # Parse request line: GET /ws?token=xxx HTTP/1.1
        parts = request_line.split()
        if len(parts) < 3 or parts[0] != "GET":
            return False, None

        path = parts[1]
        query_params = {}
        if "?" in path:
            _, qs = path.split("?", 1)
            query_params = urllib.parse.parse_qs(qs)

        # Read headers
        while True:
            line = self.rfile.readline(8192).decode("utf-8", errors="replace").strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        # Validate WebSocket upgrade request
        if headers.get("upgrade", "").lower() != "websocket":
            self.request.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return False, None

        ws_key = headers.get("sec-websocket-key", "")
        if not ws_key:
            self.request.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return False, None

        # Compute accept key
        accept = base64.b64encode(
            hashlib.sha1(ws_key.encode("utf-8") + _WS_MAGIC).digest()
        ).decode("ascii")

        # Send upgrade response
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n" % accept
        )
        self.request.sendall(response.encode("utf-8"))
        return True, query_params

    def _authenticate(self, params):
        """Check auth token from query params.
        Returns True if authenticated or no auth required.
        """
        token = self.server.auth_token
        if not token:
            return True
        client_token = params.get("token", [""])[0]
        return client_token == token

    def _message_loop(self, conn):
        """Main message processing loop."""
        while not conn.is_closed:
            try:
                opcode, payload = conn.recv()
            except ConnectionError:
                break
            except Exception:
                logger.debug("WS recv error for %s", conn.client_id)
                break

            if opcode == OP_TEXT:
                try:
                    self._handle_message(conn, payload)
                except Exception:
                    logger.exception(
                        "Error handling WS message from %s", conn.client_id
                    )

    def _handle_message(self, conn, text):
        """Parse and dispatch a JSON message from the client."""
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            conn.send_json({"error": "Invalid JSON"})
            return

        if not isinstance(msg, dict):
            conn.send_json({"error": "Expected JSON object"})
            return

        action = msg.get("action", "")
        msg_id = msg.get("id")

        dispatch = {
            "subscribe": self._handle_action_subscribe,
            "unsubscribe": self._handle_action_unsubscribe,
            "broadcast": self._handle_action_broadcast,
            "api": self._handle_action_api,
            "ping": lambda c, m: self._send_reply(c, m.get("id"), True, {"pong": True}),
        }

        handler = dispatch.get(action)
        if handler:
            handler(conn, msg)
        else:
            self._send_reply(conn, msg_id, False, error="Unknown action: %s" % action)

    def _handle_action_subscribe(self, conn, msg):
        channel = msg.get("channel", "")
        msg_id = msg.get("id")
        if not channel:
            self._send_reply(conn, msg_id, False, error='Missing "channel"')
            return
        self.server.ws_manager.subscribe(conn.client_id, channel)
        self._send_reply(conn, msg_id, True, {"channel": channel})

    def _handle_action_unsubscribe(self, conn, msg):
        channel = msg.get("channel", "")
        msg_id = msg.get("id")
        if not channel:
            self._send_reply(conn, msg_id, False, error='Missing "channel"')
            return
        self.server.ws_manager.unsubscribe(conn.client_id, channel)
        self._send_reply(conn, msg_id, True, {"channel": channel})

    def _handle_action_broadcast(self, conn, msg):
        channel = msg.get("channel", "")
        data = msg.get("data", {})
        msg_id = msg.get("id")
        if not channel:
            self._send_reply(conn, msg_id, False, error='Missing "channel"')
            return
        broadcast_msg = {
            "event": "broadcast",
            "channel": channel,
            "data": data,
            "from": conn.client_id,
        }
        self.server.ws_manager.broadcast(channel, broadcast_msg, exclude=conn.client_id)
        self._send_reply(conn, msg_id, True)

    def _handle_action_api(self, conn, msg):
        """Proxy a REST API call through the WebSocket."""
        msg_id = msg.get("id")
        req = msg.get("data", {})
        method = req.get("method", "GET").upper()
        path = req.get("path", "")
        body = req.get("body")

        api = self.server.api
        if not api:
            self._send_reply(conn, msg_id, False, error="API not available")
            return

        if not path or not path.startswith("/api/"):
            self._send_reply(conn, msg_id, False, error="Invalid API path")
            return

        # Parse the path and query string
        if "?" in path:
            path_part, qs = path.split("?", 1)
            params = urllib.parse.parse_qs(qs)
        else:
            path_part = path
            params = {}

        api_path = path_part[5:]  # strip '/api/'
        parts = [urllib.parse.unquote(p) for p in api_path.split("/") if p]

        if not parts:
            self._send_reply(
                conn,
                msg_id,
                True,
                data={
                    "name": "WebBridge API",
                    "version": "2.5",
                },
            )
            return

        # Route to API method — delegate to a simple routing helper
        try:
            status, headers, result = self._route_api(api, method, parts, params, body)
            self._send_reply(conn, msg_id, status < 400, data=result)
        except Exception as e:
            logger.exception("WS API error: %s %s", method, path)
            self._send_reply(conn, msg_id, False, error=str(e))

    def _route_api(self, api, method, parts, params, body):
        """Route an API request to the appropriate NotebookAPI method.
        Returns (status, headers, body_dict).

        All JSON-based endpoints are supported.  Binary endpoints
        (attachment GET/POST, export/download) and lifecycle endpoints
        (_yield, applets install/update/delete) are intentionally
        excluded — use HTTP for those.
        """
        endpoint = parts[0]

        # ---- Notebook / meta ----
        if endpoint == "notebook" and method == "GET":
            return api.get_notebook_info()
        elif endpoint == "current" and method == "GET":
            return api.get_current_page()
        elif endpoint == "stats" and method == "GET":
            return api.get_stats()
        elif endpoint == "capabilities" and method == "GET":
            return api.get_capabilities()
        elif endpoint == "formats" and method == "GET":
            return api.list_formats()
        elif endpoint == "history" and method == "GET":
            limit = min(int(params.get("limit", ["50"])[0]), 200)
            return api.get_history(limit)

        # ---- Pages list / match / walk / count ----
        elif endpoint == "pages" and method == "GET":
            if len(parts) >= 2 and parts[1] == "match":
                query = params.get("q", [""])[0]
                limit = int(params.get("limit", ["10"])[0])
                return api.match_pages(query, min(limit, 50))
            elif len(parts) >= 2 and parts[1] == "walk":
                namespace = params.get("namespace", [None])[0]
                return api.walk_pages(namespace)
            elif len(parts) >= 2 and parts[1] == "count":
                namespace = params.get("namespace", [None])[0]
                return api.count_pages(namespace)
            namespace = params.get("namespace", [None])[0]
            limit_str = params.get("limit", [None])[0]
            offset = int(params.get("offset", ["0"])[0])
            limit = min(int(limit_str), 1000) if limit_str else None
            return api.list_pages_paginated(namespace, limit, offset)

        # ---- Page tree ----
        elif endpoint == "pagetree" and method == "GET":
            namespace = params.get("namespace", [None])[0]
            depth = min(int(params.get("depth", ["2"])[0]), 10)
            return api.get_page_tree(namespace, depth)

        # ---- Single page CRUD + sub-endpoints ----
        elif endpoint == "page" and len(parts) >= 2:
            last = parts[-1]

            # Sub-endpoints: /api/page/<path>/<sub>
            if last == "append" and method == "POST" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                content = (body or {}).get("content", "")
                fmt = (body or {}).get("format", "wiki")
                return api.append_to_page(page_path, content, fmt)

            elif last == "move" and method == "POST" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                new_path = (body or {}).get("newpath", "")
                update_links = (body or {}).get("update_links", True)
                if not new_path:
                    return 400, {}, {"error": 'Missing "newpath"'}
                return api.move_page(page_path, new_path, update_links)

            elif last == "trash" and method == "POST" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                return api.trash_page(page_path)

            elif last == "tags" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                if method == "GET":
                    return api.get_page_tags(page_path)
                elif method == "POST":
                    tag = (body or {}).get("tag", "")
                    if not tag:
                        return 400, {}, {"error": 'Missing "tag"'}
                    return api.add_tag_to_page(page_path, tag)
                elif method == "DELETE":
                    tag = params.get("tag", [""])[0]
                    if not tag:
                        return 400, {}, {"error": 'Missing "tag" param'}
                    return api.remove_tag_from_page(page_path, tag)

            elif last == "siblings" and method == "GET" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                return api.get_page_siblings(page_path)

            elif last == "parsetree" and method == "GET" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                return api.get_page_parsetree(page_path)

            elif last == "toc" and method == "GET" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                return api.get_page_toc(page_path)

            elif last == "analytics" and method == "GET" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                return api.get_page_analytics(page_path)

            elif last == "export" and method == "GET" and len(parts) >= 3:
                page_path = ":".join(parts[1:-1])
                fmt = params.get("format", ["html"])[0]
                return api.export_page(page_path, fmt)

            # Standard page CRUD
            page_path = ":".join(parts[1:])
            if method == "GET":
                fmt = params.get("format", ["wiki"])[0]
                return api.get_page(page_path, fmt)
            elif method == "PUT" and body:
                content = body.get("content", "")
                fmt = body.get("format", "wiki")
                expected_mtime = body.get("expected_mtime")
                if expected_mtime is not None:
                    try:
                        expected_mtime = float(expected_mtime)
                    except (ValueError, TypeError):
                        expected_mtime = None
                return api.save_page(page_path, content, fmt, expected_mtime)
            elif method == "PATCH" and body:
                operations = body.get("operations", [])
                expected_mtime = body.get("expected_mtime")
                if expected_mtime is not None:
                    try:
                        expected_mtime = float(expected_mtime)
                    except (ValueError, TypeError):
                        expected_mtime = None
                return api.patch_page(page_path, operations, expected_mtime)
            elif method == "POST" and body:
                content = body.get("content", "")
                fmt = body.get("format", "wiki")
                return api.create_page(page_path, content, fmt)
            elif method == "DELETE":
                return api.delete_page(page_path)

        # ---- Search ----
        elif endpoint == "search" and method == "GET":
            query = params.get("q", [""])[0]
            snippets = params.get("snippets", [""])[0].lower() in ("true", "1")
            if snippets:
                snippet_len = int(params.get("snippet_length", ["120"])[0])
                return api.search_pages_with_snippets(query, True, snippet_len)
            return api.search_pages(query)

        # ---- Tags ----
        elif endpoint == "tags" and method == "GET":
            if len(parts) == 1:
                return api.list_tags()
            elif len(parts) == 2 and parts[1] == "intersecting":
                tags_str = params.get("tags", [""])[0]
                tag_names = [t.strip() for t in tags_str.split(",") if t.strip()]
                if not tag_names:
                    return 400, {}, {"error": 'Missing "tags" param'}
                return api.get_intersecting_tags(tag_names)
            elif len(parts) >= 3 and parts[2] == "pages":
                return api.get_tag_pages(parts[1])

        # ---- Links ----
        elif endpoint == "links" and method == "GET":
            if len(parts) == 2 and parts[1] == "floating":
                return api.list_floating_links()
            if len(parts) >= 2:
                if parts[-1] == "count" and len(parts) >= 3:
                    page_path = ":".join(parts[1:-1])
                    direction = params.get("direction", ["forward"])[0]
                    return api.count_links(page_path, direction)
                if parts[-1] == "section" and len(parts) >= 3:
                    page_path = ":".join(parts[1:-1])
                    direction = params.get("direction", ["forward"])[0]
                    return api.get_links_section(page_path, direction)
                page_path = ":".join(parts[1:])
                direction = params.get("direction", ["forward"])[0]
                return api.get_links(page_path, direction)

        # ---- Attachments (list only — binary GET/POST via HTTP) ----
        elif endpoint == "attachments" and len(parts) >= 2 and method == "GET":
            page_path = ":".join(parts[1:])
            return api.list_attachments(page_path)

        # ---- Recent ----
        elif endpoint == "recent" and method == "GET":
            limit = min(int(params.get("limit", ["20"])[0]), 100)
            offset = int(params.get("offset", ["0"])[0])
            return api.get_recent_changes(limit, offset)

        # ---- Navigate ----
        elif endpoint == "navigate" and method == "POST" and body:
            return api.navigate_to_page(body.get("page", ""))

        # ---- Resolve / Create / Suggest Link ----
        elif endpoint == "resolve-link" and method == "POST" and body:
            return api.resolve_link(body.get("source", ""), body.get("link", ""))
        elif endpoint == "create-link" and method == "POST" and body:
            return api.create_link(body.get("source", ""), body.get("target", ""))
        elif endpoint == "suggest-link" and method == "GET":
            source = params.get("from", ["Home"])[0]
            text = params.get("text", [""])[0]
            return api.suggest_link(source, text)

        # ---- KV Store ----
        elif endpoint == "store" and len(parts) >= 2:
            applet = parts[1]
            key = parts[2] if len(parts) >= 3 else None
            if method == "GET":
                return api.store_get(applet, key)
            elif method == "PUT" and key and body:
                value = body.get("value", body)
                return api.store_put(applet, key, value)
            elif method == "DELETE" and key:
                return api.store_delete(applet, key)

        # ---- Batch ----
        elif endpoint == "batch" and method == "POST" and body:
            operations = body if isinstance(body, list) else body.get("operations", [])
            return api.batch(operations)

        # ---- Emit Custom Event ----
        elif endpoint == "emit" and method == "POST" and body:
            return api.emit_custom_event(body.get("event", ""), body.get("data", {}))

        # ---- Analysis ----
        elif endpoint == "analysis" and method == "GET":
            if len(parts) >= 2 and parts[1] == "orphans":
                return api.get_orphan_pages()
            elif len(parts) >= 2 and parts[1] == "dead-links":
                return api.get_dead_links()

        # ---- Graph ----
        elif endpoint == "graph" and method == "GET":
            namespace = params.get("namespace", [None])[0]
            return api.get_graph(namespace)

        # ---- Templates ----
        elif endpoint == "templates" and method == "GET":
            fmt = params.get("format", [None])[0]
            return api.list_templates(fmt)

        # ---- Sitemap (JSON only) ----
        elif endpoint == "sitemap" and method == "GET":
            return api.get_sitemap("json", "")

        # ---- Applets (read-only via WS) ----
        elif endpoint == "applets" and method == "GET":
            if len(parts) == 1:
                if hasattr(api, "applet_manager") and api.applet_manager:
                    api.applet_manager.refresh()
                    applets = api.applet_manager.list_applets()
                    return 200, {}, {"applets": applets}
                return 200, {}, {"applets": []}
            elif len(parts) >= 3 and parts[2] == "config":
                return api.get_applet_config(parts[1])
            elif len(parts) >= 3 and parts[2] == "source":
                return api.get_applet_source(parts[1])
        elif endpoint == "applets" and method == "PUT":
            if len(parts) >= 3 and parts[2] == "config" and body:
                return api.save_applet_config(parts[1], body)

        return (
            404,
            {},
            {
                "error": "Unknown or unsupported WS API endpoint: %s %s"
                % (method, "/".join(parts))
            },
        )

    def _send_reply(self, conn, msg_id, ok, data=None, error=None):
        """Send a reply to a client request."""
        reply = {"ok": ok}
        if msg_id is not None:
            reply["id"] = msg_id
        if data is not None:
            reply["data"] = data
        if error is not None:
            reply["error"] = error
        conn.send_json(reply)


# ---- WebSocket Server ----


class WebSocketTCPServer(ThreadingTCPServer):
    """Threaded TCP server for WebSocket connections."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, server_address, handler_class, manager, auth_token=None, api=None
    ):
        self.ws_manager = manager
        self.auth_token = auth_token
        self.api = api  # NotebookAPI instance for proxied API calls
        super().__init__(server_address, handler_class)


# ---- Factory ----


def create_ws_server(port, bind_address="localhost", auth_token=None, api=None):
    """Create a WebSocket server.

    @param port: TCP port to listen on
    @param bind_address: address to bind to
    @param auth_token: optional auth token
    @param api: NotebookAPI instance for proxied API calls
    @returns: (WebSocketTCPServer, WebSocketManager)
    """
    manager = WebSocketManager()
    server = WebSocketTCPServer(
        (bind_address, port),
        WebSocketRequestHandler,
        manager,
        auth_token=auth_token,
        api=api,
    )
    logger.info("WebSocket server created on %s:%d", bind_address, port)
    return server, manager
