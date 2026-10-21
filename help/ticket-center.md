# Ticket Center

Use **Ticket Center** to report the bugs you find in the tool, suggest improvements and ask for new features, with their screenshots, and to follow each ticket until it is resolved. Every ticket has a type, **Bug**, **Improvement** or **New Feature**, and keeps the version of the tool it was opened with and its date.

> [!NOTE]
> **Module access.** Ticket Center is in every Modules Profile, and it is the only main module that opens without a workspace: tickets belong to the tool, not to a workspace. Super-admins choose who sees it in **Super Admin → Modules Profiles** and can rename it in **Super Admin → Interface Settings**. Every role, `user-viewer` included, can open tickets and comment on them.

> [!TIP]
> **Share a ticket by its link.** The list (`/tickets`) and each ticket (`/tickets/<number>`), with its screenshots, open without signing in, read-only, so a link can be sent to anyone who reaches the server. Opening, commenting and editing ask to sign in, and signing in from there returns to the ticket. The addresses of Bugs Report, as the module was called before (`/bugs-report`, `/bugs-report/<number>`), lead to the same pages.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Read the dashboard | [Open section](#dashboard) |
| Open a ticket | [Open section](#new-ticket) |
| Find and follow tickets | [Open section](#tickets) |
| The page of a ticket | [Open section](#the-page-of-a-ticket) |
| Types, priorities and statuses | [Open section](#types-priorities-and-statuses) |
| Who can do what | [Open section](#who-can-do-what) |
| Portability | [Open section](#portability) |

## Dashboard

The top of the page sums up every ticket; each count, bar and cell lists its tickets in **Tickets** below (clearing the other filters) and tells what it is when the mouse is over it.

- **Tiles**: the **Open** tickets (New, In Progress and Waiting for Info), each of those three statuses, those **Resolved** or closed in the last 30 days and, signed in, **My open** tickets. A tile pressed again lists the open tickets.
- **Tickets by type and status**: a row per type and a column per status, with the totals of each row and column; click a count to list those tickets.
- **Created vs resolved**: the tickets opened and those resolved or closed in each period chosen at its top right, the current one last: **Daily** (the last 30 days), **Weekly** (the last 12 weeks from Monday, by default), **Monthly** (the last 12 months), **Quarterly** (the last 8 quarters) or **Yearly** (the last 5 years). The browser remembers the period chosen. Below the chart, the **age of the oldest open ticket**, with a link to it.
- **A card per type**: its open tickets out of all of them, a bar with its tickets by status, and its open tickets by priority (P1 to P5).
- **Open tickets per module**: the open tickets of each module, the module with most first.

## New Ticket

**New Ticket**, at the top of the page or in the menu of the tab, opens the form of a new ticket:

- **Type** (required): **Bug** (something does not work as it should), **Improvement** (something that works could work better) or **New Feature** (something the tool cannot do yet). The description shows the guide of the chosen type.
- **Title**: what it is about, in a few words (required).
- **Module**: the main module it is about, or **General**.
- **Priority**: from **P1 · Critical** to **P5 · Trivial** (**P3 · Medium** by default).
- **Description**: for a bug, what you did, what happened and what you expected (the steps to reproduce it help a lot); for an improvement, how it works today and how it could work better; for a new feature, what you need and how the tool could do it. It reads as written below.
- **Screenshots**: paste them with Ctrl+V (⌘V on a Mac) anywhere in the form, drop them on the zone or click it to choose them. Up to 10 PNG, JPEG, GIF or WebP images of 10 MB each; each one shows a preview that can be removed before sending.

**Open Ticket** saves it with the version of the tool and the date, and opens its page. The browser it was opened from is kept too, to help reproduce a bug.

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

## Tickets

The **Tickets** table lists every ticket, the latest activity first: its number, type, title, module, reporter, date and version, priority, status (with the version that fixed it), who attends it, its last update and how many comments and screenshots it has. Click a row to open its page.

Below the search, the chips filter the list by **Type**, **Status**, **Priority**, **Module** and **Assignee** (**Unassigned** or a super-admin); press several chips of a group to list any of them, and none to list every value of it. The list starts with the open statuses (New, In Progress and Waiting for Info). Search by title, reporter or number (`#12`), choose a reporter (by name, the default users first) or **Only mine**, and order by latest activity, priority, newest or oldest; **Reset filters** lists the open tickets again. Each browser remembers the filters and the order.

## The page of a ticket

The page shows the title with its type, status, priority and module, who opened it, when and with which version, and the version that fixed it; **Back to Tickets**, above it, returns to the list.

- **Description** shows the text and the screenshots of the ticket; click a screenshot to see it full size (**Open original** opens the image itself). The reporter and the super-admins add more screenshots below it.
- **Timeline** lists, oldest first, the comments and every change: who changed the type, status, priority, module, assignment, fixed version, title or description, from what to what and when.
- **Add a comment** writes a comment with optional screenshots, pasted, dropped or chosen as in the New Ticket form. The author of a comment edits it (it shows *edited*) and deletes it; super-admins delete any comment.
- **Details** sums up the type, status, priority, module, reporter, who attends it, the versions it was opened and fixed with, and its dates.
- **Edit** (reporter and super-admins) changes the title and the description (and the module, for the reporter), and the **Priority** of **Details** changes as soon as another one is chosen.
- **Manage** (super-admins) changes the type, status, who attends the ticket, who reported it, its module, the version it was opened with and the version that fixed it, whoever opened it; **Save** records each change in the timeline.

## Types, priorities and statuses

| Type | Meaning |
| --- | --- |
| **Bug** (red) | Something does not work as it should |
| **Improvement** (teal) | Something that works could work better |
| **New Feature** (magenta) | Something the tool cannot do yet |

The tickets opened before the types existed are bugs.

| Priority | Meaning |
| --- | --- |
| **P1 · Critical** | Blocks the work or loses data; it must be attended first |
| **P2 · High** | A main feature does not work, or is missing, and there is no simple way around it |
| **P3 · Medium** | Something does not work as expected, or could be better, but there is a way around it |
| **P4 · Low** | A minor problem or improvement |
| **P5 · Trivial** | Cosmetic details, texts or suggestions |

| Status | Meaning |
| --- | --- |
| **New** | Opened and not attended yet |
| **In Progress** | A super-admin is working on it |
| **Waiting for Info** | The super-admin needs more information: answer with a comment |
| **Resolved** | Fixed or done; **Fixed in** shows the version |
| **Closed** | Finished without further work |
| **Rejected** | Not a bug, a duplicate or not going to be done (the timeline or a comment says why) |

New, In Progress and Waiting for Info are the open statuses. The date a ticket is resolved, closed or rejected is kept, and reopening it clears that date.

## Who can do what

| Action | Who |
| --- | --- |
| Read the tickets, their timeline and screenshots | Anyone with the link, without signing in |
| Open tickets and comment on them | Every signed-in user with the module |
| Edit a ticket (title, module, description), change its priority and add screenshots to it | Its reporter and the super-admins |
| Edit or delete a comment | Its author (super-admins also delete any comment) |
| Manage a ticket: **Attend this ticket**, its type, its status, who attends it (a super-admin), who reported it, its module, the version it was opened with and the version that fixes it, whoever opened it | Super-admins |
| Delete a ticket with its timeline and screenshots | Super-admins |

**Attend this ticket** sets a new ticket **In Progress** and assigns it to the super-admin who presses it. Moving a ticket to In Progress or Waiting for Info assigns it to that super-admin when nobody attends it, and resolving it without a fixed version records the version running then.

After signing in, and as soon as they arrive while signed in, each super-admin is told of the tickets still **New** that other users opened and it has not opened, with their type, in the dialog that also lists the [access requests](super-admin.md#access-requests) waiting for activation; **Open Ticket Center** lists the New tickets. Each ticket is told once to each super-admin.

Every action (opening, editing, comments, screenshots, attention, type changes and deletion) is recorded in the [App Events](app-logs.md#app-events), as *Ticket created*, *Ticket managed* and so on.

## Portability

The tickets live in the application database, so **Application Config** exports, transfers, backups and restores include them with every workspace. **Ticket Center** in [Import / Export / Transfer](administrator-config.md#import-export-transfer) and in [Backup Protection](super-admin.md#backup-protection) also moves them on their own (super-admins only): one JSON document with every ticket, its type and its timeline, and each screenshot as a file. Importing or restoring it merges the tickets into the server: the tickets, comments and screenshots it does not have are added, a ticket or comment changed later in the package takes its newer content, and nothing is deleted. The tables are **Tickets**, **Ticket Comments** and **Ticket Attachments** in the Database Viewer, where the screenshots show as their size and cannot be edited.
