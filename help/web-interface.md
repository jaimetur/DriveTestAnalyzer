# Web Interfaces

The UI uses a shared header, module tabs, panels, dialogs and tables. Read [Product Overview](overview.md) for the purpose of each module.

> [!NOTE]
> **Role-sensitive navigation.** Sections and actions depend on your role and workspace access. A hidden administrative module does not indicate missing data.

> [!TIP]
> **Long-running work.** Floating task cards follow server-side work while you navigate. Minimizing a card does not stop its task.

## In this guide

| Task or topic | Go to |
| --- | --- |
| Navigation | [Open section](#navigation) |
| Header controls | [Open section](#header-controls) |
| Panels | [Open section](#panels) |
| Searchable selectors | [Open section](#searchable-selectors) |
| Operator patterns (`VF*`, `NOT Lebara`) | [Open section](#operator-patterns) |
| Filter Builder | [Open section](#filter-builder) |
| Tables | [Open section](#tables) |
| Dialogs and progress | [Open section](#dialogs-and-progress) |
| Floating background-task cards | [Open section](#floating-background-task-cards) |
| Unassigned values card | [Open section](#unassigned-values-card) |
| Images of charts and tables | [Open section](#images-of-charts-and-tables) |
| Laptop screens | [Open section](#laptop-screens) |
| Small screens | [Open section](#small-screens) |
| PPT navigation and overlays | [Open section](#ppt-navigation-and-overlays) |

## Navigation

The dark application bar at the top, in a darker shade of the colour of the module open (dark blue and teal outside the modules), holds the name of the tool with its version, the active workspace and the user (with a dot of the colour of its role) with **Logout**. Under it, one white panel holds the tabs: the administrative tabs, as buttons, on its upper row, and under a line the primary module tabs, as folder tabs with a line of the colour of their module on top and their icon in that colour, the open one filled with that colour; on a narrower window the main tabs take their short names and wrap to a second row when they do not fit. On small screens a bar at the bottom of the screen takes the place of both rows (see [Small screens](#small-screens)).

Primary tabs, in their default order (super-admins change their order, titles, icons and colours in **Super Admin → Interface Settings**):

- **Workspace**
- CDR Analysis
- PPT Designer
- Scoring & GAP Analysis
- Network Insights
- Non-Qualified Calls (in development)
- **Reporting**
- **Builders** (dropdown with Chart Builder and Query Builder)
- AI Assistant
- Ticket Center (opens without a workspace)

Each main tab is a module. An account sees the modules of its Modules Profile (**Super Admin → Modules Profiles**), and a super-admin every module until it is given one; a module an account does not see disappears from its tabs and Modules menu, and its pages and API answer 403. When the tabs do not fit on one line they wrap onto further lines, and main module tabs never share a line with the administrative tabs.

Other tabs:

- Help
- App Logs
- Config (dropdown with Application Config and Workspace Config, each with the list of its sections on hover), for `user-editor`, `admin` and `super-admin` roles
- Admin, for `admin` and `super-admin` roles
- Super Admin, for the `super-admin` role

The browser tab of each page shows `DT Analyzer - ` and its module, so several open tabs can be told apart: the main modules by their Short title of **Super Admin → Interface Settings** (for example `DT Analyzer - Scoring` or `DT Analyzer - Tickets`; CDR Analysis, PPT Designer, Network Insights and AI Assistant by their Module Title), and Chart Builder, Query Builder, Workspace Config, Application Config, Readme and Changelog by their own name. The Product Presentations chapter shows `DT Analyzer - Presentations`, and the link of a presentation its title.

Help Home opens by default after login. The login page also offers **Request Access** to new users (see [Super Admin › Access Requests](super-admin.md#access-requests)) and, when [Email Delivery](app-config.md#email-delivery) is set up, **Forgot your password?** (see [Forgotten passwords](super-admin.md#forgotten-passwords)). The menu of the user badge, at the top right, has **Change password** and **Email address**, the address the emails of the tool go to (empty: none). Help, the Readme, the Changelog and the tickets of Ticket Center are also available without signing in, with a prominent **Sign in** button at the top right that returns to the page after signing in. Every module except Workspace and Ticket Center requires an open workspace. After five wrong passwords in a row for a username, its next tries wait (30 seconds, then longer, up to five minutes), also for the password an access request asks an existing account for; a right password, or half an hour, starts over.

Hovering a tab, or focusing it with the keyboard, opens below it the list of its sections, each with an icon and in the colour of the module: the panels of each main module (for example Scoring Calculation, Scoring & GAP Results and Favourites Filters in Scoring & GAP Analysis, where Scoring & GAP Results lists beside it Summary, Scoring Charts, Scoring Tables, Geographical Areas, Scoring Trends, GAP Analysis and Points Lost to open that results tab; on small screens these lists appear below their page, indented), App Events and Execution Log in App Logs, the panels of Admin and Super Admin, the chapters of the Readme and the latest releases of the Changelog. Help lists Help Home and, beside each group, the chapters of General, Main Modules, Administrative Modules and Reference (with the Readme and the Changelog), and ends with **About**, the credits of the application: its logo, name, version, release date and author. Choosing one opens that page with that section at its top (the Scoring & GAP Results entries bring the results tabs there), unfolding it when it was folded, and keeps it there while the page fills its panels, until you scroll — in Non-Qualified Calls until every panel is drawn, however long a large workspace takes (a reload then returns to where the page was being read, with its results tab); clicking the tab itself still opens the module, at its top when it is the page being shown. **Builders** and **Config** open their menu on hover too, and so does the **User** badge, with **Change password**, **Email address** and, while an LLM writer of the generated comments takes each user's key, **API keys** (your own keys for the LLM writers that Super Admin sets to each user's key, see [AI Comment Writers](super-admin.md#ai-comment-writers)).

The tabs stay at the top of the window while you scroll, so you can change module from anywhere in a page (unless they would take more than a third of the window); on small screens the menu bar stays there instead.

Every page with two or more sections also shows them in a floating **sections bar**, in the colour of its module, below the introduction of the page: it stays at the top of the window, below the tabs, while you scroll (on small screens, just above the bar of the modules at the bottom of the screen, see [Small screens](#small-screens)) and holds every entry of the list of its tab (or of its Config or Builders page). Its first entry, an arrow, goes back to the top of the page; choosing a section opens it at the top of the page, as from the list, and the bar marks the section being read as you scroll (the arrow while no section has reached the bar). An entry with parts of its own (Scoring & GAP Results with Summary, Scoring Charts, Scoring Tables, Geographical Areas, Scoring Trends, GAP Analysis and Points Lost, or Mappings & Reference Data with Operator Maps, Vendor Maps, Campaign Maps, Map Areas, Spectrum Holdings and Serving Networks in Workspace Config) shows an arrow and opens them below it (above it when the bar is at the bottom of the screen) on hover, on focus or with a click on the arrow. When the bar does not fit, its labels get smaller and then lose their icons, and on a narrow window it scrolls sideways. Non-Qualified Calls has its own bar, with the number of calls and the NQ Analysis Configuration beside it.

A round button at the bottom left, in the colour of the current module, appears once a page is scrolled down and takes it back to the top.

Open **Builders** to choose **Chart Builder** or **Query Builder**, each with the list of its sections on hover. The **Modules & Sections** drawer lists each builder with its sections. Within its Administrative Modules group, App Logs is first, then Administrator Config and Super Admin. The top tab for Administrator Config remains **Admin**.

Move the pointer near the edge of the window to reveal the collapsed Modules & Sections tab (on a touch screen, touch that edge): the left edge on large screens (1200 px wide and more), the right edge on smaller ones. An invisible hover area beside the tab responds even while background tasks are running; task cards leave that edge clear. The tab recedes when the pointer leaves, and keyboard focus also reveals it.

**Modules & Sections**, the tab at the left edge of large screens (at the right edge below 1200 px wide), opens the whole tree of the modules: Main Modules, Administrative Modules and Documentation, each module with its sections and their parts (as the lists of the tabs; Help with its chapters in their groups and, in a chapter, the headings of the document being read). The module of the page is open and marked; the other modules open with their arrow, and choosing a module or a section goes there and closes the drawer. It uses nearly the full height of the window, scrolls if the window is too short for every entry and, open, stands above every floating card.

Open **Config** and choose **Application Config** for application-wide runtime settings or **Workspace Config** for Operator Mappings, Vendor Mappings, Spectrum Holdings, Serving Networks, Main Cities and the Scoring hierarchy/KPI/GAP settings in the active workspace. The **Modules & Sections** tab at the edge of the window jumps between the panels of Workspace Config. Hovering **Application Config** or **Workspace Config** in the menu opens the list of their sections (Application Runtime and Email Delivery; Main Cities, Mappings & Reference Data with its Operator, Vendor and Campaign Maps, Map Areas and Spectrum Holdings, and Scoring & GAP Analysis Setup): choosing one opens that page at that section, unfolding it when it was folded.

Help Navigation lists unnumbered documents under General, Main Modules, Administrative Modules and Reference. Main Modules follow the order of the main tabs, by default: [Workspace Management](workspace-management.md), CDR Analysis, PPT Designer, Scoring & GAP Analysis, Network Insights, Non-Qualified Calls, [Reporting](reporting.md), Chart Builder, Query Builder, AI Assistant and Ticket Center. Docker Deployment follows Deployment Configuration in General. App Logs is the first administrative document and Super Admin the last, after Administrator Config. Readme and Changelog open Reference before Project Structure and Roadmap.

The Help Home link stays above the groups. Every chapter is available to every reader.

The Changelog adds a **Releases** list that jumps to each release; it highlights the release being read, as Help Navigation highlights the open document. Both lists grow down to the end of the document and only scroll beyond it.

## Header controls

- Click the active-workspace badge to switch workspace.
- The workspace-size badge is recalculated after dataset and report operations.
- The username badge shows the role and the Modules Profile of the account (Full Access for a super-admin without one), in the colour of the role for admins and super-admins and in that of the profile for the other users; hover or focus it for its menu (**Change password**, **Email address** and **API keys**, see [Navigation](#navigation)).
- Use Logout to end the session.

## Panels

- A panel heading explains its purpose.
- Collapsible panels remember their open/closed state where supported.
- Status pills distinguish ready, processing, failed and stopped work.
- Destructive actions use red styling and request confirmation when appropriate.

## Searchable selectors

Single-select and multi-select controls share a compact searchable style.

- Type in the search field to narrow values.
- Multi-select controls preserve the order in which values are selected when order has meaning.
- **Select all / none** toggles the currently available options.
- Open menus are layered above their active dialog and positioned against their field.

### Operator patterns

Every **Operator** filter (Scoring & GAP Analysis, CDR Analysis, PPT Designer, Network Insights, Non-Qualified Calls, the common filters of the reports of [Reporting](reporting.md) and the scenarios of the Scoring report editor and its saved configurations) takes patterns besides the operators listed: type one in the filter of the list and press Enter (or **＋ Add pattern**, which tells how many operators it takes now). A pattern is saved as such, travels with what keeps it (Saved Filters, favourites, reports, Designs, exports, transfers and backups) and is resolved each time the filter is used, so it also takes the operators that appear later:

- `*` stands for any characters, whatever the case: `VF*` takes VF, VF SA, VF VoNR, VF SM… and `*O2*` every operator with O2 in its name;
- `-` or `NOT` (followed by a space) before a value leaves it out: `-Lebara` or `NOT Lebara` is every operator but Lebara, `NOT Leb*` every operator but those that start with Leb, and several exclusions leave out each one;
- values and exclusions together take the values but the excluded ones: `VF*` with `-VF SM` is every VF variant but VF SM.

Patterns come first in their list, tagged **pattern** or **except**, and an operator of the Operator Maps is taken or left out with the spellings of the CDRs it stands for. A pattern added while every operator is ticked chooses on its own (the operators are unticked), and the list shows what it takes: `-Three` alone shows **All except Three**. An operator that every filter must leave out needs no pattern: give it the **Exclude** role in [Operator Maps](workspace-config.md#operator-maps).

## Filter Builder

The shared Filter Builder is used by Chart Builder and Report Template Chart Preview.

- The field selector is searchable.
- Operators adapt to list, text and numeric conditions.
- Add or remove conditions without editing raw syntax.
- The parsed filter appears beneath the builder.
- `IN`/`NOT IN` lists may be typed without parentheses; the parser adds them.

## Tables

- Wide desktop tables use fixed action areas where needed.
- Database and filtered-dataset tables paginate on the server.
- Excel-style header menus search distinct values from the complete filtered source.
- Horizontal/vertical scrolling stays inside the table viewport when controls must remain visible.

## Dialogs and progress

Long operations use progress dialogs for stages such as:

- preparing an export;
- transmitting or receiving a server transfer;
- processing an import;
- loading a Chart Data Preview;
- loading a filtered dataset.

Server-transfer dialogs can be hidden with **Hide** while the transfer continues as a background task, and are restored after a browser reload while the transfer remains active. On the destination, once the package has arrived, a dialog without **Hide** keeps every open page out of use until the import ends; on the source, the dialog comes back once when that import starts and can be hidden again.

After signing in and while signed in, a super-admin is told in the same style as an incoming server transfer of the [access requests](super-admin.md#access-requests) waiting for activation and of the new [tickets](ticket-center.md#who-can-do-what) it has not been told of, once each, on any page: the poll of incoming transfers checks for them every few seconds (every 30 seconds in a hidden tab), and an open dialog takes in what arrives meanwhile. The dialog waits for any other dialog or running operation of the page to close first, and a dialog that opens while it is shown goes over it.

## Floating background-task cards

Every authenticated page polls active background work (every 2 seconds while work runs, every 8 seconds otherwise and every 30 seconds in a hidden tab) and shows compact floating cards until it finishes. Work for the open workspace appears at the lower right. Work for one or more other accessible workspaces appears in differently coloured lower-left cards, grouped by workspace name; changing the active workspace moves each running task to the appropriate side.

Each card preserves its expanded or minimized state when moving between modules or reloading the page.

Each card shows the task, its current stage and progress when the job reports one. The red circular **Stop Job** control is available only for interruptible work in a workspace the user can access and asks for confirmation before requesting a stop.

Browser dataset uploads retain their latest measured percentage between progress events and can be interrupted while their request is active; dataset jobs already accepted by the server then appear separately and can be stopped at their safe checkpoints. Auto-calculated Field and combined-CDR work use the same cooperative stop behaviour.

A stopped duplication removes its partial workspace; stopped exports remove temporary output; imports cannot be stopped after importing has begun.

## Unassigned values card

While the ready CDRs of the open workspace have Operators, Vendors or Campaigns that no Operator, Vendor or Campaign Map assigns, a red card at the bottom centre of every page lists them until they are assigned. With task cards on screen it takes the middle of their row, between those of other workspaces and of the open workspace and as wide as them, and stands above the system task cards when there are any; on a phone the row takes the whole width of the screen and the button back to the top rises above it. Editors open the assignment table from its buttons; the user-viewer role is asked to inform an administrator. On a [laptop screen](#laptop-screens) it starts minimized to its title line, and **+** opens it. See [Unassigned values warning](workspace-config.md#unassigned-values-warning).

## Images of charts and tables

The charts, maps and tables of [Scoring & GAP Analysis](scoring-gap-analysis.md#results-tabs), [Network Insights](network-insights.md), [Non-Qualified Calls](non-qualified-calls.md), [Chart Builder](chart-builder.md#interactive-preview) and [PPT Designer](ppt-designer.md#live-and-expanded-chart-controls) download as an image, or copy to the clipboard as a screenshot, from two floating buttons at their top right corner, shown while the pointer is over them (on touch screens, a tap shows them for a few seconds, until a tap elsewhere):

| Button | What it does |
| --- | --- |
| Download (an arrow) | Saves a PNG image of what is shown: the theme, the choices of the section and the zoom of a chart or map, without the buttons of the page; a table that scrolls sideways or downwards, or a card taller than the window, is saved whole. A browser that does not let a page save what it draws saves an SVG image instead |
| Screenshot (a camera), on the left | Copies the same image to the clipboard, to paste it elsewhere (a presentation, an email or a chat); it turns green a moment once copied. The browser lets a page copy images only at a secure address (https, or the application opened on this computer): elsewhere the image opens in a window, to copy it from its menu (right-click it, or keep it pressed, and choose **Copy Image**) or download it |

The buttons of a whole card (a panel, a slide) are blue and stand on its top edge, at its right; in a card that holds several charts or tables, the one under the pointer shows buttons of its own in light blue, at its own top right corner. They keep clear of the buttons of the page (zoom, Collapse, the controls of a PPT chart), stay at the top of their card, chart or table, and show only while it is in sight, below the floating bars. The larger view of a chart, map or table (a double-click) has them in its corner. The file is named after the title of what it shows, and App Events records each download or copy, with `destination: clipboard` for a copy or `copy-dialog` when it opened in the window, or the reason it failed.

## Laptop screens

On a short screen (a 13" to 15" laptop, about 860 px of height or less in the browser, or a large zoom of the browser), wider than a phone, the page gives its content more room: the header of the application loses its line above the brand and takes less height with its tabs, the hero of each module shows its title on one line and its description on two (cut with *…*), the panels are closer to each other, and the notice of the unassigned values of the CDRs starts minimized at the bottom (**+** opens it). In the [Non-Qualified Calls](non-qualified-calls.md#call-details-and-activity) the panel of a call scrolls as a whole there. Larger screens keep the full layout.

## Small screens

The interface targets compact screens around the iPhone 17 base viewport (`402 × 874`).

- The application bar is two short lines: the name of the tool with its version and, under it, the active workspace, the user and **Logout**. The header of each module is short: its title of the size of the title of a panel and two lines of its description (its Help chapter has it whole).

- Instead of the rows of tabs, a bar at the bottom of the screen (phones up to 640 px wide, and phones in landscape) holds every main module you have, in the order of their tabs, the one open marked in its colour, then **Config** and **Menu** last: on a phone they go in two rows of six when they do not fit in one, **Menu** at the end of the second row. **Builders** opens above the bar the list of its builders (Chart Builder and Query Builder), and **Config** the list of the configuration pages of your role (Application Config and Workspace Config, Administrator Config for admins and Super Admin for super-admins), each in the colour of its module; a user without them has **Help** in its place. A module (or a page of Builders or Config) chosen in the bar opens where you left it; the module open, chosen again, goes back to the top of its page. **Menu** opens, from the top of the screen down to the bar, the tree of **Modules & Sections**: Main Modules, Administrative Modules and Documentation, each module with its sections and their parts, the module of the page open and marked, and **About**. While it is open its button shows **×** and **Close** and closes it; choosing a module or a section goes there and closes it too, as do the **×** of its header and Escape. The buttons of the bar are large enough to read and tap at a glance. The sections bar of the page floats just above it and fits the screen without scrolling sideways: it shows the section being read (**Sections** at the top of the page) between **‹** and **›**, which go to the previous and the next section, and a tap on it opens above the bar, in the colour of the bar, the list of every section of the page with its parts, the one being read marked (a section whose panel is hidden, such as the Charts Panel of PPT Designer before any PPT is generated, is left out); the colour theme of the themed modules is its palette icon at the start. Once the page is scrolled down, the button back to the top stands at its left, in the same row. What floats at the bottom of the page (the tasks in the background, the card of the unassigned values) stands above both bars, and the Modules & Sections tab stays at the right edge, above them.
- Added to the Home Screen of the phone (in Safari, **Share** › **Add to Home Screen**), the tool opens as an application on the whole screen, without the bars of the browser, so the bar of the modules stays still at the bottom while you scroll; in the browser, the bars of the browser come and go as you scroll and the bar of the modules moves with them. Its sign-in is its own: sign in once in it.
- Panels use reduced side margins and never widen the page: wide content scrolls inside its own container.
- Forms stack vertically, filters go two per row and action buttons are as wide as their text, sharing a row.
- The tables that change to cards (the workspaces of Workspace Management, the PPT Templates and the PPT Generation Jobs of PPT Designer, the maps and the CDR Field Dictionary of Workspace Config, the packages received in Administrator Config) are compact cards as those of [Reporting](reporting.md): the name in bold on top with its state beside it, the NR Mode, scope, slides, charts and filters as small chips, who made it and when in one small line, the other values two per row, each under the name of its column, the progress only while it is not done, and the actions at the bottom, five cards per page (the Charts Panel, four charts per page), with the pager below them; another page starts at its first card. The Super Admin tables of Modules Profiles, Workspace Groups and interface settings change to cards too, each value under the name of its column. While a dialog is open, the bars at the bottom of the screen give way to it. On every screen, the fields to create a workspace, a user, a Modules Profile, a Workspace Group, an Operator or Vendor label, a term of the AI Assistant Glossary or a PPT Design are not shown all the time: a **New …** button opens them in a dialog. The Charts Panel of PPT Designer shows its selection as small chips and its filters two per row, and Select Workspace its counts as small pills and the workspace to open with **Open** and **Close** in one row.
- The Designs of PPT Designer are a list of cards, as the reports of [Reporting](reporting.md): the name of each Design (which opens it in the viewer) with its state, its NR Mode and PPT Template, who changed it and when, **View PPT** and **Generate PPT**, and **⋯** with Edit Design, Edit details (its name, NR Mode and PPT Template), Duplicate, Export Design and Delete. Larger screens keep the table.
- In [Reporting](reporting.md), the report editor takes the whole screen and each run of History is a card.
- The Datasets of Workspace Management (all their tables, with their campaign bands), the Super Admin tables of users and of the Database Viewer, Datasets Management, the App Events of Application Logs and the Non-Qualified Calls stay tables, scrolled sideways, so a row is found at a glance; the App Events take at most 70% of the screen, with their pages right below them.
- Every pager of the application, on phones and on larger screens, has the same look: a white pill with round arrow buttons (first, previous, next, last) and the page between them.
- Chart navigation appears below the chart and before Interactive Preview.
- In Scoring & GAP Analysis, the tabs of the results (Summary, Scoring Charts, Scoring Tables…) are one row scrolled sideways, with the tab shown brought into view, also while it stays at the top of the results; the bar that moves, updates and deletes the Favourites Filters scrolls away with the page.
- The card of the unassigned values of the CDRs starts minimized, as a small pill at the bottom right; **+** opens it.
- The panels of the tasks in the background stay in their place above the bar (on larger screens they can be dragged by their header): **−** minimizes one and **+** opens it again. With the card of the unassigned values on screen, the tasks take the row and the card, minimized, is a round badge beside the button back to the top; opened, it is as wide as the screen.
- Wide data tables scroll inside their own containers rather than widening the page; in the Non-Qualified Calls tables their first column stays in view.
- Workspace Management remains visible when expanded.

On a phone, use portrait orientation for forms and landscape orientation when inspecting a very wide data table.

## PPT navigation and overlays

By default the analytical tabs are ordered **CDR Analysis** → **PPT Designer** → **Scoring & GAP Analysis** → **Network Insights** → **Non-Qualified Calls** → **Reporting** for users with each feature. CDR Analysis uses blue, Network Insights electric indigo, PPT Designer muted violet, Scoring & GAP Analysis the navy-to-green gradient of its header, Non-Qualified Calls raspberry and **Reporting** green; Network Insights and Non-Qualified Calls also use their colour for their header, buttons, tables and dialogs. Once a super-admin turns them on in **Super Admin → Interface Settings** (they are off on a new deployment), module tabs show their stage in a small label in the top-right corner, without taking space from their name: a red **ALPHA** while in development (Network Insights and Non-Qualified Calls, and the AI Assistant with a sparkle), a yellow **BETA** while being validated (**Reporting** and **Builders**) and a blue **NEW** once consolidated (Scoring & GAP Analysis, with a star, and Ticket Center); established modules (Workspace, CDR Analysis and PPT Designer) have no label. Super-admins choose in Interface Settings the order of the main tabs, the title of each one and its short title for narrow windows, its icon and its colour, and the label of each module with its colour and optional icon, or hide every label. Each module header shows a subtle decoration that represents the module (for example CDF curves in CDR Analysis or an antenna with radio waves in Network Insights) and is only as tall as its content; the controls of the module, such as the workspace or dataset selectors, follow in their own panel. The administrative tabs (Help, App Logs, Config and Admin) show an icon too, and the main tabs cover their lower part so both rows show the same tab height. Scoring offers NR Mode and CDR selection, aggregation controls, saved background jobs and tables/charts/GAP exports. Network Insights analyses RSRP/SINR, coverage and interference maps, sites, spectrum and network deployment. Each main tab shows a representative icon before its name. On narrower windows the main tabs switch to their short names (Analysis, Designer, Scoring, Network, NQ Calls, Reporting, Builders, Assistant, Tickets) and then drop their icons, so the tab rows never overlap.

**Reporting** is shown only to the super-admins without a Modules Profile and to the users whose Modules Profile includes it; on a new deployment it is in every profile. The design viewer groups charts by Slide and opens the same PPT Filters controls in a floating panel. Its dataset dialog provides pagination and CSV export.

App Logs is available from the utility navigation and includes App Events for the active workspace plus the live Execution Log for the running server. See [App Logs](app-logs.md).
