# Ticket Center

Use **Ticket Center** to report the bugs you find in the tool, suggest improvements and ask for new features, with their screenshots and files, and to follow each ticket until it is resolved. Every ticket has a type, **Bug**, **Improvement** or **New Feature**, and keeps the version of the tool it was opened with and its date.

> [!NOTE]
> **Module access.** Ticket Center is in every Modules Profile, and it is the only main module that opens without a workspace: tickets belong to the tool, not to a workspace. Super-admins choose who sees it in **Super Admin → Modules Profiles** and can rename it in **Super Admin → Interface Settings**. Every role, `user-viewer` included, can open tickets and comment on them.

> [!TIP]
> **Share a ticket by its link.** The list (`/tickets`) and each ticket (`/tickets/<number>`), with its screenshots and files, open without signing in, read-only, so a link can be sent to anyone who reaches the server. Opening, commenting and editing ask to sign in, and signing in from there returns to the ticket. The addresses of Bugs Report, as the module was called before (`/bugs-report`, `/bugs-report/<number>`), lead to the same pages.

## Presentation & Guide

```presentations
ticket-center
guide:ticket-center.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| See the state of all the tickets at a glance | [Dashboard](#dashboard) |
| Read the statistics of the tickets | [Statistics](#statistics) |
| See the time spent on the tickets | [Time Spent](#time-spent) |
| Report a bug or ask for an improvement | [New Ticket](#new-ticket) |
| <span class="guide-sub">↳ Format descriptions and comments</span> | <span class="guide-sub">↳ [Writing descriptions and comments](#writing-descriptions-and-comments)</span> |
| Find and follow the tickets | [All Tickets](#all-tickets) |
| Read, comment and change a ticket | [The page of a ticket](#the-page-of-a-ticket) |
| Know the types, priorities and statuses | [Types, priorities and statuses](#types-priorities-and-statuses) |
| Know who can change a ticket | [Who can do what](#who-can-do-what) |
| Get the updates by email | [Email updates](#email-updates) |
| Free the space of old attachments | [Clean up attachments](#clean-up-attachments) |
| Export, import and transfer the tickets | [Portability](#portability) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Dashboard

The header of the module sums up every ticket with its tiles, and its tabs choose the view shown below the floating bar of its sections: **New Ticket**, **All Tickets** (the list), **Dashboard** (by default; New Ticket while there is no ticket), **Statistics** or **Time Spent**. Each browser remembers the tab chosen. The sections menu of the tab and the floating bar list the same views in the same order, and a link to the tickets of a status (such as those of the notices of new tickets) opens All Tickets.

**Period.** Dashboard, Statistics and Time Spent share one **Period**, chosen at the top of each: **All time** (by default), **This week** (from Monday), **This month**, **This quarter** or **This year**; the browser remembers it. They count the tickets opened in the period, and those resolved or closed in it for the times to resolve, the tickets resolved last and the versions that fixed them. **All time** covers every ticket since the first, drawn over time by months when it spans 8 months or more, else by weeks (by days under 4 weeks). Each tile, count, bar, cell or chart part that lists tickets opens them in **All Tickets** (clearing its other filters), all those of its value of any period, and tells what it is when the mouse is over it.

- **Tiles** (in the header): the **Open** tickets (New, In Progress and Waiting for Info), each of those three statuses, those **Resolved** or closed in the last 30 days and, signed in, **My open** tickets. A tile pressed again lists the open tickets.
- **Created vs resolved:** the tickets opened and those resolved or closed in each day (this week and this month), week (this quarter) or month (this year) of the period, up to today, with the count over each bar; weekends are shaded. With more than 24 periods (the days of this month), each has a single bar: the resolved tickets, narrow and solid, inside the created ones, wide and light, with both counts over it (created first) and the day under it.
- **At a glance:** a ring of the tickets opened in the period, open, resolved or closed, and rejected, with the open ones in its centre (**All clear** when none is open); a part of the ring or its line lists them. Below it, the tickets opened and those resolved or closed in the period, the **age of the oldest open ticket** with a link to it, and the open tickets nobody attends.
- **Tickets by type and status:** a row per type and a column per status, with totals; click a count to list those tickets.
- **Tickets per module:** each module's tickets, its open ones in its colour, those with most open tickets first.
- **A card per type:** its open tickets out of all, a bar with its tickets by status, the median time its tickets resolved or closed in the period took and, while it has open tickets, those by priority (P1 to P5).
- **Needs attention:** up to 5 open tickets opened in the period, the most urgent priority and then the oldest first, with status, module, assignee and age (green under a week, amber under a month, red after), and a link to the others; with none, **All caught up**. Below, the tickets **resolved last** in the period, with the version that fixed them, the time they took and when.
- **Latest activity:** the newest entries of the period (tickets opened, comments and changes, a change of status with the new one), who made them and how long ago, as many as fit beside Needs attention.

## Statistics

The **Statistics** tab shows how the tickets of the [period](#dashboard) are going, every bar coloured by type (Bug, Improvement, New Feature), with what each part is when the mouse is over it. Comparisons are with the period before (last week, last month…); All time has none. Each browser remembers the view chosen in each card.

- **Resolution rate:** the share of the tickets opened in the period already resolved or closed, as a ring. **Time to resolve:** the median time from opened to resolved of the tickets resolved in the period, against the period before. **Tickets opened:** how many, against the period before. **Comments per ticket**, with the attachments (screenshots and files) per ticket.
- **Every ticket:** three donuts of the tickets opened in the period by type, status and priority, with the count and share of each.
- **Time to resolve:** the tickets resolved or closed by the time they took (under a day, 1–3 days, 3–7 days, 1–2 weeks, 2–4 weeks, 1–3 months, more), with their median, average and the time 9 in 10 of them took, and the median of each type and priority. **Open** shows instead the age of the open tickets by the same groups.
- **Backlog:** the tickets created, resolved (or closed) and open by the end of each day, week or month of the period, up to today. A ticket is open from the day it was opened to the day it was resolved, closed or rejected.
- **Tickets fixed in each version:** the tickets resolved or closed in each of the latest 10 versions, as the Changelog lists them (also those without tickets), by their **Fixed in version**; **Opened with** shows those opened with each version.
- **Tickets per module:** the module with most first.
- **Tickets per reporter:** the tickets each user opened; **Assignees** shows those of each assignee, open, resolved or closed, and rejected, and how many open tickets nobody attends.
- **Activity:** how many tickets were opened, commented and changed each day, darker the busier, weekends underlined, with the totals and the busiest day below. This week and this month: a calendar of their days, a row per week from Monday, each day with its number. This quarter, this year and all time: a small calendar of each month in its own box (three or six in a row), the days still to come faint; all time from the first activity, the last 53 weeks at most (over 12 months, a heat map with a column per week from Monday).

## Time Spent

The **Time Spent** tab adds up the time from opened to resolved or closed of the tickets resolved or closed in the [period](#dashboard). A note at its top says how it is measured:

- The time of a ticket is the **calendar time** from opened to resolved or closed, 24 hours a day (nights and weekends included): the tool does not record working hours.
- Only the tickets resolved or closed in the period count; open and rejected ones are left out. Totals add up their time; the average and the median are per ticket.
- Times are written in hours and minutes (`316h`, `7h 12m`, `42m`), never in days, as everywhere in Ticket Center.

It shows:

- **Figures:** the time spent in all, the tickets resolved or closed, the average and median per ticket, and the longest one, with a link to it.
- **Where the time goes:** the time those tickets spent **New**, **In Progress** and **Waiting for Info** until resolved, by the changes of status of their timelines (a ticket starts New), with its share and average per ticket.
- **Time spent per day** (this week and this month), **per week** (this quarter) or **per month** (this year; all time as Statistics draws it): the time of the tickets resolved in each. Per day, weekends have a shaded column, a slate axis and slate bars.
- **By module**, **By type** and **By priority**, then **By assignee**, **By reporter** and **By version that fixed them**, three in a row: the time of each in all, with its tickets and average per ticket under its name, the most time first (types and priorities in their order, versions the latest first); a row lists its tickets.

## New Ticket

**New Ticket**, the first tab (also the button of the header, the floating bar and the menu of the tab), shows the form of a new ticket; without signing in it shows dimmed, with a note and a **Sign in** button, and cannot be filled:

- **Type** (required): **Bug** (red: something does not work as it should), **Improvement** (teal: something that works could work better) or **New Feature** (magenta: something the tool cannot do yet). The description shows the guide of the chosen type. Tickets opened before the types existed are bugs.
- **Title** (required): what it is about, in a few words.
- **Module:** the main module it is about, or **General**.
- **Priority:** **P1 · Critical** to **P5 · Trivial** (**P3 · Medium** by default; see [Types, priorities and statuses](#types-priorities-and-statuses)).
- **Description:** for a bug, what you did, what happened and what you expected (the steps to reproduce it help a lot); for an improvement, how it works today and how it could work better; for a new feature, what you need and how the tool could do it.
- **Screenshots and files:** paste them with Ctrl+V (⌘V on a Mac) anywhere in the form, drop them on the zone or click it to choose them; up to 10 of 100 MB each at once, each with a preview that can be removed before sending. PNG, JPEG, GIF and WebP images are screenshots and show as their image; any other file (a log, a CDR sample, an Excel, PowerPoint, Word or PDF file, a ZIP…) shows its type, name and size. Programs and scripts (`.exe`, `.bat`, `.cmd`, `.ps1`, `.sh`, `.jar`, `.js`, `.msi`…) are not taken: zip them to attach them.

**Open Ticket** saves it with the version of the tool, the date and the browser it was opened from (to help reproduce a bug), and opens its page.

### Writing descriptions and comments

Descriptions and comments are written in Markdown and read the same while they are written: the editor shows every line as the page shows it (an empty one shows the guide of the type of the ticket in grey). Use the toolbar above the text, its keys (see [Tips & shortcuts](#tips-shortcuts)) or type the Markdown, which takes its format as you write:

| Write | It reads as |
|---|---|
| `# Heading`, `## Heading`, `### Heading` (up to six `#`) | A heading, larger with fewer `#` |
| A short line ending with a colon (`Problem:`), or followed by a list (`Steps to reproduce`) | A title in blue; a bullet ending with a colon is in blue too |
| `- item` (also `*`, `+`, `·` or `•`) | A bullet |
| `1. item`, `1) item`, `a) item`, `A) item` or `1.1. item` | A numbered item, numbered from the first number of its list; a `1.1.` item takes the numbers of the items above it |
| `- [ ] task` or `- [x] done` | A task; a click on its box ticks it |
| A text between two asterisks, one asterisk, two tildes, two equal signs or backticks | Bold, italic, strikethrough, highlight and code |
| `[text](https://…)` or a web address | A link; in the editor, Ctrl and a click open it |
| `#` and the number of a ticket (`#7`) | A link to that ticket, which shows its title and status when pointed at; a number of no ticket, one inside a word, a web address or code, or one with a backslash before its `#` stays text. In the editor a number typed links once the text is saved |
| `> [!TIP] Title` and its lines starting with `>` | A card with its title (or the name of its kind): **NOTE**, **INFO**, **TIP**, **SUCCESS**, **QUESTION**, **IMPORTANT**, **WARNING**, **CAUTION** or **ERROR** |
| `> text` | A quote |
| A line of three backticks, the code, and another line of three backticks | A code block, as written |
| `---` or `----- Notes -----` | A divider, with its text |
| Any other line | Text; an indented line under a bullet goes on in it |

