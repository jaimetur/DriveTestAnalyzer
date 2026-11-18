# Super Admin

Super Admin, for the `super-admin` role only, centralises the users and their access, the tabs and labels of the modules and the databases of the application. Portable packages and datasets are in [Administrator Config](administrator-config.md), the **Admin** tab, which admins open too.

## Presentation

```presentations
administration
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Know what each role can do | [Roles](#roles) |
| <span class="guide-sub">↳ Delete items shared by others</span> | <span class="guide-sub">↳ [Deleting shared items](#deleting-shared-items)</span> |
| Create and manage the user accounts | [Users](#users) |
| Choose the modules each user sees | [Modules Profiles](#modules-profiles) |
| Choose which workspaces each user sees | [Workspace Groups](#workspace-groups) |
| Answer access requests | [Access Requests](#access-requests) |
| <span class="guide-sub">↳ Reset forgotten passwords</span> | <span class="guide-sub">↳ [Forgotten passwords](#forgotten-passwords)</span> |
| Rename the modules or change the look of the tool | [Interface Settings](#interface-settings) |
| Choose the figures of the Help presentations | [Presentations](#presentations) |
| Set up the AI comment writers | [AI Comment Writers](#ai-comment-writers) |
| Protect, back up or browse the databases | [Database Management](#database-management) |
| <span class="guide-sub">↳ Protect and schedule the backups</span> | <span class="guide-sub">↳ [Backup Protection](#backup-protection)</span> |
| <span class="guide-sub">↳ Browse the tables of a database</span> | <span class="guide-sub">↳ [Database Viewer](#database-viewer)</span> |
| Reset the application | [Reset Application](#reset-application) |
| Check the platform regularly | [Operational checklist](#operational-checklist) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Roles

| Role | Available administration |
| --- | --- |
| `user-viewer` | Explore the permitted workspace features, datasets and App Logs, and generate jobs (PPTs with any filters, Scoring calculations, Network Insights analyses and exports, queries and reports). Cannot change the workspace: no uploading, deleting, reprocessing, stopping, mapping or clearing datasets, editing NR Modes, recreating combined tables, saving, renaming or deleting Designs, saved queries or Scoring jobs, and no access to Application Config or Workspace Config. |
| `user-editor` | edit Application Config and the active workspace's Workspace Config panels and follow up the Non-Qualified Calls; delete only the [shared items](#deleting-shared-items) they created; cannot upload datasets to a workspace, change their Active?, change the NQ Analysis Configuration or open Admin or Super Admin. |
| `admin` | edit Application Config and Workspace Config, upload and manage datasets (also their Active?), change the NQ Analysis Configuration and the table layout of the workspace in Non-Qualified Calls, and, in [Admin](administrator-config.md), export and transfer content for accessible workspaces and manage datasets; cannot import packages or open Super Admin. |
| `super-admin` | everything an admin does, import packages and export Full Environments, approve incoming server transfers and, in Super Admin, manage the users and their access (Modules Profiles and Workspace Groups), Interface Settings and Database Management, and reset the application. |

### Deleting shared items

PPT Designs, PPT Templates, Saved Scorings, Scoring Methodologies, the saved configurations of the Scoring & GAP Analysis report editor and the reports of [Reporting](reporting.md) are shared by the users of the workspace.

- **Who deletes them:** admins and super-admins delete any; the other roles only those they created. Otherwise **Delete** is disabled with a tooltip that says why.
- **Saved Scorings:** one belongs to the user who starred it, and until then to the user who calculated it last; only its owner, admins and super-admins unstar it. Deleting several at once deletes none when one belongs to another user, and the message names it.
- **Imported items** belong to their creator on the source server when that user is active here, otherwise to the importer (see [Matching and creators](administrator-config.md#matching-and-creators)).
- **Unknown creators:** each time a workspace opens, the items without a known creator (created before v0.8.3 or brought by a transfer from an earlier version) and those created by `system` (such as the starter content) are assigned to `super`, the super-admin every deployment starts with (also when that account no longer exists), so only admins and super-admins delete them; App Events records how many of each kind (`assign_unknown_creators`).
- **PPT Designs and PPT Templates** of an admin or a super-admin (or of `super`) are changed and deleted only by their creator and by super-admins, never by another admin (see [Who changes a Design](ppt-designer.md#who-changes-a-design)).

Only super-admins open Super Admin, so only they manage the accounts. The signed-in account cannot delete itself, and at least one active super-admin must remain. Access to [Application Config](app-config.md) and [Workspace Config](workspace-config.md) follows the roles above.

## Users

What each account can do, see and open comes from three independent settings, and access only ever adds up:

- **Role:** what it can do (see [Roles](#roles)).
- **Modules Profile:** which main modules it sees (see [Modules Profiles](#modules-profiles)).
- **Workspaces:** those of its [Workspace Groups](#workspace-groups) plus those granted to it individually. Super-admins open every workspace (their rows show **All workspaces**) and see every module unless given a Modules Profile (their **Modules Profile** offers **Full Access** above the profiles).

The **Users** table edits every account in place and saves each change at once:

- **User:** the name of the account (its username when it has none) above its username, ID, creation date and email address; the pencil edits first name, last name, username and email. A green dot on its initials marks a user online now (a page of the tool open in the last minute), updated while the page stays open.
- **Online:** a green **N online** pill beside the number of users counts the users online now, kept up to date as they come and go; a click on it lists them first (again to reverse), remembered like the sort of the columns.
  - The email receives the account's [Ticket Center](ticket-center.md#email-updates) updates, the activation of its access request and the links to choose a new password; each user also changes it with **Email address** in the user badge menu. Accounts of before v0.12.0 were given `first.last@ericsson.com` from their names (none when two accounts would share it): correct it where the real address differs.
- **Last Log-in:** date and time of its last sign-in, in the timezone of Application Runtime, above how long ago it was (*Never* before the first). Sign-ins recorded in App Events before v0.9.1 fill it in once.
- **Password**, **Role**, **Modules Profile** and **Active**. An empty password field keeps the current password.
- **Workspaces:** its **Workspace Groups**, each listed with its workspaces, and its **Individual workspaces**; the summary names the groups and counts the individual workspaces. Super-admins grant any workspace individually.
- **Reset password** restores `super123`, `admin123` or `demo123` for the three bootstrap names and `Ericsson123` for any other account; the dialog shows the resulting password so it can be changed or communicated securely. **Delete** deletes the account.

Above the table:

- **New user**, at the end of the bar of search and filters, opens a dialog (name, username, email address, password, role, Modules Profile and workspaces) with **Cancel** and **Create user**. It shows the user's initials and suggests the email `name.surname@ericsson.com` from the names until another address is typed. A new user is active, with the default Modules Profile at first; a new super-admin, or a user who becomes one, sees every module until given a profile.
- **Search and filters:** by name or username, role, Modules Profile, Workspace Group (or none) or status; the status **Pending access requests** lists the inactive users waiting for activation after an [access request](#access-requests). The badge beside **Collapse** counts the users, or those listed (`10 of 16 users`).
- **Sorting:** click the title of any column but **Password**, again to reverse (an arrow shows it): **User** by name, **Last Log-in** most recent first (*Never* last), **Role** from `user-viewer` to `super-admin`, **Modules Profile**, **Active** active first, and **Workspaces**. The sort follows the changes made in the table, and the browser remembers it.
- **Changing several users:** tick users, or every listed user with the header box, and use the bar that appears: **Modules Profile…**, **Add to group…**, **Remove from group…**, **Role…**, **Activate** or **Deactivate**. Users that cannot change are left as they are and listed (an admin does not change super-admins, nobody deactivates their own account, and at least one active admin and one active super-admin remain).

## Modules Profiles

A profile is a set of main modules. Every user has exactly one and sees its modules; a super-admin sees every module until given one (**Full Access** returns it to every module). **Modules Profiles** shows one card per profile, and every change on a card is saved at once for all its users:

- **Name** and **description**, edited in place.
- **Modules:** every main module as a chip with the icon, colour and title of its tab, in tab order (renaming or moving a tab in [Interface Settings](#interface-settings) changes the chips; profiles keep their modules). Click a chip to add or remove it; the counter shows how many the profile has.
- **Users:** gives the profile to several users at once and lists them. Like every list of users of the tool, it shows them by first and last name (username when they have none; the filter also finds usernames), the default users (super, admin and demo) first, tagged *default user*, with a line before the others. A user added leaves its previous profile, and one only removed gets the default profile (a super-admin, every module). Only super-admins give profiles to super-admins. The **Modules Profile** column of [Users](#users) follows at once, and the other way round.
- **Colour** (the coloured circle): marks the profile on its card, in the **Modules Profile** of each user and in Request Access.
- **Default:** the profile of users without one (created without choosing one, or whose profile was deleted). **Make default** moves it; the default profile cannot be deleted.
- **New Modules Profile** opens a dialog that creates a profile without modules or users; the bin deletes a profile.

A module that is in no profile is seen only by the super-admins without a profile, as a module added by a later version until it is added to the profiles that should have it. A module not shown to a user disappears from the main tabs and the Modules menu, and its pages and API answer 403; workspace switching, dataset uploads and processing remain available everywhere.

A new deployment starts with five profiles, in pink, blue, teal, green and purple: **Non-Qualified Calls** (**Workspace**, Non-Qualified Calls, **Reporting**, **Builders**, AI Assistant and Ticket Center), **Benchmarking** (every main module except Non-Qualified Calls), **All Modules** (every main module, the default one), **Reporting** (**Reporting**, AI Assistant and Ticket Center) and **Executive Reporting** (Scoring & GAP Analysis, **Reporting**, AI Assistant and Ticket Center). A deployment older than the last two gets them once, unless it already has a profile of that name; deleted or changed afterwards, they stay as they were left. Profiles are stored in the application database (`Modules Profiles` table, and each user's profile in `Users`).

## Workspace Groups

A user opens the workspaces of all their groups plus those granted to them individually; super-admins open every workspace. **Workspace Groups** shows one card per group, and every change is saved at once:

- **Name** and **description**, edited in place.
- **Workspaces:** every workspace as a chip; click one to add or remove it.
- **Users:** adds or removes several users at once and lists them; super-admins are not listed. The **Workspaces** of each user in [Users](#users) follow at once, and the other way round; users also join or leave a group with the selection bar of [Users](#users).
- **New Workspace Group** opens a dialog that creates a group without workspaces or users; the bin deletes a group, keeping its users and their other workspaces.

**Workspace → Access** chooses, for each workspace, its Workspace Groups and the users granted it individually. Groups are stored in the application database (`Workspace Groups` and `Workspace Group Members` tables).

## Access Requests

**Request Access**, below the sign-in of the login page, lets a new user ask for access without an account. Its dialog asks for:

- **First name** and **Last name**, shown in [Users](#users);
- **Email address**, prefilled as `first.last@ericsson.com` until another is typed; only Ericsson addresses (`ericsson.com` or a subdomain) are accepted, and an existing user who leaves it empty keeps its own if it is of Ericsson;
- **Username:** the Ericsson signum, 7 letters starting with E (stored in capitals; sign-in ignores case);
- **Password**, typed twice;
- **Workspaces**, at least one: the [Workspace Groups](#workspace-groups) that open workspaces (for example DE or UK), as tiles with their description and workspaces;
- **Modules Profile**, required: one of the [Modules Profiles](#modules-profiles), as tiles with their description and modules.

Nothing is preselected, and **Submit Request** is enabled only once every field is valid. It creates the user, inactive, as `user-editor`, in the chosen groups and profile, and says the administrator must activate it.

- **The email** goes to the administrator (the author of the application), copied to the approvers of the deployment and the requester, with the user, name, email, role, workspaces, profile, time of the request and the address of the Super Admin page. With [Email Delivery](app-config.md#email-delivery) set up and **Access requests** checked, the tool sends it at once on the requester's behalf (replies go to the requester) and the dialog says so; otherwise, or if it fails, **Request Activation** opens it in the default mail application.
  - An **Approval needed** box that stands out (framed by lines, in capitals, in the mail application) asks an approver to approve by replying to all; an **After the approval** box asks the administrator to activate the user then. The tool's email lists the details in a table, each Workspace Group and the profile in bold with what they open, and ends with an **Open Super Admin** button (at the Public address of the server when set).
- **Activation:** with the user's **Active** switch in [Users](#users) (or **Activate** in its selection bar), where its profile and workspaces can also change. With **Access requests** checked, the user is emailed its activation, profile, Workspace Groups and a sign-in link, copied to the administrator and the approvers.
- **Existing users:** a signum that already has a user is warned of as soon as it is typed, and the dialog asks for its **Current Password** instead of a new one. The request updates the name, replaces its Workspace Groups and profile with those chosen (groups that open no workspace, individual workspaces and role stay), deactivates it and ends its sessions until reactivated; the email (**Access Changed**) also lists the previous workspaces and profile. Administrator accounts change their access in Super Admin, not with a request.
- **App Logs** records every request (`access_request`, or `access_change_request` for an existing user) and every email (see [Email Delivery](app-config.md#email-delivery)).

**Notices to super-admins.** After signing in and on any page (checked every few seconds with the poll of incoming transfers, every 30 seconds in a hidden tab), each super-admin is told, in a dialog like that of an incoming transfer, of the requests waiting for activation (name, username, time) and of the new [tickets](ticket-center.md#who-can-do-what) still **New** that other users opened and it has not opened (with their type); the dialog takes in what arrives while open.

- **Open Access Requests** opens [Users](#users) filtered on **Pending access requests**; **Open Ticket Center** (by the module title) lists the New tickets; **Close** closes it.
- Each request and ticket is told once to each super-admin, whatever button closes the dialog (App Logs `admin_notices_seen`, executed by the module of the page); a later request of the same user is told again.
- A request is pending until its user is activated; inactive editors and viewers of earlier versions count as pending since their creation. Users & Access carries each inactive user's pending request, and the **Admin Notices Seen** table of the application database keeps what each super-admin was told, so Application Config exports, transfers, backups and restores include it.

### Forgotten passwords

When [Email Delivery](app-config.md#email-delivery) is set up, **Forgot your password?**, below the sign-in of the login page, asks for the username and emails the user a link to choose a new password, also to a user whose access request still waits for activation.

- The link works once and for 60 minutes; a new one can be asked for after a minute. It opens the login page with **Choose a new password**, and the new password ends the open sessions of the user.
- A user without an email address is asked to contact the administrator, who can still reset the password from [Users](#users).
- App Logs records each link sent (`password_reset_requested`) and each password chosen with one (`password_reset`), as public actions of the sign-in page.

## Interface Settings

**Interface Settings** applies to every user. Its table has one row per main module, in tab order; drag a row by its handle (⠿) or use the arrows to move it, and the Modules menu, the Help navigation and the module chips of Modules Profiles follow. For each tab:

- **Module Title** and **Short title:** the name on the tab, and the one used on narrow windows and in the browser tab of its pages (empty uses the title; CDR Analysis, PPT Designer, Network Insights and AI Assistant always use the Module Title in the browser tab).
  - The Modules menu and the Help use the Module Title: a renamed module's chapter takes its new title in the Help navigation and as its heading, and the Help text names the module with it. Section headings keep their name so their links keep working; Workspace, Reporting and Builders, also ordinary words, change where the Help names the module as a link to its chapter or in bold.
- **Icon**, shown before the title, and **Colour**, the accent of the tab (its top line and icon when not selected, its gradient when selected); the default keeps the palette of the module.
- **Label** in the corner of the tab (for example ALPHA, BETA or NEW, or empty), its colour and an optional icon with its own colour. By default the modules in development are labelled and the stable ones (Workspace, CDR Analysis and PPT Designer) have none (see [Web Interfaces](web-interface.md#navigation)). Phones and other small screens never show the labels.

The Preview column draws each tab as it looks when not selected; colours show their hexadecimal value below them to copy or paste it. The **Module labels** switch (**Show a label on the tab of each main module**), off on a new deployment, shows or hides every label, and **Reset tabs and labels to defaults** restores the default order, titles, icons, colours and labels. Interface Settings travel with **App Config** in Import / Export, transfers, Full Environment packages and backups.

## Presentations

**Presentations** chooses the workspaces whose figures the [presentations of the Help](help.md#presentations) show (Overview, one-slider and roadmap, also in the Full Presentation): check one or several and **Save Presentations**. With none checked, they show those of the workspace with the most CDR rows.

- **Figures added up:** the CDRs (with their campaigns and the calls of the Data and Voice CDRs; a Speech CDR measures calls of the Voice one), the Network Inventories, the Vendor Mappings and the Non-Qualified Calls with their follow-up, Ericsson RCA results and comments; the users and roles, the workspaces of the server with their campaigns, and the Help, tests and releases of the application complete them.
- **Where they are kept:** the server generates every presentation of the Help, with the pictures of its slides, into the `presentations` folder of the data directory (in Docker, the data volume), which keeps them across restarts and updates; none is kept with the application.
- **When:** always in the background, in about half a minute, so the application never waits. At start, when one is missing (a first start, or a new version that brings one), at once, the Help saying *The server is generating the presentations* meanwhile. When their figures, or the presentations of a new version, change: at the next start, the first time a signed-in user opens them in the Help and when this setting is saved; until then the Help shows the last ones. **Regenerate Presentations** generates them all again at once. The label of the panel says when they were generated, or *Generating…*.
- **Requirements:** Node.js with the packages of `tools/presentations`, a Chromium browser (that of [Configuration](configuration.md), else Chrome, Chromium, Brave or Edge) to draw the slides and LibreOffice to render them, all in the Docker image. Where one is missing the panel says so, **Regenerate Presentations** is disabled and the Help says why it shows no presentation.
- **App Events:** every change of the setting (`save_presentation_figures`), every **Regenerate Presentations** (`regenerate_presentations`) and every generation with who or what asked for it and why, or why it failed (`generate_presentations`, `generate_presentations_failed`).

## AI Comment Writers

The writers of the generated comments of [PPT Designer](ppt-designer.md#generated-comments) (Generate comments for this slide or for all slides, and Auto comments). The rules always read the charts on the server; an LLM writer rewrites their facts, and every figure it writes must be one of them, or the rules comment is kept. The [AI Assistant](assistant.md) answers with the same engines: the enabled Kiro CLI and Claude, with their keys, models, effort and timeout (for each request of a question), the default one first in its engine selector; with none enabled, it asks nothing.

Three cards, side by side: the choosable writers, default writer and timeout; Kiro CLI (enabled or not, installed or not, and its installation); and Claude (enabled or not), each with key, model and (Claude) effort. **Save AI Comment Writers** saves all three.

| Setting | Effect |
| --- | --- |
| **Kiro CLI**, **Kiro Brief**, **Claude** | The writers users can choose. Without any, the rules write every comment |
| **Default writer** | Kiro CLI, Claude or Rules: the one Generate comments starts with and Auto comments use unless they choose another (Rules when it is not enabled) |
| **Timeout** | How long a writer may take for one slide (15–900 seconds, 120 by default) |
| **API key** (Kiro CLI and Claude) | **Each user's key** (each user saves their own in the user menu, **API keys**) or **Key of the server** (one key for everyone, saved here: empty keeps the saved one; **Remove key**, beside the field while a key is saved, removes it once you confirm, leaving the other settings). By default Kiro CLI takes each user's key and Claude the key of the server; without a key of the server, Claude uses the `ANTHROPIC_API_KEY` of the server. The account of the key used is charged |
| **Kiro model** | The model Kiro CLI uses (empty: Kiro's own default) |
| **Claude** | Its model (Claude Opus 5.5 by default, Sonnet 5.5 or Haiku 5.5) and effort (Medium by default). A request Claude declines goes to Anthropic's default fallback model |

**Installing Kiro CLI:**

1. **Open Artifactory** opens the screened Kiro CLI packages of the [Ericsson Artifactory](https://arm.seli.gic.ericsson.se/artifactory/proj-AmazonQ-Kiro-generic-local/kiro-cli/) in a new tab. Open the version you want (the [Kiro CLI release notes](https://kiro.dev/changelog/cli/) list them), then **Windows_WSL**, and download **kiro-cli.deb**, a Linux package despite the name of the folder, for the Linux server of the app; when the app runs on a Mac, download **Kiro CLI.dmg** (a Linux package never runs on macOS, and the message says so).
2. **Install Kiro CLI** installs that package (`.deb`, `.zip`, `.tar.gz`, the `kiro-cli` executable, or `.dmg` on a Mac, whose image is opened read-only to copy its kiro-cli programs; never a version downloaded from AWS), taking the kiro-cli program among the shell completions, icons and menu entries of the same name.
3. The server unpacks it into `tools/kiro-cli` of its configuration folder, which keeps it across restarts and image updates (in Docker, the config volume), checks that it runs on this server (the package must match its processor) and shows its version.

It is checked again every few minutes, so an update that breaks it shows here: while Kiro CLI is not installed, or no longer runs, a warning card in its section says so (and, when it is enabled, that the rules write the comments asked of it until it works). `DRIVETEST_ANALYZER_KIRO_CLI` points to a Kiro CLI already installed instead (a local run, a team server with `module add kiro_cli`). Kiro CLI runs headless (`kiro-cli chat --no-interactive`) with no tools trusted, in an empty folder, with the API key chosen above (Kiro's API keys must be enabled by the Kiro administrator; the credits come off the plan of the key used).

The keys are written to `ai-credentials.json` in the configuration folder, readable only by the server: never in the application database, exports, transfers or backups, and never shown again; on another server, save them there again. App Events records each change of the settings (`save_comment_writers`, with the key source of each writer and whether its server key was replaced or removed, never a key), each Kiro CLI installed or refused (`install_kiro_cli`, `install_kiro_cli_failed`) and the API keys each user saves or removes (`save_user_api_keys`).

## Database Management

Database Management has two subsections: **Backup Protection** and **Database Viewer**.

### Backup Protection

> [!IMPORTANT]
> **Server-visible backup folders.** The folder picker shows storage visible to the server or container, not folders on the browser computer.

The top of **Backup Protection** shows:

- the stored backups and their total size, each with how many and how much are full and light;
- the free space of the backup folder's disk, with its size and use (in Docker, the host disk of the mounted data folder, not the container's; on macOS counting space the system frees on demand), red with a note under 50 GB;
- the last successful backup and the next scheduled one, each saying whether it is full or light;

and three cards: **Back up now**, **Restore** and **Scheduled backups**.

#### Backup content

**Backup content** chooses one or more content types and the workspaces they apply to. Each element is the same as its element of [Import / Export / Transfer](administrator-config.md#export-targets), and restoring it works like importing it (replace the items the destination has and add the others, or merge, as described there):

- **Configuration Content:** **Application database** (the shared application configuration, with the Scoring aggregation hierarchy, users, Modules Profiles, Workspace Groups and tickets), **Users & Access** and **Ticket Center**. The last two merge on restore, keeping the other users, settings and tickets.
- **Workspace Content:** **Workspace Database** (the selected workspace SQLite databases), **Input** (raw dataset files) and **Output** (generated reports and PPT Designer jobs), both opt-in; then by module, as Current Workspace Content in Export: Auto-calculated Fields, Main Cities, Mappings & Reference Data, App Events, Designs, PPT Templates, Scoring & GAP Analysis Methodologies, Scoring & GAP Favourite Scorings (without their results), Scoring & GAP Report Templates, Scoring Export Panels, Scoring Excluded Calls, Network Insights Favourites, NQ Call Tracking, NQ Calls Configuration, Report Definitions and AI Assistant Glossary.
- **Selected by default:** Application database, Workspace Database, Designs, PPT Templates, Main Cities, Mappings & Reference Data, Scoring & GAP Analysis Methodologies, Auto-calculated Fields, Scoring Export Panels and Scoring Excluded Calls.
- **Earlier backups:** their methodologies also carry the Favourite Scorings and the report configurations, and restoring them still recovers those, adding the Saved Scorings the workspace does not have yet, each finding its CDRs by the SHA-256 of their files (waiting for those not processed there yet); their **Report Schedules** are restored too.
- **Workspaces:** the group lists only the workspaces you can access; Workspace Content applies to the selected ones and is left out when none is selected.
- **Paths:** Design, template and mapping JSON/CSV files use dedicated paths below `workspaces/<workspace name>/` in Backup and Export ZIPs, independent of the internal workspace folder name.

The menu widens beyond the selector on desktop to show descriptions, wrapping long text (also on mobile). The content, workspaces and folder are saved as they change (**Saved for the next backups**) and used by every next backup, scheduled ones included; **Save scheduler settings** saves only the timing.

#### Back up now

Choose the server-visible **Backup folder** with **Browse**, then **Backup Now**; the line below the selection says what that backup keeps. It first asks for a **Full backup** or a **Light backup** (without the workspace databases, Input and Output, so other content must be selected), with the size of the latest scheduled backup of each kind; **Cancel** makes none. The ZIP is created in the background, in the floating task card, keeping the Admin panel in place.

**Browse** opens a server-side directory picker limited to `APP_DATA_DIR` (directories visible to the host or Docker container, not the browser's computer), which can create a folder before selecting it. The default folder is `APP_DATA_DIR/scheduled-backups`.

#### Restore

1. Choose a server-visible **Backup folder**, the **Backup type** (**Full backups** or **Light backups**) and one of its ZIP files, from the `full` or `light` folder of the backup folder (or the backup folder itself, for backups copied there, which count as full); those made with **Backup Now** say so.
2. The application reads the backup's manifest (with a structural fallback for older ZIPs) to detect its content and workspaces, and shows an overwrite confirmation grouped into **Configuration Content**, **Workspaces** and **Workspace Content**.
3. Choose the parts and workspaces to restore only after reviewing that existing data will be replaced. Workspace Content is restored only in the selected workspaces, which must exist on this server with the same name (others are listed as *not on this server*); the workspaces left out keep their data. The restore runs in the floating task card.

The ZIP selector refreshes after an immediate backup and periodically while Admin is open, so completed scheduled backups appear without a reload.

#### Scheduled backups

- **Frequency:** hourly (at the minute of the **Execution time**), every 4 hours from its hour (01:30 runs at 01:30, 05:30, 09:30…), daily, weekly (with a weekday) or monthly (with a day of the month).
- **Light backups** (hourly, every 4 hours and daily): the backups between full ones leave the workspace databases, Input and Output out, and a full backup is made once a week on the **Full backup day** (its first backup). A full backup missed, because the server was off or had no room, is made at the next backup.
- **Folders:** full backups, scheduled or made with **Backup Now**, go to the `full` folder of the backup folder and light ones to `light`; older backups, all full, are moved from the backup folder of the schedule and the default one into `full` when the application starts (recorded in App Events).
- **Retention:** after each scheduled backup, the scheduler keeps every scheduled backup of the last **Days to keep** days (today included) and, of the full ones, the newest and the newest of each of the last **Weeks to keep** weeks and **Months to keep** months (this week and month included; 7 days, 4 weeks and 6 months by default), and deletes the other scheduled backups, recording them in App Events. Schedules saved before kept a number of backups, now the days those backups covered. Backups made with **Backup Now** are never deleted (remove those no longer needed from the folder); backups made before backups recorded who made them count as scheduled.
- **Planning:** below the settings the panel explains what the keep settings keep (with **Light backups**, the full backups are the weekly ones, named among the days kept), the dates a backup made today keeps, and the most light and full backups kept at once over the next year, with their space from the latest sizes, to size the folder.
- **Room:** before writing anything, a backup checks that the folder has room for the snapshot of its largest database (made there, one database at a time) and for the ZIP, estimated from the latest backup of the same content; on macOS the room counts what the system frees on demand (local Time Machine snapshots, caches), as its storage settings show. Without room it is not started; a scheduled one with **Light backups** on is made light instead. The reason shows below the tiles until a scheduled backup is made as configured, and is recorded in App Events.

Backups stay in the chosen folder of this server: copy them to other storage to keep them away from its disk. They complement infrastructure backups and portable Export packages.

**Cleanup.** Leftovers of interrupted work untouched for six hours (snapshots and partial ZIPs of killed backups, temporary folders of imports, exports, transfers and restores, CDR uploads unfinished after a week, temporary files of the workspace caches) are removed once a night between 00:00 and 07:00, after 15 minutes without users and while no import, export, transfer, backup, restore or CDR processing runs (after two days without a cleanup, at the next idle moment). Each backup also first clears what an interrupted backup left in its folder. App Events records what was removed and the space freed.

### Database Viewer

**Database Viewer** shows the global configuration tables, the active workspace database and the materialised combined CDR tables, grouped by ownership:

- **Config Tables:** global application configuration.
- **Workspace Tables:** templates, datasets, profiles, logs, workspace state, PPT selections, Design selected rows and PPT Designer jobs.
- **Individual Datasets:** one materialised table per dataset.
- **Combined CDR rows:** reporting acceleration tables by CDR type.

The **Table** picker lists the tables of each group by kind (Users & Access, Application, Datasets, PPT Designer & Templates, Scoring & GAP Analysis, Non-Qualified Calls, Reporting, Mappings & Maps, Query Builder, Ticket Center, AI Assistant, Workspace, and the Voice, Data, Speech or other datasets of each individual dataset), each kind in its colour; its search finds a table by title or database name (<kbd>Enter</kbd> opens the first one found, <kbd>Esc</kbd> closes it).

- **Rows:** 100 per page on the server (First/Previous/Next/Last), Excel-style distinct-value filters, active-filter chips, editing and deletion, and orphaned materialisation cleanup. A saved or deleted row applies to the active workspace at once and clears the analysis caches for later Design and Reporting requests: export first when changing production data by hand.
- **Read-only rows:** those of a CDR in its [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs), and of a combined CDR table kept in the copies, show **View only**: CDRs stay as imported and change only by processing or mapping them again.
- **PPT Designer jobs** keep the PowerPoint history, each row with its PPT definition and applied filter snapshot.
- **PPT Templates** is the active workspace's `report_templates` table: each template name, technology, default flag, timestamps and CSV content. CSV templates are migrated automatically when their workspace opens; CSV copies are generated only for portable packages.

#### Operator Mappings and Vendor Mappings tables

**Operator Mappings** (`operator_mappings`) and **Vendor Mappings** (`vendor_mappings`) are workspace tables that explain why different source spellings appear as one Operator or Vendor in charts. Each row maps a `source_value` to its `canonical_value`: one row maps the canonical label to itself, the others map source aliases to it. Lookup is case-insensitive, and one source label cannot belong to two canonical groups of the same type. `source_value` is a primary key and cannot be edited here.

**Chart Mapping Groups** (`chart_mapping_groups`) identifies each group by `mapping_type` and `canonical_value` and holds its `position` and `color`. The position is the chart order (Operator order also drives Subscriber dimensions; Vendor order drives Vendor dimensions and the Vendor part of `Operator_Vendor`); the `#RRGGBB` colour gives a stable chart theme, with related shades for several campaigns or series. Neither aliases nor chart order rewrite source workbooks, CDR rows or combined CDR tables.

