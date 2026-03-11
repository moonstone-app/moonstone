# -*- coding: utf-8 -*-
"""Main loop replacement for GLib.MainLoop.

Provides a stdlib-only main loop + idle_add replacement, so that
WebBridge can work without PyGObject/GLib.
"""

import queue
import signal
import threading
import logging

logger = logging.getLogger("moonstone.mainloop")


class MainLoop:
    """Replacement for GLib.MainLoop using stdlib threading.

    Usage::
        loop = MainLoop()
        # start your HTTP/WS servers in threads...
        loop.run()   # blocks until quit() or SIGINT/SIGTERM
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._task_queue = queue.Queue()
        self._running = False

    def run(self):
        """Run the main loop (blocks current thread).

        Processes tasks from idle_add and waits for quit().
        """
        self._running = True

        # Install signal handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def _shutdown(signum, frame):
            logger.info("Received signal %s, shutting down...", signum)
            self.quit()

        try:
            signal.signal(signal.SIGINT, _shutdown)
            signal.signal(signal.SIGTERM, _shutdown)
        except (OSError, ValueError):
            # signal handling not available (e.g., not in main thread)
            pass

        try:
            while not self._stop_event.is_set():
                try:
                    task = self._task_queue.get(timeout=0.5)
                    if task is None:
                        break
                    try:
                        task()
                    except Exception:
                        logger.exception("Error in idle task")
                except queue.Empty:
                    continue
        finally:
            self._running = False
            # Restore original signal handlers
            try:
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)
            except (OSError, ValueError):
                pass

    def quit(self):
        """Stop the main loop."""
        self._stop_event.set()
        self._task_queue.put(None)  # unblock the get()

    def is_running(self):
        return self._running


# ---- idle_add replacement ----

_notebook_lock = threading.RLock()


def idle_add(func, *args):
    """Schedule a function to run on the main thread.

    In Moonstone headless mode, we use RLock + WAL for thread safety
    (no actual main-thread dispatch needed). This is a simplified
    replacement that just runs the function immediately with a lock.

    For full GLib.idle_add compatibility, see _run_on_main_thread
    in api.py which wraps this.
    """
    with _notebook_lock:
        if args:
            return func(*args)
        return func()
