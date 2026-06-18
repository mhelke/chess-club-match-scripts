#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
track_upcoming_matches.py
=========================
Fetches all UPCOMING (registered) matches for a given Chess.com club and:

  Section 1 — New matches since last run
  Section 2 — Player count changes since last run (both teams)
  Section 3 — Calendar view: per-day match count, our player totals,
               rating coverage (chess / chess960 separate), and gaps.

USAGE:
  pip install requests pandas
  python scripts/track_upcoming_matches.py <club_id>
  python scripts/track_upcoming_matches.py 1-day-per-move-club
  python scripts/track_upcoming_matches.py my-club --output matches.csv --prev matches_prev.csv
"""

import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

import requests
import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────────────

API_BASE      = "https://api.chess.com/pub"
DEFAULT_USER_AGENT = "ClubScheduleAnalyzer/1.0"
REQUEST_DELAY = 0.5
MAX_RETRIES   = 3

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

# Rating bands for gap detection (label, lo_inclusive, hi_exclusive).
RATING_BANDS = [
    ("≤800",       0,    800),
    ("800–1000",   800,  1000),
    ("1000–1200",  1000, 1200),
    ("1200–1400",  1200, 1400),
    ("1400–1600",  1400, 1600),
    ("1600–1800",  1600, 1800),
    ("1800+",      1800, 9999),
]

CSV_COLS = ["match_url", "match_name", "start_date", "opponent",
            "game_type", "time_control", "rating_range", "our_players", "opp_players"]

SEP  = "=" * 72
DASH = "─" * 72


# ── HTTP ───────────────────────────────────────────────────────────────────────

def _get(url: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    headers = {"User-Agent": user_agent}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 2 ** attempt))
                print(f"  [rate-limit] waiting {wait}s ...")
                time.sleep(wait)
                continue
            if r.status_code in (500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            print(f"  [warn] HTTP {r.status_code} for {url}")
            return {}
        except requests.RequestException:
            time.sleep(2 ** attempt)
    print(f"  [error] Gave up on {url}")
    return {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def api_url_to_web(api_url: str) -> str:
    m = re.search(r"/match/(\d+)$", api_url)
    return f"https://www.chess.com/club/matches/{m.group(1)}" if m else api_url


def format_rating_range(min_r, max_r) -> str:
    has_min = min_r and int(min_r) > 0
    has_max = max_r and int(max_r) > 0
    if has_min and has_max:
        return f"{int(min_r)}-{int(max_r)}"
    if has_min:
        return f"{int(min_r)}+"
    if has_max:
        return f"<={int(max_r)}"
    return "Open"


def parse_rating_bounds(rng: str) -> tuple:
    r = rng.strip()
    if r.lower() == "open":
        return (0, 9999)
    if r.startswith("<=") or r.startswith("\u2264"):
        try:
            return (0, int(r.lstrip("<=\u2264")))
        except ValueError:
            pass
    if r.endswith("+"):
        try:
            return (int(r[:-1]), 9999)
        except ValueError:
            pass
    # Handle both en-dash (–) and plain hyphen
    for sep in ("\u2013", "-"):
        if sep in r:
            parts = r.split(sep, 1)
            try:
                return (int(parts[0]), int(parts[1]))
            except ValueError:
                pass
    return (0, 9999)


def band_overlaps(match_lo: int, match_hi: int, band_lo: int, band_hi: int) -> bool:
    """True if the match rating window overlaps the band."""
    return match_lo < band_hi and match_hi > band_lo


# ── Time control parsing ───────────────────────────────────────────────────────

def _parse_time_control(tc: str) -> str:
    """Convert Chess.com time-control strings to readable labels.
    "1/86400" -> "1 day/move", "1/172800" -> "2 days/move", etc.
    """
    if not tc or tc == "None":
        return "Unknown"
    if "/" in tc:
        try:
            seconds = int(tc.split("/")[1])
            days = seconds / 86400
            if days == int(days):
                d = int(days)
                return f"{d} day/move" if d == 1 else f"{d} days/move"
            return f"{days:.1f} days/move"
        except (ValueError, IndexError):
            pass
    else:
        try:
            base = int(tc.split("+")[0])
            mins = base // 60
            return f"{mins} min" if mins else f"{base}s"
        except ValueError:
            pass
    return tc


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_upcoming(club_id: str, user_agent: str = DEFAULT_USER_AGENT) -> list:
    raw = _get(f"{API_BASE}/club/{club_id}/matches", user_agent)
    if not raw:
        print("ERROR: Could not fetch match list.")
        sys.exit(1)

    stubs = raw.get("registered", [])
    print(f"Found {len(stubs)} upcoming match stub(s). Fetching details ...")

    rows = []
    for i, stub in enumerate(stubs, 1):
        match_api_url = stub.get("@id", "")
        if not match_api_url:
            continue
        print(f"  [{i}/{len(stubs)}] {match_api_url}")
        time.sleep(REQUEST_DELAY)
        detail = _get(match_api_url, user_agent)
        if not detail:
            continue

        raw_ts = (detail.get("start_time") or detail.get("start_datetime")
                  or stub.get("start_time") or stub.get("start_datetime"))
        if raw_ts:
            start_dt  = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
            start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        else:
            start_str = "Unknown"

        settings     = detail.get("settings", {})
        min_r        = settings.get("min_rating") or detail.get("min_rating")
        max_r        = settings.get("max_rating") or detail.get("max_rating")
        rating_range = format_rating_range(min_r, max_r)
        game_type    = settings.get("rules", detail.get("rules", "chess"))
        match_name   = detail.get("name", stub.get("name", ""))

        # Time control: "1/86400" -> "1 day/move", "1/172800" -> "2 days/move", etc.
        tc_raw = str(settings.get("time_control") or detail.get("time_control", ""))
        time_control = _parse_time_control(tc_raw)

        our_count = 0
        opp_count = 0
        opp_name  = "Unknown"
        for team_data in detail.get("teams", {}).values():
            club_url = team_data.get("@id", "") or team_data.get("url", "")
            players  = team_data.get("players", [])
            if club_id.lower() in club_url.lower():
                our_count = len(players)
            else:
                opp_count = len(players)
                opp_name  = team_data.get("name", "Unknown")

        rows.append({
            "match_url":    api_url_to_web(match_api_url),
            "match_name":   match_name,
            "start_date":   start_str,
            "opponent":     opp_name,
            "game_type":    game_type,
            "time_control": time_control,
            "rating_range": rating_range,
            "our_players":  our_count,
            "opp_players":  opp_count,
        })

    return rows


# ── Diff ───────────────────────────────────────────────────────────────────────

def diff(current: pd.DataFrame, prev: pd.DataFrame) -> tuple:
    prev_urls = set(prev["match_url"].str.strip())
    curr_urls = set(current["match_url"].str.strip())

    new_matches = current[current["match_url"].isin(curr_urls - prev_urls)].to_dict("records")

    changed_rows = []
    prev_idx = prev.set_index("match_url")
    for url in curr_urls & prev_urls:
        crow = current[current["match_url"] == url].iloc[0]
        prow = prev_idx.loc[url]
        if (str(crow["our_players"]) != str(prow["our_players"]) or
                str(crow["opp_players"]) != str(prow["opp_players"])):
            changed_rows.append((prow, crow))

    return new_matches, changed_rows


# ── Display ────────────────────────────────────────────────────────────────────

def fmt_match(row) -> str:
    opp = _trunc(row['opponent'], 40)
    return (
        f"  {str(row['start_date']):<18}  vs {opp}\n"
        f"  {'':18}  {str(row['game_type']):<10} {_trunc(row.get('time_control',''), 16):<16} {str(row['rating_range']):<14}"
        f"  Us:{str(row['our_players']):>3} / Them:{str(row['opp_players']):>3}\n"
        f"  {'':18}  {str(row['match_name'])}\n"
        f"  {'':18}  {str(row['match_url'])}"
    )


def _trunc(s: str, width: int) -> str:
    """Truncate string to `width` chars, appending '…' if truncated."""
    s = str(s)
    return s if len(s) <= width else s[:width - 1] + "…"


def _fmt_range(lo: int, hi: int) -> str:
    """Describe a numeric rating range naturally: 0→800 = '≤800', 1800→9999 = '1800+', else 'lo–hi'."""
    if lo == 0:
        return f"≤{hi}"
    if hi >= 9999:
        return f"{lo}+"
    return f"{lo}–{hi}"


def print_calendar(df: pd.DataFrame) -> None:
    print(f"\n{DASH}")
    print("SECTION 3 -- CALENDAR VIEW")
    print(DASH)

    df = df.copy()
    df["day"] = df["start_date"].str[:10]

    for day in sorted(df["day"].unique()):
        day_df    = df[df["day"] == day]
        total_our = day_df["our_players"].astype(int).sum()

        print(f"\n  {day}  |  {len(day_df)} match(es)  |  {total_our} of our players registered")
        print(f"  {'':4}{'Opponent':<36} {'Type':<10} {'Time Control':<16} {'Rating Range':<14} Players")
        print(f"  {'':4}{'-'*36} {'-'*10} {'-'*16} {'-'*14} -------")

        for _, row in day_df.sort_values("start_date").iterrows():
            print(f"  {'':4}{_trunc(row['opponent'], 36):<36} {_trunc(row['game_type'], 10):<10}"
                  f" {_trunc(row.get('time_control', ''), 16):<16} {_trunc(row['rating_range'], 14):<14}"
                  f" Us:{row['our_players']:>3} / Them:{row['opp_players']:>3}")

        # Coverage analysis — chess and chess960 separately
        for gtype in ("chess", "chess960"):
            gdf = day_df[day_df["game_type"].str.lower() == gtype]
            if gdf.empty:
                print(f"\n  [{gtype}] No matches this day.")
                continue

            label = "Standard" if gtype == "chess" else "Chess960"
            if (gdf["rating_range"].str.lower() == "open").any():
                print(f"\n  [{label}] All ratings covered (Open match present).")
                continue

            covered = set()
            for _, mrow in gdf.iterrows():
                lo, hi = parse_rating_bounds(mrow["rating_range"])
                for bname, blo, bhi in RATING_BANDS:
                    if band_overlaps(lo, hi, blo, bhi):
                        covered.add(bname)

            gap_bands = [b for b in RATING_BANDS if b[0] not in covered]
            if not gap_bands:
                print(f"\n  [{label}] All ratings covered.")
            else:
                # Merge contiguous gap bands into natural range descriptions.
                merged = []
                run_lo = gap_bands[0][1]
                run_hi = gap_bands[0][2]
                for _, blo, bhi in gap_bands[1:]:
                    if blo == run_hi:          # contiguous — extend the run
                        run_hi = bhi
                    else:                      # gap in the gaps — close current run
                        merged.append(_fmt_range(run_lo, run_hi))
                        run_lo, run_hi = blo, bhi
                merged.append(_fmt_range(run_lo, run_hi))
                print(f"\n  [{label}] Gaps: {', '.join(merged)}")

    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main(club_id: str, output_csv: str = None, prev_csv: str = None, user_agent: str = DEFAULT_USER_AGENT):
    if output_csv is None:
        output_csv = os.path.join(PROJECT_ROOT, "upcoming_matches.csv")
    if prev_csv is None:
        prev_csv = os.path.join(PROJECT_ROOT, "upcoming_matches_prev.csv")
    
    print(SEP)
    print(f"  UPCOMING MATCH TRACKER -- {club_id}")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(SEP + "\n")

    rows = fetch_upcoming(club_id, user_agent)
    if not rows:
        print("\nNo upcoming matches found.")
        sys.exit(0)

    current_df = pd.DataFrame(rows)
    current_df["our_players"] = current_df["our_players"].astype(int)
    current_df["opp_players"] = current_df["opp_players"].astype(int)
    current_df = current_df.sort_values("start_date").reset_index(drop=True)

    # Rotate snapshot: current -> prev before overwriting
    prev_df = None
    if os.path.exists(output_csv):
        shutil.copy2(output_csv, prev_csv)
        try:
            prev_df = pd.read_csv(prev_csv, dtype=str).fillna("")
        except Exception:
            prev_df = None

    current_df[CSV_COLS].to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Snapshot saved -> {output_csv}  ({len(current_df)} matches)\n")

    # ── Section 1: New matches ─────────────────────────────────────────────────
    print(DASH)
    print("SECTION 1 -- NEW MATCHES SINCE LAST RUN")
    print(DASH)

    if prev_df is None:
        print("  (No previous snapshot -- all matches shown as new.)\n")
        new_matches  = current_df.to_dict("records")
        changed_rows = []
    else:
        new_matches, changed_rows = diff(current_df, prev_df)

    if new_matches:
        for row in sorted(new_matches, key=lambda r: r["start_date"]):
            print(fmt_match(row))
            print()
    else:
        print("  No new matches since last run.\n")

    # ── Section 2: Player count changes ───────────────────────────────────────
    print(DASH)
    print("SECTION 2 -- PLAYER COUNT CHANGES SINCE LAST RUN")
    print(DASH)

    if changed_rows:
        for prow, crow in sorted(changed_rows, key=lambda x: x[1]["start_date"]):
            our_d = int(crow["our_players"]) - int(prow["our_players"])
            opp_d = int(crow["opp_players"]) - int(prow["opp_players"])
            print(f"  {str(crow['start_date']):<18}  vs {str(crow['opponent'])}")
            print(f"    Us  : {prow['our_players']:>3} -> {crow['our_players']:>3}  ({our_d:+d})")
            print(f"    Them: {prow['opp_players']:>3} -> {crow['opp_players']:>3}  ({opp_d:+d})\n")
    else:
        print("  No player count changes since last run.\n")

    # ── Section 3: Calendar ────────────────────────────────────────────────────
    print_calendar(current_df)

    print(SEP)
    print(f"  Total upcoming matches : {len(current_df)}")
    print(f"  Total our players reg  : {current_df['our_players'].sum()}")
    print(SEP)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Fetch and track upcoming matches for a Chess.com club"
    )
    parser.add_argument(
        "club_id",
        help="Club ID from Chess.com (e.g., '1-day-per-move-club')"
    )
    parser.add_argument(
        "--output", default=None,
        help="Path for upcoming_matches.csv output (default: PROJECT_ROOT/upcoming_matches.csv)"
    )
    parser.add_argument(
        "--prev", default=None,
        help="Path for upcoming_matches_prev.csv (default: PROJECT_ROOT/upcoming_matches_prev.csv)"
    )
    parser.add_argument(
        "--user-agent", default=DEFAULT_USER_AGENT,
        help=f"User-Agent string for API requests (default: {DEFAULT_USER_AGENT})"
    )
    args = parser.parse_args()
    main(args.club_id, args.output, args.prev, args.user_agent)
