# -*- coding: utf-8 -*-
"""Page, Path, and HRef classes for Moonstone.

Standalone page module — provides the same
duck-typing interface that WebBridge api.py expects.
"""

import re
import os
import hashlib
from datetime import datetime, timezone

from moonstone.signals import SignalEmitter
from moonstone.errors import PageReadOnlyError

# ---- Page name validation ----

_pagename_reduce_colon_re = re.compile("::+")
_pagename_invalid_char_re = re.compile(
    "("
    + r"^(?!;)[_\W]+|(?<=:)(?!;)[_\W]+"
    + "|"
    + "["
    + re.escape(
        "".join(("?", "#", "/", "\\", "*", '"', "<", ">", "|", "%", "\t", "\n", "\r"))
    )
    + "]"
    + ")",
    re.UNICODE,
)


# ---- HRef rel flavors ----

HREF_REL_ABSOLUTE = 0
HREF_REL_FLOATING = 1
HREF_REL_RELATIVE = 2


def heading_to_anchor(text):
    """Convert heading text to a valid anchor string."""
    anchor = text.strip().lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"[\s]+", "-", anchor)
    return anchor


class Path:
    """Represents a page name in the notebook.

    Compatible with Path interface — provides name, basename,
    namespace, parent, parts, isroot, child(), ischild(), etc.
    """

    __slots__ = ("name",)

    @staticmethod
    def assertValidPageName(name):
        """Raises AssertionError if name is not valid."""
        assert isinstance(name, str)
        if (
            not name.strip(":")
            or _pagename_reduce_colon_re.search(name)
            or _pagename_invalid_char_re.search(name)
        ):
            raise AssertionError("Not a valid page name: %s" % name)

    @staticmethod
    def makeValidPageName(name):
        """Clean up and return a valid page name string."""
        newname = _pagename_reduce_colon_re.sub(":", name.strip(":"))
        newname = _pagename_invalid_char_re.sub("", newname)
        newname = newname.replace("_", " ")
        try:
            Path.assertValidPageName(newname)
        except AssertionError:
            raise ValueError("Not a valid page name: %s (was: %s)" % (newname, name))
        return newname

    def __init__(self, name):
        if isinstance(name, (list, tuple)):
            self.name = ":".join(name)
        else:
            self.name = name.strip(":")

    @classmethod
    def new_from_config(cls, string):
        return cls(cls.makeValidPageName(string))

    def serialize_config(self):
        return self.name

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.name)

    def __str__(self):
        return self.name

    def __hash__(self):
        return self.name.__hash__()

    def __eq__(self, other):
        if isinstance(other, Path):
            return self.name == other.name
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __add__(self, name):
        return self.child(name)

    @property
    def parts(self):
        return self.name.split(":") if self.name else []

    @property
    def basename(self):
        i = self.name.rfind(":") + 1
        return self.name[i:]

    @property
    def namespace(self):
        i = self.name.rfind(":")
        if i > 0:
            return self.name[:i]
        return ""

    @property
    def isroot(self):
        return self.name == ""

    @property
    def parent(self):
        namespace = self.namespace
        if namespace:
            return Path(namespace)
        elif self.isroot:
            return None
        else:
            return Path(":")

    def parents(self):
        """Generator for parent Paths including root."""
        if ":" in self.name:
            path = self.name.split(":")
            path.pop()
            while len(path) > 0:
                yield Path(":".join(path))
                path.pop()
        yield Path(":")

    def child(self, basename):
        if self.isroot:
            return Path(basename)
        return Path(self.name + ":" + basename)

    def ischild(self, parent):
        return parent.isroot or self.name.startswith(parent.name + ":")

    def match_namespace(self, namespace):
        return (
            namespace.isroot
            or self.name == namespace.name
            or self.name.startswith(namespace.name + ":")
        )

    def relname(self, path):
        if path.name == "":
            return self.name
        elif self.name.startswith(path.name + ":"):
            i = len(path.name) + 1
            return self.name[i:].strip(":")
        else:
            raise ValueError('"%s" is not below "%s"' % (self, path))

    def commonparent(self, other):
        parent = []
        parts = self.parts
        other_parts = other.parts
        if not parts or not other_parts or parts[0] != other_parts[0]:
            return Path(":")
        for i in range(min(len(parts), len(other_parts))):
            if parts[i] == other_parts[i]:
                parent.append(parts[i])
            else:
                break
        return Path(":".join(parent)) if parent else Path(":")


