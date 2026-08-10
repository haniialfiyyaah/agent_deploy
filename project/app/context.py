"""Bounded context construction and deterministic classroom compaction."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.schemas import ContextInfo, MessageRecord, ProviderMessage, ThreadSummary
from app.settings import Settings
from app.store import ConversationStore


class ContextOverflowError(ValueError):
    """Raised when the current request cannot fit the configured input budget."""


def estimate_tokens(text: str) -> int:
    """Return a conservative, tokenizer-independent classroom estimate."""

    if not text:
        return 0
    return max(1, ceil(len(text) / 4))


@dataclass(frozen=True)
class PreparedContext:
    messages: list[ProviderMessage]
    info: ContextInfo


class ContextBuilder:
    """Select recent context and compact older transcript into a summary."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def prepare(
        self,
        store: ConversationStore,
        thread: ThreadSummary,
    ) -> PreparedContext:
        messages = [
            message
            for message in store.list_messages(thread.id)
            if message.status == "completed"
            and message.position > thread.summarized_through_position
        ]
        compacted = False

        if self._estimate(thread.summary, messages) > self.settings.available_input_tokens:
            older = messages[: -self.settings.context_recent_messages]
            if older:
                summary = self._merge_summary(thread.summary, older)
                thread = store.update_summary(
                    thread.owner_id,
                    thread.id,
                    summary,
                    older[-1].position,
                )
                messages = messages[-self.settings.context_recent_messages :]
                compacted = True

        selected = list(messages)
        while (
            self._estimate(thread.summary, selected)
            > self.settings.available_input_tokens
            and len(selected) > 1
        ):
            selected.pop(0)

        estimated = self._estimate(thread.summary, selected)
        if estimated > self.settings.available_input_tokens:
            raise ContextOverflowError(
                "The current message and required instructions exceed the input budget."
            )

        provider_messages = [
            ProviderMessage(role="system", content=self.settings.system_prompt)
        ]
        if thread.summary:
            provider_messages.append(
                ProviderMessage(
                    role="system",
                    content=f"Earlier conversation summary:\n{thread.summary}",
                )
            )
        provider_messages.extend(
            ProviderMessage(role=message.role, content=message.content)
            for message in selected
        )
        return PreparedContext(
            messages=provider_messages,
            info=ContextInfo(
                estimated_input_tokens=estimated,
                compacted=compacted,
                summarized_through_position=thread.summarized_through_position,
                included_message_count=len(selected),
            ),
        )

    def _estimate(self, summary: str, messages: list[MessageRecord]) -> int:
        total = estimate_tokens(self.settings.system_prompt)
        total += estimate_tokens(summary)
        total += sum(estimate_tokens(message.content) + 4 for message in messages)
        return total

    def _merge_summary(self, current: str, messages: list[MessageRecord]) -> str:
        lines: list[str] = []
        if current:
            lines.append(f"Previous summary: {current}")
        for message in messages:
            compact = " ".join(message.content.split())
            if len(compact) > 240:
                compact = compact[:237] + "..."
            lines.append(f"{message.role.title()}: {compact}")
        merged = "\n".join(lines)
        if len(merged) > self.settings.summary_max_characters:
            merged = merged[-self.settings.summary_max_characters :]
            merged = "[Earlier details omitted] " + merged.lstrip()
        return merged
