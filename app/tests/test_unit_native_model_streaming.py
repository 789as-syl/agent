
from __future__ import annotations

from types import SimpleNamespace

from app.agents.runtime.native_model import _is_generation_stream_final, _message_field


class _RaisesKeyErrorOnMissing:
    def __init__(self) -> None:
        self.output = SimpleNamespace()

    def __getattr__(self, name: str):
        raise KeyError(name)


def test_generation_stream_final_probe_ignores_keyerror_style_missing_attrs() -> None:
    response = _RaisesKeyErrorOnMissing()

    assert _is_generation_stream_final(response) is False


def test_message_field_ignores_keyerror_style_missing_attrs() -> None:
    value = _RaisesKeyErrorOnMissing()

    assert _message_field(value, "is_end") is None