class HRef:
    """Represents a wiki link — link type + target names + optional anchor.

    Compatible with HRef interface.
    """

    __slots__ = ("rel", "names", "anchor")

    # Expose class-level constants for duck-typing compatibility
    REL_RELATIVE = HREF_REL_RELATIVE
    REL_ABSOLUTE = HREF_REL_ABSOLUTE
    REL_FLOATING = HREF_REL_FLOATING

    @classmethod
    def makeValidHRefString(cls, href):
        return cls.new_from_wiki_link(href).to_wiki_link()

    @classmethod
    def new_from_wiki_link(cls, href):
        """Parse a wiki link string into an HRef object."""
        href = href.strip()

        if href.startswith(":"):
            rel = HREF_REL_ABSOLUTE
        elif href.startswith("+"):
            rel = HREF_REL_RELATIVE
        else:
            rel = HREF_REL_FLOATING

        anchor = None
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = heading_to_anchor(anchor)

        names = (
            Path.makeValidPageName(href.lstrip("+"))
            if href.lstrip(":").lstrip("+")
            else ""
        )

        return cls(rel, names, anchor)

    def __init__(self, rel, names, anchor=None):
        self.rel = rel
        self.names = names
        self.anchor = anchor

    def __str__(self):
        rel_str = {
            HREF_REL_ABSOLUTE: "abs",
            HREF_REL_FLOATING: "float",
            HREF_REL_RELATIVE: "rel",
        }[self.rel]
        return "<%s: %s %s %s>" % (
            self.__class__.__name__,
            rel_str,
            self.names,
            self.anchor,
        )

    def __eq__(self, other):
        return (self.__class__ is other.__class__) and (
            self.rel == other.rel
            and self.names == other.names
            and self.anchor == other.anchor
        )

    def parts(self):
        return self.names.split(":") if self.names else []

    def short_name(self):
        name = self.parts()[-1] if self.names else ""
        return name + "#" + self.anchor if self.anchor else name

    def to_wiki_link(self):
        """Return href as text for a wiki link."""
        if self.rel == HREF_REL_ABSOLUTE:
            link = ":" + self.names.strip(":")
        elif self.rel == HREF_REL_RELATIVE:
            link = "+" + self.names
        else:
            link = self.names

        if self.anchor:
            link += "#" + self.anchor

        return link


# ---- File-like wrapper for page source ----


class SourceFile:
    """Minimal file wrapper compatible with page.source_file interface.

    Provides .path, .exists(), .mtime(), .ctime(), .read(),
    .readlines_with_etag(), .writelines_with_etag(), .iswritable(),
    .readline(), .remove(), .verify_etag(), ._get_etag().
    """

    def __init__(self, filepath):
        self.path = filepath

    def exists(self):
        return os.path.isfile(self.path)

    def mtime(self):
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return None

    def ctime(self):
        try:
            # On Linux ctime is inode change time, not creation.
            # Use mtime as fallback for creation estimate.
            st = os.stat(self.path)
            return st.st_ctime
        except OSError:
            return None

    def iswritable(self):
        if self.exists():
            return os.access(self.path, os.W_OK)
        # File doesn't exist — walk up to find an existing parent dir
        parent = os.path.dirname(self.path)
        while parent and not os.path.isdir(parent):
            up = os.path.dirname(parent)
            if up == parent:
                break
            parent = up
        return os.access(parent, os.W_OK) if parent else False

    def read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def read_with_etag(self):
        text = self.read()
        etag = self._get_etag()
        return text, etag

    def readline(self, size=None):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                if size:
                    return f.read(size).split("\n")[0]
                return f.readline()
        except (OSError, IOError):
            return ""

    def readlines_with_etag(self):
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        etag = self._get_etag()
        return lines, etag

    def writelines(self, lines):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def writelines_with_etag(self, lines, prev_etag=None):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return self._get_etag()

    def remove(self):
        if self.exists():
            os.remove(self.path)

    def _get_etag(self):
        try:
            st = os.stat(self.path)
            return "%s-%s" % (st.st_mtime, st.st_size)
        except OSError:
            return None

    def verify_etag(self, etag):
        return self._get_etag() == etag

    def isequal(self, other):
        if hasattr(other, "path"):
            return os.path.realpath(self.path) == os.path.realpath(other.path)
        return False


