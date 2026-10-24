# Project structure

## In this guide

| Task or topic | Go to |
| --- | --- |
| Repository tree | [Open section](#repository-tree) |
| Python application layer | [Open section](#python-application-layer) |
| Browser layer | [Open section](#browser-layer) |
| Persistent data layout | [Open section](#persistent-data-layout) |
| Bundled assets | [Open section](#bundled-assets) |
| Documentation | [Open section](#documentation) |
| Tests, tooling and delivery | [Open section](#tests-tooling-and-delivery) |

## Repository tree

> [!IMPORTANT]
> **Source and runtime data.** Keep uploaded datasets, workspace databases, generated output and backups out of source control. The default runtime folders are excluded from Git and Docker build context. Cache files are regenerable; user data is not.

```text
DriveTestAnalyzer/
├── src/
│   ├── DriveTestAnalyzer.py
│   ├── main.py
│   ├── config.py
│   ├── branding.py
│   ├── version.py
│   ├── dataset_worker.py
│   ├── report_worker.py
│   ├── modules/
│   ├── utils/
│   └── web_interface/
│       ├── templates/
│       └── static/
├── assets/
│   ├── autocalculated-fields/
│   ├── labels-campaigns/
│   ├── labels-operators/
│   ├── labels-vendors/
│   ├── map-areas/
│   ├── powerpoint-templates/
│   ├── ppt-dashboards/
│   ├── ppt-templates/
│   ├── query-builder-queries/
│   ├── reporting-jobs/
│   ├── scoring-methodologies/
│   └── scoring-report-configurations/
├── docker/
├── help/
├── macos-launcher/
├── macos-installer/
├── tests/
├── tools/
├── .github/workflows/
├── storage-paths.conf
├── pyproject.toml
├── requirements.txt
├── README.md
└── CHANGELOG.md
```

Runtime `config/` and `data/` directories use project-local defaults but are excluded from source control and Docker build context.

## Python application layer

- `src/main.py`: shared source, PyCharm and Docker launcher using `APP_HOST`, `APP_PORT` and the timestamped Uvicorn logging configuration.
- `src/DriveTestAnalyzer.py`: FastAPI application, page/API routes, workspace activation, shared background-task orchestration, Admin portability and classic Reporting jobs.
- `src/config.py`: environment and `storage-paths.conf` resolution.
- `src/branding.py`: product identifiers of exports, backups and environment variables, and compatibility with those written under the former Dashboard Analytic name.
- `src/dataset_worker.py`: isolated worker process that parses large CDR source files outside the server process.
- `src/report_worker.py`: worker process that runs a Reporting Job of a workspace that is not open in the server.
- `src/version.py`: application version and release date shown by the UI.
- `src/modules/repository.py`: global/workspace SQLite schemas, migrations and persistence methods.
- `src/modules/workspaces.py`: workspace registry, lifecycle, path migration, duplication and deletion.
- `src/modules/output_layout.py`: module folders below `output/reports/` and the one-time move of documents written with the former layout.
- `src/modules/upload_sessions.py`: resumable dataset uploads (chunks kept in `.upload-sessions` of the workspace until the upload ends); `static/js/background_uploads.js` sends and resumes them on every page.
- `src/modules/ingestion.py`: workbook/CSV ingestion, CDR classification helpers and derived input fields.
- `src/modules/cdr_types.py` and `cdr_field_profiles.py`: the CDR type of each workspace (NetCheck, Umlaut, P3) and the field profile of each type, the CDR columns every module reads; `umlaut_cdr.py` reads the Umlaut service workbooks (their sides and the columns the tool derives) and `cdr_field_dictionary.py` keeps the fields a workspace changes in its CDR Field Dictionary (`static/js/cdr_field_dictionary.js` in Workspace Config).
- `src/modules/analytics.py`: single-dataset analytical calculations.
- `src/modules/exports.py`: CDR Analysis Word and PowerPoint output, including the multi-dataset Summary CDR Analysis.
- `src/modules/network_insights_export.py`: Summary Network Insights PowerPoint and Word output.
- `src/modules/network_insights_findings.py` and `network_insights_findings_slides.py`: the Key Findings of Network Insights (six benchmark views of the Data tests with their headlines) and their slides drawn with shapes in the colours of the theme; `static/js/network_insights_findings.js` draws them on the page.
- `src/modules/starter_content.py`: the starter content of every workspace (methodologies, Report Templates, Dashboards and Auto-calculated Fields from `assets`).
- `src/modules/map_areas.py`: Map Areas of a workspace (`map_area_layers`): the countries of the tests, the geoBoundaries levels and downloads, imported layers and the area of each test used by the Scoring points-lost map.
- `src/modules/presentations.py`: the presentations of the Help with live figures: the figures of the workspaces chosen in Super Admin (read without changing their databases), their generation in the background with `tools/presentations` when they change, into `presentations/current` of the data directory, and `/api/presentations` and `/presentations/files/…`, which serve the last ones (those of `static/presentations` until then).
- `src/modules/report_tasks.py`: Reporting Jobs (`report_tasks`, `report_task_runs`), schedules, artifact generation, email bodies, the scheduler and the artifact provider registry for other modules.
- `src/modules/email_delivery.py`: SMTP settings (Application Config → Email Delivery) and sending.
- `src/modules/non_qualified_calls.py`: Non-Qualified Calls: indexing of the NQ calls of every CDR (`nq_calls`, `nq_call_sources`), their follow-up (`nq_call_tracking`, `nq_call_comments`, `nq_call_history`, `nq_call_options`), the Analysis Center catalog in the workspace (`nq_analysis_fields`, `nq_root_catalog`, `nq_rca_results`), the DT Analyzer RCA of the calls (`nq_dta_rca_results`), the automatic statuses, the summary, lifecycle, RCA insights and drill-down queries, the Excel export, the NQ Call Tracking portability document and its routes.
- `src/modules/nq_catalog.py`: NQ Analysis Center catalog without database access: the sections, default fields, statuses, teams, root cause catalog and Status Rules, their validation and the Excel catalog workbook.
- `src/modules/nq_prioritization.py`: NQ Prioritization: the scoring points each Non-Qualified Call loses (from the Scoring History of its campaign), its repeated issues by place, the Prioritization Rules that prioritize it and fill its Priority (`nq_call_priority`, `nq_priority_campaigns`), its calculation in the background and the panel.
- `src/modules/nq_rca.py`: NQ Ericsson RCA results file format and the root cause recommendation merged from the NetCheck RCA, the Ericsson RCA, the DT Analyzer RCA, the comments and previous decisions.
- `src/modules/nq_dta_rca.py`: DT Analyzer RCA of Non-Qualified Calls: the values it reads, its default rules and their validation, and the evaluation that gives every call its root category, cause, domain and evidence (`non_qualified_calls` stores them in `nq_dta_rca_results`).
- `src/modules/cdr_reporting.py`: Report Template parsing, filters, aggregations, chart contracts, map tiles and classic report rendering.
- `src/modules/ppt_dashboards.py`: Dashboard definitions, direct combined-CDR SQL selections, preview/model caches, live previews, filtered chart data and Dashboard PPT jobs.
- `src/modules/dashboard_canvas_renderer.mjs`: Node/Chromium-compatible Canvas rendering used for consistent interactive and exported charts.
- `src/modules/auth.py`: password and authentication helpers.
- `src/utils/`: chart, filesystem and font utilities shared by modules.

## Browser layer

- `src/web_interface/templates/`: Jinja pages for Workspace, CDR Analysis, PPT Dashboards, PPT Reporting (old), Chart Builder, Admin, App Logs and document viewing.
- `src/web_interface/static/js/`: shared UI behaviour, common chart drawing and the PPT Dashboard client.
- `src/web_interface/static/css/`: application and module-specific styles.
- `src/web_interface/static/markdown_renderer.js`: in-app README, Changelog and Help rendering, including cross-document heading anchors.
- `src/web_interface/static/img/`: brand and interface images.
- `src/web_interface/static/reports/`: reports kept as pages of their own, in their own design, such as the Umlaut and P3 CDR compatibility reports; the Help shows them below their chapter in Help Navigation (`HELP_REPORTS` in `src/DriveTestAnalyzer.py`, `/documents/reports/<id>`).
- `src/web_interface/static/presentations/`: the presentations of the Help kept with the application, shown until the server generates them with live figures (`presentations.json` lists each one with its PowerPoint, the title of each slide by section and its figures, and `<id>/slide-NN.png` and `thumb-NN.png` are its slides); `static/js/presentation_viewer.js` shows a `presentations` code block of a Help chapter (their ids, one per line) as their cards and opens them in the slide viewer.

## Persistent data layout

Scoring calculations live in `src/modules/scoring.py`, with the authoritative rules stored in the workspace database. `saved_filters.py` keeps the Saved Filters (every selection used, with its result calculated in the background and saved until its CDRs or methodology change) in `saved_filters`; `scoring_history.py` keeps the Scoring History; `scoring_config.py` validates workspace KPI settings and GAP priority; `scoring_views.py` projects saved configuration snapshots into comparison matrices and signed GAP views. `scoring_exports.py` uses the CDR PowerPoint master for saved-result exports. The Saved Filters and their results travel with the workspace SQLite database, and the Favourites Filters without results as the Scoring & GAP Favourites Filters element of packages and backups.

```text
APP_CONFIG_DIR/
└── application.db

APP_DATA_DIR/
├── workspaces/
│   ├── workspace-registry.db
│   └── <workspace>/
│       ├── <workspace>.db
│       ├── .dashboard-cache-version.json
│       ├── .dashboard-data-cache/
│       │   ├── dashboard-previews/
│       │   ├── charts-canvas/
│       │   ├── charts-pil/
│       │   └── columns/
│       ├── .network-insights-cache/
│       ├── input/
│       └── output/
│           └── reports/
│               ├── dashboards/
│               ├── cdr-analysis/
│               ├── network-insights/
│               ├── reporting-jobs/
│               ├── reports-old/
│               └── reports-charts-old/
├── transfer-packages/
├── scheduled-backups/
│   ├── full/
│   └── light/
└── .map-tiles-cache/
    └── openstreetmap/
```

Directories are created when their corresponding feature first needs them, so an unused workspace may contain only its database and basic input/output roots. SQLite can also create temporary `-wal` and `-shm` sidecars beside active databases.

### Global database

`APP_CONFIG_DIR/application.db` owns:

- users, roles and workspace access lists;
- global application state;
- server-transfer offers.

### Workspace registry

`APP_DATA_DIR/workspaces/workspace-registry.db` owns workspace IDs, display names, registered paths, lifecycle status and the active-workspace pointer. Registry paths are rewritten during portable import instead of preserving absolute paths from another server.

### Workspace database

Each `<workspace>.db` owns:

- dataset records, processing profiles and audit logs;
- individual materialised dataset-row tables and combined Data/Voice/Speech reporting tables;
- Auto-calculated Field definitions;
- complete database-backed Report Templates in `report_templates`;
- saved Dashboard definitions in workspace state;
- cached Dashboard selection metadata and bounded row identities;
- classic Report/Chart Set jobs in `generated_jobs`;
- Dashboard PowerPoint history in `dashboard_ppt_jobs`.

Report Templates become CSV files only inside portable export, transfer and backup packages.

### Regenerable Dashboard cache

`.dashboard-cache-version.json` records the application and cache-format signature. Opening a workspace deletes older incompatible cache versions and selection metadata. `.dashboard-data-cache` contains reusable preview manifests, Canvas chart models and legacy PIL artifacts. Dashboard rows remain only in the workspace's combined CDR tables. The cache can be cleared without removing datasets, Dashboard definitions, templates or generated jobs, and clearing it does not trigger an automatic rebuild.

### Generated output

- `output/reports/dashboards/`: Dashboard PowerPoint jobs and their persistent PNG, tooltip and Canvas-model assets.
- `output/reports/cdr-analysis/`: CDR Analysis PowerPoint and Word exports.
- `output/reports/network-insights/`: Summary Network Insights PowerPoint and Word exports.
- `output/reports/reports-old/`: PPT Reporting (old) PowerPoint reports and their PNG charts.
- `output/reports/reports-charts-old/`: PPT Reporting (old) Chart Sets.
- `output/reports/reporting-jobs/`: Reporting Job runs, one folder per run with its artifacts.

Workspaces, backups and transfer packages created with the former layout (module folders directly below `output/` and loose documents in `output/reports/`) are moved to these folders the first time the workspace is opened, and the job paths stored in the workspace database follow them.

`transfer-packages/` holds temporary or recoverable portable packages. `scheduled-backups/` is the default Super Admin backup destination, with the full backups in `full/` and the light ones in `light/`. `.map-tiles-cache/openstreetmap/` is a shared regenerable tile cache outside individual workspaces.

## Bundled assets

- `assets/powerpoint-templates/Template_VodafoneThree.pptx` supplies slide masters, named layouts and placeholders; its Title Page, Transition and Title Only layouts have the Vodafone-Three red with the Ericsson mark. `src/modules/report_structure.py` gives every cover and transition its sizes, places and counter.
- `assets/autocalculated-fields/default-autocalculated-fields.json` holds the Auto-calculated Fields every new workspace starts with (the only source of default fields).
- Starter content added to every workspace that does not have it yet (see `src/modules/starter_content.py`): `assets/scoring-methodologies/*.json` (Scoring methodologies in the portable configuration format), `assets/ppt-templates/<nsa|sa>/*.csv` (Report Templates, named after their file), `assets/ppt-dashboards/*.json` (Dashboards without CDRs, dates or Operator and Vendor filters), `assets/scoring-report-configurations/*.json` (saved Scoring report configurations), `assets/query-builder-queries/*.json` (saved Query Builder queries) and `assets/reporting-jobs/*.json` (Reporting Jobs, naming their Dashboards and carrying their Scoring reports, or naming a Scoring report configuration), `assets/bundle-report-template-favourites/*.json` (favourite Bundle Report Templates, naming their Dashboards) and `assets/scoring-favourites-filters/*.json` (Favourites Filters without CDRs, each taking those of its Campaign choice). Adding a file to these folders ships it.
- `assets/labels-operators/operators-by-country.json` holds the operators (labels, corporate colours and CDR spellings) of the 50 main countries, which a workspace created for one of them starts with (see `src/modules/workspace_countries.py`).
- `assets/labels-vendors/default-vendor-maps.json` holds the Vendor Maps (labels, colours and CDR spellings) a new workspace starts with.
- `assets/labels-campaigns/default-campaign-map.json` holds the default Campaign Maps (label format, order of the radio modes and exceptions) of the workspaces without their own.
- `assets/map-areas/` holds the Map Areas shipped with the application (one `<ISO3>.json.gz` per country, such as the UK ITL3 areas, listed in `manifest.json`) and the world country polygons that find the country of each test (see its README).
- Workspace Report Templates supply slide/chart definitions and are documented in [Workspace Config → Report Template reference](workspace-config.md#report-template-reference).

## Documentation

- `README.md`: product summary, source quick start and deployment overview.
- `CHANGELOG.md`: versioned release history.
- `help/help.md`: in-app Help index.
- `help/overview.md`: product and module tour.
- `help/technical-considerations.md`: data interpretation, persistence, caching and job semantics.
- Other Help chapters: focused operational and deployment guides.

The Help navigation order and labels are curated in `src/DriveTestAnalyzer.py`. Renaming an article requires updating that list, incoming links and related tests.

## Tests, tooling and delivery

- `tests/test_app.py`: routes, shared UI, Admin, documentation and integration behaviour.
- `tests/test_ppt_dashboards.py`: Dashboard definitions, filtering, caching, rendering and PPT jobs.
- `tests/test_cdr_reporting.py`: template, filter, chart and classic Reporting contracts.
- Other test modules cover analytics, exports, Query Builder, workspaces and workspace template isolation.
- `tests/conftest.py`: the `client` fixture. Dataset sources are parsed by isolated background workers, so after upload, retry, reprocess and mapping requests the fixture waits for those workers and the combined CDR rebuilds they start; `wait_for_background_dataset_work()` does the same for work queued by other requests.
- `tools/presentations/`: the generator of the presentations of the Help, in Ericsson style (Node.js: `build.js`, `art.js`, and `package.json` with its `package-lock.json`). `benchmarking-providers/` keeps the deck of the adaptation to other benchmarking providers in its own design: a picture of each slide and `slides.json` with their order, section, title and speaker notes, which `build.js` turns into its PowerPoint. The server runs it with the figures of `src/modules/presentations.py`; `npm install` and `node build.js` there write the copies of `static/presentations/` with the figures written in `build.js`, and `python tools/presentations/render.py`, from the project root, renders their slides with LibreOffice as the previews of the Bundle Report Templates.
- `tools/CreateUpdateRelease.py`: release helper that updates `src/version.py`, the `pyproject.toml` project version and the current `CHANGELOG.md` release, and can create and push a release branch.
- `pyproject.toml`: package metadata and runtime dependencies (kept in sync with `requirements.txt`) plus the pytest configuration.
- `.github/workflows/`: automated tests, Docker publishing and source packaging.
- `docker/`: production/development Compose files, image definition and execution notes.

Run the complete suite from the repository root:

```bash
python -m pytest -q
```

Keep databases, uploaded customer files, generated output, cache files and secrets out of source control.

The database-backed scoring configuration and its import/update procedure are documented in [Scoring methodology configuration](scoring-gap-analysis.md#methodology); reference source documents are not runtime dependencies.
