from __future__ import annotations

from app.services.retrieval.retrieval_service import RetrievalService


def test_question_results_project_to_evidence_without_raw_protocol() -> None:
    blocks = RetrievalService._question_results_to_evidence([
        {
            "question_id": "11111111-1111-1111-1111-111111111111",
            "question_text": "1+1=?",
            "question_type": "single",
            "options": [{"label": "A", "text": "2"}],
            "answer": "A",
            "explanation": "basic math",
            "similarity": 0.9,
        }
    ])

    assert blocks[0]["evidence_block_id"].startswith("question::")
    assert blocks[0]["group_type"] == "question"
    assert "答案：A" in blocks[0]["content"]
    assert "provider_payload" not in str(blocks)
