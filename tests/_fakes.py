from __future__ import annotations


class FakeSleeper:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def assert_monotonic_increasing(calls: list[float]) -> None:
    for i in range(1, len(calls)):
        assert calls[i] >= calls[i - 1], f"Not monotonic increasing: {calls}"
