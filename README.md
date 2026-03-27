# rhea-cli

CLI wrapper for the public Rhea search and download interfaces.

## What is implemented

- Intent-oriented lookup commands for reactions, compounds, enzymes, proteins, publications, and free text.
- Master and directional Rhea ID resolution.
- Directional `RXN` and `RD` downloads from ExPASy.
- Exhaustive first-class normalization for every documented Rhea table column.
- Local higher-order views for participants, cross-references, neighborhood, grouped enzymes, grouped protein counts, explanation, and mixed-term resolution.
- Current and historical release/archive inspection workflows.
- Resumable local paging over full verified web exports for stateful traversal.
- Machine-readable `json`, `jsonl`, `tsv`, and shell-friendly text output where applicable.

## Live API behavior this tool is built around

These behaviors were verified on March 27, 2026:

- `https://www.rhea-db.org/rhea/?query=...&columns=...&format=tsv&limit=...` works for programmatic search.
- `https://ftp.expasy.org/databases/rhea/ctfiles/rxn/<id>.rxn` and `.../rd/<id>.rd` work for directional reactions.
- `https://ftp.expasy.org/databases/rhea/tsv/rhea-directions.tsv` maps master IDs to directional IDs.
- Direct entry fetches like `https://www.rhea-db.org/rhea/10000` and `https://www.rhea-db.org/rhea/10000.rxn` returned a Cloudflare challenge to non-browser clients during implementation, so this CLI does not depend on them.

Important detail:

- Master reactions such as `RHEA:10000` do not have direct RXN/RD files.
- Their directional counterparts do, for example `RHEA:10001`, `RHEA:10002`, and `RHEA:10003`.

## Install

```bash
pip install .
```

## Core commands

```bash
rhea reaction 10000
rhea compound CHEBI:15377
rhea enzyme EC:3.5.1.50
rhea protein P11562
rhea publication 21429607
rhea term amidase
rhea directions 10000
rhea download 10000 --direction lr --file-format rxn
rhea explain 10000
rhea resolve 10000 CHEBI:15377 P11562 amidase
```

## Command groups

### Entity lookups

- `rhea reaction <id>`
- `rhea compound <chebi>`
- `rhea enzyme <ec>`
- `rhea protein <uniprot>`
- `rhea publication <pubmed>`
- `rhea term <text>`

### Direction and identity

- `rhea directions <id>`
- `rhea counterparts <id>`
- `rhea canonicalize <id>`

### Relationship and extraction

- `rhea participants <id>`
- `rhea xrefs <id>`
- `rhea neighborhood <chebi>`
- `rhea enzymes-for <chebi>`
- `rhea proteins-for <chebi>`

### Downloads and shell helpers

- `rhea download <id> --file-format {rxn,rd}`
- `rhea equation <id>`
- `rhea ids <query>`
- `rhea table <query>`
- `rhea grep <text>`
- `rhea explain <id>`
- `rhea resolve <terms...>`
- `rhea columns`

### Release and archive workflows

- `rhea release current`
- `rhea release list`
- `rhea release files <category>`
- `rhea release bundle [release]`
- `rhea archive ls [path]`
- `rhea archive members <archive>`
- `rhea archive download <path-or-url> <output>`

### Compatibility commands

- `rhea search ...`
- `rhea fetch ...`

## Examples

```bash
rhea reaction 10000 --format json
rhea compound 15377 --limit 5 --format text
rhea enzyme 3.5.1.50 --format json
rhea protein P11562 --format json
rhea publication 21429607 --format json
rhea participants 10000 --format json
rhea xrefs 10000 --format text
rhea counterparts 10002
rhea canonicalize 10003
rhea equation 10000
rhea ids 'chebi:15377' --limit 10
rhea grep amidase --limit 10
rhea neighborhood CHEBI:15377 --limit 20
rhea enzymes-for CHEBI:15377 --format text
rhea proteins-for CHEBI:15377 --format json
rhea download 10000 --direction bi --file-format rd
rhea resolve 10000 CHEBI:15377 EC:3.5.1.50 P11562 21429607 amidase
rhea columns --format text
rhea release current --format json
rhea release list --format text
rhea release files tsv --format text
rhea archive members tsv/rhea-tsv.tar.gz --limit 20 --format json
```

`--columns` is passed through to Rhea table queries, so documented Rhea table columns outside the default set are usable without changing this tool.

For JSON output, documented Rhea columns are normalized into typed values:

- `chebi`, `chebi-id`, `ec`, `pubmed`, and reaction cross-references become lists
- `go` becomes a list of `{id, label}`
- `uniprot` becomes an integer count

The raw TSV strings are still preserved in `items`; normalized values are exposed in `normalizedItems`.

## Stateful traversal

The documented web table export supports `limit` but not server-side cursor parameters. This CLI adds client-side paging and resumable traversal by retrieving the full verified export and paging locally.

```bash
rhea search '' --columns rhea-id,equation --page-size 100 --page 1 --format json
rhea search '' --columns rhea-id,equation --page-size 100 --cursor-file /tmp/rhea.cursor.json --format json
rhea search '' --columns rhea-id,equation --page-size 100 --cursor-file /tmp/rhea.cursor.json --resume --format json
```

## Configuration

Environment variables:

- `RHEA_EMAIL`: optional contact address appended to the user agent.
- `RHEA_USER_AGENT`: override default user agent prefix.
- `RHEA_BASE_URL`: override `https://www.rhea-db.org`.
- `RHEA_FTP_BASE_URL`: override `https://ftp.expasy.org/databases/rhea`.
- `RHEA_TIMEOUT_SECONDS`: override the default timeout of 30 seconds.

## Verification

```bash
python -m unittest discover -s tests -v
python -m rhea_cli --help
python -m rhea_cli reaction 10000 --format json
python -m rhea_cli compound CHEBI:15377 --limit 3
python -m rhea_cli download 10000 --direction lr --file-format rxn
```
