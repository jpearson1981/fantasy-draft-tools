"""Turn Yahoo Fantasy API JSON into a platform-neutral shape.

Yahoo's JSON is awkward: collections are dicts keyed "0","1",... plus "count", and a single
resource is often a *list* of small dicts that must be merged. These helpers are deliberately
tolerant of missing fields. The full raw payload is also stored by the caller, so anything we
fail to interpret is never lost.
"""
from __future__ import annotations

from typing import Any, Iterator

# Yahoo roster position codes -> neutral names used throughout the app.
POSITION_MAP = {
    "W/R/T": "FLEX",          # RB/WR/TE
    "W/R": "FLEX_WR_RB",
    "W/T": "FLEX_WR_TE",
    "Q/W/R/T": "SUPERFLEX",   # QB/RB/WR/TE
    "BN": "BN",
    "IR": "IR",
    "IR+": "IR",
    "NA": "NA",
}
NON_ROSTER_SLOTS = {"IR", "NA"}  # do not count toward drafted roster size
NON_STARTER_SLOTS = {"BN", "IR", "NA"}


def flatten(node: Any) -> dict:
    """Merge a dict, or a (nested) list of dicts, into one dict. Later keys win."""
    if isinstance(node, dict):
        return node
    out: dict = {}
    if isinstance(node, list):
        for el in node:
            out.update(flatten(el))
    return out


def items(node: Any) -> Iterator[Any]:
    """Iterate a Yahoo collection: a list, or a dict keyed '0','1',... (ignoring 'count')."""
    if isinstance(node, list):
        yield from node
    elif isinstance(node, dict):
        for key in sorted((k for k in node if str(k).isdigit()), key=int):
            yield node[key]


def find_all(node: Any, key: str) -> Iterator[Any]:
    """Yield the value of every `key` found anywhere in the tree (not descending into matches)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            else:
                yield from find_all(v, key)
    elif isinstance(node, list):
        for el in node:
            yield from find_all(el, key)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_user_leagues(payload: dict) -> list[dict]:
    out = []
    for league_node in find_all(payload, "league"):
        meta = flatten(league_node)
        key = meta.get("league_key")
        if not key:
            continue
        out.append(
            {
                "league_key": key,
                "league_id": str(meta.get("league_id", "")),
                "name": meta.get("name", ""),
                "season": _int(meta.get("season")),
                "num_teams": _int(meta.get("num_teams")),
                "draft_status": meta.get("draft_status"),
            }
        )
    out.sort(key=lambda r: (-(r["season"] or 0), r["name"]))  # newest season first, then name
    return out


def parse_league_settings(payload: dict) -> dict:
    league_node = next(find_all(payload, "league"), None)
    if league_node is None:
        raise ValueError("No league found in Yahoo settings response")
    league = flatten(league_node)
    settings = flatten(league.get("settings", {}))

    # Roster slots
    slots: dict[str, int] = {}
    for rp in items(settings.get("roster_positions", [])):
        rp = rp.get("roster_position", rp) if isinstance(rp, dict) else {}
        pos = rp.get("position")
        if not pos:
            continue
        name = POSITION_MAP.get(pos, pos)
        slots[name] = slots.get(name, 0) + (_int(rp.get("count")) or 0)
    roster_spots = sum(c for p, c in slots.items() if p not in NON_ROSTER_SLOTS)
    starters = sum(c for p, c in slots.items() if p not in NON_STARTER_SLOTS)

    # Scoring: join stat definitions with their point modifiers
    definitions: dict[str, dict] = {}
    for st in items(flatten(settings.get("stat_categories", {})).get("stats", [])):
        st = st.get("stat", st) if isinstance(st, dict) else {}
        if "stat_id" in st:
            definitions[str(st["stat_id"])] = st
    scoring = []
    for st in items(flatten(settings.get("stat_modifiers", {})).get("stats", [])):
        st = st.get("stat", st) if isinstance(st, dict) else {}
        sid = str(st.get("stat_id", ""))
        if not sid:
            continue
        d = definitions.get(sid, {})
        try:
            value = float(st.get("value"))
        except (TypeError, ValueError):
            continue
        scoring.append(
            {
                "stat_id": sid,
                "name": d.get("display_name") or d.get("name") or f"stat {sid}",
                "value": value,
            }
        )

    is_auction = str(settings.get("is_auction_draft", "0")) == "1"
    yahoo_draft_type = settings.get("draft_type")  # observed values include "live"; others treated as offline
    budget = _int(settings.get("auction_budget"))

    return {
        "league_key": league.get("league_key"),
        "league_id": str(league.get("league_id", "")),
        "name": league.get("name", ""),
        "season": _int(league.get("season")),
        "num_teams": _int(league.get("num_teams")),
        "scoring_type": league.get("scoring_type"),
        "draft_status": league.get("draft_status"),
        "draft_type": "auction" if is_auction else "snake",
        "draft_mode": "online" if yahoo_draft_type == "live" else "offline",
        "roster": slots,
        "roster_spots": roster_spots,
        "starters": starters,
        "scoring": scoring,
        "auction_budget": budget,
        "renew_key": (league.get("renew") or "").replace("_", ".l.") or None,
    }


def parse_teams(payload: dict) -> list[dict]:
    teams = []
    for team_node in find_all(payload, "team"):
        t = flatten(team_node)
        key = t.get("team_key")
        if not key:
            continue
        managers = []
        for m in items(t.get("managers", [])):
            m = m.get("manager", m) if isinstance(m, dict) else {}
            if m:
                managers.append(m)
        primary = managers[0] if managers else {}
        guid = primary.get("guid")
        nickname = primary.get("nickname")
        if nickname in ("--", "--hidden--"):
            nickname = None
        if guid and guid != "--":
            owner_id = guid
        elif nickname:
            owner_id = f"nick:{nickname}"
        else:
            owner_id = None
        teams.append(
            {
                "team_key": key,
                "name": t.get("name", ""),
                "owner_external_id": owner_id,
                "owner_name": nickname,
                "is_mine": str(t.get("is_owned_by_current_login", "0")) == "1",
            }
        )
    return teams
