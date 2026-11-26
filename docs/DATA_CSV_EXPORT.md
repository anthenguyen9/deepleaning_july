# FoodLens CSV export

Snapshot: `datasets/csv/2026-11-26/`.

The export contains 92 CSV files from the operational database, the separate
research database, training/evaluation input files and the location catalog.
`manifest.csv` records row counts, column counts, file sizes and SHA-256 checksums.
`sources.csv` identifies each input and its snapshot checksum. Both SQLite
databases were read through online backups to memory, including committed WAL data.

| Folder | Contents |
| --- | --- |
| `operational/` | Public app snapshot: 146 restaurants, 14,206 reviews, 9,989 model analyses and 100 anonymized study responses |
| `research/` | Research snapshot: 138 restaurants, 7,331 reviews and 5,170 saved annotations |
| `training/` | ViTASA restaurant data and converted train/dev/test files, historical FoodLens annotations, rating-derived labels and retrieval evaluation inputs |
| `geography/` | Administrative-unit and OpenStreetMap street source catalogs |

## CSV conventions

- Files use UTF-8 with BOM, comma separators and standard quoted CSV cells.
  Newlines and commas inside review text remain within the same cell.
- Use Excel's **Data → From Text/CSV** and import IDs as text. Preserve identifiers
  such as `restaurant_id`, `review_id` and `document_key` when joining tables.
- Empty cells represent missing values. `labels_available=0` means labels were
  not supplied. When it is `1`, the fifteen aspect/polarity columns contain 0/1.
  `labels` preserves the source label order using `|` as a separator.
- Join reviews to restaurants by `restaurant_id = restaurants.id`. Review keys
  are the pair `(restaurant_id, id)`, not the review ID alone. Annotation tables
  use `(restaurant_id, review_id)`.
- `published_at`, `date_text`, `raw_iso_date` and `raw_iso_date_of_last_edit`
  preserve stored date information. This export does not invent a day when the
  source only provides a month, year or relative date. `fetched_at` is the
  collection time, not the original review time.
- Nested source attributes, evaluation pools, original ViTASA spans and source
  metadata use `record_index`, `field_path`, `value_type`, `value` columns.
  These CSV files preserve nested structure without putting JSON blobs in cells.
- Dense vectors are partitioned into files of at most 1,000 records. Columns
  `v0000` onward contain float32 components at round-trip precision. These are
  stored caches with their original model/hash, including older entries. Rebuild
  an index before assuming it matches the current review-document table.
- Text cells that could be interpreted as Excel formulas receive a leading
  apostrophe. Email addresses and phone-like strings in review/free-text values
  are replaced with explicit redaction markers. Public business phone fields in
  `restaurants` attributes remain business contact data.

## Annotation and split provenance

The research annotation table contains 3,332 records attributed to `admin`,
109 to `ai:gemini-3.6-flash` and 1,729 to
`ai:local-svm-df8559348c34-star-rule`. `annotation_origin` distinguishes AI records
from account annotations whose human authorship has not been independently
verified. Exporting a row does not establish that its label is human gold.

The existing `training/gold/` name and original metadata are preserved to keep
the input files traceable. Some historical metadata describes human annotation
while also listing AI models. Treat this as source metadata, not a verification
made by this export. Rating-derived labels remain in `training/rating_weak/`.
Unfilled independent-annotator forms retain their missing labels.

The operational and research snapshots overlap. Keep their provenance when
combining them and deduplicate by the composite review key. The supplied
train/dev/test assignments remain unchanged; do not concatenate them into one
training set for an evaluation on the same records. The retrieval mapping CSV is
included for reproducibility and reveals the original blinded candidate mapping.

## Publication scope

`source_inventory.csv` lists every database table, source row count, whether it
was exported and the reason for any exclusion. Credentials, account identities,
password hashes, personal profiles, chats, feedback, personal search history,
raw API caches and SQLite/FTS internals are excluded. Raw provider payloads,
pagination tokens and diagnostic error text are omitted from published fields.

Study responses retain numeric scores, consent, completion flags, duration and
sample number under anonymous participant IDs. Participant names/codes, free-text
responses and submission timestamps are omitted. This is a data export, not a
new assessment of study quality or evaluator identity.

The upstream ViTASA license is included as `VITASA_LICENSE.txt`. It applies to
the upstream material as supplied and does not relicense Google Maps reviews.
Review source URLs and the original training-data source manifest are retained.

## Recreate and verify

From the repository root with the project's Python environment:

```powershell
python -m scripts.export_csv_snapshot --output datasets/csv/YYYY-MM-DD
```

Choose a new output directory. The exporter refuses to replace an existing
snapshot. It checks source row counts, CSV round trips, field widths, finite
numbers, vector dimensions, configured-secret exclusion and file sizes.
`validation.csv` records the completed CSV checks. No collection or AI API is
called during export, and the live databases are not modified.
