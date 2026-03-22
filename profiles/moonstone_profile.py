# -*- coding: utf-8 -*-
"""Moonstone native vault profile.

Moonstone's own format — a standalone PKM system:
- .md files with YAML frontmatter
- #tag syntax (standard Markdown hashtags)
- [[Page:Name]] wiki links with `:` namespace separator
- Attachments in page-named folders
- Filenames preserved as-is (no underscore/space conversion)
"""

import re
from moonstone.profiles.base import BaseProfile


class MoonstoneProfile(BaseProfile):
    """Moonstone native format — standalone Markdown-based PKM."""

    name = "moonstone"
    display_name = "Moonstone"

    # File format
    file_extension = ".md"
    default_format = "markdown"
    file_has_headers = False

    # Tags — standard Markdown hashtags
    tag_prefix = "#"
    tag_regex = r"(?<!\w)#(\w[\w-]*)"

    # Links — wiki-style with : separator
    link_regex = r"\[\[(.+?)(?:\|.*?)?\]\]"

    # Namespaces
    namespace_separator = ":"
    use_filename_spaces = True  # preserve filenames as-is (underscores stay underscores)

    # Metadata — YAML frontmatter
    metadata_format = "yaml_frontmatter"

    # Attachments
    attachments_mode = "page_folder"
    attachments_dir_name = None

    # Detection
    config_marker = "notebook.moon"

    def strip_metadata(self, text):
        """Parse YAML frontmatter from file text.

        Frontmatter is enclosed between two `---` lines at the start.

        @param text: raw file content
        @returns: (metadata_dict, body_text)
        """
        meta = {}
        if not text.startswith("---"):
            return meta, text

        lines = text.split("\n")
        # Find closing ---
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return meta, text

        # Parse YAML key: value pairs (simple flat parsing)
        for line in lines[1:end_idx]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                # Handle YAML lists (tags: [a, b, c])
                if value.startswith("[") and value.endswith("]"):
                    value = [
                        v.strip().strip('"').strip("'")
                        for v in value[1:-1].split(",")
                        if v.strip()
                    ]
                # Handle quoted strings
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                meta[key] = value

        body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
        return meta, body

    def add_metadata(self, text, metadata):
        """Prepend YAML frontmatter to file text.

        @param text: body content
        @param metadata: dict of metadata
        @returns: full file text with frontmatter
        """
        if not metadata:
            return text

        lines = ["---"]
        for key, value in metadata.items():
            if isinstance(value, list):
                lines.append("%s: [%s]" % (key, ", ".join(str(v) for v in value)))
            else:
                lines.append("%s: %s" % (key, value))
        lines.append("---")
        lines.append("")

        return "\n".join(lines) + text
