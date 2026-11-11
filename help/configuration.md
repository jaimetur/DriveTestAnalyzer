# Deployment Configuration

DriveTest Analyzer separates application settings, storage roots and Docker deployment variables. Source installations can set the three storage roots in `storage-paths.conf`; real environment variables take precedence. Docker deployments normally keep all settings in `docker/.env`.

> [!IMPORTANT]
> **Three storage roots.** Keep configuration, workspace data and writable assets on persistent storage. Code template/static overrides are separate settings.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Runtime settings | [Open section](#runtime-settings) |
| Application Config page | [Open section](#application-config-page) |
| Storage roots | [Open section](#storage-roots) |
| Code asset overrides | [Open section](#code-asset-overrides) |
| Docker settings | [Open section](#docker-settings) |
| Persistence layout | [Open section](#persistence-layout) |
| Bootstrap accounts | [Open section](#bootstrap-accounts) |
| Validation checklist | [Open section](#validation-checklist) |

## Runtime settings

| Variable | Purpose | Default or typical value |
| --- | --- | --- |
| `APP_NAME` | Application-name setting retained by the runtime configuration. Current release branding remains DriveTest Analyzer. | `DriveTest Analyzer` |
| `APP_HOST` | Bind address used when launching `python src/main.py`. | `0.0.0.0` |
| `APP_PORT` | Source launcher port and production host port in Compose. | `7278` |
| `APP_DEV_PORT` | Development host port mapped to the container service. | `7279` |
| `APP_SECRET_KEY` | Signs authenticated session cookies. | A long private random value |
| `DRIVETEST_ANALYZER_REPORT_CHART_RENDERER` | Renderer for reports, previews and PPT exports. | `canvas`; use `pil` only for the legacy painter |
| `DRIVETEST_ANALYZER_CHROMIUM` | Optional explicit Chromium-family executable used by the server Canvas renderer. | Auto-detected supported browser |
| `DRIVETEST_ANALYZER_DESIGN_FRAME_CACHE_SNAPSHOTS` | Number of recently used PPT snapshots that keep their chart data frames in memory. Lower it on servers with little RAM. | `3` |
| `DRIVETEST_ANALYZER_MIRROR_OF` | Names the installation this server is a synchronized copy of (a *mirror*, kept with `tools/mirror` of the source code). A mirror runs no recurring backups or Reporting schedules, sends no emails and says on every page that what is changed on it is overwritten by the next synchronization; `/healthz` reports it as `mirror_of`. A server started without environment variables (the macOS launcher) is a mirror when `APP_CONFIG_DIR` holds a `mirror-of` file with that name. | Not set |
| `DRIVETEST_ANALYZER_DEVELOPMENT_COPY_OF` | Names the server that holds the data in use (its address, or a name) on a development copy of it. A development copy works as any server; every page says that the data in use is on the other server, with a link when it is named by its address, and that what is changed on the copy stays on its computer; `/healthz` reports it as `development_copy_of`. A server started without environment variables (the macOS launcher) takes it from a `development-copy-of` file in `APP_CONFIG_DIR`, read without a restart. | Not set |
| `TZ` | IANA timezone used by Docker and displayed/persisted timestamps. | `Europe/Madrid` |
| `IGNORE_EVENT_TIME_FILTERING` | When true, ignores date and template filters based on Event_Start_Time or Event_End_Time. | `false` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` | Default SMTP server, port and encryption (`starttls`, `ssl` or `none`) for [Reporting](reporting.md) emails. Application Config → Email Delivery overrides them. | Not set; `587`; `starttls` |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Default SMTP account. The password is used whenever no password is saved in Application Config. | Not set |
| `SMTP_FROM`, `SMTP_FROM_NAME` | Default sender address and name of [Reporting](reporting.md) emails. | Not set; `DriveTest Analyzer` |
| `SMTP_MAX_ATTACHMENTS_MB` | Default limit for the total size of a [Reporting](reporting.md) email's attachments. | `20` |
| `EMAIL_TRANSPORT` | How the tool sends its emails: `smtp` (an SMTP server) or `webhook` (a Power Automate flow, see [Email Delivery](app-config.md#email-delivery)). Application Config → Email Delivery overrides it. | `smtp` |
| `EMAIL_WEBHOOK_URL` | Default HTTP POST address of the Power Automate flow, used whenever none is saved in Application Config. | Not set |
| `EMAIL_LINK_DAYS` | Default days the View Online and Download links of the [Reporting](reporting.md) emails work. | `60` |

Before version 0.6.0 the application was named Dashboard Analytic. Variables with the former `DASHBOARD_ANALYTIC_` prefix are still read when the matching `DRIVETEST_ANALYZER_` variable is not set, and export packages, JSON exports and backups created with the former name (format identifiers and backup files starting with `dashboard-analytic-`) are still imported and restored.

## Application Config page

`user-editor`, `admin` and `super-admin` accounts can choose **Config → Application Config** to persist runtime settings in the application database. Values saved there take precedence over Docker and environment variables, and apply to every workspace.

- **Timezone** accepts an IANA name such as `Europe/Madrid`. It controls displayed timestamps and newly stored local timestamps. Without it, or `TZ`, the server's own timezone is used (UTC when the server has none).
- **Report Chart Renderer** selects `canvas` or the legacy `pil` renderer.
- **Chromium Executable** accepts an absolute executable path. Saving it restarts the shared Canvas renderer, so the next chart uses the selected browser.
- **Ignore event time filtering** ignores Design, CDR Analysis and template conditions based on `Event_Start_Time` or `Event_End_Time`. Use it when source timestamps are incomplete and must not exclude valid rows.
- **Maximum simultaneous tasks** sets the background concurrency from 1 to 32, which is also how many datasets of a workspace are processed in parallel; the effective limit reserves one logical CPU for interactive requests.
- **Public address of the server** (`https://name[:port]`) is the address of the links of the presentations and of their previews; empty, they take the address each user opened the application with (the links of the emails, only an address a super-admin has signed in at). Admins and super-admins change it, and the Chromium Executable.
- **Email Delivery** sets how the tool sends its emails (SMTP server or Power Automate flow, sender, validity of the report links and the users told of their own changes) and sends a test email; see [Email Delivery](app-config.md#email-delivery).

See [Application Config](app-config.md) for the complete in-app workflow. Workspace-owned chart mappings are managed separately in [Workspace Config](workspace-config.md), and the PPT Templates in [PPT Designer](ppt-designer.md#ppt-templates); they require an active workspace.

`0.0.0.0` is a server bind address, not a browser destination. When the application binds to it locally, open `http://127.0.0.1:7278` or `http://localhost:7278`. From another computer, use the server's reachable hostname or IP address and the published host port.

Always replace `APP_SECRET_KEY` outside local development.

A login ends after one hour without activity in its browser; the owner account of the tool keeps it for 90 days. A session still valid goes on across restarts and updates of the application: only the hash of its token is kept, in the **User Login Sessions** table of the application database. While it is valid, the login page opens the application. It ends when the user signs out, changes their password (on their other browsers) or has it reset, and when the account is deactivated or deleted. A change of role applies within a minute. A session token is a credential: serve the application over HTTPS outside local development.

## Storage roots

| Variable | Contains |
| --- | --- |
| `APP_CONFIG_DIR` | Global `application.db`: users, roles, workspace permissions, application state and transfer offers. |
| `APP_DATA_DIR` | Workspace registry and directories, uploads, generated output, PPT caches, map tiles, backup ZIPs and temporary transfer/export packages. |
| `APP_ASSETS_DIR` | Bundled PowerPoint masters used by report and PPT generation. |

Only these three variables are accepted in `storage-paths.conf`:

```text
APP_CONFIG_DIR = /srv/drivetest-analyzer/config
APP_DATA_DIR = /srv/drivetest-analyzer/data
APP_ASSETS_DIR = /srv/drivetest-analyzer/assets
```

Relative paths are resolved from the project root. `~` and environment-variable references are expanded. If the file is absent, the defaults are `config/`, `data/` and `assets/` inside the project. Environment variables with the same names override the file, which lets Docker use `/app/config`, `/app/data` and `/app/assets` without editing a developer's local configuration.

A data folder copied or moved to another place, machine or user (for example from `/Users/<other>/DriveTestAnalyzer/data`) can be used as it is: at startup, a workspace whose folder is missing at the path the registry stored but exists under `APP_DATA_DIR/workspaces/` is pointed at its new place, together with the file and folder paths its database stored (CDRs, scoring history files, PPT jobs and report runs).

The process needs read/write access to `APP_CONFIG_DIR` and `APP_DATA_DIR`, including permission to create SQLite WAL/SHM sidecars and atomic temporary files. `APP_ASSETS_DIR` only needs to be readable during ordinary operation.

## Code asset overrides

These advanced environment variables relocate application code assets and are not valid entries in `storage-paths.conf`:

| Variable | Default | Use |
| --- | --- | --- |
| `APP_TEMPLATE_DIR` | `src/web_interface/templates` | Jinja HTML templates. |
| `APP_STATIC_DIR` | `src/web_interface/static` | CSS, JavaScript, images and fonts served below `/static`. |

Ordinary source and Docker installations should retain these defaults. They are deployment overrides, not workspace storage locations.

## Docker settings

These values are consumed by Compose rather than by the Python application:

| Variable | Purpose |
| --- | --- |
| `IMAGE_REPOSITORY` | Published Docker image repository. |
| `IMAGE_TAG` | Image version to pull and run. |
| `CONTAINER_NAME` | Container name. |
| `HOST_CONFIG_DIR` | Host directory mounted at `/app/config`. |
| `HOST_DATA_DIR` | Host directory mounted at `/app/data`. |

Production maps `${APP_PORT}:7278`; development maps `${APP_DEV_PORT}:7278`. The application inside the container always listens on `0.0.0.0:7278`. `APP_ASSETS_DIR=/app/assets` points to assets bundled in the image, so the standard Compose files persist only config and data.

Use a pinned `IMAGE_TAG` when a production deployment must be reproducible. See [Docker Deployment](docker-deployment.md) for complete commands and upgrade checks.

## Persistence layout

The configured roots produce this high-level layout:

```text
APP_CONFIG_DIR/
└── application.db

APP_DATA_DIR/
├── workspaces/
│   ├── workspace-registry.db
│   └── <workspace>/
├── transfer-packages/
├── scheduled-backups/
│   ├── full/
│   └── light/
└── .map-tiles-cache/

APP_ASSETS_DIR/
└── powerpoint-templates/
    └── Template_VodafoneThree.pptx
```

Report Templates are records in each workspace database. CSV files appear in export, transfer and backup ZIPs as their portable representation; no persistent template CSV directory is required.

The starter content of every workspace stays a code asset in the application folder: `assets/autocalculated-fields/default-autocalculated-fields.json` (Auto-calculated Fields), `assets/labels-operators/`, `assets/labels-vendors/`, `assets/labels-campaigns/`, `assets/scoring-methodologies/`, `assets/scoring-report-configurations/`, `assets/ppt-templates/`, `assets/ppt-designs/`, `assets/query-builder-queries/`, `assets/scoring-favourites-filters/` and `assets/bundle-report-template-favourites/` (see [Workspace Management](workspace-management.md#workspace-lifecycle)), as are the Map Areas included with the application (`assets/map-areas/`); changing `APP_ASSETS_DIR` currently relocates the PowerPoint master lookup only.

For the complete workspace, output and cache tree, see [Project Structure → Persistent data layout](project-structure.md#persistent-data-layout).

## Bootstrap accounts

> [!WARNING]
> **Initial access.** Replace the bootstrap passwords and configure a private APP_SECRET_KEY before exposing the service.

A brand-new empty `application.db` creates these accounts once:

- `super / super123` — `super-admin`
- `admin / admin123` — `admin`
- `demo / demo123` — `user-viewer`

All three receive access to the `Default` workspace. Later restarts do not recreate deleted users, reset passwords or restore changed roles.

After first login:

1. Click the username badge.
2. Change every bootstrap password that will remain enabled.
3. Review roles and workspace access in Admin.
4. Store the session secret and deployment configuration in the approved secret-management system.

## Validation checklist

- `http://127.0.0.1:7278/healthz` responds locally, or the equivalent published host and port responds remotely.
- A file uploaded to `Default` remains after an application or container restart.
- Workspace Report Templates and PPT definitions remain available.
- The workspace size and cache size reflect the configured data root.
- PPT preparation writes nothing in the workspace: its caches are kept in memory.
- `APP_CONFIG_DIR` and `APP_DATA_DIR` are included in infrastructure backups.
