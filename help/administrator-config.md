# Administrator Config

Administrator Config, the **Admin** tab, centralises portability and dataset administration: Import / Export / Transfer and Datasets Management, for the `admin` and `super-admin` roles (only super-admins import packages). The users and their access, Interface Settings and the databases and backups of the application are in [Super Admin](super-admin.md), for super-admins only. Application-wide runtime settings are in Application Config; workspace-owned templates and chart mappings are on the separate Workspace Config page.


> [!TIP]
> **Choose a portable component.** Use individual configuration components for settings, workspace packages for workspace content, and Full Environment for deployment-wide migration.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Import / Export / Transfer | [Open section](#import-export-transfer) |
| Datasets Management | [Open section](#datasets-management) |

## Import / Export / Transfer

### Export targets

- Application Config (the whole application database, its users, Modules Profiles, Workspace Groups and tickets included)
- Users & Access (only the users, Modules Profiles and Workspace Groups)
- Ticket Center (only the tickets, with their type, timeline and screenshots; importing it merges them, see [Ticket Center](ticket-center.md#portability))
- Dashboards from the active workspace
- PPT Templates from the active workspace
- Main Cities from the active workspace
- Mappings & Reference Data from the active workspace
- Scoring & GAP Analysis Methodologies from the active workspace (all saved methodologies, default methodology, KPI definitions and GAP KPI priorities; packages exported before also carry the Saved Filters and the report configurations, which their import still restores)
- Auto-calculated Fields from the active workspace
- Query Builder Queries from the active workspace
- Network Insights Favourites from the active workspace (the favourite Analysis Selections; importing them adds new favourites and replaces those with the same name)
- Bundle Report Template Favourites from the active workspace (the favourite Bundle Report Templates of [Reporting](reporting.md), formerly Complete Reports, whose packages still import, with every option of their sections, such as the GAP reference, methodology and Geographical Areas & Scoring Trends of Scoring with Main Cities kept as such; importing them adds new favourites and replaces those with the same name, and each finds its Dashboards by name and NR Mode, keeping which are checked and their order)
- Scoring & GAP Favourites Filters from the active workspace (the Favourites Filters of [Scoring & GAP Analysis](scoring-gap-analysis.md) without their results, with every field of their calculation, their Geographical Areas & Scoring Trends (Main Cities kept as such); importing them adds those the workspace does not have, each finding its CDRs by file (one with a Campaign choice such as Latest campaign takes the CDRs it stands for here), and keeps their name and order)
- Scoring & GAP Report Templates from the active workspace (the saved configurations of the Scoring report editor, each scenario with its Geographical Areas & Scoring Trends; importing them adds new configurations and replaces those with the same name)
- Scoring Export Panels from the active workspace (the Scoring panels the PowerPoint and Word include and the operators of each one, see [Workspace Config](workspace-config.md#scoring-export-panels); importing them replaces those of each destination workspace)
- Scoring Excluded Calls from the active workspace (the lists of calls left out of every scoring, with their CDRs by file name, see [Scoring & GAP Analysis](scoring-gap-analysis.md#excluded-calls); importing them adds the lists to each destination workspace and replaces those of the same name)
- Reporting Jobs from the active workspace (every field of their artifacts, such as the GAP reference and the report of each Scoring artifact; packages exported before also carry the favourite Bundle Report Templates, which their import still restores)
- NQ Call Tracking from the active workspace (the Non-Qualified Calls Analysis Center: sections, field catalog, statuses, teams, Status Rules, root cause catalog, Ericsson RCA results, follow-up, comments and history)
- NQ Calls Configuration from the active workspace (only the configuration of the Non-Qualified Calls Analysis Center: sections, field catalog with its lists, statuses, teams with their members, Status Rules, root cause catalog with its suggestion rule and table columns, without Ericsson RCA results, follow-up, comments or history)
- App Events from the active workspace (every event with its user, action, details and time; importing them adds the events a workspace does not have, among its own by date, without replacing or deleting any)
- An accessible workspace
- Full Environment with selected workspaces

In the selector, **Current Workspace Content** groups the elements of the active workspace by the module where they are managed: first Workspace Config (the Config pages and the [Workspace](workspace-management.md) module together: Auto-calculated Fields, Main Cities, Mappings & Reference Data, PPT Templates), then in the order of the menu App Logs (App Events) and the main modules in tab order with their titles of Interface Settings: PPT Dashboards (Dashboards), Scoring & GAP Analysis (its Methodologies, Favourites Filters and Report Templates), Network Insights (its Favourites), Non-Qualified Calls (NQ Call Tracking, NQ Calls Configuration), [Reporting](reporting.md) (Bundle Report Template Favourites, Reporting Jobs) and **Builders** (Query Builder Queries). The elements of each module are listed alphabetically.

Admins can export/transfer the active workspace's Dashboards, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Bundle Report Template Favourites, Scoring & GAP Favourites Filters, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, Reporting Jobs, NQ Call Tracking and NQ Calls Configuration, plus complete workspaces they can access. Super-admins can also export Application Config, Users & Access and a Full Environment.

**Users & Access** moves the users between servers without the rest of the configuration: every account with its name, password, role, active status (with its pending access request), Modules Profile, Workspace Groups and individual workspaces, plus every Modules Profile and Workspace Group. Its import, transfer or restore adds the users, profiles and groups that are missing and updates those with the same name (without case differences), keeping the others; a user keeps its membership of groups the package does not have. Workspaces are matched by name: those the destination does not have are left out and listed in the completion message, and the destination keeps the workspaces of groups and users that only it has. The account that imports keeps its role, status and password, and nothing is imported when no active super-admin would remain.

Dashboard, template, mapping and field packages preselect a destination workspace with the same name as their source, where available, and allow one or more accessible destinations to be selected.

Importing or transferring Auto-calculated Fields stores them at once and updates the CDR tables as a background task, only when the fields differ from those of the destination workspace; in an import or transfer of several packages it starts once every package is imported.

Importing or transferring PPT Templates synchronizes the destination library with the package. Templates absent from the package are removed unless a saved local Dashboard uses them. A template used by a local Dashboard keeps its local definition when the package contains a matching name; names are matched without case differences, so the import does not create a second copy.

When the same package also includes Dashboards, its PPT Templates replace the destination library because the Dashboard definitions are replaced too. Selective backup restore uses the same rule.

A Full Environment always contains Application Config and the complete database/input content, Dashboard definitions, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Bundle Report Template Favourites, Scoring & GAP Favourites Filters, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, Reporting Jobs and NQ Call Tracking for every selected workspace. Selecting Full Environment only chooses the package type; the workspace picker opens when **Export ZIP** or **Transfer to other server** is pressed.

**Include generated Reports, Chart Sets and Dashboard PPT jobs** controls whether their `output/` trees, and the [Reporting](reporting.md) run history, are included. Reporting Job imports add new jobs and replace jobs with the same name; their dataset references are matched by file name in the destination workspace. At least one workspace is required.

Exporting or transferring a complete workspace asks which folders to include: **Output** (generated dashboards, reports and chart sets) and **Input** (the original CDR files, needed to reprocess datasets). Leave a folder out when the destination already holds an identical copy, for example from an earlier transfer: the package lists its files (name and size), and when it replaces a workspace with the same name that holds all of them, that workspace keeps its own folder, and with Output also the history of generated files, which travels in the workspace database. Otherwise the folder is empty (and without Output files their history is left out too), and a warning says so for the Input files, the Output files or both: on a transfer, in the destination's approval dialog and in the source's progress dialog; on every import, in its completion message.

If a selected workspace has not been opened since the application was updated, its database still has the layout of an earlier version: before the export or transfer starts, a dialog lists those workspaces and offers **Convert and include** (their database is updated to the current version first, which can take several minutes for large workspaces) or **Exclude them**.

Exports run as disk-backed jobs and show estimated progress. The ZIP download starts when package creation finishes.

### Import workflow

> [!IMPORTANT]
> **Only super-admins import packages.** For admins the **Import** card says so instead of offering the file; they export and transfer as before.

> [!WARNING]
> **Review replacement scope.** Import and Restore can replace existing data. Review the detected components and affected workspaces in the overwrite confirmation.

1. Drop a DriveTest Analyzer ZIP or Scoring & GAP Analysis Methodologies JSON on the **Import** card, or click it to choose one (the card names the file and its size), press **Import ZIP / JSON** and wait for its upload.
2. Review the manifest-detected content, affected workspaces and overwrite warnings.
3. For Dashboard, PPT Template, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies or Auto-calculated Field packages, choose one or more accessible destination workspaces; a matching source name is preselected when available.
4. Confirm import.
5. Follow the background import in the floating task card.

Workspace replacement is automatic: the application closes the target when required, imports the replacement, and removes obsolete old files only after success.

### Transfer to other server

1. Choose **Content to export/transfer**.
2. Enter destination URL/IP and port; the default port is `7278`.
3. Press Enter or select **Connect and request approval**.
4. A destination super-admin accepts or rejects the offer.
5. Follow export creation and transmission at source.
6. Follow reception and automatic import at destination.

The dialog remembers the last destination. Active state is restored after page reload and resumable reception tolerates temporary connection cuts; each retry is received into its own file. If either server stops the transfer because of an error, the other one shows its reason.

The transfer runs as a background task on both servers, shown in the red **System tasks** card:

- **Source:** **Hide** closes the progress dialog to keep using the application. The dialog comes back once when the destination starts importing the package, with **Hide** again, and the result is always shown. **Cancel operation**, or stopping the task, cancels the transfer at any stage; once the destination has started importing, that import continues there and its result is shown on the destination.
- **Destination:** while the source creates and sends the package, its task and dialog follow the source's progress, **Hide** closes the dialog and the task can be stopped from the card. When the package has arrived, a dialog without **Hide** keeps every open page out of use until the import ends, because the received data replaces the current data. An import that stops without recording a result is reported as failed on both servers instead of being left running. An accepted transfer whose package does not arrive within 24 hours expires.

Literal private IP destinations such as `192.168.1.17` are contacted directly, bypassing proxy variables inherited by Docker. The receiving application must listen on `0.0.0.0` rather than only `127.0.0.1`, and its host firewall must allow inbound TCP traffic on the selected port. When the destination is the Docker host itself, use `host.docker.internal`; a different computer on the LAN should use that computer's LAN IP.

For super-admins, complete unimported packages appear in **Recovered transfer packages** with content, workspaces, creation time, size, Import and Delete actions. Incomplete remnants are removed automatically; a package still being received is never removed, so Admin pages can be opened or reloaded during a transfer.

## Datasets Management

- Review dataset ID, editable name, stored path, uploader, upload time and last update; below its name each dataset shows its kind (Voice, Data or Speech CDR) and its processing status (Ready, Queued, Processing, Failed or Stopped).
- Rename a dataset inline; queued and processing rows remain locked until their current work finishes.
- Preview any Ready dataset in a separate tab.
- Open Ready Data, Voice or Speech CDRs in CDR Analysis.
- Apply available VFUK/3UK mappings to an eligible CDR or clear its persisted Vendor mapping.
- Delete a dataset after confirmation whenever it is not processing; stop active processing from Workspace first.
