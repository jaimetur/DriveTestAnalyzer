# Administrator Config

Administrator Config, the **Admin** tab, centralises portability and dataset administration: Import / Export / Transfer and Datasets Management, for the `admin` and `super-admin` roles (only super-admins import packages). The users and their access, Interface Settings and the databases and backups of the application are in [Super Admin](super-admin.md), for super-admins only. Application-wide runtime settings are in Application Config; workspace-owned templates and chart mappings are on the separate Workspace Config page.


> [!TIP]
> **Choose a portable component.** Use individual configuration components for settings, workspace packages for workspace content, and Full Environment for deployment-wide migration.

## Presentation

The presentation **Administration** sums up Admin and Super Admin: who sees and does what (roles, Modules Profiles, Workspace Groups and Access Requests) and the management of every account in Users, the application and workspace databases with the Database Viewer, the scheduled backups and their restore, the packages and transfers between servers, the configuration of the application at every level (Application Config, Admin Config, Super Admin Config and Workspace Config) and App Events. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
administration
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Import / Export / Transfer | [Open section](#import-export-transfer) |
| Datasets Management | [Open section](#datasets-management) |

## Import / Export / Transfer

### Export targets

- Application Config (the whole application database, its users, Modules Profiles, Workspace Groups, tickets, Interface Settings and Scoring Aggregation Hierarchy included; importing it replaces those of the destination, so what only the destination has is lost, while its Scheduled Backups and Application Runtime settings, its transfers and its workspaces are kept; the access of each workspace of the source server goes to the destination workspace with its identity, or else its name, and the access to workspaces only the destination has is kept)
- Users & Access (only the users, Modules Profiles and Workspace Groups)
- Ticket Center (only the tickets, with their type, timeline and screenshots; importing it merges them, see [Ticket Center](ticket-center.md#portability))
- Dashboards from the active workspace (importing them replaces the Dashboards the destination has and adds the others, see [Matching and creators](#matching-and-creators))
- PPT Templates from the active workspace (importing them replaces the templates the destination has and adds the others, see below)
- Main Cities from the active workspace
- Mappings & Reference Data from the active workspace
- Scoring & GAP Analysis Methodologies from the active workspace (all saved methodologies, default methodology, KPI definitions and GAP KPI priorities; importing them replaces the methodologies the destination has and adds the others, keeping those only the destination has and its default methodology; the Saved Filters and report configurations that packages exported before also carried are left out by imports and transfers, and only backups made before still restore them)
- Auto-calculated Fields from the active workspace (importing them replaces the fields the destination has and adds the others)
- Query Builder Queries from the active workspace (importing them replaces the queries the destination has and adds the others)
- Network Insights Favourites from the active workspace (the favourite Analysis Selections; importing them replaces the favourites the destination has and adds the others)
- Bundle Report Template Favourites from the active workspace (the favourite Bundle Report Templates of [Reporting](reporting.md), formerly Complete Reports, whose packages still import, with every option of their sections, such as the GAP reference, methodology and Geographical Areas & Scoring Trends of Scoring with Main Cities kept as such; importing them replaces the favourites the destination has and adds the others, and each finds its Dashboards by name and NR Mode, keeping which are checked and their order)
- Scoring & GAP Favourites Filters from the active workspace (the Favourites Filters of [Scoring & GAP Analysis](scoring-gap-analysis.md) without their results, with every field of their calculation, their Geographical Areas & Scoring Trends (Main Cities kept as such); importing them adds those the workspace does not have, each finding its CDRs by file (one with a Campaign choice such as Latest campaign takes the CDRs it stands for here, so the preview and the completion message compare it by its choice, not by the CDRs it stood for on the other server), and keeps their name and order; one the workspace already has, with the same selection, takes the name and the creator of the package, and its star when it has one, while a star of the destination stays with whoever gave it)
- Scoring & GAP Report Templates from the active workspace (the saved configurations of the Scoring report editor, each scenario with its Geographical Areas & Scoring Trends; importing them replaces the configurations the destination has and adds the others)
- Scoring Export Panels from the active workspace (the Scoring panels the PowerPoint and Word include and the operators of each one, see [Workspace Config](workspace-config.md#scoring-export-panels); importing them replaces those of each destination workspace)
- Scoring Excluded Calls from the active workspace (the lists of calls left out of every scoring, with their CDRs by file name, see [Scoring & GAP Analysis](scoring-gap-analysis.md#excluded-calls); importing them replaces the lists each destination workspace has, found by their identity or name, and adds the others)
- Reporting Jobs from the active workspace (every field of their artifacts, such as the GAP reference and the report of each Scoring artifact; packages exported before also carry the favourite Bundle Report Templates, which their import still restores)
- NQ Call Tracking from the active workspace (the Non-Qualified Calls Analysis Center: sections, field catalog, statuses, teams, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, root cause catalog, Ericsson RCA results, follow-up, comments and history)
- NQ Calls Configuration from the active workspace (only the configuration of the Non-Qualified Calls Analysis Center: sections, field catalog with its lists, statuses, teams with their members, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, root cause catalog with its suggestion rule and table columns, without Ericsson RCA results, follow-up, comments or history)
- App Events from the active workspace (every event with its user, action, details and time; importing them adds the events a workspace does not have, among its own by date, without replacing or deleting any)
- An accessible workspace (its whole database, which replaces that of the workspace of the destination)
- Full Environment with selected workspaces

In the selector, Application Config, each Full Workspace and Full Environment carry an amber warning tag (**Whole application database**, **Whole workspace database**, **Whole application and workspace databases**): importing them replaces those databases instead of merging their items.

In the selector, **Current Workspace Content** groups the elements of the active workspace by the module where they are managed (the PPT Templates with the PPT Dashboards that use them), and the Workspace Content of backups is grouped the same way: first Workspace Config (the Config pages and the [Workspace](workspace-management.md) module together: Auto-calculated Fields, Main Cities, Mappings & Reference Data), then in the order of the menu App Logs (App Events) and the main modules in tab order with their titles of Interface Settings: PPT Dashboards (Dashboards and the PPT Templates they use), Scoring & GAP Analysis (its Methodologies, Favourites Filters and Report Templates), Network Insights (its Favourites), Non-Qualified Calls (NQ Call Tracking, NQ Calls Configuration), [Reporting](reporting.md) (Bundle Report Template Favourites, Reporting Jobs) and **Builders** (Query Builder Queries). The elements of each module are listed alphabetically.

Admins can export/transfer the active workspace's Dashboards, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Bundle Report Template Favourites, Scoring & GAP Favourites Filters, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, Reporting Jobs, NQ Call Tracking and NQ Calls Configuration, plus complete workspaces they can access. Super-admins can also export Application Config, Users & Access and a Full Environment.

**Users & Access** moves the users between servers without the rest of the configuration: every account with its name, password, role, active status (with its pending access request), Modules Profile, Workspace Groups and individual workspaces, plus every Modules Profile and Workspace Group. Its import, transfer or restore finds each user, profile and group by its identity, then by its username or name (without case differences): it updates those the destination has, adds those that are missing and keeps the others; a user keeps its membership of groups the package does not have. One renamed on the source server is renamed in the destination (a user whose new username another user has keeps its own, and a new user whose username another user has is left out; the completion message lists them). Workspaces are found by their identity, then by their name: those the destination does not have are left out and listed in the completion message, and the destination keeps the workspaces of groups and users that only it has. The account that imports keeps its username, role, status and password, and nothing is imported when no active super-admin would remain.

Dashboard, template, mapping and field packages preselect a destination workspace with the same name as their source, where available, and allow one or more accessible destinations to be selected.

Importing or transferring Auto-calculated Fields stores them at once and updates the CDR tables as a background task, only when the fields differ from those of the destination workspace; in an import or transfer of several packages it starts once every package is imported.

Importing or transferring PPT Templates replaces the templates the destination has and adds the others, keeping those only the destination has; the destination keeps its default template, and the default of the package becomes the default only where the destination has none. A template used by a Dashboard of the destination keeps its local definition, unless the same package also includes the Dashboards.

A backup restore of PPT Templates, Dashboards or Auto-calculated Fields works the same way: it replaces those the workspace has and adds the others, keeping those the backup does not have.

#### Matching and creators

Dashboards, PPT Templates, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Bundle Report Template Favourites, Scoring & GAP Report Templates, Scoring Excluded Calls, Reporting Jobs and Scoring & GAP Analysis Methodologies (by their ID) carry the identity of each item (backups too), and so do the workspaces of Full Workspace and Full Environment packages and the users, Modules Profiles and Workspace Groups of Users & Access. A Full Workspace or Full Environment import replaces the workspace with that identity, or else with its name, keeping its local ID and access, and one renamed on the source server takes its new name (unless another workspace has it). An import, transfer or backup restore replaces the item of the destination with that identity, or else the one with the same name (without case differences; Dashboards by name and NR Mode and PPT Templates by name in each NR Mode), adds the others and keeps those only the destination has; a methodology replaced this way keeps its ID in the destination, so the Saved Filters and Reporting Jobs that use it still find it. An item renamed on the source server is therefore renamed in the destination instead of being added a second time, and its new name reaches what uses it: the Dashboards of a renamed PPT Template, the PPT Templates, Dashboards, saved Query Builder queries and CDR tables of a renamed Auto-calculated Field, the Reporting Jobs based on a renamed favourite Bundle Report Template and the Scoring artifacts of Reporting Jobs that name a renamed Scoring & GAP Report Template (Dashboards and the other items are referred to by ID, a Dashboard refers to its PPT Template by the template's identity, and a Reporting Job or favourite that names a Dashboard by the ID it had on the source server finds it). When another item of the destination already has that name, the imported item is named `Name (2)`. The completion message and its App Event list the renamed items: the message opens in a wide window with the packages imported and, for each element and workspace, a table of the items renamed (before and after, and those imported with another name because another item had theirs). Items exported by earlier versions carry no identity and are found by their name.

Each package of the completion message says, in the same way, how many items it brought and what the import did to them, for example `Imported 32 Reporting Jobs into 1 workspace: 2 new, 1 updated and 29 unchanged.` An item counts as updated only when one of its values really changed, not when the import only saved it again (when and by whom it was last saved, its order, its use count and its identity are not compared), and the summary window shows, for each element and workspace, a table with each updated item and what changed in it (a short value as `Role: user-editor → user-viewer`, a list as `Workspace Groups: +UK, −DE`, a password or a long value by its name only). What was added stands out in green (`2 new`, `1 new comment`) and what was updated in amber (`3 updated`, `updated`), and so do the titles of the sections of the updated items. Mappings & Reference Data, Main Cities, the Scoring Export Panels and the NQ Calls Configuration say whether they were updated or unchanged in each workspace and list what changed: the NQ Calls Configuration each status, team, section, field (its settings and values), Status Rule, root cause entry and suggestion rule, layout of the workspace and of each user, equivalence of the Previous NQ Analyses and setting of the NQ Prioritization that changed (for example `Layout of ana: Columns: +Prioritization, −Scoring Impact` or `NQ Prioritization · Strategy: Dual Queue (Cities first) → Vodafone Proposal`). Each updated call of the follow-up of the Non-Qualified Calls (the first 300 of an import) unfolds **Details** under its changes: every value before and after, whole, and each comment added, edited or removed with its author and text; Users & Access counts its users, Modules Profiles and Workspace Groups this way, Ticket Center its tickets (a new comment or screenshot updates its ticket) with the comments and screenshots added, and App Events the events added and those the workspace already had.

Each imported Dashboard, PPT Template, Scoring & GAP Analysis Methodology, Auto-calculated Field, Query Builder Query, favourite, Scoring & GAP Report Template, Favourites Filter, list of Scoring Excluded Calls and Reporting Job belongs to the user who created it on the source server when that user exists and is active in the destination, and otherwise to the user who accepts the transfer, imports the package or restores the backup. A package of an earlier version, which does not say who created an item, leaves a replaced item with its creator and gives the new ones to that user. Scoring Export Panels have no creator.

A Full Environment always contains Application Config and the complete database/input content, Dashboard definitions, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Bundle Report Template Favourites, Scoring & GAP Favourites Filters, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, Reporting Jobs and NQ Call Tracking for every selected workspace. Selecting Full Environment only chooses the package type; the workspace picker opens when **Export ZIP** or **Transfer to other server** is pressed.

**Include generated Reports, Chart Sets and Dashboard PPT jobs** controls whether their `output/` trees, and the [Reporting](reporting.md) run history, are included. Reporting Job imports replace the jobs the destination has (found by their identity, then by their name) and add the others; their dataset references are matched by file name in the destination workspace. At least one workspace is required.

Exporting or transferring a complete workspace asks which folders to include: **Output** (generated dashboards, reports and chart sets) and **Input** (the original CDR files, needed to reprocess datasets). Leave a folder out when the destination already holds an identical copy, for example from an earlier transfer: the package lists its files (name and size), and when it replaces a workspace that holds all of them (the workspace with its identity, or else its name, also in the check of a transfer before it is accepted), that workspace keeps its own folder, and with Output also the history of generated files, which travels in the workspace database. Otherwise the folder is empty (and without Output files their history is left out too), and a warning says so for the Input files, the Output files or both: on a transfer, in the destination's approval dialog and in the source's progress dialog; on every import, in its completion message.

If a selected workspace has not been opened since the application was updated, its database still has the layout of an earlier version: before the export or transfer starts, a dialog lists those workspaces and offers **Convert and include** (their database is updated to the current version first, which can take several minutes for large workspaces) or **Exclude them**.

Exports run as disk-backed jobs and show estimated progress. The ZIP download starts when package creation finishes.

### Import workflow

> [!IMPORTANT]
> **Only super-admins import packages.** For admins the **Import** card says so instead of offering the file; they export and transfer as before.

> [!WARNING]
> **Review replacement scope.** Import and Restore can replace existing data. Review in the preview what each package would add, update or leave as it is before importing it.

1. Drop a DriveTest Analyzer ZIP or Scoring & GAP Analysis Methodologies JSON on the **Import** card, or click it to choose one (the card names the file and its size), press **Import ZIP / JSON** and wait for its upload.
2. For Dashboard, PPT Template, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies or Auto-calculated Field packages, choose one or more accessible destination workspaces; a matching source name is preselected when available.
3. Review the preview, which compares the package with the data of this server without importing anything, as the import would save it (each item with the creator the import gives it, the Reporting Jobs pointing at the CDRs, favourites and Dashboards of this server, the PPT Templates keeping the default of this server and the NQ Calls Configuration keeping what only this server has): below the overwrite warning, a box for each package of the selection says what its import would do, in the words of the completion message (for example `Imports 32 Reporting Jobs into 1 workspace: 2 new, 1 updated and 29 unchanged.`, the counts of new and updated items in green and amber; for the App Events, how many the workspace does not have yet), and **What would change** unfolds the items it would add (in green) and those it would update with what would change in each. An Application Config, which replaces the whole application database, is compared as its import would leave it: the users, Modules Profiles, Workspace Groups, tickets, Interface Settings (each module and the stage labels) and Scoring Aggregation Hierarchy it would add, update and remove (in red: those only this server has); a Full Workspace or Full Environment names the workspaces whose whole database it would replace. Only the packages that would change something come checked. The packages fill two columns (three on very wide screens), so a full transfer fits in one view. Check the packages to import (**Select all**, **Select none** or **Invert selection**), then press **Import selected**; **Cancel** imports nothing and discards the upload. A package whose preview cannot be prepared says so and can still be imported.
4. Follow the background import in the floating task card.

Workspace replacement is automatic: the application closes the target when required, imports the replacement, and removes obsolete old files only after success.

### Transfer to other server

1. Choose **Content to export/transfer**.
2. Enter destination URL/IP and port; the default port is `7278`.
3. Press Enter or select **Connect and request approval**.
4. A destination super-admin accepts or rejects the offer.
5. Follow export creation and transmission at source.
6. When the package has arrived, the destination prepares its preview (as that of an import, see above) and nothing is imported until a super-admin chooses what to import: **Import selected** imports the checked packages and **Reject transfer** imports nothing, deletes the package and tells the source. The preview opens on every Admin page of a super-admin, also after a reload or a restart, and the source waits for the decision (its dialog says it is waiting for the import to be confirmed).

The dialog remembers the last destination. Active state is restored after page reload and resumable reception tolerates temporary connection cuts; each retry is received into its own file. If either server stops the transfer because of an error, the other one shows its reason.

The transfer runs as a background task on both servers, shown in the red **System tasks** card:

- **Source:** while it creates the package, the dialog (and the dialog of **Export ZIP**) says which part it is archiving: the application database, and the database (with its size), settings, Input and Output files of each workspace, or each element of a selection by its position; a database is first copied whole, so the bar moves once its copy is done. **Hide** closes the progress dialog to keep using the application. The dialog comes back once when the destination starts importing the package, with **Hide** again, and the result is always shown. **Cancel operation**, or stopping the task, cancels the transfer at any stage; once the destination has started importing, that import continues there and its result is shown on the destination.
- **Destination:** while the source creates and sends the package, its task and dialog follow the source's progress, **Hide** closes the dialog and the task can be stopped from the card. While a package of several elements is imported, the bar moves within each element, which says what it is doing (for example the CDR it identifies by its file or the Favourites Filter it prepares). When the package has arrived, a dialog without **Hide** keeps every open page out of use until the import ends, because the received data replaces the current data. An import that stops without recording a result is reported as failed on both servers instead of being left running. An accepted transfer whose package does not arrive within 24 hours expires.

Literal private IP destinations such as `192.168.1.17` are contacted directly, bypassing proxy variables inherited by Docker. The receiving application must listen on `0.0.0.0` rather than only `127.0.0.1`, and its host firewall must allow inbound TCP traffic on the selected port. When the destination is the Docker host itself, use `host.docker.internal`; a different computer on the LAN should use that computer's LAN IP.

For super-admins, complete unimported packages appear in **Recovered transfer packages** with content, workspaces, creation time, size, Import and Delete actions. Incomplete remnants are removed automatically; a package still being received is never removed, so Admin pages can be opened or reloaded during a transfer.

## Datasets Management

- Review dataset ID, editable name, stored path, uploader, upload time and last update; below its name each dataset shows its kind (Voice, Data or Speech CDR) and its processing status (Ready, Queued, Processing, Failed or Stopped).
- Rename a dataset inline; queued and processing rows remain locked until their current work finishes.
- Preview any Ready dataset in a separate tab.
- Open Ready Data, Voice or Speech CDRs in CDR Analysis.
- Apply available VFUK/3UK mappings to an eligible CDR or clear its persisted Vendor mapping.
- Delete a dataset after confirmation whenever it is not processing; stop active processing from Workspace first.
