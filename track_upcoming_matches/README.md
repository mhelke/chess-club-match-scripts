# Track Upcoming Matches

Fetches and tracks upcoming matches for a Chess.com club.

## Usage

```bash
python track_upcoming_matches.py <club_id>
```

### Examples

```bash
# Track matches for a specific club
python track_upcoming_matches.py 1-day-per-move-club

# Save to custom locations
python track_upcoming_matches.py my-club --output matches.csv --prev matches_prev.csv

# Use a custom User-Agent
python track_upcoming_matches.py my-club --user-agent "MyBot/1.0"
```

## Output

Generates two CSV files (by default in the project root):
- `upcoming_matches.csv` – Current snapshot of upcoming matches
- `upcoming_matches_prev.csv` – Previous snapshot for comparison

## Display Sections

1. **New Matches** – Matches added since the last run
2. **Player Count Changes** – Changes in team roster sizes
3. **Calendar View** – Per-day breakdown with rating coverage and gaps

## Parameters

- `club_id` (required) – Chess.com club ID
- `--output` – Path for upcoming_matches.csv (default: PROJECT_ROOT/upcoming_matches.csv)
- `--prev` – Path for upcoming_matches_prev.csv (default: PROJECT_ROOT/upcoming_matches_prev.csv)
- `--user-agent` – Custom User-Agent for API requests

## Requirements

```bash
pip install requests pandas
```
