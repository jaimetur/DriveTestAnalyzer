# Ticket Center

Use **Ticket Center** to report the bugs you find in the tool, suggest improvements and ask for new features, with their screenshots, and to follow each ticket until it is resolved. Every ticket has a type, **Bug**, **Improvement** or **New Feature**, and keeps the version of the tool it was opened with and its date.

> [!NOTE]
> **Module access.** Ticket Center is in every Modules Profile, and it is the only main module that opens without a workspace: tickets belong to the tool, not to a workspace. Super-admins choose who sees it in **Super Admin → Modules Profiles** and can rename it in **Super Admin → Interface Settings**. Every role, `user-viewer` included, can open tickets and comment on them.

> [!TIP]
> **Share a ticket by its link.** The list (`/tickets`) and each ticket (`/tickets/<number>`), with its screenshots, open without signing in, read-only, so a link can be sent to anyone who reaches the server. Opening, commenting and editing ask to sign in, and signing in from there returns to the ticket. The addresses of Bugs Report, as the module was called before (`/bugs-report`, `/bugs-report/<number>`), lead to the same pages.

## Presentation

The presentation **Ticket Center** sums the module up. Report bugs, suggest improvements and ask for new features with screenshots, and follow each ticket until it is resolved. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
ticket-center
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Presentation | [Open section](#presentation) |
| Read the dashboard | [Open section](#dashboard) |
| Statistics | [Open section](#statistics) |
| Open a ticket | [Open section](#new-ticket) |
| Find and follow tickets | [Open section](#all-tickets) |
| The page of a ticket | [Open section](#the-page-of-a-ticket) |
| Types, priorities and statuses | [Open section](#types-priorities-and-statuses) |
| Who can do what | [Open section](#who-can-do-what) |
| Portability | [Open section](#portability) |

## Dashboard

The header of the module sums up every ticket with its tiles, and its tabs choose the view shown below the floating bar of its sections: **New Ticket**, **All Tickets**, the list of tickets, **Dashboard** (by default; New Ticket while there is no ticket) or **Statistics**. Each browser remembers the tab chosen. The sections menu of the tab of Ticket Center and the floating bar list the same views in the same order, and a link to the tickets of a status (such as those of the notices of new tickets) opens All Tickets.

Each tile, and each count, bar and cell of the **Dashboard** panel, lists its tickets in **All Tickets** (opening that tab and clearing the other filters) and tells what it is when the mouse is over it.

- **Tiles** (in the header): the **Open** tickets (New, In Progress and Waiting for Info), each of those three statuses, those **Resolved** or closed in the last 30 days and, signed in, **My open** tickets. A tile pressed again lists the open tickets.
- **Created vs resolved**: the tickets opened and those resolved or closed in each period chosen at its top right, the current one last: **Daily** (the last 30 days), **Weekly** (the last 12 weeks from Monday, by default), **Monthly** (the last 12 months), **Quarterly** (the last 8 quarters) or **Yearly** (the last 5 years). The browser remembers the period chosen.
- **At a glance**: a ring of every ticket, open, resolved or closed, and rejected, with the open ones in its centre (**All clear** when none is open); a part of the ring or its line lists those tickets. Below it, the tickets opened and resolved this week (from Monday), the **age of the oldest open ticket**, with a link to it, and the open tickets nobody attends.
- **Needs attention**: up to 5 open tickets, the most urgent priority first and then the oldest, with their status, module, assignee and age (green under a week, amber under a month, red after it), and a link to the others; with no open ticket, **All caught up**. Below, the tickets **resolved last**, with the version that fixed them, the time they took and when.
- **Latest activity**: the 8 newest entries of every ticket (tickets opened, comments and changes, a change of status with the new one), who made them and how long ago.
- **Tickets by type and status**: a row per type and a column per status, with the totals of each row and column; click a count to list those tickets.
- **Tickets per module**: every ticket of each module, its open ones in the colour of the module, those with most open tickets first; a module lists all its tickets.
- **A card per type**: its open tickets out of all of them, a bar with its tickets by status, the median time its tickets took to be resolved and, while it has open tickets, those by priority (P1 to P5).

## Statistics

The **Statistics** tab shows how the tickets are going, with every bar coloured by type (Bug, Improvement, New Feature) and what each part is when the mouse is over it:

- **Resolution rate**: the share of every ticket resolved or closed, as a ring. **Time to resolve · 30 days**: the median time from opened to resolved of the tickets resolved in the last 30 days, and how much faster or slower it is than in the 30 days before. **Opened · 30 days**: the tickets opened in the last 30 days and how many more or fewer than in the 30 days before. **Comments per ticket**, with the screenshots per ticket.
- **Every ticket**: three donuts of every ticket by type, status and priority, with the count and share of each; a part, or its line in the legend, lists its tickets.
- **Time to resolve**: the tickets resolved or closed by the time they took (under a day, 1–3 days, 3–7 days, 1–2 weeks, 2–4 weeks, 1–3 months, more), with their median, average and the time 9 in 10 of them took, and the median of each type and priority. **Open** shows instead the age of the open tickets by the same groups.
- **Backlog over time**: the tickets created, resolved (or closed) and open by the end of each period, with the same choice as **Created vs resolved** (Daily to Yearly, which changes both charts). A ticket is open from the day it was opened to the day it was resolved, closed or rejected.
- **Tickets fixed in each version**: the tickets resolved or closed in each of the latest 10 versions of the tool, as the Changelog lists them (also those without tickets), by their **Fixed in version**; **Opened with** shows those opened with each version.
- **Tickets per module**: every ticket of each module, the module with most first; a row lists its tickets.
- **Tickets per reporter**: the tickets each user opened; **Assignees** shows those of each assignee, open, resolved or closed, and rejected, and how many open tickets nobody attends. A row lists the tickets of that reporter or assignee.
- **Activity**: a calendar of the last 26 weeks, a column per week from Monday, darker the more tickets were opened, commented and changed that day, with the totals and the busiest day.

Each browser remembers the view chosen in each card.

## New Ticket

**New Ticket**, the first tab (also the button of the header, the floating bar and the menu of the tab), shows the form of a new ticket; without signing in it shows dimmed, with a note and a **Sign in** button, and cannot be filled:

- **Type** (required): **Bug** (something does not work as it should), **Improvement** (something that works could work better) or **New Feature** (something the tool cannot do yet). The description shows the guide of the chosen type.
- **Title**: what it is about, in a few words (required).
- **Module**: the main module it is about, or **General**.
- **Priority**: from **P1 · Critical** to **P5 · Trivial** (**P3 · Medium** by default).
- **Description**: for a bug, what you did, what happened and what you expected (the steps to reproduce it help a lot); for an improvement, how it works today and how it could work better; for a new feature, what you need and how the tool could do it. It reads as written below.
- **Screenshots**: paste them with Ctrl+V (⌘V on a Mac) anywhere in the form, drop them on the zone or click it to choose them. Up to 10 PNG, JPEG, GIF or WebP images of 10 MB each; each one shows a preview that can be removed before sending.

**Open Ticket** saves it with the version of the tool and the date, and opens its page. The browser it was opened from is kept too, to help reproduce a bug.

### Writing descriptions and comments

Descriptions and comments are written in Markdown and read the same while they are written: the editor shows every line as the page shows it (an empty one shows the guide of the type of the ticket in grey). Use the toolbar above the text or its keys (⌘ instead of Ctrl on a Mac), or type the Markdown, which takes its format as you write it:

| Write | It reads as |
|---|---|
| `# Heading`, `## Heading`, `### Heading` (up to six `#`) | A heading, larger with fewer `#` (**Ctrl+Alt+1**, **2** and **3**) |
| A short line ending with a colon (`Problem:`), or followed by a list (`Steps to reproduce`) | A title in blue; a bullet ending with a colon is in blue too |
| `- item` (also `*`, `+`, `·` or `•`) | A bullet (**Ctrl+Shift+8**) |
| `1. item`, `1) item`, `a) item`, `A) item` or `1.1. item` | A numbered item (**Ctrl+Shift+7**), numbered from the first number of its list; a `1.1.` item takes the numbers of the items above it |
| `- [ ] task` or `- [x] done` | A task (**Ctrl+Shift+9**); a click on its box ticks it |
| A text between two asterisks, one asterisk, two tildes, two equal signs or backticks | Bold (**Ctrl+B**), italic (**Ctrl+I**), strikethrough (**Ctrl+Shift+X**), highlight (**Ctrl+Shift+H**) and code (**Ctrl+E**) |
| `[text](https://…)` or a web address | A link (**Ctrl+K**); in the editor, Ctrl and a click open it |
| `#` and the number of a ticket (`#7`) | A link to that ticket, which shows its title and status when pointed at; a number of no ticket, one inside a word, a web address or code, or one with a backslash before its `#` stays text. In the editor a number typed links once the text is saved |
| `> [!TIP] Title` and its lines starting with `>` | A card with its title (or the name of its kind): **NOTE**, **INFO**, **TIP**, **SUCCESS**, **QUESTION**, **IMPORTANT**, **WARNING**, **CAUTION** or **ERROR** |
| `> text` | A quote |
| A line of three backticks, the code, and another line of three backticks | A code block, as written |
| `---` or `----- Notes -----` | A divider, with its text |
| Any other line | Text; an indented line under a bullet goes on in it |

In the editor, **Enter** goes on with a list at the level of the item above (a bullet, a number or a task), and on an empty item goes up a level and then out of the list (or out of a card); **Shift+Enter** goes on in the same item; **Tab** and **Shift+Tab** nest an item under the one above it or bring it back; **Backspace** at the start of an item takes it up a level and then makes it text. Pasted text is read as Markdown, copied text keeps its Markdown, and **Ctrl+Z** and **Ctrl+Shift+Z** undo and redo. **Edit the Markdown** shows the text as it is saved, to change it as such, and **How to write it** sums up this table. **Ctrl+Enter** posts a comment or saves the description.

```text
Steps to reproduce
1. Open Scoring & GAP Analysis
2. Export to PowerPoint
   a) With 3 campaigns
Expected:
- The PowerPoint downloads

> [!WARNING]
> It only fails with **NSA** campaigns
```

## All Tickets

The **All Tickets** tab shows the table of every ticket, the latest activity first: its number, type, title, module, reporter, date and version, priority, status (with the version that fixed it), who attends it, its last update and how many comments and screenshots it has. Click a row to open its page.

Below the search, the chips filter the list by **Type**, **Status**, **Priority**, **Module** and **Assignee** (**Unassigned** or a super-admin); press several chips of a group to list any of them, and none to list every value of it: **All**, the first chip of each group, is pressed then, and a click on it unpresses the others. The list starts with the open statuses (New, In Progress and Waiting for Info); **All** of Status lists every ticket. Search by title, reporter or number (`#12`), choose a reporter (by name, the default users first) or **Only mine**, the days the tickets were **Created** and last **Updated** (several days at once, the newest first, after **Last Day**: the newest day of creation or of update of the tickets, whatever day it is; while it is chosen, the days are unticked and disabled), and order by latest activity, priority, newest or oldest.

Every column of the table also filters the tickets as in Excel: the **▾** of its header lists its values (the title of **Ticket**, the priority, the status with the version that fixed it, the comments and screenshots of **Activity**…) with a search, **Select all** and **Clear**, and **Apply** shows only the tickets with a value checked (while searching, only the values found); **Updated** lists its days by year and month. Filtered columns are highlighted, and every filter adds up with the others. **Reset filters** lists the open tickets again, clearing every other filter and the column filters. Each browser remembers the filters and the order.

## The page of a ticket

The page shows the title with its type, status, priority and module, who opened it, when and with which version, and the version that fixed it; **Back to Tickets**, above it, returns to the list.

The buttons at the end of that row open the **First**, **Previous**, **Next** and **Last** ticket, around the position of the ticket (*3 of 12*). They follow the Tickets list as the browser showed it last, with its filters and its order (*Tickets list*); a ticket that is not in that list, for example one opened from a link or left out by the filters, goes through every ticket by number (*By number*), and so do the tickets it leads to. Where the ticket cannot move (before the first one, after the last one) the buttons are disabled, and pointing at a button shows the number and title of the ticket it opens.

- **Description** shows the text and the screenshots of the ticket; click a screenshot to see it full size (**Open original** opens the image itself). The reporter and the super-admins add more screenshots below it.
- **Timeline** lists, oldest first, the comments and every change: who changed the type, status, priority, module, assignment, fixed version, title or description, from what to what and when.
- **Add a comment** writes a comment with optional screenshots, pasted, dropped or chosen as in the New Ticket form. The author of a comment edits it (it shows *edited*) and deletes it; super-admins delete any comment.
- **Details** sums up the type, status, priority, module, reporter, who attends it, the versions it was opened and fixed with, and its dates.
- **Edit** (reporter and super-admins) changes the title and the description (and the module, for the reporter), and the **Priority** of **Details** changes as soon as another one is chosen.
- **Manage** (super-admins) changes the type, status, who attends the ticket, who reported it, its module, the version it was opened with and the version that fixed it, whoever opened it; **Save** records each change in the timeline.
- **Opened on** and **Resolved on**, at the end of Manage, correct the dates the ticket was opened and resolved (also closed or rejected; Resolved on only for those), for example for a ticket recorded after the work it describes. Its timeline follows them: the change that set its current status and the comment just before it (its resolution) take the Resolved date, the entries before them that fall before the Opened date or after the Resolved date take the Opened date, and the others (those between both, and those written after the resolution) keep theirs, every entry in its order. **Updated** becomes the latest of those dates. The timeline does not record the change of dates; App Events does (`ticket_managed`).

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
| Manage a ticket: **Attend this ticket**, its type, its status, who attends it (a super-admin), who reported it, its module, the version it was opened with the version that fixes it and the dates it was opened and resolved, whoever opened it | Super-admins |
| Delete a ticket with its timeline and screenshots | Super-admins |

**Attend this ticket** sets a new ticket **In Progress** and assigns it to the super-admin who presses it. Moving a ticket to In Progress or Waiting for Info assigns it to that super-admin when nobody attends it, and resolving it without a fixed version records the version running then.

After signing in, and as soon as they arrive while signed in, each super-admin is told of the tickets still **New** that other users opened and it has not opened, with their type, in the dialog that also lists the [access requests](super-admin.md#access-requests) waiting for activation; **Open Ticket Center** lists the New tickets. Each ticket is told once to each super-admin.

Every action (opening, editing, comments, screenshots, attention, type changes and deletion) is recorded in the [App Events](app-logs.md#app-events), as *Ticket created*, *Ticket managed* and so on.

## Portability

The tickets live in the application database, so **Application Config** exports, transfers, backups and restores include them with every workspace. **Ticket Center** in [Import / Export / Transfer](administrator-config.md#import-export-transfer) and in [Backup Protection](super-admin.md#backup-protection) also moves them on their own (super-admins only): one JSON document with every ticket, its type and its timeline, and each screenshot as a file. Importing or restoring it merges the tickets into the server: the tickets, comments and screenshots it does not have are added, a ticket or comment changed later in the package takes its newer content, and nothing is deleted. The tables are **Tickets**, **Ticket Comments** and **Ticket Attachments** in the Database Viewer, where the screenshots show as their size and cannot be edited.
