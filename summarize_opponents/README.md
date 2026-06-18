# Summarize Opponents

Generates a detailed summary of opponents from match data, grouped by opponent, game type, and rating range.

## Usage

```bash
python summarize_opponents.py --input club_matches_raw.csv
```

### Examples

```bash
# Default usage
python summarize_opponents.py --input club_matches_raw.csv

# Custom output location
python summarize_opponents.py --input data.csv --output summary.csv

# Both options
python summarize_opponents.py --input matches.csv --output opponent_summary.csv
```

## Output

Generates `club_opponent_summary.csv` with one row per unique (opponent × game_type × rating_range) combination:

- **opponent** – Hyperlink to club's Chess.com page
- **game_type** – chess or chess960
- **rating_range** – Open, ≤1400, 1000–1500, etc.
- **opp_roster_size** – Opponent player count from most relevant match
- **match_date** – Start date of that match
- **status** – Upcoming / In Progress / Finished
- **total_matches** – Total matches in this group

### Match Selection Priority

When multiple matches exist for a group, the "most relevant" is selected as:
1. **Status**: Upcoming > In Progress > Finished
2. **Date**: Most recent within the status

## Parameters

- `--input` (required) – Path to club_matches_raw.csv
- `--output` – Path for output (default: PROJECT_ROOT/club_opponent_summary.csv)

## Requirements

```bash
pip install pandas
```
