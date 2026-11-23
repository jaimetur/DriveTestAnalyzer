# Web Interfaces

The UI uses a shared header, module tabs, panels, dialogs and tables. Read [Product Overview](overview.md) for the purpose of each module.

> [!NOTE]
> **Role-sensitive navigation.** Sections and actions depend on your role and workspace access. A hidden administrative module does not indicate missing data.

> [!TIP]
> **Long-running work.** Floating task cards follow server-side work while you navigate. Minimizing a card does not stop its task.

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Present the tool to visitors | [Landing page](#landing-page) |
| Move between modules and workspaces | [Navigation](#navigation) · [Header controls](#header-controls) |
| Pick values and operators quickly (`VF*`, `NOT Lebara`) | [Searchable selectors](#searchable-selectors) · [Operator patterns](#operator-patterns) |
| Build a filter | [Filter Builder](#filter-builder) |
| Sort, filter and copy tables | [Tables](#tables) |
| Follow the tasks running in the background | [Floating background-task cards](#floating-background-task-cards) |
| Save a chart or table as an image | [Images of charts and tables](#images-of-charts-and-tables) |
| Use the tool on a laptop or a phone | [Laptop screens](#laptop-screens) · [Small screens](#small-screens) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Landing page

The address of the server (`/`) opens the landing page of DriveTest Analyzer to anyone without signing in; a signed-in user opens the application instead (or the landing page with `/?landing`). The old `/landing` address redirects to `/`.

- **Hero:** the slides of the Overview presentation in a laptop screen, with **Sign in** (**Open the app** when signed in) and **Watch the overview**.
- **Figures:** live counts of the workspaces of the server (CDR rows, tests and calls, CDRs, campaigns, NQ calls, network cells, users and releases), the same ones as the presentations; a figure the server does not have yet is left out.
- **Modules:** each one with the slides of its presentation (they play while in view; arrows, a swipe or a click to enlarge), what it does, **Watch the presentation** and **Read the guide** (its Help chapter). The main modules show their titles of [Interface Settings](super-admin.md#interface-settings).
- **Presentations:** the Full Presentation (play it or download it) and a card per presentation, opening it in the slide viewer of [Product Presentations](presentations.md).
- **Technical guide:** the size and chapters of the whole documentation, a fan of its pages and its PDF and Word downloads; each chapter opens the guide at its page.
- **What's new:** the new features and enhancements of the two latest releases of the Changelog, with a link to their release notes.
- **Help:** cards to the main chapters of the Help, open to everyone.

## Navigation

The dark application bar at the top, in a darker shade of the colour of the module open (dark blue and teal outside the modules), holds the name of the tool with its version, the active workspace, and the user (with a dot of the colour of its role) with **Logout**. Under it, one white panel holds the tabs:

- **Upper row:** the administrative tabs as buttons, each with an icon: Help, App Logs, Config (Application Config and Workspace Config, for `user-editor`, `admin` and `super-admin`), Admin (Administrator Config, for `admin` and `super-admin`) and Super Admin (for `super-admin`). They never share a line with the main tabs.
- **Main tabs**, under a line: folder tabs with a line of the colour of their module on top and their icon in that colour, the open one filled with that colour. Each is a module, by default in this order: **Workspace**, CDR Analysis, PPT Designer, Scoring & GAP Analysis, Network Insights, Non-Qualified Calls (in development), **Reporting**, **Builders** (Chart Builder and Query Builder), AI Assistant and Ticket Center.
- **Narrow windows:** the main tabs take their short names (Analysis, Designer, Scoring, Network, NQ Calls, Reporting, Builders, AI Assistant, Tickets), then drop their icons, and wrap to further rows when they still do not fit, so the rows never overlap. On small screens a bar at the bottom replaces both rows (see [Small screens](#small-screens)).
- **Who sees what:** an account sees the modules of its [Modules Profile](super-admin.md#modules-profiles) (a super-admin every module until it is given one). Every module except Workspace and Ticket Center needs an open workspace.
- **Look:** super-admins change the order, titles, short titles, icons, colours and stage labels of the main tabs in [Interface Settings](super-admin.md#interface-settings). By default CDR Analysis is blue, Network Insights electric indigo, PPT Designer muted violet, Scoring & GAP Analysis the navy-to-green gradient of its header, Non-Qualified Calls raspberry and **Reporting** green; Network Insights and Non-Qualified Calls also use their colour for their header, buttons, tables and dialogs. Each module header shows a subtle decoration of the module (for example CDF curves in CDR Analysis or an antenna with radio waves in Network Insights), only as tall as its content; the controls of the module, such as the workspace or dataset selectors, follow in their own panel.
- **Stage labels:** once a super-admin turns them on (off on a new deployment), a small label in the top-right corner of a tab shows its stage without taking space from its name: a red **ALPHA** in development (Network Insights, Non-Qualified Calls, and the AI Assistant with a sparkle), a yellow **BETA** while validated (**Reporting** and **Builders**) and a blue **NEW** once consolidated (Scoring & GAP Analysis, with a star, and Ticket Center); established modules (Workspace, CDR Analysis and PPT Designer) have none.
- **Staying in sight:** the tabs stay at the top of the window while you scroll (unless they would take more than a third of it), and so does the application bar when both take no more than a third of the window; on small screens the bar of the modules stays instead.

**Browser tab titles** read `DT Analyzer - ` plus the module's Short title (`DT Analyzer - Scoring`, `DT Analyzer - Tickets`; CDR Analysis, PPT Designer, Network Insights and AI Assistant use their Module Title), the page name (Chart Builder, Query Builder, Workspace Config, Application Config, Readme, Changelog), `Presentations` for Product Presentations, or the title of a linked presentation.

**Section lists.** Hovering or focusing a tab opens the list of its sections below it, with icons in the module colour (<kbd>Esc</kbd> or scrolling closes it):

- **Main modules:** their panels (for example Scoring Calculation, Scoring & GAP Analysis, with its results tabs beside it, and Favourite Scorings). On small screens these lists appear indented below their page.
- **App Logs:** App Events and Execution Log. **Admin** and **Super Admin:** their panels.
- **Config:** Application Config (Application Runtime and Email Delivery) and Workspace Config (Main Cities, Mappings & Reference Data with its Operator, Vendor and Campaign Maps, Map Areas and Spectrum Holdings, and Scoring & GAP Analysis Setup). **Builders:** Chart Builder and Query Builder, each with its sections. Both open their menu on hover too.
- **Readme and Changelog:** the chapters of the Readme and the latest releases of the Changelog.
- **Help:** Help Home and, beside each group, the chapters of General, Main Modules, Administrative Modules and Reference, ending with **About**.
- **Choosing a section** opens the page with that section (or results tab) at its top, unfolded, and keeps it there while the page fills, until you scroll; in Non-Qualified Calls until every panel is drawn, however long it takes (a reload then returns to where you were reading, with its results tab).
- **Clicking the tab itself** still opens the module, at its top when it is the page being shown.

**Sections bar.** A page with two or more sections shows them in a floating bar in its module colour, below its introduction, that stays below the tabs while you scroll (on small screens, above the bar of the modules) and holds the entries of its tab list.

- Its first entry, an arrow, goes to the top of the page; it marks the section being read (the arrow before the first).
- An entry with parts (Scoring & GAP Analysis with its results tabs; Mappings & Reference Data with Operator, Vendor and Campaign Maps, Map Areas, Spectrum Holdings and Serving Networks) shows an arrow that opens them below it (above, when the bar is at the bottom) on hover, focus or click.
- When it does not fit, its labels shrink, then lose their icons, then scroll sideways. Non-Qualified Calls has its own bar, with the number of calls and the NQ Analysis Configuration.

**Modules & Sections** is a collapsed tab at the left edge of screens 1200 px wide or more, at the right edge below. Move the pointer near that edge (or touch it), or focus it, to reveal it; its hover area responds even while tasks run, task cards leave the edge clear, and it recedes when the pointer leaves. It opens the tree of Main Modules, Administrative Modules (App Logs, Administrator Config, still the **Admin** tab, and Super Admin) and Documentation, with every section and part (Help with its chapters and, in a chapter, its headings). The current module is open and marked; choosing an entry goes there and closes the drawer. It is nearly as tall as the window, scrolls when needed and stands above every floating card.

**Help navigation** lists every chapter, for every reader, below Help Home: General (Docker Deployment after Deployment Configuration), Main Modules in tab order ([Workspace Management](workspace-management.md) to Ticket Center, with Chart Builder and Query Builder for **Builders**), Administrative Modules (App Logs, Administrator Config, Super Admin) and Reference (Readme and Changelog, then Project Structure and Roadmap). It highlights the open chapter, as the **Releases** list of the Changelog highlights the release being read; both lists grow to the end of the document and only scroll beyond it.

**Export the Help.** **Export**, beside **Documentation** at the top of every Help page (also without signing in), opens a dialog to choose **This guide** or **All the documentation**, and **Word (.docx)** or **PDF**:

- **Content:** a cover with the version and the date, then a table of contents of every heading with its page, on pages of their own (it replaces the *Main topics in this guide* table of a chapter). The headings are numbered as on the page and the sections follow each other on the same page; the title is at the top of every page and its number at the bottom. The whole documentation opens each module with a sub-cover with its number, and leaves out Help Home and Product Presentations.
- **Layout:** tables, lists, notes and tips, code and keys keep their look; the presentations are not included (open the chapter in the Help to watch them).
- **PDF:** made by LibreOffice on the server (without it, the dialog says so). The whole documentation takes a while the first time; each file is kept until the Help or the version changes, so the next exports are immediate.
- **App Events:** each export is recorded as `help_exported` (content, chapter, format, size, whether it was kept and its time).
- **Guides in the viewer:** the **Complete guide** card on Help Home opens the whole documentation page by page in the slide viewer, by module, and the card of the guide of each module, beside its presentation at the start of its chapter (**Presentation & Guide**, or **Guide** when it has none), opens that chapter by section; both with **PDF** and **Word** to download (`help_guide_opened`).

A round button at the bottom left, in the colour of the current module, appears once a page is scrolled down and takes it back to the top.

## Header controls

- **Logo:** takes the page back to its top. **Name of the application:** opens **About** (logo, version, release date, author and links to the Help, Readme and Changelog). **Version badge:** opens the Changelog.
- **Active-workspace badge:** switches workspace. The workspace-size badge is recalculated after dataset and report operations.
- **Username badge:** shows the role and the Modules Profile of the account (Full Access for a super-admin without one), with a left edge in the colour of the role for admins and super-admins and in that of the profile for the other users. Hover or focus it for its menu:
  - **Change password**;
  - **Email preferences**, where the emails of the tool go (empty: none) and how often you get the emails of your tickets and, apart, those of the NQ calls (see [Email Delivery](app-config.md#email-delivery));
  - **API keys**, your own keys for the LLM writers that Super Admin sets to each user's key (see [AI Comment Writers](super-admin.md#ai-comment-writers));
  - **Start Demo Mode…**, for admins and super-admins (see [Demo Mode](#demo-mode)).
- **DEMO MODE · until …** pill: shown to the users of a running demo.
- **Logout** ends the session.

**Signing in.** Help Home opens by default after login. The login page also offers **Request Access** to new users (see [Access Requests](super-admin.md#access-requests)) and, when [Email Delivery](app-config.md#email-delivery) is set up, **Forgot your password?** (see [Forgotten passwords](super-admin.md#forgotten-passwords)). Help, the Readme, the Changelog and the tickets of Ticket Center open without signing in, with a prominent **Sign in** button at the top right that returns to the page. After five wrong passwords in a row for a username, its next tries wait (30 seconds, then longer, up to five minutes), also for the password an access request asks an existing account for; a right password, or half an hour, starts over.

## Demo Mode

Demo Mode keeps the platform for the users of a live demo: everybody else is signed out and cannot sign in until it is over. Admins and super-admins start it with **Start Demo Mode…**, which asks:

- **Expected end of the demo:** a date and time (**+30 min**, **+1 h** and **+2 h** set it from now).
- **Message for the users:** a proposed text that can be changed, shown to the users signed out with who started the demo and its expected end.
- **Users with access during the demo:** every active account, a green dot for those online and a tag for those with unsaved changes. Its starter always keeps access and, when an admin starts it or changes its users, so does every super-admin (a super-admin can leave the others out). A summary counts who keeps access and which online users will be warned or asked to save.

Then:

- **Users without access with a page open** are warned (who, until when, the message) and signed out within **5 minutes**, or at once with **Sign out now**.
- **Users with unsaved changes** (a PPT Design, a report of [Reporting](reporting.md), a Scoring Methodology, an Auto-calculated Field, an NQ call or the NQ Prioritization Rules, a chart template, Operator and Vendor Map labels) see a banner asking them to save; they are signed out once nothing is left to save (saved or discarded), however long it takes, or when their pages close. Meanwhile buttons that start new changes (New, Create, Add, Edit, Duplicate, Import, Upload, Generate…) are refused, and then the server refuses their changes too.
- **Users with a session but no page open** are signed out at once.
- **The sign-in page** refuses users without access, saying who runs the demo, until when and the message; a signed-out user sees why, and the page tells when the demo is over.

Users with access see the **DEMO MODE · until …** pill, with how many users are still leaving or saving; for admins and super-admins it opens a menu with those users (their unsaved changes or time left), **Change end time…**, **Users and message…** and **End Demo Mode now**.

Demo Mode never ends by itself: at the expected end its starter (or, while that user has no page open, the demo's other admins and super-admins) is asked to **extend it by 5, 15, 30, 45 or 60 minutes**, **Remind me in 5 min** or **End Demo Mode now**, while the sign-in page says the demo is taking longer than expected. [App Events](app-logs.md) records its start, changes, extensions and end, every user warned, signed out (and why) or refused at sign-in, and every change refused. It survives a server restart; describing what the server does now, it is never exported, transferred or backed up.

## Panels

- A panel heading explains its purpose; collapsible panels remember their open/closed state where supported.
- Status pills distinguish ready, processing, failed and stopped work.
- Destructive actions use red styling and request confirmation when appropriate.
- On every screen, the fields to create a workspace, a user, a Modules Profile, a Workspace Group, an Operator or Vendor label, a term of the AI Assistant Glossary or a PPT Design are not shown all the time: a **New …** button opens them in a dialog.

## Searchable selectors

Single-select and multi-select controls share a compact searchable style and open the application's own list below their field, layered above their active dialog.

- Type in the search field to narrow values; in a list without a search field, typing the first letters of a value jumps to it.
- Multi-select controls keep the order in which values are selected when order has meaning.
- **Select all / none** toggles the currently available options.

### Operator patterns

Every **Operator** filter (Scoring & GAP Analysis, CDR Analysis, PPT Designer, Network Insights, Non-Qualified Calls, the common filters of the reports of [Reporting](reporting.md), and the scenarios of the Scoring report editor and its saved configurations) takes patterns besides the operators listed: type one in the search of the list and press Enter (or **＋ Add pattern**, which tells how many operators it takes now).

- `*` stands for any characters, whatever the case: `VF*` takes VF, VF SA, VF VoNR, VF SM… and `*O2*` every operator with O2 in its name.
- `-` or `NOT` (followed by a space) before a value leaves it out: `-Lebara` or `NOT Lebara` is every operator but Lebara, `NOT Leb*` every operator but those that start with Leb; several exclusions leave out each one.
- Values and exclusions together take the values but the excluded ones: `VF*` with `-VF SM` is every VF variant but VF SM.

A pattern is saved as such, travels with what keeps it (Saved Scorings, favourites, reports, Designs, exports, transfers and backups) and is resolved each time the filter is used, so it also takes operators that appear later. Patterns come first in their list, tagged **pattern** or **except**, and an operator of the Operator Maps is taken or left out with the spellings of the CDRs it stands for. A pattern added while every operator is ticked chooses on its own (the operators are unticked), and the list shows what it takes: `-Three` alone shows **All except Three**. An operator that every filter must leave out needs no pattern: give it the **Exclude** role in [Operator Maps](workspace-config.md#operator-maps).

## Filter Builder

The shared Filter Builder of Chart Builder and the Report Template Chart Preview adds or removes conditions without editing raw syntax: its field selector is searchable, its operators adapt to list, text and numeric conditions, and the parsed filter appears beneath it. `IN`/`NOT IN` lists may be typed without parentheses; the parser adds them.

## Tables

- Wide desktop tables use fixed action areas where needed; horizontal and vertical scrolling stays inside the table when controls must remain visible.
- Database and filtered-dataset tables paginate on the server, and their Excel-style header menus search the distinct values of the complete filtered source.
- Every pager has the same look: a white pill with round arrow buttons (first, previous, next, last) and the page between them.
- The dataset dialog of the PPT Designer viewer, which groups charts by Slide and opens the PPT Filters in a floating panel, provides pagination and CSV export.

## Dialogs and progress

Long operations use progress dialogs, for example while preparing an export, sending or receiving a server transfer, processing an import, loading a Chart Data Preview or a filtered dataset. Server-transfer dialogs can be hidden while the transfer goes on (see [Transfer to other server](administrator-config.md#transfer-to-other-server)).

A super-admin is told on any page, in the same style as an incoming transfer, of the access requests waiting for activation and of new tickets (see [Access Requests](super-admin.md#access-requests)). That dialog waits for any other dialog or running operation of the page to close first, and a dialog that opens while it is shown goes over it.

## Floating background-task cards

Every signed-in page polls background work (every 2 seconds while work runs, 8 seconds otherwise, 30 seconds in a hidden tab) and shows a floating card per task until it finishes.

- **Where:** work of the open workspace at the lower right; work of other accessible workspaces in differently coloured lower-left cards, grouped by workspace name. Changing the active workspace moves each running task to its side.
- **Each card** shows the task, its current stage and its progress when the job reports one, and keeps its expanded or minimized state (**−** / **+**) across modules and reloads. Except on phones, drag it by its header to move it (the browser remembers where); its button with four corners puts it back.
- **Stop Job**, the red round control, appears only for interruptible work in a workspace the user can access and asks for confirmation.
- **Uploads** keep their last measured percentage and can be interrupted while their request is active; dataset jobs the server already accepted appear separately and stop at safe checkpoints, as do Auto-calculated Field and combined-CDR work.
- **After a stop:** a stopped duplication removes its partial workspace and a stopped export its temporary output; an import cannot be stopped once importing has begun.

## Unassigned values card

While the ready CDRs of the open workspace have Operators, Vendors or Campaigns that no Operator, Vendor or Campaign Map assigns, a red card at the bottom centre of every page lists them until they are assigned (see [Unassigned values warning](workspace-config.md#unassigned-values-warning)). Editors open the assignment table from its buttons; the user-viewer role is asked to inform an administrator.

- With task cards on screen it takes the middle of their row, between those of other workspaces and of the open workspace and as wide as them, above the system task cards when there are any.
- On a [laptop screen](#laptop-screens) it starts minimized to its title line, and on a phone as a small pill at the bottom right (a round badge beside the button back to the top while task cards take the row); **+** opens it, as wide as the screen on a phone, where the button back to the top rises above it.

## Images of charts and tables

The charts, maps and tables of [Scoring & GAP Analysis](scoring-gap-analysis.md#results-tabs), [Network Insights](network-insights.md), [Non-Qualified Calls](non-qualified-calls.md), [Chart Builder](chart-builder.md#interactive-preview) and [PPT Designer](ppt-designer.md#live-and-expanded-chart-controls) download as an image, or copy to the clipboard, from two floating buttons at their top right corner, shown while the pointer is over them (on touch screens, a tap shows them for a few seconds, until a tap elsewhere):

- **Download** (arrow): a PNG of what is shown, with the theme, the section's choices and the zoom, without the page's buttons; a scrolling table or a card taller than the window is saved whole. Where the browser does not let a page save what it draws, an SVG.
- **Screenshot** (camera, on the left): copies the same image to the clipboard, turning green a moment. Browsers allow it only at a secure address (https, or the application opened on this computer); elsewhere the image opens in a window, to copy it (right-click or long-press, **Copy Image**) or download it.

A whole card (a panel, a slide) has blue buttons on its top edge, at the right; inside it, the chart or table under the pointer has its own, light blue. They avoid the page's own buttons (zoom, Collapse, PPT chart controls), stay at the top of what they capture while it is in sight, below the floating bars, and sit in the corner of the larger view (double-click). The file takes the title of what it shows; App Events records each download or copy (`destination: clipboard`, or `copy-dialog` when it opened in the window) or why it failed.

## Laptop screens

On a short screen (a 13" to 15" laptop, about 860 px of height or less in the browser, or a large browser zoom) wider than a phone, the page gives its content more room: the header loses its line above the brand and takes less height with its tabs, the hero of each module shows its title on one line and its description on two (cut with *…*), the panels are closer to each other and the unassigned values card starts minimized. In [Non-Qualified Calls](non-qualified-calls.md#call-details-and-activity) the panel of a call scrolls as a whole. Larger screens keep the full layout.

## Small screens

The interface targets compact screens around the iPhone 17 base viewport (`402 × 874`). Use portrait for forms and landscape for very wide tables.

- **Header:** two short lines (the tool and version; the workspace, the user and **Logout**). Module headers show a panel-size title and two lines of description (the Help chapter has it whole).
- **Bar of the modules:** on phones (up to 640 px wide, and in landscape) a bar at the bottom replaces the tabs, with large buttons: your main modules in tab order (the open one in its colour), **Config**, **App Logs**, **Help**, **Changes** (Changelog), **Readme**, **Slides** ([Product Presentations](presentations.md)), **Roadmap** and **Menu**.
  - When they do not fit, they form one row that scrolls sideways (fading on the side where more wait, the open module in sight), **Menu** fixed at its end. Swipe up on the bar, or tap its handle, for rows of six; swipe down (or tap the handle) for one row. A vertical swipe on the bar never scrolls the page, and each page starts with one row.
  - **Builders** opens its builders above the bar, **Config** the configuration pages of your role (Application Config, Workspace Config, Administrator Config for admins, Super Admin for super-admins), each in its colour; without any, there is no **Config**.
  - A module opens where you left it; the open one, chosen again, goes back to its top.
  - **Menu** opens the **Modules & Sections** tree, with **About**, from the top down to the bar. Its button becomes **×** **Close**; choosing an entry, the **×** of its header or Escape also close it.
- **Sections bar:** floats above the bar of the modules without scrolling sideways, showing the section being read (**Sections** at the top) between **‹** and **›** (previous and next section).
  - A tap opens the list of every section and part, the current one marked. Hidden panels (such as the Charts Panel of PPT Designer before any PPT is generated) are left out; the views of Ticket Center are all listed, each opening its view.
  - Themed modules show their palette icon at its start; the button back to the top stands at its left once the page is scrolled.
- **At the bottom:** task cards (fixed in place) and the unassigned values card stand above both bars, and the Modules & Sections tab at the right edge above them. The bars give way to an open dialog.
- **Home Screen:** added to the Home Screen (Safari **Share** › **Add to Home Screen**), the tool opens full screen without the browser bars, so the bar of the modules stays still while you scroll (in the browser it moves with the browser bars). It has its own sign-in: sign in once in it.
- **Layout:** panels have reduced margins and never widen the page (wide content and tables scroll in their own container); forms stack, filters go two per row and action buttons are as wide as their text, sharing a row.
- **Cards instead of tables:** the workspaces of Workspace Management, the PPT Templates and PPT Generation Jobs of PPT Designer, the maps and CDR Field Dictionary of Workspace Config and the packages received in Administrator Config become compact cards like those of [Reporting](reporting.md): the name in bold with its state; NR Mode, scope, slides, charts and filters as small chips; who made it and when in one line; other values two per row under their column name; progress only while not done; the actions at the bottom. Five cards per page (the Charts Panel, four charts), the pager below, a new page starting at its first card. The Super Admin tables of Modules Profiles, Workspace Groups and Interface Settings also become cards.
  - PPT Designer's Designs are cards with the name (opening the viewer), state, NR Mode, PPT Template, who changed it and when, **View PPT**, **Generate PPT** and **⋯** (Edit Design, Edit details (name, NR Mode and PPT Template), Duplicate, Export Design, Delete).
  - In [Reporting](reporting.md) the report editor takes the whole screen and each History run is a card.
  - The Charts Panel of PPT Designer shows its selection as chips and filters two per row; Select Workspace its counts as small pills, with **Open** and **Close** in one row.
- **Tables that stay tables**, scrolled sideways: the Datasets of Workspace Management (with campaign bands), the Super Admin users and Database Viewer, Datasets Management, App Events (at most 70% of the screen, the pager right below) and Non-Qualified Calls (first column kept in view).
- **Charts:** navigation sits below the chart, before Interactive Preview.
- **Scoring & GAP Analysis:** the results tabs are one sideways-scrolling row with the current tab in view, also while it stays at the top; the Favourite Scorings bar scrolls away with the page.
- Workspace Management stays visible when expanded; stage labels never show on the tabs.

## Tips & shortcuts

These gestures and keys work on every page. Each module adds its own: see **Module tips** at the end of this section.

**Moving around**

| To… | Do this |
| --- | --- |
| Go back to the top of the page | Click the logo in the header, or the round button at the bottom left that appears once the page is scrolled down |
| Go back to the top of the module you are in | Click its tab again. <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+click or <kbd>Shift</kbd>+click opens it as an ordinary link (a new tab or window) |
| Jump to a section of a module | Hover its tab, or focus it with <kbd>Tab</kbd>, and choose the section. <kbd>Esc</kbd> or scrolling closes the list |
| Reveal the collapsed **Modules & Sections** tab | Move the pointer within 44 px of the window edge: the left edge on screens 1200 px wide or more, the right edge below. It recedes when the pointer leaves. On touch: touch within 30 px of that edge; it hides again after 5 seconds |

**On a phone (bottom bar)**

| To… | Do this |
| --- | --- |
| Show every module in rows | Swipe up on the bar, or tap the handle at its top |
| Go back to one row | Swipe down on the bar, or tap the handle again |
| Close **Menu**, **Builders** or **Config** | <kbd>Esc</kbd>, or tap outside the list |

**Dropdowns of the application**

| To… | Do this |
| --- | --- |
| Open a dropdown from the keyboard | Focus it and press <kbd>Space</kbd>, <kbd>Enter</kbd>, <kbd>↑</kbd>, <kbd>↓</kbd> or <kbd>F4</kbd> |
| Jump to an option | Type its first letters (in a list without a search box) |
| Move through the options | <kbd>↑</kbd> / <kbd>↓</kbd>; <kbd>Home</kbd> / <kbd>End</kbd> for the first and the last |
| Choose the option marked | <kbd>Enter</kbd> |
| Close without choosing | <kbd>Esc</kbd> or <kbd>Tab</kbd> |
| Narrow a searchable list | Type in its search box; <kbd>↓</kbd> goes from the search into the list |
| Add an Operator pattern | Type it in the search of an **Operator** filter (`VF*`, `NOT Lebara`) and press <kbd>Enter</kbd> (see [Operator patterns](#operator-patterns)) |

**Dialogs**

| To… | Do this |
| --- | --- |
| Accept a dialog that asks for a text | <kbd>Enter</kbd> |
| Cancel a dialog | <kbd>Esc</kbd>, or click outside it |

**Charts, maps and tables**

| To… | Do this |
| --- | --- |
| Download or copy a picture of a card, chart, map or table | Hover it and use the two buttons at its top right corner. On touch: tap it to show them for a few seconds (see [Images of charts and tables](#images-of-charts-and-tables)) |
| Hide or show a series of a chart | Click its entry in the legend; click it again to show it |
| Zoom into part of a chart | Drag a rectangle over its plot area (not over its title) with the mouse; once zoomed, drag to move around |

**Panels of the tasks in the background**

| To… | Do this |
| --- | --- |
| Move a panel out of the way | Drag it by its header (not on phones); the browser remembers where |
| Put it back in its place | Its button with four corners (**Return panel to its default position**) |
| Minimize it or open it again | **−** / **+** |

**Module tips**

- [Workspace Management](workspace-management.md#tips-shortcuts) and [Workspace Config](workspace-config.md#tips-shortcuts)
- [CDR Analysis](datasets-analysis.md#tips-shortcuts)
- [PPT Designer](ppt-designer.md#tips-shortcuts)
- [Scoring & GAP Analysis](scoring-gap-analysis.md#tips-shortcuts)
- [Network Insights](network-insights.md#tips-shortcuts)
- [Non-Qualified Calls](non-qualified-calls.md#tips-shortcuts)
- [Reporting](reporting.md#tips-shortcuts)
- [Chart Builder](chart-builder.md#tips-shortcuts) and [Query Builder](query-builder.md#tips-shortcuts)
- [AI Assistant](assistant.md#tips-shortcuts)
- [Ticket Center](ticket-center.md#tips-shortcuts)
- [Super Admin](super-admin.md#tips-shortcuts)
- [The slide viewer of the presentations](presentations.md#using-the-slide-viewer)
