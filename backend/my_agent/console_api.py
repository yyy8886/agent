"""Local JSON API and static server for the management console."""

import argparse
import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from my_agent.agent_manager import AgentManager
from my_agent.pipline_manager import PipelineManager
from my_agent.skill_manager import (
    install_skill,
    list_skills,
    search_market_skills,
    set_skill_enabled,
    set_skill_globally_blocked,
)


UI_DIR = Path(__file__).resolve().parent / "console_ui"
agent_manager = AgentManager()
pipeline_manager = PipelineManager()


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "MyAgentConsole/0.1"

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("请求内容过大。")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _serve_static(self, path: str):
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (UI_DIR / relative).resolve()
        if UI_DIR.resolve() not in target.parents and target != UI_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            target = UI_DIR / "index.html"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/overview":
            self._json({"agents": agent_manager.list(), "pipelines": pipeline_manager.list(), "skills": list_skills()})
        elif parsed.path == "/api/agents":
            self._json(agent_manager.list())
        elif parsed.path == "/api/pipelines":
            self._json(pipeline_manager.list())
        elif parsed.path == "/api/skills":
            self._json(list_skills())
        elif parsed.path == "/api/skills/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._json(search_market_skills(query))
        else:
            self._serve_static(parsed.path)

    def do_POST(self):
        try:
            payload = self._payload()
            if self.path == "/api/agents":
                result = agent_manager.save(payload)
            elif self.path == "/api/pipelines":
                result = pipeline_manager.save(payload, agent_manager.ids())
            elif self.path == "/api/skills/install":
                result = {"message": install_skill(str(payload["source_url"]))}
            elif self.path == "/api/skills/enabled":
                result = {"message": set_skill_enabled(str(payload["name"]), bool(payload["enabled"]))}
            elif self.path == "/api/skills/block":
                result = {"message": set_skill_globally_blocked(str(payload["name"]), bool(payload["blocked"]))}
            else:
                self._json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": f"操作失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[0] != "api":
            self._json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        if parts[1] == "agents":
            removed = agent_manager.delete(parts[2])
        elif parts[1] == "pipelines":
            removed = pipeline_manager.delete(parts[2])
        else:
            removed = False
        self._json({"deleted": removed})

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ConsoleHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"管理控制台：{url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("控制台已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

