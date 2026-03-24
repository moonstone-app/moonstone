# -*- coding: utf-8 -*-
"""Markdown parser + dumper for Moonstone.

Full CommonMark-compatible parser with extensions for wiki-links
([[Page]], [[Page|alias]]), embeds (![[file]]), highlights (==text==),
checkboxes (- [ ] / - [x]), blockquotes, tables, and YAML frontmatter.

Converts ParseTree ↔ Markdown format.
"""

import re
from xml.etree import ElementTree as ET
from moonstone.formats import ParseTree, BaseParser, BaseDumper

# ---------------------------------------------------------------------------
# Inline patterns — compiled once, ordered by priority
# ---------------------------------------------------------------------------

# Wiki-style embed: ![[file]] or ![[file|option]]
_RE_EMBED = re.compile(r"!\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]")

# Standard image: ![alt](src) or ![alt](<path with spaces.jpg>) or with title
_RE_IMAGE = re.compile(r'!\[([^\]]*?)\]\((<[^>]+>|[^)\s]+?)(?:\s+(?:"[^"]*"|\'[^\']*\'))?\)')

# Wiki link: [[Page]] or [[Page|alias]]
_RE_WIKILINK = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]")

# Standard markdown link: [text](url) or [text](<url with spaces>) or with title
_RE_LINK = re.compile(r'\[([^\[\]]*?)\]\((<[^>]+>|[^)\s]+?)(?:\s+(?:"[^"]*"|\'[^\']*\'))?\)')

# Bold+italic: ***text*** or ___text___
_RE_BOLDITALIC = re.compile(r"\*\*\*(.+?)\*\*\*|___(.+?)___")

# Bold: **text** or __text__
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")

# Italic: *text* or _text_ (not preceded/followed by word char for _)
_RE_ITALIC = re.compile(
    r"\*([^\s*](?:.*?[^\s*])?)\*|(?<!\w)_([^\s_](?:.*?[^\s_])?)_(?!\w)"
)

# Inline code: `text`
_RE_CODE = re.compile(r"`([^`]+?)`")

# Strikethrough: ~~text~~
_RE_STRIKE = re.compile(r"~~(.+?)~~")

# Highlight (Obsidian/Logseq): ==text==
_RE_HIGHLIGHT = re.compile(r"==(.+?)==")

# Logseq caret highlight: ^^text^^
_RE_CARET_HIGHLIGHT = re.compile(r"\^\^(.+?)\^\^")

# Bare URL (autolink)
_RE_BARE_URL = re.compile(
    r'(?<![(\["\'])(https?://[^\s<>\[\]()]+[^\s<>\[\]().,;:!?\'")])(?![)\]])'
)

# Logseq block reference: ((uuid))
_RE_BLOCKREF = re.compile(
    r"\(\(([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)\)"
)

# Logseq macro: {{macro arg}} — simplified
_RE_MACRO = re.compile(r"\{\{([^}]+?)\}\}")

# Inline patterns in priority order
_INLINE_PATTERNS = [
    ("embed", _RE_EMBED),
    ("image", _RE_IMAGE),
    ("wikilink", _RE_WIKILINK),
    ("link", _RE_LINK),
    ("code", _RE_CODE),
    ("bolditalic", _RE_BOLDITALIC),
    ("bold", _RE_BOLD),
    ("italic", _RE_ITALIC),
    ("strike", _RE_STRIKE),
    ("highlight", _RE_HIGHLIGHT),
    ("caret_highlight", _RE_CARET_HIGHLIGHT),
    ("blockref", _RE_BLOCKREF),
    ("macro", _RE_MACRO),
    ("bare_url", _RE_BARE_URL),
    ("comment", re.compile(r"%%(.+?)%%")),
]

# ---------------------------------------------------------------------------
# Block-level patterns
# ---------------------------------------------------------------------------

