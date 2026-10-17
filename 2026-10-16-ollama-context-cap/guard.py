"""Client-side guard: notice when the server quietly cut the conversation.

Ollama reports how many prompt tokens it actually processed
(`usage.prompt_tokens` on /v1, `prompt_eval_count` on /api/chat). Two cheap
signals show that history was cut, with no tokenizer needed:

1. Growth: within one conversation, every turn adds messages, so the
   processed prompt must grow. If it stays flat or falls while you sent
   more messages, the server dropped earlier ones.
2. Headroom: if you know the window the model was loaded with (Ollama's
   /api/ps reports `context_length`), a prompt above `ceiling` (default 75%)
   of it means you are at the edge: the next turn will be cut.

A character-count estimate is NOT used: dense text such as logs, hex IDs and
code runs at 2-3 characters per token, so "characters / 4" under-counts and
would miss the cut (see README).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ContextTruncated(RuntimeError):
    pass


@dataclass
class TruncationGuard:
    context_length: int | None = None   # from /api/ps, if you can read it
    ceiling: float = 0.75
    raise_on_truncation: bool = True
    _last_msgs: int = 0
    _last_tokens: int = 0
    warnings: list[str] = field(default_factory=list)

    def check(self, msgs: list[dict], prompt_tokens: int) -> list[str]:
        found = []
        if self._last_msgs and len(msgs) > self._last_msgs and prompt_tokens <= self._last_tokens:
            found.append(
                f"truncated: prompt_tokens {self._last_tokens} -> {prompt_tokens} "
                f"while messages grew {self._last_msgs} -> {len(msgs)}"
            )
        if self.context_length and prompt_tokens > self.context_length * self.ceiling:
            found.append(
                f"near limit: {prompt_tokens} of {self.context_length} context tokens used"
            )
        self._last_msgs, self._last_tokens = len(msgs), prompt_tokens
        self.warnings += found
        if found and self.raise_on_truncation and found[0].startswith("truncated"):
            raise ContextTruncated(found[0])
        return found
