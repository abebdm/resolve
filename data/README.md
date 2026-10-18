# data/

Local card data lives here and is **never committed** (see `.gitignore`). The snapshot date is
recorded in `docs/rules/README.md`. The bulk files are stored exactly as Scryfall serves them:
gzip-compressed JSON Lines (one JSON object per line).

| File | Contents |
|---|---|
| `oracle-cards.jsonl.gz` | Scryfall's "Oracle Cards" bulk file: one card object per Oracle ID. |
| `rulings.jsonl.gz` | Scryfall's "Rulings" bulk file. |
| `snapshot.json` | Manifest written by the fetch tool: each file's publication time, source and SHA-256. The loader refuses files that don't match it. |

## Getting the snapshot

```bash
uv run python tools/fetch_scryfall.py            # download from Scryfall's API
uv run python tools/fetch_scryfall.py --update   # deliberately replace an existing snapshot
```

The tool validates both files before replacing anything, then records the snapshot in
`docs/rules/README.md`. The card data and the rules are updated together and deliberately, so an
existing snapshot is only replaced with `--update`.

**Without access to Scryfall's API** (for example from a restricted network), download the files
by hand and import them:

1. Open <https://scryfall.com/docs/api/bulk-data>.
2. Download **Oracle Cards** (a file named like `oracle-cards-20261017210157.jsonl.gz`) and
   **Rulings** (`rulings-20261017210032.jsonl.gz`). Keep the file names: they carry the publication
   time.
3. Run:

   ```bash
   uv run python tools/fetch_scryfall.py --import-files path/to/oracle-cards-*.jsonl.gz path/to/rulings-*.jsonl.gz
   ```

   If the files were renamed, add `--updated-at 2026-10-17T21:01:57Z` (their publication time,
   shown on the bulk-data page).
