#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_club_schedule.py
========================
Analyzes a Chess.com club's current match schedule to surface team load,
parameter trends, and scheduling gaps — helping admins optimize future
match offerings.

OUTPUTS:
  1. club_matches_raw.csv   — Raw data for every in-progress / upcoming match.
  2. Printed report         — Analytics & scheduling insights summary.

USAGE:
  pip install requests pandas
  python scripts/analyze_club_schedule.py <club_id>
  python scripts/analyze_club_schedule.py 1-day-per-move-club
  python scripts/analyze_club_schedule.py my-club --output matches.csv --cutoff 2025-01-01
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
import pandas as pd

# ── Constants ──────────────────────────────────────────────────────────────────

# Chess.com API base URL
API_BASE    = "https://api.chess.com/pub"
DEFAULT_USER_AGENT = "ClubScheduleAnalyzer/1.0"

# Seconds to wait between individual match-detail API calls (rate-limit courtesy).
REQUEST_DELAY = 0.5

# Maximum number of retries on transient HTTP errors (429, 5xx).
MAX_RETRIES = 3


# ── URL conversion ────────────────────────────────────────────────────────────

def api_url_to_web(api_url: str) -> str:
    """
    Convert the Chess.com API match URL to the browseable web URL.
    https://api.chess.com/pub/match/1234567
         → https://www.chess.com/club/matches/1234567
    """
    import re
    m = re.search(r"/match/(\d+)$", api_url)
    return f"https://www.chess.com/club/matches/{m.group(1)}" if m else api_url


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(url: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    GET `url` with retries and exponential back-off.
    Returns the parsed JSON body, or raises on permanent failure.
    """
    headers = {"User-Agent": user_agent}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                # Respect Retry-After if present, otherwise back off exponentially.
                wait = int(response.headers.get("Retry-After", 2 ** attempt))
                print(f"  [rate-limit] 429 on {url} — waiting {wait}s …")
                time.sleep(wait)
                continue
            if response.status_code in (500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"  [server error] {response.status_code} on {url} — retrying in {wait}s …")
                time.sleep(wait)
                continue
            # 404 or other client errors — not retriable.
            print(f"  [warn] HTTP {response.status_code} for {url}")
            return {}
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"  [network error] {exc} — retrying in {wait}s …")
            time.sleep(wait)
    print(f"  [error] Giving up on {url} after {MAX_RETRIES} attempts.")
    return {}


# ── Time-control parsing ───────────────────────────────────────────────────────

def parse_days_per_move(time_control_str: str) -> str:
    """
    Convert a Chess.com time-control string to a human-readable days-per-move label.

    Chess.com daily time controls are expressed as "1/<seconds>" where the
    denominator is the number of seconds per move.

    Examples:
      "1/86400"   → "1 day/move"
      "1/172800"  → "2 days/move"
      "1/259200"  → "3 days/move"
      "1/604800"  → "7 days/move"
      "600"       → "10 min" (live — included for completeness)
    """
    if not time_control_str:
        return "Unknown"

    if "/" in time_control_str:
        parts = time_control_str.split("/")
        if len(parts) == 2:
            try:
                seconds = int(parts[1])
                days = seconds / 86400
                if days == int(days):
                    return f"{int(days)} day{'s' if days != 1 else ''}/move"
                return f"{days:.1f} days/move"
            except ValueError:
                pass
    else:
        # Live game — expressed in seconds (or seconds+increment "600+5").
        try:
            base_secs = int(time_control_str.split("+")[0])
            minutes = base_secs // 60
            return f"{minutes} min" if minutes else f"{base_secs}s"
        except ValueError:
            pass

    return time_control_str  # Return raw if we cannot parse.


# ── Rating-range formatting ────────────────────────────────────────────────────

def format_rating_range(min_rating, max_rating) -> str:
    """
    Build a readable rating-range label from optional min/max values.
    Both may be None/0 (meaning no restriction).
    """
    has_min = min_rating and int(min_rating) > 0
    has_max = max_rating and int(max_rating) > 0

    if has_min and has_max:
        return f"{int(min_rating)}–{int(max_rating)}"
    if has_min:
        return f"{int(min_rating)}+"
    if has_max:
        return f"≤{int(max_rating)}"
    return "Open"


# ── Player-count extraction ────────────────────────────────────────────────────

def get_player_counts(match_detail: dict, our_club_id: str) -> tuple[int, int]:
    """
    Return (our_count, opponent_count) player counts from a match detail object.

    For IN PROGRESS matches the API populates `teams.<team>.players` with only
    the players who still have active boards — that is the "active" count.
    For REGISTERED (upcoming) matches the same field holds all registered players.
    """
    teams = match_detail.get("teams", {})
    our_count = 0
    opp_count = 0

    for team_key, team_data in teams.items():
        players = team_data.get("players", [])
        club_url = team_data.get("@id", "") or team_data.get("url", "")

        # Match team to our club by checking whether our CLUB_ID appears in the
        # team's API URL (e.g. "/club/our-club-name").
        if our_club_id.lower() in club_url.lower():
            our_count = len(players)
        else:
            opp_count = len(players)

    return our_count, opp_count


# ── Opposing club name / URL extraction ──────────────────────────────────────────────

def get_opponent_name(match_detail: dict, our_club_id: str) -> str:
    """Return the display name of the opposing club."""
    teams = match_detail.get("teams", {})
    for team_data in teams.values():
        club_url = team_data.get("@id", "") or team_data.get("url", "")
        if our_club_id.lower() not in club_url.lower():
            return team_data.get("name", "Unknown")
    return "Unknown"


def get_opponent_url(match_detail: dict, our_club_id: str) -> str:
    """
    Derive the Chess.com web URL for the opposing club from its API @id.
    API URL format: https://api.chess.com/pub/club/<slug>
    Web URL format: https://www.chess.com/club/<slug>
    """
    teams = match_detail.get("teams", {})
    for team_data in teams.values():
        api_url = team_data.get("@id", "") or team_data.get("url", "")
        if our_club_id.lower() not in api_url.lower() and "/club/" in api_url:
            slug = api_url.rstrip("/").split("/club/")[-1]
            return f"https://www.chess.com/club/{slug}"
    return ""


# ── Core data-collection logic ─────────────────────────────────────────────────

def fetch_club_matches(club_id: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    Fetch the top-level match listing for `club_id`.
    Returns a dict with keys: "finished", "in_progress", "registered".
    """
    url = f"{API_BASE}/club/{club_id}/matches"
    print(f"Fetching match list: {url}")
    return _get(url, user_agent)


def fetch_match_detail(match_url: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """Fetch the full detail object for a single match by its API URL."""
    time.sleep(REQUEST_DELAY)  # Courtesy delay to avoid rate-limiting.
    return _get(match_url, user_agent)


def collect_matches(club_id: str, cutoff: datetime, user_agent: str = DEFAULT_USER_AGENT) -> list[dict]:
    """
    Gather all finished, in-progress, and upcoming (registered) matches for
    the club that start on or after `cutoff`.  Returns a list of row dicts
    ready for a DataFrame.
    """
    raw = fetch_club_matches(club_id, user_agent)
    if not raw:
        print("ERROR: Could not retrieve match list. Check your CLUB_ID and network connection.")
        sys.exit(1)

    # Chess.com uses different key names across API versions.
    finished_list    = raw.get("finished", [])
    in_progress_list = raw.get("in_progress", [])
    upcoming_list    = raw.get("registered", [])   # "registered" = upcoming

    print(f"\nFound {len(finished_list)} finished, {len(in_progress_list)} in-progress, "
          f"and {len(upcoming_list)} upcoming match(es) in the full club history.")

    rows = []

    for status_label, match_list in [("Finished",    finished_list),
                                      ("In Progress", in_progress_list),
                                      ("Upcoming",    upcoming_list)]:
        print(f"\nProcessing {status_label} matches …")
        kept = 0

        for i, match_stub in enumerate(match_list, 1):
            match_url = match_stub.get("@id", "")
            if not match_url:
                continue

            # ── Date filter ────────────────────────────────────────────────────
            # Prefer the stub's own start_time to avoid an extra API call when
            # the match is clearly outside our window.  Stubs for "registered"
            # matches may not always include start_time — fall back to detail.
            stub_ts = match_stub.get("start_time") or match_stub.get("start_datetime")
            if stub_ts:
                stub_dt = datetime.fromtimestamp(int(stub_ts), tz=timezone.utc)
                if stub_dt < cutoff:
                    continue  # Skip — before our cutoff date.

            # ── Fetch full match detail ────────────────────────────────────────
            print(f"  [{i}/{len(match_list)}] Fetching: {match_url}")
            detail = fetch_match_detail(match_url, user_agent)
            if not detail:
                continue

            # ── Start time ────────────────────────────────────────────────────
            raw_ts = (detail.get("start_time")
                      or detail.get("start_datetime")
                      or stub_ts)
            if raw_ts:
                start_dt = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                # Re-check cutoff using the authoritative detail timestamp.
                if start_dt < cutoff:
                    continue
                start_str = start_dt.strftime("%Y-%m-%d %H:%M")
            else:
                start_str = "Unknown"
                start_dt  = None

            # ── Settings ──────────────────────────────────────────────────────
            settings = detail.get("settings", {})

            time_control_raw = (settings.get("time_control")
                                or detail.get("time_control", ""))
            days_per_move    = parse_days_per_move(str(time_control_raw))

            game_type   = settings.get("rules", detail.get("rules", "standard"))
            min_rating  = settings.get("min_rating") or detail.get("min_rating")
            max_rating  = settings.get("max_rating") or detail.get("max_rating")
            rating_range = format_rating_range(min_rating, max_rating)

            # ── Players ───────────────────────────────────────────────────────
            our_count, opp_count = get_player_counts(detail, club_id)
            opponent_name        = get_opponent_name(detail, club_id)
            opponent_url         = get_opponent_url(detail, club_id)

            kept += 1
            rows.append({
                "start_date":    start_str,
                "start_dt":      start_dt,   # kept for analytics; excluded from CSV
                "status":        status_label,
                "rating_range":  rating_range,
                "game_type":     game_type,
                "time_control":  days_per_move,
                "opponent":      opponent_name,
                "opponent_url":  opponent_url,
                "our_players":   our_count,
                "opp_players":   opp_count,
                "match_url":     api_url_to_web(match_url),
            })

        print(f"  → {kept} {status_label} match(es) after {cutoff.strftime('%Y-%m-%d')} cutoff.")

    return rows


# ── Analytics ─────────────────────────────────────────────────────────────────

def run_analytics(df: pd.DataFrame, club_id: str) -> None:
    """
    Print a text-based analytics and scheduling insights report.
    Covers team load, parameter trends, and scheduling gaps.
    """
    SEP = "=" * 70

    print(f"\n{SEP}")
    print("  CHESS.COM CLUB SCHEDULE ANALYTICS REPORT")
    print(f"  Club: {club_id}   |   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(SEP)

    # ── 1. Overview ───────────────────────────────────────────────────────────
    finished = df[df["status"] == "Finished"]
    in_prog  = df[df["status"] == "In Progress"]
    upcoming = df[df["status"] == "Upcoming"]

    print(f"\n{'─'*70}")
    print("1. OVERVIEW")
    print(f"{'─'*70}")
    print(f"  Finished matches    : {len(finished)}")
    print(f"  In-Progress matches : {len(in_prog)}")
    print(f"  Upcoming matches    : {len(upcoming)}")
    print(f"  Total matches       : {len(df)}")

    # ── 2. Team Load ──────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("2. TEAM LOAD")
    print(f"{'─'*70}")

    if not in_prog.empty:
        total_active = in_prog["our_players"].sum()
        print(f"\n  IN PROGRESS — Active player-boards commitment:")
        print(f"    Total active boards for our team : {total_active}")
        print(f"    Average team size (our side)     : {in_prog['our_players'].mean():.1f}")
        print(f"    Largest single match             : {in_prog['our_players'].max()} players "
              f"(vs {in_prog.loc[in_prog['our_players'].idxmax(), 'opponent']})")
        print(f"    Smallest single match            : {in_prog['our_players'].min()} players "
              f"(vs {in_prog.loc[in_prog['our_players'].idxmin(), 'opponent']})")

        # Flag lopsided matches (our count vs opponent count differs by >30%).
        in_prog_copy = in_prog.copy()
        in_prog_copy["size_diff"] = abs(in_prog_copy["our_players"] - in_prog_copy["opp_players"])
        lopsided = in_prog_copy[in_prog_copy["size_diff"] > 2]
        if not lopsided.empty:
            print(f"\n  ⚠  Lopsided matches (size difference > 2 boards):")
            for _, row in lopsided.iterrows():
                print(f"     vs {row['opponent']:<30}  "
                      f"Us: {row['our_players']}  |  Them: {row['opp_players']}")
    else:
        print("  No in-progress matches found.")

    if not upcoming.empty:
        print(f"\n  UPCOMING — Registered player commitments:")
        print(f"    Total upcoming registered boards (our team) : {upcoming['our_players'].sum()}")
        for _, row in upcoming.sort_values("start_date").iterrows():
            print(f"    {row['start_date']}  vs {row['opponent']:<30}  "
                  f"Us: {row['our_players']}  |  Them: {row['opp_players']}")
    else:
        print("  No upcoming matches found.")

    # ── 3. Parameter Trends ───────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("3. PARAMETER TRENDS")
    print(f"{'─'*70}")

    print("\n  Time Controls (days/move):")
    tc_counts = df["time_control"].value_counts()
    for tc, cnt in tc_counts.items():
        bar = "█" * cnt
        tag = " ← HEAVILY OCCUPIED" if cnt == tc_counts.max() and cnt > 1 else ""
        print(f"    {tc:<20} {cnt:>3} match(es)  {bar}{tag}")

    print("\n  Rating Ranges:")
    rr_counts = df["rating_range"].value_counts()
    for rr, cnt in rr_counts.items():
        bar = "█" * cnt
        tag = " ← HEAVILY OCCUPIED" if cnt == rr_counts.max() and cnt > 1 else ""
        print(f"    {rr:<20} {cnt:>3} match(es)  {bar}{tag}")

    print("\n  Game Types:")
    gt_counts = df["game_type"].value_counts()
    for gt, cnt in gt_counts.items():
        bar = "█" * cnt
        print(f"    {gt:<20} {cnt:>3} match(es)  {bar}")

    # ── 4. Weekly Load Distribution ───────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("4. WEEKLY LOAD DISTRIBUTION")
    print(f"{'─'*70}")

    dated = df[df["start_dt"].notna()].copy()
    if not dated.empty:
        dated["week"] = dated["start_dt"].dt.to_period("W").astype(str)
        weekly = dated.groupby("week").agg(
            match_count=("opponent", "count"),
            our_boards=("our_players", "sum")
        ).reset_index()
        print()
        print(f"  {'Week (Mon–Sun)':<22} {'Matches':>8} {'Our Boards':>12}")
        print(f"  {'─'*22} {'─'*8} {'─'*12}")
        for _, row in weekly.iterrows():
            print(f"  {row['week']:<22} {row['match_count']:>8} {row['our_boards']:>12}")
    else:
        print("  No date information available for weekly breakdown.")

    # ── 5. Scheduling Gaps ────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("5. SCHEDULING GAPS & RECOMMENDATIONS")
    print(f"{'─'*70}\n")

    gaps_found = False

    # Gap A — Under-represented time controls.
    all_common_tcs = {"1 day/move", "2 days/move", "3 days/move"}
    used_tcs = set(df["time_control"].unique())
    missing_tcs = all_common_tcs - used_tcs
    if missing_tcs:
        for tc in sorted(missing_tcs):
            print(f"  GAP: No current matches use '{tc}'. "
                  f"This is an open slot for a new match.")
        gaps_found = True

    # Gap B — Under-represented time controls (used but sparse).
    if not tc_counts.empty:
        min_tc_count = tc_counts.min()
        max_tc_count = tc_counts.max()
        if max_tc_count > 1 and min_tc_count < max_tc_count:
            sparse_tcs = tc_counts[tc_counts == min_tc_count].index.tolist()
            for tc in sparse_tcs:
                if tc in all_common_tcs:
                    print(f"  GAP: '{tc}' is under-represented ({min_tc_count} match). "
                          f"Room to add more matches at this time control.")
                    gaps_found = True

    # Gap C — Weeks with very low board load.
    if not dated.empty:
        weekly_our = dated.groupby("week")["our_players"].sum()
        low_threshold = weekly_our.mean() * 0.5  # Below 50% of average is a "light" week.
        low_weeks = weekly_our[weekly_our <= low_threshold]
        if not low_weeks.empty:
            for week, boards in low_weeks.items():
                print(f"  GAP: Week {week} has only {int(boards)} active/upcoming board(s) "
                      f"— well below the weekly average of {weekly_our.mean():.0f}. "
                      f"Good opportunity to schedule a new match.")
            gaps_found = True

    # Gap D — Open (unrestricted) rating range under-represented.
    open_count = (df["rating_range"] == "Open").sum()
    total      = len(df)
    if total > 0 and open_count / total < 0.25:
        print(f"  GAP: Only {open_count}/{total} matches are 'Open' (no rating limit). "
              f"Consider adding an open-rated match to welcome players of all strengths.")
        gaps_found = True

    # Gap E — Smallest upcoming match (ideal anchor to add adjacent match).
    if not upcoming.empty:
        smallest_up = upcoming.loc[upcoming["our_players"].idxmin()]
        print(f"\n  BEST UPCOMING SLOT: The upcoming match vs '{smallest_up['opponent']}' "
              f"(starts {smallest_up['start_date']}) has only {smallest_up['our_players']} "
              f"registered player(s) on our side — it's the lightest upcoming commitment, "
              f"making it a natural anchor date to open a new match nearby.")
        gaps_found = True

    if not gaps_found:
        print("  No obvious scheduling gaps detected — schedule looks well-balanced!")

    print(f"\n{SEP}\n")


# ── Entry point ────────────────────────────────────────────────────────────────

def main(club_id: str, cutoff_date: datetime = None, output_csv: str = None, user_agent: str = DEFAULT_USER_AGENT):
    if cutoff_date is None:
        cutoff_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    if output_csv is None:
        output_csv = "club_matches_raw.csv"

    print(f"Club Schedule Analyzer — Club: '{club_id}'")
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')} UTC\n")

    # ── 1. Collect match data ─────────────────────────────────────────────────
    rows = collect_matches(club_id, cutoff_date, user_agent)

    if not rows:
        print("\nNo matches found after the cutoff date. Nothing to report.")
        sys.exit(0)

    # ── 2. Build DataFrame ────────────────────────────────────────────────────
    df = pd.DataFrame(rows)

    # ── 3. Export raw CSV ─────────────────────────────────────────────────────
    # Build an =HYPERLINK() formula for the opponent column so that Excel and
    # Google Sheets render it as a clickable link when the CSV is opened.
    csv_df = df.copy()
    csv_df["opponent"] = csv_df.apply(
        lambda r: f'=HYPERLINK("{r["opponent_url"]}","{r["opponent"]}")'
                  if r["opponent_url"] else r["opponent"],
        axis=1,
    )
    csv_columns = [
        "start_date", "status", "rating_range",
        "game_type", "time_control", "opponent", "our_players",
        "opp_players", "match_url",
    ]
    csv_df[csv_columns].to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nRaw data exported → {output_csv}  ({len(df)} rows)")

    # ── 3. Print analytics report ─────────────────────────────────────────────
    run_analytics(df, club_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze a Chess.com club's match schedule and generate insights"
    )
    parser.add_argument(
        "club_id",
        help="Club ID from Chess.com (e.g., '1-day-per-move-club')"
    )
    parser.add_argument(
        "--cutoff", default=None,
        help="Cutoff date (YYYY-MM-DD) — only matches on or after this date. Default: 2026-01-01"
    )
    parser.add_argument(
        "--output", default="club_matches_raw.csv",
        help="Path for output CSV (default: club_matches_raw.csv)"
    )
    parser.add_argument(
        "--user-agent", default=DEFAULT_USER_AGENT,
        help=f"Custom User-Agent for API requests (default: {DEFAULT_USER_AGENT})"
    )
    args = parser.parse_args()
    
    cutoff = None
    if args.cutoff:
        try:
            cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"ERROR: Invalid date format '{args.cutoff}'. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    main(args.club_id, cutoff, args.output, args.user_agent)
