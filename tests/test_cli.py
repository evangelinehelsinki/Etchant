"""Tests for the CLI entry point."""

from __future__ import annotations

from click.testing import CliRunner

from etchant.cli import main


class TestCli:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "LM2596" in result.output

    def test_default_invocation(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-o", "./test_output"])
            assert result.exit_code == 0
            assert "buck_converter" in result.output
            assert "Components: 6" in result.output
            assert "Nets: 5" in result.output

    def test_validation_pass(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-o", "./test_output", "--validate"])
            assert result.exit_code == 0
            assert "PASS" in result.output

    def test_no_validate(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-o", "./test_output", "--no-validate"])
            assert result.exit_code == 0
            assert "Validation" not in result.output

    def test_verbose(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-o", "./test_output", "-v"])
            assert result.exit_code == 0

    def test_custom_voltages(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["-o", "./test_output", "-vin", "24", "-vout", "5", "-i", "1.5"]
            )
            assert result.exit_code == 0
            assert "Components: 6" in result.output

    def test_invalid_output_voltage_fails(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-o", "./test_output", "-vout", "3.3"])
            assert result.exit_code != 0
