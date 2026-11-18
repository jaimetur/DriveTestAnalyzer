# Administrator Config

Administrator Config, the **Admin** tab, centralises portability and dataset administration: Import / Export / Transfer and Datasets Management, for the `admin` and `super-admin` roles (only super-admins import packages). The users and their access, Interface Settings and the databases and backups of the application are in [Super Admin](super-admin.md), for super-admins only. Application-wide runtime settings are in Application Config; workspace-owned templates and chart mappings are on the separate Workspace Config page.


> [!TIP]
> **Choose a portable component.** Use individual configuration components for settings, workspace packages for workspace content, and Full Environment for deployment-wide migration.

## Presentation

```presentations
administration
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Export or import packages of a workspace | [Import / Export / Transfer](#import-export-transfer) |
| Send to or request from another server | [Transfer to other server](#transfer-to-other-server) · [Request from other server](#request-from-other-server) |
| Manage the datasets | [Datasets Management](#datasets-management) |

## Import / Export / Transfer

### Export targets

Unless an element says otherwise, importing, transferring or restoring it replaces the items the destination has (by identity, else by name) and adds the others, keeping those only the destination has (see [Matching and creators](#matching-and-creators)).

**Configuration elements** (super-admins):

- **Application Config:** the whole application database, with its users, Modules Profiles, Workspace Groups, tickets, Interface Settings and Scoring Aggregation Hierarchy. Importing it replaces those of the destination, so what only the destination has is lost; the destination keeps its Scheduled Backups and Application Runtime settings, its transfers and its workspaces. The access of each source workspace goes to the destination workspace with its identity, else its name, and the access to workspaces only the destination has is kept.
- **Users & Access:** only the users, Modules Profiles and Workspace Groups (see below).
- **Ticket Center:** only the tickets, with their type, timeline, screenshots and files; importing merges them (see [Ticket Center](ticket-center.md#portability)).

**Workspace elements**, from the active workspace:

- **Designs** and **PPT Templates** (see the order and default rules below).
- **Main Cities:** the city selection of the workspace.
- **Mappings & Reference Data:** every canonical Operator and Vendor with its aliases, row position and thematic colour, the comments of the Operator names, the Spectrum Holdings, Serving Networks and Campaign Maps.
- **Scoring & GAP Analysis Methodologies:** all saved methodologies, the default methodology, KPI definitions and GAP KPI priorities; the destination keeps its default methodology. The Saved Scorings and report configurations that older packages also carried are left out by imports and transfers; only older backups still restore them.
- **Auto-calculated Fields**, **Query Builder Queries** and **Network Insights Favourites** (the favourite Analysis Selections).
- **Report Definitions:** what each report of [Reporting](reporting.md) includes, with its schedule, email and stars, not the reports it generated; see [Reporting → Portability](reporting.md#portability).
- **Scoring & GAP Favourite Scorings:** the Favourite Scorings of [Scoring & GAP Analysis](scoring-gap-analysis.md) without their results, with every field of their calculation and their Country Areas & Scoring Trends (Main Cities kept as such).
  - Importing adds those the workspace does not have, each finding its CDRs by file (one with a Campaign choice such as Latest campaign takes the CDRs it stands for here, so the preview and the completion message compare it by its choice, not by the CDRs it stood for on the other server), keeping their name and order.
  - One the workspace already has, with the same selection, takes the name and the creator of the package, and its star when it has one, while a star of the destination stays with whoever gave it.
- **Scoring & GAP Report Templates:** the saved configurations of the Scoring report editor, each scenario with its Country Areas & Scoring Trends.
- **Scoring Export Panels:** the Scoring panels the PowerPoint and Word include and the operators of each (see [Workspace Config](workspace-config.md#scoring-export-panels)); importing replaces those of each destination workspace. They have no creator.
- **Scoring Excluded Calls:** the lists of calls left out of every scoring, with their CDRs by file name (see [Scoring & GAP Analysis](scoring-gap-analysis.md#excluded-calls)).
- **NQ Call Tracking:** the Non-Qualified Calls Analysis Center (sections, field catalog, statuses, teams, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, Map Levels, root cause catalog, Ericsson RCA results), follow-up, comments and history, with the `JOIN_ID` of each call. It merges without duplicating comments, history or RCA results (see the preview below).
- **NQ Calls Configuration:** only that configuration (sections, field catalog with its lists, statuses, teams with their members, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, Map Levels, root cause catalog with its suggestion rule, and table columns), without Ericsson RCA results, follow-up, comments or history; it merges, keeping what only the destination has.
- **App Events:** every event with its user, action, details and time; importing adds the events a workspace does not have (same user, action, details and time), among its own by date, without replacing or deleting any.
- **AI Assistant Glossary:** the terms of the [glossary](assistant.md#the-glossary-of-the-workspace), without the suggestions not accepted; an imported term replaces the one with the same identity, else the same term.

**Whole databases:**

- **Full Workspace:** an accessible workspace with its whole database, which replaces that of the destination workspace.
- **Full Environment:** Application Config plus, for every selected workspace, the complete database and input content, PPT definitions, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Report Definitions, Scoring & GAP Favourite Scorings, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, NQ Call Tracking and AI Assistant Glossary. Selecting it only chooses the package type; the workspace picker opens with **Export ZIP** or **Transfer to other server**.
- In the selector, Application Config, each Full Workspace and Full Environment carry an amber tag (**Whole application database**, **Whole workspace database**, **Whole application and workspace databases**): importing them replaces those databases instead of merging their items.

**Who exports what.** Admins export and transfer the active workspace's Designs, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Network Insights Favourites, Report Definitions, Scoring & GAP Favourite Scorings, Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls and AI Assistant Glossary, plus complete workspaces they can access. Super-admins also export Application Config, Users & Access, Ticket Center, Query Builder Queries, NQ Call Tracking, NQ Calls Configuration, App Events and a Full Environment.

**Current Workspace Content**, in the selector, groups the workspace elements by the module where they are managed, as does the Workspace Content of backups: first Workspace Config (the Config pages and the [Workspace](workspace-management.md) module: Auto-calculated Fields, Main Cities, Mappings & Reference Data), then App Logs (App Events) and the main modules in tab order with their titles of Interface Settings: PPT Designer (Designs and the PPT Templates they use), Scoring & GAP Analysis (Methodologies, Favourite Scorings, Report Templates), Network Insights (Favourites), Non-Qualified Calls (NQ Call Tracking, NQ Calls Configuration), [Reporting](reporting.md) (Report Definitions), **Builders** (Query Builder Queries) and AI Assistant (AI Assistant Glossary). The elements of each module are listed alphabetically.

**Destination workspaces.** Design, template, mapping and field packages preselect the destination workspace with the same name as their source, where available, and allow one or more accessible destinations.

**Users & Access** moves the users between servers without the rest of the configuration: every account with its name, email, password, role, active status (with its pending access request), last log-in, Modules Profile, Workspace Groups and individual workspaces, plus every Modules Profile and Workspace Group.

- Its import, transfer or restore finds each user, profile and group by identity, then by username or name (case-insensitive), updates those the destination has, adds the missing ones and keeps the others; a user keeps its membership of groups the package does not have.
- One renamed on the source server is renamed in the destination (a user whose new username another user has keeps its own, and a new user whose username another user has is left out; the completion message lists them).
- Workspaces are found by identity, then name: those the destination does not have are left out and listed, and the destination keeps the workspaces of groups and users only it has.
- Each server records the sign-ins it receives, so a user keeps the most recent last log-in of both; the preview shows it (`Last Log-in: before → after`, in the time zone of Application Runtime) for the users the import would update.
- The account that imports keeps its username, role, status and password, and nothing is imported when no active super-admin would remain.

**Auto-calculated Fields** imported or transferred are stored at once and update the CDR tables as a background task, only when they differ from those of the destination workspace; in an import of several packages it starts once every package is imported.

**PPT Templates and Designs.**

- The destination keeps its default template; the default of the package becomes the default only where the destination has none.
- A template used by a Design of the destination keeps its local definition, unless the same package also includes the Designs: checked in the preview, or left unchecked because the destination has them already (the templates then replace those they use as when the Designs are imported).
- Templates and Designs keep the order they had in the library of their workspace, ahead of those only the destination has; a package of a library still sorted by name (Designs: by NR Mode and name), or of an earlier version, adds its new ones at the end.
- The Scoring & GAP Favourite Scorings likewise take the order they had in their workspace, also when the destination already has them; when only that order differs, the preview tells it and the package stays checked.

#### Matching and creators

These elements carry the identity of each item (backups too): Designs, PPT Templates, Auto-calculated Fields, Query Builder Queries, Network Insights Favourites, Report Definitions, Scoring & GAP Report Templates, Scoring Excluded Calls and Scoring & GAP Analysis Methodologies (by their ID), the workspaces of Full Workspace and Full Environment packages, and the users, Modules Profiles and Workspace Groups of Users & Access. Items exported by earlier versions carry no identity and are found by their name.

- **Workspaces:** a Full Workspace or Full Environment import replaces the workspace with that identity, else that name, keeping its local ID and access; one renamed on the source server takes its new name (unless another workspace has it).
- **Items:** an import, transfer or backup restore replaces the item with that identity, else with the same name (case-insensitive; Designs by name and NR Mode, PPT Templates by name in each NR Mode), adds the others and keeps those only the destination has. A methodology replaced this way keeps its ID, so the Saved Scorings and reports that use it still find it.
- **Renames:** an item renamed on the source server is renamed in the destination instead of being added again, and its new name reaches what uses it: the Designs of a renamed PPT Template; the PPT Templates, Designs, saved queries and CDR tables of a renamed Auto-calculated Field; the schedule of a renamed report. Items refer to each other by ID: a Design refers to its PPT Template by the identity the template has in its own workspace (a template added apart on two servers keeps its own identity on each, and the Designs that use it are not shown as changed when they travel back and forth), and a report that names a Design by its ID on the source server finds it.
- **Name clashes:** when another item of the destination already has the name, the imported one is named `Name (2)`.
- **Creators:** each imported Design, PPT Template, methodology, Auto-calculated Field, query, favourite, report, Scoring & GAP Report Template, Favourite Scoring, list of Scoring Excluded Calls and report schedule belongs to its creator on the source server when that user exists and is active in the destination, otherwise to the user who accepts the transfer, imports the package or restores the backup. A package of an earlier version, which does not say who created an item, leaves a replaced item with its creator and gives the new ones to that user.

**The completion message** (and its App Event) opens in a wide window with the packages imported and, for each package, how many items it brought and what the import did, for example `Imported 32 Report Definitions into 1 workspace: 2 new, 1 updated and 29 unchanged.`

- **Renamed items:** for each element and workspace, a table of the items renamed (before and after, and those imported with another name because another item had theirs).
- **Updated items:** counted only when a value really changed (not when they were only saved again: when and by whom last saved, order, use count and identity are not compared). For each element and workspace, a table shows each updated item and what changed: a short value as `Role: user-editor → user-viewer`, a list as `Workspace Groups: +UK, −DE`, a password or long value by its name only. A report says what it includes and each value changed as its editor names it (for example `Filters · Regions: +London`, `Scoring & GAP Analysis · Campaigns: +Latest 2 campaigns, −Latest 4 campaigns` or `PPT Designs: +Coverage`; of its PPT Designs, only those it checks count).
- **Colours:** what was added stands out in green (`2 new`, `1 new comment`) and what was updated in amber (`3 updated`, `updated`), as do the section titles of the updated items.
- **Settings elements:** Mappings & Reference Data, Main Cities, Scoring Export Panels and NQ Calls Configuration say whether they were updated or unchanged in each workspace and list what changed. The NQ Calls Configuration names each status, team, section, field (settings and values), Status Rule, root cause entry and suggestion rule, layout of the workspace and of each user, equivalence of the Previous NQ Analyses and NQ Prioritization setting that changed (for example `Layout of ana: Columns: +Prioritization, −Scoring Impact` or `NQ Prioritization · Strategy: Dual Queue (Cities first) → Vodafone Proposal`).
- **Follow-up of the Non-Qualified Calls:** each updated call (the first 300 of an import) unfolds **Details** under its changes: every value before and after, whole, and each comment added, edited or removed with its author and text (one added or removed alone, without an empty before or after).
- **Counts:** Users & Access counts its users, Modules Profiles and Workspace Groups; Ticket Center its tickets (a new comment or screenshot updates its ticket) with the comments and screenshots added; App Events the events added and those the workspace already had.

### Exporting

- **Include generated designs and reports** decides whether their `output/` trees, and the History of [Reporting](reporting.md), are included. At least one workspace is required.
- **Folders of a complete workspace:** exporting or transferring one asks for **Output** (generated designs and reports) and **Input** (the original CDR files, needed to reprocess datasets). Leave one out when the destination already holds an identical copy, for example from an earlier transfer: the package lists its files (name and size), and when it replaces a workspace that holds all of them (by identity, else name, also in the check of a transfer before it is accepted), that workspace keeps its own folder, and with Output also the history of generated files, which travels in the workspace database. Otherwise the folder is empty (without Output files their history is left out too) and a warning says so for the Input files, the Output files or both: on a transfer in the destination's approval dialog and the source's progress dialog, on every import in its completion message.
- **Workspaces of an earlier version:** if a selected workspace has not been opened since the application was updated, its database still has an earlier layout; before the export or transfer starts, a dialog lists them and offers **Convert and include** (updating their database first, which can take several minutes for large workspaces) or **Exclude them**.
- Exports run as disk-backed jobs with estimated progress; the ZIP download starts when the package is ready.

### Import workflow

> [!IMPORTANT]
> **Only super-admins import packages.** For admins the **Import** card says so instead of offering the file; they export and transfer as before.

> [!WARNING]
> **Review replacement scope.** Import and Restore can replace existing data. Review in the preview what each package would add, update or leave as it is before importing it.

1. Drop a DriveTest Analyzer ZIP or Scoring & GAP Analysis Methodologies JSON on the **Import** card, or click it to choose one (the card names the file and its size), press **Import ZIP / JSON** and wait for its upload.
2. For Design, PPT Template, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies or Auto-calculated Field packages, choose one or more accessible destination workspaces; a matching source name is preselected when available.
3. Review the preview. It compares each package with the data of this server without importing anything, as the import would save it: each item with the creator the import gives it, the reports pointing at the Designs here and the Report Schedules of earlier packages at the reports here, the PPT Templates keeping the default of this server and, without the Designs, the definition of those its Designs use, the importing account keeping its username, role, status and password, the NQ Calls Configuration keeping what only this server has, and the NQ Call Tracking merged as its import merges it (only newer follow-up, field values and RCA results, comments added once and none removed).
   - Below the overwrite warning, a box per package says what its import would do in the words of the completion message (for example `Imports 32 Report Definitions into 1 workspace: 2 new, 1 updated and 29 unchanged.`, new and updated counts in green and amber; for App Events, how many the workspace does not have yet). **What would change** unfolds the items it would add (green) and update, with what would change in each.
   - The boxes of Report Definitions, and of the Report Schedules of an earlier package (which still import), say what they hold (each report with its schedule, email and stars, not the generated reports) and that they belong to [Reporting](reporting.md).
   - An Application Config is compared as its import would leave the whole application database: the users, Modules Profiles, Workspace Groups, tickets, Interface Settings (each module and the stage labels) and Scoring Aggregation Hierarchy it would add, update and remove (red: those only this server has). A Full Workspace or Full Environment names the workspaces whose whole database it would replace.
   - Only the packages that would change something come checked, in two columns (three on very wide screens), so a full transfer fits in one view. A package whose preview cannot be prepared says so and can still be imported.
   - Check the packages (**Select all**, **Select none** or **Invert selection**) and press **Import selected**; **Cancel** imports nothing and discards the upload.
4. Follow the background import in the floating task card.

Workspace replacement is automatic: the application closes the target when required, imports the replacement, and removes obsolete old files only after success.

### Transfer to other server

1. Choose **Content to export/transfer**.
2. Enter the destination URL/IP and port (default `7278`); the dialog remembers the last destination.
3. Press Enter or select **Connect and request approval**.
4. A destination super-admin accepts or rejects the offer.
5. Follow the creation and sending of the package at the source.
6. On arrival, the destination prepares its preview (as for an import) and nothing is imported until a super-admin chooses: **Import selected** imports the checked packages; **Reject transfer** imports nothing, deletes the package and tells the source. The preview opens on every Admin page of a super-admin, also after a reload or a restart, and the source's dialog says it is waiting for the import to be confirmed.

The transfer runs as a background task on both servers, in the red **System tasks** card. Its state is restored after a page reload; reception resumes after connection cuts, each retry into its own file. If either server stops the transfer because of an error, the other one shows the reason.

- **Source:** while it creates the package, its dialog (as that of **Export ZIP**) says which part it is archiving: the application database, the database (with its size), settings, Input and Output files of each workspace, or each element of a selection by its position; a database is first copied whole, so the bar moves once the copy is done. **Hide** closes the dialog to keep working; it comes back once when the destination starts importing, with **Hide** again, and the result stays until closed on any page. **Cancel operation**, or stopping the task, cancels the transfer at any stage; once the destination has started importing, the import continues there and its result shows there.
- **Destination:** while the source creates and sends the package, its task and dialog follow the source's progress; **Hide** closes the dialog and the task can be stopped from the card. While a package of several elements is imported, the bar moves within each element, which says what it is doing (for example the CDR it identifies by its file or the Favourite Scoring it prepares). Once the package has arrived, a dialog without **Hide** keeps every open page out of use until the import ends, because the received data replaces the current data. An import that stops without recording a result is reported as failed on both servers. An accepted transfer whose package does not arrive within 24 hours expires.
- **Network:** literal private IP destinations such as `192.168.1.17` are contacted directly, bypassing proxy variables inherited by Docker. The receiving application must listen on `0.0.0.0`, not only `127.0.0.1`, and its host firewall must allow inbound TCP on the port. When the destination is the Docker host itself, use `host.docker.internal`; another computer on the LAN uses its LAN IP.

### Request from other server

A server that cannot be reached from outside (a laptop whose network closes every incoming connection, a computer behind a NAT without port forwarding) receives the other way round: it asks the other server for the content, and every connection goes from the requesting server to the source. Only super-admins request content, as the package is reviewed like an incoming transfer.

1. Choose **Content to export/transfer** as for an export: workspace elements, Application Config, Users & Access, Ticket Center, Full Workspaces or a Full Environment. A Full Workspace names the workspace to the source; the source super-admin chooses which of their workspaces to send.
2. Press **Request from other server**, enter the source URL/IP and port and select **Connect and request approval**. With workspace elements, choose the workspaces of this server to receive them (the active one preselected).
3. A super-admin of the source sees the request on any page, as an incoming transfer: what is requested and by which server, the workspaces named, and that workspace elements come from the source's active workspace. **Accept request** opens the choice of the workspaces to send for Full Workspaces or a Full Environment (those of the same name preselected); the folders of a Full Workspace are chosen in the request dialog. **Reject** tells the requesting server. A request not accepted within 15 minutes expires.
4. The source creates the package as an export job, in its **System tasks** card, and the requesting server downloads it as soon as it is ready (resuming after a connection cut). The source deletes the package once received, or after 24 hours.
5. The requesting dialog follows the approval, the creation and the download, and can be hidden; on arrival the preview opens as for a received transfer, and nothing is imported until a super-admin chooses **Import selected** or **Reject transfer**.

Both servers record the request in App Events (received, accepted or rejected and the package sent on the source; made, completed, stopped or failed on the requester).

**Dialogs on several pages.** Every open page of a super-admin shows the dialogs of a transfer: the incoming transfer or request to accept or reject, the preview of a received package and the window with its result. Once one page handles one (accepting or rejecting, **Import selected** or **Reject transfer**, closing the result), it closes at once in the other tabs of the browser and within a few seconds in other browsers, and no page shows it again, also after a reload. The result window is closed once per user, on any page or device, and recorded in App Events (`transfer_result_seen`, with the window, the transfer, its content, status and result); the result of a transfer to another server, shown to the user who started it, closes the same way.

**Recovered transfer packages** lists, for super-admins, complete unimported packages with content, workspaces, creation time, size, **Import** and **Delete**. Incomplete remnants are removed automatically; a package still being received never is, so Admin pages can be opened or reloaded during a transfer.

## Datasets Management

- Review dataset ID, editable name, stored path, uploader, upload time and last update; below its name each dataset shows its kind (Voice, Data or Speech CDR) and its processing status (Ready, Queued, Processing, Failed or Stopped).
- Rename a dataset inline; queued and processing rows remain locked until their current work finishes.
- Preview any Ready dataset in a separate tab.
- Open Ready Data, Voice or Speech CDRs in CDR Analysis.
- Move a dataset up or down in the list (disabled while a dataset is queued or processing). Moves and renames are staged, and **Apply Changes** saves them in the background.
- Apply the ready Multivendor Mappings (each one for its Operators) and the VFUK and 3UK mappings chosen in its dialog to an eligible CDR with **Map Vendors**, or clear its persisted Vendor mapping with **Clear Vendors**.
- **Reprocess Dataset** rebuilds a Ready, Failed or Stopped dataset from its original source file after confirmation; **Stop Processing** stops one that is processing.
- Delete a dataset after confirmation whenever it is not processing.
- The bulk buttons act on every eligible dataset: **Map All**, **Clear All**, **Reprocess All** (it opens a list to confirm which datasets are rebuilt), **Stop All** (every queued or processing dataset) and **Remove All** (every dataset and its original source file, not available while one is processing).
