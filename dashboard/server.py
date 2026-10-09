"""Loopback-only HTTP server for the development-memory dashboard."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import memory


STATIC_DIR = Path(__file__).parent
DEFAULT_REGISTRY = Path(
    os.environ.get(
        "DEV_MEMORY_DASHBOARD_REGISTRY",
        str(Path.home() / ".dev-memory-agent" / "dashboard-projects.json"),
    )
)


def path_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]


class DashboardCatalog:
    """Keep only project paths centrally; the memory stays in each repository."""

    def __init__(self, registry_path: Path = DEFAULT_REGISTRY):
        self.registry_path = registry_path
        self._lock = threading.RLock()

    def _paths(self) -> list[Path]:
        if not self.registry_path.exists():
            return []
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(not isinstance(item, str) for item in data):
            raise ValueError("项目列表格式无效")
        return [Path(item) for item in data]

    def _save(self, paths: list[Path]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.registry_path.with_name(self.registry_path.name + ".tmp")
        temp.write_text(json.dumps([str(path) for path in paths], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.registry_path)

    def add(self, raw_path: str) -> dict:
        root = Path(raw_path).expanduser().resolve()
        if not (root / memory.MEMORY_DIR / "project.json").is_file():
            raise ValueError("该目录没有 .dev-memory/project.json，请先对项目运行 init")
        project = memory.read_json(root / memory.MEMORY_DIR / "project.json")
        if not project.get("project_id") or not project.get("name"):
            raise ValueError("项目身份文件缺少 ID 或名称")
        with self._lock:
            paths = self._paths()
            if root not in paths:
                paths.append(root)
                self._save(paths)
        return self._summary(root)

    def remove(self, item_id: str) -> None:
        with self._lock:
            paths = self._paths()
            kept = [path for path in paths if path_id(path) != item_id]
            if len(kept) == len(paths):
                raise KeyError(item_id)
            self._save(kept)

    def _find(self, item_id: str) -> Path:
        with self._lock:
            for path in self._paths():
                if path_id(path) == item_id:
                    return path
        raise KeyError(item_id)

    @staticmethod
    def _summary(root: Path) -> dict:
        meta = memory.read_json(root / memory.MEMORY_DIR / "project.json")
        nodes = list(memory.load_nodes(root).values())
        return {
            "id": path_id(root),
            "project_id": meta["project_id"],
            "name": meta["name"],
            "goal": meta.get("goal", ""),
            "path": str(root),
            "node_count": len(nodes),
            "completed": sum(node["status"] == "completed" for node in nodes),
            "pending": sum(node["status"] in {"planned", "in_progress", "blocked", "pending_approval"} for node in nodes),
            "updated_at": max((node["updated_at"] for node in nodes), default=meta.get("updated_at", meta.get("created_at", ""))),
        }

    def summaries(self) -> list[dict]:
        with self._lock:
            paths = self._paths()
        result = []
        for root in paths:
            try:
                result.append(self._summary(root))
            except (OSError, ValueError, KeyError) as exc:
                result.append({"id": path_id(root), "name": root.name, "path": str(root), "error": str(exc), "node_count": 0})
        return result

    def detail(self, item_id: str) -> dict:
        root = self._find(item_id)
        meta = memory.read_json(root / memory.MEMORY_DIR / "project.json")
        nodes = memory.load_nodes(root)
        versions = []
        with (root / memory.MEMORY_DIR / "NODES.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    versions.append(json.loads(line))
        return {
            "project": self._summary(root),
            "meta": meta,
            "nodes": sorted(nodes.values(), key=lambda node: (node["occurred_at"], node["created_at"])),
            "versions": versions,
            "status_text": memory.render_status(meta, nodes),
            "flow_text": memory.render_flow(meta, nodes),
            "handoff_text": memory.render_handoff(meta, nodes),
        }


def make_handler(catalog: DashboardCatalog):
    class Handler(BaseHTTPRequestHandler):
        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self._headers(status, content_type, len(body))
            self.wfile.write(body)

        def _json(self, status: int, value: object) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _local_request(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            return host in {"localhost", "127.0.0.1"}

        def _valid_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            parsed = urlsplit(origin)
            return parsed.scheme == "http" and parsed.netloc == self.headers.get("Host")

        def _path(self) -> str:
            return urlsplit(self.path).path

        def do_GET(self) -> None:
            if not self._local_request():
                self._json(403, {"error": "仅允许本机访问"})
                return
            path = self._path()
            try:
                if path == "/api/state":
                    self._json(200, {"projects": catalog.summaries()})
                    return
                if path.startswith("/api/projects/"):
                    self._json(200, catalog.detail(path.removeprefix("/api/projects/")))
                    return
                allowed = path in {"/", "/index.html", "/style.css", "/app.js", "/assets/universe-reference.png"}
                if not allowed:
                    self._json(404, {"error": "未找到页面"})
                    return
                target = (STATIC_DIR / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
                if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
                    self._json(404, {"error": "未找到页面"})
                    return
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._send(200, target.read_bytes(), content_type)
            except KeyError:
                self._json(404, {"error": "未找到项目"})
            except (OSError, ValueError) as exc:
                self._json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            if not self._local_request() or not self._valid_origin():
                self._json(403, {"error": "请求来源无效"})
                return
            if self._path() != "/api/projects":
                self._json(404, {"error": "未找到接口"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("请求内容大小无效")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or not isinstance(payload.get("path"), str):
                    raise ValueError("请提供项目目录路径")
                self._json(201, catalog.add(payload["path"]))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})

        def do_DELETE(self) -> None:
            if not self._local_request() or not self._valid_origin():
                self._json(403, {"error": "请求来源无效"})
                return
            path = self._path()
            if not path.startswith("/api/projects/"):
                self._json(404, {"error": "未找到接口"})
                return
            try:
                catalog.remove(path.removeprefix("/api/projects/"))
                self._json(200, {"ok": True})
            except KeyError:
                self._json(404, {"error": "未找到项目"})
            except (OSError, ValueError) as exc:
                self._json(500, {"error": str(exc)})

    return Handler


def serve(project: Path | None = None, port: int = 8765, open_browser: bool = True) -> None:
    catalog = DashboardCatalog()
    root = memory.find_project(project or Path.cwd())
    if root:
        catalog.add(str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(catalog))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"开发记忆仪表盘：{url}", flush=True)
    print("按 Ctrl+C 关闭本地服务", flush=True)
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
