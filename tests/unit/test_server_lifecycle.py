from __future__ import annotations

from xa_guard.config import XAGuardConfig
from xa_guard.server import build_pipeline


def test_build_pipeline_only_starts_overlay_watcher_when_requested(monkeypatch) -> None:
    starts = 0

    class FakeWatcher:
        def __init__(self, _source, _overlay_root) -> None:
            pass

        def start(self) -> bool:
            nonlocal starts
            starts += 1
            return True

    monkeypatch.setattr("xa_guard.server.OverlayWatcher", FakeWatcher)
    cfg = XAGuardConfig.from_yaml("configs/xa-guard.yaml")

    passive = build_pipeline(cfg)
    active = build_pipeline(cfg, start_overlay_watcher=True)

    assert passive.overlay_watcher is None
    assert isinstance(active.overlay_watcher, FakeWatcher)
    assert starts == 1
