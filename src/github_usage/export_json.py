"""JSON writer for report exports."""

from __future__ import annotations

import datetime
import json


class _DatetimeEncoder(json.JSONEncoder):
    """Serialize ``datetime.datetime`` and ``datetime.date`` as ISO-8601 strings."""

    def default(self, obj):
        if isinstance(obj, datetime.datetime | datetime.date):
            return obj.isoformat()
        return super().default(obj)


def write(data: dict, file_obj) -> None:
    """Serialize the report data dict to JSON and write to ``file_obj``.

    Output is pretty-printed (``indent=2``), preserves unicode
    (``ensure_ascii=False``), and uses :class:`_DatetimeEncoder` for
    datetime values. A trailing newline is appended for POSIX compliance.
    """
    payload = json.dumps(data, indent=2, ensure_ascii=False, cls=_DatetimeEncoder)
    file_obj.write(payload)
    file_obj.write("\n")
