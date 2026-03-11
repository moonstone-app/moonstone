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


def _update_tree_links(tree, old_name, new_name):
    """Update link hrefs in a ParseTree.

    @param tree: ParseTree object
    @param old_name: old page name (e.g. "Old:Path")
    @param new_name: new page name (e.g. "New:Path")
    @returns: True if any links were updated
    """
    updated = False

    for element in tree.root.iter():
        if element.tag == "link":
            href = element.get("href", "")
            if not href:
                continue

            # Normalize for comparison
            normalized = href.strip().strip(":")

            if normalized == old_name:
                element.set("href", new_name)
                updated = True
            elif normalized.startswith(old_name + ":"):
                # Child page of moved page
                suffix = normalized[len(old_name) :]
                element.set("href", new_name + suffix)
                updated = True

    return updated


def update_links_in_moved_page(notebook, page, oldpath, newpath):
    """Update relative links inside the moved page itself.

    When a page moves from one namespace to another, its relative
    links may need updating.

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
        for element in tree.root.iter():
            if element.tag == "link":
                href = element.get("href", "")
                if not href:
                    continue

                # Only update relative links (starting with +)
                if href.startswith("+"):
                    continue  # sub-page relative — stays
                if href.startswith(":"):
                    continue  # absolute — stays

                # Floating link — check if it was relative to old namespace
                # This is a heuristic; for now we leave floating links as-is
                # since they resolve by searching upward through namespaces

        if updated:
            page.set_parsetree(tree)
            notebook.store_page(page)
    except Exception:
        logger.warning(
            "Failed to update links in moved page %s", page.name, exc_info=True
        )
