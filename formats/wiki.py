# -*- coding: utf-8 -*-
"""Moonstone format parser and dumper for Moonstone.

Handles the Moonstone wiki markup format:
    Content-Type: text/x-moonstone-wiki
    Wiki-Format: moonstone 1.0
    Creation-Date: 2026-01-15T09:00:00+03:00

    ====== Heading 1 ======
    ===== Heading 2 =====

    **bold**  //italic//  __underline__  ~~strikethrough~~  ''monospace''
    [[Page:Link]]  [[Page:Link|Label]]
    {{image.png}}
    * Bullet    1. Numbered    [ ] Checkbox    [*] Checked
    @tag
    '''verbatim block'''
    {{{code block}}}
    --- (horizontal line)
"""

import re
from xml.etree import ElementTree as ET

from moonstone.formats import ParseTree, BaseParser, BaseDumper

# ---- Header parsing ----

_HEADER_RE = re.compile(r"^([\w-]+):\s*(.*)$")


def _parse_headers(text):
    """Parse file headers and return (headers_dict, body_text)."""
    headers = {}
    lines = text.split("\n") if isinstance(text, str) else list(text)
    body_start = 0

    for i, line in enumerate(lines):
        line = line.rstrip("\r\n")
        if not line.strip():
            body_start = i + 1
            break
        m = _HEADER_RE.match(line)
        if m:
            headers[m.group(1)] = m.group(2).strip()
            body_start = i + 1
        else:
            break

    body = "\n".join(lines[body_start:])
    return headers, body


def _dump_headers(meta):
    """Dump file headers from meta dict."""
    lines = []
    if "Content-Type" not in meta:
        meta["Content-Type"] = "text/x-moonstone-wiki"
    if "Wiki-Format" not in meta:
        meta["Wiki-Format"] = "moonstone 1.0"

    # Preserve order: Content-Type, Wiki-Format, Creation-Date, then rest
    order = ["Content-Type", "Wiki-Format", "Creation-Date"]
    done = set()
    for key in order:
        if key in meta:
            lines.append("%s: %s\n" % (key, meta[key]))
            done.add(key)
    for key, val in meta.items():
        if key not in done:
            lines.append("%s: %s\n" % (key, val))
    lines.append("\n")
    return lines


# ---- Heading patterns ----
# ====== H1 ====== (6 '='), ===== H2 ===== (5 '='), etc.

_HEADING_RE = re.compile(r"^(={2,6})\s+(.+?)\s+\1\s*$")

_HEADING_LEVEL = {6: "1", 5: "2", 4: "3", 3: "4", 2: "5"}

# ---- Inline patterns ----

_LINK_RE = re.compile(r"\[\[(.+?)(?:\|(.+?))?\]\]")
_IMAGE_RE = re.compile(r"\{\{(.+?)(?:\|(.+?))?\}\}")
_TAG_RE = re.compile(r"(?<!\w)@(\w+)")

# Inline formatting (order matters for greedy matching)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"//(.+?)//")
_UNDERLINE_RE = re.compile(r"__(.+?)__")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_MONO_RE = re.compile(r"''(.+?)''")
_SUP_RE = re.compile(r"\^\{(.+?)\}")
_SUB_RE = re.compile(r"_\{(.+?)\}")

# Block patterns
_BULLET_RE = re.compile(r"^(\t*)(\*)\s+(.*)")
_NUMBERED_RE = re.compile(r"^(\t*)(\d+\.)\s+(.*)")
_CHECKBOX_RE = re.compile(r"^(\t*)\[([ *x>])\]\s+(.*)")
_VERBATIM_START_RE = re.compile(r"^'''$")
_CODE_START_RE = re.compile(r"^\{\{\{(?:\s*$|(.*))")
_CODE_END_RE = re.compile(r"^\}\}\}\s*$")
_HR_RE = re.compile(r"^-{3,}\s*$")


