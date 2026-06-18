#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
club_lookup.py
==============
Reads club_matches_raw.csv and produces club_lookup.csv — one row per
unique opponent club — for use as a quick reference when deciding who
to challenge next.

Output columns:
  opponent        – HYPERLINK to the club's Chess.com page
  total_matches   – Total matches played (or scheduled) vs this club
  last_match_date – Most recent match date, or next upcoming date if scheduled
  active          – "Yes" if an Upcoming or In Progress match exists right now
  game_types      – Distinct game types accepted (e.g. "chess, chess960")
  time_controls   – Distinct time controls accepted (e.g. "1 day/move, 3 days/move")
  rating_pref     – Derived preference label(s): Open / Low / Mid / High
                    Low  = any accepted range whose upper bound is ≤ 1200
                    Mid  = upper bound 1201–1600
                    High = upper bound > 1600 (or open-ended from ≥ 1400)
  rating_ranges   – All distinct raw rating ranges accepted, comma-separated
  avg_opp_roster  – Their average player count across all matches (rounded)

USAGE:
  python scripts/club_lookup.py --input club_matches_raw.csv
  python scripts/club_lookup.py --input club_matches_raw.csv --output club_lookup.csv
  python scripts/club_lookup.py --input club_matches_raw.csv --time-control "1 day/move"
  python scripts/club_lookup.py --input club_matches_raw.csv --time-control "3 days/move"
