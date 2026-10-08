"""Check local static responses, then stop the test-only loopback server."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.request import urlopen
import json


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


root = Path(__file__).resolve().parent / "dist"
server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
results = []
try:
    for name, expected_type in [("index.html", "text/html"), ("health.json", "application/json"), ("report.txt", "text/plain")]:
        with urlopen(f"http://127.0.0.1:{server.server_port}/{name}", timeout=5) as response:
            body = response.read()
            assert response.status == 200
            assert expected_type in response.headers["Content-Type"]
            assert body == (root / name).read_bytes()
            results.append({"asset": name, "status": response.status, "bytes": len(body)})
    print(json.dumps({"verified": True, "responses": results}))
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
