# Club Lookup

Builds a per-club summary from match data for quick reference when deciding which clubs to challenge.

## Usage

```bash
python club_lookup.py --input club_matches_raw.csv
```

### Examples

```bash
# Default usage
python club_lookup.py --input club_matches_raw.csv

# Filter to specific time control
python club_lookup.py --input club_matches_raw.csv --time-control "1 day/move"

# Custom output location
python club_lookup.py --input club_matches_raw.csv --output my_lookup.csv

# Combine options
python club_lookup.py --input data.csv --output lookup.csv --time-control "3 days/move"
```

## Output

Generates `club_lookup.csv` with one row per unique opponent club containing:

- **opponent** – Hyperlink to club's Chess.com page
- **total_matches** – Total matches vs this club
- **last_match_date** – Most recent or upcoming match date
- **active** – "Yes" if Upcoming or In Progress match exists
- **game_types** – Distinct game types (chess, chess960, etc.)
- **time_controls** – Distinct time controls accepted
- **rating_pref** – Preference band(s): Open / Low / Mid / High
- **rating_ranges** – All rating ranges accepted
- **avg_opp_roster** – Average opponent player count

## Parameters

- `--input` (required) – Path to club_matches_raw.csv
- `--output` – Path for output (default: PROJECT_ROOT/club_lookup.csv)
- `--time-control` – Optional time control filter (e.g., "1 day/move"). If omitted, all time controls included

## Requirements

```bash
pip install pandas
```
