# -*- coding: utf-8 -*-
"""Plain text dumper for Moonstone.

Converts ParseTree → plain text (strips all markup).
"""

from moonstone.formats import BaseDumper, BaseParser, ParseTree
from xml.etree import ElementTree as ET


class Parser(BaseParser):
    """Parse plain text into a ParseTree (wraps each line in <p>)."""

    def parse(self, text, file_input=False):
        if isinstance(text, (list, tuple)):
            text = "".join(text)

        tree = ParseTree()
        root = tree.getroot()

        for line in text.split("\n"):
            if line.strip():
                p = ET.SubElement(root, "p")
                p.text = line
        return tree


class Dumper(BaseDumper):
    """Dump ParseTree as plain text (all formatting stripped)."""

    def dump(self, tree, file_output=False):
        lines = []
        root = tree.getroot()
        self._dump_node(root, lines)
        return lines

    def _dump_node(self, elem, lines):
        tag = elem.tag

        if tag == "moonstone-tree":
            if elem.text and elem.text.strip():
                lines.append(elem.text)
            for child in elem:
                self._dump_node(child, lines)
                if child.tail:
                    lines.append(child.tail)

        elif tag == "h":
            text = self._get_text(elem)
            lines.append(text + "\n")
            lines.append("\n")

        elif tag == "p":
            text = self._get_text(elem)
            lines.append(text + "\n")

        elif tag in ("ul", "ol"):
            for child in elem:
                self._dump_node(child, lines)

        elif tag == "li":
            bullet = elem.attrib.get("bullet", "*")
            indent = int(elem.attrib.get("indent", "0"))
            text = self._get_text(elem)
            prefix = "  " * indent

            if "box" in bullet:
                check = "[x]" if "checked" in bullet else "[ ]"
                lines.append("%s%s %s\n" % (prefix, check, text))
            elif bullet and bullet[0].isdigit():
                lines.append("%s%s %s\n" % (prefix, bullet, text))
            else:
                lines.append("%s- %s\n" % (prefix, text))

        elif tag == "pre":
            if elem.text:
                lines.append(elem.text + "\n")

        elif tag == "code":
            if elem.text:
                lines.append(elem.text + "\n")

        elif tag == "blockquote":
            for child in elem:
                child_lines = []
                self._dump_node(child, child_lines)
                for cl in child_lines:
                    for sub in cl.split("\n"):
                        if sub.strip():
                            lines.append("> %s\n" % sub)

        elif tag == "table":
            for section in elem:
                for tr in section:
                    if tr.tag == "tr":
                        cells = [self._get_text(td) for td in tr]
                        lines.append(" | ".join(cells) + "\n")

        elif tag in ("thead", "tbody", "tr", "th", "td"):
            text = self._get_text(elem)
            if text:
                lines.append(text)

        elif tag == "line":
            lines.append("---\n")

        elif tag == "img":
            src = elem.attrib.get("src", "")
            lines.append("[Image: %s]\n" % src)

        else:
            text = self._get_text(elem)
            if text:
                lines.append(text)

    def _get_text(self, elem):
        """Get all text content recursively."""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(self._get_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)
