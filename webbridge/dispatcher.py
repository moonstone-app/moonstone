import re
import json
import urllib.parse

class APIRouter:
    def __init__(self):
        self.routes = []

    def route(self, method, pattern):
        def decorator(func):
            self.routes.append((method, re.compile(pattern), func))
            return func
        return decorator

    def dispatch(self, app, method, path, params, environ, start_response, cors_headers):
        for route_method, pattern, handler in self.routes:
            if route_method == method or route_method == "ANY":
                match = pattern.match(path)
                if match:
                    kwargs = match.groupdict()
                    if "page_path" in kwargs:
                        kwargs["page_path"] = kwargs["page_path"].replace("/", ":")
                    return handler(app, params, environ, start_response, cors_headers, **kwargs)
        return None

router = APIRouter()
