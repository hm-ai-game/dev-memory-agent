"""Dashboard reads each project in place and serves it only on loopback."""

from __future__ import annotations

import json
import hashlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import memory
from dashboard.server import DashboardCatalog, make_handler


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.first = self.base / "first"
        self.second = self.base / "second"
        self.first.mkdir()
        self.second.mkdir()
        memory.initialize(self.first, "First", "First goal", "First scope")
        memory.initialize(self.second, "Second", "Second goal", "Second scope")
        memory.append_node(self.first, {
            "id": "n1", "kind": "requirement", "title": "First requirement",
            "summary": "A durable first-project fact", "phase": "Build", "status": "planned",
        })
        memory.append_node(self.first, {
            "title": "First requirement completed", "summary": "Verified in the first project",
            "status": "completed", "evidence_level": "observed",
        }, revise_id="n1")
        self.catalog = DashboardCatalog(self.base / "registry.json")

    def test_registry_keeps_only_paths_and_preserves_project_isolation(self) -> None:
        first = self.catalog.add(str(self.first))
        second = self.catalog.add(str(self.second))
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["node_count"], 1)
        self.assertEqual(first["completed"], 1)
        self.assertEqual(second["node_count"], 0)
        detail = self.catalog.detail(first["id"])
        self.assertEqual(len(detail["nodes"]), 1)
        self.assertEqual(len(detail["versions"]), 2)
        self.assertIn("First requirement completed", detail["status_text"])
        self.assertNotIn("Second goal", detail["handoff_text"])
        registry = self.catalog.registry_path.read_text(encoding="utf-8")
        self.assertNotIn("First requirement", registry)
        self.catalog.remove(first["id"])
        self.assertEqual(len(self.catalog.summaries()), 1)
        self.assertTrue((self.first / ".dev-memory" / "NODES.jsonl").exists())

    def test_http_serves_dashboard_and_rejects_foreign_origin(self) -> None:
        self.catalog.add(str(self.first))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.catalog))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(url + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["projects"][0]["name"], "First")
        with urlopen(url + "/") as response:
            self.assertIn(b"/app.js", response.read())
        with urlopen(url + "/assets/universe-reference.png") as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(hashlib.sha256(response.read()).hexdigest(),
                             "ffe8464afd1993c93da3dc7ec44e69a044f7316acb2546d2378796a6bb382d67")
        with self.assertRaises(HTTPError) as missing:
            urlopen(url + "/server.py")
        self.assertEqual(missing.exception.code, 404)
        with self.assertRaises(HTTPError) as no_bitmap:
            urlopen(url + "/assets/galaxy-spiral.png")
        self.assertEqual(no_bitmap.exception.code, 404)
        request = Request(url + "/api/projects", data=json.dumps({"path": str(self.second)}).encode(),
                          headers={"Origin": "http://example.com", "Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as forbidden:
            urlopen(request)
        self.assertEqual(forbidden.exception.code, 403)
        self.assertEqual(len(self.catalog.summaries()), 1)
        allowed = Request(url + "/api/projects", data=json.dumps({"path": str(self.second)}).encode(),
                          headers={"Origin": url, "Content-Type": "application/json"})
        with urlopen(allowed) as response:
            added = json.load(response)
        self.assertEqual(added["name"], "Second")
        with urlopen(url + "/api/projects/" + added["id"]) as response:
            detail = json.load(response)
        self.assertEqual(detail["meta"]["goal"], "Second goal")
        delete = Request(url + "/api/projects/" + added["id"], method="DELETE", headers={"Origin": url})
        with urlopen(delete) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(len(self.catalog.summaries()), 1)


if __name__ == "__main__":
    unittest.main()
