"""watchfiles 热加载：监听 overlay/ 目录变更，触发 LayeredPolicySource.reload()。

设计要点：
- 只监听 overlay/，baseline 运行时只读（防止线上被改）
- 失败保留旧 snapshot，写一条 audit 告警；不抛出
- watchfiles 不可用时 fail-safe：自动降级为 noop（运维仍可手动调 source.reload()）

启动方式：xa-guard CLI / pipeline 启动期；线程后台跑，无 asyncio 依赖。
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from xa_guard.policy.layered import LayeredPolicySource

log = logging.getLogger("xa_guard.policy.hot_reload")

try:
    from watchfiles import watch  # type: ignore

    _HAS_WATCHFILES = True
except Exception:  # pragma: no cover
    watch = None  # type: ignore
    _HAS_WATCHFILES = False


class OverlayWatcher:
    """单线程 watchfiles 监听器；可 start() / stop()。"""

    def __init__(
        self,
        source: LayeredPolicySource,
        overlay_root: str | Path,
        *,
        on_reload: Callable[[bool], None] | None = None,
    ) -> None:
        self.source = source
        self.overlay_root = Path(overlay_root)
        self.on_reload = on_reload
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return _HAS_WATCHFILES and self.overlay_root.exists()

    def start(self) -> bool:
        if not self.available:
            log.info(
                "OverlayWatcher disabled (watchfiles=%s, overlay_root_exists=%s)",
                _HAS_WATCHFILES, self.overlay_root.exists(),
            )
            return False
        if self._thread is not None:
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="xa-guard-overlay-watcher",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:  # pragma: no cover - 依赖文件系统事件
        log.info("OverlayWatcher watching %s", self.overlay_root)
        try:
            for _changes in watch(  # type: ignore[misc]
                str(self.overlay_root),
                stop_event=self._stop_event,
                recursive=True,
                debounce=300,
            ):
                ok = self.source.reload()
                old_sha = self.source.bundle_sha[:12]
                if ok:
                    log.info("overlay reload OK; new bundle_sha=%s", old_sha)
                else:
                    log.warning("overlay reload rejected; keeping previous snapshot")
                if self.on_reload is not None:
                    try:
                        self.on_reload(ok)
                    except Exception:
                        log.exception("on_reload callback failed")
        except Exception:
            log.exception("OverlayWatcher crashed; hot reload disabled")