"""

import argparse
import os
import re

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

DEFAULT_INPUT  = os.path.join(PROJECT_ROOT, "club_matches_raw.csv")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "club_lookup.csv")

# Status priority: lower = higher priority for picking "representative" date.
STATUS_PRIORITY = {"Upcoming": 0, "In Progress": 1, "Finished": 2}

# ── HYPERLINK helpers ──────────────────────────────────────────────────────────

_HYPERLINK_RE = re.compile(
    r'=HYPERLINK\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)',
    re.IGNORECASE,
)


def parse_hyperlink(cell: str) -> tuple[str, str]:
    """Return (url, label) from an =HYPERLINK formula, or ("", raw_text)."""
    m = _HYPERLINK_RE.match(str(cell).strip())
    return (m.group(1), m.group(2)) if m else ("", str(cell).strip())


def make_hyperlink(url: str, label: str) -> str:
    if url:
        safe_url   = url.replace('"', '""')
        safe_label = label.replace('"', '""')
        return f'=HYPERLINK("{safe_url}","{safe_label}")'
    return label


# ── Rating range classification ────────────────────────────────────────────────

def classify_rating_range(rating_range: str) -> str:
    """
    Map a single rating range string to a preference band label.

    "Open"        → "Open"
    ≤ N or N+     → band by N
    N–M           → band by M (upper bound)
    Low  : upper ≤ 1200
    Mid  : upper 1201–1600
    High : upper > 1600  (or open-ended from a high floor like 1400+)
    """
    r = str(rating_range).strip()

    if r.lower() == "open":
        return "Open"

    # ── Open-ended lower bound: e.g. "1400+" ──────────────────────────────────
    if r.endswith("+"):
        try:
            floor = int(r[:-1])
            if floor >= 1400:
                return "High"
            if floor >= 1200:
                return "Mid"
            return "Low"
        except ValueError:
            pass

    # ── Upper-bounded: e.g. "≤1400" ───────────────────────────────────────────
    if r.startswith("≤"):
        try:
            cap = int(r[1:])
            if cap <= 1200:
                return "Low"
            if cap <= 1600:
                return "Mid"
            return "High"
        except ValueError:
            pass

    # ── Closed range: e.g. "1000–1500" or "900–1200" (uses en-dash or hyphen) ─
    sep = "–" if "–" in r else ("-" if "-" in r else None)
    if sep:
        parts = r.split(sep, 1)
        if len(parts) == 2:
            try:
                upper = int(parts[1])
                if upper <= 1200:
                    return "Low"
                if upper <= 1600:
                    return "Mid"
                return "High"
            except ValueError:
                pass

    # Fallback — can't parse, treat as restricted-unknown
    return "Restricted"


# ── Main logic ─────────────────────────────────────────────────────────────────

def main(input_path: str, output_path: str, time_control_filter: str = None) -> None:

    # ── 1. Load raw CSV ───────────────────────────────────────────────────────
    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        raise SystemExit(1)

    df = pd.read_csv(input_path, dtype=str).fillna("")
    print(f"Loaded {len(df)} rows from {input_path}")

    # ── Filter by time control if specified ──────────────────────────────────
    if time_control_filter:
        df = df[df["time_control"].str.strip() == time_control_filter].reset_index(drop=True)
        print(f"After filtering to '{time_control_filter}': {len(df)} rows")
    else:
        print(f"No time control filter applied")

    # ── 2. Parse HYPERLINK formulas back to (url, name) ───────────────────────
    parsed = df["opponent"].apply(parse_hyperlink)
    df["opponent_url"]  = parsed.apply(lambda t: t[0])
    df["opponent_name"] = parsed.apply(lambda t: t[1])

    # ── 3. Numeric fields ─────────────────────────────────────────────────────
    df["start_dt"]      = pd.to_datetime(df["start_date"], format="%Y-%m-%d %H:%M", errors="coerce")
    df["opp_players"]   = pd.to_numeric(df["opp_players"], errors="coerce").fillna(0)
    df["status_prio"]   = df["status"].map(STATUS_PRIORITY).fillna(99).astype(int)

    # ── 4. Build one row per club ─────────────────────────────────────────────
    rows = []

    for (opp_name, opp_url), group in df.groupby(["opponent_name", "opponent_url"], sort=False):

        # ── Reference date: prefer upcoming > in-progress, then most recent ──
        sorted_g = group.sort_values(["status_prio", "start_dt"], ascending=[True, False])
        best = sorted_g.iloc[0]
        last_date = best["start_date"]

        # ── Active flag ───────────────────────────────────────────────────────
        active_statuses = {"Upcoming", "In Progress"}
        is_active = group["status"].isin(active_statuses).any()

        # ── Game types — sorted for consistency ───────────────────────────────
        game_types = ", ".join(sorted(group["game_type"].dropna().unique()))

        # ── Time controls — sorted ────────────────────────────────────────────
        # Sort meaningfully: 1 day < 2 days < 3 days etc.
        def tc_sort_key(tc: str) -> float:
            m = re.search(r"([\d.]+)", tc)
            return float(m.group(1)) if m else 999
        raw_tcs = sorted(group["time_control"].dropna().unique(), key=tc_sort_key)
        time_controls = ", ".join(raw_tcs)

        # ── Rating ranges & preference labels ─────────────────────────────────
        raw_ranges    = group["rating_range"].dropna().unique().tolist()
        # Remove duplicates, keep a stable order (sort alphabetically)
        unique_ranges = sorted(set(raw_ranges))

        # Map each range to a band, deduplicate, then sort in a logical order
        band_order = {"Open": 0, "Low": 1, "Mid": 2, "High": 3, "Restricted": 4}
        bands = sorted(
            set(classify_rating_range(r) for r in unique_ranges),
            key=lambda b: band_order.get(b, 9),
        )
        rating_pref   = ", ".join(bands)
        rating_ranges = ", ".join(unique_ranges)

        # ── Average roster size ───────────────────────────────────────────────
        avg_roster = round(group["opp_players"].mean())

        rows.append({
            "opponent":        make_hyperlink(opp_url, opp_name),
            "total_matches":   len(group),
            "last_match_date": last_date,
            "active":          "Yes" if is_active else "No",
            "game_types":      game_types,
            "rating_pref":     rating_pref,
            "rating_ranges":   rating_ranges,
            "avg_opp_roster":  avg_roster,
        })

    lookup_df = pd.DataFrame(rows)

    # ── 5. Sort: active matches first, then by last_match_date descending ─────
    lookup_df["_active_sort"] = (lookup_df["active"] == "Yes").astype(int)
    lookup_df["_date_sort"]   = pd.to_datetime(
        lookup_df["last_match_date"], format="%Y-%m-%d %H:%M", errors="coerce"
    )
    lookup_df = (
        lookup_df
        .sort_values(["_active_sort", "_date_sort"], ascending=[False, False])
        .drop(columns=["_active_sort", "_date_sort"])
        .reset_index(drop=True)
    )

    # ── 6. Write CSV ──────────────────────────────────────────────────────────
    lookup_df.to_csv(output_path, index=False, encoding="utf-8")

    # ── 7. Summary ────────────────────────────────────────────────────────────
    print(f"Club lookup exported → {output_path}  ({len(lookup_df)} clubs)")
    print(f"\nActive (Upcoming/In Progress) : {(lookup_df['active'] == 'Yes').sum()}")
    print(f"Inactive (Finished only)      : {(lookup_df['active'] == 'No').sum()}")
    print(f"\nRating preference breakdown:")
    # Expand multi-value cells for counting
    pref_counts: dict[str, int] = {}
    for prefs in lookup_df["rating_pref"]:
        for p in prefs.split(", "):
            pref_counts[p] = pref_counts.get(p, 0) + 1
    for pref, cnt in sorted(pref_counts.items(), key=lambda x: -x[1]):
        print(f"  {pref:<12} {cnt} club(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a per-club challenge lookup from club_matches_raw.csv")
    parser.add_argument("--input",  default=DEFAULT_INPUT,  help="Path to club_matches_raw.csv")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path for club_lookup.csv output")
    parser.add_argument("--time-control", default=None, help="Optional time control filter (e.g., '1 day/move'). If not specified, all time controls are included.")
    args = parser.parse_args()
    main(args.input, args.output, args.time_control)
