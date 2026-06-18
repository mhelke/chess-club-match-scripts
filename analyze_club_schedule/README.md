# Analyze Club Schedule

Fetches and analyzes a Chess.com club's current match schedule to identify team load patterns, scheduling gaps, and opportunities.

## Usage

```bash
python analyze_club_schedule.py <club_id>
```

### Examples

```bash
# Analyze a club (generates club_matches_raw.csv + analytics report)
python analyze_club_schedule.py 1-day-per-move-club

# Custom output location
python analyze_club_schedule.py my-club --output my_matches.csv

# Filter to matches starting on or after a date
python analyze_club_schedule.py my-club --cutoff 2025-06-01

# All options combined
python analyze_club_schedule.py my-club --output data.csv --cutoff 2025-01-01
```

## Output

### 1. CSV File (club_matches_raw.csv by default)
Contains detailed match data with columns:
- **start_date** – Match start date and time
- **status** – Finished / In Progress / Upcoming
- **rating_range** – Min–max rating or Open
- **game_type** – chess or chess960
- **time_control** – 1 day/move, 3 days/move, etc.
- **opponent** – Hyperlinked club name
- **our_players** – Players from your club
- **opp_players** – Players from opponent club
- **match_url** – Link to the match

### 2. Analytics Report (printed to console)
Includes:
1. **Overview** – Match count by status
2. **Parameter Trends** – Time controls, rating ranges, game types
3. **Load Distribution** – Player counts and match frequency
4. **Weekly Load** – Per-week match and board counts
5. **Scheduling Gaps** – Recommendations for new matches

## Parameters

- `club_id` (required) – Chess.com club ID
- `--cutoff` – Date filter (YYYY-MM-DD), default: 2026-01-01
- `--output` – CSV output path (default: club_matches_raw.csv)
- `--user-agent` – Custom User-Agent for API requests

## Requirements

```bash
pip install requests pandas
```