class Page(Path, SignalEmitter):
    """Represents a single page in the notebook.

    Inherits from Path (for .name, .basename, etc.) and SignalEmitter
    (for connect/emit). Provides the duck-typing interface expected
    by WebBridge api.py.
    """

    def __init__(self, path, haschildren=False, file=None, folder=None, format=None):
        # Path init
        if isinstance(path, Path):
            self.name = path.name
        else:
            self.name = str(path).strip(":")

        # SignalEmitter init
        self._signal_handlers = {}
        self._signal_counter = 0
        import threading

        self._signal_lock = threading.Lock()

        self.haschildren = haschildren
        self._modified = False
        self._parsetree = None
        self._meta = None
        self._readonly = None
        self._last_etag = None
        self._cached_mtime = None  # mtime when parsetree was loaded

        # file and folder
        if isinstance(file, str):
            self.source_file = SourceFile(file)
        elif file is None:
            self.source_file = SourceFile("")
        else:
            self.source_file = file

        self.attachments_folder = folder

        # Format
        if format is None:
            from moonstone.formats import get_format

            self.format = get_format("wiki")
        elif isinstance(format, str):
            from moonstone.formats import get_format

            self.format = get_format(format)
        else:
            self.format = format

    @property
    def readonly(self):
        if self._readonly is None:
            self._readonly = not self.source_file.iswritable()
        return self._readonly

    @readonly.setter
    def readonly(self, value):
        self._readonly = value

    @property
    def mtime(self):
        return self.source_file.mtime() if self.source_file.exists() else None

    @property
    def ctime(self):
        return self.source_file.ctime() if self.source_file.exists() else None

    @property
    def hascontent(self):
        if self._parsetree:
            return self._parsetree.hascontent
        return self.source_file.exists()

    @property
    def modified(self):
        return self._modified

    def set_modified(self, modified):
        self._modified = modified

    def get_parsetree(self):
        """Returns the parse tree for the page content, or None.

        Checks file mtime to detect external changes — if the file
        was modified since last read, the cached parsetree is invalidated.
        """
        if self._parsetree:
            # Check if file changed on disk since we cached
            try:
                disk_mtime = self.source_file.mtime()
                if (
                    disk_mtime is not None
                    and self._cached_mtime is not None
                    and disk_mtime != self._cached_mtime
                ):
                    # File changed externally — invalidate cache
                    self._parsetree = None
                    self._meta = None
                else:
                    return self._parsetree
            except (OSError, AttributeError):
                return self._parsetree

        if not self.source_file.exists():
            return None

        try:
            text, self._last_etag = self.source_file.read_with_etag()
        except (OSError, IOError):
            return None

        parser = self.format.Parser()
        self._parsetree = parser.parse(text, file_input=True)
        self._meta = self._parsetree.meta
        self._cached_mtime = self.source_file.mtime()
        return self._parsetree

    def set_parsetree(self, tree):
        """Set new content for this page (must call store_page to persist)."""
        if self.readonly:
            raise PageReadOnlyError(self)
        self._parsetree = tree
        self.set_modified(True)

    def _store(self):
        """Write current parsetree to disk."""
        tree = self.get_parsetree()
        self._store_tree(tree)

    def _store_tree(self, tree):
        """Write a parse tree to the source file."""
        if tree and tree.hascontent:
            if self._meta is not None:
                tree.meta.update(self._meta)
            elif self.source_file.exists():
                # Try preserving headers from existing file
                try:
                    text = self.source_file.read()
                    parser = self.format.Parser()
                    old_tree = parser.parse(text, file_input=True)
                    self._meta = old_tree.meta
                    tree.meta.update(self._meta)
                except Exception:
                    pass
            else:
                now = datetime.now(timezone.utc)
                tree.meta["Creation-Date"] = now.isoformat()

            lines = self.format.Dumper().dump(tree, file_output=True)
            self._last_etag = self.source_file.writelines_with_etag(
                lines, self._last_etag
            )
            self._meta = tree.meta
            self._cached_mtime = self.source_file.mtime()
        else:
            self.source_file.remove()
            self._last_etag = None
            self._meta = None

    def dump(self, format, linker=None):
        """Get content in a specific format.

        @param format: format module or string name
        @param linker: optional linker object
        @returns: list of strings
        """
        if isinstance(format, str):
            from moonstone.formats import get_format

            format = get_format(format)

        if linker is not None:
            linker.set_path(self)

        tree = self.get_parsetree()
        if tree:
            return format.Dumper(linker=linker).dump(tree)
        return []

    def parse(self, format, text, append=False):
        """Parse text in given format and set as page content.

        @param format: format module or string name
        @param text: content string or list of lines
        @param append: if True, append instead of replace
        """
        if isinstance(format, str):
            from moonstone.formats import get_format

            format = get_format(format)

        tree = format.Parser().parse(text)
        if append:
            existing = self.get_parsetree()
            if existing:
                # Simple merge: concatenate the XML trees
                existing.extend(tree)
                self.set_parsetree(existing)
            else:
                self.set_parsetree(tree)
        else:
            self.set_parsetree(tree)

    def get_title(self):
        """Get the page title (heading or basename)."""
        tree = self.get_parsetree()
        if tree:
            return tree.get_heading_text() or self.basename
        return self.basename

    def heading_matches_pagename(self):
        tree = self.get_parsetree()
        if tree:
            return tree.get_heading_text() == self.basename
        return False

    def exists(self):
        return self.haschildren or self.hascontent