_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#*\s*)?$")
_RE_COMMENT_BLOCK = re.compile(r"^%%\s*$")
_RE_FENCED_CODE_OPEN = re.compile(r"^(`{3,}|~{3,})\s*(.*)")
_RE_HR = re.compile(r"^(?:[-*_]\s*){3,}$")
_RE_BLOCKQUOTE = re.compile(r"^>\s?(.*)")
_RE_UL = re.compile(r"^(\s*)([-*+])\s+(.*)")
_RE_OL = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)")
_RE_CHECKBOX = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)")
_RE_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_RE_TABLE_SEP = re.compile(r"^\|[\s:]*[-]+[\s:|-]*\|\s*$")
_RE_FRONTMATTER_OPEN = re.compile(r"^---\s*$")
_RE_LOGSEQ_PROPERTY = re.compile(r"^(\w[\w-]*)::\s*(.*)")


class Parser(BaseParser):
    """Parse Markdown into a ParseTree."""

    def parse(self, text, file_input=False):
        if isinstance(text, (list, tuple)):
            text = "".join(text)

        tree = ParseTree()
        root = tree.getroot()

        lines = text.split("\n")
        n = len(lines)
        i = 0

        # --- YAML frontmatter ---
        if i < n and _RE_FRONTMATTER_OPEN.match(lines[i].strip()):
            i += 1
            fm_lines = []
            while i < n and not _RE_FRONTMATTER_OPEN.match(lines[i].strip()):
                fm_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing ---
            tree.meta["frontmatter"] = "\n".join(fm_lines)
            # Parse simple key: value pairs
            for fl in fm_lines:
                m = re.match(r"^(\w[\w\s-]*?):\s*(.*)", fl)
                if m:
                    tree.meta[m.group(1).strip()] = m.group(2).strip()

        # --- Main block parsing ---
        while i < n:
            line = lines[i]
            stripped = line.strip()

            # Empty line — skip
            if not stripped:
                i += 1
                continue

            # Obsidian block comment (%% ... %%)
            if _RE_COMMENT_BLOCK.match(stripped):
                block_lines = []
                i += 1
                while i < n and not _RE_COMMENT_BLOCK.match(lines[i].strip()):
                    block_lines.append(lines[i])
                    i += 1
                comment = ET.SubElement(root, "comment")
                comment.text = "\n".join(block_lines)
                if i < n:
                    i += 1  # skip closing %%
                continue

            # Logseq properties at top level (key:: value) — store as meta, skip
            m = _RE_LOGSEQ_PROPERTY.match(stripped)
            if m and i < 3:  # only at very top of file
                tree.meta[m.group(1)] = m.group(2)
                i += 1
                continue

            # Fenced code block
            m = _RE_FENCED_CODE_OPEN.match(stripped)
            if m:
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                lang = m.group(2).strip()
                block_lines = []
                i += 1
                while i < n:
                    cl = lines[i]
                    # Closing fence: same char, at least same length
                    cm = re.match(r"^(`{3,}|~{3,})\s*$", cl.strip())
                    if (
                        cm
                        and cm.group(1)[0] == fence_char
                        and len(cm.group(1)) >= fence_len
                    ):
                        i += 1
                        break
                    block_lines.append(cl)
                    i += 1
                code = ET.SubElement(root, "code")
                if lang:
                    code.attrib["lang"] = lang
                code.text = "\n".join(block_lines)
                continue

            # Heading
            m = _RE_HEADING.match(stripped)
            if m:
                level = str(len(m.group(1)))
                h = ET.SubElement(root, "h", {"level": level})
                self._parse_inline(h, m.group(2).strip())
                i += 1
                continue

            # Horizontal rule
            if _RE_HR.match(stripped):
                ET.SubElement(root, "line")
                i += 1
                continue

            # Table
            if _RE_TABLE_ROW.match(stripped):
                i = self._parse_table(root, lines, i, n)
                continue

            # Blockquote
            m = _RE_BLOCKQUOTE.match(stripped)
            if m:
                i = self._parse_blockquote(root, lines, i, n)
                continue

            # List (checkbox, unordered, ordered)
            if _RE_CHECKBOX.match(line) or _RE_UL.match(line) or _RE_OL.match(line):
                i = self._parse_list(root, lines, i, n)
                continue

            # Logseq property line (key:: value) in the middle of content
            m = _RE_LOGSEQ_PROPERTY.match(stripped)
            if m:
                # Emit as a paragraph with special class
                p = ET.SubElement(root, "p")
                p.attrib["class"] = "property"
                p.text = stripped
                i += 1
                continue

            # Paragraph — collect consecutive non-blank lines that aren't
            # block-level starts
            para_parts = []
            while i < n:
                pline = lines[i]
                pstripped = pline.strip()
                if not pstripped:
                    break
                # Check for block-level interrupts
                if _RE_HEADING.match(pstripped):
                    break
                if _RE_FENCED_CODE_OPEN.match(pstripped):
                    break
                if _RE_HR.match(pstripped):
                    break
                if _RE_BLOCKQUOTE.match(pstripped):
                    break
                if _RE_TABLE_ROW.match(pstripped):
                    break
                if (
                    _RE_CHECKBOX.match(pline)
                    or _RE_UL.match(pline)
                    or _RE_OL.match(pline)
                ):
                    break
                if _RE_LOGSEQ_PROPERTY.match(pstripped):
                    break
                para_parts.append(pstripped)
                i += 1

            if para_parts:
                p = ET.SubElement(root, "p")
                self._parse_inline(p, " ".join(para_parts))

        return tree

    # ---- Block parsers ----

    def _parse_blockquote(self, parent, lines, i, n):
        """Parse a blockquote block (possibly multi-line)."""
        bq = ET.SubElement(parent, "blockquote")
        bq_lines = []
        while i < n:
            m = _RE_BLOCKQUOTE.match(lines[i].strip())
            if m:
                bq_lines.append(m.group(1))
                i += 1
            else:
                break
        # Parse blockquote content recursively (may contain sub-blocks)
        bq_text = "\n".join(bq_lines)
        sub_parser = Parser()
        sub_tree = sub_parser.parse(bq_text)
        sub_root = sub_tree.getroot()
        # Transfer children
        for child in list(sub_root):
            bq.append(child)
        if sub_root.text:
            bq.text = sub_root.text
        return i

    def _parse_list(self, parent, lines, i, n):
        """Parse a list block (ul/ol) with nesting and checkboxes."""
        # Determine list type from first line
        first = lines[i]
        is_ordered = bool(_RE_OL.match(first))

        # Build a flat list of (indent_level, bullet_type, text) tuples
        items = []
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                # Blank line may end or continue a list (loose list);
                # for simplicity break on blank
                break

            # Try checkbox first
            m = _RE_CHECKBOX.match(line)
            if m:
                indent = len(m.group(1))
                checked = m.group(2).lower() == "x"
                bullet = "checked-box" if checked else "unchecked-box"
                items.append((indent, bullet, m.group(3)))
                i += 1
                continue

            # Unordered
            m = _RE_UL.match(line)
            if m:
                indent = len(m.group(1))
                items.append((indent, "*", m.group(3)))
                i += 1
                continue

            # Ordered
            m = _RE_OL.match(line)
            if m:
                indent = len(m.group(1))
                items.append((indent, "1.", m.group(3)))
                i += 1
                continue

            # Continuation line (indented, no bullet) — append to last item
            if line.startswith((" ", "\t")) and items:
                # Check if it's a Logseq property (key:: value) — skip
                pm = _RE_LOGSEQ_PROPERTY.match(stripped)
                if pm:
                    i += 1
                    continue
                # Append to previous item text
                prev_indent, prev_bullet, prev_text = items[-1]
                items[-1] = (prev_indent, prev_bullet, prev_text + " " + stripped)
                i += 1
                continue

            # Not a list line — stop
            break

        # Build tree from flat items using indent levels
        self._build_list_tree(parent, items, 0, is_ordered)
        return i

    def _build_list_tree(self, parent, items, start_indent, is_ordered):
        """Build nested list elements from flat (indent, bullet, text) list."""
        if not items:
            return

        tag = "ol" if is_ordered else "ul"
        ul = ET.SubElement(parent, tag)

        idx = 0
        while idx < len(items):
            indent, bullet, text = items[idx]

            li = ET.SubElement(ul, "li", {"bullet": bullet})
            self._parse_inline(li, text)
            idx += 1

            # Collect deeper-indented children
            children = []
            while idx < len(items) and items[idx][0] > indent:
                children.append(items[idx])
                idx += 1

            if children:
                child_ordered = children[0][1] not in (
                    "*",
                    "checked-box",
                    "unchecked-box",
                )
                # Shift indent levels
                min_child = min(c[0] for c in children)
                shifted = [(c[0] - min_child, c[1], c[2]) for c in children]
                self._build_list_tree(li, shifted, 0, child_ordered)

    def _parse_table(self, parent, lines, i, n):
        """Parse a Markdown table."""
        table = ET.SubElement(parent, "table")

        # Header row
        m = _RE_TABLE_ROW.match(lines[i].strip())
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            thead = ET.SubElement(table, "thead")
            tr = ET.SubElement(thead, "tr")
            for cell in cells:
                th = ET.SubElement(tr, "th")
                self._parse_inline(th, cell)
            i += 1

        # Separator row (skip)
        if i < n and _RE_TABLE_SEP.match(lines[i].strip()):
            i += 1

        # Body rows
        tbody = ET.SubElement(table, "tbody")
        while i < n:
            m = _RE_TABLE_ROW.match(lines[i].strip())
            if not m:
                break
            cells = [c.strip() for c in m.group(1).split("|")]
            tr = ET.SubElement(tbody, "tr")
            for cell in cells:
                td = ET.SubElement(tr, "td")
                self._parse_inline(td, cell)
            i += 1

        return i

    # ---- Inline parser ----

    def _parse_inline(self, parent, text):
        """Parse Markdown inline markup recursively.

        Finds the earliest match among all inline patterns,
        processes it, and recurses on the remaining text.
        """
        if not text:
            return

        best = None
        best_kind = None
        best_start = len(text)

        for kind, pat in _INLINE_PATTERNS:
            m = pat.search(text)
            if m and m.start() < best_start:
                best = m
                best_kind = kind
                best_start = m.start()

        if best is None:
            # No patterns found — all plain text
            self._append_text(parent, text)
            return

        # Text before the match
        before = text[:best_start]
        if before:
            self._append_text(parent, before)

        # Process the match
        if best_kind == "embed":
            target = best.group(1).strip()
            option = (best.group(2) or "").strip()
            attrs = {"src": target, "embed": "true"}

            # Obsidian embed option semantics:
            # - |300 -> width
            # - |300x200 -> width + height
            # - |Alias text -> display text / alt
            if option:
                attrs["embed_option"] = option
                m_wh = re.fullmatch(r"(\d+)x(\d+)", option)
                if m_wh:
                    attrs["width"] = m_wh.group(1)
                    attrs["height"] = m_wh.group(2)
                    attrs["alt"] = target
                elif option.isdigit():
                    attrs["width"] = option
                    attrs["alt"] = target
                else:
                    attrs["alt"] = option
            else:
                attrs["alt"] = target

            ET.SubElement(parent, "img", attrs)

        elif best_kind == "image":
            alt = best.group(1)
            src = best.group(2).strip()
            if src.startswith("<") and src.endswith(">"):
                src = src[1:-1].strip()
            elem = ET.SubElement(parent, "img", {"src": src, "alt": alt})

        elif best_kind == "wikilink":
            target = best.group(1).strip()
            alias = best.group(2)
            elem = ET.SubElement(parent, "link", {"href": target})
            elem.text = alias.strip() if alias else target

        elif best_kind == "link":
            link_text = best.group(1)
            href = best.group(2).strip()
            if href.startswith("<") and href.endswith(">"):
                href = href[1:-1].strip()
            elem = ET.SubElement(parent, "link", {"href": href})
            # Parse inline markup within link text
            self._parse_inline(elem, link_text)

        elif best_kind == "code":
            elem = ET.SubElement(parent, "code")
            elem.text = best.group(1)

        elif best_kind == "bolditalic":
            elem = ET.SubElement(parent, "strong")
            inner_elem = ET.SubElement(elem, "emphasis")
            inner_text = best.group(1) or best.group(2)
            self._parse_inline(inner_elem, inner_text)

        elif best_kind == "bold":
            elem = ET.SubElement(parent, "strong")
            inner = best.group(1) or best.group(2)
            self._parse_inline(elem, inner)

        elif best_kind == "italic":
            elem = ET.SubElement(parent, "emphasis")
            inner = best.group(1) or best.group(2)
            self._parse_inline(elem, inner)

        elif best_kind == "strike":
            elem = ET.SubElement(parent, "strike")
            self._parse_inline(elem, best.group(1))

        elif best_kind == "highlight":
            elem = ET.SubElement(parent, "mark")
            self._parse_inline(elem, best.group(1))

        elif best_kind == "caret_highlight":
            elem = ET.SubElement(parent, "mark")
            self._parse_inline(elem, best.group(1))

        elif best_kind == "blockref":
            elem = ET.SubElement(parent, "span")
            elem.attrib["class"] = "block-ref"
            elem.attrib["data-ref"] = best.group(1)
            elem.text = "((" + best.group(1)[:8] + "…))"

        elif best_kind == "macro":
            elem = ET.SubElement(parent, "macro")
            elem.attrib["name"] = best.group(1).split(" ")[0]
            elem.text = best.group(1)

        elif best_kind == "comment":
            elem = ET.SubElement(parent, "comment")
            elem.text = best.group(1)

        elif best_kind == "bare_url":
            url = best.group(0)
            elem = ET.SubElement(parent, "link", {"href": url})
            elem.text = url

        else:
            elem = ET.SubElement(parent, "span")
            elem.text = best.group(0)

        # Text after the match — recurse
        after = text[best.end() :]
        if after:
            self._parse_inline(parent, after)

    def _append_text(self, parent, text):
        """Append text to the right place in the element tree."""
        if len(parent) == 0:
            parent.text = (parent.text or "") + text
        else:
            parent[-1].tail = (parent[-1].tail or "") + text


