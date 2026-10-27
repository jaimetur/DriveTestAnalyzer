# Super Admin

Super Admin centralises the users and their access, the tabs and labels of the modules and the databases of the application. Only visible for the `super-admin` role: portable packages and datasets are in [Administrator Config](administrator-config.md), the **Admin** tab, which admins open too.

## Presentation

The presentation **Administration** sums up Admin and Super Admin: who sees and does what (roles, Modules Profiles, Workspace Groups and Access Requests) and the management of every account in Users, the application and workspace databases with the Database Viewer, the scheduled backups and their restore, the packages and transfers between servers, the configuration of the application at every level (Application Config, Admin Config, Super Admin Config and Workspace Config) and App Events. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
administration
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Roles | [Open section](#roles) |
| Users | [Open section](#users) |
| Modules Profiles | [Open section](#modules-profiles) |
| Workspace Groups | [Open section](#workspace-groups) |
| Access Requests | [Open section](#access-requests) |
| Interface Settings | [Open section](#interface-settings) |
| Presentations | [Open section](#presentations) |
| AI Comment Writers | [Open section](#ai-comment-writers) |
| Database Management | [Open section](#database-management) |
| Reset Application | [Open section](#reset-application) |
| Operational checklist | [Open section](#operational-checklist) |

## Roles

| Role | Available administration |
| --- | --- |
| `user-viewer` | Explore the permitted workspace features, datasets and App Logs, and generate jobs (Dashboard PPTs with any filters, Scoring calculations, Network Insights analyses and exports, queries and reports). Cannot change the workspace: no uploading, deleting, reprocessing, stopping, mapping or clearing datasets, editing NR Modes, recreating combined tables, saving, renaming or deleting Dashboards, saved queries or Scoring jobs, and no access to Application Config or Workspace Config. |
| `user-editor` | edit Application Config and the active workspace's Workspace Config panels and follow up the Non-Qualified Calls; delete only the [shared items](#deleting-shared-items) they created; cannot upload datasets to a workspace, change their In Combined?, change the NQ Analysis Configuration or open Admin or Super Admin. |
| `admin` | edit Application Config and Workspace Config, upload and manage datasets (also their In Combined?), change the NQ Analysis Configuration and the table layout of the workspace in Non-Qualified Calls, and, in [Admin](administrator-config.md), export and transfer content for accessible workspaces and manage datasets; cannot import packages or open Super Admin. |
| `super-admin` | everything an admin does, import packages and export Full Environments, approve incoming server transfers and, in Super Admin, manage the users and their access (Modules Profiles and Workspace Groups), Interface Settings and Database Management, and reset the application. |

### Deleting shared items

PPT Dashboards, PPT Templates, Scoring Saved Filters, Scoring Methodologies, the saved configurations of the Scoring & GAP Analysis report editor, Reporting Jobs and favourite Bundle Report Templates are shared by the users of the workspace. Admins and super-admins delete any of them; the other roles delete only those they created (a Saved Filter belongs to the user who starred it, and only until then to the user who calculated it last, and only its owner, admins and super-admins unstar it), and for the rest the **Delete** button is disabled with a tooltip that says why; deleting several Saved Filters or Reporting Jobs at once deletes none of them when one belongs to another user, and the message names it. Imported items belong to the user who created them on the source server when that user is active here, and otherwise to the user who imports them (see [Matching and creators](administrator-config.md#matching-and-creators)). Each time a workspace opens, the items without a known creator (such as those created before v0.8.3 or brought by a transfer from an earlier version) and those created by the application (`system`, like the starter content) are assigned to `super`, the super-admin every deployment starts with (also when that account no longer exists), so only admins and super-admins delete them, and App Events records how many of each kind (`assign_unknown_creators`).

Only super-admins open Super Admin, so only they manage the accounts. The signed-in account cannot delete itself, and at least one active super-admin must remain.

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

- **User**: the name of the account (its username when it has none) above its username, ID and creation date; the pencil edits its first name, last name and username.
- **Last Log-in**: the date and time of its last sign-in, in the timezone of Application Runtime, above how long ago it was (*Never* before its first sign-in). The sign-ins recorded in App Events before v0.9.1 fill it in once.
- **Password**, **Role**, **Modules Profile** and **Active**. Leave a password field empty to keep the current password. **Reset password** restores `super123`, `admin123` or `demo123` for the three bootstrap names and uses `Ericsson123` for another account; the dialog displays the resulting password so it can be changed or communicated securely.
- **Workspaces**: its **Workspace Groups**, each listed with its workspaces, and its **Individual workspaces**. The summary names the groups and counts the individual workspaces. Super-admins grant any workspace individually.
- **Reset password** and **Delete**.

Above the table, the search and the filters show only the users with a name or username, role, Modules Profile, Workspace Group (or none) or status; the status **Pending access requests** lists the inactive users waiting for activation after an [access request](#access-requests). The badge beside **Collapse** counts the users, or those listed out of them (`10 of 16 users`). Tick users, or every listed user with the header box, and the bar that appears changes them all at once: **Modules Profile…**, **Add to group…**, **Remove from group…**, **Role…**, **Activate** or **Deactivate**. Users that cannot change are left as they are and listed (an admin does not change super-admins, nobody deactivates their own account, and at least one active admin and one active super-admin remain). The last row of the table creates a user with its first and last name, username, password, role, Modules Profile (the default one at first) and workspaces; new users are active, and a new super-admin, or a user who becomes one, sees every module until it is given a profile.

## Modules Profiles

**Modules Profiles** shows one card per profile. A profile is a set of main modules; every user has exactly one profile and sees its modules, and a super-admin sees every module until it is given one (**Full Access** returns it to every module). Every change on a card is saved at once and applies to all its users.

- The name and the description are edited in place.
- **Modules** shows every main module as a chip with the icon, colour and title of its tab, in the order of the main tabs (renaming or moving a tab in [Interface Settings](#interface-settings) changes the chips too, and profiles keep their modules). Click a chip to add the module to the profile or remove it; the counter shows how many modules it has.
- **Users** gives the profile to several users at once, and the names of its users are listed beside it. Like every list of users of the tool, it shows them by their first and last name (their username when they have none, and the filter also finds them by username), the default users (super, admin and demo) first and tagged *default user*, with a line before the others. A user added to a profile leaves its previous one, and a user only removed from its profile gets the default profile (a super-admin, every module). Only super-admins give profiles to super-admins. The **Modules Profile** of each user in [Users](#users) follows at once, and the other way round.
- The coloured circle chooses the colour of the profile, which marks it on its card, in the **Modules Profile** of each user in [Users](#users) and in Request Access.
- **Default** marks the profile of users without one: users created without choosing one, and the users of a deleted profile. **Make default** moves it to another profile; the default profile cannot be deleted.
- The **New profile** card creates a profile without modules or users; the bin deletes a profile.

A module that is in no profile is seen only by the super-admins without a profile, as PPT Reporting (old) on a new deployment or a module added by a later version until it is added to the profiles that should have it. A module that is not shown to a user disappears from the main tabs and the Modules menu, and its pages and API answer 403. Workspace switching, dataset uploads and processing remain available everywhere. Reporting Jobs can only include artifacts of the modules their author sees; see [Reporting](reporting.md).

A new deployment starts with three profiles: **Non-Qualified Calls** (**Workspace**, Non-Qualified Calls, **Reporting**, **Builders** and Ticket Center), **Benchmarking** (every main module except Non-Qualified Calls and PPT Reporting (old)) and **All Modules** (every main module except PPT Reporting (old)), the default one, in pink, blue and teal. Profiles are stored in the application database (`Modules Profiles` table, and each user's profile in `Users`).

## Workspace Groups

**Workspace Groups** shows one card per group. A user opens the workspaces of all their groups plus those granted to them individually; super-admins open every workspace. Every change on a card is saved at once.

- The name and the description are edited in place.
- **Workspaces** shows every workspace as a chip: click one to add it to the group or remove it.
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

**Submit Request** creates the user, inactive, with the `user-editor` role, in the chosen Workspace Groups and with the chosen Modules Profile. A dialog then says that the user has been created but must be activated by the administrator, and **Request Activation** opens an email in the default mail application, addressed to the administrator (the author of the application) and copied to the approvers of the deployment, with the user, its name, role, workspaces and modules profile, the time of the request and the address of the Super Admin page. The email asks one of the approvers, in an **APPROVAL NEEDED** block framed by lines, to approve the request by replying to all, and then, apart, the administrator to activate the user once one of them has approved it: the administrator then activates the user with its **Active** switch in [Users](#users), where its profile and workspaces can also be changed. When the signum already has a user, the dialog warns of it as soon as it is typed and asks for its **Current Password** instead of a new one: the request then updates its name and replaces the Workspace Groups and the Modules Profile of that user with the chosen ones (its groups that open no workspace, its individual workspaces and its role stay), deactivates it and ends its open sessions until the administrator activates it again, and the email (**Access Changed**) also lists its previous workspaces and modules profile. Administrator accounts change their access in Super Admin, not with a request. Every request is written to App Logs (`access_request`, or `access_change_request` for an existing user).

After signing in, and while signed in on any page (the pages check every few seconds, with the poll of incoming server transfers), each super-admin is told of the requests waiting for activation in a dialog like that of an incoming server transfer, with the name, username and time of each one; the same dialog lists the new [tickets](ticket-center.md#who-can-do-what) of other users, with their type, and takes in those that arrive while it is open. **Open Access Requests** opens [Users](#users) with only the **Pending access requests**, **Open Ticket Center** (by the title of the module) lists the New tickets, and **Close** closes it. Each super-admin is told of each request once, whichever button closes the dialog (App Logs `admin_notices_seen`, executed by the module of the page it was shown on), and a later request of the same user is told again. A request is pending until its user is activated; the inactive editors and viewers of earlier versions are taken as pending since their creation. Users & Access carries the pending request of each inactive user, and what each super-admin has been told of is kept in the **Admin Notices Seen** table of the application database, so Application Config exports, transfers, backups and restores include it.

## Interface Settings

**Interface Settings**, visible only to super-admins below Workspace Groups, applies to every user. Its table has one row per main module, in the order of the main tabs; drag a row by its handle (⠿) or use the arrows to move it. The Modules menu, the Help navigation and the module chips of Modules Profiles follow the same order. For each tab choose:

- **Module Title** and **Short title**, the name shown on the tab and the one used on narrow windows (empty uses the title). The Modules menu and the Help use the Module Title too: the chapter of a renamed module takes its new title in the Help navigation and as its heading, and the Help text names the module with it (section headings keep their name so their links keep working; Workspace, Reporting and Builders, also ordinary words of the Help, change where the Help names the module as a link to its chapter or in bold).
- **Icon**, shown before the title, and **Colour**, the accent of the tab: its top line and icon when not selected and its gradient when selected. The default colour keeps the palette of the module.
- The **Label** in the corner of the tab (for example ALPHA, BETA or NEW, or empty for none), its colour, and an optional icon with its own colour. By default the modules in development are labelled (ALPHA, BETA or NEW) and the stable ones (Workspace, CDR Analysis and PPT Dashboards) have an empty label. Phones and other small screens never show the labels on the tabs.

The Preview column draws each tab as it looks when it is not selected. Colours show their hexadecimal value below them to copy or paste it. The **Module labels** switch (**Show a label on the tab of each main module**), off on a new deployment, shows or hides every label at once, and **Reset tabs and labels to defaults** restores the default order, titles, icons, colours and labels. Interface Settings belong to the application configuration, so they travel with **App Config** in Import / Export, transfers to another server, Full Environment packages and backups.

## Presentations

**Presentations**, below Interface Settings, chooses the workspaces whose figures the [presentations of the Help](help.md#presentations) show (Overview, one-slider and roadmap, also in the Full Presentation): check one or several and **Save Presentations**. Their figures are added up: the CDRs (with their campaigns and the calls of the Data and Voice CDRs; a Speech CDR measures calls of the Voice one), the Network Inventories, the Vendor Mappings and the Non-Qualified Calls with their follow-up, Ericsson RCA results and comments; the users and their roles, the workspaces of the server with their campaigns and the Help, tests and releases of the application complete them. With none checked, they show those of the workspace with the most CDR rows.

The server generates every presentation of the Help, with the pictures of their slides, into the `presentations` folder of the data directory, which keeps them across restarts and updates of the application (in Docker, the data volume): none is kept with the application. It always generates them in the background, in about half a minute, so the application never waits for them. At its start, when one is missing (a first start, or a new version that brings a new one), it generates them at once, and until they are ready the Help says *The server is generating the presentations* where they go. When their figures, or the presentations of a new version, change, it generates them again at its start, the first time a signed-in user opens them in the Help and when this setting is saved; until then the Help shows the last ones. **Regenerate Presentations** generates them all again at once, whatever changed. The label of the panel says when they were generated, or *Generating…* while they are, and follows the generation. Generating them needs Node.js with the packages of `tools/presentations`, a Chromium browser (the one of [Configuration](configuration.md), else Chrome, Chromium, Brave or Edge) to draw the slides and LibreOffice to render them, which the Docker image includes; where one is missing the panel says so, **Regenerate Presentations** is disabled and the Help says why it shows no presentation. App Events records every change of the setting (`save_presentation_figures`), every **Regenerate Presentations** (`regenerate_presentations`) and every generation with who or what asked for it and why, or why it failed (`generate_presentations`, `generate_presentations_failed`).

## AI Comment Writers

The writers of the generated comments of [PPT Dashboards](ppt-dashboards.md#generated-comments) (Generate comments for this slide or for all slides, and Auto comments). The rules always read the charts on the server; an LLM writer rewrites their facts, and every figure it writes must be one of them, or the rules comment is kept.

| Setting | Effect |
| --- | --- |
| **Kiro CLI**, **Kiro Brief**, **Claude** | The writers users can choose. Without any, the rules write every comment |
| **Default writer** | Kiro CLI, Claude or Rules: the one Generate comments starts with and Auto comments and Reporting Jobs use unless they choose another (Rules when it is not enabled) |
| **Timeout** | How long a writer may take for one slide (15–900 seconds, 120 by default) |
| **API key** (Kiro CLI and Claude) | Which key each writer uses: **Each user's key** (each user saves their own in the user menu, **API keys**; Reporting Jobs use that of their owner) or **Key of the server** (one key for everyone, saved here: empty keeps the saved one, and **Remove key**, beside the field while a key is saved, removes it once you confirm, leaving the other settings as they were). By default Kiro CLI takes each user's key and Claude the key of the server; without a key of the server, Claude uses the `ANTHROPIC_API_KEY` of the server. The account of the key used is charged |
| **Kiro model** | The model Kiro CLI uses (empty: Kiro's own default) |
| **Claude** | Its model (Claude Opus 5.5 by default, Sonnet 5.5 or Haiku 5.5) and effort (Medium by default). A request Claude declines goes to Anthropic's default fallback model |

**Open Artifactory**, beside it, opens the screened Kiro CLI packages of the [Ericsson Artifactory](https://arm.seli.gic.ericsson.se/artifactory/proj-AmazonQ-Kiro-generic-local/kiro-cli/) in a new tab: open the version you want (the [Kiro CLI release notes](https://kiro.dev/changelog/cli/) list them), then **Windows_WSL**, and download **kiro-cli.deb**, a Linux package despite the name of the folder, for the Linux server of the app; when the app runs on a Mac, download **Kiro CLI.dmg** instead (a Linux package never runs on macOS, and the message says so). **Install Kiro CLI** installs that package (`.deb`, `.zip`, `.tar.gz`, the `kiro-cli` executable, or `.dmg` on a Mac, whose image is opened read-only to copy its kiro-cli programs; never a version downloaded from AWS), taking the kiro-cli program among the shell completions, icons and menu entries of the same name: the server unpacks it into `tools/kiro-cli` of its configuration folder, which keeps it across restarts and image updates (in Docker, the config volume), checks that it runs on this server (the package must match its processor) and shows its version; it is checked again every few minutes, so an update that breaks it shows here. `DRIVETEST_ANALYZER_KIRO_CLI` points to a Kiro CLI already installed instead (a local run, a team server with `module add kiro_cli`). Kiro CLI runs headless (`kiro-cli chat --no-interactive`) with no tools trusted, in an empty folder, with the API key chosen above (Kiro's API keys must be enabled by the Kiro administrator; the credits come off the plan of the key used).

The keys are written to `ai-credentials.json` in the configuration folder, readable only by the server: they are never in the application database, exports, transfers or backups, and never shown again; moving to another server, save them there again. App Events records each change of the settings (`save_comment_writers`, with the key source of each writer and whether its key of the server was replaced or removed, never a key), each Kiro CLI installed or refused (`install_kiro_cli`, `install_kiro_cli_failed`) and the API keys each user saves or removes (`save_user_api_keys`).

## Database Management

Database Management has two clearly separated subsections: **Backup Protection** and **Database Viewer**.

### Backup Protection

> [!IMPORTANT]
> **Server-visible backup folders.** The folder picker shows storage visible to the server or container, not folders on the browser computer.

**Super Admin → Database Management → Backup Protection** shows the stored backups, their total size, the last successful backup and the next scheduled one above three cards: **Back up now**, **Restore** and **Scheduled backups**.

In **Back up now**, select in **Backup content** one or more content types and the workspaces they apply to:

- **Configuration Content: Application database** stores the shared application configuration, including the Scoring aggregation hierarchy, the users, Modules Profiles, Workspace Groups and tickets.
- **Configuration Content: Users & Access** stores one JSON file with the users, Modules Profiles and Workspace Groups; restore merges it like an import of [Users & Access](administrator-config.md#export-targets), so the other users and settings are kept.
- **Configuration Content: Ticket Center** stores one JSON file with every ticket, its type and its timeline, and each screenshot as a file; restore merges them into the server like an import of Ticket Center, without deleting any.
- **Workspace Content: Workspace Database** stores the selected workspace SQLite databases.
- **Workspace Content: Dashboards** stores one JSON file with every Dashboard definition and its comments for each selected workspace; restore replaces the Dashboards the workspace has and adds the others, like an import (see [Matching and creators](administrator-config.md#matching-and-creators)).
- **Workspace Content: PPT Templates** stores one CSV file for each PPT Template; restore replaces the templates the workspace has and adds the others, like an import.
- **Workspace Content: Main Cities** stores the workspace city selection.
- **Workspace Content: Mappings & Reference Data** stores one JSON file containing every canonical Operator and Vendor, alias, row position and thematic colour, and the comments of the Operator names, plus the Spectrum Holdings, Serving Networks and Campaign Maps.
- **Workspace Content: Scoring & GAP Analysis Methodologies** stores all saved methodologies, their default selection, KPI definitions and GAP KPI priorities (the Favourites Filters and the report configurations have their own content types); restore replaces the methodologies the workspace has and adds the others, like an import, keeping its default methodology. Backups made before also carry the Favourites Filters and the report configurations here, and their restore still recovers them, adding the Saved Filters the workspace does not have yet, each finding its CDRs by the SHA-256 of their files (it waits for those not processed there yet).
- **Workspace Content: Auto-calculated Fields** stores one JSON file containing every selected workspace definition; restore replaces the fields the workspace has and adds the others, like an import.
- **Workspace Content: Network Insights Favourites**, **Bundle Report Template Favourites**, **Scoring & GAP Favourites Filters**, **Scoring & GAP Report Templates**, **Scoring Export Panels** and **Scoring Excluded Calls** each store one JSON file with the favourite Analysis Selections, the favourite Bundle Report Templates, the Favourites Filters (without their results), the saved configurations of the Scoring report editor, the exportable Scoring panels or the lists of Excluded Calls; restore adds them like an import of their element.
- **Workspace Content: NQ Call Tracking** stores one JSON file with the Non-Qualified Calls Analysis Center (sections, field catalog, statuses, teams, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, root cause catalog and Ericsson RCA results), follow-up, comments and history, with the `JOIN_ID` of each call; restore merges it into the workspace without duplicating comments, history or RCA results.
- **Workspace Content: NQ Calls Configuration** stores one JSON file with only the configuration of the Non-Qualified Calls Analysis Center (sections, field catalog, statuses, teams, Status Rules, DT Analyzer RCA Rules, Prioritization Rules, root cause catalog and table columns); restore merges it into the workspace like the configuration part of NQ Call Tracking.
- **Workspace Content: App Events** stores one JSON file with every App Event of the workspace; restore adds the events the workspace does not have (the same user, action, details and time), among its own by date.
- **Workspace Content: Input** stores raw dataset files when explicitly selected.
- **Workspace Content: Output** stores generated Reports, Chart Sets and Dashboard PowerPoint jobs when explicitly selected.

Application database, Workspace Database, Dashboards, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies and Auto-calculated Fields are selected by default. Main Cities precedes Mappings & Reference Data in Export and Backup/Restore component lists.

The Backup content menu expands beyond the selector on desktop to show descriptions and wraps long text within the available width, including on mobile. Input and Output are opt-in. Its **Workspaces** group lists only the workspaces you can access: the Workspace Content options apply to the selected ones and are left out of the backup when none is selected. Workspace Content lists Workspace Database, Input and Output first and then the other contents by module, as Current Workspace Content does in [Export / Transfer](administrator-config.md#export-targets).

Dashboard, template and mapping JSON/CSV files use dedicated paths below `workspaces/<workspace name>/` in Backup and Export ZIPs; these portable paths are independent from the application's internal workspace folder name. Use **Backup folder** and **Browse** to choose the server-visible destination, then use **Backup Now** to create a ZIP in the background from the current content and workspace selection; the line below the selection says what that backup keeps. **Backup Now** first asks whether it is a **Full backup** or a **Light backup** (without the workspace databases, Input and Output, so it needs other content selected too), with the size of the latest scheduled backup of each kind; **Cancel** makes none.

The content, workspaces and folder chosen are saved as soon as they change, and the card confirms **Saved for the next backups**: the next backups, scheduled ones included, use them without enabling the schedule or pressing **Save scheduler settings**, which saves the timing of the schedule. The backup job appears in the floating background-task card and keeps the Admin panel in place.

In **Restore**, choose a server-visible **Backup folder**, the **Backup type** (**Full backups** or **Light backups**, those the schedule makes without the workspace databases, Input and Output) and one of the ZIP files of that type, from the `full` or `light` folder of the backup folder (and the backup folder itself, for backups copied there, which count as full); those made with **Backup Now** say so. The application reads the selected backup's manifest to detect its granular content and affected workspace names, with a structural fallback for older ZIPs, then shows a structured overwrite confirmation grouped into **Configuration Content**, **Workspaces** and **Workspace Content**.

Choose the parts and the workspaces of the backup to restore only after reviewing that existing data will be replaced. The Workspace Content is restored only in the selected workspaces, which must exist on this server with the same name (the others are listed as *not on this server*); the workspaces left out keep their data. Restore work also runs in the floating background-task card. The ZIP selector refreshes after an immediate backup and periodically while Admin remains open, so completed scheduled backups appear without a page reload.

Enable the schedule to select hourly, every 4 hours, daily, weekly or monthly execution. Hourly schedules use the minute of the **Execution time**, every 4 hours schedules run every 4 hours from its hour (01:30 runs at 01:30, 05:30, 09:30 and so on), weekly schedules expose a weekday selector and monthly schedules expose a day-of-month selector.

Hourly, every 4 hours and daily schedules can turn **Light backups** on: the backups between the full ones leave the workspace databases, Input and Output out, and a full backup is made once a week on the **Full backup day** (the first backup of that day). A full backup missed, because the server was off or had no room for it, is made at the next backup.

Full backups, scheduled or made with **Backup Now**, go to the `full` folder of the backup folder, and light ones to its `light` folder; the backups made before, all full, are moved from the backup folder of the schedule and the default one into their `full` folder when the application starts (recorded in App Events). After each scheduled backup, the scheduler keeps every scheduled backup of the last **Days to keep** days (today included), and of the full ones the newest and the newest of each of the last **Weeks to keep** weeks and **Months to keep** months (this week and this month included; 7 days, 4 weeks and 6 months by default); it deletes the other scheduled backups and records them in App Events. Schedules saved before kept a number of backups, now the days those backups covered. Backups made with **Backup Now** are never deleted, so remove those no longer needed from the folder; backups made before backups recorded who made them count as scheduled ones.

Backups stay in the chosen folder of this server: copy them to other storage outside the application to keep them away from its disk. Before writing anything, a backup checks that the folder has room for the snapshot of its largest database (made there, one database at a time) and for the ZIP, estimated from the latest backup of the same content; on macOS the room counts what the system frees on demand (local Time Machine snapshots, caches), as its storage settings show it. Without room it is not started; a scheduled one with **Light backups** on is made light instead. The reason shows below the tiles until a scheduled backup is made as configured, and is recorded in App Events.

The default storage directory is `APP_DATA_DIR/scheduled-backups`. **Browse** opens a server-side directory picker limited to `APP_DATA_DIR`, so it reflects directories visible to the host or Docker container rather than the browser's computer. It can create a folder before selecting it.

Below the settings, the panel says what **Days to keep**, **Weeks to keep** and **Months to keep** keep as the schedule is set (with **Light backups** on, the full backups are the weekly ones, and it names those among the days kept), the dates a backup made today keeps, and the most light and full backups kept at the same time over the next year, with the space they take from the size of the latest scheduled ones, to tell how much room the backup folder needs. The tiles at the top report the stored backups and their total size, each with how many and how much of them are full and light, and the most recent successful backup and the next scheduled run, each saying whether it is full or light. Scheduled backups use the same chosen content and workspace selection as the Backup panel. Select Input and/or Output when raw datasets, Reports, Chart Sets or Dashboard PPT jobs must be included. Scheduled backups complement infrastructure backups and portable Export packages.

What interrupted work leaves behind is removed once a night, between 00:00 and 07:00, after a quarter of an hour without anyone using the application and while no import, export, transfer, backup, restore or CDR processing is running (when two days pass without a cleanup, at the next idle moment): the snapshots and partial ZIPs of backups killed mid-write, the temporary folders of imports, exports, transfers and restores, the uploads of CDRs never finished after a week, and the temporary files of the workspace caches, all untouched for six hours. Each backup also first removes what an interrupted backup left in its folder. What is removed, with the space freed, is recorded in App Events.

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

In the Database Viewer of Super Admin, **Operator Mappings** (`operator_mappings`) and **Vendor Mappings** (`vendor_mappings`) are workspace database tables. Each stores a `source_value` and its `canonical_value`. One row maps the canonical label to itself; additional rows map source aliases to that label. These tables explain why different source spellings appear as one Operator or Vendor in charts.

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

## Reset Application

> [!CAUTION]
> **Irreversible.** Resetting deletes every workspace and database and the whole config and data folders. Download an export from [Import / Export / Transfer](administrator-config.md#import-export-transfer) first, or copy a backup out of the data folder: backups stored inside it are deleted too.

Super-admins see a **Reset Application** button in the Super Admin header. It opens a confirmation listing what is deleted and the config and data folders of the deployment; the reset runs only after typing `RESET APPLICATION`. The application then:

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
