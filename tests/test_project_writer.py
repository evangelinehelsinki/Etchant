"""Tests for the KiCad project writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.models import CircuitSpec
from etchant.kicad.project_writer import ProjectWriter, _sanitize_name


class TestProjectWriter:
    def _make_design(self, spec: CircuitSpec):  # type: ignore[no-untyped-def]
        return LM2596BuckConverter().generate(spec)

    def test_write_creates_project_dir(
        self, tmp_path: Path, lm2596_spec: CircuitSpec
    ) -> None:
        design = self._make_design(lm2596_spec)
        netlist = tmp_path / "dummy.net"
        netlist.write_text("<netlist/>")

        writer = ProjectWriter(tmp_path / "output")
        pro_path = writer.write_project(design, netlist)

        assert pro_path.exists()
        assert pro_path.suffix == ".kicad_pro"

    def test_write_copies_netlist(
        self, tmp_path: Path, lm2596_spec: CircuitSpec
    ) -> None:
        design = self._make_design(lm2596_spec)
        netlist = tmp_path / "test.net"
        netlist.write_text("<netlist/>")

        writer = ProjectWriter(tmp_path / "output")
        pro_path = writer.write_project(design, netlist)

        copied_netlist = pro_path.parent / "test.net"
        assert copied_netlist.exists()

    def test_write_pro_is_valid_json(
        self, tmp_path: Path, lm2596_spec: CircuitSpec
    ) -> None:
        design = self._make_design(lm2596_spec)
        netlist = tmp_path / "test.net"
        netlist.write_text("<netlist/>")

        writer = ProjectWriter(tmp_path / "output")
        pro_path = writer.write_project(design, netlist)

        with open(pro_path) as f:
            data = json.load(f)
        assert "meta" in data
        assert data["meta"]["version"] == 1

    def test_write_design_notes(
        self, tmp_path: Path, lm2596_spec: CircuitSpec
    ) -> None:
        design = self._make_design(lm2596_spec)
        netlist = tmp_path / "test.net"
        netlist.write_text("<netlist/>")

        writer = ProjectWriter(tmp_path / "output")
        pro_path = writer.write_project(design, netlist)

        notes_path = pro_path.parent / "design_notes.txt"
        assert notes_path.exists()
        content = notes_path.read_text()
        assert "buck_converter" in content


class TestSanitizeNameEdgeCases:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="empty sanitized name"):
            _sanitize_name("")

    def test_only_special_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="empty sanitized name"):
            _sanitize_name("@#$%")


class TestSanitizeName:
    def test_simple_name(self) -> None:
        assert _sanitize_name("test") == "test"

    def test_spaces_become_underscores(self) -> None:
        assert _sanitize_name("my project") == "my_project"

    def test_special_chars(self) -> None:
        result = _sanitize_name("12V/5V@2A")
        assert "/" not in result
        assert "@" not in result

    def test_lowercase(self) -> None:
        assert _sanitize_name("MyProject") == "myproject"
