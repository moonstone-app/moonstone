# -*- coding: utf-8 -*-
"""Zim Wiki compatibility profile.

Provides read-write support for Zim Desktop Wiki notebooks:
- .txt files with Content-Type headers
- @tag syntax
- [[Page:Name]] wiki links with `:` namespace separator
- Attachments in page-named folders

This profile exists for backward compatibility with existing
Zim Wiki notebooks. For new vaults, use the Moonstone profile.
"""

import re
from moonstone.profiles.base import BaseProfile


class ZimProfile(BaseProfile):
    """Zim Wiki format — backward compatibility with Zim Desktop Wiki."""

    name = "zim"
    display_name = "Zim Wiki"

    # File format
    file_extension = ".txt"
    default_format = "wiki"
    file_has_headers = True

    # Tags
    tag_prefix = "@"
    tag_regex = r"(?<!\w)@(\w+)"

    # Links
    link_regex = r"\[\[(.+?)(?:\|.*?)?\]\]"

    # Namespaces
    namespace_separator = ":"
    use_filename_spaces = False  # spaces → underscores

    # Metadata
    metadata_format = "headers"

    # Attachments
    attachments_mode = "page_folder"
    attachments_dir_name = None

    # Detection
    config_marker = "notebook.zim"

    def strip_metadata(self, text):
        """Parse Content-Type / Wiki-Format headers from file text."""
        meta = {}
        if not text.startswith("Content-Type:"):
            return meta, text

        lines = text.split("\n")
        body_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "":
                body_start = i + 1
                break
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
            body_start = i + 1

        body = "\n".join(lines[body_start:])
        return meta, body

    def add_metadata(self, text, metadata):
        """Prepend Content-Type headers to file text."""
        if not metadata:
            return text

        headers = []
        # Ensure Content-Type is first
        if "Content-Type" in metadata:
            headers.append("Content-Type: %s" % metadata["Content-Type"])
        else:
            headers.append("Content-Type: text/x-zim-wiki")

        if "Wiki-Format" in metadata:
            headers.append("Wiki-Format: %s" % metadata["Wiki-Format"])
        else:
            headers.append("Wiki-Format: zim 0.6")

        # Other headers
        for key, value in metadata.items():
            if key not in ("Content-Type", "Wiki-Format"):
                headers.append("%s: %s" % (key, value))

        return "\n".join(headers) + "\n\n" + text
