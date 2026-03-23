# -*- coding: utf-8 -*-
"""Base profile interface for Moonstone vault profiles.

A profile defines everything format-specific:
- File extension and format
- Tag and link syntax (regex for extraction, prefix for writing)
- Metadata format (headers, YAML frontmatter, properties)
- Attachment storage strategy
- Namespace mapping (`:` vs `/`)
"""

import re


class BaseProfile:
    """Abstract base class for vault profiles.

    Subclasses must define all class attributes and may override
    methods for custom behavior.
    """

    # ---- Identity ----
    name = None  # 'moonstone', 'obsidian', 'logseq'
    display_name = None  # 'Moonstone', 'Obsidian', 'Logseq'

    # ---- File format ----
    file_extension = ".txt"  # '.txt', '.md'
    default_format = "wiki"  # format name for get_format()
    file_has_headers = True  # Content-Type / Wiki-Format headers

    # ---- Tags ----
    tag_prefix = "@"  # '@' for moonstone, '#' for obsidian
    tag_regex = r"(?<!\w)@(\w+)"  # regex to extract tags from raw text
    # Group 1 must capture the tag name without prefix

    # ---- Links ----
    link_regex = r"\[\[(.+?)(?:\|.*?)?\]\]"  # wiki-link extraction
    # Group 1 captures the target (before |)

    # ---- Namespaces ----
    namespace_separator = ":"  # ':' for moonstone, '/' for obsidian
    use_filename_spaces = False  # True = "My Page.md", False = "My_Page.txt"

    # ---- Metadata ----
    metadata_format = "headers"  # 'headers', 'yaml_frontmatter', 'properties'

    # ---- Attachments ----
    attachments_mode = "page_folder"  # 'page_folder', 'flat', 'subfolder'
    attachments_dir_name = None  # for 'flat' mode: '_attachments', 'assets', etc.

    # ---- Detection ----
    config_marker = None  # '.obsidian/', 'logseq/', 'notebook.moon'

    # ================================================================
    # Methods
    # ================================================================

    def _strip_code_blocks(self, text):
        """Remove markdown code blocks to avoid extracting fake links/tags."""
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`\n]+`", "", text)
        return text

    def extract_tags(self, text):
        """Extract tag names from raw page text.

        @param text: raw file content string
        @returns: list of tag name strings (without prefix)
        """
        text = self._strip_code_blocks(text)
        return [m.group(1) for m in re.finditer(self.tag_regex, text)]

    def extract_links(self, text):
        """Extract [[wiki links]] from text.

        @param text: raw file content string
        @returns: list of (target, heading_anchor, block_id, display_text) tuples
            - target: page name (str or None)
            - heading_anchor: heading after # (str or None)
            - block_id: block ref after ^ (str or None)
            - display_text: display text after | (str or None)
        """
        text = self._strip_code_blocks(text)
        results = []
        for m in re.finditer(self.link_regex, text):
            full = m.group(0)
            raw_target = m.group(1).strip()

            # Extract display_text from |... if present
            display_text = None
            if "|" in full:
                parts = full[2:-2].split("|", 1)
                raw_target = parts[0].strip()
                display_text = parts[1].strip() if len(parts) > 1 else None

            # Parse heading_anchor (#heading) and block_id (^blockid) from target
            heading_anchor = None
            block_id = None
            if "#" in raw_target:
                target_parts = raw_target.split("#", 1)
                raw_target = target_parts[0]
                heading_anchor = target_parts[1] if len(target_parts) > 1 else None
                # Check for block_id in heading part
                if heading_anchor and "^" in heading_anchor:
                    heading_parts = heading_anchor.split("^", 1)
                    heading_anchor = heading_parts[0]
                    block_id = heading_parts[1] if len(heading_parts) > 1 else None
            elif "^" in raw_target:
                # Block ID directly on target without heading
                target_parts = raw_target.split("^", 1)
                raw_target = target_parts[0]
                block_id = target_parts[1] if len(target_parts) > 1 else None

            results.append((raw_target, heading_anchor, block_id, display_text))
        return results

    def format_tag(self, tag_name):
        """Format a tag name for writing into a page.

        @param tag_name: tag name without prefix
        @returns: formatted tag string (e.g., '@tag' or '#tag')
        """
        return self.tag_prefix + tag_name

    def format_link(self, target, display=None):
        """Format a wiki link for writing into a page.

        @param target: page name
        @param display: optional display text
        @returns: formatted link string
        """
        if display:
            return "[[%s|%s]]" % (target, display)
        return "[[%s]]" % target

    def page_name_to_filename(self, page_name):
        """Convert internal page name (with `:`) to filename.

        @param page_name: 'Projects:Moonstone'
        @returns: relative path without extension, e.g., 'Projects/Moonstone'
        """
        if self.use_filename_spaces:
            # Obsidian: spaces stay as spaces
            return page_name.replace(":", "/")
        else:
            # Moonstone: spaces → underscores
            return page_name.replace(":", "/").replace(" ", "_")

    def filename_to_page_name(self, filename):
        """Convert filename to internal page name (with `:`).

        @param filename: relative path without extension, e.g., 'Projects/Moonstone'
        @returns: 'Projects:Moonstone'
        """
        name = filename.replace("\\", "/").replace("/", ":")
        if not self.use_filename_spaces:
            name = name.replace("_", " ")
        return name

    def link_target_to_page_name(self, target):
        """Convert a link target as written in content to internal page name.

        @param target: link target as it appears in [[target]]
        @returns: internal page name with `:` separator
        """
        # Default: replace namespace_separator with ':'
        name = target.replace(self.namespace_separator, ":").strip(":")
        if not self.use_filename_spaces:
            name = name.replace("_", " ")
        return name

    def page_name_to_link_target(self, page_name):
        """Convert internal page name to link target for writing.

        @param page_name: internal name with ':'
        @returns: string for use inside [[...]]
        """
        return page_name.replace(":", self.namespace_separator)

    def strip_metadata(self, text):
        """Remove metadata section from raw file text, return (metadata_dict, body).

        @param text: full file content
        @returns: (metadata_dict, body_text)
        """
        return {}, text  # Override in subclasses

    def add_metadata(self, text, metadata):
        """Prepend metadata to text for file output.

        @param text: body content
        @param metadata: dict of metadata
        @returns: full file text with metadata
        """
        return text  # Override in subclasses

    def get_attachments_path(self, page_name, vault_root):
        """Get the filesystem path for attachments of a given page.

        @param page_name: internal page name
        @param vault_root: vault root folder path
        @returns: absolute path string
        """
        import os

        if self.attachments_mode == "flat":
            dir_name = self.attachments_dir_name or "_attachments"
            return os.path.join(vault_root, dir_name)
        elif self.attachments_mode == "subfolder":
            # Attachments in a subfolder next to the page file
            rel = self.page_name_to_filename(page_name)
            return os.path.join(vault_root, rel)
        else:
            # page_folder: same as Moonstone default
            rel = self.page_name_to_filename(page_name)
            return os.path.join(vault_root, rel)

    def to_dict(self):
        """Serialize profile info for API response."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "file_extension": self.file_extension,
            "default_format": self.default_format,
            "tag_prefix": self.tag_prefix,
            "namespace_separator": self.namespace_separator,
            "metadata_format": self.metadata_format,
            "attachments_mode": self.attachments_mode,
            "attachments_dir": self.attachments_dir_name,
        }
