# -*- coding: utf-8 -*-
"""Formats package for Moonstone.

Standalone formats module — provides ParseTree (ElementTree-based AST),
get_format() dispatcher, and base Parser/Dumper classes.

The ParseTree is an XML tree:
    <moonstone-tree>
      <h level="1">Title</h>
      <p>Text <strong>bold</strong></p>
      <tag name="mytag">@mytag</tag>
    </moonstone-tree>
"""

import re
from xml.etree import ElementTree as ET


def get_format(name):
    """Return a format module by name.

    @param name: 'wiki', 'html', 'plain', 'markdown'
    @returns: module with Parser and Dumper classes
    """
    if name == "wiki":
        from moonstone.formats import wiki

        return wiki
    elif name == "html":
        from moonstone.formats import html

        return html
    elif name == "plain":
        from moonstone.formats import plain

        return plain
    elif name == "markdown":
        from moonstone.formats import markdown

        return markdown
    else:
        raise ValueError("Unknown format: %s" % name)


def heading_to_anchor(text):
    """Convert heading text to a valid anchor string."""
    anchor = text.strip().lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"[\s]+", "-", anchor)
    return anchor


class ParseTree:
    """ElementTree wrapper for page content AST.

    The root element is <moonstone-tree>. Child elements represent
    paragraphs, headings, formatting, links, images, tags, etc.

    Provides the duck-typing interface used by WebBridge api.py:
    - .hascontent
    - .meta (dict of headers like Content-Type, Creation-Date)
    - .get_heading_text()
    - .tostring() / .fromstring()
    - ._etree (access to raw ElementTree for _parsetree_to_json)
    - iteration over elements
    """

    def __init__(self, root=None):
        if root is None:
            root = ET.Element("moonstone-tree")
        if isinstance(root, ET.ElementTree):
            self._etree = root
        elif isinstance(root, ET.Element):
            self._etree = ET.ElementTree(root)
        else:
            self._etree = ET.ElementTree(ET.Element("moonstone-tree"))

        self.meta = {}  # Headers: Content-Type, Wiki-Format, Creation-Date

    @property
    def hascontent(self):
        """Check if tree has any real content."""
        root = self._etree.getroot()
        if root.text and root.text.strip():
            return True
        for child in root:
            return True  # Has at least one child element
        return False

    def getroot(self):
        return self._etree.getroot()

    def tostring(self):
        """Serialize tree to XML string."""
        return ET.tostring(self._etree.getroot(), encoding="unicode")

    @classmethod
    def fromstring(cls, text):
        """Create ParseTree from XML string."""
        root = ET.fromstring(text)
        tree = cls(root)
        return tree

    def copy(self):
        """Return a deep copy of this tree."""
        import copy

        new = ParseTree()
        new._etree = copy.deepcopy(self._etree)
        new.meta = dict(self.meta)
        return new

    def get_heading_text(self):
        """Get the text of the first heading (h level="1")."""
        root = self._etree.getroot()
        for elem in root:
            if elem.tag == "h":
                level = elem.attrib.get("level", "1")
                if level == "1":
                    return self._get_element_text(elem)
        return None

    def _get_element_text(self, elem):
        """Get all text content from an element and its children."""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(self._get_element_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def iter(self, tag=None):
        """Iterate over all elements."""
        return self._etree.getroot().iter(tag)

    def iter_href(self):
        """Iterate over all link elements, yielding href strings."""
        for elem in self.iter("link"):
            href = elem.attrib.get("href", "")
            if href:
                yield href

    def iter_tag_names(self):
        """Iterate over all @tag elements, yielding tag names."""
        for elem in self.iter("tag"):
            name = elem.attrib.get("name", "")
            if name:
                yield name

    def extend(self, other):
        """Append all children from another ParseTree."""
        root = self._etree.getroot()
        other_root = other._etree.getroot()
        for child in other_root:
            root.append(child)
        # Also append any trailing text
        if other_root.text:
            if len(root) > 0:
                last = root[-1]
                last.tail = (last.tail or "") + other_root.text
            else:
                root.text = (root.text or "") + other_root.text

    def __iter__(self):
        return iter(self._etree.getroot())


class BaseParser:
    """Base class for format parsers."""

    def parse(self, text, file_input=False):
        """Parse text into a ParseTree.

        @param text: string or list of lines
        @param file_input: if True, text includes file headers
        @returns: ParseTree
        """
        raise NotImplementedError


class BaseDumper:
    """Base class for format dumpers."""

    def __init__(self, linker=None):
        self.linker = linker

    def dump(self, tree, file_output=False):
        """Dump a ParseTree to a list of strings.

        @param tree: ParseTree
        @param file_output: if True, include file headers
        @returns: list of strings
        """
        raise NotImplementedError
