from __future__ import annotations

from app.context import ContextBuilder, estimate_tokens
from app.settings import Settings
from app.store import ConversationStore


def test_estimate_tokens_is_stable() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_compaction_preserves_transcript_and_advances_cursor(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "context.db",
        context_token_budget=240,
        context_reserved_output_tokens=64,
        context_recent_messages=4,
        summary_max_characters=300,
        system_prompt="Be concise.",
    )
    store = ConversationStore(settings.database_path)
    store.initialize()
    thread = store.create_thread("owner", "Long thread")

    for index in range(8):
        role = "user" if index % 2 == 0 else "assistant"
        store.add_message(
            thread.id,
            role,
            f"Turn {index}: " + ("context detail " * 8),
        )

    prepared = ContextBuilder(settings).prepare(store, thread)
    updated = store.get_thread_detail("owner", thread.id)

    assert prepared.info.compacted is True
    assert prepared.info.summarized_through_position == 3
    assert updated is not None
    assert len(updated.messages) == 8
    assert updated.summary
    assert updated.summarized_through_position == 3
    assert len(prepared.messages) <= 6  # system, summary, and four recent messages