In the editor:

- **Enter** goes on with a list at the level of the item above (a bullet, a number or a task), and on an empty item goes up a level and then out of the list (or out of a card); **Shift+Enter** goes on in the same item.
- **Tab** and **Shift+Tab** nest an item under the one above or bring it back; **Backspace** at the start of an item takes it up a level and then makes it text.
- Pasted or dropped text is read as Markdown, and copied text keeps its Markdown.
- **Edit the Markdown** shows the text as it is saved, to change it as such, and **How to write it** sums up this table.

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

The **All Tickets** tab shows the table of every ticket, the latest activity first: number, type, title, module, reporter, date and version, priority, status (with the version that fixed it), who attends it, its last update and how many comments and attachments it has. Click a row to open its page.

- **Chips** below the search filter by **Type**, **Status**, **Priority**, **Module** and **Assignee** (**Unassigned** or a super-admin): press several chips of a group to list any of them, none for every value. **All**, the first chip of each group, is pressed then, and a click on it unpresses the others. The list starts with the open statuses; **All** of Status lists every ticket.
- **Search** by title, reporter or number (`#12`); choose a reporter (by name, the default users first) or **Only mine**; the days the tickets were **Created** and last **Updated** (several days at once, the newest first, after **Last Day**: the newest day of creation or update, whatever day it is; while it is chosen the days are unticked and disabled); and order by latest activity, priority, newest or oldest.
- **Column filters:** every column filters as in Excel: its **▾** lists its values (the title of **Ticket**, the priority, the status with the version that fixed it, the comments and attachments of **Activity**…; **Updated** its days by year and month) with a search, **Select all** and **Clear**, and **Apply** shows only the tickets with a value checked (while searching, only the values found). Filtered columns are highlighted, and every filter adds up with the others.
- **Reset filters** lists the open tickets again, clearing every other filter and the column filters. Each browser remembers the filters and the order.

