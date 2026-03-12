# -*- coding: UTF-8 -*-
"""OpenAPI 3.0.3 specification for WebBridge API."""


def _schemas():
    """Reusable component schemas."""
    return {
        "Error": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "details": {"type": "string", "description": "Additional details"},
            },
            "required": ["error"],
        },
        "PageInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Projects:WebBridge"},
                "basename": {"type": "string", "example": "WebBridge"},
                "haschildren": {"type": "boolean"},
                "hascontent": {"type": "boolean"},
            },
        },
        "PageContent": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "basename": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "format": {"type": "string", "enum": ["wiki", "html", "plain"]},
                "exists": {"type": "boolean"},
                "haschildren": {"type": "boolean"},
                "mtime": {"type": "number", "nullable": True},
                "ctime": {"type": "number", "nullable": True},
            },
        },
        "TagInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "todo"},
                "count": {"type": "integer", "example": 12},
            },
        },
        "LinkInfo": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
            },
        },
        "AttachmentInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "screenshot.png"},
                "size": {"type": "integer"},
                "mtime": {"type": "number"},
            },
        },
        "NotebookInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "interwiki": {"type": "string"},
                "home": {"type": "string"},
                "icon": {"type": "string"},
                "readonly": {"type": "boolean"},
                "folder": {"type": "string", "nullable": True},
            },
        },
        "OkResponse": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean", "example": True},
            },
        },
        "PatchOperation": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["replace", "insert_after", "delete"]},
                "search": {"type": "string", "description": "Text to find in the page"},
                "replace": {
                    "type": "string",
                    "description": "Replacement text (for replace op)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to insert (for insert_after op)",
                },
            },
            "required": ["op", "search"],
        },
        "BatchOperation": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "PUT", "POST", "DELETE"]},
                "path": {"type": "string", "example": "/api/page/Home"},
                "body": {"type": "object"},
            },
            "required": ["method", "path"],
        },
        "ParseTreeNode": {
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "attrib": {"type": "object"},
                "text": {"type": "string"},
                "tail": {"type": "string"},
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ParseTreeNode"},
                },
            },
        },
        "Heading": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 1, "maximum": 6, "example": 2},
                "text": {"type": "string", "example": "Introduction"},
                "index": {"type": "integer", "description": "Sequential heading index"},
            },
        },
        "PageAnalytics": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "exists": {"type": "boolean"},
                "words": {"type": "integer", "example": 423},
                "characters": {"type": "integer", "example": 2841},
                "lines": {"type": "integer", "example": 56},
                "reading_time_minutes": {"type": "number", "example": 2.1},
                "headings": {"type": "integer"},
                "links_out": {"type": "integer"},
                "links_in": {"type": "integer"},
                "images": {"type": "integer"},
                "tags": {"type": "integer"},
                "checkboxes": {"type": "integer"},
                "checkboxes_checked": {"type": "integer"},
                "mtime": {"type": "number", "nullable": True},
                "ctime": {"type": "number", "nullable": True},
                "age_days": {"type": "number", "nullable": True},
                "days_since_edit": {"type": "number", "nullable": True},
            },
        },
        "GraphNode": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "example": "Projects:WebBridge"},
                "label": {"type": "string", "example": "WebBridge"},
                "haschildren": {"type": "boolean"},
                "degree": {"type": "integer", "description": "Number of connections"},
                "external": {
                    "type": "boolean",
                    "description": "True if node is outside the queried namespace",
                },
            },
        },
        "GraphEdge": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
            },
        },
        "ExportResult": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Projects:WebBridge"},
                "format": {
                    "type": "string",
                    "enum": ["wiki", "html", "plain", "markdown", "latex", "rst"],
                },
                "content": {"type": "string", "description": "Exported page content"},
                "content_type": {"type": "string", "example": "text/html"},
                "length": {
                    "type": "integer",
                    "description": "Content length in characters",
                },
            },
        },
        "TemplateInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Default"},
                "file": {"type": "string", "example": "Default.html"},
                "format": {"type": "string", "example": "html"},
            },
        },
        "SitemapPage": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Projects:WebBridge"},
                "basename": {"type": "string", "example": "WebBridge"},
                "path": {"type": "string", "example": "Projects/WebBridge"},
            },
        },
        "TagAction": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "page": {"type": "string"},
                "tag": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["added", "removed", "already_exists"],
                },
            },
        },
        "ServiceInfo": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "telegram-notes"},
                "label": {"type": "string", "example": "Telegram Notes"},
                "description": {"type": "string"},
                "icon": {"type": "string", "example": "🤖"},
                "version": {"type": "string", "example": "1.0.0"},
                "author": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["stopped", "starting", "running", "stopping", "error"],
                },
                "pid": {"type": "integer", "nullable": True},
                "uptime": {"type": "integer", "description": "Uptime in seconds"},
                "auto_start": {"type": "boolean"},
                "has_config": {
                    "type": "boolean",
                    "description": "True if service has configurable preferences",
                },
                "error": {"type": "string"},
                "restart_count": {"type": "integer"},
                "source": {"type": "string", "enum": ["local", "git"]},
                "repository": {"type": "string", "nullable": True},
            },
        },
        "ServiceConfigPreference": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "example": "bot_token"},
                "type": {
                    "type": "string",
                    "enum": ["string", "boolean"],
                    "default": "string",
                },
                "label": {"type": "string", "example": "Bot Token"},
                "description": {"type": "string"},
                "default": {"description": "Default value"},
                "required": {"type": "boolean", "default": False},
            },
            "required": ["key"],
        },
    }


# Placeholder — filled by _build_paths_*() helpers below
def _paths():
    """All API path definitions."""
    p = {}
    p.update(_paths_notebook())
    p.update(_paths_pages())
    p.update(_paths_page_crud())
    p.update(_paths_page_sub())
    p.update(_paths_search())
    p.update(_paths_tags())
    p.update(_paths_links())
    p.update(_paths_attachments())
    p.update(_paths_store())
    p.update(_paths_misc())
    p.update(_paths_analysis())
    p.update(_paths_export_templates())
    p.update(_paths_applet_management())
    p.update(_paths_services())
    p.update(_paths_internal())
    return p


