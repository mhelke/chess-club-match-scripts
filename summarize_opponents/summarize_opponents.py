#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_opponents.py
======================
Reads club_matches_raw.csv (produced by analyze_club_schedule.py) and
outputs club_opponent_summary.csv — one row per unique
(opponent × game_type × rating_range) combination.

Columns in the output:
  opponent        – HYPERLINK formula to the club's Chess.com page
  game_type       – chess or chess960
  rating_range    – Open, ≤1400, 1000–1500, etc.
  opp_roster_size – opponent's player count from the most relevant match
                    (upcoming > in-progress > finished; most recent wins)
  match_date      – start date of that most relevant match
  status          – Upcoming / In Progress / Finished
  total_matches   – total number of matches of this type with this club

USAGE:
  python scripts/summarize_opponents.py --input club_matches_raw.csv
  python scripts/summarize_opponents.py --input club_matches_raw.csv --output club_opponent_summary.csv
"""

import argparse
import os
import re

import pandas as pd

# ── Default paths (relative to the project root, i.e. one level up from this file) ──

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

DEFAULT_INPUT  = os.path.join(PROJECT_ROOT, "club_matches_raw.csv")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "club_opponent_summary.csv")

# Status priority for picking the "most relevant" row per group.
# Lower number = higher priority (upcoming beats in-progress beats finished).
STATUS_PRIORITY = {"Upcoming": 0, "In Progress": 1, "Finished": 2}


# ── HYPERLINK formula helpers ──────────────────────────────────────────────────

# Matches: =HYPERLINK("url","label")  or  =HYPERLINK("url", "label")
_HYPERLINK_RE = re.compile(
    r'=HYPERLINK\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)',
    re.IGNORECASE,
)


def parse_hyperlink(cell: str) -> tuple[str, str]:
    """
    Parse an Excel/Sheets HYPERLINK formula back into (url, label).
    If the cell is plain text (no formula), return ("", cell).
    """
    m = _HYPERLINK_RE.match(str(cell).strip())
    if m:
        return m.group(1), m.group(2)
    return "", str(cell).strip()


def make_hyperlink(url: str, label: str) -> str:
    """Build an =HYPERLINK() formula, or return plain label if no URL."""
    if url:
        # Escape any double-quotes inside label/url (shouldn't happen, but safe).
        safe_url   = url.replace('"', '""')
        safe_label = label.replace('"', '""')
        return f'=HYPERLINK("{safe_url}","{safe_label}")'
    return label


# ── Main logic ─────────────────────────────────────────────────────────────────

def main(input_path: str, output_path: str) -> None:
    # ── 1. Load raw CSV ───────────────────────────────────────────────────────
    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        raise SystemExit(1)

    df = pd.read_csv(input_path, dtype=str).fillna("")
    print(f"Loaded {len(df)} rows from {input_path}")

    # ── 2. Parse opponent name and URL out of HYPERLINK formulas ──────────────
    parsed = df["opponent"].apply(parse_hyperlink)
    df["opponent_url"]  = parsed.apply(lambda t: t[0])
    df["opponent_name"] = parsed.apply(lambda t: t[1])

    # ── 3. Parse dates so we can sort reliably ────────────────────────────────
    df["start_dt"] = pd.to_datetime(df["start_date"], format="%Y-%m-%d %H:%M", errors="coerce")

    # ── 4. Assign numeric priority to statuses ────────────────────────────────
    df["status_priority"] = df["status"].map(STATUS_PRIORITY).fillna(99).astype(int)

    # ── 5. For each (opponent, game_type, rating_range, time_control) group,
    #       pick the single most relevant row and count total matches. ─────────
    group_keys = ["opponent_name", "opponent_url", "game_type", "rating_range", "time_control"]

    summary_rows = []
    for (opp_name, opp_url, game_type, rating_range, time_control), group in df.groupby(group_keys, sort=False):
        # Sort by status priority first (Upcoming first), then by date descending
        # so that within the same status the most recent match floats to the top.
        sorted_group = group.sort_values(
            ["status_priority", "start_dt"],
            ascending=[True, False],
        )
        best = sorted_group.iloc[0]

        summary_rows.append({
            "opponent":        make_hyperlink(opp_url, opp_name),
            "game_type":       game_type,
            "time_control":    time_control,
            "rating_range":    rating_range,
            "opp_roster_size": best["opp_players"],
            "match_date":      best["start_date"],
            "status":          best["status"],
            "total_matches":   len(group),
        })

    summary_df = pd.DataFrame(summary_rows)

    # ── 6. Sort final output: by opponent name, then game_type, then range ────
    summary_df["_sort_name"] = summary_df["opponent"].apply(
        lambda c: parse_hyperlink(c)[1].lower()
    )
    summary_df = summary_df.sort_values(
        ["_sort_name", "game_type", "time_control", "rating_range"]
    ).drop(columns=["_sort_name"]).reset_index(drop=True)

    # ── 7. Write CSV ──────────────────────────────────────────────────────────
    summary_df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Summary exported → {output_path}  ({len(summary_df)} rows, "
          f"{summary_df['_sort_name' if '_sort_name' in summary_df.columns else 'opponent'].nunique()} unique clubs)")

    # ── 8. Quick stats ────────────────────────────────────────────────────────
    unique_clubs = summary_df["opponent"].apply(lambda c: parse_hyperlink(c)[1]).nunique()
    print(f"\nUnique opponent clubs : {unique_clubs}")
    print(f"Unique game types     : {summary_df['game_type'].nunique()}  "
          f"({', '.join(summary_df['game_type'].unique())})")
    print(f"Unique rating ranges  : {summary_df['rating_range'].nunique()}")
    print(f"\nStatus breakdown of most-relevant match per group:")
    print(summary_df["status"].value_counts().to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize opponents from club_matches_raw.csv")
    parser.add_argument(
        "--input",  default=DEFAULT_INPUT,
        help=f"Path to club_matches_raw.csv (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Path for the output summary CSV (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    main(args.input, args.output)
