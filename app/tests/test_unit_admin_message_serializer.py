from __future__ import annotations

from uuid import uuid4

from app.models.message import Message
from app.services.admin_user_service import serialize_admin_message


def test_serialize_admin_message_exposes_only_minimal_fields() -> None:
    reply_id = uuid4()
    message = Message(
        id=uuid4(),
        conversation_id=uuid4(),
        role="assistant",
        content="hello",
        metadata_json={"reply_to_message_id": str(reply_id), "thinking_steps": [{"title": "legacy"}]},
    )

    payload = serialize_admin_message(message).model_dump(mode="python")

    assert payload["reply_to_message_id"] == reply_id
    assert "thinking_steps" not in payload