def _paths_notebook():
    return {
        "/api/notebook": {
            "get": {
                "tags": ["Notebook"],
                "summary": "Get notebook metadata",
                "operationId": "getNotebookInfo",
                "description": "Returns notebook name, home page, read-only status and folder path.",
                "responses": {
                    "200": {
                        "description": "Notebook metadata",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/NotebookInfo"}
                            }
                        },
                    },
                },
            },
        },
        "/api/current": {
            "get": {
                "tags": ["Notebook"],
                "summary": "Get currently open page",
                "operationId": "getCurrentPage",
                "description": "Returns the currently focused page. In headless mode, updated via POST /api/navigate.",
                "responses": {
                    "200": {
                        "description": "Current page",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "page": {
                                            "type": "string",
                                            "nullable": True,
                                            "example": "Home",
                                        }
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/stats": {
            "get": {
                "tags": ["Notebook"],
                "summary": "Get notebook statistics",
                "operationId": "getStats",
                "description": "Returns total page count and tag count.",
                "responses": {
                    "200": {
                        "description": "Statistics",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {"type": "integer", "example": 142},
                                        "tags": {"type": "integer", "example": 23},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_pages():
    _ns_param = {
        "name": "namespace",
        "in": "query",
        "schema": {"type": "string"},
        "description": 'Namespace to list (e.g. "Projects"). Root if omitted.',
        "example": "Projects",
    }
    return {
        "/api/pages": {
            "get": {
                "tags": ["Pages"],
                "summary": "List pages in a namespace",
                "operationId": "listPages",
                "description": "Returns pages in the given namespace with optional pagination.",
                "parameters": [
                    _ns_param,
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "maximum": 1000},
                        "description": "Max pages to return. All if omitted.",
                    },
                    {
                        "name": "offset",
                        "in": "query",
                        "schema": {"type": "integer", "default": 0},
                        "description": "Number of pages to skip.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Page list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "namespace": {"type": "string"},
                                        "total": {"type": "integer"},
                                        "limit": {"type": "integer", "nullable": True},
                                        "offset": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/pages/match": {
            "get": {
                "tags": ["Pages"],
                "summary": "Fuzzy-match page names",
                "operationId": "matchPages",
                "description": "Returns pages whose names match the query string (autocomplete).",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Search query",
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 10, "maximum": 50},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Matched pages",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/pages/walk": {
            "get": {
                "tags": ["Pages"],
                "summary": "Recursively list all pages",
                "operationId": "walkPages",
                "description": "Walks the entire page tree recursively from the given namespace.",
                "parameters": [_ns_param],
                "responses": {
                    "200": {
                        "description": "All pages",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "namespace": {"type": "string"},
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/pages/count": {
            "get": {
                "tags": ["Pages"],
                "summary": "Count pages",
                "operationId": "countPages",
                "description": "Returns the number of pages without loading them.",
                "parameters": [_ns_param],
                "responses": {
                    "200": {
                        "description": "Page count",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "count": {"type": "integer"},
                                        "namespace": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/pagetree": {
            "get": {
                "tags": ["Pages"],
                "summary": "Get page hierarchy tree",
                "operationId": "getPageTree",
                "description": "Returns a nested tree structure of pages up to the given depth.",
                "parameters": [
                    _ns_param,
                    {
                        "name": "depth",
                        "in": "query",
                        "schema": {"type": "integer", "default": 2, "maximum": 10},
                        "description": "Max nesting depth.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Page tree",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "tree": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                        "namespace": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_page_crud():
    _page_param = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "description": "Page path using `/` as separator (e.g. `Projects/WebBridge`).",
        "example": "Projects/WebBridge",
    }
    _err_responses = {
        "403": {
            "description": "Notebook or page is read-only",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
        "404": {
            "description": "Page not found",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
    }
    return {
        "/api/page/{page_path}": {
            "get": {
                "tags": ["Page CRUD"],
                "summary": "Get page content",
                "operationId": "getPage",
                "description": "Returns the content of a page in the requested format.",
                "parameters": [
                    _page_param,
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["wiki", "html", "plain"],
                            "default": "wiki",
                        },
                        "description": "Output format.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Page created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": _err_responses["403"],
                    "409": {
                        "description": "Page already exists",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "patch": {
                "tags": ["Page CRUD"],
                "summary": "Partial page update",
                "operationId": "patchPage",
                "description": "Apply search/replace, insert_after or delete operations to a page without rewriting the whole content.",
                "parameters": [_page_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["operations"],
                                "properties": {
                                    "operations": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/PatchOperation"
                                        },
                                    },
                                    "expected_mtime": {
                                        "type": "number",
                                        "nullable": True,
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Patch applied",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "page": {"type": "string"},
                                        "mtime": {"type": "number", "nullable": True},
                                        "operations": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "403": _err_responses["403"],
                    "404": _err_responses["404"],
                    "409": {
                        "description": "Conflict",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "delete": {
                "tags": ["Page CRUD"],
                "summary": "Update page content",
                "operationId": "savePage",
                "description": "Replaces the entire page content. Supports optimistic concurrency via expected_mtime.",
                "parameters": [_page_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["content"],
                                "properties": {
                                    "content": {
                                        "type": "string",
                                        "description": "New page content",
                                    },
                                    "format": {
                                        "type": "string",
                                        "enum": ["wiki", "html", "plain"],
                                        "default": "wiki",
                                    },
                                    "expected_mtime": {
                                        "type": "number",
                                        "nullable": True,
                                        "description": "If set, returns 409 when page was modified since this mtime.",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Page saved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "page": {"type": "string"},
                                        "mtime": {"type": "number", "nullable": True},
                                    },
                                }
                            }
                        },
                    },
                    "403": _err_responses["403"],
                    "409": {
                        "description": "Conflict — page modified since expected_mtime",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "post": {
                "tags": ["Page CRUD"],
                "summary": "Create a new page",
                "operationId": "createPage",
                "description": "Creates a new page. Returns 409 if the page already has content.",
                "parameters": [_page_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string", "default": ""},
                                    "format": {
                                        "type": "string",
                                        "enum": ["wiki", "html", "plain"],
                                        "default": "wiki",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Page created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": _err_responses["403"],
                    "409": {
                        "description": "Page already exists",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "patch": {
                "tags": ["Page CRUD"],
                "summary": "Partial page update",
                "operationId": "patchPage",
                "description": "Apply search/replace, insert_after or delete operations to a page without rewriting the whole content.",
                "parameters": [_page_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["operations"],
                                "properties": {
                                    "operations": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/PatchOperation"
                                        },
                                    },
                                    "expected_mtime": {
                                        "type": "number",
                                        "nullable": True,
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Patch applied",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "page": {"type": "string"},
                                        "mtime": {"type": "number", "nullable": True},
                                        "operations": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "403": _err_responses["403"],
                    "404": _err_responses["404"],
                    "409": {
                        "description": "Conflict",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "delete": {
                "tags": ["Page CRUD"],
                "summary": "Delete a page",
                "operationId": "deletePage",
                "description": "Permanently deletes a page and its content. Use trash endpoint for safe deletion.",
                "parameters": [_page_param],
                "responses": {
                    "200": {
                        "description": "Page deleted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": _err_responses["403"],
                },
            },
        },
    }


def _paths_page_sub():
    _pp = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "Projects/WebBridge",
    }
    _403 = {
        "description": "Read-only",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        },
    }
    return {
        "/api/page/{page_path}/append": {
            "post": {
                "tags": ["Page Operations"],
                "summary": "Append content to a page",
                "operationId": "appendToPage",
                "description": "Appends content to the end of an existing page, or creates a new one.",
                "parameters": [_pp],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["content"],
                                "properties": {
                                    "content": {"type": "string"},
                                    "format": {"type": "string", "default": "wiki"},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Content appended",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": _403,
                },
            },
        },
        "/api/page/{page_path}/move": {
            "post": {
                "tags": ["Page Operations"],
                "summary": "Move / rename a page",
                "operationId": "movePage",
                "description": "Moves a page to a new path. Optionally updates all links pointing to it.",
                "parameters": [_pp],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["newpath"],
                                "properties": {
                                    "newpath": {
                                        "type": "string",
                                        "description": "New page path (colon-separated)",
                                        "example": "Archive:OldPage",
                                    },
                                    "update_links": {
                                        "type": "boolean",
                                        "default": True,
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Page moved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "old": {"type": "string"},
                                        "new": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Move failed",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "403": _403,
                },
            },
        },
        "/api/page/{page_path}/trash": {
            "post": {
                "tags": ["Page Operations"],
                "summary": "Move page to trash",
                "operationId": "trashPage",
                "description": "Safely deletes a page by moving it to the system trash. Falls back to permanent delete if trash is unavailable.",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Page trashed",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": _403,
                },
            },
        },
        "/api/page/{page_path}/tags": {
            "get": {
                "tags": ["Page Operations"],
                "summary": "Get tags for a page",
                "operationId": "getPageTags",
                "description": "Returns the list of tags assigned to the given page.",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Page tags",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "page": {"type": "string"},
                                        "tags": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"}
                                                },
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "post": {
                "tags": ["Tag Management"],
                "summary": "Add a tag to a page",
                "operationId": "addTagToPage",
                "description": (
                    "Adds a @tag to the page content by appending it at the end. "
                    'If the tag already exists (case-insensitive), returns success with action "already_exists". '
                    "The @ prefix is optional in the request body."
                ),
                "parameters": [_pp],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["tag"],
                                "properties": {
                                    "tag": {
                                        "type": "string",
                                        "example": "todo",
                                        "description": "Tag name (with or without @ prefix)",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Tag action result",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TagAction"}
                            }
                        },
                    },
                    "403": {
                        "description": "Page is read-only",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/page/{page_path}/tags/{tag}": {
            "delete": {
                "tags": ["Tag Management"],
                "summary": "Remove a tag from a page",
                "operationId": "removeTagFromPage",
                "description": (
                    "Removes a @tag from the page content. Handles standalone tag lines and inline tags. "
                    "Case-insensitive matching. Pass the tag name as a path parameter."
                ),
                "parameters": [
                    _pp,
                    {
                        "name": "tag",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Tag name to remove (with or without @ prefix)",
                        "example": "todo",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Tag removed",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TagAction"}
                            }
                        },
                    },
                    "403": {
                        "description": "Page is read-only",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "404": {
                        "description": "Tag not found on page",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/page/{page_path}/siblings": {
            "get": {
                "tags": ["Page Operations"],
                "summary": "Get previous and next pages",
                "operationId": "getPageSiblings",
                "description": "Returns the previous and next sibling pages in the index order.",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Siblings",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "page": {"type": "string"},
                                        "previous": {
                                            "type": "string",
                                            "nullable": True,
                                        },
                                        "next": {"type": "string", "nullable": True},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/page/{page_path}/parsetree": {
            "get": {
                "tags": ["Page Operations"],
                "summary": "Get structured parse tree",
                "operationId": "getPageParseTree",
                "description": "Returns the page content as a JSON parse tree — useful for programmatic analysis of page structure (headings, lists, links, etc.).",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Parse tree",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "tree": {
                                            "$ref": "#/components/schemas/ParseTreeNode"
                                        },
                                        "exists": {"type": "boolean"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_search():
    return {
        "/api/search": {
            "get": {
                "tags": ["Search"],
                "summary": "Search pages",
                "operationId": "searchPages",
                "description": "Full-text search across all pages using search query syntax. Optionally returns text snippets around matches.",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Search query (search syntax)",
                        "example": "Content: python AND Name: projects",
                    },
                    {
                        "name": "snippets",
                        "in": "query",
                        "schema": {"type": "boolean", "default": False},
                        "description": "Include text snippets around matches.",
                    },
                    {
                        "name": "snippet_length",
                        "in": "query",
                        "schema": {"type": "integer", "default": 120},
                        "description": "Max snippet length in characters.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Search results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "basename": {"type": "string"},
                                                    "title": {"type": "string"},
                                                    "snippet": {
                                                        "type": "string",
                                                        "description": "Present only when snippets=true",
                                                    },
                                                },
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Missing query",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_tags():
    return {
        "/api/tags": {
            "get": {
                "tags": ["Tags"],
                "summary": "List all tags",
                "operationId": "listTags",
                "description": "Returns all tags in the notebook ordered by page count (descending).",
                "responses": {
                    "200": {
                        "description": "Tag list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "tags": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/TagInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/tags/{tag_name}/pages": {
            "get": {
                "tags": ["Tags"],
                "summary": "List pages with a tag",
                "operationId": "getTagPages",
                "description": "Returns all pages that have the given tag.",
                "parameters": [
                    {
                        "name": "tag_name",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "todo",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Pages with tag",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "tag": {"type": "string"},
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Tag not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/tags/intersecting": {
            "get": {
                "tags": ["Tags"],
                "summary": "Find co-occurring tags",
                "operationId": "getIntersectingTags",
                "description": "Returns tags that co-occur with the given tags on the same pages.",
                "parameters": [
                    {
                        "name": "tags",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Comma-separated tag names",
                        "example": "todo,urgent",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Intersecting tags",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "query_tags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "intersecting": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/TagInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Tag not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_links():
    _pp = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "Home",
    }
    _dir = {
        "name": "direction",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["forward", "backward", "both"],
            "default": "forward",
        },
        "description": "Link direction.",
    }
    _links_resp = {
        "type": "object",
        "properties": {
            "page": {"type": "string"},
            "direction": {"type": "string"},
            "links": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/LinkInfo"},
            },
            "count": {"type": "integer"},
        },
    }
    return {
        "/api/links/{page_path}": {
            "get": {
                "tags": ["Links"],
                "summary": "Get links for a page",
                "operationId": "getLinks",
                "description": "Returns forward links (outgoing), backward links (backlinks), or both for the given page.",
                "parameters": [_pp, _dir],
                "responses": {
                    "200": {
                        "description": "Links",
                        "content": {"application/json": {"schema": _links_resp}},
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/links/{page_path}/section": {
            "get": {
                "tags": ["Links"],
                "summary": "Get links for a whole section",
                "operationId": "getLinksSection",
                "description": "Returns links for the page and all its children (the whole namespace section).",
                "parameters": [_pp, _dir],
                "responses": {
                    "200": {
                        "description": "Section links",
                        "content": {"application/json": {"schema": _links_resp}},
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/links/{page_path}/count": {
            "get": {
                "tags": ["Links"],
                "summary": "Count links for a page",
                "operationId": "countLinks",
                "description": "Returns the number of links without loading them.",
                "parameters": [_pp, _dir],
                "responses": {
                    "200": {
                        "description": "Link count",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "page": {"type": "string"},
                                        "direction": {"type": "string"},
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/links/floating": {
            "get": {
                "tags": ["Links"],
                "summary": "List floating (ambiguous) links",
                "operationId": "listFloatingLinks",
                "description": "Returns all floating-style links in the notebook, aggregated by iterating every unique page basename. May be slow on very large notebooks.",
                "responses": {
                    "200": {
                        "description": "Floating links",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "links": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/LinkInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_attachments():
    _pp = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "Projects/WebBridge",
    }
    _fn = {
        "name": "filename",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "screenshot.png",
    }
    return {
        "/api/attachments/{page_path}": {
            "get": {
                "tags": ["Attachments"],
                "summary": "List attachments for a page",
                "operationId": "listAttachments",
                "description": "Returns file names, sizes and modification times of all attachments.",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Attachment list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "page": {"type": "string"},
                                        "attachments": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/AttachmentInfo"
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/attachment/{page_path}/{filename}": {
            "get": {
                "tags": ["Attachments"],
                "summary": "Download an attachment",
                "operationId": "getAttachment",
                "description": "Returns the raw file content with the appropriate MIME type.",
                "parameters": [_pp, _fn],
                "responses": {
                    "200": {
                        "description": "File content",
                        "content": {
                            "application/octet-stream": {
                                "schema": {"type": "string", "format": "binary"}
                            }
                        },
                    },
                    "403": {
                        "description": "Access denied",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "404": {
                        "description": "Not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "post": {
                "tags": ["Attachments"],
                "summary": "Upload an attachment",
                "operationId": "uploadAttachment",
                "description": "Uploads a file as an attachment to the specified page.",
                "parameters": [_pp, _fn],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/octet-stream": {
                            "schema": {"type": "string", "format": "binary"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Uploaded",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": {
                        "description": "Read-only",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "delete": {
                "tags": ["Attachments"],
                "summary": "Delete an attachment",
                "operationId": "deleteAttachment",
                "description": "Permanently removes the attachment file.",
                "parameters": [_pp, _fn],
                "responses": {
                    "200": {
                        "description": "Deleted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "403": {
                        "description": "Access denied",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "404": {
                        "description": "Not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_store():
    _ap = {
        "name": "applet",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "kanban",
    }
    _kp = {
        "name": "key",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "boards",
    }
    return {
        "/api/store/{applet}": {
            "get": {
                "tags": ["Store"],
                "summary": "List stored keys",
                "operationId": "storeListKeys",
                "description": "Returns all stored key names for the given applet.",
                "parameters": [_ap],
                "responses": {
                    "200": {
                        "description": "Key list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "applet": {"type": "string"},
                                        "keys": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/store/{applet}/{key}": {
            "get": {
                "tags": ["Store"],
                "summary": "Get stored value",
                "operationId": "storeGet",
                "description": "Returns the JSON value stored under the given key.",
                "parameters": [_ap, _kp],
                "responses": {
                    "200": {
                        "description": "Stored value",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "applet": {"type": "string"},
                                        "key": {"type": "string"},
                                        "value": {},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Key not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "put": {
                "tags": ["Store"],
                "summary": "Save a value",
                "operationId": "storePut",
                "description": "Stores a JSON value under the given key. Emits a `store-changed` SSE event.",
                "parameters": [_ap, _kp],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "value": {"description": "Any JSON value to store"}
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Saved",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid key",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "delete": {
                "tags": ["Store"],
                "summary": "Delete a stored key",
                "operationId": "storeDelete",
                "description": "Removes the stored value. Emits a `store-changed` SSE event.",
                "parameters": [_ap, _kp],
                "responses": {
                    "200": {
                        "description": "Deleted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "404": {
                        "description": "Key not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def _paths_misc():
    return {
        "/api/applets": {
            "get": {
                "tags": ["Applets"],
                "summary": "List installed applets",
                "operationId": "listApplets",
                "description": "Returns metadata for all installed web applets.",
                "responses": {
                    "200": {
                        "description": "Applet list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "applets": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/applets/{applet_name}/config": {
            "get": {
                "tags": ["Applets"],
                "summary": "Get applet config",
                "operationId": "getAppletConfig",
                "description": "Returns the stored configuration and preference schema for the given applet.",
                "parameters": [
                    {
                        "name": "applet_name",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Config",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "404": {
                        "description": "Applet not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
            "put": {
                "tags": ["Applets"],
                "summary": "Save applet config",
                "operationId": "saveAppletConfig",
                "description": "Saves the applet configuration as a JSON object.",
                "parameters": [
                    {
                        "name": "applet_name",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {
                        "description": "Saved",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                },
            },
        },
        "/api/formats": {
            "get": {
                "tags": ["Formats"],
                "summary": "List available formats",
                "operationId": "listFormats",
                "description": "Returns the list of page export/dump formats supported by this Moonstone instance.",
                "responses": {
                    "200": {
                        "description": "Format list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "formats": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "example": ["wiki", "html", "plain"],
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/recent": {
            "get": {
                "tags": ["History"],
                "summary": "Recently changed pages",
                "operationId": "getRecentChanges",
                "description": "Returns pages ordered by modification time (most recent first).",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 20, "maximum": 100},
                    },
                    {
                        "name": "offset",
                        "in": "query",
                        "schema": {"type": "integer", "default": 0},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Recent pages",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "limit": {"type": "integer"},
                                        "offset": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/history": {
            "get": {
                "tags": ["History"],
                "summary": "Navigation history",
                "operationId": "getHistory",
                "description": "Returns the navigation history (pages visited via POST /api/navigate).",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 50, "maximum": 200},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "History",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "history": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "recent": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/navigate": {
            "post": {
                "tags": ["Navigation"],
                "summary": "Open a page",
                "operationId": "navigateToPage",
                "description": "Navigates to the specified page — sets current page focus, records in history, and emits a page-changed SSE event.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["page"],
                                "properties": {
                                    "page": {"type": "string", "example": "Home"}
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Navigation triggered",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "503": {
                        "description": "Navigation unavailable",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/resolve-link": {
            "post": {
                "tags": ["Navigation"],
                "summary": "Resolve a wiki link",
                "operationId": "resolveLink",
                "description": "Resolves a wiki link from the context of a source page to an absolute page path.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["source", "link"],
                                "properties": {
                                    "source": {
                                        "type": "string",
                                        "example": "Projects:WebBridge",
                                    },
                                    "link": {"type": "string", "example": "+SubPage"},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Resolved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "source": {"type": "string"},
                                        "link": {"type": "string"},
                                        "resolved": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Cannot resolve",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/create-link": {
            "post": {
                "tags": ["Navigation"],
                "summary": "Create a wiki link",
                "operationId": "createLink",
                "description": "Creates the shortest wiki link notation from source to target page.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["source", "target"],
                                "properties": {
                                    "source": {
                                        "type": "string",
                                        "example": "Projects:WebBridge",
                                    },
                                    "target": {
                                        "type": "string",
                                        "example": "Projects:OtherProject",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Link created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "source": {"type": "string"},
                                        "target": {"type": "string"},
                                        "href": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/suggest-link": {
            "get": {
                "tags": ["Navigation"],
                "summary": "Get link suggestions",
                "operationId": "suggestLink",
                "description": "Returns page name suggestions for creating a link from the given source page.",
                "parameters": [
                    {
                        "name": "from",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Source page",
                        "example": "Home",
                    },
                    {
                        "name": "text",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Partial text to match",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Suggestions",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "source": {"type": "string"},
                                        "text": {"type": "string"},
                                        "suggestions": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"}
                                                },
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/batch": {
            "post": {
                "tags": ["Batch"],
                "summary": "Execute batch operations",
                "operationId": "batch",
                "description": "Executes multiple API operations in a single HTTP request. All operations run on the main thread atomically.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "operations": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/BatchOperation"
                                        },
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Batch results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "index": {"type": "integer"},
                                                    "status": {"type": "integer"},
                                                    "body": {"type": "object"},
                                                },
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/emit": {
            "post": {
                "tags": ["Events"],
                "summary": "Emit a custom event",
                "operationId": "emitEvent",
                "description": "Emits a custom event to all connected SSE clients. The event type is prefixed with `custom:` to avoid conflicts.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["event"],
                                "properties": {
                                    "event": {"type": "string", "example": "my-event"},
                                    "data": {
                                        "type": "object",
                                        "example": {"key": "value"},
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Event emitted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OkResponse"}
                            }
                        },
                    },
                    "503": {
                        "description": "Event manager unavailable",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/events": {
            "get": {
                "tags": ["Events"],
                "summary": "SSE event stream",
                "operationId": "sseStream",
                "description": "Opens a Server-Sent Events connection. Events include page-saved, page-moved, page-deleted, page-changed, store-changed, and custom events. Event data may include a `source` field (`api`, `notebook`, or `filesystem`). Use `subscribe` to filter.",
                "parameters": [
                    {
                        "name": "subscribe",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Comma-separated event types to subscribe to. All if omitted.",
                        "example": "page-saved,store-changed",
                    },
                    {
                        "name": "token",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Auth token (for SSE, since EventSource cannot set headers).",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "SSE stream",
                        "content": {
                            "text/event-stream": {"schema": {"type": "string"}}
                        },
                    },
                },
            },
        },
    }


def _paths_analysis():
    _pp = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "Projects/WebBridge",
    }
    return {
        "/api/page/{page_path}/toc": {
            "get": {
                "tags": ["Page Operations"],
                "summary": "Get table of contents",
                "operationId": "getPageTOC",
                "description": "Extracts all headings from the page as a structured table of contents. Parsed directly from the page tree — computed from core data.",
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Table of contents",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "headings": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/Heading"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                        "exists": {"type": "boolean"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/page/{page_path}/analytics": {
            "get": {
                "tags": ["Page Operations"],
                "summary": "Get page content analytics",
                "operationId": "getPageAnalytics",
                "description": (
                    "Returns detailed statistics for a page: word count, character count, "
                    "reading time, heading/image/checkbox counts, incoming/outgoing links, "
                    "tags, page age and days since last edit. All computed from core data — computed from core data."
                ),
                "parameters": [_pp],
                "responses": {
                    "200": {
                        "description": "Page analytics",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PageAnalytics"}
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/capabilities": {
            "get": {
                "tags": ["Capabilities"],
                "summary": "Check available features",
                "operationId": "getCapabilities",
                "description": (
                    "Reports which API features are available and which optional modules "
                    "are active. Core features (pages, tags, links, search, toc, analytics, graph, analysis) "
                    "are always available. Optional features (tasklist, journal, fts, versioncontrol) "
                    "depend on user configuration. Applets should check this endpoint to adapt their UI."
                ),
                "responses": {
                    "200": {
                        "description": "Capabilities map",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "capabilities": {
                                            "type": "object",
                                            "additionalProperties": {"type": "boolean"},
                                            "example": {
                                                "pages": True,
                                                "search": True,
                                                "tags": True,
                                                "links": True,
                                                "toc": True,
                                                "analytics": True,
                                                "graph": True,
                                                "analysis": True,
                                                "tasklist": False,
                                                "journal": True,
                                                "fts": False,
                                                "readonly": False,
                                            },
                                        },
                                        "api_version": {
                                            "type": "string",
                                            "example": "2.3",
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/analysis/orphans": {
            "get": {
                "tags": ["Analysis"],
                "summary": "Find orphan pages",
                "operationId": "getOrphanPages",
                "description": (
                    "Returns pages that have no incoming links (backlinks) from any other page. "
                    'These are "orphan" pages that may be forgotten or unreachable through navigation. '
                    "Scans the entire notebook — may take a moment for large notebooks."
                ),
                "responses": {
                    "200": {
                        "description": "Orphan pages",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "orphans": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/PageInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/analysis/dead-links": {
            "get": {
                "tags": ["Analysis"],
                "summary": "Find dead links",
                "operationId": "getDeadLinks",
                "description": (
                    "Returns links that point to non-existent pages (pages without content). "
                    "Useful for cleaning up broken references. Scans the entire notebook."
                ),
                "responses": {
                    "200": {
                        "description": "Dead links",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "dead_links": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/LinkInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/graph": {
            "get": {
                "tags": ["Analysis"],
                "summary": "Get link graph data",
                "operationId": "getGraph",
                "description": (
                    "Returns nodes (pages) and edges (links) for visualizing the knowledge graph. "
                    "Each node includes a degree (number of connections). Can be filtered by namespace. "
                    "Suitable for rendering with D3.js, vis.js, Cytoscape, etc."
                ),
                "parameters": [
                    {
                        "name": "namespace",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Limit graph to pages in this namespace. All pages if omitted.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Graph data",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "nodes": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/GraphNode"
                                            },
                                        },
                                        "edges": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/GraphEdge"
                                            },
                                        },
                                        "node_count": {"type": "integer"},
                                        "edge_count": {"type": "integer"},
                                        "namespace": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
    }


# Endpoints NOT available through WebSocket (binary, streaming, lifecycle)
_WS_EXCLUDED = {
    ("/api/attachment/{page_path}/{filename}", "get"),  # binary download
    ("/api/attachment/{page_path}/{filename}", "post"),  # binary upload
    ("/api/attachment/{page_path}/{filename}", "delete"),  # use HTTP
    ("/api/page/{page_path}/export/download", "get"),  # raw file download
    ("/api/applets/install", "post"),  # long-running git clone
    ("/api/applets/updates", "get"),  # long-running git fetch
    ("/api/applets/{applet_name}", "delete"),  # destructive lifecycle
    ("/api/applets/{applet_name}/update", "post"),  # long-running git pull
    ("/api/_yield", "post"),  # server lifecycle
    ("/events", "get"),  # SSE streaming
    ("/api/services/install", "post"),  # long-running git clone + venv
    ("/api/services/{service_name}", "delete"),  # destructive lifecycle
    ("/api/services/{service_name}/start", "post"),  # process management
    ("/api/services/{service_name}/stop", "post"),  # process management
    ("/api/services/{service_name}/restart", "post"),  # process management
    ("/api/services/{service_name}/update", "post"),  # long-running git pull
}


def _annotate_ws_proxy(spec):
    """Add x-websocket-proxy extension to all operations.

    Marks each operation with x-websocket-proxy: true/false so applet
    developers know which endpoints can be called via the WebSocket
    ``api`` action and which require direct HTTP.
    """
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            key = (path, method)
            if key in _WS_EXCLUDED:
                operation["x-websocket-proxy"] = False
            else:
                operation["x-websocket-proxy"] = True
    return spec


def get_openapi_spec(port=8090):
    """Return the complete OpenAPI 3.0.3 spec as a dict."""
    return _annotate_ws_proxy(
        {
            "openapi": "3.0.3",
            "info": {
                "title": "Moonstone API",
                "version": "2.5.0",
                "description": (
                    "REST API for the Moonstone personal knowledge management system.\n\n"
                    "Gives full access to notebook pages, tags, links, attachments, "
                    "search, navigation history, and more.\n\n"
                    "## Real-time Communication\n\n"
                    "**SSE** (Server-Sent Events): `GET /events` — unidirectional server→client push.\n\n"
                    "**WebSocket**: `ws://host:PORT+1` — bidirectional real-time communication. "
                    "Discovered via `GET /api/capabilities` → `websocket.url`.\n\n"
                    "### WebSocket Protocol\n\n"
                    "JSON messages over text frames:\n\n"
                    "**Client → Server:**\n"
                    '- `{"action":"subscribe","channel":"ch","id":"1"}` — subscribe to a channel\n'
                    '- `{"action":"unsubscribe","channel":"ch","id":"2"}` — unsubscribe\n'
                    '- `{"action":"broadcast","channel":"ch","data":{...},"id":"3"}` — send to channel\n'
                    '- `{"action":"api","data":{"method":"GET","path":"/api/page/Home"},"id":"4"}` — proxy REST call\n'
                    '- `{"action":"ping"}` — keepalive\n\n'
                    "**Server → Client (replies):**\n"
                    '- `{"id":"1","ok":true,"data":{"channel":"ch"}}` — subscribe OK\n'
                    '- `{"id":"4","ok":true,"data":{...}}` — API result\n\n'
                    "**Server → Client (push events):**\n"
                    '- `{"event":"connected","data":{"client_id":"ws_...","message":"..."}}` — welcome\n'
                    '- `{"event":"broadcast","channel":"ch","data":{...},"from":"ws_..."}` — channel broadcast\n'
                    '- `{"event":"page-saved","data":{"page":"Home"}}` — notebook events (global channel)\n\n'
                    "Auth: pass `?token=SECRET` in the WebSocket URL query string."
                ),
                "contact": {"name": "Moonstone"},
                "license": {
                    "name": "GPL-2.0-or-later",
                    "url": "https://www.gnu.org/licenses/gpl-2.0.html",
                },
            },
            "servers": [
                {
                    "url": "http://localhost:%d" % port,
                    "description": "Local WebBridge server",
                },
            ],
            "tags": [
                {
                    "name": "Notebook",
                    "description": "Notebook-level metadata and stats",
                },
                {"name": "Pages", "description": "List, walk, match and count pages"},
                {
                    "name": "Page CRUD",
                    "description": "Create, read, update, delete individual pages",
                },
                {
                    "name": "Page Operations",
                    "description": "Append, move, trash, siblings, parse tree",
                },
                {
                    "name": "Search",
                    "description": "Full-text search with optional snippets",
                },
                {
                    "name": "Tags",
                    "description": "Tag listing, pages by tag, intersecting tags",
                },
                {
                    "name": "Links",
                    "description": "Forward/backward links, floating links, sections",
                },
                {
                    "name": "Attachments",
                    "description": "List, download, upload and delete attachments",
                },
                {"name": "Store", "description": "Key-value storage per applet"},
                {"name": "Applets", "description": "Applet listing and configuration"},
                {"name": "Events", "description": "Server-Sent Events stream"},
                {
                    "name": "Navigation",
                    "description": "Navigate pages, resolve/create links",
                },
                {
                    "name": "Batch",
                    "description": "Execute multiple operations in one request",
                },
                {"name": "Formats", "description": "Available export formats"},
                {
                    "name": "History",
                    "description": "Navigation history and recent pages",
                },
                {
                    "name": "Analysis",
                    "description": "Orphan pages, dead links, graph data",
                },
                {
                    "name": "Export",
                    "description": "Export pages to HTML, Markdown, LaTeX, RST",
                },
                {"name": "Templates", "description": "Available export templates"},
                {"name": "Sitemap", "description": "XML/JSON sitemap generation"},
                {
                    "name": "Tag Management",
                    "description": "Add and remove tags from pages",
                },
                {"name": "Capabilities", "description": "Feature availability"},
                {
                    "name": "Services",
                    "description": "Background services (bots, integrations, daemons)",
                },
                {
                    "name": "Internal",
                    "description": "Internal/service endpoints (hot handoff, etc.)",
                },
            ],
            "components": {
                "schemas": _schemas(),
                "securitySchemes": {
                    "TokenAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-Auth-Token",
                        "description": "Authentication token (optional, if server started with --token)",
                    },
                },
            },
            "security": [
                {},
                {"TokenAuth": []},
            ],
            "paths": _paths(),
        }
    )


def _paths_export_templates():
    _pp = {
        "name": "page_path",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "Projects/WebBridge",
    }
    _fmt = {
        "name": "format",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["html", "wiki", "plain", "markdown", "latex", "rst"],
            "default": "html",
        },
        "description": "Export format.",
    }
    return {
        "/api/page/{page_path}/export": {
            "get": {
                "tags": ["Export"],
                "summary": "Export page content",
                "operationId": "exportPage",
                "description": (
                    "Exports the page content in the specified format (HTML, Markdown, LaTeX, RST, plain text, or wiki markup). "
                    "Returns the exported content as a JSON envelope with metadata including MIME type and content length."
                ),
                "parameters": [
                    _pp,
                    _fmt,
                    {
                        "name": "template",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Template name (not yet fully supported, reserved for future use).",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Exported content",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ExportResult"}
                            }
                        },
                    },
                    "400": {
                        "description": "Unsupported format",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/page/{page_path}/export/download": {
            "get": {
                "tags": ["Export"],
                "summary": "Download exported page",
                "operationId": "exportPageDownload",
                "description": (
                    "Downloads the page content as a raw file with the appropriate MIME type and Content-Disposition header. "
                    'Suitable for "Save As" functionality in web applets.'
                ),
                "parameters": [_pp, _fmt],
                "responses": {
                    "200": {
                        "description": "Raw file download",
                        "content": {
                            "text/html": {"schema": {"type": "string"}},
                            "text/markdown": {"schema": {"type": "string"}},
                            "application/x-latex": {"schema": {"type": "string"}},
                            "text/x-rst": {"schema": {"type": "string"}},
                            "text/plain": {"schema": {"type": "string"}},
                        },
                    },
                    "400": {
                        "description": "Unsupported format",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                    "404": {
                        "description": "Page not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
        "/api/templates": {
            "get": {
                "tags": ["Templates"],
                "summary": "List available export templates",
                "operationId": "listTemplates",
                "description": (
                    "Returns all available export templates grouped by format. "
                    "Templates include HTML (Default, Print, SlideShow, etc.), LaTeX (Article, Report, Part), "
                    "Markdown, RST, and Wiki templates. Use the format parameter to filter."
                ),
                "parameters": [
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["html", "latex", "markdown", "rst", "wiki"],
                        },
                        "description": "Filter templates by format.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Template list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "templates": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/TemplateInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                        "formats": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                },
            },
        },
        "/api/sitemap": {
            "get": {
                "tags": ["Sitemap"],
                "summary": "Generate notebook sitemap",
                "operationId": "getSitemap",
                "description": (
                    "Generates a sitemap of all pages in the notebook. "
                    "Supports XML (standard sitemap.org format) and JSON output. "
                    "XML format is suitable for SEO tools and external crawlers. "
                    "JSON format provides page names, basenames and URL paths."
                ),
                "parameters": [
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["xml", "json"],
                            "default": "json",
                        },
                        "description": "Output format. XML returns standard sitemap.org XML.",
                    },
                    {
                        "name": "base_url",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Base URL for sitemap entries (defaults to server URL).",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Sitemap",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/SitemapPage"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                        "format": {"type": "string"},
                                    },
                                }
                            },
                            "application/xml": {
                                "schema": {
                                    "type": "string",
                                    "description": "Standard sitemap.org XML",
                                }
                            },
                        },
                    },
                },
            },
        },
    }


def _paths_applet_management():
    """Applet installation, update, and uninstall endpoints (v2.5)."""
    _an = {
        "name": "applet_name",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "kanban",
    }
    _err = {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        }
    }
    return {
        "/api/applets/install": {
            "post": {
                "tags": ["Applets"],
                "summary": "Install applet from Git",
                "operationId": "installApplet",
                "description": (
                    "Clones a Git repository into the applets directory and registers it as a new applet. "
                    "The repository must contain a valid manifest.json. After installation the applet manager "
                    "is refreshed and an `applet-installed` SSE event is emitted."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["url"],
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "description": "Git repository URL",
                                        "example": "https://github.com/user/moonstone-applet",
                                    },
                                    "branch": {
                                        "type": "string",
                                        "nullable": True,
                                        "description": "Branch to clone (default: repo default branch)",
                                    },
                                    "name": {
                                        "type": "string",
                                        "nullable": True,
                                        "description": "Override applet directory name",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Applet installed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "name": {
                                            "type": "string",
                                            "description": "Applet directory name",
                                        },
                                        "label": {
                                            "type": "string",
                                            "description": "Human-readable applet name",
                                        },
                                        "version": {"type": "string"},
                                        "warnings": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Installation error (invalid URL, missing manifest, etc.)",
                        **_err,
                    },
                    "500": {"description": "Internal error", **_err},
                },
            },
        },
        "/api/applets/updates": {
            "get": {
                "tags": ["Applets"],
                "summary": "Check all applets for updates",
                "operationId": "checkAppletUpdates",
                "description": (
                    "Checks all git-installed applets for available updates by comparing "
                    "local HEAD with the remote. Returns a list of applets with their update status."
                ),
                "responses": {
                    "200": {
                        "description": "Update check results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "applets": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "has_update": {"type": "boolean"},
                                                    "local_commit": {"type": "string"},
                                                    "remote_commit": {"type": "string"},
                                                },
                                            },
                                        },
                                        "count": {"type": "integer"},
                                        "has_updates": {
                                            "type": "boolean",
                                            "description": "True if any applet has an available update",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "500": {"description": "Check failed", **_err},
                },
            },
        },
        "/api/applets/{applet_name}": {
            "delete": {
                "tags": ["Applets"],
                "summary": "Uninstall an applet",
                "operationId": "uninstallApplet",
                "description": (
                    "Removes an applet and all its files from the applets directory. "
                    "Refreshes the applet manager and emits an `applet-uninstalled` SSE event."
                ),
                "parameters": [_an],
                "responses": {
                    "200": {
                        "description": "Applet uninstalled",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "name": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Uninstall error", **_err},
                    "500": {"description": "Internal error", **_err},
                },
            },
        },
        "/api/applets/{applet_name}/update": {
            "post": {
                "tags": ["Applets"],
                "summary": "Update a git-installed applet",
                "operationId": "updateApplet",
                "description": (
                    "Pulls the latest changes from the remote Git repository for the given applet. "
                    "Refreshes the applet manager and emits an `applet-updated` SSE event if changes were pulled."
                ),
                "parameters": [_an],
                "responses": {
                    "200": {
                        "description": "Update result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "name": {"type": "string"},
                                        "updated": {
                                            "type": "boolean",
                                            "description": "True if new changes were pulled",
                                        },
                                        "new_commit": {
                                            "type": "string",
                                            "description": "New HEAD commit hash",
                                        },
                                        "message": {
                                            "type": "string",
                                            "description": 'Status message (e.g. "Already up to date")',
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Update error (not a git repo, etc.)",
                        **_err,
                    },
                    "500": {"description": "Internal error", **_err},
                },
            },
        },
        "/api/applets/{applet_name}/source": {
            "get": {
                "tags": ["Applets"],
                "summary": "Get applet installation source info",
                "operationId": "getAppletSource",
                "description": (
                    "Returns information about how the applet was installed: "
                    "Git repository URL, current commit, branch, and whether it was installed from Git or is a local applet."
                ),
                "parameters": [_an],
                "responses": {
                    "200": {
                        "description": "Source info",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "source": {
                                            "type": "string",
                                            "enum": ["git", "local"],
                                            "description": "Installation source type",
                                        },
                                        "repository": {
                                            "type": "string",
                                            "nullable": True,
                                            "description": "Git remote URL",
                                        },
                                        "branch": {"type": "string", "nullable": True},
                                        "commit": {
                                            "type": "string",
                                            "nullable": True,
                                            "description": "Current HEAD commit hash",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Applet not found", **_err},
                },
            },
        },
    }


def _paths_services():
    """Background service management endpoints (v2.6)."""
    _sn = {
        "name": "service_name",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "telegram-notes",
    }
    _err = {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        }
    }
    _svc_resp = {
        "description": "Service info",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ServiceInfo"}}
        },
    }
    _ok_resp = {
        "description": "OK",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/OkResponse"}}
        },
    }
    return {
        "/api/services": {
            "get": {
                "tags": ["Services"],
                "summary": "List all services",
                "operationId": "listServices",
                "description": (
                    "Returns metadata and status for all installed background services. "
                    "Each service includes its current status (running/stopped/error), PID, uptime, and configuration availability."
                ),
                "responses": {
                    "200": {
                        "description": "Service list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "services": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/ServiceInfo"
                                            },
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "503": {"description": "Service manager not available", **_err},
                },
            },
        },
        "/api/services/install": {
            "post": {
                "tags": ["Services"],
                "summary": "Install service from Git",
                "operationId": "installService",
                "description": (
                    "Clones a Git repository into the services directory. The repository must contain "
                    'a manifest.json with `"type": "service"` and an entry script (default: service.py). '
                    "A Python venv is created automatically if requirements.txt is present."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["url"],
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "example": "https://github.com/user/moonstone-telegram-bot",
                                    },
                                    "branch": {"type": "string", "nullable": True},
                                    "name": {
                                        "type": "string",
                                        "nullable": True,
                                        "description": "Override service directory name",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Service installed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "name": {"type": "string"},
                                        "label": {"type": "string"},
                                        "version": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Installation error", **_err},
                },
            },
        },
        "/api/services/{service_name}": {
            "get": {
                "tags": ["Services"],
                "summary": "Get service details",
                "operationId": "getService",
                "description": "Returns detailed information about a specific service including status, PID, uptime, and error messages.",
                "parameters": [_sn],
                "responses": {
                    "200": _svc_resp,
                    "404": {"description": "Service not found", **_err},
                },
            },
            "delete": {
                "tags": ["Services"],
                "summary": "Uninstall a service",
                "operationId": "uninstallService",
                "description": "Stops the service if running and removes all its files including venv and data.",
                "parameters": [_sn],
                "responses": {
                    "200": _ok_resp,
                    "400": {"description": "Uninstall error", **_err},
                },
            },
        },
        "/api/services/{service_name}/start": {
            "post": {
                "tags": ["Services"],
                "summary": "Start a service",
                "operationId": "startService",
                "description": (
                    "Starts the service process. Creates a venv and installs requirements.txt on first run. "
                    "Environment variables MOONSTONE_API_URL, MOONSTONE_AUTH_TOKEN, MOONSTONE_SERVICE_DATA_DIR are passed to the process."
                ),
                "parameters": [_sn],
                "responses": {
                    "200": _ok_resp,
                    "400": {
                        "description": "Start error (already running, missing entry, etc.)",
                        **_err,
                    },
                },
            },
        },
        "/api/services/{service_name}/stop": {
            "post": {
                "tags": ["Services"],
                "summary": "Stop a service",
                "operationId": "stopService",
                "description": "Sends SIGTERM to the service process and waits for graceful shutdown (5s timeout, then SIGKILL).",
                "parameters": [_sn],
                "responses": {
                    "200": _ok_resp,
                    "400": {"description": "Stop error", **_err},
                },
            },
        },
        "/api/services/{service_name}/restart": {
            "post": {
                "tags": ["Services"],
                "summary": "Restart a service",
                "operationId": "restartService",
                "description": "Stops and then starts the service. Equivalent to stop + start.",
                "parameters": [_sn],
                "responses": {
                    "200": _ok_resp,
                    "400": {"description": "Restart error", **_err},
                },
            },
        },
        "/api/services/{service_name}/update": {
            "post": {
                "tags": ["Services"],
                "summary": "Update a git-installed service",
                "operationId": "updateService",
                "description": "Pulls the latest changes from Git. Reinstalls requirements if requirements.txt changed.",
                "parameters": [_sn],
                "responses": {
                    "200": {
                        "description": "Update result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "name": {"type": "string"},
                                        "updated": {"type": "boolean"},
                                        "message": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Update error", **_err},
                },
            },
        },
        "/api/services/updates": {
            "get": {
                "tags": ["Services"],
                "summary": "Check all services for updates",
                "operationId": "checkServiceUpdates",
                "description": (
                    "Checks all git-installed services for available updates by comparing "
                    "local HEAD with the remote. Returns a list of services with their update status."
                ),
                "responses": {
                    "200": {
                        "description": "Update check results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "services": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "has_update": {"type": "boolean"},
                                                    "local_commit": {"type": "string"},
                                                    "remote_commit": {"type": "string"},
                                                },
                                            },
                                        },
                                        "count": {"type": "integer"},
                                        "has_updates": {
                                            "type": "boolean",
                                            "description": "True if any service has an available update",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "503": {"description": "Service manager not available", **_err},
                },
            },
        },
        "/api/services/{service_name}/logs": {
            "get": {
                "tags": ["Services"],
                "summary": "Get service logs",
                "operationId": "getServiceLogs",
                "description": "Returns the last N lines of stdout/stderr from the service process.",
                "parameters": [
                    _sn,
                    {
                        "name": "tail",
                        "in": "query",
                        "schema": {"type": "integer", "default": 100, "maximum": 1000},
                        "description": "Number of log lines to return.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Service logs",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "lines": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "count": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Service not found", **_err},
                },
            },
        },
        "/api/services/{service_name}/config": {
            "get": {
                "tags": ["Services"],
                "summary": "Get service configuration",
                "operationId": "getServiceConfig",
                "description": (
                    "Returns the current configuration values and the preferences schema from manifest.json. "
                    "The schema describes available config keys, types, labels, and defaults."
                ),
                "parameters": [_sn],
                "responses": {
                    "200": {
                        "description": "Service config",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "config": {
                                            "type": "object",
                                            "description": "Current config key-value pairs",
                                        },
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/ServiceConfigPreference"
                                            },
                                            "description": "Preferences schema from manifest.json",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Service not found", **_err},
                },
            },
            "put": {
                "tags": ["Services"],
                "summary": "Save service configuration",
                "operationId": "saveServiceConfig",
                "description": (
                    "Saves the service configuration. Values are stored in `_data/_config.json` within the service directory. "
                    "Restart the service for changes to take effect."
                ),
                "parameters": [_sn],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "description": "Key-value pairs to save as service configuration",
                                "additionalProperties": True,
                            }
                        }
                    },
                },
                "responses": {
                    "200": _ok_resp,
                    "400": {"description": "Save error", **_err},
                },
            },
        },
    }


def _paths_internal():
    """Internal/service endpoints."""
    return {
        "/api/_yield": {
            "post": {
                "tags": ["Internal"],
                "summary": "Yield server (hot handoff)",
                "operationId": "yieldServer",
                "description": (
                    "Internal endpoint for hot handoff. Requests the current server instance to yield, "
                    "allowing another instance to take over the port. Used by the headless launcher to "
                    "coordinate server restarts without downtime."
                ),
                "responses": {
                    "200": {
                        "description": "Server yielding",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "message": {
                                            "type": "string",
                                            "example": "Yielding server",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "501": {
                        "description": "Yield not supported by this server instance",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    },
                },
            },
        },
    }


def get_swagger_ui_html(spec_url="/api/openapi.json"):
    """Return Swagger UI HTML page."""
    return (
        '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Moonstone API — Swagger UI</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<style>
body { margin: 0; background: #fafafa; }
.topbar-wrapper img { content: url("data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%%3E%%3Ctext y='80' font-size='80'%%3E🌉%%3C/text%%3E%%3C/svg%%3E"); height: 40px; }
.swagger-ui .topbar { background: #2c3e50; padding: 8px 0; }
.swagger-ui .topbar .download-url-wrapper input { border-color: #3498db; }
.swagger-ui .info .title { font-size: 2rem; }
</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: "'''
        + spec_url
        + """",
  dom_id: "#swagger-ui",
  deepLinking: true,
  presets: [SwaggerUIBundle.presets.apis],
  layout: "BaseLayout",
  defaultModelsExpandDepth: 2,
  defaultModelExpandDepth: 2,
  docExpansion: "list",
  filter: true,
  showExtensions: true,
  tryItOutEnabled: true,
});
</script>
</body>
</html>"""
    )
