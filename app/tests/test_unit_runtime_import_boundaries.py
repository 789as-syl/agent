from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".." / "app"


def test_deleted_runtime_shells_are_absent() -> None:
    for path in [
        ROOT / "agents" / "react_agent.py",
        ROOT / "agents" / "react_planner.py",
        ROOT / "agents" / "react_generator.py",
        ROOT / "agents" / "agent_state.py",
        ROOT / "agents" / "trace_projector.py",
        ROOT / "agents" / "checkpoint_codec.py",
        ROOT / "agents" / "compat" / "legacy_runtime.py",
        ROOT / "tools" / "policy.py",
    ]:
        assert not path.exists(), f"legacy runtime shell still exists: {path}"
