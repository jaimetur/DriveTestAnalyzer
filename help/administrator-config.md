# Administrator Config

Administrator Config centralises user, portability, database and dataset administration. Application-wide runtime settings are in Application Config; workspace-owned templates and chart mappings are on the separate Workspace Config page. Available actions depend on the signed-in role. Only visible for `admin` and `super-admin` roles.


> [!TIP]
> **Choose a portable component.** Use individual configuration components for settings, workspace packages for workspace content, and Full Environment for deployment-wide migration.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Roles | [Open section](#roles) |
| Users | [Open section](#users) |
| Modules Profiles | [Open section](#modules-profiles) |
| Workspace Groups | [Open section](#workspace-groups) |
| Access Requests | [Open section](#access-requests) |
| Import / Export / Transfer | [Open section](#import-export-transfer) |
| Interface Settings | [Open section](#interface-settings) |
| Database Management | [Open section](#database-management) |
| Datasets Management | [Open section](#datasets-management) |
| Reset Application | [Open section](#reset-application) |
| Operational checklist | [Open section](#operational-checklist) |

## Roles

| Role | Available administration |
| --- | --- |
| `user-viewer` | Explore the permitted workspace features, datasets and App Logs, and generate jobs (Dashboard PPTs with any filters, Scoring calculations, Network Insights analyses and exports, queries and reports). Cannot change the workspace: no uploading, deleting, reprocessing, stopping, mapping or clearing datasets, editing NR Modes, recreating combined tables, saving, renaming or deleting Dashboards, saved queries or Scoring jobs, and no access to Application Config or Workspace Config. |
| `user-editor` | edit Application Config and the active workspace's Workspace Config panels; cannot use user-management controls. |
| `admin` | manage users within policy, edit Application Config and Workspace Config, manage datasets, and export/import/transfer content for accessible workspaces. |
| `super-admin` | create or modify super-admin accounts, assign workspace access, edit Application Config and Workspace Config, export Full Environments, and approve incoming server transfers. |

An admin cannot modify a super-admin account or assign the super-admin role. The signed-in account cannot delete itself, and at least one active super-admin must remain.

**Application Config** is the application-wide runtime settings page and is available to `user-editor`, `admin` and `super-admin`. **Workspace Config** is a separate workspace-scoped page with PPT Templates Management, Main Cities, Mappings & Reference Data and Scoring & GAP Analysis Setup. Both require an active session; Workspace Config operations also require an open workspace. See [Application Config](app-config.md) and [Workspace Config](workspace-config.md) for the respective workflows.

## Users

What each account can do, see and open comes from three independent settings, and access only ever adds up:

| Setting | Decides | Where it is defined |
| --- | --- | --- |
| **Role** | what the account can do (see [Roles](#roles)) | each user |
| **Modules Profile** | which main modules it sees | [Modules Profiles](#modules-profiles) |
| **Workspaces** | which workspaces it opens: those of its Workspace Groups plus those granted to it individually | [Workspace Groups](#workspace-groups) |

Super-admins open every workspace, so their rows show **All workspaces**, and see every module unless they are given a Modules Profile: their **Modules Profile** offers **Full Access** (every module) above the profiles.

The **Users** table edits every account in place and saves each change at once:

- **User**: the name of the account (its username when it has none) above its username, ID and creation date; the pencil edits its first name, last name and username. **Password**, **Role**, **Modules Profile** and **Active**. Leave a password field empty to keep the current password. **Reset password** restores `super123`, `admin123` or `demo123` for the three bootstrap names and uses `Ericsson123` for another account; the dialog displays the resulting password so it can be changed or communicated securely.
- **Workspaces**: its **Workspace Groups**, each listed with its workspaces, and its **Individual workspaces**. The summary names the groups and counts the individual workspaces. Super-admins grant any workspace individually; admins grant and remove only the workspaces they can open, and the others are kept.
- **Reset password** and **Delete**.

Above the table, the search and the filters show only the users with a name or username, role, Modules Profile, Workspace Group (or none) or status. Tick users, or every listed user with the header box, and the bar that appears changes them all at once: **Modules Profile…**, **Add to group…**, **Remove from group…**, **Role…**, **Activate** or **Deactivate**. Users that cannot change are left as they are and listed (an admin does not change super-admins, nobody deactivates their own account, and at least one active admin and one active super-admin remain). The last row of the table creates a user with its first and last name, username, password, role, Modules Profile (the default one at first) and workspaces; new users are active, and a new super-admin, or a user who becomes one, sees every module until it is given a profile.

## Modules Profiles

**Modules Profiles** shows one card per profile. A profile is a set of main modules; every user has exactly one profile and sees its modules, and a super-admin sees every module until it is given one (**Full Access** returns it to every module). Every change on a card is saved at once and applies to all its users.

- The name and the description are edited in place.
- **Modules** shows every main module as a chip with the icon, colour and title of its tab, in the order of the main tabs (renaming or moving a tab in [Interface Settings](#interface-settings) changes the chips too, and profiles keep their modules). Click a chip to add the module to the profile or remove it; the counter shows how many modules it has.
- **Users** gives the profile to several users at once, and the names of its users are listed beside it. A user added to a profile leaves its previous one, and a user only removed from its profile gets the default profile (a super-admin, every module). Only super-admins give profiles to super-admins. The **Modules Profile** of each user in [Users](#users) follows at once, and the other way round.
- The coloured circle chooses the colour of the profile, which marks it on its card, in the **Modules Profile** of each user in [Users](#users) and in Request Access.
- **Default** marks the profile of users without one: users created without choosing one, and the users of a deleted profile. **Make default** moves it to another profile; the default profile cannot be deleted.
- The **New profile** card creates a profile without modules or users; the bin deletes a profile.

A module that is in no profile is seen only by the super-admins without a profile, as PPT Reporting (old) on a new deployment or a module added by a later version until it is added to the profiles that should have it. A module that is not shown to a user disappears from the main tabs and the Modules menu, and its pages and API answer 403. Workspace switching, dataset uploads and processing remain available everywhere. Reporting Jobs can only include artifacts of the modules their author sees; see [Reporting](reporting.md).

A new deployment starts with three profiles: **Non-Qualified Calls** (**Workspace**, Non-Qualified Calls, **Reporting** and **Builders**), **Benchmarking** (every main module except Non-Qualified Calls and PPT Reporting (old)) and **All Modules** (every main module except PPT Reporting (old)), the default one, in pink, blue and teal. Profiles are stored in the application database (`Modules Profiles` table, and each user's profile in `Users`).

## Workspace Groups

**Workspace Groups** shows one card per group. A user opens the workspaces of all their groups plus those granted to them individually; super-admins open every workspace. Every change on a card is saved at once.

- The name and the description are edited in place.
- **Workspaces** shows every workspace as a chip: click one to add it to the group or remove it. Admins change only the workspaces they can open; the others are kept.
- **Users** adds users to the group or removes them, several at once, and lists them; super-admins are not listed, since they open every workspace. The **Workspaces** of each user in [Users](#users) follow at once, and the other way round; users can also join or leave a group with the selection bar of [Users](#users).
- The **New Workspace Group** card creates a group without workspaces or users; the bin deletes a group, keeping its users and their other workspaces.

**Workspace → Access** chooses, for each workspace, its Workspace Groups and the users it is granted to individually. Groups are stored in the application database (`Workspace Groups` and `Workspace Group Members` tables).

## Access Requests

**Request Access**, below the sign-in of the login page, lets a new user ask for access without an account. Its dialog asks for:

- the **First name** and **Last name**, shown in [Users](#users);
- the **Username**: the Ericsson signum, 7 letters starting with E (stored in capitals; sign-in ignores the case);
- a **Password**, typed twice;
- the **Workspaces**, at least one: the [Workspace Groups](#workspace-groups) that open workspaces (for example DE or UK), each a tile with its description and its workspaces;
- the **Modules Profile**, required: one of the [Modules Profiles](#modules-profiles), each a tile with its description and its modules.

Nothing is chosen beforehand: **Submit Request** is enabled once every field is filled in, and the request is not sent without the names, a valid signum, matching passwords, a workspace and the modules profile.

**Submit Request** creates the user, inactive, with the `user-editor` role, in the chosen Workspace Groups and with the chosen Modules Profile. A dialog then says that the user has been created but must be activated by the administrator, and **Request Activation** opens an email in the default mail application, addressed to the administrator (the author of the application), with the user, its name, role, workspaces and modules profile, the time of the request and the address of the Admin page. The administrator reviews it and activates the user with its **Active** switch in [Users](#users), where its profile and workspaces can also be changed. When the signum already has a user, the dialog warns of it as soon as it is typed and asks for its **Current Password** instead of a new one: the request then updates its name and replaces the Workspace Groups and the Modules Profile of that user with the chosen ones (its groups that open no workspace, its individual workspaces and its role stay), deactivates it and ends its open sessions until the administrator activates it again, and the email (**Access Changed**) also lists its previous workspaces and modules profile. Administrator accounts change their access in Admin, not with a request. Every request is written to App Logs (`access_request`, or `access_change_request` for an existing user).

## Import / Export / Transfer

### Export targets

- Application Config (the whole application database, its users, Modules Profiles and Workspace Groups included)
- Users & Access (only the users, Modules Profiles and Workspace Groups)
- Dashboards from the active workspace
- PPT Templates from the active workspace
- Main Cities from the active workspace
- Mappings & Reference Data from the active workspace
- Scoring & GAP Analysis Configuration from the active workspace (all saved methodologies, default methodology, KPI definitions and GAP KPI priorities, and the Saved Filters without their results, whose CDRs are found by file in the receiving workspace)
- Auto-calculated Fields from the active workspace
- Query Builder Queries from the active workspace
- Reporting Jobs from the active workspace
- NQ Call Tracking from the active workspace (the Non-Qualified Calls Analysis Center: sections, field catalog, statuses, teams, Status Rules, root cause catalog, Ericsson RCA results, follow-up, comments and history)
- NQ Calls Configuration from the active workspace (only the configuration of the Non-Qualified Calls Analysis Center: sections, field catalog with its lists, statuses, teams with their members, Status Rules, root cause catalog with its suggestion rule and table columns, without Ericsson RCA results, follow-up, comments or history)
- An accessible workspace
- Full Environment with selected workspaces

Admins can export/transfer the active workspace's Dashboards, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Configuration, Auto-calculated Fields, Query Builder Queries, Reporting Jobs, NQ Call Tracking and NQ Calls Configuration, plus complete workspaces they can access. Super-admins can also export Application Config, Users & Access and a Full Environment.

**Users & Access** moves the users between servers without the rest of the configuration: every account with its name, password, role, active status, Modules Profile, Workspace Groups and individual workspaces, plus every Modules Profile and Workspace Group. Its import, transfer or restore adds the users, profiles and groups that are missing and updates those with the same name (without case differences), keeping the others; a user keeps its membership of groups the package does not have. Workspaces are matched by name: those the destination does not have are left out and listed in the completion message, and the destination keeps the workspaces of groups and users that only it has. The account that imports keeps its role, status and password, and nothing is imported when no active super-admin would remain.

Dashboard, template, mapping and field packages preselect a destination workspace with the same name as their source, where available, and allow one or more accessible destinations to be selected.

Importing or transferring Auto-calculated Fields stores them at once and updates the CDR tables as a background task, only when the fields differ from those of the destination workspace; in an import or transfer of several packages it starts once every package is imported.

Importing or transferring PPT Templates synchronizes the destination library with the package. Templates absent from the package are removed unless a saved local Dashboard uses them. A template used by a local Dashboard keeps its local definition when the package contains a matching name; names are matched without case differences, so the import does not create a second copy.

When the same package also includes Dashboards, its PPT Templates replace the destination library because the Dashboard definitions are replaced too. Selective backup restore uses the same rule.

A Full Environment always contains Application Config and the complete database/input content, Dashboard definitions, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Configuration, Auto-calculated Fields, Query Builder Queries, Reporting Jobs and NQ Call Tracking for every selected workspace. Selecting Full Environment only chooses the package type; the workspace picker opens when **Export ZIP** or **Transfer to other server** is pressed.

**Include generated Reports, Chart Sets and Dashboard PPT jobs** controls whether their `output/` trees, and the [Reporting](reporting.md) run history, are included. Reporting Job imports add new jobs and replace jobs with the same name; their dataset references are matched by file name in the destination workspace. At least one workspace is required.

Exporting or transferring a complete workspace asks which folders to include: **Output** (generated dashboards, reports and chart sets) and **Input** (the original CDR files, needed to reprocess datasets). Leave a folder out when the destination already holds an identical copy, for example from an earlier transfer: the package lists its files (name and size), and when it replaces a workspace with the same name that holds all of them, that workspace keeps its own folder, and with Output also the history of generated files, which travels in the workspace database. Otherwise the folder is empty (and without Output files their history is left out too), and a warning says so for the Input files, the Output files or both: on a transfer, in the destination's approval dialog and in the source's progress dialog; on every import, in its completion message.

If a selected workspace has not been opened since the application was updated, its database still has the layout of an earlier version: before the export or transfer starts, a dialog lists those workspaces and offers **Convert and include** (their database is updated to the current version first, which can take several minutes for large workspaces) or **Exclude them**.

Exports run as disk-backed jobs and show estimated progress. The ZIP download starts when package creation finishes.

### Import workflow

> [!WARNING]
> **Review replacement scope.** Import and Restore can replace existing data. Review the detected components and affected workspaces in the overwrite confirmation.

1. Drop a DriveTest Analyzer ZIP or Scoring & GAP Analysis Configuration JSON on the **Import** card, or click it to choose one (the card names the file and its size), press **Import ZIP / JSON** and wait for its upload.
2. Review the manifest-detected content, affected workspaces and overwrite warnings.
3. For Dashboard, PPT Template, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Configuration or Auto-calculated Field packages, choose one or more accessible destination workspaces; a matching source name is preselected when available.
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

## Interface Settings

**Interface Settings**, visible only to super-admins below Workspace Groups, applies to every user. Its table has one row per main module, in the order of the main tabs; drag a row by its handle (⠿) or use the arrows to move it. The Modules menu, the Help navigation and the module chips of Modules Profiles follow the same order. For each tab choose:

- **Module Title** and **Short title**, the name shown on the tab and the one used on narrow windows (empty uses the title). The Modules menu and the Help use the Module Title too: the chapter of a renamed module takes its new title in the Help navigation and as its heading, and the Help text names the module with it (section headings keep their name so their links keep working; Workspace, Reporting and Builders, also ordinary words of the Help, change where the Help names the module as a link to its chapter or in bold).
- **Icon**, shown before the title, and **Colour**, the accent of the tab: its top line and icon when not selected and its gradient when selected. The default colour keeps the palette of the module.
- The **Label** in the corner of the tab (for example ALPHA, BETA or NEW, or empty for none), its colour, and an optional icon with its own colour. By default the modules in development are labelled (ALPHA, BETA or NEW) and the stable ones (Workspace, CDR Analysis and PPT Dashboards) have an empty label. Phones and other small screens never show the labels on the tabs.

The Preview column draws each tab as it looks when it is not selected. Colours show their hexadecimal value below them to copy or paste it. The **Module labels** switch (**Show a label on the tab of each main module**), off on a new deployment, shows or hides every label at once, and **Reset tabs and labels to defaults** restores the default order, titles, icons, colours and labels. Interface Settings belong to the application configuration, so they travel with **App Config** in Import / Export, transfers to another server, Full Environment packages and backups.

## Database Management

Database Management has two clearly separated subsections: **Backup Protection** and **Database Viewer**.

### Backup Protection

> [!IMPORTANT]
> **Server-visible backup folders.** The folder picker shows storage visible to the server or container, not folders on the browser computer.

**Admin → Database Management → Backup Protection** shows the stored backups, their total size, the last successful backup and the next scheduled one above three cards: **Back up now**, **Restore** and **Scheduled backups**.

In **Back up now**, select in **Backup content** one or more content types and the workspaces they apply to:

- **Configuration Content: Application database** stores the shared application configuration, including the Scoring aggregation hierarchy, the users, Modules Profiles and Workspace Groups.
- **Configuration Content: Users & Access** stores one JSON file with the users, Modules Profiles and Workspace Groups; restore merges it like an import of [Users & Access](#export-targets), so the other users and settings are kept.
- **Workspace Content: Workspace Database** stores the selected workspace SQLite databases.
- **Workspace Content: Dashboards** stores one JSON file with every Dashboard definition and its comments for each selected workspace.
- **Workspace Content: PPT Templates** stores one CSV file for each PPT Template.
- **Workspace Content: Main Cities** stores the workspace city selection.
- **Workspace Content: Mappings & Reference Data** stores one JSON file containing every canonical Operator and Vendor, alias, row position and thematic colour, plus the Spectrum Holdings and Campaign Maps.
- **Workspace Content: Scoring & GAP Analysis Configuration** stores all saved methodologies, their default selection, KPI definitions and GAP KPI priorities, and the Saved Filters without their results; import and restore recover every Scoring Setup subpanel together and add the Saved Filters the workspace does not have yet, each finding its CDRs by the SHA-256 of their files (it waits for those not processed there yet).
- **Workspace Content: Auto-calculated Fields** stores one JSON file containing every selected workspace definition.
- **Workspace Content: NQ Call Tracking** stores one JSON file with the Non-Qualified Calls Analysis Center (sections, field catalog, statuses, teams, Status Rules, root cause catalog and Ericsson RCA results), follow-up, comments and history, with the `JOIN_ID` of each call; restore merges it into the workspace without duplicating comments, history or RCA results.
- **Workspace Content: NQ Calls Configuration** stores one JSON file with only the configuration of the Non-Qualified Calls Analysis Center (sections, field catalog, statuses, teams, Status Rules, root cause catalog and table columns); restore merges it into the workspace like the configuration part of NQ Call Tracking.
- **Workspace Content: Input** stores raw dataset files when explicitly selected.
- **Workspace Content: Output** stores generated Reports, Chart Sets and Dashboard PowerPoint jobs when explicitly selected.

Application database, Workspace Database, Dashboards, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Configuration and Auto-calculated Fields are selected by default. Main Cities precedes Mappings & Reference Data in Export and Backup/Restore component lists.

The Backup content menu expands beyond the selector on desktop to show descriptions and wraps long text within the available width, including on mobile. Input and Output are opt-in. Its **Workspaces** group lists only the workspaces you can access: the Workspace Content options apply to the selected ones and are left out of the backup when none is selected.

Dashboard, template and mapping JSON/CSV files use dedicated paths below `workspaces/<workspace name>/` in Backup and Export ZIPs; these portable paths are independent from the application's internal workspace folder name. Use **Backup folder** and **Browse** to choose the server-visible destination, then use **Backup Now** to create a ZIP in the background from the current content and workspace selection.

The content, workspaces and folder chosen are saved as soon as they change, and the card confirms **Saved for the next backups**: the next backups, scheduled ones included, use them without enabling the schedule or pressing **Save scheduler settings**, which saves the timing of the schedule. The backup job appears in the floating background-task card and keeps the Admin panel in place.

In **Restore**, choose a server-visible **Backup folder** and one of its ZIP files. The application reads the selected backup's manifest to detect its granular content and affected workspace names, with a structural fallback for older ZIPs, then shows a structured overwrite confirmation grouped into **Configuration Content**, **Workspaces** and **Workspace Content**.

Choose the parts and the workspaces of the backup to restore only after reviewing that existing data will be replaced. The Workspace Content is restored only in the selected workspaces, which must exist on this server with the same name (the others are listed as *not on this server*); the workspaces left out keep their data. Restore work also runs in the floating background-task card. The ZIP selector refreshes after an immediate backup and periodically while Admin remains open, so completed scheduled backups appear without a page reload.

Enable the schedule to select hourly, daily, weekly or monthly execution. Weekly schedules expose a weekday selector and monthly schedules expose a day-of-month selector.

Set **Retention backups** to keep a maximum number of ZIPs; the scheduler removes the oldest successful backups after creating a newer one. The default storage directory is `APP_DATA_DIR/scheduled-backups`. **Browse** opens a server-side directory picker limited to `APP_DATA_DIR`, so it reflects directories visible to the host or Docker container rather than the browser's computer. It can create a folder before selecting it.

The tiles at the top report the stored backup count and size, the most recent successful backup and the next scheduled run. Scheduled backups use the same chosen content and workspace selection as the Backup panel. Select Input and/or Output when raw datasets, Reports, Chart Sets or Dashboard PPT jobs must be included. Scheduled backups complement infrastructure backups and portable Export packages.

### Database Viewer

**Database Viewer** covers Application and Workspace Databases. It exposes global application-configuration tables, the active workspace database and the materialised combined CDR tables used to accelerate reporting; it is therefore broader than the active workspace alone.

Tables are grouped by ownership:

- **Config Tables**: global application configuration.
- **Workspace Tables**: templates, datasets, profiles, logs, workspace state, Dashboard selections, Dashboard selected rows, Dashboard PPT jobs and unified classic generated jobs.
- **Individual dataset rows**: one materialised table per dataset.
- **Combined CDR rows**: reporting acceleration tables by CDR type.

The **Table** picker lists the tables of each group by kind (Users & Access, Application, Datasets, Dashboards & Templates, Scoring & GAP Analysis, Non-Qualified Calls, Reporting, Mappings & Maps, Query Builder, Workspace, and the Voice, Data or Speech CDRs of each individual dataset), each kind in its colour, and its search box finds a table by its title or its database name.

The **Generated jobs** table contains Report and Chart Set rows, distinguished by `job_type`. Dashboard PowerPoint history is stored separately in **Dashboard PPT jobs** because each row retains its Dashboard definition and applied filter snapshot.

The **PPT Templates** table is the active workspace's `report_templates` table. It stores each template name, technology, default flag, timestamps and CSV content. Existing CSV templates are migrated automatically when their workspace is opened; compatibility CSV copies are generated only for portable packages.

#### Operator Mappings and Vendor Mappings tables

In Admin's Database Viewer, **Operator Mappings** (`operator_mappings`) and **Vendor Mappings** (`vendor_mappings`) are workspace database tables. Each stores a `source_value` and its `canonical_value`. One row maps the canonical label to itself; additional rows map source aliases to that label. These tables explain why different source spellings appear as one Operator or Vendor in charts.

Alias lookup is case-insensitive, and one source label cannot belong to two canonical groups of the same type.

The related **Chart mapping groups** table (`chart_mapping_groups`) stores each group's `mapping_type`, `canonical_value`, `position` and `color`. Its position establishes the explicit chart order: Operator order also drives Subscriber dimensions, while Vendor order drives Vendor dimensions and the Vendor part of `Operator_Vendor`. The `#RRGGBB` colour provides a stable chart theme; related shades distinguish multiple campaigns or series.

Neither alias mapping nor chart order rewrites source workbooks, individual CDR rows or combined CDR tables.

Select either mapping table in Database Viewer to inspect its rows, paginate 100 at a time, filter distinct values from a column, review active filter chips, edit a non-key cell or delete one row. `source_value` is a primary key and cannot be edited there; use Workspace Config to add or change an alias.

In **Chart mapping groups**, `mapping_type` and `canonical_value` identify the group, while `position` and `color` hold its order and colour. Direct edits to these related tables are individual row operations and can leave a group's aliases, identity or order inconsistent.

Use [Workspace Config → Operator Maps](workspace-config.md#operator-maps) or [Vendor Maps](workspace-config.md#vendor-maps) to give each name of the CDRs its label and to add, rename, colour, move or delete labels. Renaming a label also updates exact references in Report Templates and saved Dashboards, and label changes clear chart caches.

Database Viewer supports inspection, filtering and individual row edits or deletion, but a row-level change there does not perform the rename and ordering workflow of a label. Use the Workspace Config controls when changing a label so its names, order and colour stay consistent. Admin's export, transfer and backup workflows carry both mapping types together as **Mappings & Reference Data**.

Capabilities:

- 100-row server-side pagination with First/Previous/Next/Last;
- Excel-style distinct-value filters;
- active-filter chips;
- row editing and deletion;
- orphaned materialisation cleanup.

Saving or deleting a row clears analysis caches so later Dashboard and Reporting requests use the new value. Database edits affect the active workspace immediately. Use Export first when changing production data manually.

## Datasets Management

- Review dataset ID, editable name, stored path, uploader, upload time and last update; below its name each dataset shows its kind (Voice, Data or Speech CDR) and its processing status (Ready, Queued, Processing, Failed or Stopped).
- Rename a dataset inline; queued and processing rows remain locked until their current work finishes.
- Preview any Ready dataset in a separate tab.
- Open Ready Data, Voice or Speech CDRs in CDR Analysis.
- Apply available VFUK/3UK mappings to an eligible CDR or clear its persisted Vendor mapping.
- Delete a dataset after confirmation whenever it is not processing; stop active processing from Workspace first.

## Reset Application

> [!CAUTION]
> **Irreversible.** Resetting deletes every workspace and database and the whole config and data folders. Download an export from **Import / Export / Transfer** first, or copy a backup out of the data folder: backups stored inside it are deleted too.

Super-admins see a **Reset Application** button in the Administrator Config header. It opens a confirmation listing what is deleted and the config and data folders of the deployment; the reset runs only after typing `RESET APPLICATION`. The application then:

- stops background work (dataset processing, queued jobs and Query Builder runs);
- deletes every workspace, the application database (users, Modules Profiles, Workspace Groups and settings) and the whole config and data folders, scheduled backups and transfer packages included; the code and the shipped assets are kept;
- starts as a new deployment, with an empty **Default** workspace and the default accounts;
- ends every session and opens the login page, which says the application was reset.

App Logs of the new deployment record who reset the application.

## Operational checklist

1. Replace bootstrap passwords.
2. Review workspace access periodically.
3. Back up configuration and data roots.
4. Test restoration with a non-production package.
5. Review App Logs after failures or permission changes.
6. Avoid manual Database Management edits unless the impact is understood.
