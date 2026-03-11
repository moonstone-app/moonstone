# -*- coding: utf-8 -*-
"""Logseq graph profile for Moonstone.

Full read-write compatibility with Logseq graphs:
- .md files in pages/ and journals/ subdirectories
- #tag syntax (same as Obsidian)
- [[Page Name]] wiki links
- Properties: key:: value (double colon) in first block
- Outliner mode (every line is a bullet "- ...")
- Attachments in assets/ directory
- config.edn for graph settings
- Triple-lowbar encoding for special chars in filenames
"""

import os
import re
from moonstone.profiles.obsidian import ObsidianProfile


def _parse_edn_value(raw):
    """Parse a simple EDN value to Python.

    Handles strings, keywords, booleans, integers, and simple vectors/maps.
    Not a full EDN parser — covers Logseq config.edn needs.
    """
    raw = raw.strip()
    if not raw:
        return None

    # String
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]

    # Keyword
    if raw.startswith(":"):
        return raw

    # Boolean
    if raw == "true":
        return True
    if raw == "false":
        return False

    # Integer
    try:
        return int(raw)
    except ValueError:
        pass

    return raw


def _parse_edn_simple(text):
    """Extract top-level key-value pairs from a Logseq config.edn.

    Simplified parser that handles the most common patterns:
    - :key value
    - :key "string"
    - :key :keyword
    - :key true/false
    - :key integer

    Skips nested structures (maps, vectors, queries) for safety.

    Returns dict of {key_string: value}.
    """
    result = {}

    # Remove comments
    lines = []
    for line in text.split("\n"):
        # Remove ;; comments (but not inside strings)
        in_string = False
        clean = []
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                in_string = not in_string
                clean.append(ch)
            elif (
                ch == ";" and not in_string and i + 1 < len(line) and line[i + 1] == ";"
            ):
                break
            else:
                clean.append(ch)
            i += 1
        lines.append("".join(clean))

    content = "\n".join(lines)

    # Match simple :key value pairs at top level
    # Pattern: :keyword followed by a simple value (string, keyword, bool, int)
    for m in re.finditer(
        r"(?:^|[\s{])(:[\w/?.!-]+)\s+" r'("(?:[^"\\]|\\.)*"|:[\w-]+|true|false|\d+)',
        content,
    ):
        key = m.group(1)
        val = _parse_edn_value(m.group(2))
        result[key] = val

    return result


