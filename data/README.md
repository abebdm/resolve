# data/

Local card data lives here and is **never committed** (see `.gitignore`). The snapshot date is
recorded in `docs/rules/README.md`.

| File | Contents |
|---|---|
| `oracle-cards.json` | Scryfall's "Oracle Cards" bulk file: one object per Oracle card. |
| `rulings.json` | Scryfall's "Rulings" bulk file. |
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
2. Download **Oracle Cards** (a file named like `oracle-cards-20261018090211.json`) and
   **Rulings** (`rulings-20261018090034.json`). Keep the file names: they carry the publication
   time.
3. Run:

   ```bash
   uv run python tools/fetch_scryfall.py --import-files path/to/oracle-cards-*.json path/to/rulings-*.json
   ```

   If the files were renamed, add `--updated-at 2026-10-18T09:02:11Z` (their publication time,
   shown on the bulk-data page).
