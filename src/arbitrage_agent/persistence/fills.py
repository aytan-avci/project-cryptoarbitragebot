"""SQLite-backed fill store. Faz 4 skeleton; schema + writer in Faz 5+."""

from arbitrage_agent.domain import Fill


class FillStore:
    def record(self, fill: Fill) -> None:
        raise NotImplementedError("FillStore.record — Faz 5+")
