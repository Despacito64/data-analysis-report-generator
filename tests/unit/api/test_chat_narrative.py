"""Chat bubble narrative helper."""

from da_agent.api.chat_narrative import chat_user_narrative


def test_drill_down_preface() -> None:
    text = chat_user_narrative(
        "tell me more about furniture",
        "Furniture: 741,999.80.",
        [{"category": "Furniture", "amount": 741999.8}],
    )
    assert text is not None
    assert "Furniture" in text
    assert "741,999.80" in text
