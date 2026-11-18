"""Sample payloads shaped like Yahoo Fantasy API JSON (collections keyed "0","1",..., resources as
lists of dicts). Written from the documented structure, NOT captured from a live account -- the
first real import should be compared against these (see README)."""

USER_LEAGUES = {
    "fantasy_content": {
        "users": {
            "0": {
                "user": [
                    {"guid": "GUID_ME"},
                    {
                        "games": {
                            "0": {
                                "game": [
                                    {"game_key": "461", "code": "nfl", "season": "2025"},
                                    {
                                        "leagues": {
                                            "0": {"league": [{"league_key": "461.l.111", "league_id": "111",
                                                              "name": "Lone Rangers", "num_teams": 10,
                                                              "season": "2025", "draft_status": "postdraft"}]},
                                            "1": {"league": [{"league_key": "461.l.222", "league_id": "222",
                                                              "name": "Dynasty", "num_teams": 12,
                                                              "season": "2025", "draft_status": "postdraft"}]},
                                            "count": 2,
                                        }
                                    },
                                ]
                            },
                            "1": {
                                "game": [
                                    {"game_key": "449", "code": "nfl", "season": "2024"},
                                    {"leagues": {"0": {"league": [{"league_key": "449.l.333", "league_id": "333",
                                                                   "name": "Lone Rangers", "num_teams": 10,
                                                                   "season": "2024", "draft_status": "postdraft"}]},
                                                 "count": 1}},
                                ]
                            },
                            "count": 2,
                        }
                    },
                ]
            },
            "count": 1,
        }
    }
}


def _positions(pairs):
    d = {str(i): {"roster_position": {"position": p, "position_type": "O", "count": c}}
         for i, (p, c) in enumerate(pairs)}
    d["count"] = len(pairs)
    return d


def settings_payload(league_key="461.l.111", league_id="111", name="Lone Rangers", num_teams=10,
                     auction=False, draft_type="live", renew="449_333", positions=None):
    positions = positions or [("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("W/R/T", 1),
                              ("K", 1), ("DEF", 1), ("BN", 6), ("IR", 1)]
    return {
        "fantasy_content": {
            "league": [
                {"league_key": league_key, "league_id": league_id, "name": name,
                 "num_teams": num_teams, "season": "2025", "scoring_type": "head",
                 "draft_status": "predraft", "renew": renew},
                {
                    "settings": [
                        {
                            "draft_type": draft_type,
                            "is_auction_draft": "1" if auction else "0",
                            "roster_positions": _positions(positions),
                            "stat_categories": {"stats": [
                                {"stat": {"stat_id": 4, "name": "Passing Yards", "display_name": "Pass Yds"}},
                                {"stat": {"stat_id": 5, "name": "Passing Touchdowns", "display_name": "Pass TD"}},
                                {"stat": {"stat_id": 11, "name": "Receptions", "display_name": "Rec"}},
                            ]},
                            "stat_modifiers": {"stats": [
                                {"stat": {"stat_id": 4, "value": "0.04"}},
                                {"stat": {"stat_id": 5, "value": "4"}},
                                {"stat": {"stat_id": 11, "value": "0.5"}},
                            ]},
                        }
                    ]
                },
            ]
        }
    }


def teams_payload(my_index=0):
    def team(i, key, name, guid, nick):
        row = [
            {"team_key": key}, {"team_id": str(i + 1)}, {"name": name},
            [],  # Yahoo sprinkles empty lists between fields
            {"managers": [{"manager": {"manager_id": str(i + 1), "nickname": nick, "guid": guid}}]},
        ]
        if i == my_index:
            row.append({"is_owned_by_current_login": 1})
        return {"team": [row]}

    teams = {
        "0": team(0, "461.l.111.t.1", "Gridiron Gurus", "GUID_ME", "Jeff"),
        "1": team(1, "461.l.111.t.2", "Blitz Krieg", "GUID_BOB", "Bob"),
        "2": team(2, "461.l.111.t.3", "Mystery Team", "--", "--hidden--"),
        "3": team(3, "461.l.111.t.4", "Nick Only", "--", "Sam"),
        "count": 4,
    }
    return {"fantasy_content": {"league": [{"league_key": "461.l.111"}, {"teams": teams}]}}
