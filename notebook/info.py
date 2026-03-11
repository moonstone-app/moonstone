# -*- coding: utf-8 -*-
"""NotebookInfo and resolve_notebook for Moonstone.

Standalone notebook info module — provides notebook discovery and metadata.
"""

import os


class NotebookInfo:
    """Metadata holder for a notebook location.

    Stores the path and parsed notebook.moon config.
    """

    def __init__(self, uri=None, name=None, path=None, **kwargs):
        if path:
            self.path = os.path.abspath(path)
            self.uri = "file://" + self.path
        elif uri:
            if uri.startswith("file://"):
                self.path = uri[7:]
            else:
                self.path = os.path.abspath(uri)
            self.uri = uri
        else:
            self.path = ""
            self.uri = ""

        self.name = name or os.path.basename(self.path)
        self.icon = kwargs.get("icon", "")
        self.interwiki = kwargs.get("interwiki", "")

    def __eq__(self, other):
        if isinstance(other, NotebookInfo):
            return self.path == other.path
        return False

    def __repr__(self):
        return "<NotebookInfo: %s>" % self.path


def resolve_notebook(string, pwd=None):
    """Resolve a string to a NotebookInfo.

    @param string: path to a notebook directory
    @param pwd: working directory for relative paths
    @returns: NotebookInfo or None
    """
    from moonstone.profiles import get_all_config_markers

    NOTEBOOK_CONFIGS = get_all_config_markers()

    if pwd:
        path = os.path.join(pwd, string)
    else:
        path = os.path.abspath(string)

    # Check if it's a notebook directory
    if os.path.isdir(path):
        for config_name in NOTEBOOK_CONFIGS:
            config_file = os.path.join(path, config_name)
            if os.path.isfile(config_file):
                return NotebookInfo(path=path)

        # Check parent directories
        current = path
        for _ in range(10):
            parent = os.path.dirname(current)
            if parent == current:
                break
            for config_name in NOTEBOOK_CONFIGS:
                if os.path.isfile(os.path.join(parent, config_name)):
                    return NotebookInfo(path=parent)
            current = parent

        # No config found, but directory exists — allow it
        # (headless may work with a bare directory)
        return NotebookInfo(path=path)

    elif os.path.isfile(path) and os.path.basename(path) in NOTEBOOK_CONFIGS:
        return NotebookInfo(path=os.path.dirname(path))

    return None
