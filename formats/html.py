# -*- coding: utf-8 -*-
"""HTML dumper for Moonstone.

Converts ParseTree → HTML output.
Supports all elements from the markdown parser: headings, paragraphs,
lists (nested, checkboxes), blockquotes, tables, code blocks,
images, links, wiki-links, embeds, highlights, and inline formatting.
"""

from html import escape as html_escape
from moonstone.formats import BaseDumper, BaseParser, ParseTree


class Parser(BaseParser):
    """Stub HTML parser — not typically used for writing."""

    def parse(self, text, file_input=False):
        tree = ParseTree()
        from xml.etree import ElementTree as ET

        p = ET.SubElement(tree.getroot(), "p")
        p.text = text if isinstance(text, str) else "".join(text)
        return tree


class Dumper(BaseDumper):
    """Dump ParseTree as HTML."""

    def dump(self, tree, file_output=False):
        lines = []

        # Dump metadata as semantic HTML
        if tree.meta:
            lines.append('<div class="ms-frontmatter">\n')
            for k, v in tree.meta.items():
                # skip raw frontmatter block to avoid duplication
                if k == "frontmatter":
                    continue
                lines.append('  <div class="ms-meta-item">\n')
                lines.append(
                    '    <span class="ms-meta-key">%s</span>\n' % html_escape(str(k))
                )
                lines.append(
                    '    <span class="ms-meta-value">%s</span>\n' % html_escape(str(v))
                )
                lines.append("  </div>\n")
            lines.append("</div>\n")

        root = tree.getroot()
        self._dump_node(root, lines)
        return lines

    def _dump_node(self, elem, lines):
        tag = elem.tag

        if tag == "moonstone-tree":
            if elem.text and elem.text.strip():
                lines.append(html_escape(elem.text))
            for child in elem:
                self._dump_node(child, lines)
                if child.tail:
                    lines.append(html_escape(child.tail))

        elif tag == "h":
            level = elem.attrib.get("level", "1")
            inner = self._inline_html(elem)
            lines.append("<h%s>%s</h%s>\n" % (level, inner, level))

        elif tag == "p":
            cls = elem.attrib.get("class", "")
            inner = self._inline_html(elem)
            if cls:
                lines.append('<p class="%s">%s</p>\n' % (html_escape(cls), inner))
            else:
                lines.append("<p>%s</p>\n" % inner)

        elif tag == "blockquote":
            lines.append("<blockquote>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</blockquote>\n")

        elif tag == "ul":
            lines.append("<ul>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</ul>\n")

        elif tag == "ol":
            lines.append("<ol>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</ol>\n")

        elif tag == "li":
            bullet = elem.attrib.get("bullet", "*")
            # Render only inline content (skip nested ul/ol)
            inner = self._inline_html(elem, skip_tags=("ul", "ol"))

            if "box" in bullet:
                checked = (
                    " checked"
                    if "checked" in bullet and "unchecked" not in bullet
                    else ""
                )
                lines.append(
                    '<li class="task-list-item"><input type="checkbox"%s disabled> %s'
                    % (checked, inner)
                )
            else:
                lines.append("<li>%s" % inner)

            # Nested lists rendered separately
            for child in elem:
                if child.tag in ("ul", "ol"):
                    lines.append("\n")
                    self._dump_node(child, lines)

            lines.append("</li>\n")

        elif tag == "table":
            lines.append("<table>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</table>\n")

        elif tag == "thead":
            lines.append("<thead>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</thead>\n")

        elif tag == "tbody":
            lines.append("<tbody>\n")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</tbody>\n")

        elif tag == "tr":
            lines.append("<tr>")
            for child in elem:
                self._dump_node(child, lines)
            lines.append("</tr>\n")

        elif tag == "th":
            inner = self._inline_html(elem)
            lines.append("<th>%s</th>" % inner)

        elif tag == "td":
            inner = self._inline_html(elem)
            lines.append("<td>%s</td>" % inner)

        elif tag == "pre":
            text = html_escape(elem.text or "")
            lines.append("<pre>%s</pre>\n" % text)

        elif tag == "code":
            lang = elem.attrib.get("lang", "")
            text = html_escape(elem.text or "")
            if "\n" in (elem.text or ""):
                cls = ' class="language-%s"' % html_escape(lang) if lang else ""
                lines.append("<pre><code%s>%s</code></pre>\n" % (cls, text))
            else:
                lines.append("<code>%s</code>" % text)

        elif tag == "comment":
            # Hide comment visually but preserve data
            text = html_escape(elem.text or "")
            lines.append(
                '<div class="ms-comment" style="display:none;" data-raw="%s">%s</div>\n'
                % (text, text)
            )

        elif tag == "line":
            lines.append("<hr>\n")

        elif tag == "img":
            src = elem.attrib.get("src", "")
            alt = elem.attrib.get("alt", "")
            is_embed = elem.attrib.get("embed", "")
            if self.linker:
                src = self.linker.img(src)
            if is_embed:
                lines.append(
                    '<span class="embed" data-src="%s">![[%s]]</span>'
                    % (html_escape(src), html_escape(alt or src))
                )
            else:
                lines.append(
                    '<img src="%s" alt="%s">' % (html_escape(src), html_escape(alt))
                )

        elif tag == "link":
            href = elem.attrib.get("href", "")
            if self.linker:
                href = self.linker.link(href)
            inner = self._inline_html(elem)
            # Wiki links get a special class
            if (
                "://" not in href
                and not href.startswith("#")
                and not href.startswith("mailto:")
            ):
                lines.append(
                    '<a href="%s" class="wiki-link">%s</a>' % (html_escape(href), inner)
                )
            else:
                lines.append('<a href="%s">%s</a>' % (html_escape(href), inner))

        elif tag == "strong":
            lines.append("<strong>%s</strong>" % self._inline_html(elem))

        elif tag == "emphasis":
            lines.append("<em>%s</em>" % self._inline_html(elem))

        elif tag == "mark":
            lines.append("<mark>%s</mark>" % self._inline_html(elem))

        elif tag == "strike":
            lines.append("<del>%s</del>" % self._inline_html(elem))

        elif tag == "tag":
            name = elem.attrib.get("name", "")
            lines.append('<span class="tag">#%s</span>' % html_escape(name))

        elif tag == "sup":
            lines.append("<sup>%s</sup>" % self._inline_html(elem))

        elif tag == "sub":
            lines.append("<sub>%s</sub>" % self._inline_html(elem))

        elif tag == "span":
            cls = elem.attrib.get("class", "")
            inner = self._inline_html(elem)
            if cls == "block-ref":
                ref = elem.attrib.get("data-ref", "")
                lines.append(
                    '<span class="block-ref" data-ref="%s">%s</span>'
                    % (html_escape(ref), inner)
                )
            elif cls == "macro":
                lines.append('<span class="macro">%s</span>' % inner)
            elif cls:
                lines.append('<span class="%s">%s</span>' % (html_escape(cls), inner))
            else:
                lines.append(inner)

        else:
            inner = self._inline_html(elem)
            if inner:
                lines.append(inner)

    def _inline_html(self, elem, skip_tags=None):
        """Convert inline content to HTML string.

        @param skip_tags: tuple of tag names to skip (e.g. ('ul', 'ol'))
        """
        parts = []
        if elem.text:
            parts.append(html_escape(elem.text))
        for child in elem:
            if skip_tags and child.tag in skip_tags:
                if child.tail:
                    parts.append(html_escape(child.tail))
                continue
            child_parts = []
            self._dump_node(child, child_parts)
            parts.append("".join(child_parts))
            if child.tail:
                parts.append(html_escape(child.tail))
        return "".join(parts)
