# -*- coding: utf-8 -*-
"""Moonstone notebook package.

Provides Path, HRef, Page, Notebook and related classes — drop-in
standalone replacements for the notebook layer used by WebBridge api.py.
"""

from moonstone.notebook.page import (
    Path,
    HRef,
    HREF_REL_ABSOLUTE,
    HREF_REL_FLOATING,
    HREF_REL_RELATIVE,
)
from moonstone.notebook.info import NotebookInfo, resolve_notebook
from moonstone.notebook.layout import encode_filename, decode_filename
from moonstone.errors import (
    PageNotFoundError,
    PageExistsError,
    TrashNotSupportedError,
    IndexNotFoundError,
)

# Link direction constants (re-exported for compatibility)
from moonstone.notebook.index.links import (
    LINK_DIR_FORWARD,
    LINK_DIR_BACKWARD,
    LINK_DIR_BOTH,
)


def build_notebook(location, profile=None):
    """Create a Notebook object from a NotebookInfo or path string.

    @param location: a NotebookInfo object or a path string
    @param profile: optional vault profile (BaseProfile instance or None for auto-detect)
    @returns: (Notebook, None) tuple for compatibility with Moonstone API
    """
    from moonstone.notebook.notebook import Notebook

    if isinstance(location, NotebookInfo):
        folder = location.path
    elif isinstance(location, str):
        folder = location
    elif hasattr(location, "uri"):
        folder = location.uri
        if folder.startswith("file://"):
            folder = folder[7:]
    else:
        folder = str(location)

    notebook = Notebook(folder, profile=profile)
    return notebook, None
