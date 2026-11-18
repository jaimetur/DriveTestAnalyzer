# App Logs

App Logs records meaningful application and workspace events for operational review: who triggered each event and from where it ran.

> [!NOTE]
> **Two different scopes.** App Events belongs to the active workspace. Execution Log shows output from the running server process.

> [!IMPORTANT]
> **Server restarts.** Execution Log capture resets when the server restarts; it is not a replacement for persisted workspace events.

## In this guide

| Task or topic | Go to |
| --- | --- |
| See who did what, and when | [App Events](#app-events) |
| Follow the background runs and their errors | [Execution Log](#execution-log) |
| Know which logs I can see | [Access and workspace scope](#access-and-workspace-scope) |

## Access and workspace scope

App Logs is available to every signed-in user. App Events shows the audit entries of the active workspace: open a workspace in Workspace Management to review its events. Without an active workspace the App Events table is unavailable; the live Execution Log still shows the output of the running server process.

## App Events

Each event says who triggered it and where it ran:

- **Triggered by:** the person, or `system`, shown in red as **System** tagged *application*, for the events of the application itself, which no signed-in user performed. People show by first and last name with their username as a badge below (the username alone when the account has no name or no longer exists).
- **Executed by** (never empty), with its tag below:
  - the module whose page a signed-in person used (its title in Interface Settings, tagged *module*);
  - the **Server**, tagged *Scheduler* (scheduled backups and reports generated on their schedule), *Background job* (processing and mapping CDRs, combined tables, Scoring calculations, PPT and chart jobs, package and transfer jobs), *Idle task* (PPT warm-up, NQ indexing, Map Areas fill) or *Startup* (each start of the application, upgrades and the recovery of interrupted work);
  - a **Remote server**, tagged with its name, for the transfers it sends;
  - **Public**, tagged *Sign-in*, *Access request*, *Ticket Center* or *Page*, for the pages used without signing in.
  - Events of earlier versions, which did not record where they ran, take it from their action, or show **Application** tagged *not recorded*.
- **Date:** each event's date, with its time as a green badge below.

### Filters

**Date**, **Triggered by**, **Executed by**, **Type** and **Action** are lists where you tick one or several values.

- **Using a list:** search it, choose **Include** / **Exclude** or **Select All / None** (which stay at its top while its values scroll). The list is as tall as most of the window and as wide as its values need, opening above its button when there is more room there.
- **Include** (default): an event is shown when it matches one of the values ticked in every filter; a filter with nothing ticked shows every event (*All users*, *All dates*…).
- **Exclude:** shows every event except those of the values ticked, crossed out in red, so the events of values that appear later are shown too; its button reads in red, for example *All except login* or *2/9 excluded*. Each filter has its own mode, and switching it keeps the values ticked.
- **Values offered:** each filter offers the values of the events the other filters leave (values it leaves out stay in its list while an event has them), except **Date**, which always lists every date.
- **Last Day:** first in **Date**, above a line: the newest date of the events, whatever day it is, to include or exclude like any value. While it is ticked the button reads *Last Day* and the days are unticked and disabled.
- **Triggered by** lists `system` first (red, **System**, *application*) on a line of its own, then the default users (super, admin and demo) tagged *default user* and, after another line, the other users by first and last name (username when they have none); names of no account show as they are. User matching is case-insensitive.
- **Executed by** lists the **Server** places first, then remote servers, public pages and the modules in their order, with a line between the groups.
- The browser remembers the values ticked and the mode of each filter. An open list stays as it is while the table refreshes; values of new events join it when it closes.
- **Clear Filters** restores the full list (every filter back to **Include**); **Refresh** requests the latest entries.

### The table

- Shows the newest 100,000 events of the workspace, 100 a page with a pager below; every event is kept, and exports and backups include them all.
- The server filters the events; the count beside **Refresh** shows how many there are, or how many match the filters.
- Refreshes automatically every five seconds, fetching the events again only when one was added, imported or deleted.
- **Details** describes each event in one sentence; **Raw details**, folded by default, unfolds the data recorded with it, for troubleshooting.
  - Each save of a user account lists only the fields it changed, from the previous value to the new one (names, role, active, Modules Profile, Workspace Groups and workspaces, and whether the password changed, never its value), for example `User EUSER01: role user-viewer → user-editor; activated; Workspace Groups +UK.`, or says it was saved with no changes. Creating or deleting a user records the account as it was.
  - The changes of several users at once, Modules Profiles, Workspace Groups, Interface Settings, the application configuration, email delivery, scheduled backups and the backup selection, and Operator and Vendor Maps also say what changed; other events name the action and the values recorded. Events of earlier versions, which kept only what was saved, show those values and say they did not record which fields changed.
  - Scoring calculations and exports name their Saved Scoring as `saved scoring ID 57 (favourite)` when it is one of the Favourite Scorings (marked with the star), and as `unsaved scoring ID 57` otherwise, since only the Favourite Scorings are kept.

### What is recorded

- **Application starts** (`application_started`, by `system` in every workspace: first in the active workspace it opens and, once the application is ready, in the others, except one being duplicated or never opened yet): the version, the active workspace, how long it took to be ready, the address it listens on, the Python version, the platform and the process ID, and, as an Error, why the active workspace could not be opened.
- **Sign-in and out:** a failed sign-in is recorded with the `system` user and the login typed in its details.
- **Workspaces:** opening, closing, creating, renaming, duplicating and deleting them (a deleted workspace is recorded in the workspace open at that moment), clearing their cache and changing their access.
- **Datasets:** uploading (or cancelling an upload), processing, mapping and deleting them and downloading their CSV previews.
- **Analyses:** Datasets Analysis and Network Insights analyses, Query Builder runs and their cancellation, and Scoring & GAP Analysis calculations (`scoring_calculation_requested`; a failed one writes `scoring_calculation_failed` with its error and where it happened).
- **Non-Qualified Calls:** every action of [the module](non-qualified-calls.md#app-events-of-the-module) (the module opened, the calls listed and opened, each value a call changed from what to what, the changes of several calls, comments with their text, what each configuration change changed, the maps opened, previews, imports and exports).
- **Reports:** generating, downloading, stopping and deleting reports, their runs and PPTs.
- **Configuration changes.**
- **Exports:** of data, chart data, PPT Templates, Designs, Scoring results and reports (also the charts and tables of Scoring & GAP Analysis, Network Insights, Non-Qualified Calls, Chart Builder and PPT Designer downloaded as images or copied as screenshots), methodologies and report configurations.
- **Ticket Center:** opening, editing, comments, screenshots and files added, deleted and cleaned up, attention, type changes and deletion.
- **Packages:** imports (each uploaded package with its file and kind, and each refused file with the reason), backups, export packages and transfers to and from other servers with their outcome.
- **Requests to stop background tasks.**
- **Not recorded:** outside Non-Qualified Calls, opening pages, previews, filter selections and status refreshes.

Background events keep their requester in **Triggered by** and show the **Server** in **Executed by**. Events that earlier versions recorded under the name of a process instead of `system` (`import`, for the table columns taken from an imported Non-Qualified Calls configuration) belong to `system` when the workspace opens, with that process in their details, and a `migrate_app_event_users` event records how many changed; App Events imported or restored from older packages come in the same way.

**App Events** also travel on their own, as App Events in [Import / Export / Transfer](administrator-config.md#export-targets) and in the Workspace Content of [Backup Protection](super-admin.md#backup-protection): importing or restoring them adds the events a workspace does not have, which take their place among the others by date and time.

## Execution Log

The Execution Log shows the live output of the current server process, in the application timezone, to help diagnose runtime and background-task failures. It holds only what was captured since the process began; a restart starts a new capture.

It opens on its latest lines and follows the new ones. Scrolling up stops it so you can read; **Go to the end**, in its bottom corner while you are away from the end, or scrolling back down follows the latest lines again.

For workspace settings, see [Workspace Config](workspace-config.md). For runtime settings, see [Application Config](app-config.md).
