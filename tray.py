# -*- coding: utf-8 -*-
"""System tray icon for Moonstone.

Uses pystray + Pillow for the tray icon, tkinter for dialogs.
Provides a context menu to configure and control the server.
"""

import logging
import os
import threading
import webbrowser

logger = logging.getLogger("moonstone.tray")


def _create_moon_icon(size=64):
    """Generate a crescent moon icon using Pillow.

    @param size: icon size in pixels
    @returns: PIL.Image
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Full circle (moon body) — warm amber
    draw.ellipse([4, 4, size - 4, size - 4], fill=(230, 180, 60, 255))

    # Shadow ellipse to make crescent — offset to the right
    shadow_offset = size // 4
    draw.ellipse(
        [4 + shadow_offset, 2, size - 4 + shadow_offset, size - 2],
        fill=(0, 0, 0, 0),
    )

    return img


def _ask_string(title, prompt, initial=""):
    """Show a tkinter input dialog in a temporary root window.

    @returns: string value or None if cancelled
    """
    result = [None]

    def _run():
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        val = simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
        result[0] = val
        root.destroy()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    return result[0]


def _ask_integer(title, prompt, initial=0, minvalue=1, maxvalue=65535):
    """Show a tkinter integer input dialog.

    @returns: int value or None if cancelled
    """
    result = [None]

    def _run():
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        val = simpledialog.askinteger(
            title,
            prompt,
            initialvalue=initial,
            minvalue=minvalue,
            maxvalue=maxvalue,
            parent=root,
        )
        result[0] = val
        root.destroy()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    return result[0]


def _ask_directory(title="Select directory", initial=None):
    """Show a tkinter directory chooser dialog.

    @returns: path string or None if cancelled
    """
    result = [None]

    def _run():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        kwargs = {"title": title, "parent": root}
        if initial and os.path.isdir(initial):
            kwargs["initialdir"] = initial
        val = filedialog.askdirectory(**kwargs)
        result[0] = val if val else None
        root.destroy()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    return result[0]


class MoonstoneTray:
    """System tray icon for Moonstone server.

    Provides a context menu for configuration and server control.
    Runs pystray in the main thread (required by some backends).

    @param settings: dict — current settings (mutable, shared with server)
    @param on_restart: callable — restart the server with current settings
    @param on_quit: callable — shutdown everything
    @param server_info: callable — returns dict with server status info
    @param save_settings: callable — persist settings to disk
    """

    def __init__(
        self, settings, on_restart, on_quit, server_info=None, save_settings=None
    ):
        self._settings = settings
        self._on_restart = on_restart
        self._on_quit = on_quit
        self._server_info = server_info or (lambda: {})
        self._save_settings = save_settings
        self._icon = None

    def _save(self):
        """Persist current settings."""
        if self._save_settings:
            self._save_settings(self._settings)

    def _get_info(self):
        """Get current server info dict."""
        return self._server_info()

    # ---- Menu actions ----

    def _open_dashboard(self, icon, item):
        info = self._get_info()
        url = info.get("url", "http://localhost:%d" % self._settings.get("port", 8090))
        webbrowser.open(url)

    def _change_notebook(self, icon, item):
        current = self._settings.get("notebook", "")
        path = _ask_directory("Select notebook directory", initial=current)
        if path and path != current:
            self._settings["notebook"] = path
            self._save()
            self._restart_server()

    def _change_port(self, icon, item):
        current = self._settings.get("port", 8090)
        val = _ask_integer("Port", "HTTP port:", initial=current)
        if val is not None and val != current:
            self._settings["port"] = val
            self._save()
            self._restart_server()

    def _change_host(self, icon, item):
        current = self._settings.get("host", "localhost")
        val = _ask_string("Host", "Host to bind to:", initial=current)
        if val is not None and val != current:
            self._settings["host"] = val
            self._save()
            self._restart_server()

    def _change_token(self, icon, item):
        current = self._settings.get("token", "")
        val = _ask_string(
            "Auth Token", "Auth token (empty = no auth):", initial=current
        )
        if val is not None and val != current:
            self._settings["token"] = val
            self._save()
            self._restart_server()

    def _change_ws_port(self, icon, item):
        current = self._settings.get("ws_port") or (
            self._settings.get("port", 8090) + 1
        )
        val = _ask_integer(
            "WebSocket Port",
            "WebSocket port (0 = disable):",
            initial=current,
            minvalue=0,
        )
        if val is not None:
            self._settings["ws_port"] = val if val > 0 else 0
            self._save()
            self._restart_server()

    def _change_applets_dir(self, icon, item):
        current = self._settings.get("applets_dir", "")
        path = _ask_directory("Select applets directory", initial=current)
        if path:
            self._settings["applets_dir"] = path
            self._save()
            self._restart_server()

    def _change_services_dir(self, icon, item):
        current = self._settings.get("services_dir", "")
        path = _ask_directory("Select services directory", initial=current)
        if path:
            self._settings["services_dir"] = path
            self._save()
            self._restart_server()

    def _set_profile(self, profile_name):
        def _action(icon, item):
            if self._settings.get("profile") != profile_name:
                self._settings["profile"] = profile_name
                self._save()
                self._restart_server()

        return _action

    def _is_profile(self, profile_name):
        def _check(item):
            return self._settings.get("profile", "auto") == profile_name

        return _check

    def _set_logging(self, level):
        def _action(icon, item):
            self._settings["verbose"] = level == "verbose"
            self._settings["debug"] = level == "debug"
            self._save()
            # Logging can be changed live
            root_logger = logging.getLogger()
            if level == "debug":
                root_logger.setLevel(logging.DEBUG)
            elif level == "verbose":
                root_logger.setLevel(logging.INFO)
            else:
                root_logger.setLevel(logging.WARNING)
            logger.info("Logging level changed to %s", level)

        return _action

    def _is_logging(self, level):
        def _check(item):
            if level == "debug":
                return self._settings.get("debug", False)
            elif level == "verbose":
                return self._settings.get("verbose", False) and not self._settings.get(
                    "debug", False
                )
            else:
                return not self._settings.get(
                    "verbose", False
                ) and not self._settings.get("debug", False)

        return _check

    def _restart_server(self):
        """Request server restart in a background thread."""
        logger.info("Restart requested from tray")
        threading.Thread(target=self._on_restart, daemon=True).start()
        # Update the tray menu
        if self._icon:
            self._icon.update_menu()

    def _do_restart(self, icon, item):
        self._restart_server()

    def _do_quit(self, icon, item):
        logger.info("Quit requested from tray")
        if self._icon:
            self._icon.stop()
        self._on_quit()

    # ---- Menu building ----

    def _build_menu(self):
        import pystray

        info = self._get_info()
        notebook = self._settings.get("notebook", "") or "(not set)"
        # Shorten long paths
        if len(notebook) > 40:
            notebook = "..." + notebook[-37:]

        status = info.get("status", "not running")
        n_pages = info.get("n_pages", "?")
        profile = info.get("profile", self._settings.get("profile", "auto"))
        port = self._settings.get("port", 8090)
        host = self._settings.get("host", "localhost")

        return pystray.Menu(
            pystray.MenuItem("🌉 Moonstone", None, enabled=False),
            pystray.MenuItem(
                "Server: %s" % status,
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                "Pages: %s | Profile: %s" % (n_pages, profile),
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📂 Open Dashboard", self._open_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "📁 Notebook: %s" % notebook,
                self._change_notebook,
            ),
            pystray.MenuItem(
                "Port: %d" % port,
                self._change_port,
            ),
            pystray.MenuItem(
                "Host: %s" % host,
                self._change_host,
            ),
            pystray.MenuItem(
                "Auth Token: %s" % ("***" if self._settings.get("token") else "(none)"),
                self._change_token,
            ),
            pystray.MenuItem(
                "WebSocket Port: %s" % (self._settings.get("ws_port") or "auto"),
                self._change_ws_port,
            ),
            pystray.MenuItem(
                "Applets Dir...",
                self._change_applets_dir,
            ),
            pystray.MenuItem(
                "Services Dir...",
                self._change_services_dir,
            ),
            pystray.MenuItem(
                "Profile",
                pystray.Menu(
                    pystray.MenuItem(
                        "Auto",
                        self._set_profile("auto"),
                        checked=self._is_profile("auto"),
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Moonstone",
                        self._set_profile("moonstone"),
                        checked=self._is_profile("moonstone"),
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Obsidian",
                        self._set_profile("obsidian"),
                        checked=self._is_profile("obsidian"),
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Logseq",
                        self._set_profile("logseq"),
                        checked=self._is_profile("logseq"),
                        radio=True,
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Logging",
                pystray.Menu(
                    pystray.MenuItem(
                        "Normal",
                        self._set_logging("normal"),
                        checked=self._is_logging("normal"),
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Verbose",
                        self._set_logging("verbose"),
                        checked=self._is_logging("verbose"),
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Debug",
                        self._set_logging("debug"),
                        checked=self._is_logging("debug"),
                        radio=True,
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔄 Restart Server", self._do_restart),
            pystray.MenuItem("❌ Quit", self._do_quit),
        )

    def run(self):
        """Start the tray icon (blocks the calling thread)."""
        import pystray

        icon_image = _create_moon_icon()
        self._icon = pystray.Icon(
            "moonstone",
            icon_image,
            "Moonstone",
            menu=self._build_menu(),
        )
        logger.info("System tray icon started")
        self._icon.run()

    def stop(self):
        """Stop the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def update_menu(self):
        """Refresh the menu (e.g. after settings change)."""
        if self._icon:
            self._icon.menu = self._build_menu()
            try:
                self._icon.update_menu()
            except Exception:
                pass
