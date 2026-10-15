# Bugs Report

Use **Bugs Report** to report the bugs you find in the tool, with their screenshots, and to follow each one until it is fixed. Every bug report keeps the version of the tool it was opened with and its date.

> [!NOTE]
> **Module access.** **Bugs Report** is in every Modules Profile, and it is the only main module that opens without a workspace: bug reports belong to the tool, not to a workspace. Admins and super-admins choose who sees it in **Admin → Modules Profiles**. Every role, `user-viewer` included, can report bugs and comment on them.

> [!TIP]
> **Share a bug report by its link.** The list (`/bugs-report`) and each bug report (`/bugs-report/<number>`), with its screenshots, open without signing in, read-only, so a link can be sent to anyone who reaches the server. Reporting, commenting and editing ask to sign in, and signing in from there returns to the bug report.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Report a bug | [Open section](#new-bug-report) |
| Find and follow bug reports | [Open section](#bug-reports) |
| The page of a bug report | [Open section](#the-page-of-a-bug-report) |
| Priorities and statuses | [Open section](#priorities-and-statuses) |
| Who can do what | [Open section](#who-can-do-what) |
| Portability | [Open section](#portability) |

## New Bug Report

**New Bug Report**, at the top of the page or in the menu of the tab, opens the form of a new report:

- **Title**: what is wrong, in a few words (required).
- **Module**: where the bug happens, one of the main modules or **General**.
- **Priority**: from **P1 · Critical** to **P5 · Trivial** (**P3 · Medium** by default).
- **Description**: what you did, what happened and what you expected; the steps to reproduce it help a lot. It reads as written below.
- **Screenshots**: paste them with Ctrl+V (⌘V on a Mac) anywhere in the form, drop them on the zone or click it to choose them. Up to 10 PNG, JPEG, GIF or WebP images of 10 MB each; each one shows a preview that can be removed before sending.

**Open Bug Report** saves it with the version of the tool and the date, and opens its page. The browser it was reported from is kept too, to help reproduce it.

### Writing descriptions and comments

Descriptions and comments are saved as written and read with their structure (the empty field shows a grey guide):

- A line starting with `-`, `*` or `·` is a bullet; indent it (with spaces or a tab) to nest it under the bullet above it, as many levels as needed. An indented line without a marker goes on in the bullet above it.
- A line ending with a colon, such as `Problem:`, is a title in blue; a bullet ending with one is shown in blue too.
- A line of dashes (`----- Notes -----`) is a divider with its text.
- Every other line is a paragraph, and an empty line separates paragraphs and lists.

```text
Problem:
- The export never ends
  - Only with 3 campaigns
Expected:
- The PowerPoint downloads
```

## Bug Reports

The header counts the reports **New**, **In Progress**, **Waiting for Info** and **Resolved**, and **My open reports**; click a count to list those reports (the other filters are cleared), and click it again to list the open ones. The **Bug Reports** table lists every report, the latest activity first: its number, title, module, reporter, date and version, priority, status (with the version that fixed it), who attends it, its last update and how many comments and screenshots it has. Click a row to open its page.

Search by title, reporter or number (`#12`), and filter by status (the open ones by default: New, In Progress and Waiting for Info), priority, module, reporter (by name, the default users first) or **Only mine**; order by latest activity, priority, newest or oldest. Each browser remembers the filters and the order.

## The page of a bug report

The page shows the title with its status, priority and module, who opened it, when and with which version, and the version that fixed it; **Back to Bug Reports**, above it, returns to the list.

- **Description** shows the text and the screenshots of the report; click a screenshot to see it full size (**Open original** opens the image itself). The reporter and the super-admins add more screenshots below it.
- **Timeline** lists, oldest first, the comments and every change: who changed the status, priority, module, assignment, fixed version, title or description, from what to what and when.
- **Add a comment** writes a comment with optional screenshots, pasted, dropped or chosen as in the new report form. The author of a comment edits it (it shows *edited*) and deletes it; super-admins delete any comment.
- **Details** sums up the status, priority, module, reporter, who attends it, the versions it was opened and fixed with, and its dates.
- **Edit** (reporter and super-admins) changes the title and the description (and the module, for the reporter), and the **Priority** of **Details** changes as soon as another one is chosen.
- **Manage** (super-admins) changes the status, who attends the report, who reported it, its module, the version it was opened with and the version that fixed it, whoever opened it; **Save** records each change in the timeline.

## Priorities and statuses

| Priority | Meaning |
| --- | --- |
| **P1 · Critical** | Blocks the work or loses data; it must be fixed first |
| **P2 · High** | A main feature does not work and there is no simple way around it |
| **P3 · Medium** | Something does not work as expected but there is a way around it |
| **P4 · Low** | A minor problem |
| **P5 · Trivial** | Cosmetic details, texts or suggestions |

| Status | Meaning |
| --- | --- |
| **New** | Reported and not attended yet |
| **In Progress** | A super-admin is working on it |
| **Waiting for Info** | The super-admin needs more information: answer with a comment |
| **Resolved** | Fixed; **Fixed in** shows the version |
| **Closed** | Finished without further work |
| **Rejected** | Not a bug, a duplicate or not going to be fixed (the timeline or a comment says why) |

New, In Progress and Waiting for Info are the open statuses. The date a report is resolved, closed or rejected is kept, and reopening it clears that date.

## Who can do what

| Action | Who |
| --- | --- |
| Read the bug reports, their timeline and screenshots | Anyone with the link, without signing in |
| Report bugs and comment on them | Every signed-in user with the module |
| Edit a report (title, module, description), change its priority and add screenshots to it | Its reporter and the super-admins |
| Edit or delete a comment | Its author (super-admins also delete any comment) |
| Manage a report: **Attend this bug**, its status, who attends it (a super-admin), who reported it, its module, the version it was opened with and the version that fixes it, whoever opened it | Super-admins |
| Delete a report with its timeline and screenshots | Super-admins |

**Attend this bug** sets a new report **In Progress** and assigns it to the super-admin who presses it. Moving a report to In Progress or Waiting for Info assigns it to that super-admin when nobody attends it, and resolving it without a fixed version records the version running then.

After signing in, each super-admin is told of the bug reports still **New** that other users reported and it has not opened, in the dialog that also lists the [access requests](administrator-config.md#access-requests) waiting for activation; **Open Bugs Report** lists the New reports. Each report is told once to each super-admin.

Every action (opening, editing, comments, screenshots, attention and deletion) is recorded in the [App Events](app-logs.md#app-events).

## Portability

The bug reports live in the application database, so **Application Config** exports, transfers, backups and restores include them with every workspace. **Bugs Report** in [Import / Export / Transfer](administrator-config.md#import-export-transfer) and in [Backup Protection](administrator-config.md#backup-protection) also moves them on their own (super-admins only): one JSON document with every report and its timeline, and each screenshot as a file. Importing or restoring it merges the reports into the server: the reports, comments and screenshots it does not have are added, a report or comment changed later in the package takes its newer content, and nothing is deleted. The tables are **Bug Reports**, **Bug Report Comments** and **Bug Report Attachments** in the Database Viewer, where the screenshots show as their size and cannot be edited.
