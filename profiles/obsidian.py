# -*- coding: utf-8 -*-
"""Obsidian vault profile for Moonstone.

Full read-write compatibility with Obsidian vaults:
- .md files with YAML frontmatter
- #tag syntax
- [[Page Name]] wiki links (spaces, not underscores)
- Configurable attachments folder
- No Content-Type headers
"""

import re
import os
from moonstone.profiles.base import BaseProfile


class ObsidianProfile(BaseProfile):
    """Obsidian vault — full read-write compatibility."""

    name = "obsidian"
    display_name = "Obsidian"

    # File format
    file_extension = ".md"
    default_format = "markdown"
    file_has_headers = False  # No Content-Type headers!

    # Tags: #tag (but not inside code blocks or headings like ## )
    tag_prefix = "#"
    tag_regex = r"(?<![#\w])#([\w][\w/-]*)"
    # Negative lookbehind for # prevents matching ## headings
    # Matches: #tag #nested/tag #tag-name
    # Skips: ## heading, ```#comment```, email@#

    # Links: [[Page Name]] or [[Page Name|Display]]
    # Obsidian also supports [[Page Name#heading]] anchors
    link_regex = r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]*?)?\]\]"

    # Namespaces: folder-based, / separator
    namespace_separator = "/"
    use_filename_spaces = True  # "My Page.md" not "My_Page.md"

    # Metadata: YAML frontmatter
    metadata_format = "yaml_frontmatter"

    # Attachments: Obsidian default is vault root (.), configurable via app.json
    attachments_mode = "flat"
    attachments_dir_name = None  # None = vault root (Obsidian default)

    # Detection
    config_marker = ".obsidian"

    def __init__(self):
        super().__init__()
        self._obsidian_config = None

    def load_vault_config(self, vault_path):
        """Load Obsidian's app.json config if available.

        Falls back to heuristic detection of attachment directories
        when .obsidian/app.json is missing (e.g. gitignored).
        """
        import json

        config_path = os.path.join(vault_path, ".obsidian", "app.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._obsidian_config = json.load(f)
                # Apply Obsidian attachment settings
                att_folder = self._obsidian_config.get("attachmentFolderPath")
                if att_folder and att_folder != ".":
                    self.attachments_dir_name = att_folder
                    self.attachments_mode = "flat"
            except (json.JSONDecodeError, OSError):
                pass

        # Heuristic: if no config found, scan for common attachment directories
        if self.attachments_dir_name is None:
            self._detect_attachments_dir(vault_path)

    def _detect_attachments_dir(self, vault_path):
        """Heuristic detection of attachment directory when config is missing.

        Scans top-level directories for common names like:
        attachments, Attachments, assets, media, images, files,
        or dirs containing "attach" or "asset" in the name.
        """
        common_names = {
            "attachments",
            "Attachments",
            "assets",
            "Assets",
            "media",
            "Media",
            "images",
            "Images",
            "files",
            "Files",
        }
        candidates = []

        try:
            for entry in os.scandir(vault_path):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                name_lower = entry.name.lower()
                # Exact common name match
                if entry.name in common_names:
                    candidates.insert(0, entry.name)
                # Fuzzy match: contains 'attach', 'asset', or 'media'
                elif any(kw in name_lower for kw in ("attach", "asset", "media")):
                    candidates.append(entry.name)
        except OSError:
            return

        if candidates:
            self.attachments_dir_name = candidates[0]
            self.attachments_mode = "flat"

    def extract_tags(self, text):
        """Extract #tags from Obsidian markdown, skipping code blocks.

        Also extracts tags from YAML frontmatter `tags:` field.
        """
        tags = set()

        # 1) YAML frontmatter tags
        meta, body = self.strip_metadata(text)
        fm_tags = meta.get("tags", [])
        if isinstance(fm_tags, list):
            for t in fm_tags:
                if isinstance(t, str):
                    tags.add(t.strip().lstrip("#"))
        elif isinstance(fm_tags, str):
            # tags: tag1, tag2
            for t in fm_tags.split(","):
                t = t.strip().lstrip("#")
                if t:
                    tags.add(t)

        # 2) Inline #tags (skip code blocks)
        # Remove fenced code blocks
        cleaned = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        # Remove inline code
        cleaned = re.sub(r"`[^`]+`", "", cleaned)

        for m in re.finditer(self.tag_regex, cleaned):
            tags.add(m.group(1))

        return list(tags)

    def extract_links(self, text):
        """Extract [[wiki links]] from Obsidian markdown.

        Handles:
        - [[Page Name]]
        - [[Page Name|Display Text]]
        - [[Page Name#Heading]]
        - [[Page Name#Heading|Display]]
        """
        results = []
        _, body = self.strip_metadata(text)

        # Remove code blocks
        cleaned = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        cleaned = re.sub(r"`[^`]+`", "", cleaned)

        # Full regex: capture everything inside [[ ]]
        for m in re.finditer(r"\[\[([^\]]+?)\]\]", cleaned):
            content = m.group(1)
            # Split by | for display text
            if "|" in content:
                target_part, display = content.split("|", 1)
            else:
                target_part = content
                display = None

            # Split by # for anchor
            if "#" in target_part:
                target = target_part.split("#", 1)[0].strip()
            else:
                target = target_part.strip()

            if target:
                results.append((target, display.strip() if display else None))

        return results

    def link_target_to_page_name(self, target):
        """Convert Obsidian link target to internal page name.

        Obsidian uses spaces and / for paths:
        [[Projects/Moonstone]] → 'Projects:Moonstone'
        [[My Page]] → 'My Page'
        """
        name = target.replace("/", ":").strip(":")
        return name

    def page_name_to_link_target(self, page_name):
        """Convert internal page name to Obsidian link format.

        'Projects:Moonstone' → 'Projects/Moonstone'
        """
        return page_name.replace(":", "/")

    def page_name_to_filename(self, page_name):
        """Convert page name to filesystem path.

        Obsidian preserves spaces in filenames:
        'Projects:Moonstone' → 'Projects/Moonstone'
        """
        return page_name.replace(":", "/")

    def filename_to_page_name(self, filename):
        """Convert filename to page name.

        'Projects/Moonstone' → 'Projects:Moonstone'
        Spaces in filenames are preserved as spaces in page names.
        """
        return filename.replace("\\", "/").replace("/", ":")

    def strip_metadata(self, text):
        """Parse YAML frontmatter from markdown file.

        Supports both inline and multi-line YAML list formats:
        ---
        title: My Page
        tags: [tag1, tag2]
        ---

        ---
        tags:
          - tag1
          - tag2
        ---
        Body content here
        """
        meta = {}
        if not text.startswith("---"):
            return meta, text

        lines = text.split("\n")
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx < 0:
            return meta, text

        # Parse YAML-like frontmatter (handles key: value AND multi-line lists)
        current_key = None
        current_list = None

        for line in lines[1:end_idx]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Check for multi-line list item: "  - value"
            if current_key is not None and re.match(r"^[\s]+-\s+", line):
                item = stripped.lstrip("- ").strip().strip('"').strip("'")
                if item:
                    if current_list is None:
                        current_list = []
                    current_list.append(item)
                continue

            # Flush previous multi-line list if any
            if current_key is not None and current_list is not None:
                meta[current_key] = current_list
                current_key = None
                current_list = None
            elif current_key is not None:
                # Key with empty value and no list items following — store as empty string
                current_key = None
                current_list = None

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if not key:
                    continue

                # Parse YAML lists: [item1, item2]
                if value.startswith("[") and value.endswith("]"):
                    items = value[1:-1].split(",")
                    meta[key] = [
                        item.strip().strip('"').strip("'")
                        for item in items
                        if item.strip()
                    ]
                    current_key = None
                    current_list = None
                elif value:
                    # Bare scalar value
                    meta[key] = value.strip('"').strip("'")
                    current_key = None
                    current_list = None
                else:
                    # Empty value — might be followed by multi-line list
                    current_key = key
                    current_list = None

        # Flush last key if it was a multi-line list
        if current_key is not None and current_list is not None:
            meta[current_key] = current_list

        body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
        return meta, body

    def add_metadata(self, text, metadata):
        """Add YAML frontmatter to markdown file."""
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

    def extract_attachment_refs(self, text):
        """Extract referenced attachment filenames from page content.

        Handles Obsidian/markdown image/embed syntaxes:
        - ![[filename.png]]            (Obsidian embed)
        - ![[filename.png|300]]        (Obsidian embed with size)
        - ![alt](filename.png)         (standard markdown image)
        - ![alt](path/to/file.png)     (with path)

        Returns set of basenames (no paths).
        """
        refs = set()

        # 1) Obsidian embeds: ![[file.ext]] or ![[file.ext|size]]
        for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|[^\]]*?)?\]\]", text):
            target = m.group(1).strip()
            # Take basename only (handle paths like assets/img.png)
            basename = os.path.basename(target)
            if basename and "." in basename:
                refs.add(basename)

        # 2) Standard markdown images: ![alt](file.ext) or ![alt](path/file.ext)
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
            target = m.group(1).strip()
            # Skip URLs
            if target.startswith(("http://", "https://", "data:")):
                continue
            # Handle // path separators (Moonstone-converted paths)
            # pasted//image//260225.png → pasted_image_260225.png (on disk)
            normalized = target.replace("//", "_").replace("/", "_")
            if "." in normalized:
                refs.add(normalized)
            # Also try the plain basename
            basename = os.path.basename(target.replace("//", "/"))
            if basename and "." in basename and basename != normalized:
                refs.add(basename)

        return refs

    def get_attachments_path(self, page_name, vault_root):
        """Get Obsidian attachments path.

        Respects Obsidian's attachmentFolderPath setting.
        - None / '.' → vault root (Obsidian default)
        - 'assets' → vault_root/assets/ subfolder
        """
        if self.attachments_mode == "flat":
            if self.attachments_dir_name:
                return os.path.join(vault_root, self.attachments_dir_name)
            else:
                # Default: vault root (Obsidian stores attachments alongside pages)
                return vault_root
        else:
            rel = self.page_name_to_filename(page_name)
            return os.path.join(vault_root, rel)

    def to_dict(self):
        """Serialize profile info with Obsidian-specific fields."""
        d = super().to_dict()
        d["obsidian_config"] = self._obsidian_config is not None
        return d
