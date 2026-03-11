# -*- coding: utf-8 -*-
"""File ↔ page mapping for Moonstone.

Standalone layout module — maps page names to filesystem paths
and vice versa, using pathlib + os using pathlib.
"""

import os
import re
import sys

from moonstone.notebook.page import Path, SourceFile

_fs_encoding = sys.getfilesystemencoding() or "utf-8"


def encode_filename(pagename, use_spaces=False):
    """Encode a pagename to a filename.

    Namespaces ":" → "/".
    If use_spaces is False (Moonstone default), spaces → "_".
    If use_spaces is True (Obsidian), spaces are preserved.
    Characters incompatible with filesystem encoding are percent-encoded.
    """
    # Percent-encode chars that can't be represented in fs encoding
    try:
        encoded = pagename.encode(_fs_encoding)
        pagename = encoded.decode(_fs_encoding)
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: percent-encode problematic chars
        result = []
        for ch in pagename:
            try:
                ch.encode(_fs_encoding)
                result.append(ch)
            except UnicodeEncodeError:
                for byte in ch.encode("utf-8"):
                    result.append("%%%02X" % byte)
        pagename = "".join(result)

    result = pagename.replace(":", "/")
    if not use_spaces:
        result = result.replace(" ", "_")
    return result


_url_decode_re = re.compile(r"%([a-fA-F0-9]{2})")


def _url_decode(match):
    return chr(int(match.group(1), 16))


def decode_filename(filename, use_spaces=False):
    """Decode a filename to a pagename.

    Reverse of encode_filename: "/" → ":".
    If use_spaces is False (Moonstone default), "_" → " ".
    If use_spaces is True (Obsidian), underscores are preserved.
    Percent-encoded chars are decoded.
    """
    filename = _url_decode_re.sub(_url_decode, filename)
    result = filename.replace("\\", ":").replace("/", ":")
    if not use_spaces:
        result = result.replace("_", " ")
    return result


class FilesAttachmentFolder:
    """Attachments folder that filters out page source files.

    Wraps a directory path and provides list_names(), file(),
    exists(), touch(), .path attribute for duck-typing compatibility.
    """

    def __init__(self, folder_path, is_source_file_func=None):
        self.path = folder_path
        self._is_source_file = is_source_file_func

    def exists(self):
        return os.path.isdir(self.path)

    def touch(self):
        os.makedirs(self.path, exist_ok=True)

    def file(self, name):
        """Return a SourceFile for a named attachment."""
        return SourceFile(os.path.join(self.path, name))

    def list_names(self):
        """Yield names of attachment files (excluding source files)."""
        if not self.exists():
            return
        for name in sorted(os.listdir(self.path)):
            filepath = os.path.join(self.path, name)
            if os.path.isfile(filepath):
                # Skip config files (e.g. notebook.moon)
                if name.startswith("notebook.") and not name.endswith(
                    self._source_ext if hasattr(self, "_source_ext") else ""
                ):
                    from moonstone.profiles import get_all_config_markers

                    if name in get_all_config_markers():
                        continue
                if self._is_source_file and self._is_source_file(filepath):
                    continue
                yield name

    def list_files(self):
        for name in self.list_names():
            yield SourceFile(os.path.join(self.path, name))

    def __iter__(self):
        return self.list_files()

    def __str__(self):
        return self.path


class FilesLayout:
    """Maps page names ↔ filesystem files.

    FilesLayout interface.
    """

    def __init__(
        self,
        root_folder,
        endofline="unix",
        default_format="wiki",
        default_extension=".txt",
        use_filename_spaces=False,
        profile=None,
    ):
        self.root = root_folder  # string path
        self.endofline = endofline
        self.use_filename_spaces = use_filename_spaces
        self.profile = profile  # vault profile for custom file mapping

        if not default_extension.startswith("."):
            default_extension = "." + default_extension
        self.default_extension = default_extension
        self.default_format_name = default_format

    def map_page(self, pagename):
        """Map a Path to (source_file_path, attachments_folder_path).

        If a profile is set, delegates to profile.page_name_to_filename()
        for correct mapping (e.g., Logseq routes to pages/ or journals/).

        @param pagename: a Path object
        @returns: (file_path_str, folder_path_str)
        """
        if self.profile and hasattr(self.profile, "page_name_to_filename"):
            rel = self.profile.page_name_to_filename(pagename.name)
        else:
            rel = encode_filename(pagename.name, self.use_filename_spaces)
        file_path = os.path.join(self.root, rel + self.default_extension)
        folder_path = os.path.join(self.root, rel) if rel else self.root
        

                    
        return file_path, folder_path

    def get_attachments_folder(self, pagename):
        """Return a FilesAttachmentFolder for the given page."""
        _, folder_path = self.map_page(pagename)
        return FilesAttachmentFolder(folder_path, self.is_source_file)

    def is_source_file(self, filepath):
        """Check whether a file is a page source file.

        For .txt files: checks for Content-Type headers (Moonstone format; also reads legacy headers).
        For .md files: all .md files are source files (Obsidian/Logseq format).
        """
        if isinstance(filepath, str):
            path = filepath
        elif hasattr(filepath, "path"):
            path = filepath.path
        else:
            path = str(filepath)

        if not path.endswith(self.default_extension):
            return False

        # .md files are always source files (Obsidian, Logseq)
        if self.default_extension == ".md":
            return True

        # .txt files: check for Content-Type header (any recognized type)
        if self.default_extension == ".txt":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    line = f.read(60)
                return line.strip().startswith("Content-Type:")
            except (OSError, IOError):
                return True  # benefit of the doubt
        return True

    def map_file(self, filepath):
        """Map a filepath to (Path, file_type).

        If a profile is set, delegates to profile.filename_to_page_name()
        for correct reverse mapping (e.g., Logseq strips pages/ prefix).

        @param filepath: absolute path string
        @returns: (Path, 'source' | 'attachment')
        """
        relpath = os.path.relpath(filepath, self.root)
        is_source = self.is_source_file(filepath)

        if is_source and relpath.endswith(self.default_extension):
            relpath = relpath[: -len(self.default_extension)]

        # Convert to page name using profile if available
        if self.profile and hasattr(self.profile, "filename_to_page_name"):
            name = self.profile.filename_to_page_name(relpath)
        else:
            name = decode_filename(relpath, self.use_filename_spaces)

        if name == ".":
            return Path(":"), "source" if is_source else "attachment"

        return Path(name), "source" if is_source else "attachment"

    def index_list_children(self, pagename):
        """List child pages of a given page.

        @param pagename: a Path object
        @returns: list of Path objects for child pages
        """
        _, folder_path = self.map_page(pagename)
        if not os.path.isdir(folder_path):
            return []

        names = set()
        try:
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    if entry.name.endswith(self.default_extension):
                        basename = entry.name[: -len(self.default_extension)]
                        pname = decode_filename(basename, self.use_filename_spaces)
                        if encode_filename(pname, self.use_filename_spaces) == basename:
                            names.add(pname)
                elif entry.is_dir():
                    pname = decode_filename(entry.name, self.use_filename_spaces)
                    if encode_filename(pname, self.use_filename_spaces) == entry.name:
                        names.add(pname)
        except OSError:
            return []

        return [pagename.child(basename) for basename in sorted(names)]
