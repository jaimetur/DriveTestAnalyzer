# Technical considerations

This article collects rules that affect data interpretation, performance, persistence and generated output. Read it before comparing DriveTest Analyzer with another analytical tool.

> [!IMPORTANT]
> **Source values and presentation.** Stored source values and the labels the tool shows are different layers. Operators, Vendors and Campaigns are shown everywhere with their Operator, Vendor and Campaign Maps labels, and a mapped selection matches every source spelling; only Preview Dataset shows the source values. Each value of the CDRs is assigned to its label in Workspace Config, so values share a label (and are added up as one) only when they are explicitly given the same one. The maps never rewrite uploaded workbooks or stored CDR values.

> [!NOTE]
> **Compare equivalent selections.** Match CDRs, NR Mode, filters, aggregation levels and missing-value rules before comparing results with another tool.

> [!TIP]
> **Caches and backups.** Caches accelerate views and can be rebuilt. Preserve databases and raw input when a recoverable backup is required.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Storage boundaries | [Open section](#storage-boundaries) |
| Processed and derived columns | [Open section](#processed-and-derived-columns) |
| Operator normalisation | [Open section](#operator-normalisation) |
| NR Mode and radio-access selection | [Open section](#nr-mode-and-radio-access-selection) |
| Test result semantics | [Open section](#test-result-semantics) |
| Campaign ordering | [Open section](#campaign-ordering) |
| Template execution semantics | [Open section](#template-execution-semantics) |
| Multivendor calculation and remapping | [Open section](#multivendor-calculation-and-remapping) |
| Interactive previews and PPT preparation | [Open section](#interactive-previews-and-design-preparation) |
| Filtered dataset preview | [Open section](#filtered-dataset-preview) |
| Background jobs and output | [Open section](#background-jobs-and-output) |
| Import, export and server transfer | [Open section](#import-export-and-server-transfer) |
| Performance and scale | [Open section](#performance-and-scale) |

## Storage boundaries

DriveTest Analyzer separates global configuration from workspace data.

### Global configuration

Stored below `APP_CONFIG_DIR`:

- `application.db`: users, roles, workspace permissions and server-transfer offers.

### Workspace data

Stored below `APP_DATA_DIR/workspaces/<workspace>/`:

- `<workspace>.db`: datasets, profiles, audit events, PPT definitions and selections, Auto-calculated Fields, complete Report Templates in `report_templates`, and materialised reporting rows.
- `input/`: uploaded source files.
- `output/reports/ppt-designs/`: PPT Designer jobs and their persistent PNG, tooltip and Canvas-model assets.
- `output/reports/cdr-analysis/`: CDR Analysis PowerPoint and Word exports.
- `output/reports/network-insights/`: Summary Network Insights PowerPoint and Word exports.
- `output/reports/reports-old/` and `output/reports/reports-charts-old/`: the PowerPoint reports and Chart Sets of a reports module of earlier versions, kept as they were (no module writes there any more).
- `output/reports/reporting-jobs/`: Reporting Job runs, one folder per run with its artifacts.
- `.cdr-store/`: the [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) of each CDR (Parquet files and a manifest) and the catalogs of views for other tools; it travels with the workspace database in backups, packages and transfers. `.cdr-store/nq/` holds a Parquet copy of the NQ Call Population Counts table for the failure panels of Non-Qualified Calls, written again from the table when it is missing.
- `.cache/`: the caches of the modules, one folder each: `scoring/` (the Scoring Trends and Points Lost Maps that Saved Filters share), `network-insights/` (the cells of each inventory snapshot and the prepared panels), `ppt-designer/` (the preparations of the PPT Designs and the models of their charts) and `bundle-reports/` (the sections and documents of the Bundle Report Templates kept for the next exports). They are worked out again when missing: left out of backups, packages and transfers, moved with the workspace when it is renamed and deleted with it. The cache folders of earlier versions (`.scoring-cache`, `.network-insights-cache`, `.ppt-designer-cache` and `output/reports/bundle-reports/cache`) move to it the first time the workspace opens (App Event `workspace_cache_folders_moved`).

Workspaces, backups and transfer packages created with the former layout (module folders directly below `output/` and loose documents in `output/reports/`) are moved to these folders the first time the workspace is opened, and the job paths stored in the workspace database follow them.

Application-level derived data lives below `APP_DATA_DIR`: `transfer-packages/` holds temporary/recoverable portability archives, `scheduled-backups/` is the default Super Admin backup destination and `.map-tiles-cache/openstreetmap/` stores regenerable map tiles.

The workspace registry is local to the deployment. Full Environment imports rebuild it from the imported workspaces instead of retaining source-server absolute paths. Report Template import, export, backup and transfer packages use CSV as a portable representation; the live templates remain database-backed and current flows remove obsolete `slides-templates` directories. See [Project Structure → Persistent data layout](project-structure.md#persistent-data-layout) for the complete ownership tree.

## Processed and derived columns

The importer preserves source fields and adds normalised fields used across modules. Common examples include:

- `Campaign`, preserving source text; filters and chart labels present recognised values with the workspace [Campaign Maps](workspace-config.md#campaign-maps), by default as `YYYY-Qn`, `YYYY-Qn-NSA` or `YYYY-Qn-SA`.
- `Operator`, preserving source values; configured aliases supply canonical labels for charts and comparisons.
- `Operator_Vendor`, the `<Operator>_<Vendor>` identity populated by explicit vendor mapping (and `Vendor_Operator`, the same identity as `<Vendor>_<Operator>`, derived when the CDRs are read), and `Vendor`, which removes a recognised operator prefix for real vendors. Both store `Operator - All` for operators without an assigned vendor. Workspaces created before these names are migrated once at startup (`Vendor` → `Operator_Vendor`, `Vendor_Only` → `Vendor`), together with their stored filter values and Report Templates.
- `Call Family`, derived from call/session mode.
- `Test Family`, derived from the available test type/name fields.
- `Rate Bucket`, calculated for distribution charts from configured bucket limits.

Derived preview columns are visually distinguished from source columns. They do not imply that the original workbook contained those headings.

### Auto-calculated Fields and combined tables

Auto-calculated Fields are workspace definitions. A field has a name, selected source datasets, a fallback (a fixed value, the value of other fields, or both in that order) and either ordered case-insensitive rules (each one an AND/OR condition and its result, kept as written) or a nested Tableau-style `IF / THEN / ELSEIF / ELSE / END` expression. It is materialised only in the individual and combined CDR tables for its selected sources, and never takes the name of a column the application keeps there (such as `NR_Mode`).

The same parsed decision tree drives in-memory previews and parameterized SQLite materialization (with SQLite functions for case folding, numbers and `MATCHES`) so nested-branch and fallback semantics remain identical. Each update compares the definitions with those the tables hold (recorded in the workspace state `calculated_dimensions_materialized` after each complete update) and rewrites only the changed fields and the fields that read them; a CDR table that already holds them is not touched. For a CDR whose columnar copy is its only store, the fields are worked out on the copy (`cdr_store.change_copy_columns`): the columns they read are read with DuckDB, the fields worked out as when the CDR is processed, and the copy rewritten part by part with their columns, its empty table following with `ALTER TABLE` and its manifest with the new columns, so the copy stays its store and the CDR is never put back in SQLite nor copied again.

Combined reporting tables are intentionally compact. They always retain reporting-core fields, Preview filter fields, source fields required by applicable Auto-calculated Field rules and resulting calculated fields. Other template-requested source fields are added lazily when a chart/report first requires them. This avoids eagerly copying every source column for every template, which would make imports and template changes unnecessarily expensive.

Materialization and combined-table recreation run in background jobs. Recreate rebuilds a CDR type from the ready individual datasets it includes (Final CDRs and the Weekly and Daily CDRs no Final CDR replaces), reloads an inconsistent individual store from its source file when available, and verifies both per-dataset and total counts.

## Operator normalisation

Report-facing operator aliases are resolved consistently without rewriting the source workbook.

- Vodafone spellings resolve to `VF`.
- Telefónica/O2 spellings resolve to `O2`.
- Three, `3` and `Three UK` resolve to `3`.
- Recognised EE spellings resolve to `EE`.

Normalisation is case-insensitive and avoids ambiguous fragments. For example, `H3G` is not treated as Three because it can refer to unrelated vendor/technology text.

## NR Mode and radio-access selection

NSA/SA selection chooses CDRs: every row keeps the NR Mode of its CDR (set when the CDR is uploaded, see [NR Mode](workspace-management.md#nr-mode)), rather than a row-level RAT or Call Mode classification.

- A Design, a Reporting job and the template editor previews read the CDRs of their NR Mode and every Data, Voice and Speech test of them, whatever RAT or call mode a test ran on: an EPS fallback (EPSFB) call of an SA CDR is an SA test.
- Valid Data attempts remain available even when a sampled radio-access value records fallback. This prevents an otherwise valid data test from disappearing solely because one sample is LTE.
- Report Templates have no NR Mode: the NR Mode is part of the selection of the Design that uses a template (NSA, SA or NSA & SA), and the titles name it with `{NR Mode}` and `{NR Mode Name}`. The combined CDR tables keep the NR Mode of the CDR of each row in their `NR_Mode` column (the **NR Mode** field of filters, splits and legends), added and filled once per CDR in the background when a workspace opens after the update and corrected on its rows when the NR Mode of a CDR changes. PPT Designer does not expose Technology as an adaptive filter, while the separate RAT filter can restrict explicit `RAT_A`, `RAT` or `Sample_RAT_A` values.
- Missing radio values are not silently relabelled as a recognised technology.

When a chart looks incomplete, compare its chart-filtered dataset with the source RAT and Call Mode fields and with the NR Mode of the CDRs it reads.

## Test result semantics

Charts must not treat every unknown result as a failure.

- Empty, null and NaN results are excluded from categorical result calculations.
- Template filters can explicitly restrict accepted states, for example:

```text
Test_Result IN (Completed, Dropped, Failed);
```

- Values outside that list, such as `Cutoff`, are excluded by the template rule rather than hardcoded globally.
- Conditions use the real field value after ordinary normalisation; substring accidents such as treating `Not Completed` as `Completed` must be avoided.

This design keeps the business rule visible in the template and makes comparisons with Tableau or another source reproducible.

## Campaign ordering

Every chart, table, legend and PowerPoint or Word report shows a campaign as its year (two digits) and quarter, followed by its radio mode when it has one: **26-Q2**, **26-Q2-NSA** or **26-Q2-SA** (for example `UK_Q2_SA_2026`, `2026 Q2 SA` or `2026-Q2_SA` all read `26-Q2-SA`). Values without a year and quarter are shown as they are. Filters keep the full campaign, and the Excel and CSV exports keep the original values.

Campaigns are ordered chronologically from oldest to newest; inside a quarter, the campaign without a mode comes first, then NSA, then SA. Values without a year and quarter come first, by name. These are the defaults: the label format, the order inside a quarter and exceptions for campaigns that do not follow the pattern are set per workspace in [Campaign Maps](workspace-config.md#campaign-maps).

Example:

```text
25-Q4 → 26-Q1 → 26-Q2 → 26-Q2-NSA → 26-Q2-SA
```

## Template execution semantics

Template filters are parsed as ordered, semicolon-terminated conditions joined with logical AND. Rows and Columns are ordered dimensions, so reversing their selection changes the grouping hierarchy. Legends derive their content from the chosen dimension, filter, threshold or bucket rule, and side legends reserve plot space.

These contracts are shared by PPT Designer, Chart Builder and Template Editor so a saved definition has the same meaning in previews and generated output. The authoring syntax, operators, examples, aggregation behaviour and legend rules are centralized in [PPT Designer → Report Template reference](ppt-designer.md#report-template-reference).

## Multivendor calculation and remapping

Vendor mapping is performed explicitly in Workspace and stored on the CDR before Vendor Comparison is enabled.

### CDR lookup key

The mapping logic takes the first and last usable Global Cell ID from available fields such as:

- `Cell_ID_A`
- `Cell_IDs_A`
- `Cell_ID`
- `Global CI`
- `GCID`, `GCI`, `CGI` or `ECI`

Case and separator variations are accepted.

### Vodafone mapping

VFUK mappings materialise `GCID` as:

- 4G: the ECI, `eNodeB ID × 256 + Cell ID`
- 5G: the NCI, `gNodeB ID × 16384 + Cell ID` (22-bit gNodeB IDs; a `gNodeB ID Length` column changes the multiplier to 2^(36 − length))

The `Cell ID` is the identity the cell broadcasts and the CDRs report. Huawei and Nokia cells also carry a different internal `Local Cell ID`, used only when a row has no `Cell ID`.

### Three mapping

3UK mappings use `Cid__ECI` or `CId___ECI` as the materialised `GCID`.

### Resolution rules

Every selected inventory (VFUK and 3UK Multivendor Mappings and Network Inventories, Cell Configuration KMZ packages included) is normalised into the **Inventory Cells** table: each cell with its technology, owner `Network` (the inventory's Operator when it has no Network column: Vodafone for VFUK, 3 for 3UK), `Host Network`, vendor, site, identity and position. The first and last cells of each sample are looked up there:

- only among the cells of the networks that can serve the sample's Operator, its own network first (Workspace Config → Serving Networks; by default Vodafone and Three serve each other through eMOCN, Lebara is served by both and every other Operator by its own network);
- in the snapshot whose date is closest to the CDR's measurements (the median start time of its samples, else the date in its file name), the newest on a tie;
- ignoring cells farther from the sample's position than the maximum serving distance (30 km by default), since a global cell identity only identifies a cell within its Operator.

Vodafone UK (`Vodafone_`), Three UK (`3_`) and every other Operator (its own name as prefix, for example `Vodafone VoNR_`, `VF_SA_` or `O2 (UK)_`) resolve the first and last cell with the same rule, stored in `Operator_Vendor`:

- Same first/last vendor → `<Operator>_<Vendor>`.
- Ericsson at either end and a different or missing vendor at the other → `<Operator>_Ericsson (Mixed)`.
- Any other different or missing combination → `<Operator>_Mixed (non-Ericsson)`.
- No endpoint found in the snapshots → `<Operator>_Unknown`.

Operators that no selected snapshot serves (EE without its own inventory) store `<Operator> - All`. `Vendor` keeps the vendor alone (`Ericsson`, `Ericsson (Mixed)`, `Mixed (non-Ericsson)`) and `Vendor_Operator`, derived when the CDRs are read, the same identity as `<Vendor>_<Operator>`. The cell that served the start of each sample fills `Serving_Network`, `Serving_Host_Network`, `Serving_Site_ID`, `Serving_eMOCN_Scenario`, `Serving_Distance_km` and `Serving_Inventory_Snapshot`.

### Remapping

Map CDRs again to apply a newer mapping; the new result replaces the previous one without a prior Clear. Mapping and clearing are background operations and can be applied to several CDRs. Each mapped CDR keeps a signature of what its Vendor was calculated from (the mapping rule version, the Serving Networks and every inventory snapshot with its revision and date); the Map dialog marks the CDRs with another signature as **Vendor mapping outdated** and selects them.

For Vendor Comparison, the renderer also appends this effective filter without altering the stored template:

```text
vendor NOT CONTAINS (Mixed, Other);
```

## Interactive previews and PPT preparation

Chart Builder and PPT Templates Editor use the shared Interactive Preview. PPT Designer uses the same chart contracts in its live viewer, expanded viewer and historical Charts Panel, while preparing one synchronized dataset selection for the complete Design.

Live charts draw their Canvas models in the user's browser. Server-side PPT exports send those same models through a persistent Node/Chromium renderer, which keeps chart geometry and semantic tooltips aligned with the interactive view. Docker includes these runtime dependencies; source deployments using `canvas` need Node.js, a supported Chromium-family browser and the WebSocket module.

`DRIVETEST_ANALYZER_CHROMIUM` can select an explicit browser executable, while `DRIVETEST_ANALYZER_REPORT_CHART_RENDERER=pil` selects the legacy painter.

The shared preview cache separates expensive data work from presentation work:

- Dataset combination depends on selected datasets.
- Filtered rows depend on datasets, technology and filters.
- Aggregation depends on rows, columns, KPI and chart type.
- Presentation changes such as title or legend position reuse unchanged filtered data.
- Superseded browser requests are cancelled and ignored.

Changing only a title should therefore be much faster than changing datasets or filters.

PPT Designer persistence has additional layers:

- `design_filter_selections` stores a versioned selection key, faceted filter values and row counts; its predicates are reproduced from the saved PPT definition. A filter value the upload profile of a CDR does not list (such as Call Status) is read from the columnar copy of that CDR once per CDR version, a filter every CDR answers (an empty Cluster catalogue included) is not looked for in the combined tables, and the first and last day of each CDR are kept in the workspace state, so a new selection of CDRs already read (a campaign more or less, another filter) is prepared without scanning the combined tables.
- The columnar copies of the CDRs of the shared `reporting_rows_data`, `reporting_rows_voice` and `reporting_rows_speech` combined tables supply PPT filters, chart datasets and chart rendering. The facets, filter values, date limits and vendor families of a Design, whose results depend only on which values the rows hold, read each distinct combination of the columns they need once per CDR, grouped by DuckDB on its copy (`cdr_store.distinct_rows`), instead of every row.
- Compact interactive chart models and reusable preview manifests are kept in memory and as gzip files in the `.cache/ppt-designer` folder of the workspace (written to a temporary file and renamed, unreadable files deleted, the least recently used removed beyond 1 GB and the unused after 30 days; left out of backups, exports and transfers), so a restart restores them; their keys include selected datasets and revisions, NR Mode, scope, dates, filters, template definition and renderer/cache versions. Equivalent value and dataset ordering resolves to the same selection.

When a workspace opens, the application removes the PPT caches earlier versions wrote on disk (`.design-data-cache`, `.design-chart-cache` and `.design-cache-version.json`), moves the `design_chart_models` and `design_preview_manifests` tables of earlier versions to the `.cache/ppt-designer` folder (and drops them), removes a cache folder that Clear cache did not finish deleting and, when the selection format changed, the saved selection metadata. The Workspace **Clear cache** action clears the derived data on demand without deleting definitions, datasets, combined CDR tables, templates or generated jobs.

Chart models are generated only when the corresponding chart is viewed or included in a requested PPT.

The combined-table revision in these cache keys advances only when rows are inserted or rebuilt. Adding or filling columns (for example when another Design or template needs a new field) records a separate timestamp and keeps every prepared universe valid.

PPT Designs status checks read each universe manifest directly from its fingerprint-derived path and are reused until datasets, combined rows, auto-calculated fields, mappings, templates or manifests change. Only the most recently used PPT snapshots keep their pandas chart frames in memory (3 by default, configurable with `DRIVETEST_ANALYZER_DESIGN_FRAME_CACHE_SNAPSHOTS`); older snapshots rebuild them from the combined tables on demand, which bounds memory use on smaller servers.

## Filtered dataset preview

The filtered-data overlay uses the complete chart-filtered dataset, not a fixed first-200-row sample.

- Pages contain 100 rows.
- Page navigation is server-side and remains fixed outside table scrolling.
- Vertical and horizontal scrolling affect only the table viewport.
- Column-filter value lists are calculated from all chart-filtered rows.
- Counters distinguish total dataset rows, chart-filtered rows, rows after column filters and rows shown on the current page.

## Startup and workspace upgrades

At startup the server opens the active workspace in a background thread. A normal start finishes within a few seconds, as before; when the workspace database needs one-time upgrades after an update (for example the vendor column migration), the server starts answering after three seconds with a page that shows the step being done (checking or upgrading the database of the workspace, emptying the CDR tables its [columnar copies](workspace-management.md#columnar-copy-of-the-cdrs) hold and compacting it, its Output folder, the Scoring calculations and jobs the last run left unfinished, the PPT Templates, the starter content and the creators, and the CDRs) and opens the application as soon as it is ready. Only the first start of another version says that the workspace database is upgraded and can take a few minutes; the version of the last start is kept in the application database. Until then every page answers `503` with that page and every API answers `503` with a JSON message; `/api/startup-status` reports the progress.

## Background jobs and output

PowerPoint generations use the `design_ppt_jobs` table because they preserve a saved Design identity and its exact applied definition. Each job records its CDR selection, dates, NR Mode, scope, adaptive filters, preview fingerprint and progress. Its output contains the PPTX plus persistent PNG, tooltip and Canvas-model assets:

```text
output/reports/ppt-designs/<timestamp - design-name>/
```

The Design jobs UI supports stop, retry, relaunch and deletion. A completed job can be reopened through Charts Panel without rerendering its charts, and its Filtered Chart Dataset replays the saved selection directly against the combined CDR table used at generation time.

PowerPoint generations continue after leaving the page or signing out. A process restart marks interrupted in-process jobs as failed and retryable because the current worker model runs inside the application process.

A workspace of an earlier version drops, when it opens, the `generated_jobs` table of the PowerPoint reports and Chart Sets made by a former reports module (App Event `retired_report_jobs_dropped`, with the jobs it held); the documents of those jobs stay in `output/reports/reports-old/` and `output/reports/reports-charts-old/`, and packages and backups that still hold that table import and restore as usual.

## Import, export and server transfer

Portable ZIPs can contain Application Config, PPT definitions, Report Templates, Auto-calculated Fields, complete workspaces or a selected Full Environment.

- Large packages are built and processed on disk rather than fully in browser memory.
- Workspace database snapshots use SQLite-safe copy/backup behaviour, and take the columnar copies of the CDRs (`cdr-store/` beside `database.sqlite`) as they were when the snapshot was made; a copy being written meanwhile takes its place once the snapshot has them.
- Backups write each database snapshot to a temporary `drivetest-analyzer-export-*` folder inside the backup folder and delete it when the snapshot is archived. Every finished backup also deletes snapshot folders left by backups that were killed mid-copy, once they have been unchanged for six hours.
- Workspace replacement closes the target automatically when required.
- Old workspace files are removed only after the replacement succeeds.
- Full Environment import preserves imported workspace permissions, including the workspace that was active on the source.
- Design-only packages contain definitions and comments. Complete workspace and Full Environment packages can include source CDRs and generated output; regenerable Design and map caches are never portability content.

Server transfers use a persisted offer and resumable package reception:

1. Source requests approval from the destination.
2. A destination super-admin accepts or rejects it from any page.
3. Source builds the package with progress, reporting it to the destination every few seconds while it builds and sends it.
4. Destination receives chunks with progress, each transmission attempt into its own file.
5. Completed reception starts import with progress, which the destination stores as each phase begins.
6. Reloading either browser restores the active transfer state; the dialogs can be hidden while the transfer continues as a background task, except on the destination while the package is imported.

An import that ends without recording its result is reported as failed to both servers. Incomplete transfer files are cleaned up, except the file of a package still being received. Complete packages that were not imported appear in the Admin recovery table.

## Performance and scale

- SQLite uses WAL mode, a busy timeout and normal synchronous mode.
- Processed CDR rows are materialised per dataset and into combined tables by CDR type.
- PPT Designer filter catalogues normally come from persisted dataset profiles. If an older profile lacks a current default or added field, the application reads only the missing catalogues from combined CDR tables in one grouped pass per CDR type.
- Combined CDR tables are queried directly and compact Canvas models persist across restarts after being requested. Live, expanded, historical and exported charts share aggregation, hierarchy, colour, title, legend and semantic-tooltip contracts.
- Interactive Preview caches combined and filtered frames separately.
- Database import prefers bulk database/file replacement over row-by-row queries where safe.

SQLite suits the current deployment model, but very large concurrent installations may eventually require an external database and worker queue.
