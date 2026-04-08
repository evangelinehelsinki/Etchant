"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from etchant.cli import cli


class TestCliGroup:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Etchant" in result.output

    def test_no_subcommand_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "generate" in result.output


class TestGenerate:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "power supply" in result.output

    def test_default_invocation(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["generate", "-o", "./test_output"])
            assert result.exit_code == 0
            assert "Components: 6" in result.output

    def test_validation_pass(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["generate", "-o", "./out", "--validate"])
            assert result.exit_code == 0
            assert "PASS" in result.output

    def test_no_validate(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["generate", "-o", "./out", "--no-validate"])
            assert result.exit_code == 0
            assert "Validation" not in result.output

    def test_custom_voltages(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["generate", "-o", "./out", "-vin", "24", "-vout", "5", "-i", "1.5"]
            )
            assert result.exit_code == 0
            assert "Components: 6" in result.output

    def test_step_up_fails(self) -> None:
        """Buck converter should reject step-up (Vout > Vin)."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["generate", "-o", "./out", "-vin", "5", "-vout", "12", "-i", "1"]
            )
            assert result.exit_code != 0

    def test_ldo_topology(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["generate", "-t", "ldo_regulator", "-vin", "5", "-vout", "3.3", "-i", "0.5"]
            )
            assert result.exit_code == 0
            assert "Components: 3" in result.output

    def test_save_design(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["generate", "-o", "./out", "--save", "design.json"]
            )
            assert result.exit_code == 0
            assert Path("design.json").exists()


class TestTopologies:
    def test_list(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["topologies"])
        assert result.exit_code == 0
        assert "buck_converter" in result.output
        assert "ldo_regulator" in result.output


class TestCompare:
    def test_identical_designs_match(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["generate", "-o", ".", "--save", "a.json"])
            runner.invoke(cli, ["generate", "-o", ".", "--save", "b.json"])
            result = runner.invoke(cli, ["compare", "a.json", "b.json"])
            assert result.exit_code == 0
            assert "match" in result.output.lower()

    def test_different_designs_show_diffs(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["generate", "-o", ".", "--save", "buck.json"])
            runner.invoke(
                cli, [
                    "generate", "-t", "ldo_regulator",
                    "-vin", "5", "-vout", "3.3", "-i", "0.5",
                    "-o", ".", "--save", "ldo.json",
                ]
            )
            result = runner.invoke(cli, ["compare", "buck.json", "ldo.json"])
            assert result.exit_code == 1
            assert "difference" in result.output.lower()