## The page of a ticket

The page shows the title with its type, status, priority and module, who opened it, when and with which version, and the version that fixed it; **Back to Tickets**, above it, returns to the list.

The buttons at the end of that row open the **First**, **Previous**, **Next** and **Last** ticket, around its position (*3 of 12*). They follow the Tickets list as the browser showed it last, with its filters and order (*Tickets list*); a ticket not in that list (opened from a link, or left out by the filters) goes through every ticket by number (*By number*), and so do the tickets it leads to. Where it cannot move the buttons are disabled, and pointing at one shows the number and title of the ticket it opens.

- **Description:** the text and attachments of the ticket: its screenshots, which open full size when clicked (**Open original** opens the image itself), and below them its files, with type, name and size, which download when clicked (never opening in the page). The reporter and super-admins add more below it.
- **Timeline:** oldest first, the comments and every change: who changed the type, status, priority, module, assignment, fixed version, title or description, from what to what and when.
- **Add a comment:** a comment with optional screenshots and files, added as in the New Ticket form. An edited comment shows *edited*.
- **Details:** the type, status, priority, module, reporter, who attends it, the versions it was opened and fixed with, and its dates. Its **Priority** changes as soon as another one is chosen.
- **Edit:** the title and description (and the module, for the reporter).
- **Manage:** the type, status, who attends it, who reported it, its module, the version it was opened with and the version that fixed it; **Save** records each change in the timeline.
- **Opened on** and **Resolved on**, at the end of Manage, correct the dates the ticket was opened and resolved (also closed or rejected; Resolved on only for those), for example for a ticket recorded after the work it describes. The change that set its current status and the comment just before it (its resolution) take the Resolved date; earlier entries that fall before the Opened date or after the Resolved date take the Opened date; the others (between both, and those written after the resolution) keep theirs, every entry in its order. **Updated** becomes the latest of those dates. The timeline does not record the change of dates; App Events does (`ticket_managed`).