class Dumper(BaseDumper):
    """Dump ParseTree as Markdown."""

    def dump(self, tree, file_output=False):
        lines = []
        root = tree.getroot()

        # Emit frontmatter if present
        if tree.meta.get("frontmatter"):
            lines.append("---\n")
            lines.append(tree.meta["frontmatter"] + "\n")
            lines.append("---\n")

        self._dump_node(root, lines, indent=0)
        return lines

    def _dump_node(self, elem, lines, indent=0):
        tag = elem.tag

        if tag == "moonstone-tree":
            if elem.text and elem.text.strip():
                lines.append(elem.text)
            for child in elem:
                self._dump_node(child, lines, indent)
                if child.tail and child.tail.strip():
                    lines.append(child.tail)

        elif tag == "h":
            level = int(elem.attrib.get("level", "1"))
            prefix = "#" * level
            lines.append("%s %s\n\n" % (prefix, self._inline(elem)))

        elif tag == "p":
            cls = elem.attrib.get("class", "")
            text = self._inline(elem)
            if cls == "property":
                lines.append(text + "\n")
            else:
                lines.append(text + "\n\n")

        elif tag in ("ul", "ol"):
            for child in elem:
                self._dump_node(child, lines, indent)
            lines.append("\n")

        elif tag == "li":
            bullet = elem.attrib.get("bullet", "*")
            text = self._inline(elem)
            prefix = "  " * indent

            if bullet == "checked-box":
                lines.append("%s- [x] %s\n" % (prefix, text))
            elif bullet == "unchecked-box":
                lines.append("%s- [ ] %s\n" % (prefix, text))
            elif bullet == "xchecked-box":
                lines.append("%s- [x] %s\n" % (prefix, text))
            elif bullet and bullet[0].isdigit():
                lines.append("%s%s %s\n" % (prefix, bullet, text))
            else:
                lines.append("%s- %s\n" % (prefix, text))

            # Nested lists
            for child in elem:
                if child.tag in ("ul", "ol"):
                    for grandchild in child:
                        self._dump_node(grandchild, lines, indent + 1)

        elif tag == "blockquote":
            # Dump inner content, then prefix each line with >
            inner_lines = []
            for child in elem:
                self._dump_node(child, inner_lines, indent)
            for il in inner_lines:
                for subline in il.split("\n"):
                    if subline.strip():
                        lines.append("> %s\n" % subline)
            lines.append("\n")

        elif tag == "table":
            self._dump_table(elem, lines)

        elif tag == "pre":
            lines.append("```\n%s\n```\n\n" % (elem.text or ""))

        elif tag == "code":
            lang = elem.attrib.get("lang", "")
            code_text = elem.text or ""
            if "\n" in code_text:
                lines.append("```%s\n%s\n```\n\n" % (lang, code_text))
            else:
                lines.append("`%s`" % code_text)

        elif tag == "line":
            lines.append("---\n\n")

        elif tag == "img":
            src = elem.attrib.get("src", "")
            alt = elem.attrib.get("alt", "")
            is_embed = elem.attrib.get("embed", "")
            embed_option = elem.attrib.get("embed_option", "")
            if self.linker:
                src = self.linker.img(src)
            if is_embed:
                if embed_option:
                    lines.append("![[%s|%s]]" % (src, embed_option))
                else:
                    lines.append("![[%s]]" % src)
            else:
                lines.append("![%s](%s)" % (alt, src))

        else:
            text = self._inline(elem)
            if text:
                lines.append(text)

    def _dump_table(self, table_elem, lines):
        """Dump a table element as Markdown."""
        rows = []
        for section in table_elem:
            if section.tag in ("thead", "tbody"):
                for tr in section:
                    if tr.tag == "tr":
                        cells = []
                        for cell in tr:
                            cells.append(self._inline(cell))
                        rows.append(cells)
            elif section.tag == "tr":
                cells = []
                for cell in section:
                    cells.append(self._inline(cell))
                rows.append(cells)

        if not rows:
            return

        # Determine column widths
        n_cols = max(len(r) for r in rows) if rows else 0
        widths = [3] * n_cols
        for row in rows:
            for j, cell in enumerate(row):
                if j < n_cols:
                    widths[j] = max(widths[j], len(cell))

        # Header row
        header = rows[0] if rows else []
        hdr_cells = []
        for j in range(n_cols):
            cell = header[j] if j < len(header) else ""
            hdr_cells.append(" " + cell.ljust(widths[j]) + " ")
        lines.append("|" + "|".join(hdr_cells) + "|\n")

        # Separator
        sep_cells = []
        for j in range(n_cols):
            sep_cells.append("-" * (widths[j] + 2))
        lines.append("|" + "|".join(sep_cells) + "|\n")

        # Data rows
        for row in rows[1:]:
            data_cells = []
            for j in range(n_cols):
                cell = row[j] if j < len(row) else ""
                data_cells.append(" " + cell.ljust(widths[j]) + " ")
            lines.append("|" + "|".join(data_cells) + "|\n")

        lines.append("\n")

    def _inline(self, elem):
        """Render inline content of an element as Markdown text."""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(self._inline_elem(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def _inline_elem(self, elem):
        tag = elem.tag
        inner = self._inline(elem)

        if tag == "strong":
            return "**%s**" % inner
        elif tag == "emphasis":
            return "*%s*" % inner
        elif tag == "mark":
            return "==%s==" % inner
        elif tag == "strike":
            return "~~%s~~" % inner
        elif tag == "code":
            return "`%s`" % (elem.text or "")
        elif tag == "link":
            href = elem.attrib.get("href", "")
            if self.linker:
                href = self.linker.link(href)
            # Wiki link (no protocol) vs markdown link
            if "://" not in href and not href.startswith("#"):
                return "[[%s]]" % href if inner == href else "[[%s|%s]]" % (href, inner)
            return "[%s](%s)" % (inner, href)
        elif tag == "img":
            src = elem.attrib.get("src", "")
            alt = elem.attrib.get("alt", "")
            is_embed = elem.attrib.get("embed", "")
            embed_option = elem.attrib.get("embed_option", "")
            if self.linker:
                src = self.linker.img(src)
            if is_embed:
                if embed_option:
                    return "![[%s|%s]]" % (src, embed_option)
                return "![[%s]]" % src
            return "![%s](%s)" % (alt, src)
        elif tag == "tag":
            return "#%s" % elem.attrib.get("name", "")
        elif tag == "sup":
            return "<sup>%s</sup>" % inner
        elif tag == "sub":
            return "<sub>%s</sub>" % inner
        elif tag == "span":
            cls = elem.attrib.get("class", "")
            if cls == "block-ref":
                ref = elem.attrib.get("data-ref", "")
                return "((%s))" % ref
            elif cls == "macro":
                return elem.text or ""
            return inner
        elif tag in ("ul", "ol"):
            # Nested list inside an <li> — skip here, handled by _dump_node
            return ""

        return inner
