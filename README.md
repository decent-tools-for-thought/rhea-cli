<div align="center">

# rhea-cli

[![Release](https://img.shields.io/github/v/release/decent-tools-for-thought/rhea-cli?sort=semver&color=0f766e)](https://github.com/decent-tools-for-thought/rhea-cli/releases)
![Python](https://img.shields.io/badge/python-3.11%2B-0ea5e9)
![License](https://img.shields.io/badge/license-MIT-14b8a6)

Command-line client for Rhea search, relationship lookup, directional downloads, release inspection, and archive browsing.

</div>

> [!IMPORTANT]
> This codebase is entirely AI-generated. It is useful to me, I hope it might be useful to others, and issues and contributions are welcome.

## Map
- [Install](#install)
- [Functionality](#functionality)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Credits](#credits)

## Install
$$\color{#0EA5E9}Install \space \color{#14B8A6}Tool$$

```bash
pip install .
rhea --help
```

## Functionality
$$\color{#0EA5E9}Entity \space \color{#14B8A6}Lookup$$
- `rhea reaction|compound|enzyme|protein|publication|term`: resolve reactions and related biology entities.
- `rhea directions|counterparts|canonicalize`: move between master and directional reaction IDs.

$$\color{#0EA5E9}Graph \space \color{#14B8A6}Browse$$
- `rhea participants|xrefs|neighborhood`: inspect reaction participants and graph neighbors.
- `rhea enzymes-for|proteins-for`: find enzymes and proteins linked to one ChEBI term.
- `rhea explain|resolve`: summarize and normalize mixed lookup inputs.

$$\color{#0EA5E9}Table \space \color{#14B8A6}Export$$
- `rhea ids|table|grep|columns`: work with Rhea table-style query exports and column selection.
- `rhea equation`: print a reaction equation summary.
- `rhea download <id> --file-format rxn|rd`: fetch directional reaction files.

$$\color{#0EA5E9}Release \space \color{#14B8A6}Archive$$
- `rhea release current|list|files|bundle`: inspect published releases and downloadable file groups.
- `rhea archive ls|members|download`: browse and extract archive contents.
- `rhea search` and `rhea fetch`: compatibility entrypoints over the same underlying workflows.

## Configuration
$$\color{#0EA5E9}Tune \space \color{#14B8A6}Defaults$$

Environment variables:

- `RHEA_EMAIL`
- `RHEA_USER_AGENT`
- `RHEA_BASE_URL`
- `RHEA_FTP_BASE_URL`
- `RHEA_TIMEOUT_SECONDS`

Notes:

- Master reactions such as `RHEA:10000` do not have direct `RXN` or `RD` files.
- Directional counterparts do, such as `RHEA:10001`, `RHEA:10002`, and `RHEA:10003`.
- The CLI uses the documented query and release surfaces rather than browser-only entry pages.

## Quick Start
$$\color{#0EA5E9}Try \space \color{#14B8A6}Lookup$$

```bash
rhea reaction 10000
rhea compound CHEBI:15377
rhea directions 10000
rhea participants 10000 --format json
rhea xrefs 10000 --format text
rhea download 10000 --direction lr --file-format rxn
rhea release current --format json
rhea archive members tsv/rhea-tsv.tar.gz --limit 20 --format json
```

## Credits

This client is built for Rhea and is not affiliated with Rhea or ExPASy.

Credit goes to the Rhea project and ExPASy for the reaction data, download surfaces, and documentation this tool depends on.
