# -*- coding: utf-8 -*-
"""WebBridge package — bundled for Moonstone standalone mode.

The original __init__.py contains GTK widget classes (
which were only needed when WebBridge ran as a
GUI extension. In standalone Moonstone mode, only the headless modules
are used: api.py, server.py, events.py, websocket.py, etc.

The GTK __init__.py is preserved as __init__gtk.py for reference
if needed.
"""