> [!WARNING]
> **Change labels in Workspace Config.** A row edit here is a single-row operation and can leave a group's aliases, identity or order inconsistent. Use [Operator Maps](workspace-config.md#operator-maps) or [Vendor Maps](workspace-config.md#vendor-maps) to give each name of the CDRs its label and to add, rename, colour, move or delete labels: renaming a label also updates exact references in Report Templates and saved Designs, and label changes clear chart caches. Both mapping types travel together as **Mappings & Reference Data** in exports, transfers and backups.

## Reset Application

> [!CAUTION]
> **Irreversible.** Resetting deletes every workspace and database and the whole config and data folders. Download an export from [Import / Export / Transfer](administrator-config.md#import-export-transfer) first, or copy a backup out of the data folder: backups stored inside it are deleted too.

**Reset Application**, in the Super Admin header, opens a confirmation listing what is deleted and the config and data folders of the deployment; it runs only after typing `RESET APPLICATION`. The application then:

- stops background work (dataset processing, queued jobs and Query Builder runs);
- deletes every workspace, the application database (users, Modules Profiles, Workspace Groups and settings) and the whole config and data folders, scheduled backups and transfer packages included, keeping the code and the shipped assets;
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

## Tips & shortcuts

These gestures speed up the administration pages. The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

| To… | Do this |
| --- | --- |
| Sort the users | Click the title of a column (but **Password**); click it again to reverse the order |
| Change many users at once | Tick them, or every listed user with the header box, and use the bar that appears |
| Reorder the main tabs in **Interface Settings** | Drag a row by its handle (⠿), also on touch, or use its arrows |
| Open a table in the **Database Viewer** | Type part of its title or database name in the search of the **Table** picker and press <kbd>Enter</kbd> to open the first one found; <kbd>Esc</kbd> closes the picker |
| Import a package (**Admin → Import / Export / Transfer**) | Drop the ZIP or JSON file on the **Import** zone, or click it to choose it |
