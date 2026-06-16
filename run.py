"""One-command launcher for LLM WIKI."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def inside_project_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV_DIR.resolve()


def ensure_venv() -> None:
    if not VENV_PYTHON.exists():
        print("[LLM WIKI] Creating .venv ...", flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    if not inside_project_venv():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def ensure_dependencies() -> None:
    if importlib.util.find_spec("pypdf") is not None:
        return
    print("[LLM WIKI] Installing dependencies ...", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])


def check_project() -> None:
    from src.mcp_client import MCPClient

    client = MCPClient()
    try:
        validation = client.call_tool("validate_wiki")
        tools = client.list_tools()
    finally:
        client.close()
    if not validation.get("ok"):
        raise SystemExit(f"Wiki validation failed: {validation.get('issues', [])}")
    print(f"[LLM WIKI] Ready: {validation['page_count']} pages, {len(tools)} MCP tools")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up and run LLM WIKI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="check dependencies, MCP, and Wiki validation without starting the server")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    os.chdir(ROOT)
    ensure_venv()
    ensure_dependencies()
    if args.check:
        check_project()
        return

    command = [sys.executable, str(ROOT / "app" / "server.py"), "--host", args.host, "--port", str(args.port)]
    if not args.no_open:
        command.append("--open")
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