class Parser(BaseParser):
    """Parse wiki markup into a ParseTree."""

    def parse(self, text, file_input=False):
        if isinstance(text, (list, tuple)):
            text = "".join(text)

        tree = ParseTree()
        root = tree.getroot()

        # Parse headers if file input
        if file_input:
            headers, text = _parse_headers(text)
            tree.meta.update(headers)
        else:
            # Check if text starts with headers anyway
            if text.lstrip().startswith("Content-Type:"):
                headers, text = _parse_headers(text)
                tree.meta.update(headers)

        lines = text.split("\n")
        self._parse_lines(root, lines)
        return tree

    def _parse_lines(self, root, lines):
        """Parse lines into XML elements under root."""
        i = 0
        current_list = None  # track list nesting
        list_stack = []

        while i < len(lines):
            line = lines[i]

            # ---- Verbatim block ''' ... ''' ----
            if _VERBATIM_START_RE.match(line.strip()):
                self._close_list(root, list_stack)
                current_list = None
                block_lines = []
                i += 1
                while i < len(lines):
                    if _VERBATIM_START_RE.match(lines[i].strip()):
                        i += 1
                        break
                    block_lines.append(lines[i])
                    i += 1
                pre = ET.SubElement(root, "pre")
                pre.text = "\n".join(block_lines)
                continue

            # ---- Code block {{{ ... }}} ----
            m = _CODE_START_RE.match(line.strip())
            if m:
                self._close_list(root, list_stack)
                current_list = None
                block_lines = []
                lang = (m.group(1) or "").strip()
                i += 1
                while i < len(lines):
                    if _CODE_END_RE.match(lines[i].strip()):
                        i += 1
                        break
                    block_lines.append(lines[i])
                    i += 1
                code = ET.SubElement(root, "code")
                if lang:
                    code.attrib["lang"] = lang
                code.text = "\n".join(block_lines)
                continue

            # ---- Horizontal rule ----
            if _HR_RE.match(line.strip()):
                self._close_list(root, list_stack)
                current_list = None
                ET.SubElement(root, "line")
                i += 1
                continue

            # ---- Heading ----
            m = _HEADING_RE.match(line)
            if m:
                self._close_list(root, list_stack)
                current_list = None
                n_eq = len(m.group(1))
                level = _HEADING_LEVEL.get(n_eq, "5")
                h = ET.SubElement(root, "h", {"level": level})
                self._parse_inline(h, m.group(2).strip())
                i += 1
                continue

            # ---- Checkbox ----
            m = _CHECKBOX_RE.match(line)
            if m:
                indent = len(m.group(1))
                state = m.group(2)
                content = m.group(3)

                bullet_map = {
                    " ": "unchecked-box",
                    "*": "checked-box",
                    "x": "xchecked-box",
                    ">": "migrated-box",
                }
                bullet = bullet_map.get(state, "unchecked-box")

                ul = self._ensure_list(root, list_stack, indent, "ul")
                li = ET.SubElement(ul, "li", {"bullet": bullet, "indent": str(indent)})
                self._parse_inline(li, content)
                i += 1
                continue

            # ---- Bullet list ----
            m = _BULLET_RE.match(line)
            if m:
                indent = len(m.group(1))
                content = m.group(3)
                ul = self._ensure_list(root, list_stack, indent, "ul")
                li = ET.SubElement(ul, "li", {"bullet": "*", "indent": str(indent)})
                self._parse_inline(li, content)
                i += 1
                continue

            # ---- Numbered list ----
            m = _NUMBERED_RE.match(line)
            if m:
                indent = len(m.group(1))
                content = m.group(3)
                ol = self._ensure_list(root, list_stack, indent, "ol")
                li = ET.SubElement(
                    ol, "li", {"bullet": m.group(2), "indent": str(indent)}
                )
                self._parse_inline(li, content)
                i += 1
                continue

            # ---- Empty line ----
            if not line.strip():
                self._close_list(root, list_stack)
                current_list = None
                i += 1
                continue

            # ---- Regular paragraph ----
            self._close_list(root, list_stack)
            current_list = None
            p = ET.SubElement(root, "p")
            self._parse_inline(p, line)
            i += 1

    def _ensure_list(self, root, list_stack, indent, tag):
        """Get or create a list element at the right indent level."""
        if list_stack:
            # Use the last list if same or deeper indent
            return list_stack[-1]
        else:
            lst = ET.SubElement(root, tag)
            list_stack.append(lst)
            return lst

    def _close_list(self, root, list_stack):
        """Close all open lists."""
        list_stack.clear()

    def _parse_inline(self, parent, text):
        """Parse inline markup within a text string.

        Builds child elements under parent for bold, italic,
        links, images, tags, etc.
        """
        if not text:
            return

        # We process the text by finding the earliest match of any
        # inline pattern and splitting around it.
        patterns = [
            ("link", _LINK_RE),
            ("image", _IMAGE_RE),
            ("bold", _BOLD_RE),
            ("italic", _ITALIC_RE),
            ("underline", _UNDERLINE_RE),
            ("strike", _STRIKE_RE),
            ("mono", _MONO_RE),
            ("tag", _TAG_RE),
        ]

        # Find the earliest match
        best_match = None
        best_kind = None
        best_start = len(text)

        for kind, pattern in patterns:
            m = pattern.search(text)
            if m and m.start() < best_start:
                best_match = m
                best_kind = kind
                best_start = m.start()

        if best_match is None:
            # No inline markup — just text
            self._append_text(parent, text)
            return

        # Text before the match
        before = text[:best_start]
        if before:
            self._append_text(parent, before)

        # Process the match
        if best_kind == "link":
            href = best_match.group(1).strip()
            label = best_match.group(2)
            elem = ET.SubElement(parent, "link", {"href": href})
            if label:
                elem.text = label.strip()
            else:
                elem.text = href

        elif best_kind == "image":
            src = best_match.group(1).strip()
            alt = best_match.group(2)
            attrib = {"src": src}
            if alt:
                attrib["alt"] = alt.strip()
            elem = ET.SubElement(parent, "img", attrib)

        elif best_kind == "bold":
            elem = ET.SubElement(parent, "strong")
            self._parse_inline(elem, best_match.group(1))

        elif best_kind == "italic":
            elem = ET.SubElement(parent, "emphasis")
            self._parse_inline(elem, best_match.group(1))

        elif best_kind == "underline":
            elem = ET.SubElement(parent, "mark")
            self._parse_inline(elem, best_match.group(1))

        elif best_kind == "strike":
            elem = ET.SubElement(parent, "strike")
            self._parse_inline(elem, best_match.group(1))

        elif best_kind == "mono":
            elem = ET.SubElement(parent, "code")
            elem.text = best_match.group(1)

        elif best_kind == "tag":
            tag_name = best_match.group(1)
            elem = ET.SubElement(parent, "tag", {"name": tag_name})
            elem.text = "@" + tag_name

        # Text after the match — continue parsing
        after = text[best_match.end() :]
        if after:
            # Set as tail of the created element or continue inline parsing
            self._parse_inline_tail(parent, elem, after)

    def _parse_inline_tail(self, parent, elem, text):
        """Parse remaining text after an inline element (as tail)."""
        # Check if there's more inline markup in the tail
        patterns = [
            ("link", _LINK_RE),
            ("image", _IMAGE_RE),
            ("bold", _BOLD_RE),
            ("italic", _ITALIC_RE),
            ("underline", _UNDERLINE_RE),
            ("strike", _STRIKE_RE),
            ("mono", _MONO_RE),
            ("tag", _TAG_RE),
        ]

        best_match = None
        best_kind = None
        best_start = len(text)

        for kind, pattern in patterns:
            m = pattern.search(text)
            if m and m.start() < best_start:
                best_match = m
                best_kind = kind
                best_start = m.start()

        if best_match is None:
            elem.tail = (elem.tail or "") + text
            return

        # Text before next match goes as tail
        before = text[:best_start]
        if before:
            elem.tail = (elem.tail or "") + before

        # Remaining text — parse as new inline children of parent
        remaining = text[best_start:]
        self._parse_inline(parent, remaining)

    def _append_text(self, elem, text):
        """Append plain text to an element."""
        if len(elem) == 0:
            elem.text = (elem.text or "") + text
        else:
            last = elem[-1]
            last.tail = (last.tail or "") + text


