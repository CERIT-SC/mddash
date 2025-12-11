#!/usr/bin/env python3
"""Wait for Caddy proxy sidecar before starting Jupyter."""

import socket
import time

while True:
    try:
        s = socket.socket()
        s.connect(("localhost", 8888))
        s.close()
        print("Proxy is ready on port 8888")
        break
    except OSError:
        print("Waiting for proxy on port 8888...")
        time.sleep(1)
