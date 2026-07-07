import team_registry
from team_registry import (
    CANONICAL_TEAM_NAMES,
    HUB_TO_CANONICAL,
    TEAM_LOCATIONS,
    TEAMS_INFO_PATH,
    load_teams,
)


def test_teams_info_path_is_absolute_and_exists():
    # Must work regardless of the caller's working directory.
    assert TEAMS_INFO_PATH.is_absolute()
    assert TEAMS_INFO_PATH.exists()


def test_registry_is_single_source_for_short_names_and_aliases():
    teams = load_teams()
    for name, info in teams.items():
        assert info.get("short"), f"{name} missing 'short'"
        assert isinstance(info.get("aliases"), list), f"{name} missing 'aliases'"


def test_hub_to_canonical_maps_every_canonical_name_to_itself():
    for name in CANONICAL_TEAM_NAMES:
        assert HUB_TO_CANONICAL[name] == name


def test_hub_to_canonical_includes_legacy_hub_spellings():
    assert HUB_TO_CANONICAL["Indianapolis Red"] == "Indy Red"
    assert HUB_TO_CANONICAL["Nashville Nightshade"] == "Nashville NightShade"


def test_team_locations_still_derived():
    assert TEAM_LOCATIONS["Atlanta Soul"] == "Atlanta, GA"
    assert TEAM_LOCATIONS["Medellin Revolution"] == "Medellin, Colombia"
