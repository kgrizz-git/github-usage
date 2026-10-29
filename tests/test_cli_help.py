"""Interpreter-specific installation guidance stays shell-safe across entry points."""

import contextlib
import io
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage import cli, cli_gui, export_report
from github_usage.cli_help import get_help, pip_install_command


class InterpreterInstallGuidanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _python_in(self, environment):
        return str(self.root / environment / "bin" / "python")

    def test_pip_command_preserves_interpreter_and_requirement_as_single_arguments(self):
        executable = self._python_in("Test Env's Python")
        with mock.patch.object(sys, "executable", executable):
            command = pip_install_command("textual>=0.70.0", target_shell="posix")
        self.assertEqual(
            shlex.split(command),
            [executable, "-m", "pip", "install", "textual>=0.70.0"],
        )

    def test_both_help_routes_render_commands_for_the_current_interpreter(self):
        executable = self._python_in("Other Env's Python")
        for args in (["--help"], ["--cli"]):
            with self.subTest(args=args):
                output = io.StringIO()
                with (
                    mock.patch.object(sys, "executable", executable),
                    mock.patch.object(cli, "resolve_token") as token,
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(cli.main(args), 0)
                    for requirement in ("textual>=0.70.0", "openpyxl>=3.1", "fpdf2>=2.7"):
                        self.assertIn(
                            "\n".join(
                                line.strip()
                                for line in pip_install_command(requirement).splitlines()
                            ),
                            "\n".join(line.strip() for line in output.getvalue().splitlines()),
                        )
                token.assert_not_called()
                self.assertIn("scripts/python -m pip install -e '.[gui]'", output.getvalue())

    def test_help_generation_does_not_keep_an_old_interpreter(self):
        for executable in (self._python_in("first"), self._python_in("second")):
            with mock.patch.object(sys, "executable", executable):
                self.assertIn(
                    "\n".join(
                        line.strip() for line in pip_install_command("textual>=0.70.0").splitlines()
                    ),
                    "\n".join(line.strip() for line in get_help().splitlines()),
                )

    def test_missing_gui_error_targets_the_running_interpreter(self):
        output = io.StringIO()
        with (
            mock.patch.object(sys, "executable", self._python_in("GUI Env's Python")),
            mock.patch.object(cli_gui.importlib.util, "find_spec", return_value=None),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(cli_gui.run_tui(), 1)
            self.assertIn(pip_install_command("textual>=0.70.0"), output.getvalue())
        self.assertIn("scripts/python -m pip install -e '.[gui]'", output.getvalue())

    def test_export_errors_target_the_running_interpreter(self):
        for kind, module, requirement in (
            ("xlsx", "openpyxl", "openpyxl>=3.1"),
            ("pdf", "fpdf", "fpdf2>=2.7"),
        ):
            with self.subTest(format=kind):
                with (
                    mock.patch.object(sys, "executable", self._python_in("Export Env's Python")),
                    mock.patch.dict(sys.modules, {module: None}),
                    self.assertRaises(RuntimeError) as error,
                ):
                    export_report.export({}, kind)
                with mock.patch.object(sys, "executable", self._python_in("Export Env's Python")):
                    command = pip_install_command(requirement)
                self.assertIn(command, str(error.exception))
