"""Export orchestrator.

Owns file paths, atomic writes, stdout routing, dependency checks, and
redaction. The format-specific writers are pure: they take ``(data, file_obj)``
and do not open files or check dependencies.

Atomic write protocol:
- A temp file is created in the target directory via :func:`tempfile.mkstemp`.
- The file object is passed to the writer; on success, the temp file is
  renamed to the final path via :func:`os.replace`.
- On exception, the temp file is unlinked before re-raising.
"""

from __future__ import annotations

import contextlib
import datetime
import os
import sys
import tempfile

from . import export_csv, export_json, export_pdf, export_text, export_xlsx, redact

_STRUCTURED_FORMATS = {"csv", "xlsx", "pdf"}
_BINARY_FORMATS = {"xlsx", "pdf"}
_FILE_EXTENSIONS = {
    "csv": "csv",
    "xlsx": "xlsx",
    "pdf": "pdf",
    "json": "json",
    "text": "txt",
}
_WRITERS = {
    "csv": export_csv,
    "xlsx": export_xlsx,
    "json": export_json,
    "text": export_text,
    "pdf": export_pdf,
}


def export(
    data,
    export_format: str,
    output_path: str | None = None,
    username: str | None = None,
    month: str | None = None,
    redact_data: bool = True,
    to_stdout: bool = False,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
) -> str:
    """Write ``data`` to a file in ``export_format``.

    Returns the absolute path of the written file, or ``""`` when writing
    to stdout or when ``export_format == "none"``.
    """
    if export_format == "none":
        return ""

    if export_format not in _WRITERS:
        raise ValueError(f"Unsupported export format: {export_format}")

    if export_format in _STRUCTURED_FORMATS and isinstance(data, str):
        raise ValueError(
            f"Format '{export_format}' requires structured dict data, not plain text. "
            "Use '--export text' for plain text output."
        )

    _check_optional_deps(export_format)

    if redact_data:
        if isinstance(data, dict):
            data = redact.redact_report_data(data)
        elif isinstance(data, str):
            data = redact.redact_text(data)

    writer = _WRITERS[export_format]
    writer_kwargs = {
        "include_forecast": include_forecast,
        "premium_requests_limit": premium_requests_limit,
    }

    if to_stdout:
        if export_format in _BINARY_FORMATS:
            writer.write(data, sys.stdout.buffer, **writer_kwargs)
        else:
            writer.write(data, sys.stdout, **writer_kwargs)
        return ""

    path = output_path or generate_filename(export_format, username, month)
    if export_format in _BINARY_FORMATS:
        return _atomic_write_bytes(path, lambda f: writer.write(data, f, **writer_kwargs))
    return _atomic_write_text(path, lambda f: writer.write(data, f, **writer_kwargs))


def generate_filename(
    export_format: str, username: str | None = None, month: str | None = None
) -> str:
    """Return a default output filename for ``export_format``."""
    ext = _FILE_EXTENSIONS[export_format]
    if month:
        base = f"github-usage-{username + '-' if username else ''}{month}"
    else:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        base = f"github-usage-{username + '-' if username else ''}{today}"
    return f"reports/{base}.{ext}"


def _check_optional_deps(export_format: str) -> None:
    """Raise ``RuntimeError`` with install instructions if optional deps are missing."""
    if export_format == "xlsx":
        try:
            import openpyxl  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "XLSX export requires openpyxl. Install with: pip install github-usage[export-xlsx]"
            ) from exc
    if export_format == "pdf":
        try:
            from fpdf import FPDF  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "PDF export requires fpdf2. Install with: pip install github-usage[export-pdf]"
            ) from exc


def _validated_directory(path: str) -> str:
    """Validate ``path`` and return the directory it lives in.

    ``path`` is an operator-supplied export destination (``--output`` or the
    generated default). Reject NUL and other control characters up front so a
    malformed value can never reach the filesystem calls below, then create the
    parent directory.
    """
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in path):
        raise ValueError("Output path must not contain control characters.")
    directory = os.path.dirname(path) or "."
    # Safe: local single-user CLI; the destination is an operator-chosen path
    # (--output / generated default), not attacker-controlled network input.
    os.makedirs(directory, exist_ok=True)  # NOSONAR
    return directory


def _atomic_write_text(path: str, write_fn) -> str:
    """Write to ``path`` atomically via a UTF-8 text-mode temp file."""
    directory = _validated_directory(path)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_fn(f)
        # Safe: path validated in _validated_directory; operator-chosen destination.
        os.replace(tmp_path, path)  # NOSONAR
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise
    return os.path.abspath(path)


def _atomic_write_bytes(path: str, write_fn) -> str:
    """Write to ``path`` atomically via a binary-mode temp file."""
    directory = _validated_directory(path)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            write_fn(f)
        # Safe: path validated in _validated_directory; operator-chosen destination.
        os.replace(tmp_path, path)  # NOSONAR
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise
    return os.path.abspath(path)
