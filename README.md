# Chess Club Match Scripts

A collection of Python scripts for Chess.com club admins to manage and analyze club matches.

## Who this is for

These scripts are designed for **Chess.com club administrators** who want to:
- Track upcoming matches and roster changes
- Analyze opponent clubs and their preferences
- Build reference guides for challenge decisions

## Scripts

### [track_upcoming_matches](track_upcoming_matches/)
Fetches and displays all upcoming matches for your club with detailed breakdowns by day, game type, and rating coverage. Shows new matches since the last run and any player count changes.

**Usage**: `python track_upcoming_matches.py <club_id>`

### [club_lookup](club_lookup/)
Generates a quick-reference summary of all opponent clubs you've matched against, including match counts, game types, time controls, and rating preferences. Helpful for deciding who to challenge next.

**Usage**: `python club_lookup.py --input club_matches_raw.csv`

### [summarize_opponents](summarize_opponents/)
Creates a detailed breakdown of opponents grouped by game type and rating range, showing the most relevant match for each combination. Useful for understanding your opponent lineup.

**Usage**: `python summarize_opponents.py --input club_matches_raw.csv`

## Getting Started

1. Install dependencies:
   ```bash
   pip install requests pandas
   ```

2. See the README in each script folder for detailed usage and examples.

## Requirements

- Python 3.7+
- `requests` (for API calls)
- `pandas` (for data processing)

## License

MIT License - See [LICENSE](LICENSE) for details.

