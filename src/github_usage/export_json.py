"""JSON writer for report exports."""

from __future__ import annotations

import datetime
import json

from .report_forecast_data import build_report_forecast


class _DatetimeEncoder(json.JSONEncoder):
    """Serialize ``datetime.datetime`` and ``datetime.date`` as ISO-8601 strings."""

    def default(self, obj):  # type: ignore[override]
        if isinstance(obj, datetime.datetime | datetime.date):
            return obj.isoformat()
        return super().default(obj)


def write(
    data: dict,
    file_obj,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    **kwargs,
) -> None:
    """Serialize the report data dict to JSON and write to ``file_obj``.

    Output is pretty-printed (``indent=2``), preserves unicode
    (``ensure_ascii=False``), and uses :class:`_DatetimeEncoder` for
    datetime values. A trailing newline is appended for POSIX compliance.

    A derived ``forecast`` block is computed at export time and merged into
    a shallow copy of ``data`` without mutating the source dict.
    """
    del kwargs
    export_data = dict(data)
    if include_forecast:
        export_data["forecast"] = build_report_forecast(
            data,
            premium_requests_limit=premium_requests_limit,
        )
    payload = json.dumps(export_data, indent=2, ensure_ascii=False, cls=_DatetimeEncoder)
    file_obj.write(payload)
    file_obj.write("\n")
