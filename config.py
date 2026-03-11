# -*- coding: utf-8 -*-
"""Config utilities for Moonstone.

Standalone config module — provides data_dirs() for template/data discovery.
"""

import os
import sys


def data_dirs(subdir=None):
    """Yield directories to search for data files (templates, etc.).

    Uses XDG conventions:
    1. $XDG_DATA_HOME/moonstone/  (typically ~/.local/share/moonstone/)
    2. Each dir in $XDG_DATA_DIRS plus /moonstone/
    3. Package data directory

    @param subdir: optional subdirectory (e.g. 'templates')
    @returns: iterator of pathlib-compatible path strings
    """
    dirs = []

    # XDG_DATA_HOME
    xdg_data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    dirs.append(os.path.join(xdg_data_home, "moonstone"))

    # XDG_DATA_DIRS
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for d in xdg_data_dirs.split(":"):
        if d:
            dirs.append(os.path.join(d, "moonstone"))

    # PyInstaller frozen binary: data extracted to sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        dirs.append(os.path.join(sys._MEIPASS, "moonstone", "data"))

    # Package bundled data: moonstone/data/
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(pkg_dir, "data"))

    # Fallback: sibling data/ (for dev layout)
    dirs.append(os.path.join(os.path.dirname(pkg_dir), "data"))

    for d in dirs:
        if subdir:
            path = os.path.join(d, subdir)
        else:
            path = d
        if os.path.isdir(path):
            yield path