class Dumper(BaseDumper):
    """Dump a ParseTree back to Moonstone wiki markup."""

    def dump(self, tree, file_output=False):
        lines = []

        if file_output:
            lines.extend(_dump_headers(tree.meta))

        root = tree.getroot()
        self._dump_element(root, lines, indent_level=0)
        return lines

    def _dump_element(self, elem, lines, indent_level=0):
        """Recursively dump an element and its children."""
        tag = elem.tag

        if tag == "moonstone-tree":
            if elem.text and elem.text.strip():
                lines.append(elem.text)
            for child in elem:
                self._dump_element(child, lines, indent_level)
                if child.tail:
                    lines.append(child.tail)

        elif tag == "h":
            level = int(elem.attrib.get("level", "1"))
            n_eq = {1: 6, 2: 5, 3: 4, 4: 3, 5: 2}.get(level, 2)
            prefix = "=" * n_eq
            text = self._dump_inline(elem)
            lines.append("%s %s %s\n" % (prefix, text, prefix))

        elif tag == "p":
            text = self._dump_inline(elem)
            lines.append(text + "\n")

        elif tag in ("ul", "ol"):
            for child in elem:
                self._dump_element(child, lines, indent_level)

        elif tag == "li":
            indent = "\t" * indent_level
            bullet = elem.attrib.get("bullet", "*")
            text = self._dump_inline(elem)

            if bullet == "unchecked-box":
                lines.append("%s[ ] %s\n" % (indent, text))
            elif bullet == "checked-box":
                lines.append("%s[*] %s\n" % (indent, text))
            elif bullet == "xchecked-box":
                lines.append("%s[x] %s\n" % (indent, text))
            elif bullet == "migrated-box":
                lines.append("%s[>] %s\n" % (indent, text))
            elif bullet and bullet[0].isdigit():
                lines.append("%s%s %s\n" % (indent, bullet, text))
            else:
                lines.append("%s* %s\n" % (indent, text))

        elif tag == "pre":
            lines.append("'''\n")
            if elem.text:
                lines.append(elem.text + "\n")
            lines.append("'''\n")

        elif tag == "code":
            lang = elem.attrib.get("lang", "")
            if "\n" in (elem.text or ""):
                # Block code
                lines.append("{{{%s\n" % (" " + lang if lang else ""))
                if elem.text:
                    lines.append(elem.text + "\n")
                lines.append("}}}\n")
            else:
                # Inline code handled by _dump_inline
                pass

        elif tag == "line":
            lines.append("---\n")

        elif tag == "img":
            src = elem.attrib.get("src", "")
            alt = elem.attrib.get("alt", "")
            if alt:
                lines.append("{{%s|%s}}" % (src, alt))
            else:
                lines.append("{{%s}}" % src)

        else:
            # Unknown tag — dump as text
            text = self._dump_inline(elem)
            if text:
                lines.append(text)

    def _dump_inline(self, elem):
        """Dump inline content of an element to wiki markup string."""
        parts = []
        if elem.text:
            parts.append(elem.text)

        for child in elem:
            parts.append(self._inline_element(child))
            if child.tail:
                parts.append(child.tail)

        return "".join(parts)

    def _inline_element(self, elem):
        """Convert a single inline element to wiki markup."""
        tag = elem.tag
        inner = self._dump_inline(elem)

        if tag == "strong":
            return "**%s**" % inner
        elif tag == "emphasis":
            return "//%s//" % inner
        elif tag == "mark":
            return "__%s__" % inner
        elif tag == "strike":
            return "~~%s~~" % inner
        elif tag == "code":
            return "''%s''" % (elem.text or "")
        elif tag == "link":
            href = elem.attrib.get("href", "")
            label = inner
            if self.linker:
                href = self.linker.link(href)
            if label and label != href:
                return "[[%s|%s]]" % (href, label)
            return "[[%s]]" % href
        elif tag == "img":
            src = elem.attrib.get("src", "")
            alt = elem.attrib.get("alt", "")
            if self.linker:
                src = self.linker.img(src)
            if alt:
                return "{{%s|%s}}" % (src, alt)
            return "{{%s}}" % src
        elif tag == "tag":
            name = elem.attrib.get("name", "")
            return "@%s" % name
        elif tag == "sup":
            return "^{%s}" % inner
        elif tag == "sub":
            return "_{%s}" % inner
        elif tag == "h":
            # Heading inside inline context (shouldn't happen but handle)
            return inner
        elif tag == "anchor":
            return ""
        else:
            return inner