class LogseqProfile(ObsidianProfile):
    """Logseq graph — extends Obsidian profile with Logseq specifics.

    Logseq and Obsidian share most conventions (.md, #tags, [[links]]).
    Key differences handled here:
    - pages/ subfolder for page files
    - journals/ subfolder for daily notes
    - Properties use `key:: value` syntax (double colon)
    - Attachments stored in assets/ directory
    - Outliner mode (everything is a bullet)
    - config.edn for graph configuration
    - Triple-lowbar (___) filename encoding for /
    """

    name = "logseq"
    display_name = "Logseq"

    # Detection
    config_marker = "logseq"

    # Metadata: Logseq properties (key:: value), not YAML frontmatter
    metadata_format = "properties"

    # Attachments: flat in assets/ directory
    attachments_mode = "flat"
    attachments_dir_name = "assets"

    # Content directories — pages and journals are structural dirs, not namespaces
    content_dirs = ["pages", "journals"]

    def __init__(self):
        super().__init__()
        self._logseq_config = None
        self._pages_dir = "pages"
        self._journals_dir = "journals"
        self._journal_file_format = "yyyy_MM_dd"
        self._file_name_format = ":triple-lowbar"

    def load_vault_config(self, vault_path):
        """Load Logseq's config.edn if available."""
        config_path = os.path.join(vault_path, "logseq", "config.edn")
        if not os.path.isfile(config_path):
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                text = f.read()
            self._logseq_config = _parse_edn_simple(text)
        except (OSError, IOError):
            return

        # Apply settings from config
        cfg = self._logseq_config

        pages_dir = cfg.get(":pages-directory")
        if pages_dir and isinstance(pages_dir, str):
            self._pages_dir = pages_dir.strip('"')

        journals_dir = cfg.get(":journals-directory")
        if journals_dir and isinstance(journals_dir, str):
            self._journals_dir = journals_dir.strip('"')

        journal_fmt = cfg.get(":journal/file-name-format")
        if journal_fmt and isinstance(journal_fmt, str):
            self._journal_file_format = journal_fmt.strip('"')

        name_fmt = cfg.get(":file/name-format")
        if name_fmt:
            self._file_name_format = name_fmt

        # Update content_dirs from config
        self.content_dirs = [self._pages_dir, self._journals_dir]

    def _is_journal_name(self, page_name):
        """Check if a page name looks like a Logseq journal entry.

        Journal filenames match the configured date format pattern.
        Default: yyyy_MM_dd → e.g., 2026_03_06
        """
        # Common journal patterns
        if re.match(r"^\d{4}_\d{2}_\d{2}$", page_name):
            return True
        # Also match with dashes or dots
        if re.match(r"^\d{4}[-_.]\d{2}[-_.]\d{2}$", page_name):
            return True
        return False

    def _encode_page_name(self, name):
        """Encode page name for filename using Logseq conventions.

        Triple-lowbar format:
        - / in page name → ___ in filename
        - Other special chars → percent-encoded
        """
        if self._file_name_format == ":triple-lowbar":
            # / → ___
            name = name.replace("/", "___")
        # Logseq percent-encodes chars invalid in filenames
        # Common ones: < > : " | ? *
        for ch in '<>"|?*':
            if ch in name:
                name = name.replace(ch, "%%%02X" % ord(ch))
        return name

    def _decode_page_name(self, filename):
        """Decode a Logseq filename back to page name.

        Reverse of _encode_page_name.
        """
        name = filename
        if self._file_name_format == ":triple-lowbar":
            name = name.replace("___", "/")

        # Decode percent-encoded chars
        def _decode_percent(m):
            return chr(int(m.group(1), 16))

        name = re.sub(r"%([0-9A-Fa-f]{2})", _decode_percent, name)
        return name

    def page_name_to_filename(self, page_name):
        """Convert page name to relative file path (without extension).

        Routes to pages/ or journals/ based on page name pattern.
        'page' → 'pages/page'
        '2026_03_06' → 'journals/2026_03_06'
        'Nested/Page' → 'pages/Nested___Page' (triple-lowbar)
        """
        encoded = self._encode_page_name(page_name)

        if self._is_journal_name(page_name):
            return self._journals_dir + "/" + encoded
        return self._pages_dir + "/" + encoded

    def filename_to_page_name(self, filename):
        """Convert relative file path (without extension) to page name.

        Strips pages/ or journals/ prefix and decodes the filename.
        'pages/page' → 'page'
        'journals/2026_03_06' → '2026_03_06'
        'pages/Nested___Page' → 'Nested/Page'
        """
        name = filename.replace("\\", "/")

        # Strip content directory prefix
        if name.startswith(self._pages_dir + "/"):
            name = name[len(self._pages_dir) + 1 :]
        elif name.startswith(self._journals_dir + "/"):
            name = name[len(self._journals_dir) + 1 :]

        return self._decode_page_name(name)

    def link_target_to_page_name(self, target):
        """Convert Logseq link target to internal page name.

        Logseq [[links]] use the page name directly (spaces preserved).
        [[My Page]] → 'My Page'
        """
        return target.strip()

    def page_name_to_link_target(self, page_name):
        """Convert internal page name to Logseq link format.

        'My Page' → 'My Page'
        """
        return page_name

    def strip_metadata(self, text):
        """Parse Logseq properties from the first block.

        Logseq properties use double-colon syntax in the first bullet:
        - key1:: value1
          key2:: value2
        - normal content

        Also handles page-level properties (without bullet prefix):
        key1:: value1
        key2:: value2
        """
        meta = {}
        if not text:
            return meta, text

        lines = text.split("\n")
        body_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines at the beginning
            if not stripped and i == body_start:
                body_start = i + 1
                continue

            # Strip leading bullet "- " if present
            prop_line = stripped
            if prop_line.startswith("- "):
                prop_line = prop_line[2:]

            # Check for property pattern: key:: value
            prop_match = re.match(r"^([\w][\w-]*)::\s*(.*)", prop_line)
            if prop_match:
                key = prop_match.group(1).strip()
                value = prop_match.group(2).strip()

                # Parse comma-separated values as lists
                if "," in value and not value.startswith('"'):
                    meta[key] = [v.strip() for v in value.split(",") if v.strip()]
                # Parse [[page ref]] lists
                elif value.startswith("[["):
                    refs = re.findall(r"\[\[([^\]]+)\]\]", value)
                    if refs:
                        meta[key] = refs
                    else:
                        meta[key] = value
                else:
                    meta[key] = value

                body_start = i + 1
            else:
                # First non-property, non-empty line — stop
                break

        body = "\n".join(lines[body_start:])
        return meta, body

    def add_metadata(self, text, metadata):
        """Add Logseq properties to the beginning of text.

        Outputs key:: value format as a bullet block.
        """
        if not metadata:
            return text

        lines = []
        for key, value in metadata.items():
            if isinstance(value, list):
                # Format as comma-separated or [[refs]]
                if all(isinstance(v, str) and not v.startswith("[[") for v in value):
                    val_str = ", ".join(str(v) for v in value)
                else:
                    val_str = ", ".join(
                        "[[%s]]" % v if not v.startswith("[[") else v for v in value
                    )
                lines.append("%s:: %s" % (key, val_str))
            else:
                lines.append("%s:: %s" % (key, value))

        prop_block = "\n".join(lines)
        if text:
            return prop_block + "\n" + text
        return prop_block

    def extract_tags(self, text):
        """Extract tags from Logseq content.

        Handles:
        - #tag inline tags (same as Obsidian)
        - tags:: tag1, tag2 property in first block
        - tags:: [[tag1]] [[tag2]] inline in any block
        """
        tags = set()

        # 1) Tags from first-block properties
        meta, body = self.strip_metadata(text)
        prop_tags = meta.get("tags", [])
        if isinstance(prop_tags, list):
            for t in prop_tags:
                if isinstance(t, str):
                    tags.add(t.strip().lstrip("#"))
        elif isinstance(prop_tags, str):
            for t in prop_tags.split(","):
                t = t.strip().lstrip("#")
                if t:
                    tags.add(t)

        # 2) Inline tags:: in ANY block (not just first block)
        # Logseq allows tags:: as a block-level property anywhere
        for m in re.finditer(r"(?:^|\n)\s*tags::\s*(.+)", text):
            value = m.group(1).strip()
            # Parse [[page ref]] style
            ref_tags = re.findall(r"\[\[([^\]]+)\]\]", value)
            if ref_tags:
                for t in ref_tags:
                    tags.add(t.strip().lstrip("#"))
            else:
                # Comma-separated
                for t in value.split(","):
                    t = t.strip().lstrip("#")
                    if t:
                        tags.add(t)

        # 3) Inline #tags (skip code blocks) — inherited from ObsidianProfile
        cleaned = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        cleaned = re.sub(r"`[^`]+`", "", cleaned)

        for m in re.finditer(self.tag_regex, cleaned):
            tags.add(m.group(1))

        return list(tags)

    def extract_attachment_refs(self, text):
        """Extract referenced attachment filenames from Logseq content.

        Logseq typically uses:
        - ![alt](../assets/filename.png)  — relative path from pages/ to assets/
        - ![image.png](../assets/image_1772815273625_0.png)
        """
        refs = set()

        # Obsidian embeds: ![[file.ext]]
        for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|[^\]]*?)?\]\]", text):
            target = m.group(1).strip()
            basename = os.path.basename(target)
            if basename and "." in basename:
                refs.add(basename)

        # Standard markdown images: ![alt](path)
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "data:")):
                continue
            basename = os.path.basename(target)
            if basename and "." in basename:
                refs.add(basename)

        return refs

    def get_attachments_path(self, page_name, vault_root):
        """Get Logseq attachments path — always assets/ in graph root."""
        return os.path.join(vault_root, self.attachments_dir_name or "assets")

    def to_dict(self):
        """Serialize profile info with Logseq-specific fields."""
        d = super().to_dict()
        d["logseq_config"] = self._logseq_config is not None
        d["pages_dir"] = self._pages_dir
        d["journals_dir"] = self._journals_dir
        d["content_dirs"] = self.content_dirs
        return d
