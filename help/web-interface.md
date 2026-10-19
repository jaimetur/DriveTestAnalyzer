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
| Small screens | [Open section](#small-screens) |
| Dashboard navigation and overlays | [Open section](#dashboard-navigation-and-overlays) |

## Navigation

Administrative tabs occupy the upper row, aligned to the left. Primary module tabs occupy the lower row, directly beside the first content panel. The same order applies on smaller screens.

Primary tabs, in their default order (super-admins change their order, titles, icons and colours in **Admin → Interface Settings**):

- **Workspace**
- CDR Analysis
- PPT Dashboards
- PPT Reporting (old)
- Scoring & GAP Analysis
- Network Insights
- Non-Qualified Calls (in development, hidden until activated)
- **Reporting**
- **Builders** (dropdown with Chart Builder and Query Builder)
- Ticket Center (opens without a workspace)

Each main tab is a module. An account sees the modules of its Modules Profile (**Admin → Modules Profiles**), and a super-admin every module until it is given one; a module an account does not see disappears from its tabs and Modules menu, and its pages and API answer 403. When the tabs do not fit on one line they wrap onto further lines, and main module tabs never share a line with the administrative tabs.

Other tabs:

- Help
- App Logs
- Config (dropdown with Application Config and Workspace Config, each with the list of its sections on hover), for `user-editor`, `admin` and `super-admin` roles
- Admin, for `admin` and `super-admin` roles

Help Home opens by default after login. The login page also offers **Request Access** to new users (see [Administrator Config › Access Requests](administrator-config.md#access-requests)). Help, the Readme, the Changelog and the tickets of Ticket Center are also available without signing in, with a prominent **Sign in** button at the top right that returns to the page after signing in. Every module except Workspace requires an open workspace.

Hovering a tab, or focusing it with the keyboard, opens below it the list of its sections, each with an icon and in the colour of the module: the panels of each main module (for example Scoring Calculation, Scoring & GAP Results and Favourites Filters in Scoring & GAP Analysis, where Scoring & GAP Results lists beside it Summary, Scoring Charts, Scoring Tables, Geographical Areas, Scoring Trends, GAP Analysis and Points Lost to open that results tab; on small screens these lists appear below their page, indented), App Events and Execution Log in App Logs, the panels of Admin, the chapters of the Readme and the latest releases of the Changelog. Help lists Help Home and, beside each group, the chapters of General, Main Modules, Administrative Modules and Reference (with the Readme and the Changelog), and ends with **About**, the credits of the application: its logo, name, version, release date and author. Choosing one opens that page with that section at its top (the Scoring & GAP Results entries bring the results tabs there), unfolding it when it was folded, and keeps it there while the page fills its panels (a reload then returns to where the page was being read, with its results tab); clicking the tab itself still opens the module, at its top when it is the page being shown. **Builders** and **Config** open their menu on hover too, and so does the **User** badge, with **Change password**.

The tabs stay at the top of the window while you scroll, so you can change module from anywhere in a page (unless they would take more than a third of a small screen).

Every page with two or more sections also shows them in a floating **sections bar**, in the colour of its module, below the introduction of the page: it stays at the top of the window, below the tabs, while you scroll and holds every entry of the list of its tab (or of its Config or Builders page). Its first entry, an arrow, goes back to the top of the page; choosing a section opens it at the top of the page, as from the list, and the bar marks the section being read as you scroll (the arrow while no section has reached the bar). An entry with parts of its own (Scoring & GAP Results with Summary, Scoring Charts, Scoring Tables, Geographical Areas, Scoring Trends, GAP Analysis and Points Lost, or Mappings & Reference Data with Operator Maps, Vendor Maps, Campaign Maps, Map Areas, Spectrum Holdings and Serving Networks in Workspace Config) shows an arrow and opens them below it on hover, on focus or with a click on the arrow. When the bar does not fit, its labels get smaller and then lose their icons, and on a narrow window it scrolls sideways. Non-Qualified Calls has its own bar, with the number of calls and the NQ Analysis Configuration beside it.

A round button at the bottom left, in the colour of the current module, appears once a page is scrolled down and takes it back to the top.

Open **Builders** to choose **Chart Builder** or **Query Builder**, each with the list of its sections on hover. The **Modules & Sections** drawer lists each builder with its sections. Within its Administrative Modules group, Application Logs is first and Administrator Config is last. The top tab for Administrator Config remains **Admin**.

Move the pointer near the left edge to reveal the collapsed Modules & Sections tab. An invisible hover area beside the tab responds even while background tasks are running; task cards leave that edge clear. The tab recedes when the pointer leaves, and keyboard focus also reveals it.

**Modules & Sections**, the tab at the left edge, opens the whole tree of the modules: Main Modules, Administrative Modules and Documentation, each module with its sections and their parts (as the lists of the tabs; Help with its chapters in their groups and, in a chapter, the headings of the document being read). The module of the page is open and marked; the other modules open with their arrow, and choosing a module or a section goes there and closes the drawer. It uses nearly the full height of the window and scrolls if the window is too short for every entry.

Open **Config** and choose **Application Config** for application-wide runtime settings or **Workspace Config** for PPT Templates Management, Operator Mappings, Vendor Mappings, Spectrum Holdings, Serving Networks, Main Cities and the Scoring hierarchy/KPI/GAP settings in the active workspace. The **Modules & Sections** tab at the left edge jumps between the panels of Workspace Config. Hovering **Application Config** or **Workspace Config** in the menu opens the list of their sections (Application Runtime and Email Delivery; PPT Templates Management, Main Cities, Mappings & Reference Data with its Operator, Vendor and Campaign Maps, Map Areas and Spectrum Holdings, and Scoring & GAP Analysis Setup): choosing one opens that page at that section, unfolding it when it was folded.

Help Navigation lists unnumbered documents under General, Main Modules, Administrative Modules and Reference. Main Modules follow the order of the main tabs, by default: [Workspace Management](workspace-management.md), CDR Analysis, PPT Dashboards, PPT Reporting (old), Scoring & GAP Analysis, Network Insights, Non-Qualified Calls, [Reporting](reporting.md), Chart Builder and Query Builder. Docker Deployment follows Deployment Configuration in General. App Logs is the first administrative document and Administrator Config is the last. Readme and Changelog open Reference before Project Structure and Roadmap.

The Help Home link stays above the groups. Every chapter is available to every reader except PPT Reporting (old), which only users with that feature see.

The Changelog adds a **Releases** list that jumps to each release; it highlights the release being read, as Help Navigation highlights the open document. Both lists grow down to the end of the document and only scroll beyond it.

## Header controls

- Click the active-workspace badge to switch workspace.
- The workspace-size badge is recalculated after dataset, report and Chart Set operations.
- The username badge shows the role and the Modules Profile of the account (Full Access for a super-admin without one), in the colour of the role for admins and super-admins and in that of the profile for the other users; click it to change the current password.
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

Every **Operator** filter (Scoring & GAP Analysis, CDR Analysis, PPT Dashboards, Network Insights, Non-Qualified Calls, the common filters of the Bundle Report Templates, the artifacts of the Reporting Jobs and the scenarios of the Scoring report editor and its saved configurations) takes patterns besides the operators listed: type one in the filter of the list and press Enter (or **＋ Add pattern**, which tells how many operators it takes now). A pattern is saved as such, travels with what keeps it (Saved Filters, favourites, Reporting Jobs, Dashboards, exports, transfers and backups) and is resolved each time the filter is used, so it also takes the operators that appear later:

- `*` stands for any characters, whatever the case: `VF*` takes VF, VF SA, VF VoNR, VF SM… and `*O2*` every operator with O2 in its name;
- `-` or `NOT` (followed by a space) before a value leaves it out: `-Lebara` or `NOT Lebara` is every operator but Lebara, `NOT Leb*` every operator but those that start with Leb, and several exclusions leave out each one;
- values and exclusions together take the values but the excluded ones: `VF*` with `-VF SM` is every VF variant but VF SM.

Patterns come first in their list, tagged **pattern** or **except**, and an operator of the Operator Maps is taken or left out with the spellings of the CDRs it stands for. An operator that every filter must leave out needs no pattern: give it the **Exclude** role in [Operator Maps](workspace-config.md#operator-maps).

## Filter Builder

The shared Filter Builder is used by Chart Builder, PPT Reporting (old) Chart Preview and Report Template Chart Preview.

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

After signing in and while signed in, a super-admin is told in the same style as an incoming server transfer of the [access requests](administrator-config.md#access-requests) waiting for activation and of the new [tickets](ticket-center.md#who-can-do-what) it has not been told of, once each, on any page: the poll of incoming transfers checks for them every few seconds (every 30 seconds in a hidden tab), and an open dialog takes in what arrives meanwhile. The dialog waits for any other dialog or running operation of the page to close first, and a dialog that opens while it is shown goes over it.

## Floating background-task cards

Every authenticated page polls active background work (every 2 seconds while work runs, every 8 seconds otherwise and every 30 seconds in a hidden tab) and shows compact floating cards until it finishes. Work for the open workspace appears at the lower right. Work for one or more other accessible workspaces appears in differently coloured lower-left cards, grouped by workspace name; changing the active workspace moves each running task to the appropriate side.

Each card preserves its expanded or minimized state when moving between modules or reloading the page.

Each card shows the task, its current stage and progress when the job reports one. The red circular **Stop Job** control is available only for interruptible work in a workspace the user can access and asks for confirmation before requesting a stop.

Browser dataset uploads retain their latest measured percentage between progress events and can be interrupted while their request is active; dataset jobs already accepted by the server then appear separately and can be stopped at their safe checkpoints. Report, Chart Set, Auto-calculated Field and combined-CDR work use the same cooperative stop behaviour.

A stopped duplication removes its partial workspace; stopped exports remove temporary output; imports cannot be stopped after importing has begun.

## Unassigned values card

While the ready CDRs of the open workspace have Operators, Vendors or Campaigns that no Operator, Vendor or Campaign Map assigns, a red card at the lower right of every page lists them until they are assigned. Editors open the assignment table from its buttons; the user-viewer role is asked to inform an administrator. See [Unassigned values warning](workspace-config.md#unassigned-values-warning).

## Small screens

The interface targets compact screens around the iPhone 13 base viewport (`390 × 844`).

- Panels use reduced side margins and never widen the page: wide content scrolls inside its own container.
- Forms stack vertically, filters go two per row and action buttons are as wide as their text, sharing a row.
- Dataset Management, Workspace Management, the Reporting Jobs and their Run History, PPT Dashboards and the Admin tables of users, Modules Profiles, Workspace Groups and interface settings change to cards, each value under the name of its column, shown one card per page.
- Every pager of the application, on phones and on larger screens, has the same look: a white pill with round arrow buttons (first, previous, next, last) and the page between them.
- Chart navigation appears below the chart and before Interactive Preview.
- Wide data tables scroll inside their own containers rather than widening the page; in the Non-Qualified Calls tables their first column stays in view.
- Workspace Management remains visible when expanded.

On a phone, use portrait orientation for forms and landscape orientation when inspecting a very wide data table.

## Dashboard navigation and overlays

By default the analytical tabs are ordered **CDR Analysis** → **PPT Dashboards** → **PPT Reporting (old)** → **Scoring & GAP Analysis** → **Network Insights** → **Non-Qualified Calls** → **Reporting** for users with each feature. CDR Analysis uses blue, Network Insights electric indigo, PPT Dashboards muted violet, Scoring & GAP Analysis the navy-to-green gradient of its header, Non-Qualified Calls raspberry, **Reporting** green and PPT Reporting (old) brighter purple; Network Insights and Non-Qualified Calls also use their colour for their header, buttons, tables and dialogs. Once a super-admin turns them on in **Admin → Interface Settings** (they are off on a new deployment), module tabs show their stage in a small label in the top-right corner, without taking space from their name: a red **ALPHA** while in development (Network Insights and Non-Qualified Calls), a yellow **BETA** while being validated (**Reporting** and **Builders**) and a blue **NEW** with a star once consolidated (Scoring & GAP Analysis); established modules (Workspace, CDR Analysis and PPT Dashboards) have no label. Super-admins choose in Interface Settings the order of the main tabs, the title of each one and its short title for narrow windows, its icon and its colour, and the label of each module with its colour and optional icon, or hide every label. Each module header shows a subtle decoration that represents the module (for example CDF curves in CDR Analysis or an antenna with radio waves in Network Insights) and is only as tall as its content; the controls of the module, such as the workspace or dataset selectors, follow in their own panel. The administrative tabs (Help, App Logs, Config and Admin) show an icon too, and the main tabs cover their lower part so both rows show the same tab height. Scoring offers NR Mode and CDR selection, aggregation controls, saved background jobs and tables/charts/GAP exports. Network Insights analyses RSRP/SINR, coverage and interference maps, sites, spectrum and network deployment. Each main tab shows a representative icon before its name. On narrower windows the main tabs switch to their short names (Analysis, Dashboards, Reporting, Scoring, Network) and then drop their icons, so the tab rows never overlap.

**Reporting** and PPT Reporting (old) are shown only to the super-admins without a Modules Profile and to the users whose Modules Profile includes them; on a new deployment **Reporting** is in every profile and PPT Reporting (old) in none. The dashboard viewer groups charts by Slide and opens the same Dashboard Filters controls in a floating panel. Its dataset dialog provides pagination and CSV export.

App Logs is available from the utility navigation and includes App Events for the active workspace plus the live Execution Log for the running server. See [App Logs](app-logs.md).
