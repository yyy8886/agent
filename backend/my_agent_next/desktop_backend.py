"""Standalone desktop backend entry point used by PyInstaller."""

from __future__ import annotations

import os
import sys
import traceback

from my_agent_next.app.runtime_paths import DATA_DIR, initialize_runtime


def _configure_packaged_logging():
    """Give windowed PyInstaller builds real streams and a diagnostic log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(DATA_DIR / "backend.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    return log


def main() -> None:
    initialize_runtime()
    log = _configure_packaged_logging()
    import uvicorn

    host = os.environ.get("MY_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("MY_AGENT_PORT", "19845"))
    try:
        uvicorn.run(
            "my_agent_next.app.web_server:app",
            host=host,
            port=port,
            reload=False,
        )
    except BaseException:
        traceback.print_exc(file=log)
        raise


if __name__ == "__main__":
    main()