## Types, priorities and statuses

The three types are described in [New Ticket](#new-ticket).

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
| Read the tickets, their timeline, screenshots and files | Anyone with the link, without signing in |
| Open tickets and comment on them | Every signed-in user with the module |
| Edit a ticket (title, module, description), change its priority and add screenshots and files to it | Its reporter and the super-admins |
| Edit or delete a comment | Its author (super-admins also delete any comment) |
| Delete an attachment | Who added it and the super-admins |
| Manage a ticket: **Attend this ticket**, its type, its status, who attends it (a super-admin), who reported it, its module, the version it was opened with and the version that fixes it, and the dates it was opened and resolved, whoever opened it | Super-admins |
| Delete a ticket with its timeline and attachments | Super-admins |
| Clean up the large attachments of finished tickets | Super-admins |

**Attend this ticket** sets a new ticket **In Progress** and assigns it to the super-admin who presses it. Moving a ticket to In Progress or Waiting for Info assigns it to that super-admin when nobody attends it, and resolving it without a fixed version records the version running then.

Super-admins are told of the new tickets of other users in the notices dialog of [Access Requests](super-admin.md#access-requests), once each; **Open Ticket Center** lists the New tickets.

Every action (opening, editing, comments, attachments added, deleted and cleaned up, attention, type changes and deletion) is recorded in the [App Events](app-logs.md#app-events), as *Ticket created*, *Ticket managed* and so on.

## Email updates

When [Email Delivery](app-config.md#email-delivery) is set up with **Ticket Center** checked, emails go to the address of each account (see [Users](super-admin.md#users); each user changes it with **Email address** in the user badge menu):

- **The reporter** gets the confirmation that the ticket was opened, with its description; every change made to it, also its own: a comment (with its text), an edited or deleted comment, attachments added or deleted, an edit of the title, module, description or priority, a change of status, type, assignee or versions (each field before and after), and its deletion; and the same changes in any other ticket that mentions its ticket as `#<number>` in the description or a comment, and a new ticket that mentions it (the email says which of its tickets it mentions).
- **Whoever commented** a ticket gets the emails of its changes from then on, as its reporter does.
- **The users of Email Every Ticket To** get those of every ticket, new ones included.
- **Everyone** also gets their own comments and changes, so the email tells what was done with its user even when someone else worked with it.

How they look:

- **One conversation:** every email of a ticket has the same subject, `DT Analyzer - Ticket #<number>: <title>`; through an SMTP server they all go in one conversation of the mail clients (Outlook, Gmail and the others), through a Power Automate flow Outlook shows each as a conversation of its own.
- **Grouped changes:** the changes of a ticket made less than a minute apart reach each recipient in one email (sent at most 10 minutes after the first change), showing each change in turn.
- **Title:** what happened, large and in its colour, before the number and title of the ticket: **New Ticket**, **New Comment**, **Ticket Updated**, **Comment Edited**, **Comment Deleted**, **New Attachments**, **Attachment Deleted**, the new status (**In Progress**, **Waiting for Info**, **Resolved**, **Closed**, **Rejected**, **Back to New**, or **Reopened** when a done or rejected ticket opens again) or **Ticket Deleted**.
- **Contents:** who made the change, the status, priority, type and reporter of the ticket, and a link to its page. The description and comments read as on the page of the ticket, with their formats (headings, titles, bullets and numbers, tasks, quotes and cards, code, links), and their `#<number>` link to the tickets they mention.
- **In the background:** the emails never slow a page down; App Events records each one (see [Email Delivery](app-config.md#email-delivery)).

## Clean up attachments

Screenshots and files take space in the application database and in every backup that carries it. Super-admins give it back with **Clean up attachments**, beside **New Ticket** in the header:

- **Larger than** (10 MB by default) and **Of the tickets** (**Resolved** and **Closed** by default, and **Rejected**) choose the attachments; the list follows as soon as they change, and the browser remembers them.
- The list shows the largest first: the ticket (its number opens it in another tab) with its status, the attachment (in the description or a comment, and who added it), its size and the day it was added; above it, how many there are and how much they take, with every attachment of the tickets and the size of the application database.
- Every attachment listed is checked: uncheck those to keep. **Delete** (with the number and size of those checked) asks for confirmation and deletes them; the tickets keep their description, timeline, dates and other attachments, and an attachment of a ticket opened again meanwhile stays.
- The application database is then compacted to give their space back to the disk, and the message tells its size before and after (a database busy at that moment keeps its size, and new data reuses the space).

App Events records each cleanup as *Ticket attachments cleaned up*, with the size and statuses chosen and every attachment deleted.

## Portability

The tickets live in the application database, so **Application Config** exports, transfers, backups and restores include them with every workspace. **Ticket Center** in [Import / Export / Transfer](administrator-config.md#import-export-transfer) and in [Backup Protection](super-admin.md#backup-protection) also moves them on their own (super-admins only): one JSON document with every ticket, its type and its timeline, and each attachment (screenshot or file) as a file. Importing or restoring it merges the tickets into the server: the tickets, comments and attachments it does not have are added, a ticket or comment changed later in the package takes its newer content, and nothing is deleted. The tables are **Tickets**, **Ticket Comments** and **Ticket Attachments** in the Database Viewer, where the attachments show as their size and cannot be edited.

## Tips & shortcuts

These keys and gestures speed up writing tickets and comments. On a Mac use <kbd>⌘</kbd> where a key says <kbd>Ctrl</kbd> (except <kbd>Ctrl</kbd>+<kbd>Y</kbd>). The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts).

**Moving around**

| To… | Do this |
| --- | --- |
| Change view (New Ticket, All Tickets, Dashboard, Statistics, Time Spent) | Click its tab, or focus a tab and press <kbd>←</kbd> / <kbd>→</kbd> |
| List the tickets behind a tile, count, bar or cell | Click it |

**Attachments**

| To… | Do this |
| --- | --- |
| Attach a screenshot | Paste it with <kbd>Ctrl</kbd>+<kbd>V</kbd> anywhere in the form, not only in the text |
| Attach files | Drop them on the zone, or click it to choose them |

**Formatting the text** (see [Writing descriptions and comments](#writing-descriptions-and-comments))

| To… | Do this |
| --- | --- |
| Bold, italic, code | <kbd>Ctrl</kbd>+<kbd>B</kbd>, <kbd>Ctrl</kbd>+<kbd>I</kbd>, <kbd>Ctrl</kbd>+<kbd>E</kbd> |
| Strikethrough, highlight | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>H</kbd> |
| Add a link | <kbd>Ctrl</kbd>+<kbd>K</kbd> |
| Numbered list, bullets, tasks | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>7</kbd>, <kbd>8</kbd>, <kbd>9</kbd> |
| Heading of level 1, 2 or 3 | <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>1</kbd>, <kbd>2</kbd>, <kbd>3</kbd> |
| Turn a heading back into text | <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>0</kbd> |
| Undo, redo | <kbd>Ctrl</kbd>+<kbd>Z</kbd>; <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> or <kbd>Ctrl</kbd>+<kbd>Y</kbd> |
| Nest an item, or bring it back | <kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd> |
| Go on in the same item | <kbd>Shift</kbd>+<kbd>Enter</kbd> |
| Open a link while writing | <kbd>Ctrl</kbd>+click it (a plain click places the caret in it) |
| Tick a task | Click its box |
| Post the comment or save the description | <kbd>Ctrl</kbd>+<kbd>Enter</kbd> |
| Bring formatted text from elsewhere | Paste or drop it: it is read as Markdown |
