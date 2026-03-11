# -*- coding: utf-8 -*-
"""Simple observer-pattern signal system.

Replaces legacy signals.SignalEmitter — provides connect/emit/disconnect
without any dependency on GObject/GLib.
"""

import threading

SIGNAL_NORMAL = 0


class SignalEmitter:
    """Mixin class that provides signal connect/emit/disconnect.

    Usage::

        class MyObj(SignalEmitter):
            pass

        obj = MyObj()
        handler_id = obj.connect('my-signal', callback)
        obj.emit('my-signal', arg1, arg2)
        obj.disconnect(handler_id)
    """

    def __init__(self):
        self._signal_handlers = {}  # signal_name -> {id: callback}
        self._signal_counter = 0
        self._signal_lock = threading.Lock()

    def connect(self, signal_name, callback):
        """Connect a callback to a signal.

        @param signal_name: string name of the signal
        @param callback: callable to invoke when signal is emitted
        @returns: handler_id (int) for use with disconnect()
        """
        with self._signal_lock:
            self._signal_counter += 1
            handler_id = self._signal_counter
            if signal_name not in self._signal_handlers:
                self._signal_handlers[signal_name] = {}
            self._signal_handlers[signal_name][handler_id] = callback
            return handler_id

    def disconnect(self, handler_id):
        """Disconnect a previously connected handler.

        @param handler_id: the id returned by connect()
        """
        with self._signal_lock:
            for handlers in self._signal_handlers.values():
                if handler_id in handlers:
                    del handlers[handler_id]
                    return

    def emit(self, signal_name, *args):
        """Emit a signal, calling all connected handlers.

        @param signal_name: string name of the signal
        @param args: arguments to pass to handlers
        """
        with self._signal_lock:
            handlers = self._signal_handlers.get(signal_name, {})
            callbacks = list(handlers.values())
        for callback in callbacks:
            try:
                callback(self, *args)
            except Exception:
                import logging

                logging.getLogger("moonstone.signals").exception(
                    "Error in signal handler for %r", signal_name
                )

    def _ensure_signals(self):
        """Ensure signal infrastructure is initialized.
        Called by subclasses that don't call __init__.
        """
        if not hasattr(self, "_signal_handlers"):
            self._signal_handlers = {}
            self._signal_counter = 0
            self._signal_lock = threading.Lock()
