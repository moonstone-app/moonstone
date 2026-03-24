# -*- coding: utf-8 -*-

from unittest.mock import Mock

import pytest

from notebook.notebook import Notebook
from profiles.obsidian import ObsidianProfile
from webbridge.api import NotebookAPI


def _make_api(notebook):
    app = Mock()
    app.applets_dir = notebook.folder.path
    app._event_manager = Mock()
    app._history = None
    return NotebookAPI(notebook, app)


@pytest.fixture
def obsidian_api(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir()
    (obsidian_dir / "app.json").write_text(
        '{"attachmentFolderPath": ".", "vaultSize": {"amount": 1}}',
        encoding="utf-8",
    )

    pix = vault / "pix"
    pix.mkdir()
    (pix / "lion.png").write_bytes(b"PNGDATA")
    (pix / "doc.pdf").write_bytes(b"%PDF-1.7")
    (pix / "song.mp3").write_bytes(b"ID3")
    (pix / "with space.png").write_bytes(b"SPACE")

    (vault / "Note.md").write_text(
        "\n".join(
            [
                "![lion](pix/lion.png)",
                "![space](<pix/with space.png>)",
                "![root](/pix/lion.png)",
                "![[lion.png]]",
                "![[pix/lion.png|300x200]]",
                "![[pix/doc.pdf#page=3]]",
                "![[pix/song.mp3]]",
            ]
        ),
        encoding="utf-8",
    )

    notebook = Notebook(vault, profile=ObsidianProfile())
    # Ensure index contains test page
    notebook.index.check_and_update()
    return _make_api(notebook)


@pytest.mark.api
def test_obsidian_list_attachments_supports_nested_paths(obsidian_api):
    status, _, body = obsidian_api.list_attachments("Note")

    assert status == 200
    names = {a["name"] for a in body["attachments"]}
    assert "pix/lion.png" in names
    assert "pix/with space.png" in names
    assert "pix/doc.pdf" in names
    assert "pix/song.mp3" in names


@pytest.mark.api
def test_obsidian_get_attachment_accepts_encoded_nested_filename(obsidian_api):
    status, headers, content = obsidian_api.get_attachment("Note", "pix%2Flion.png")

    assert status == 200
    assert headers.get("Content-Type") == "image/png"
    assert content == b"PNGDATA"


@pytest.mark.api
def test_obsidian_get_attachment_resolves_unique_basename(obsidian_api):
    status, headers, content = obsidian_api.get_attachment("Note", "lion.png")

    assert status == 200
    assert headers.get("Content-Type") == "image/png"
    assert content == b"PNGDATA"


@pytest.mark.api
def test_obsidian_get_attachment_ignores_embed_fragment(obsidian_api):
    status, headers, content = obsidian_api.get_attachment(
        "Note", "pix%2Fdoc.pdf%23page%3D3"
    )

    assert status == 200
    assert headers.get("Content-Type") == "application/pdf"
    assert content == b"%PDF-1.7"


@pytest.mark.api
def test_obsidian_html_export_renders_embeds_and_encoded_attachment_urls(obsidian_api):
    status, _, body = obsidian_api.get_page("Note", format="html")

    assert status == 200
    html = body["content"]

    # Markdown image URLs are routed through encoded attachment endpoints
    assert "/api/attachment/Note?filename=pix%2Flion.png" in html
    assert "/api/attachment/Note?filename=pix%2Fwith%20space.png" in html

    # Obsidian embeds render as binary-capable HTML elements
    assert "<img " in html
    assert "width=\"300\"" in html
    assert "height=\"200\"" in html
    assert "<iframe " in html
    assert "embed-pdf" in html
    assert "/api/attachment/Note?filename=pix%2Fdoc.pdf#page=3" in html
    assert "<audio controls " in html
