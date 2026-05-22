"""DecisionLog — JSON-lines append-only writer."""

import json
from decimal import Decimal
from pathlib import Path

from arbitrage_agent.domain import (
    ExchangeId,
    Fill,
    Opportunity,
    OrderIntent,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.persistence.decision_log import (
    GENESIS_HASH,
    DecisionLog,
    verify_chain,
)


def _intent() -> OrderIntent:
    return OrderIntent(
        exchange=ExchangeId("paper"),
        symbol=Symbol("BTC", "USDT"),
        side="buy",
        quantity=volume("0.001"),
        limit_price=price("60000"),
    )


def _opp() -> Opportunity:
    return Opportunity(
        id=new_opportunity_id(),
        detected_at=now_utc(),
        strategy="spatial",
        legs=(_intent(),),
        expected_net_profit=Decimal("0.75"),
        confidence=0.9,
        valid_for_ms=1000,
    )


def test_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "deep" / "nested" / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    assert p.exists()


def test_writes_one_line_per_event(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    log.append_decision(RiskDecision(
        opportunity_id=new_opportunity_id(),
        approved=True, reason="ok",
    ))
    lines = p.read_text().splitlines()
    assert len(lines) == 2


def test_appended_lines_are_valid_json(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    log.append_decision(RiskDecision(
        opportunity_id=new_opportunity_id(),
        approved=False, reason="kill_switch_engaged",
    ))
    for line in p.read_text().splitlines():
        json.loads(line)  # raises on invalid JSON


def test_event_field_distinguishes_types(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    opp = _opp()
    log.append_opportunity(opp)
    log.append_decision(RiskDecision(
        opportunity_id=opp.id, approved=True, reason="ok",
    ))
    log.append_fill(Fill(
        opportunity_id=opp.id,
        exchange=ExchangeId("paper"),
        symbol=Symbol("BTC", "USDT"),
        side="buy",
        price=price("60000"),
        volume=volume("0.001"),
        fee=price("0.06"),
        timestamp_utc=now_utc(),
    ))
    events = [json.loads(line)["event"] for line in p.read_text().splitlines()]
    assert events == ["opportunity_detected", "risk_decision", "fill"]


def test_decimal_serialized_as_string(tmp_path: Path):
    """Decimal goes through `default=str` so audit numbers round-trip
    cleanly with no float precision loss."""
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    line = json.loads(p.read_text().splitlines()[0])
    assert line["expected_net_profit_usd"] == "0.75"


def test_appends_not_overwrites(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    log2 = DecisionLog(p)
    log2.append_opportunity(_opp())
    assert len(p.read_text().splitlines()) == 2


# ---- Faz 7g-b: hash chain --------------------------------------------------


def test_first_line_uses_genesis_prev_hash(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    entry = json.loads(p.read_text().splitlines()[0])
    assert entry["_prev_hash"] == GENESIS_HASH
    assert isinstance(entry["_hash"], str) and len(entry["_hash"]) == 64


def test_subsequent_lines_link_via_prev_hash(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    opp = _opp()
    log.append_opportunity(opp)
    log.append_decision(RiskDecision(
        opportunity_id=opp.id, approved=True, reason="ok",
    ))
    a, b = (json.loads(line) for line in p.read_text().splitlines())
    assert b["_prev_hash"] == a["_hash"]
    assert a["_hash"] != b["_hash"]


def test_chain_continues_across_processes(tmp_path: Path):
    """Re-opening the log MUST pick up `last_hash` from the file tail
    so a restart doesn't restart the chain at GENESIS."""
    p = tmp_path / "decisions.jsonl"
    log1 = DecisionLog(p)
    log1.append_opportunity(_opp())
    first_hash = log1.last_hash

    log2 = DecisionLog(p)
    assert log2.last_hash == first_hash
    log2.append_opportunity(_opp())

    lines = [json.loads(line) for line in p.read_text().splitlines()]
    assert lines[1]["_prev_hash"] == first_hash


def test_verify_chain_passes_on_clean_log(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    for _ in range(5):
        log.append_opportunity(_opp())
    ok, message, lines = verify_chain(p)
    assert ok is True, message
    assert lines == 5


def test_verify_chain_detects_content_tamper(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    log.append_opportunity(_opp())

    # Mutate the first line's payload but keep its `_hash` intact —
    # recomputing should reveal the mismatch.
    raw = p.read_text().splitlines()
    entry = json.loads(raw[0])
    entry["confidence"] = 0.0001
    raw[0] = json.dumps(entry, sort_keys=True, default=str)
    p.write_text("\n".join(raw) + "\n")

    ok, message, line_no = verify_chain(p)
    assert ok is False
    assert "tampered" in message or "_hash mismatch" in message
    assert line_no == 1


def test_verify_chain_detects_deleted_line(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())
    log.append_opportunity(_opp())
    log.append_opportunity(_opp())

    raw = p.read_text().splitlines()
    del raw[1]  # delete the middle line
    p.write_text("\n".join(raw) + "\n")

    ok, message, line_no = verify_chain(p)
    assert ok is False
    assert "_prev_hash mismatch" in message
    assert line_no == 2


def test_verify_chain_detects_missing_hash_field(tmp_path: Path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append_opportunity(_opp())

    raw = p.read_text().splitlines()
    entry = json.loads(raw[0])
    entry.pop("_hash")
    raw[0] = json.dumps(entry, sort_keys=True, default=str)
    p.write_text("\n".join(raw) + "\n")

    ok, message, line_no = verify_chain(p)
    assert ok is False
    assert "_hash" in message
    assert line_no == 1


def test_verify_chain_handles_missing_file(tmp_path: Path):
    ok, message, lines = verify_chain(tmp_path / "nope.jsonl")
    assert ok is False
    assert "not found" in message
    assert lines == 0
