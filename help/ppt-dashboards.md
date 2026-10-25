# PPT Dashboards

Build an interactive Dashboard from processed Data, Voice and Speech CDRs, using a saved Report Template. Apply one dataset selection to its slides, explore the charts, then export the result to PowerPoint.

> [!NOTE]
> **A Dashboard is a saved definition, not a copy of your data.** It stores its template, Scope, dates, filters and comments; its CDRs are chosen from its NR Mode and Campaign filter each time it is prepared. Source CDRs and generated caches remain separate.

## Presentation

The presentation **PPT Dashboards** sums the module up. Interactive Dashboards from Report Templates: one selection of CDRs on every slide, live charts to explore and PowerPoint exports generated in the background. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Presentations](help.md#presentations).

```presentations
ppt-dashboards
```

## Choose your task

| I want to… | Go to |
| --- | --- |
| Watch the presentation of the module | [Presentation](#presentation) |
| Create or change a Dashboard | [PPT Manage Dashboards](#ppt-manage-dashboards) |
| Choose the campaigns, dates and comparison scope | [Dashboard Scope & Filters](#dashboard-scope-filters) |
| Understand Apply versus Save | [Apply, Save, Clear and Reload](#apply-save-clear-and-reload) |
| Explore slides and chart data | [View Dashboard](#view-dashboard) |
| Export a presentation | [Generate PPT](#generate-ppt) |
| Review exported jobs or charts | [PPT Generation Jobs](#ppt-generation-jobs) / [Charts Panel](#charts-panel) |
| Resolve empty charts or preparation problems | [Troubleshooting](#troubleshooting) |

## Before creating a Dashboard

1. Open the correct workspace and process the required CDR types.
2. Create or import a compatible **NSA/SA Report Template** in Workspace Config.
3. For Multivendor Comparison, persist Vendor mappings first.
4. Open **PPT Dashboards**.

Any user with workspace access can manage Dashboard definitions. **user-editor**, **admin** and **super-admin** can also open **Edit PPT Template** and **Auto-Calculated Fields** from the viewer.

> [!TIP]
> For a first comparison: create a Dashboard (it compares the newest two campaigns of its NR Mode), choose its Scope, Campaign and other filters, apply them, then open **View Dashboard**. Inspect the charts before generating a PPT.

Dashboards use the same template schema and renderer as Reporting. Detailed template authoring is covered in [Workspace Config → Report Template reference](workspace-config.md#report-template-reference).

## PPT Manage Dashboards

### Create a definition

1. Enter **Dashboard name**.
2. Select **NR Mode** and a compatible **Template**.
3. Click **Create Dashboard**. The saved definition opens in Dashboard Scope & Filters.

Names are unique within each NR Mode: an NSA and an SA Dashboard may share a name. The library sorts NSA first, then by name.

An existing or imported Dashboard **RF Quality (RSRP & SINR)** can use the workspace template **NSA - RF Quality (RSRP & SINR)**, with separate LTE and NR RSRP/SINR CDF, average, distribution, threshold and quality-map slides for Data, Voice and Speech, followed by the NSA NetCheck black-logo closing slide. Each chart family starts with an All CDR types slide pooling valid Data, Voice and Speech observations, followed by the separate types; LTE and NR remain separate. CDF slides use a two-by-two layout with LTE and NR above their contour histograms (5 dB RSRP bins; 1 dB SINR bins). Histograms show percentages per series, match CDF colours and campaign widths, and retain multivendor line patterns; red-to-green background bands match the quality-class slides. Grouped-bar histogram slides follow each CDF/contour slide for All CDR types, Data, Voice and Speech. Their `Title + 2 rows + dynamic columns + comments down` layout and `Dynamic Columns Field = Operator` create one column per selected Operator on the same slide, with LTE above NR and comments beneath. Every bin has one bar per Campaign, ordered oldest to newest: the newest uses the Operator colour and older Campaigns use progressively lighter shades. Percentages use the same valid-sample denominator and bin widths as the contour histograms. NR shares use valid NR measurements and do not measure availability across the entire route. Its Campaign is **Latest 2 campaigns**, so it uses the CDRs of the newest NSA campaigns; edit or delete it like any other Dashboard. See [Network Insights](network-insights.md#rf-quality-template-and-dashboard).

### Row actions

| Action | Effect |
| --- | --- |
| **View Dashboard** | Open the interactive slide viewer |
| **Open Filters** | Open the Dashboard's dataset and filter controls |
| **Generate PPT** | Open the export selection dialog |
| **Duplicate** | Create an independent definition |
| **Export Dashboard** | Download a versioned ZIP accepted by Admin Import |
| **Delete** | Remove the definition after confirmation; only admins, super-admins and the user who created the Dashboard delete it |

**Close** leaves the active definition without deleting it. Deleting a Dashboard does not delete its CDRs, template or generated PPT jobs.

### Change name, NR Mode or template

Edit the name in the table and confirm with the green check. NR Mode and Template have their own selectors.

> [!WARNING]
> **Changing NR Mode or Template invalidates the prepared charts.** The application rebuilds them using the compatible template. An NR Mode change sets the Campaign filter to the newest campaigns of the new mode (the campaigns of the other mode do not apply); a template-only change keeps the Campaign.

The Scope, date settings, other filters, custom fields and comments are preserved. Only CDRs of the active NR Mode participate.

### Session and unsaved changes

The browser remembers the last open Dashboard and page position during the authenticated session. The main filter panel starts collapsed for a new session; its open/closed state is remembered while that session remains active.

Leaving with unsaved Scope, date or filter changes requires **Save Filters**, **Discard** or **Cancel**; after **Save Filters** nothing is left unsaved or unapplied, also while the saved filters are still being applied (the Dashboard is prepared), so closing the filters, opening the viewer or leaving asks nothing. Management-only name, NR Mode and Template inputs do not trigger false filter warnings.

Logging out clears temporary open-Dashboard, preview and scroll state. Saved definitions remain in the workspace.

## Dashboard Scope & Filters

**Open Filters** places this panel below the selected Dashboard row. Opening another Dashboard moves it to that row; **Close Filters** removes it.

In the viewer, **Dashboard Filters** opens the same controls in a floating panel. Small screens also use the floating version when opening filters from the library.

### How the CDRs are chosen

A Dashboard has no CDR selector: the **Campaign** filter (the first Default Filter) and the Dashboard's NR Mode choose its CDRs. They are the CDRs of that NR Mode that the combined CDR tables include, for the chosen campaigns (every campaign when the Campaign filter is not restricted):

- the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains;
- or, when it was changed, the **In Combined?** choice of the CDR in Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

Besides the campaigns, the Campaign filter offers first four choices made again whenever the Dashboard is prepared or exported, so it follows the campaigns that arrive later: **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** (the one before the latest) and **All available campaigns** (every campaign of the NR Mode at that moment, also those that arrive after it is saved, unlike every campaign checked by hand). With a single campaign, Previous campaign chooses none. Each one stands alone: checking it clears the other one and the campaigns, checking a campaign clears it, and **Select All / None** checks or clears the campaigns only. A new Dashboard compares its **Latest 2 campaigns** (**Latest campaign** in Multivendor Comparison with Operator_Vendor), as its newest CDRs did before; changing the Scope or vendor comparison updates a Campaign that still has the default of the former one. CDRs without Campaign values are used when no campaign is chosen.

**CDRs Used**, below the Scope, lists by type (Data, Voice and Speech, each showing about three CDRs and scrolling the rest) the CDRs the current selection chooses, with their stage and campaigns (Weekly and Daily CDRs outlined). It follows every change of the NR Mode or filters at once, before they are applied, and says when the filters must be applied to use them. The Campaign, Operator, Vendor, Region, Cluster and City lists follow the selection the same way, and an open list stays open while values are checked.

Dashboards saved before chose their CDRs by hand: they take, once, the campaigns of those CDRs as their Campaign filter (keeping a Campaign filter they already had), and the Dashboards without saved CDRs (which used the newest ones) take **Latest 2 campaigns**, or **Latest campaign** for Multivendor Operator_Vendor.

### Dashboard Scope

| Scope | Comparison | Default Campaign |
| --- | --- | --- |
| **Operator Comparison** | Normalized Operator values | Latest 2 campaigns |
| **Multivendor Comparison** | Operator/vendor hierarchy | Latest 2 campaigns (Vendor Only), Latest campaign (Operator_Vendor) |

The Scope and vendor comparison are applied and saved with the filters. The viewer's Scope control asks for confirmation before rendering its charts again.

> [!IMPORTANT]
> **Multivendor requires mapped Vendors.** The workspace must have at least two distinct cached Vendors, and the chosen CDRs must satisfy the mapping/comparison requirements. A single-vendor selection cannot produce a Multivendor comparison.

NR Mode follows the shared reporting rule: Voice/Speech sessions are classified as NSA/SA; valid Data attempts remain available even when a sample RAT records a fallback. Use the **RAT** filter for a narrower technology selection.

**Select Comparison Scope** shows **Vendor comparison** beside Scope when Multivendor Comparison is chosen. Vendor Only (All Operators Combined) is first and is the default when entering multivendor scope.

### Dates

**Date from** and **Date to** open the Default Filters and are applied and saved with them.

| Date setting | Meaning |
| --- | --- |
| **Oldest** | Resolve the first available date from the chosen CDRs during preparation |
| **Newest** | Resolve the last available date from the chosen CDRs during preparation |
| A chosen calendar day | Use that fixed date |

**Use oldest** / **Use newest** restore automatic bounds. The fields display their resolved dates, such as `Oldest (2026-01-01)`. Date to includes the whole selected day. Navigating calendar months does not change the date until you select a day.

> [!TIP]
> Use automatic date bounds when you want the CDRs of new campaigns included without adjusting dates. Use fixed dates for a reproducible time window.

### Read the row counts

| Count | What it represents |
| --- | --- |
| **CDRs used** | Rows contributed by the chosen CDRs |
| **Filtered rows** | Rows remaining after dates and Dashboard filters |
| **Chart rows** | Rows remaining after that chart's template filters as well |

Without date or adaptive-filter restrictions, the ready summary reuses the effective Dashboard count so both agree. When the chosen CDRs hold only the chosen campaigns, the Campaign filter needs no restriction on their rows, so the selection keeps these known counts.

An empty chart can coexist with nonempty Filtered rows: its source type or chart-specific filters may exclude the remaining rows.

### Default filters and aliases

The default order is **Campaign → Operator → Operator_Vendor → Vendor_Operator → Vendor → Market → Region → Cluster → City → RAT → Session Type → Call Status** (Campaign first, after Date from and Date to, because it chooses the CDRs), and the City selector offers **Main Cities** first. **Operator_Vendor** filters the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` (both stay in sync) and **Vendor** the vendor alone, using cached per-CDR values. Vendor choices list real vendors first, followed by Ericsson (Mixed) (and the former Mixed Vendor), Mixed (non-Ericsson) (and the former Other Vendor), All Vendor(s), and operators without vendors labelled **Operator - All**. Operators without a vendor are stored as `Operator - All` in both columns. Every vendor filter, including PPT export, expanded charts and template filters, uses these columns; the former `Vendor_Only`, `Vendor V3` and `OP_Vendor` filter names are accepted as aliases, and operator-prefixed values in a Vendor filter are resolved to the vendor name using workspace operator aliases. The comparison mode still controls whether charts group by Operator_Vendor or by Vendor (All Operators Combined). Technology is not an adaptive filter because NR Mode belongs to the definition.

| Visible filter | Source columns in priority order |
| --- | --- |
| Region | `Region` → `G_Level_2` → `G Level 2` |
| City | `City` → `G_Level_4` → `G Level 4` |
| Campaign | `Campaign` → `campaign` |
| RAT | `RAT_A` → `RAT` → `Sample_RAT_A` |
| Call Status | `Call_Status` → `call_status` → `status` |

Aliases resolve per row: an empty higher-priority field falls back to the next column. Hover or keyboard-focus the filter to inspect its aliases.

Each multiselect supports search, individual values and **Select All / None**. City offers **Main Cities** first: saved as such (not as the cities of that moment), it is the Main Cities of Workspace Config whenever the Dashboard is prepared, exported or generated by a Reporting Job, so changing the Main Cities changes the Dashboard too (every city while the workspace has none). It stands alone: checking it clears the cities and checking a city clears it. Dashboards saved before with exactly the Main Cities of the workspace take the Main Cities choice once.

> [!NOTE]
> **The filters list the values of every CDR of the NR Mode and follow each other.** Campaign lists every campaign of the Dashboard's NR Mode (with the labels of the Campaign Maps), and Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster and City the values of the chosen CDRs, each with the labels of the Operator and Vendor Maps and only those the other filters leave: choosing Vodafone as Operator leaves in Vendor only the Vendors of Vodafone. A filter's own choice does not narrow its list. These lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table), read once when the CDR is processed (or, for older CDRs, in the background the first time they are needed), so filling them never reads the rows of the CDRs; until a CDR has them, its catalogue values are offered.

> [!CAUTION]
> **Selecting no values returns no rows.** Selecting all values removes the restriction. This differs from modules where an empty filter means “all”. Use Clear Filters to remove restrictions deliberately.

Selecting every value individually also makes the field unrestricted, even when only one value is available. An unrestricted field includes new values from later-added CDRs automatically and displays **All values**.

Applying or saving a changed Campaign reloads the choices of its CDRs. Menus stay open while selecting and close after pointer exit. Older truncated catalogues are completed from source rows.

### Additional Filters

1. Search **Select field to add new filter**.
2. Choose a CDR column or an applicable workspace Auto-calculated Field.
3. Use **Add Filter**, then select its values.

Values load against the current CDRs, dates and other filters without preparing the whole Dashboard. The circular **×** removes an additional filter or hides a default filter after confirmation; the field picker can restore a hidden default.

Auto-calculated Fields apply to their declared CDR types. They are materialized into the relevant combined CDR table when first needed.

### Apply, Save, Clear and Reload

| Action | Changes the current view | Persists defaults |
| --- | --- | --- |
| **Apply Filters** | Scope, vendor comparison, dates and filters | No |
| **Save Filters** | Scope, vendor comparison, dates, filters, additional and hidden fields, and applies them | Yes |
| **Clear Filters** | Removes every restriction but the Campaign, which returns to its default (Latest 2 campaigns) | No |
| **Reload Saved Filters** | Restores the saved Scope, dates and filters | No |

**Apply Filters** and **Save Filters** are enabled as soon as a filter changes, also while the Dashboard is being prepared (when it opens, after its NR Mode changes or while other filters are applied): the new preparation replaces the one running.

> [!NOTE]
> **Apply is temporary; Save changes the Dashboard defaults.** You can preview or export an applied selection without saving it. Returning to an equivalent prepared selection reuses its cached charts.

If **View Dashboard** or **Generate PPT** encounters unapplied filter edits, choose:

| Dialog action | Outcome |
| --- | --- |
| **Apply Filters and Continue** | Prepare the edited filters, then continue |
| **Discard and Continue** | Restore the last applied filters, then continue |
| **Save and Continue** | Save, prepare and continue |
| **Cancel** | Leave the operation unchanged |

The Scope and dates are part of the filters, so they follow the same choice.

## Preparation lifecycle and cache

### What happens while preparing?

Preparations run in the background and the browser follows progress. A new foreground request replaces the same user's previous request; stale responses are ignored. An equivalent cached selection restores without recalculation.

The viewer opens immediately with a yellow **Preparing Dashboard dataset** card until its requested slides are ready. User-requested tasks appear in the floating task card and can provide **Interrupt task**.

| Status | Meaning |
| --- | --- |
| **Checking Cache** | Waiting for the server's cache status |
| **Pre-Caching Universe n/m** | Preparing reusable universe n of m |
| **Waiting** | Background pre-caching is queued or paused |
| **Loading data / Rendering** | Foreground preparation is active |
| **Data Cached · Charts n/m** | Every reusable universe is prepared; n of the m charts of the default universe are rendered, and the rest render when viewed or while the application is idle |
| **Rendering Charts n/m** | The background worker is rendering this Dashboard's charts |
| **Ready** | Every reusable universe is prepared and every chart of the default universe is rendered |

The chart counts refer to the default universe (the CDRs of the Dashboard's saved Campaign) in the Dashboard's saved comparison mode.

Open Filters, View Dashboard and PPT export remain available during background pre-caching.

### Background pre-caching

The library can prepare up to five universes: every campaign, and the newest one, two, three and four campaigns (their CDRs chosen as always). These use the Dashboard's NR Mode, saved scope/filters/template and automatic dates; duplicate universes are skipped.

One background worker handles one Dashboard at a time, in creation order (oldest first). Foreground preparation and PPT export pause this low-priority work at its next step, so opening a Dashboard never waits for another Dashboard's pre-caching; the work resumes afterward. An incompatible universe is skipped until the workspace data changes.

> [!TIP]
> You do not need to wait for every background universe to finish. Opening or exporting a Dashboard prepares the requested universe if it is not already reusable.

When nobody has used the application for two minutes, the same worker also builds the charts of each Dashboard's default universe (the CDRs of its saved Campaign) as **Operator Comparison** and as **Multivendor Comparison** with both **Vendor Only** and **Operator - Vendor**, and stores them as ready Canvas models. Modes that are not available, for example without mapped Vendors, are skipped. It then caches the CDR columns these charts read for every ready CDR of the Dashboard's NR Mode, newest first.

Opening a Dashboard or switching its comparison mode then shows the stored charts immediately. Changing the Campaign, dates or filters recalculates the charts from the cached columns without reading the CDRs again. This work stops between charts and between CDRs as soon as anyone uses the application, and continues after the next quiet period. The charts of a workspace that is closed wait until it is opened again, so they never delay those of the open workspace.

### What Clear cache removes

Combined CDR tables remain the source for filters and chart data. Selection records keep counts, facets and reproducible predicates; the cache does not copy CDR rows into a separate projection database.

Dashboard charts read the materialized combined CDR tables through a per-CDR column cache. Each column a chart needs is read from SQLite once per CDR, together with the Dashboard filter columns (the default filters, the Dashboard's custom fields and the event date). Any combination of CDRs, dates, filters and comparison mode is then assembled in memory without querying the CDRs again. `CDR-All` pools the Data, Voice and Speech tables without rereading the original uploaded files.

Preparing a changed universe also counts its rows from these cached filter columns, and reuses the distinct filter values of each CDR until that CDR changes, instead of reading the CDRs again. The assembled rows are exactly the rows SQLite returns, with the same values and types. Maps, scatter plots, tables and chart data views also keep SQLite's row order. When SQLite would return them in an order the cache cannot reproduce, for example while filtering a single City, those charts read SQLite directly. Charts reading the same fields share one read, and charts with the same source, filters and measure share one filtering pass.

`.dashboard-data-cache` holds derived preview manifests, Canvas models, the per-CDR column cache and legacy image artifacts. Their keys include dataset revisions, selection, scope and renderer version, so other sessions, restarts and PPT exports reuse them until the CDRs change. The column cache keeps up to 8 GB on disk and 1 GB in memory by default, removing the least recently used CDRs first. `DRIVETEST_ANALYZER_COLUMN_CACHE_DISK_MB` and `DRIVETEST_ANALYZER_COLUMN_CACHE_MEMORY_MB` change these limits. Older-version artifacts are removed when a workspace opens.

> [!WARNING]
> **Workspace Clear cache cancels active user-requested work and removes derived cache only.** It preserves Dashboard definitions, combined CDRs, templates and generated jobs. Nothing rebuilds automatically until requested again.

Canvas models are created when a chart is viewed, refreshed or requested for PPT. The charts of the open slide are calculated first and appear as each one is ready. After they load, nearby slides silently prefetch one chart at a time in the order next, previous, two ahead, two behind. A prefetch waits while the charts of a newly opened slide are calculated, so moving to another slide never queues it behind prefetched charts. Opening an individual chart uses the chart sequence instead. Closing the viewer stops scheduling further work.

## View Dashboard

Open **View Dashboard** from the library or filter panel. It does not expand the main filters panel automatically; use **Dashboard Filters** for the floating controls.

### Read the header

The viewer preserves the template's 16:9 layout and uses approximately 96% of the viewport. Its header identifies NR Mode, Dashboard and slide position.

- Slide titles and golden-yellow subtitles display in capitals.
- Campaigns, Scope, Regions and Cities identify the applied selection.
- Export snapshots show the selection captured by that PPT job.

Campaign labels are compact, such as **2026-Q2**, **2026-Q2-NSA** or **2026-Q2-SA** (see [Campaign ordering](technical-considerations.md#campaign-ordering)). Older CDRs may populate cached campaign labels a few seconds after first opening.

### Slides and navigation

| Control | Use |
| --- | --- |
| Slide selector | Jump to a template slide; searchable choices show the number, a purple title and a teal subtitle separated by a bold ● |
| Slides at the left | Every slide in small, as in the presentations of the [Help](help.md#presentations): the covers and transitions as in the viewer and the charts of the others once calculated, with their number and title; the slide shown is marked, and choosing one shows it (on wide screens; phones keep the slide selector) |
| **Presentation**, **First / Previous / Next / Last** | Below the slide and its comments: play the slides or move through them |
| Keyboard and wheel | ← ↑ Page Up go back and → ↓ Page Down (or Space) go forward, Home and End go to the first and last slide, when focus is outside editable controls; the wheel over the slide goes to the previous or next slide, one per turn |
| **Scope** | Switch Operator/Multivendor after confirmation |
| **Dashboard Filters** | Edit the live selection in a floating panel |
| **Generate PPT** | Export the selection |
| **Refresh Dashboard** | Refresh the Dashboard preparation |

**Theme**, at the start of the floating section bar of the page, colours the charts and the slide titles of the viewer and of the Dashboard PPTs with the colour themes of [Scoring & GAP Analysis](scoring-gap-analysis.md) (**Ericsson** by default, **NetCheck**, **Umlaut**, **Vodafone**, **Midnight**, **Paper** and **Heatmap**): the charts take its font and its colours for text, axes, grid lines, table headers and alternate rows (the colours of operators, vendors and thresholds stay as they are), and the slide title and subtitle of the viewer (still in capitals) and the titles and subtitles of the content slides of the PPT take its title style, the part that tells the slide apart in its focus style; **Midnight** paints the charts and the content slides night blue (with the logos in white) and turns their tables, text and comments light on dark. Title and Transition slides keep the template look. Each user keeps one theme per workspace for every themed module (choosing it here chooses it in Scoring & GAP Analysis, Network Insights and CDR Analysis too); changing it restyles the viewer and redraws the charts at once, is kept for the next visit and the Dashboard PPTs generated afterwards (also from Reporting Jobs), and is recorded in the App Events log.

Changing Scope renders the charts again with the Dashboard filters (a Campaign that still has the default of the former Scope takes the default of the new one). Multivendor is unavailable when the workspace has fewer than two Vendors.

Title and Transition slides preserve the template text and look as in the exported PPT: the Vodafone-Three red with the Ericsson mark, the Vodafone-Three and Ericsson logos at the top right, light titles with the room of two lines and the yellow subtitle below them. A title cover shows Campaigns above its decorative divider, with Scope, Regions and Cities beneath it, in white with bold labels; each Title or Transition slide after it shows its counter (01, 02…), as in the PPT. An End Slide shows the Ericsson mark and name centred on white, as the closing slide of the PPT, without counter. Chart rows preserve template order and placeholder geometry.

In grids with three or more rows or four or more columns, each chart's title appears as text above the chart, in the viewer and in the PPT, so it stays readable in small cells. Dynamic grids show the row or column value (for example the Operator) in bold before the title, such as **EE** · LTE RSRP histogram.

Axis labels and aggregation headers are never truncated, in the viewer or in the PPT. Each axis level wraps onto two lines, uses a smaller size or turns vertical, and the chart reserves the room it needs.

Layouts ending in **comments right** place comments beside the charts; **comments down** places them below. Layouts without comments use the full chart area. Narrow screens wrap actions and adapt navigation to the available space.

### Live and expanded chart controls

Hover or focus a chart for **Dataset**, **Expand**, **Refresh**, **Zoom** and **Chart Definition**. The controls also remain accessible on touch devices.

| Gesture / action | Result |
| --- | --- |
| **Expand** or double-click | Open the focused chart in the expanded viewer |
| **− / + / 1:1** | Zoom between 100% and 400%, or reset |
| Ctrl/Cmd + wheel (or a pinch of the touchpad) | Zoom the chart under the pointer, at the pointer |
| Drag a rectangle at 100% | Zoom into the selected plot area |
| Drag when zoomed | Pan the chart |
| Direction arrows when zoomed | Move the camera; arrows disable at boundaries |
| Click a legend entry | Hide or show that value in every slide of the Dashboard; a hidden entry stays faded and struck through |
| Right-click a legend entry or an axis label | **Keep only**, **Hide** or **Show**, **Hide All** and **Show All** for that legend or axis level; an axis menu also lists its hidden values, each opening a **Show** submenu when the pointer moves over it |

Hiding a value applies to the whole Dashboard. Every series, bar, stacked segment, row, column and category where the value appears, at any aggregation level, disappears and the chart closes the gap: hiding Operator VF_SA also hides each VF_SA Campaign, for example. In dynamic grids, the cards of a hidden value (such as an Operator) leave the slide and the remaining cards fill a smaller grid. A slide whose cards are all hidden offers **Show hidden values** and is left out of the PPT.

The legend state lasts for the browser session and also applies in the expanded viewer. **Generate PPT** exports the charts as you see them, and the PPT job's viewer shows the same state. Relaunching a PPT job keeps the state it was created with. In Network Insights, clicking a legend entry hides or shows it in that chart only.

The slide of the viewer, each of its charts and the chart of the expanded viewer download as a PNG image or copy to the clipboard as a screenshot from the floating buttons at their top right corner, beside the controls of the chart (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)); so do the Charts Panel and each of its thumbnails. App Events records each one as `export_dashboard_image`, with the slide or the Dashboard and date of the PowerPoint job.

The expanded viewer retains Dashboard filters, chart navigation and a red Close control. Compact portrait/landscape layouts fit navigation and the chart to the viewport; the Comments drawer stays accessible at the bottom.

### Edit a chart definition

The **Chart Definition** tab uses the same editor in live and expanded view:

| Action | Scope |
| --- | --- |
| **Apply** | Change the current preview |
| **Update Template** | Save the definition to the Report Template row |
| **Edit PPT Template** | Focus the exact generating row in the template editor |

Saving the template refreshes the Dashboard. Closing it unchanged preserves the current preparation. Template/calculated-field editing actions require **user-editor**, **admin** or **super-admin**.

> [!IMPORTANT]
> **Updating a Report Template is a saved configuration change.** Use Apply to inspect a temporary preview before committing the chart definition to its template.

The [Report Template reference](workspace-config.md#report-template-reference) describes supported chart types, filters, aggregations, legends and layouts.

### Filtered Chart Dataset

**Dataset** opens rows after both the Dashboard filters and that chart's template filters. It is not every row of the chosen CDRs.

The dataset viewer provides:

- Server-side pages of 100 rows, with First/Previous/Next/Last.
- Excel-style value filters across the complete chart dataset.
- A filtered-row count, **Clear N filters** and full CSV download.

Active columns are highlighted. Value choices respond to the other column filters; pagination and CSV retain the same selection.

> [!TIP]
> Open Dataset on an unexpected chart to see exactly which rows contributed. Compare its row count with Filtered rows before changing the chart formula.

### Comments, Presentation and floating tools

| Tool | Behavior |
| --- | --- |
| Slide comments | Add, edit or remove; Enter or leaving an edit saves immediately |
| **Presentation** | Advance every 3, 5, 10 or 15 seconds, with Fade, Slide or no transition |
| Pause/Resume and Stop | Floating controls remain available in Presentation mode |
| **Dashboard Filters** | Change applied selection without automatically saving defaults |
| **Auto-Calculated Fields** | Open the shared workspace manager for permitted editors |

Manual navigation stops Presentation. Its settings adapt to compact landscape screens. Backdrop/Escape closes unchanged dialogs; pending Filters, Template or calculated-field edits require a decision first.

## Generate PPT

### Choose the export inputs

Open **Generate PPT** from the library, filter panel or viewer. **Select Dashboard Scope and Filters** controls the export's exact selection, which can differ from saved defaults.

| Export subpanel | Settings |
| --- | --- |
| **Scope** | Scope (and vendor comparison) |
| **Main Dashboard Filters** | Campaigns (which choose the CDRs) and the CDRs they choose, the dates below them (the whole width), then Operators and Vendors, Regions and Cities |
| **Show All Filters** | Reveal the remaining main filters and Additional Filters |

The export has no CDR selector: **Campaigns** lists every campaign of the Dashboard's NR Mode, with **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** and **All available campaigns** first (each one alone), starts with the Dashboard's Campaign and lists below it, by type, the CDRs it chooses now; both appear as soon as the dialog opens. The other choices load from those CDRs and start with saved filter values, or all available values when unrestricted or no saved values remain available.

Cities offers **Main Cities** first, exported as the Main Cities of the workspace. Changing campaigns or dates preserves selected values still available; an All selection includes new values. The browser remembers the dialog's last Scope, Campaigns and dates per Dashboard/user.

### Save defaults only when intended

| Action | Effect |
| --- | --- |
| **Generate PPT** | Export the dialog's selection |
| **Save Filters** | Also persist its Scope, dates, Campaigns and other filters in the Dashboard |

Save Filters is enabled when the dialog differs from the saved defaults (the vendor comparison counts only in Multivendor Comparison). A complete value selection equals an unrestricted field; saved values absent from the selected CDRs are ignored.

> [!IMPORTANT]
> **Export selections take precedence for that job.** You can export applied or dialog-specific filters without saving them as Dashboard defaults. The job's Filters snapshot records what was exported.

If required, the export prepares the CDRs of its campaigns without waiting for library background pre-caching.

### Presentation contents and files

The PPT preserves template slides, layouts, chart proportions, titles, legends and saved comments. Chart subtitles use blue text; Title/Transition subtitles retain the template's yellow accent.

Title covers match the viewer: Campaigns appear in orange above the divider; Scope, Regions and Cities appear beneath in green, cyan and pink. Chart subtitles use normal letter spacing.

Generated PPTs, chart PNGs, tooltips and Canvas assets are stored under **output/reports/dashboards**.

| Filename part | Contents |
| --- | --- |
| Prefix | `yyyymmdd_HHMMSS` |
| Definition | NR Mode, Dashboard name and Scope |
| Geography | Selected Regions joined by ` + `, or All Regions |
| Multiple campaigns | Campaigns joined by `_vs_` at the end |

Operators, Vendors and Cities remain in the job Filters snapshot and are omitted from filenames. Long names are shortened only for filesystem limits.

## PPT Generation Jobs

Jobs continue on the server after you leave the page. The table records ID, creator, local date/time, NR Mode, Dashboard, Scope, filters, slide/chart counts, status and progress.

| Action | Availability / purpose |
| --- | --- |
| **Download PPT** | Download an available completed presentation |
| Chart actions | Open or download generated charts |
| Stop / retry / relaunch | Manage work when the job's state permits |
| Filter action | Inspect sources, dates, campaigns and filters in a tooltip/dialog |
| Delete / **Delete All PPTs** | Remove jobs/files; requires user-editor, admin or super-admin |

Excel-style header filters search job columns. The filter snapshot groups CDRs by Data/Voice/Speech and shows Campaigns above Operators.

> [!NOTE]
> **All Operators / Vendors / Regions / Cities refers to the job's selected CDRs.** Other workspace CDRs do not expand that selection. Saved values absent from those CDRs are not listed.

## Charts Panel

### Find an exported chart

1. Filter by NR Mode, Dashboard, Template, Scope, Region or City.
2. Select a **PowerPoint Job**.
3. Open a chart card in the expanded viewer, or use **View Filters** to inspect the snapshot.

Each filter offers only selections from jobs matching the other active filters. Choices describe complete exported selections. A job with seven cities contributes one City choice containing those seven cities; All Cities/All Regions appears only for jobs exported with those selections.

The job selector identifies its local date/time, NR Mode, Dashboard, Scope and recorded geography. Long lists expose their full values on hover. Polling loads the newest matching completed job.

### Live Dashboard versus saved snapshot

| View | Selection |
| --- | --- |
| **View Dashboard** | Current applied Dashboard inputs |
| **Charts Panel** | The generating PPT job's captured template and inputs |

Stored Canvas models repaint with the current renderer. Legacy jobs without models keep their PNG. The expanded viewer and Filtered Chart Dataset remain available.

> [!IMPORTANT]
> **Completed exports are immutable snapshots.** Dashboard Filters are hidden in Charts Panel. View Filters shows the exported selection; changing a live Dashboard does not rewrite that job.

Permitted editors can open the generating template and Auto-Calculated Fields without changing the saved snapshot.

## Portability and maintenance

**Export Dashboard** creates a versioned ZIP accepted by Admin Import; imports also accept legacy standalone JSON definitions. A compatible destination template is required.

| Included in the definition | Not copied by Dashboard definition export |
| --- | --- |
| Name, NR Mode and template association | Source CDRs |
| Scope, dates, saved filters (Campaign included), hidden/additional fields | Prepared cache files |
| Slide comments | Generated presentation assets |

A Dashboard chooses its CDRs from its NR Mode and Campaign in the workspace where it is opened, so an imported Dashboard uses the CDRs of the destination with the same campaigns (Latest campaign, Latest 2, 3 and 4 campaigns and Previous campaign, among its newest ones). Dashboards exported by earlier versions with CDRs of their own take the campaigns of the CDRs of the destination with the same name and type, or else its newest two campaigns; check the inputs after import.

Dashboards have their own Admin export/import/transfer/backup/restore component: an import or transfer replaces the Dashboards the destination has (found by their identity, so one renamed on the source server is renamed there too, or by name and NR Mode) and adds the others, and so does a restore (see [Matching and creators](administrator-config.md#matching-and-creators)). Full Workspace and Full Environment include definitions from selected workspaces, with Dashboards listed after Application Config.

> [!TIP]
> Verify the template and Campaign after moving a Dashboard to another workspace. Its CDRs do not travel with it: it uses the CDRs of the destination for its campaigns.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| View Dashboard or Generate PPT is disabled | Inspect its status badge and explicit preparation task |
| A filter has no choices | Verify source field/aliases and whether other filters leave matching rows |
| Chart says no CDR is selected | Choose a Campaign with a CDR of the type that chart needs, or check its In Combined? choice in Workspace |
| Filtered rows are zero | Check dates and empty value selections; use Clear Filters to remove restrictions |
| Chart is empty with nonzero rows | Check its source type, template filters, NR Mode and chart Dataset |
| Multivendor is unavailable | Check at least two Vendors and persist mappings for selected CDRs |
| Preparation failed or stays queued | Inspect App Logs and retry; clear derived Dashboard cache only if invalid |
| Viewer and old export differ | Compare applied live inputs with the completed job's saved snapshot |

> [!WARNING]
> Clear cache is a recovery action for derived artifacts, not a substitute for fixing missing source data, Vendor mappings or an invalid template. Inspect the cause first.

> [!NOTE]
> **Viewer comparison:** In the Dashboard viewer, selecting **Multivendor Comparison** reveals **Vendor comparison** to the right of Scope. Choose **Vendor Only (All Operators Combined)** to pool operators sharing a vendor, or **Operator - Vendor** to keep their results separate. Changing this selector renders the Dashboard again immediately. Switching into multivendor scope defaults to Vendor Only; saved Dashboards retain their saved comparison. Use **Save Universe** to persist the choice.

> **Vendor comparison:** When **Report type** is **Multivendor Comparison**, the **Vendor comparison** selector appears to its right. **Vendor Only (All Operators Combined)** is the first and default option when opening the export dialog; it pools selected operators using the same `Vendor` value. Choose **Operator - Vendor** to keep each operator separate. Campaigns remain separate. The job retains this choice for retries. Dynamic vendor grids use up to six columns per slide and keep operators of the same vendor together where possible.

### Vendor-only report ordering

For **Vendor Only (All Operators Combined)**, web charts/tables and PowerPoint reports list actual vendors alphabetically, then Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operator-only identities labelled **Operator - All**, and finally Mixed (non-Ericsson). This order also applies to dynamic chart grids. Mixed/Other groups remain visible unless an explicit template filter excludes them. Vendor mapping persists `Operator - All` in `Operator_Vendor` and `Vendor` for operators without an assigned vendor. Existing values without the suffix remain compatible.

In multivendor charts, operator-only identities such as **EE - All** retain the colour assigned to that operator in Operator mappings. This applies to web and newly generated PPT charts; the display suffix does not create a new colour identity. Real vendors retain their configured vendor colours.

The default Campaign is **Latest 2 campaigns** for **Operator Comparison** and multivendor **Vendor Only**, and **Latest campaign** for multivendor **Operator - Vendor**. Changing the vendor comparison updates a Campaign that still has the default; a chosen Campaign is retained.
