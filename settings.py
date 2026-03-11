# -*- coding: utf-8 -*-
"""Persistent settings for Moonstone.

Stores configuration in ~/.config/moonstone/settings.json.
CLI arguments override saved settings; changes from tray are persisted.
"""

import json
import os

_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "moonstone",
)
_SETTINGS_FILE = os.path.join(_CONFIG_DIR, "settings.json")

_DEFAULTS = {
    "notebook": "",
    "port": 8090,
    "host": "localhost",
    "token": "",
    "ws_port": None,
    "applets_dir": None,
    "services_dir": None,
    "verbose": False,
    "debug": False,
}


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)


def load():
    """Load settings from disk, merged with defaults.

    @returns: dict with all settings
    """
    settings = dict(_DEFAULTS)
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save(settings):
    """Save settings dict to disk.

    @param settings: dict (only known keys are saved)
    """
    _ensure_dir()
    data = {k: settings[k] for k in _DEFAULTS if k in settings}
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def merge_cli_args(args, saved):
    """Merge CLI arguments over saved settings.

    CLI args take priority; unset CLI args fall back to saved values.

    @param args: argparse.Namespace
    @param saved: dict from load()
    @returns: dict with final settings
    """
    result = dict(saved)

    # All flags that should overwrite saved settings if explicitly provided
    explicitly_set = getattr(args, "_explicit", set())

    # notebook: CLI positional arg
    if "notebook" in explicitly_set and getattr(args, "notebook", None):
        result["notebook"] = os.path.abspath(args.notebook)
    elif "notebook" not in explicitly_set and getattr(args, "notebook", None) and not result.get("notebook"):
        # Fallback if somehow it's provided but not in explicit, and we don't have one
        result["notebook"] = os.path.abspath(args.notebook)

    # port
    if "port" in explicitly_set:
        result["port"] = args.port
    elif getattr(args, "port", None) is not None and args.port != _DEFAULTS["port"]:
        result["port"] = args.port
    elif not result.get("port"):
        result["port"] = _DEFAULTS["port"]

    # host
    if "host" in explicitly_set:
        result["host"] = args.host
    elif getattr(args, "host", None) and args.host != _DEFAULTS["host"]:
        result["host"] = args.host

    # token
    if "token" in explicitly_set:
        result["token"] = args.token
    elif getattr(args, "token", None) and args.token != _DEFAULTS["token"]:
        result["token"] = args.token

    # ws_port
    if "ws_port" in explicitly_set:
        result["ws_port"] = args.ws_port
    elif getattr(args, "ws_port", None) is not None:
        result["ws_port"] = args.ws_port

    # applets_dir
    if "applets_dir" in explicitly_set:
        result["applets_dir"] = args.applets_dir
    elif getattr(args, "applets_dir", None):
        result["applets_dir"] = args.applets_dir

    # services_dir
    if "services_dir" in explicitly_set:
        result["services_dir"] = args.services_dir
    elif getattr(args, "services_dir", None):
        result["services_dir"] = args.services_dir

    # profile
    if "profile" in explicitly_set:
        result["profile"] = args.profile
    elif getattr(args, "profile", "auto") != "auto":
        result["profile"] = args.profile

    # verbose / debug
    if getattr(args, "verbose", False):
        result["verbose"] = True
    if getattr(args, "debug", False):
        result["debug"] = True

    return result
