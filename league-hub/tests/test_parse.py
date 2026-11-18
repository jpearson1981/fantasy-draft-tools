from league_hub.yahoo.parse import parse_league_settings, parse_teams, parse_user_leagues

from .fixtures import USER_LEAGUES, settings_payload, teams_payload


def test_user_leagues_across_seasons_sorted_newest_first():
    leagues = parse_user_leagues(USER_LEAGUES)
    assert [(l["league_key"], l["season"]) for l in leagues] == [
        ("461.l.222", 2025), ("461.l.111", 2025), ("449.l.333", 2024)]
    assert leagues[1]["num_teams"] == 10


def test_settings_roster_and_flex_mapping():
    s = parse_league_settings(settings_payload())
    assert s["roster"] == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1, "BN": 6, "IR": 1}
    assert s["roster_spots"] == 15          # IR excluded
    assert s["starters"] == 9               # BN and IR excluded
    assert s["num_teams"] == 10 and s["season"] == 2025


def test_settings_superflex_and_auction_and_draft_mode():
    s = parse_league_settings(settings_payload(auction=True, draft_type="offline",
                                               positions=[("QB", 1), ("Q/W/R/T", 1), ("BN", 7)]))
    assert s["roster"]["SUPERFLEX"] == 1
    assert s["draft_type"] == "auction"
    assert s["draft_mode"] == "offline"
    live = parse_league_settings(settings_payload(draft_type="live"))
    assert live["draft_type"] == "snake" and live["draft_mode"] == "online"


def test_settings_scoring_joined_with_stat_names():
    s = parse_league_settings(settings_payload())
    by_name = {x["name"]: x["value"] for x in s["scoring"]}
    assert by_name == {"Pass Yds": 0.04, "Pass TD": 4.0, "Rec": 0.5}


def test_settings_renew_key_points_to_previous_season():
    assert parse_league_settings(settings_payload())["renew_key"] == "449.l.333"
    assert parse_league_settings(settings_payload(renew=""))["renew_key"] is None


def test_teams_owners_hidden_guid_and_is_mine():
    teams = {t["team_key"]: t for t in parse_teams(teams_payload())}
    assert len(teams) == 4
    me = teams["461.l.111.t.1"]
    assert me["is_mine"] and me["owner_external_id"] == "GUID_ME" and me["owner_name"] == "Jeff"
    assert not teams["461.l.111.t.2"]["is_mine"]
    # Hidden guid with no usable nickname -> no owner identity (cannot be tracked)
    assert teams["461.l.111.t.3"]["owner_external_id"] is None
    assert teams["461.l.111.t.3"]["owner_name"] is None
    # Hidden guid but a real nickname -> falls back to nickname identity
    assert teams["461.l.111.t.4"]["owner_external_id"] == "nick:Sam"


def test_missing_fields_do_not_crash():
    assert parse_user_leagues({}) == []
    assert parse_teams({"fantasy_content": {}}) == []
