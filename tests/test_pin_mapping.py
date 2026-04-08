"""Tests for the pin mapping layer."""

from __future__ import annotations

from etchant.kicad.pin_mapping import get_pin_name, has_pin_mapping, list_mapped_ics


class TestGetPinName:
    def test_lm2596_vin(self) -> None:
        assert get_pin_name("LM2596S-5", "VIN") == "VIN"

    def test_lm2596_sw(self) -> None:
        assert get_pin_name("LM2596S-5", "SW") == "OUT"

    def test_lm2596_on_off(self) -> None:
        assert get_pin_name("LM2596S-5", "ON_OFF") == "~{ON}/OFF"

    def test_ams1117_vin(self) -> None:
        assert get_pin_name("AMS1117-3.3", "VIN") == "VI"

    def test_ams1117_vout(self) -> None:
        assert get_pin_name("AMS1117-3.3", "VOUT") == "VO"

    def test_tps563200_sw(self) -> None:
        assert get_pin_name("TPS563200", "SW") == "SW"

    def test_tps564257_gnd(self) -> None:
        assert get_pin_name("TPS564257", "GND") == "PGND"

    def test_unknown_ic_returns_generic(self) -> None:
        result = get_pin_name("UNKNOWN_IC_XYZ", "VIN")
        assert result == "VIN"

    def test_prefix_matching(self) -> None:
        """TPS564255B should match TPS564255 mapping."""
        assert get_pin_name("TPS564255B", "GND") == "PGND"


class TestHasPinMapping:
    def test_known_ic(self) -> None:
        assert has_pin_mapping("LM2596S-5")

    def test_unknown_ic(self) -> None:
        assert not has_pin_mapping("TOTALLY_UNKNOWN_IC")

    def test_prefix_match(self) -> None:
        assert has_pin_mapping("TPS564257DRLR")


class TestListMappedICs:
    def test_returns_list(self) -> None:
        ics = list_mapped_ics()
        assert len(ics) > 5
        assert "LM2596S-5" in ics
        assert "AMS1117-3.3" in ics
        assert "TPS563200" in ics
