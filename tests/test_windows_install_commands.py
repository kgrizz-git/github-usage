"""Windows install instructions quote for cmd.exe and PowerShell independently."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

from github_usage.cli_help import InstallShell, get_help, pip_install_command


class WindowsInstallRenderingTests(unittest.TestCase):
    executable = r"C:\Program Files\O'Brien & Tools\python.exe"

    def test_cmd_quotes_executable_and_requirement_operators(self):
        with mock.patch.object(sys, "executable", self.executable):
            for requirement in ("openpyxl>=3.1", "fpdf2<4", "textual[extra]>=0.70.0"):
                with self.subTest(requirement=requirement):
                    self.assertEqual(
                        pip_install_command(requirement, target_shell="cmd"),
                        f'"{self.executable}" -m pip install "{requirement}"',
                    )

    def test_powershell_uses_call_operator_and_escapes_apostrophes(self):
        with mock.patch.object(sys, "executable", self.executable):
            self.assertEqual(
                pip_install_command("openpyxl>=3.1", target_shell="powershell"),
                r"& 'C:\Program Files\O''Brien & Tools\python.exe' -m pip install 'openpyxl>=3.1'",
            )

    def test_powershell_keeps_requirement_metacharacters_literal(self):
        with mock.patch.object(sys, "executable", self.executable):
            self.assertTrue(
                pip_install_command(
                    "example; marker == 'Windows'", target_shell="powershell"
                ).endswith("-m pip install 'example; marker == ''Windows'''")
            )

    def test_windows_automatic_output_labels_both_shells(self):
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(sys, "executable", self.executable),
        ):
            command = pip_install_command("openpyxl>=3.1")
            self.assertIn('cmd.exe:\n  "C:\\Program Files', command)
            self.assertIn("PowerShell:\n  & 'C:\\Program Files", command)
            help_text = get_help()
            self.assertIn("cmd.exe:", help_text)
            self.assertIn("PowerShell:", help_text)
            self.assertNotIn("# XLSX", help_text)

    def test_cmd_expansion_characters_reject_explicit_rendering_and_offer_powershell(self):
        for character in ("%", "!", '"', "\r", "\n"):
            with (
                self.subTest(character=repr(character)),
                mock.patch.object(sys, "platform", "win32"),
                mock.patch.object(sys, "executable", self.executable + character),
            ):
                with self.assertRaisesRegex(ValueError, "Use PowerShell"):
                    pip_install_command("openpyxl>=3.1", target_shell="cmd")
                self.assertTrue(pip_install_command("openpyxl>=3.1").startswith("PowerShell:"))
                self.assertIn("cmd.exe: use PowerShell", get_help())

    def test_cmd_rejects_expansion_characters_in_requirements(self):
        with self.assertRaisesRegex(ValueError, "Use PowerShell"):
            pip_install_command("example!=1", target_shell="cmd")

    def test_unknown_shell_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported installation shell"):
            pip_install_command("example>=1", target_shell=cast(InstallShell, "unknown"))


@unittest.skipUnless(sys.platform == "win32", "Native Windows shell execution")
class NativeWindowsInstallTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _run_fake_pip(self, shell):
        package = self.root / "pip"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(
            "import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8"
        )
        command = pip_install_command("example>=1", target_shell=shell)
        environment = {**os.environ, "PYTHONPATH": str(self.root), "PYTHONNOUSERSITE": "1"}
        if shell == "cmd":
            cmd = shutil.which("cmd.exe")
            if not cmd:
                self.skipTest("cmd.exe is not installed")
            result = subprocess.run(
                f'"{cmd}" /d /s /c "{command}"',
                executable=cmd,
                cwd=self.root,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
        else:
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if not powershell:
                self.skipTest("PowerShell is not installed")
            result = subprocess.run(
                [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=self.root,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
        self.assertEqual(json.loads(result.stdout), ["install", "example>=1"])

    def test_cmd_executes_requirement_as_one_argument_without_redirecting(self):
        self._run_fake_pip("cmd")

    def test_powershell_invokes_quoted_interpreter_and_requirement(self):
        self._run_fake_pip("powershell")
