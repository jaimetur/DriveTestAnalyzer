# App Logs

App Logs records meaningful application and workspace events for operational review. It distinguishes the person associated with a workflow (**User**) from the account or process that performed each step (**Executed by**); automatic steps use `system`.

> [!NOTE]
> **Two different scopes.** App Events belongs to the active workspace. Execution Log shows output from the running server process.

> [!IMPORTANT]
> **Server restarts.** Execution Log capture resets when the server restarts; it is not a replacement for persisted workspace events.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Access and workspace scope | [Open section](#access-and-workspace-scope) |
| App Events | [Open section](#app-events) |
| Execution Log | [Open section](#execution-log) |

## Access and workspace scope

App Logs is available to authenticated users with the existing application roles. App Events show the active workspace's audit entries. Open a workspace in Workspace Management to review its events. When no workspace is active, the App Events table is unavailable; the live Execution Log still shows output from the running server process.

## App Events

Use the filters to narrow entries by **Date**, **User**, **Executed by**, **Type** and **Action**. The **User** and **Executed by** filters list the users by their first and last name (their username when they have none), the default users (super, admin and demo) first and tagged *default user*, with a line before the others; `system` and other names of no account show as they are. User matching is case-insensitive and the table shows the usernames in lowercase. Select **Clear Filters** to restore the full list, or **Refresh** to request the latest entries. The table refreshes automatically every five seconds.

Events record every action of the users and the work that runs for them: signing in and out; opening, closing, creating, renaming, duplicating and deleting workspaces (a deleted workspace is recorded in the workspace open at that moment), clearing their cache and changing their access; uploading (or cancelling an upload), processing, mapping and deleting datasets and downloading their CSV previews; Datasets Analysis and Network Insights analyses, Query Builder runs and their cancellation, and Scoring & GAP Analysis calculations (`scoring_calculation_requested`); the follow-up of the NQ Analysis Center (changes to one call or to several, comments and their edits and deletions, imports and exports); generating, downloading, stopping and deleting reports, Reporting Job runs and Dashboard PPTs; configuration changes; exports of data, chart data, PPT Templates, Dashboards, Scoring results and reports, methodologies and report configurations; bug reports (opening, editing, comments, screenshots, attention and deletion); imports (each uploaded package with its file and kind, and each refused file with the reason), backups, export packages and transfers to and from other servers with their outcome; and requests to stop background tasks. Opening pages, previews, filter selections and status refreshes are not recorded. A Scoring & GAP Analysis calculation that fails writes a `scoring_calculation_failed` event with its error and where it happened. Background events retain the requester and `system` executor separately.

**App Events** also travel on their own, as App Events in [Import / Export / Transfer](administrator-config.md#export-targets) and in the Workspace Content of [Backup Protection](administrator-config.md#backup-protection): importing or restoring them adds to a workspace the events it does not have, and App Events lists every event by its date and time, so imported events take their place among the others.

## Execution Log

The Execution Log displays live output captured from the current server process and uses the configured application timezone. It can help diagnose runtime and background-task failures. It contains only output captured since the process began; restarting starts a new capture.

For workspace settings, see [Workspace Config](workspace-config.md). For runtime settings, see [Application Config](app-config.md).
