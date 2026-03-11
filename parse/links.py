# -*- coding: utf-8 -*-
"""Link type detection for Moonstone.

Standalone link parser — determines the type of a link string.
"""

import re

_url_re = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")
_mailto_re = re.compile(r"^mailto:", re.I)
_email_re = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_file_re = re.compile(r"^(file://|/|~|\.\.?/)")
_interwiki_re = re.compile(r"^\w+\?\w")


def link_type(href):
    """Determine the type of a link.

    @param href: link target string
    @returns: 'page', 'file', 'mailto', 'url', or 'interwiki'
    """
    if not href or not href.strip():
        return "page"

    href = href.strip()

    # URL with scheme
    if _url_re.match(href):
        if href.lower().startswith("file://"):
            return "file"
        if href.lower().startswith("mailto:"):
            return "mailto"
        return "url"

    # Email
    if _email_re.match(href):
        return "mailto"

    # Mailto prefix
    if _mailto_re.match(href):
        return "mailto"

    # File path
    if _file_re.match(href):
        return "file"

    # Interwiki (word?word pattern)
    if _interwiki_re.match(href):
        return "interwiki"

    # Default — page link
    return "page"
