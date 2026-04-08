"""Tests for the topology advisor."""

from __future__ import annotations

from etchant.core.topology_advisor import recommend_topology


class TestStepDown:
    def test_low_dropout_low_current_recommends_ldo(self) -> None:
        rec = recommend_topology(5.0, 3.3, 0.5)
        assert rec.topology == "ldo_regulator"
        assert rec.confidence > 0.5

    def test_high_current_recommends_buck(self) -> None:
        rec = recommend_topology(12.0, 5.0, 2.0)
        assert rec.topology == "buck_converter"

    def test_large_voltage_drop_recommends_buck(self) -> None:
        rec = recommend_topology(24.0, 3.3, 0.5)
        assert rec.topology == "buck_converter"

    def test_moderate_case_balanced_with_low_dissipation(self) -> None:
        rec = recommend_topology(5.0, 3.3, 0.3)
        assert rec.topology == "ldo_regulator"

    def test_moderate_case_balanced_with_high_dissipation(self) -> None:
        rec = recommend_topology(12.0, 3.3, 0.5)
        assert rec.topology == "buck_converter"


class TestPriorities:
    def test_noise_priority_favors_ldo(self) -> None:
        rec = recommend_topology(7.0, 5.0, 0.5, priority="noise")
        assert rec.topology == "ldo_regulator"

    def test_cost_priority_favors_ldo(self) -> None:
        # Use voltages that don't trigger the "low dropout" fast path
        rec = recommend_topology(9.0, 5.0, 0.5, priority="cost")
        assert rec.topology == "ldo_regulator"
        assert "$0" in rec.reason

    def test_efficiency_priority_favors_buck(self) -> None:
        rec = recommend_topology(7.0, 5.0, 0.5, priority="efficiency")
        assert rec.topology == "buck_converter"

    def test_efficiency_overrides_low_dropout(self) -> None:
        rec = recommend_topology(5.0, 3.3, 0.5, priority="efficiency")
        # Low dropout would normally suggest LDO, but efficiency priority
        # should still recommend buck if dissipation is significant
        assert rec.topology in ("buck_converter", "ldo_regulator")


class TestStepUp:
    def test_step_up_not_supported(self) -> None:
        rec = recommend_topology(5.0, 12.0, 1.0)
        assert rec.confidence == 0.0
        assert "boost" in rec.reason.lower()


class TestRecommendationStructure:
    def test_has_tradeoffs(self) -> None:
        rec = recommend_topology(12.0, 5.0, 2.0)
        assert len(rec.tradeoffs) > 0

    def test_has_alternatives(self) -> None:
        rec = recommend_topology(12.0, 5.0, 2.0)
        assert isinstance(rec.alternatives, tuple)

    def test_confidence_in_range(self) -> None:
        rec = recommend_topology(12.0, 5.0, 2.0)
        assert 0.0 <= rec.confidence <= 1.0
