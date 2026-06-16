"""Terminal output helpers for the legacy report."""

from __future__ import annotations


def print_header():
    print("=" * 70)
    print("        GitHub Monthly Usage Report v3")
    print("=" * 70)
    print()


def print_sep(title):
    print(f"── {title} {'─' * (60 - len(title))}")


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")
