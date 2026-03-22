import re
import json
import urllib.parse
from moonstone.webbridge.openapi import get_openapi_spec, get_swagger_ui_html

from moonstone.webbridge.dispatcher import router

# ---- Helpers ----
def _get_json_body(app, environ, start_response, cors_headers):
    request_body = app._read_request_body(environ)
    try:
        return json.loads(request_body)
    except json.JSONDecodeError:
        return None

def _parse_int_param(params, key, default=0, max_value=None):
    """Safely parse an integer parameter.
    
    Returns (value, error_message) tuple.
    On success: (parsed_int, None)
    On failure: (None, error_string)
    """
    values = params.get(key, [])
    raw_value = values[0] if values else None
    
    # Handle missing or empty
    if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
        return default, None
    
    raw_value = raw_value.strip()
    
    try:
        value = int(raw_value)
    except ValueError:
        return None, "Invalid '%s' parameter: must be a non-negative integer, got '%s'" % (key, raw_value)
    
    if value < 0:
        return None, "Invalid '%s' parameter: must be a non-negative integer, got '%s'" % (key, raw_value)
    
    if max_value is not None and value > max_value:
        value = max_value
    
    return value, None

# ---- Notebook info ----
@router.route("GET", r"^/api/notebook$")
def notebook_info(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_notebook_info()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/current$")
def current_page(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_current_page()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/stats$")
def stats(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_stats()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/formats$")
def formats(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_formats() if hasattr(app.api, "get_formats") else app.api.list_formats()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/capabilities$")
def capabilities(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_capabilities()
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Pages ----
@router.route("GET", r"^/api/pages$")
def list_pages(app, params, environ, start_response, cors_headers):
    namespace = params.get("namespace", [None])[0]
    limit_str = params.get("limit", [None])[0]
    offset, err = _parse_int_param(params, "offset", default=0)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    if limit_str is not None:
        limit, err = _parse_int_param(params, "limit", default=20, max_value=1000)
        if err:
            return app._json_response(start_response, 400, {"error": err}, cors_headers)
        status, headers, body = app.api.list_pages_paginated(namespace, limit, offset)
    else:
        status, headers, body = app.api.list_pages_paginated(namespace, None, offset)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/pages/match$")
def match_pages(app, params, environ, start_response, cors_headers):
    query = params.get("q", [""])[0]
    limit, err = _parse_int_param(params, "limit", default=10, max_value=50)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.match_pages(query, limit)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/pages/match$")
def match_pages(app, params, environ, start_response, cors_headers):
    query = params.get("q", [""])[0]
    limit, err = _parse_int_param(params, "limit", default=10, max_value=50)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.match_pages(query, limit)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/pages/walk$")
def walk_pages(app, params, environ, start_response, cors_headers):
    namespace = params.get("namespace", [None])[0]
    status, headers, body = app.api.walk_pages(namespace)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/pages/count$")
def count_pages(app, params, environ, start_response, cors_headers):
    namespace = params.get("namespace", [None])[0]
    status, headers, body = app.api.count_pages(namespace)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Search ----
@router.route("GET", r"^/api/search$")
def search(app, params, environ, start_response, cors_headers):
    query = params.get("q", [""])[0]
    snippets = params.get("snippets", [""])[0].lower() in ("true", "1", "yes")
    if snippets:
        snippet_len, err = _parse_int_param(params, "snippet_length", default=120)
        if err:
            return app._json_response(start_response, 400, {"error": err}, cors_headers)
        status, headers, body = app.api.search_pages_with_snippets(query, True, snippet_len)
    else:
        status, headers, body = app.api.search_pages(query)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Tags ----
@router.route("GET", r"^/api/tags$")
def list_tags(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.list_tags()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/tags/intersecting$")
def intersecting_tags(app, params, environ, start_response, cors_headers):
    tags_str = params.get("tags", [""])[0]
    tag_names = [t.strip() for t in tags_str.split(",") if t.strip()]
    if not tag_names:
        return app._json_response(start_response, 400, {"error": "Missing 'tags' parameter"}, cors_headers)
    status, headers, body = app.api.get_intersecting_tags(tag_names)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/tags/(?P<tag>.+)/pages$")
def tag_pages(app, params, environ, start_response, cors_headers, tag):
    status, headers, body = app.api.get_tag_pages(tag)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Links ----
@router.route("GET", r"^/api/links/floating$")
def floating_links(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.list_floating_links()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/links/(?P<page_path>.+)/count$")
def count_links(app, params, environ, start_response, cors_headers, page_path):
    direction = params.get("direction", ["forward"])[0]
    status, headers, body = app.api.count_links(page_path, direction)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/links/(?P<page_path>.+)/section$")
def links_section(app, params, environ, start_response, cors_headers, page_path):
    direction = params.get("direction", ["forward"])[0]
    status, headers, body = app.api.get_links_section(page_path, direction)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/links/(?P<page_path>.+)$")
def get_links(app, params, environ, start_response, cors_headers, page_path):
    direction = params.get("direction", ["forward"])[0]
    status, headers, body = app.api.get_links(page_path, direction)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Link Operations ----
@router.route("POST", r"^/api/resolve-link$")
def resolve_link(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    source = data.get("source", "")
    link = data.get("link", "")
    if not source or not link: return app._json_response(start_response, 400, {"error": "Missing source or link"}, cors_headers)
    status, headers, body = app.api.resolve_link(source, link)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/create-link$")
def create_link(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    source = data.get("source", "")
    target = data.get("target", "")
    if not source or not target: return app._json_response(start_response, 400, {"error": "Missing source or target"}, cors_headers)
    status, headers, body = app.api.create_link(source, target)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/suggest-link$")
def suggest_link(app, params, environ, start_response, cors_headers):
    source = params.get("from", ["Home"])[0] or "Home"
    text = params.get("text", [""])[0]
    if not text: return app._json_response(start_response, 400, {"error": "Missing text"}, cors_headers)
    status, headers, body = app.api.suggest_link(source, text)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Navigation ----
@router.route("POST", r"^/api/navigate$")
def navigate(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    page_name = data.get("page", "")
    if not page_name: return app._json_response(start_response, 400, {"error": "Missing page"}, cors_headers)
    status, headers, body = app.api.navigate_to_page(page_name)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Recent & History ----
@router.route("GET", r"^/api/recent$")
def recent(app, params, environ, start_response, cors_headers):
    limit, err = _parse_int_param(params, "limit", default=20, max_value=100)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    offset, err = _parse_int_param(params, "offset", default=0)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.get_recent_changes(limit, offset)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/history$")
def history(app, params, environ, start_response, cors_headers):
    limit, err = _parse_int_param(params, "limit", default=50, max_value=200)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.get_history(limit)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Page specific (Must come before generic Page CRUD) ----
@router.route("POST", r"^/api/page/(?P<page_path>.+)/append$")
def page_append(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.append_to_page(page_path, data.get("content", ""), data.get("format", "wiki"))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/page/(?P<page_path>.+)/move$")
def page_move(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    new_path = data.get("newpath", "")
    if not new_path: return app._json_response(start_response, 400, {"error": "Missing newpath"}, cors_headers)
    status, headers, body = app.api.move_page(page_path, new_path, data.get("update_links", True))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/page/(?P<page_path>.+)/trash$")
def page_trash(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.trash_page(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/tags$")
def page_get_tags(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.get_page_tags(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/page/(?P<page_path>.+)/tags$")
def page_add_tag(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    tag_name = data.get("tag", "")
    if not tag_name: return app._json_response(start_response, 400, {"error": "Missing tag"}, cors_headers)
    status, headers, body = app.api.add_tag_to_page(page_path, tag_name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/page/(?P<page_path>.+)/tags/(?P<tag>.+)$")
def page_remove_tag(app, params, environ, start_response, cors_headers, page_path, tag):
    status, headers, body = app.api.remove_tag_from_page(page_path, tag)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/siblings$")
def page_siblings(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.get_page_siblings(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/parsetree$")
def page_parsetree(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.get_page_parsetree(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/toc$")
def page_toc(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.get_page_toc(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/analytics$")
def page_analytics(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.get_page_analytics(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/export/download$")
def page_export_raw(app, params, environ, start_response, cors_headers, page_path):
    fmt = params.get("format", ["html"])[0]
    status, headers, body = app.api.export_page_raw(page_path, fmt)
    if isinstance(body, str):
        content = body.encode("utf-8")
        response_headers = cors_headers + list(headers.items())
        response_headers.append(("Content-Length", str(len(content))))
        start_response(app._status_string(status), response_headers)
        return [content]
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)/export$")
def page_export(app, params, environ, start_response, cors_headers, page_path):
    fmt = params.get("format", ["html"])[0]
    template = params.get("template", [None])[0]
    status, headers, body = app.api.export_page(page_path, fmt, template)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Page CRUD ----
@router.route("GET", r"^/api/page/(?P<page_path>.+)/raw$")
def page_get_raw(app, params, environ, start_response, cors_headers, page_path):
    result = app.api.get_page_raw(page_path)
    status, headers, body = result
    # Binary response - not JSON
    if isinstance(body, bytes):
        response_headers = cors_headers + list(headers.items())
        response_headers.append(("Content-Length", str(len(body))))
        start_response(app._status_string(status), response_headers)
        return [body]
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/page/(?P<page_path>.+)$")
def page_get(app, params, environ, start_response, cors_headers, page_path):
    fmt = params.get("format", ["wiki"])[0]
    status, headers, body = app.api.get_page(page_path, fmt)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("PUT", r"^/api/page/(?P<page_path>.+)$")
def page_put(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    content = data.get("content", "")
    fmt = data.get("format", "wiki")
    expected_mtime = data.get("expected_mtime")
    if expected_mtime is not None:
        try: expected_mtime = float(expected_mtime)
        except: expected_mtime = None
    status, headers, body = app.api.save_page(page_path, content, fmt, expected_mtime)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("PATCH", r"^/api/page/(?P<page_path>.+)$")
def page_patch(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    operations = data.get("operations", [])
    expected_mtime = data.get("expected_mtime")
    if expected_mtime is not None:
        try: expected_mtime = float(expected_mtime)
        except: expected_mtime = None
    status, headers, body = app.api.patch_page(page_path, operations, expected_mtime)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/page/(?P<page_path>.+)$")
def page_post(app, params, environ, start_response, cors_headers, page_path):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.create_page(page_path, data.get("content", ""), data.get("format", "wiki"))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/page/(?P<page_path>.+)$")
def page_delete(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.delete_page(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Attachments ----
@router.route("GET", r"^/api/attachments/(?P<page_path>.+)$")
def list_attachments(app, params, environ, start_response, cors_headers, page_path):
    status, headers, body = app.api.list_attachments(page_path)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/attachment/(?P<page_path>.+)/(?P<filename>[^/]+)$")
def get_attachment(app, params, environ, start_response, cors_headers, page_path, filename):
    status, headers, body = app.api.get_attachment(page_path, filename)
    if isinstance(body, bytes):
        response_headers = cors_headers + list(headers.items())
        response_headers.append(("Content-Length", str(len(body))))
        start_response(app._status_string(status), response_headers)
        return [body]
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/attachment/(?P<page_path>.+)/(?P<filename>[^/]+)$")
def post_attachment(app, params, environ, start_response, cors_headers, page_path, filename):
    file_data = app._read_request_body_raw(environ)
    status, headers, body = app.api.upload_attachment(page_path, filename, file_data)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/attachment/(?P<page_path>.+)/(?P<filename>[^/]+)$")
def delete_attachment(app, params, environ, start_response, cors_headers, page_path, filename):
    status, headers, body = app.api.delete_attachment(page_path, filename)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Tree, Templates, Sitemap ----
@router.route("GET", r"^/api/pagetree$")
def pagetree(app, params, environ, start_response, cors_headers):
    namespace = params.get("namespace", [None])[0]
    depth, err = _parse_int_param(params, "depth", default=2, max_value=10)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.get_page_tree(namespace, depth)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/templates$")
def templates(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.list_templates(params.get("format", [None])[0])
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/sitemap$")
def sitemap(app, params, environ, start_response, cors_headers):
    fmt = params.get("format", ["json"])[0]
    base_url = params.get("base_url", [None])[0] or f"http://localhost:{app.port}"
    status, headers, body = app.api.get_sitemap(fmt, base_url)
    if isinstance(body, str):
        content = body.encode("utf-8")
        response_headers = cors_headers + list(headers.items())
        response_headers.append(("Content-Length", str(len(content))))
        start_response(app._status_string(status), response_headers)
        return [content]
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Applets ----
@router.route("GET", r"^/api/applets$")
def applets_list(app, params, environ, start_response, cors_headers):
    app.applet_manager.refresh()
    return app._json_response(start_response, 200, {"applets": app.applet_manager.list_applets()}, cors_headers)

@router.route("POST", r"^/api/applets/install$")
def applets_install(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None or not data.get("url"): return app._json_response(start_response, 400, {"error": "Missing url"}, cors_headers)
    status, headers, body = app.api.install_applet(data["url"], data.get("branch"), data.get("name"))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/applets/updates$")
def applets_updates(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.check_applet_updates()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/applets/(?P<name>[^/]+)$")
def applets_delete(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.uninstall_applet(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/applets/(?P<name>[^/]+)/update$")
def applets_update(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.update_applet(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/applets/(?P<name>[^/]+)/source$")
def applets_source(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.get_applet_source(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/applets/(?P<name>[^/]+)/config$")
def applets_get_config(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.get_applet_config(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("PUT", r"^/api/applets/(?P<name>[^/]+)/config$")
def applets_put_config(app, params, environ, start_response, cors_headers, name):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.save_applet_config(name, data)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Store ----
@router.route("GET", r"^/api/store/(?P<applet>[^/]+)$")
def store_get_list(app, params, environ, start_response, cors_headers, applet):
    status, headers, body = app.api.store_get(applet)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/store/(?P<applet>[^/]+)/(?P<key>.+)$")
def store_get_key(app, params, environ, start_response, cors_headers, applet, key):
    status, headers, body = app.api.store_get(applet, key)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("PUT", r"^/api/store/(?P<applet>[^/]+)/(?P<key>.+)$")
def store_put(app, params, environ, start_response, cors_headers, applet, key):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.store_put(applet, key, data.get("value", data))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/store/(?P<applet>[^/]+)/(?P<key>.+)$")
def store_delete(app, params, environ, start_response, cors_headers, applet, key):
    status, headers, body = app.api.store_delete(applet, key)
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Batch & Emit ----
@router.route("POST", r"^/api/batch$")
def batch(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    ops = data if isinstance(data, list) else data.get("operations", [])
    if not ops: return app._json_response(start_response, 400, {"error": "No operations"}, cors_headers)
    status, headers, body = app.api.batch(ops)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/emit$")
def emit(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.emit_custom_event(data.get("event", ""), data.get("data", {}))
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- Analysis ----
@router.route("GET", r"^/api/analysis/orphans$")
def analysis_orphans(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_orphan_pages()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/analysis/dead-links$")
def analysis_dead_links(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_dead_links()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/graph$")
def graph(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_graph(params.get("namespace", [None])[0])
    return app._json_response(start_response, status, body, cors_headers, headers)

# ---- OpenAPI / Docs ----
@router.route("GET", r"^/api/openapi.json$")
def openapi(app, params, environ, start_response, cors_headers):
    return app._json_response(start_response, 200, get_openapi_spec(app.port), cors_headers)

@router.route("GET", r"^/api/docs$")
def docs(app, params, environ, start_response, cors_headers):
    content = get_swagger_ui_html("/api/openapi.json").encode("utf-8")
    headers = cors_headers + [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(content)))]
    start_response("200 OK", headers)
    return [content]

# ---- Services ----
@router.route("GET", r"^/api/services$")
def list_services(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.list_services()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/services/install$")
def install_service(app, params, environ, start_response, cors_headers):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None or not data.get("url"): return app._json_response(start_response, 400, {"error": "Missing url"}, cors_headers)
    status, headers, body = app.api.install_service(data["url"], data.get("branch"), data.get("name"))
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/services/updates$")
def services_updates(app, params, environ, start_response, cors_headers):
    status, headers, body = app.api.check_service_updates()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/services/(?P<name>[^/]+)$")
def get_service(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.get_service(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("DELETE", r"^/api/services/(?P<name>[^/]+)$")
def delete_service(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.uninstall_service(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/services/(?P<name>[^/]+)/(?P<action>start|stop|restart|update)$")
def service_action(app, params, environ, start_response, cors_headers, name, action):
    func = getattr(app.api, f"{action}_service")
    status, headers, body = func(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/services/(?P<name>[^/]+)/logs$")
def service_logs(app, params, environ, start_response, cors_headers, name):
    tail, err = _parse_int_param(params, "tail", default=100, max_value=1000)
    if err:
        return app._json_response(start_response, 400, {"error": err}, cors_headers)
    status, headers, body = app.api.get_service_logs(name, tail)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/services/(?P<name>[^/]+)/config$")
def service_get_config(app, params, environ, start_response, cors_headers, name):
    status, headers, body = app.api.get_service_config(name)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("PUT", r"^/api/services/(?P<name>[^/]+)/config$")
def service_put_config(app, params, environ, start_response, cors_headers, name):
    data = _get_json_body(app, environ, start_response, cors_headers)
    if data is None: return app._json_response(start_response, 400, {"error": "Invalid JSON"}, cors_headers)
    status, headers, body = app.api.save_service_config(name, data)
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("POST", r"^/api/_yield$")
def _yield(app, params, environ, start_response, cors_headers):
    if hasattr(app.app, "request_yield") and callable(app.app.request_yield):
        app.app.request_yield()
        return app._json_response(start_response, 200, {"ok": True}, cors_headers)
    return app._json_response(start_response, 501, {"error": "Not supported"}, cors_headers)

@router.route("GET", r"^/api/dev-bundle$")
def dev_bundle(app, params, environ, start_response, cors_headers):
    return app._serve_dev_bundle(start_response, cors_headers)


