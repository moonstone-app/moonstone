from moonstone.webbridge.router import router
import json

@router.route("GET", r"^/api/notebook$")
def get_notebook_info(app, match, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_notebook_info()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/current$")
def get_current_page(app, match, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_current_page()
    return app._json_response(start_response, status, body, cors_headers, headers)

@router.route("GET", r"^/api/stats$")
def get_stats(app, match, params, environ, start_response, cors_headers):
    status, headers, body = app.api.get_stats()
    return app._json_response(start_response, status, body, cors_headers, headers)

