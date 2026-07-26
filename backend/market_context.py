import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


LOGGER = logging.getLogger(__name__)
CONTEXT_FILE = Path(__file__).with_name("market_context.json")
NEPAL_TIMEZONE = timezone(timedelta(hours=5, minutes=45))
ALLOWED_SCOPES = {"MARKET", "SYMBOL"}
IMPACT_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def nepal_today() -> date:
    return datetime.now(NEPAL_TIMEZONE).date()


def _parse_date(value, field_name, required=True):
    if not value:
        if required:
            raise ValueError(f"{field_name} is required")
        return None

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from exc


def load_context_entries(path=CONTEXT_FILE):
    with Path(path).open("r", encoding="utf-8") as context_file:
        data = json.load(context_file)

    if not isinstance(data, list):
        raise ValueError("market_context.json must contain a JSON array")
    return data


def _normalise_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("Each market context entry must be a JSON object")

    scope = str(entry.get("scope", "")).upper()
    if scope not in ALLOWED_SCOPES:
        raise ValueError("scope must be MARKET or SYMBOL")

    symbol = str(entry.get("symbol", "")).strip().upper() or None
    if scope == "SYMBOL" and not symbol:
        raise ValueError("symbol is required when scope is SYMBOL")

    published_at = _parse_date(entry.get("published_at"), "published_at")
    expires_at = _parse_date(entry.get("expires_at"), "expires_at", required=False)
    if expires_at and expires_at < published_at:
        raise ValueError("expires_at cannot be earlier than published_at")

    required_text_fields = ("id", "headline", "message", "verdict_message")
    for field_name in required_text_fields:
        if not str(entry.get(field_name, "")).strip():
            raise ValueError(f"{field_name} is required")

    impact = str(entry.get("impact", "MEDIUM")).upper()
    if impact not in IMPACT_ORDER:
        raise ValueError("impact must be LOW, MEDIUM, or HIGH")

    return {
        "id": str(entry["id"]).strip(),
        "scope": scope,
        "symbol": symbol,
        "headline": str(entry["headline"]).strip(),
        "message": str(entry["message"]).strip(),
        "stance": str(entry.get("stance", "NEUTRAL")).upper(),
        "impact": impact,
        "priority": int(entry.get("priority", 0)),
        "verdict_label": str(
            entry.get("verdict_label", "CONTEXT REVIEWED")
        ).strip(),
        "verdict_message": str(entry["verdict_message"]).strip(),
        "source_label": str(entry.get("source_label", "")).strip() or None,
        "source_url": str(entry.get("source_url", "")).strip() or None,
        "published_at": published_at,
        "expires_at": expires_at,
        "reviewed_by": str(entry.get("reviewed_by", "")).strip() or None,
        "status": str(entry.get("status", "DRAFT")).upper(),
    }


def select_active_context(entries, symbol, as_of=None):
    selected_symbol = symbol.strip().upper()
    effective_date = as_of or nepal_today()
    selected = []

    for raw_entry in entries:
        entry = _normalise_entry(raw_entry)

        if entry["status"] != "PUBLISHED":
            continue
        if entry["published_at"] > effective_date:
            continue
        if entry["expires_at"] and entry["expires_at"] < effective_date:
            continue
        if entry["scope"] == "SYMBOL" and entry["symbol"] != selected_symbol:
            continue

        selected.append(entry)

    selected.sort(
        key=lambda item: (
            item["priority"],
            IMPACT_ORDER[item["impact"]],
            item["published_at"],
        ),
        reverse=True,
    )

    return [
        {
            **entry,
            "published_at": entry["published_at"].isoformat(),
            "expires_at": (
                entry["expires_at"].isoformat() if entry["expires_at"] else None
            ),
        }
        for entry in selected
    ]


def resolve_market_context(symbol, as_of=None):
    effective_date = as_of or nepal_today()

    try:
        entries = load_context_entries()
        items = select_active_context(entries, symbol, effective_date)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        LOGGER.warning("Market context could not be loaded: %s", exc)
        return {
            "status": "unavailable",
            "as_of": effective_date.isoformat(),
            "symbol": symbol.strip().upper(),
            "supported_scopes": ["MARKET", "SYMBOL"],
            "items": [],
            "message": "Developer-reviewed market context is temporarily unavailable.",
        }

    return {
        "status": "active" if items else "empty",
        "as_of": effective_date.isoformat(),
        "symbol": symbol.strip().upper(),
        "supported_scopes": ["MARKET", "SYMBOL"],
        "items": items,
        "message": (
            None
            if items
            else "No active developer-reviewed market context applies to this symbol."
        ),
    }


def build_contextual_verdict(technical_verdict, context_items):
    if not context_items:
        return None

    lead_context = context_items[0]
    return {
        "label": lead_context["verdict_label"],
        "message": lead_context["verdict_message"],
        "technical_action": technical_verdict.get("action"),
        "based_on_context_id": lead_context["id"],
        "disclosure": (
            "Current developer-reviewed context is applied after the historical "
            "test and was not part of the backtest."
        ),
    }
