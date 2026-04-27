"""异步任务模块：async_runner。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop and _thread and _thread.is_alive() and not _loop.is_closed():
            return _loop

        ready = threading.Event()
        holder: dict[str, asyncio.AbstractEventLoop] = {}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["loop"] = loop
            ready.set()
            loop.run_forever()

        _thread = threading.Thread(target=_runner, name="celery-async-runner", daemon=True)
        _thread.start()
        ready.wait(timeout=5)
        loop = holder.get("loop")
        if loop is None:
            raise RuntimeError("Failed to initialize Celery async runner loop")
        _loop = loop
        return loop


def run_coroutine_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute coroutine on the dedicated loop and block for result."""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

