# -*- coding: UTF-8 -*-

"""Server-Sent Events (SSE) manager for WebBridge.

Provides real-time notifications to web applets about changes
in the Moonstone notebook (page changes, saves, etc.).
"""

import json
import logging
import threading
import time
import queue

logger = logging.getLogger("moonstone.webbridge")


class EventManager:
    """Manages SSE (Server-Sent Events) connections.

    Thread-safe: events can be emitted from any thread (GTK main loop)
    and will be delivered to all connected SSE clients.
    """

    def __init__(self):
        self._clients = []  # list of queue.Queue objects
        self._lock = threading.Lock()
        self._event_id = 0
        self._ws_manager = (
            None  # WebSocketManager instance (set after WS server starts)
        )

    def set_ws_manager(self, ws_manager):
        """Attach a WebSocketManager so that emit() also broadcasts to WS clients.
        @param ws_manager: WebSocketManager instance or None to detach
        """
        self._ws_manager = ws_manager

    def add_client(self):
        """Register a new SSE client.
        @returns: a queue.Queue that will receive events
        """
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._clients.append(q)
        logger.debug("SSE client connected (total: %d)", len(self._clients))
        return q

    def remove_client(self, q):
        """Unregister an SSE client.
        @param q: the Queue returned by add_client()
        """
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass
        logger.debug("SSE client disconnected (total: %d)", len(self._clients))

    def emit(self, event_type, data=None):
        """Emit an event to all connected clients.
        @param event_type: event name (e.g. 'page-changed', 'page-saved')
        @param data: dict with event data (will be JSON-serialized)
        """
        with self._lock:
            self._event_id += 1
            event = {
                "id": self._event_id,
                "type": event_type,
                "data": data or {},
                "timestamp": time.time(),
            }
            dead_clients = []
            for q in self._clients:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead_clients.append(q)

            for q in dead_clients:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass

        if dead_clients:
            logger.debug("Removed %d dead SSE clients", len(dead_clients))

        # Broadcast to WebSocket clients (if WS server is attached)
        ws = self._ws_manager
        if ws:
            try:
                ws.broadcast(
                    "global",
                    {
                        "event": event_type,
                        "data": data or {},
                    },
                )
            except Exception:
                logger.debug("Failed to broadcast event to WS clients")

    def format_sse(self, event):
        """Format an event dict as SSE text.
        @param event: event dict with 'id', 'type', 'data'
        @returns: SSE-formatted string

        Custom events (type starting with 'custom:') are sent without
        the 'event:' field so they arrive via EventSource.onmessage
        in the browser. The event type is embedded in the data payload.
        """
        lines = []
        lines.append("id: %d" % event["id"])
        if event["type"].startswith("custom:"):
            # Send as unnamed SSE event (no 'event:' line) so the browser's
            # onmessage handler picks it up; embed type inside data.
            data = dict(event["data"])
            data["type"] = event["type"]
            lines.append("data: %s" % json.dumps(data))
        else:
            lines.append("event: %s" % event["type"])
            lines.append("data: %s" % json.dumps(event["data"]))
        lines.append("")
        lines.append("")  # Double newline to end SSE message
        return "\n".join(lines)

    def generate_events(self, client_queue, timeout=30, subscribe=None):
        """Generator that yields SSE-formatted events for a client.
        This is a blocking generator, intended for use in a WSGI handler.

        @param client_queue: Queue returned by add_client()
        @param timeout: seconds to wait before sending a keepalive comment
        @param subscribe: optional set of event types to filter (None = all)
        @yields: SSE-formatted strings
        """
        # Send initial connection event
        yield self.format_sse(
            {
                "id": 0,
                "type": "connected",
                "data": {"message": "WebBridge SSE connected"},
                "timestamp": time.time(),
            }
        )

        while True:
            try:
                event = client_queue.get(timeout=timeout)
                # Filter events if subscribe set is provided
                if subscribe and event["type"] not in subscribe:
                    continue
                yield self.format_sse(event)
            except queue.Empty:
                # Send keepalive comment
                yield ": keepalive\n\n"
