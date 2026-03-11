# -*- coding: utf-8 -*-
"""Vault Profiles for Moonstone.

Profiles define how Moonstone reads/writes different PKM vault formats.
Each profile specifies file extension, tag/link syntax, metadata format,
and attachment strategy — enabling full read-write compatibility.

Available profiles:
- moonstone: Markdown-based PKM with YAML frontmatter, #tags, [[wiki:links]]
- zim: Zim Wiki compatibility (.txt, Content-Type headers, @tags)
- obsidian: Obsidian vault (.md, YAML frontmatter, #tags, [[wiki/links]])
- logseq: Logseq graph (.md, properties, #tags, [[wiki/links]])

Usage:
    from moonstone.profiles import auto_detect, get_profile
    profile = auto_detect('/path/to/vault')  # auto-detect vault type
    profile = get_profile('obsidian')        # explicit profile
"""

import os
import logging

logger = logging.getLogger("moonstone.profiles")


def get_profile(name):
    """Return a profile instance by name.

    @param name: 'moonstone', 'zim', 'obsidian', 'logseq'
    @returns: BaseProfile subclass instance
    """
    if name == "moonstone":
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        return MoonstoneProfile()
    elif name == "zim":
        from moonstone.profiles.zim import ZimProfile

        return ZimProfile()
    elif name == "obsidian":
        from moonstone.profiles.obsidian import ObsidianProfile

        return ObsidianProfile()
    elif name == "logseq":
        from moonstone.profiles.logseq import LogseqProfile

        return LogseqProfile()
    else:
        raise ValueError(
            "Unknown profile: %s. Available: moonstone, zim, obsidian, logseq" % name
        )


def auto_detect(folder_path):
    """Auto-detect vault type from folder contents.

    Detection order:
    1. .obsidian/ directory → Obsidian
    2. logseq/ directory → Logseq
    3. notebook.moon → Moonstone
    4. notebook.zim → Zim (legacy compatibility)
    5. Any .md files → Obsidian (most common)
    6. Fallback → Moonstone

    @param folder_path: path to vault folder
    @returns: BaseProfile subclass instance
    """
    folder = os.path.realpath(folder_path)

    # Obsidian vault
    if os.path.isdir(os.path.join(folder, ".obsidian")):
        logger.info("Auto-detected Obsidian vault: %s", folder)
        from moonstone.profiles.obsidian import ObsidianProfile

        return ObsidianProfile()

    # Logseq graph — check multiple markers with decreasing confidence:
    # 1. logseq/config.edn — definitive Logseq marker
    # 2. .logseq/ hidden directory (some Logseq versions)
    # 3. logseq/ directory WITH config.edn or pages.edn inside
    # 4. pages/ + journals/ + no .obsidian + .md files in pages/ — heuristic
    #
    # We do NOT use bare logseq/ or bare pages/+journals/ alone,
    # because Obsidian vaults can have folders named "pages"/"journals"/"logseq".
    _has_logseq_config = os.path.isfile(os.path.join(folder, "logseq", "config.edn"))
    _has_dot_logseq = os.path.isdir(os.path.join(folder, ".logseq"))
    _has_logseq_dir_with_edn = os.path.isdir(os.path.join(folder, "logseq")) and (
        os.path.isfile(os.path.join(folder, "logseq", "config.edn"))
        or os.path.isfile(os.path.join(folder, "logseq", "pages.edn"))
    )
    _has_pages_journals = os.path.isdir(
        os.path.join(folder, "pages")
    ) and os.path.isdir(os.path.join(folder, "journals"))
    # Definitive: logseq/config.edn or .logseq/ exist
    _logseq_definitive = (
        _has_logseq_config or _has_dot_logseq or _has_logseq_dir_with_edn
    )
    # Heuristic: pages/ + journals/ with .md files inside pages/
    _logseq_heuristic = False
    if _has_pages_journals and not _logseq_definitive:
        pages_dir = os.path.join(folder, "pages")
        try:
            _logseq_heuristic = any(
                f.endswith(".md")
                for f in os.listdir(pages_dir)
                if os.path.isfile(os.path.join(pages_dir, f))
            )
        except OSError:
            pass

    if _logseq_definitive or _logseq_heuristic:
        logger.info(
            "Auto-detected Logseq graph: %s (config.edn=%s .logseq/=%s pages+journals=%s)",
            folder,
            _has_logseq_config,
            _has_dot_logseq,
            _has_pages_journals,
        )
        from moonstone.profiles.logseq import LogseqProfile

        return LogseqProfile()

    # Moonstone notebook (new format)
    if os.path.isfile(os.path.join(folder, "notebook.moon")):
        logger.info("Auto-detected Moonstone notebook: %s", folder)
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        return MoonstoneProfile()

    # Zim Wiki notebook (legacy)
    if os.path.isfile(os.path.join(folder, "notebook.zim")):
        logger.info("Auto-detected Zim Wiki notebook: %s", folder)
        from moonstone.profiles.zim import ZimProfile

        return ZimProfile()

    # Heuristic: if there are .md files but no .txt with Content-Type headers → Obsidian
    has_md = False
    has_wiki_txt = False
    try:
        for entry in os.scandir(folder):
            if entry.is_file():
                if entry.name.endswith(".md"):
                    has_md = True
                elif entry.name.endswith(".txt"):
                    try:
                        with open(entry.path, "r", encoding="utf-8") as f:
                            first_line = f.readline()
                        if "Content-Type:" in first_line:
                            has_wiki_txt = True
                    except (OSError, IOError):
                        pass
    except OSError:
        pass

    if has_md and not has_wiki_txt:
        logger.info(
            "Heuristic: detected Markdown vault (Obsidian-compatible): %s", folder
        )
        from moonstone.profiles.obsidian import ObsidianProfile

        return ObsidianProfile()

    # Default: Moonstone (Markdown)
    logger.info("Default profile: Moonstone for %s", folder)
    from moonstone.profiles.moonstone_profile import MoonstoneProfile

    return MoonstoneProfile()


def list_profiles():
    """Return list of available profile names."""
    return ["moonstone", "zim", "obsidian", "logseq"]


def get_all_config_markers():
    """Collect config_marker from all registered profiles.

    Returns a tuple of filenames that identify notebook/vault roots
    (e.g., 'notebook.moon', 'notebook.zim').
    Only includes file-based markers (not directory markers like .obsidian/).

    @returns: tuple of config filename strings
    """
    markers = []
    for name in list_profiles():
        p = get_profile(name)
        # Only file-based markers (contain a dot, e.g. notebook.moon)
        # Skip directory markers (.obsidian, logseq)
        if (
            p.config_marker
            and "." in p.config_marker
            and not p.config_marker.startswith(".")
        ):
            markers.append(p.config_marker)
    return tuple(markers)
