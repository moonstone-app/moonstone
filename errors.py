# -*- coding: utf-8 -*-
"""Exception classes for Moonstone.

Standalone error classes and notebook-specific exceptions.
"""


class MoonstoneError(Exception):
    """Base exception for all Moonstone errors."""

    pass


class PageNotFoundError(MoonstoneError):
    """Raised when a page does not exist."""

    def __init__(self, path):
        self.path = path
        super().__init__("Page not found: %s" % path)


class PageExistsError(MoonstoneError):
    """Raised when trying to create a page that already exists."""

    def __init__(self, path):
        self.path = path
        super().__init__("Page already exists: %s" % path)


class PageReadOnlyError(MoonstoneError):
    """Raised when trying to modify a read-only page."""

    def __init__(self, path):
        self.path = path
        super().__init__("Can not modify page: %s" % path)


class NotebookError(MoonstoneError):
    """General notebook error."""

    pass


class IndexNotFoundError(MoonstoneError):
    """Raised when the index database is not found."""

    pass


class TrashNotSupportedError(MoonstoneError):
    """Raised when trash is not available."""

    pass
