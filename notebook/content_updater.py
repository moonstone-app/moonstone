# -*- coding: utf-8 -*-
"""Content updater for Moonstone.

Standalone content updater — handles updating links in pages
when a page is moved/renamed.

When page "Old:Path" is moved to "New:Path", all pages that link to
"Old:Path" need their link references updated.
"""

import logging

logger = logging.getLogger("moonstone.content_updater")


def update_links_on_move(notebook, oldpath, newpath):
    """Update all links pointing to oldpath after a page move.

    Uses LinksView to find backlinks (incoming links), then parses
    each linking page's ParseTree, updates href attributes, and
    saves the modified page.

    @param notebook: Notebook object
    @param oldpath: old Path
    @param newpath: new Path
    """
    from moonstone.notebook.index.links import LinksView, LINK_DIR_BACKWARD
    from moonstone.notebook.page import Path

    lv = LinksView.new_from_index(notebook.index)

    # Find all pages linking TO the old path
    backlinks = list(lv.list_links(oldpath, LINK_DIR_BACKWARD))

    if not backlinks:
        logger.debug("No backlinks to update for %s → %s", oldpath.name, newpath.name)
        return

    old_name = oldpath.name
    new_name = newpath.name

    logger.info(
        "Updating %d backlinks for move %s → %s", len(backlinks), old_name, new_name
    )

    for link_info in backlinks:
        source_name = link_info.source.name
        if source_name == old_name:
            continue  # skip self-links (the moved page itself)

        try:
            source_path = Path(source_name)
            page = notebook.get_page(source_path)
            tree = page.get_parsetree()
            if tree is None:
                continue

            updated = _update_tree_links(tree, old_name, new_name)
            if updated:
                page.set_parsetree(tree)
                notebook.store_page(page)
                logger.debug("Updated links in page %s", source_name)
        except Exception:
            logger.warning("Failed to update links in %s", source_name, exc_info=True)


def _parse_link_href(href):
    """Parse link href into (target, heading_anchor, block_id, display_text).

    Parsing order (same as extract_links):
    1. Split by | to get target_part and display
    2. Split target_part by # to get target and heading
    3. Check heading or target for ^ to get block_id
    """
    if not href:
        return None, None, None, None

    # Step 1: Split by | for display text
    if "|" in href:
        target_part, display = href.split("|", 1)
        display = display.strip()
    else:
        target_part = href
        display = None

    # Step 2: Split by # for heading anchor
    if "#" in target_part:
        target, heading = target_part.split("#", 1)
        target = target.strip().strip(":")
        heading = heading.strip()
    else:
        target = target_part.strip().strip(":")
        heading = None

    # Step 3: Check for block ref (^)
    block_id = None
    if heading and "^" in heading:
        parts = heading.split("^", 1)
        heading = parts[0].strip() if parts[0] else None
        block_id = parts[1].strip() if len(parts) > 1 else None
    elif target and "^" in target:
        parts = target.split("^", 1)
        target = parts[0].strip().strip(":")
        block_id = parts[1].strip() if len(parts) > 1 else None

    return target, heading, block_id, display


def _reconstruct_link_href(target, heading, block_id, display):
    """Reconstruct link href from components."""
    if not target:
        return None

    parts = [target]

    if heading:
        parts.append("#" + heading)

    if block_id:
        if heading:
            parts.append("^" + block_id)
        else:
            parts.append("^" + block_id)

    href = "".join(parts)

    if display:
        href += "|" + display

    return href


def _update_tree_links(tree, old_name, new_name):
    """Update link hrefs in a ParseTree, preserving anchors/blocks/display.

    @param tree: ParseTree object
    @param old_name: old page name (e.g. "Old:Path")
    @param new_name: new page name (e.g. "New:Path")
    @returns: True if any links were updated
    """
    updated = False

    for element in tree.getroot().iter():
        if element.tag == "link":
            href = element.get("href", "")
            if not href:
                continue

            # Parse href into components
            target, heading, block_id, display = _parse_link_href(href)
            if not target:
                continue

            # Compare only the target portion
            if target == old_name:
                # Reconstruct with new target, preserved components
                new_href = _reconstruct_link_href(new_name, heading, block_id, display)
                if new_href:
                    element.set("href", new_href)
                    updated = True
            elif target.startswith(old_name + ":"):
                # Child page of moved page
                suffix = target[len(old_name):]
                new_target = new_name + suffix
                new_href = _reconstruct_link_href(new_target, heading, block_id, display)
                if new_href:
                    element.set("href", new_href)
                    updated = True

    return updated


def update_links_in_moved_page(notebook, page, oldpath, newpath):
    """Update links inside a moved page.

    When a page moves from one namespace to another, floating links
    that reference child pages need to be updated.

    @param notebook: Notebook object
    @param page: the moved Page object (already at new location)
    @param oldpath: old Path
    @param newpath: new Path
    """
    old_ns = oldpath.namespace
    new_ns = newpath.namespace

    if old_ns == new_ns:
        return  # Same namespace — relative links still valid

    try:
        tree = page.get_parsetree()
        if tree is None:
            return

        updated = False
        for element in tree.getroot().iter():
            if element.tag == "link":
                href = element.get("href", "")
                if not href:
                    continue

                # Parse href into components FIRST
                target, heading, block_id, display = _parse_link_href(href)
                if not target:
                    continue

                # Skip self-links using PARSED target
                if target == oldpath.name:
                    continue

                # Only update explicit child references (Old:Parent:Child → New:Parent:Child)
                if target.startswith(oldpath.name + ":"):
                    child_suffix = target[len(oldpath.name):]
                    new_target = newpath.name + child_suffix
                    new_href = _reconstruct_link_href(new_target, heading, block_id, display)
                    if new_href:
                        element.set("href", new_href)
                        updated = True

        if updated:
            page.set_parsetree(tree)
            notebook.store_page(page)
    except Exception:
        logger.warning(
            "Failed to update links in moved page %s", page.name, exc_info=True
        )
