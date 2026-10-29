# PPT Designer

Build an interactive Design (a PPT Design) from processed Data, Voice and Speech CDRs, following a PPT Template of the workspace or starting blank. Apply one dataset selection to its slides, explore the charts, change them on screen in the Designer, then export the result to PowerPoint. The PPT Templates themselves are managed and edited here too.

> [!NOTE]
> **A Design is a saved definition, not a copy of your data.** It stores its template, Scope, dates, filters, the values of the template parameters, comments and what it changes of its template's slides; its CDRs are chosen from its NR Mode and Campaign filter each time it is prepared. Source CDRs and generated caches remain separate.

## Presentation

The presentation **PPT Designer** sums the module up. Interactive Designs from Report Templates: one selection of CDRs on every slide, live charts to explore and PowerPoint exports generated in the background. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
ppt-designer
```

## Choose your task

| I want to… | Go to |
| --- | --- |
| Watch the presentation of the module | [Presentation](#presentation) |
| Create or change a Design | [PPT Designs](#ppt-designs) |
| Choose the campaigns, dates and comparison scope | [PPT Scope & Filters](#ppt-scope-filters) |
| Understand Apply versus Save | [Apply, Save, Clear and Reload](#apply-save-clear-and-reload) |
| Explore slides and chart data | [View PPT](#view-ppt) |
| Change slides, layouts and charts on screen, for this Design or for its template | [Designer](#designer) |
| Choose the city, threshold or other values of a template's parameters | [Template parameters](#template-parameters) |
| Import, create or edit PPT Templates | [PPT Templates](#ppt-templates) |
| Write a template by hand: its columns, chart types and layouts | [Report Template reference](#report-template-reference) |
| Export a presentation | [Generate PPT](#generate-ppt) |
| Review exported jobs or charts | [PPT Generation Jobs](#ppt-generation-jobs) / [Charts Panel](#charts-panel) |
| Resolve empty charts or preparation problems | [Troubleshooting](#troubleshooting) |

## Before creating a Design

1. Open the correct workspace and process the required CDR types.
2. Create or import a **Report Template** in **PPT Templates**, at the top of the PPT Designs library. A template serves the CDRs of any NR Mode.
3. For Multivendor Comparison, persist Vendor mappings first.
4. Open **PPT Designer**.

Any user with workspace access can manage PPT definitions. **user-editor**, **admin** and **super-admin** can also open **Edit PPT Template** and **Auto-Calculated Fields** from the viewer.

> [!TIP]
> For a first comparison: create a Design (it compares the newest two campaigns of its NR Mode), choose its Scope, Campaign and other filters, apply them, then open **View PPT**. Inspect the charts before generating a PPT.

Designs use the same template schema and renderer as Reporting. Detailed template authoring is covered in [Report Template reference](#report-template-reference).

## PPT Designs

### Create a definition

1. Enter its **PPT Name** (**My New PPT Design** is offered).
2. Select the **NR Mode** of the CDRs it reads (**NSA**, **SA** or **NSA & SA** for both, see [NSA & SA in one Design](#nsa--sa-in-one-design)) and a **PPT Template**. When the NR Mode leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), their tests are left out of the Design, and its CDRs used and the viewer, beside its Campaign and Scope, name them (*Out of scope: SA · Three*). Any template serves every NR Mode: its titles name the NR Mode of the Design where they write `{NR Mode}` (NSA, SA or NSA & SA) or `{NR Mode Name}` (Non-Standalone, Standalone or Non-Standalone & Standalone).
   The button beside **PPT Template** opens the **gallery** of the templates of the workspace: a card for each one with its first slides in small, as it lays them out (the picture of each chart type in its place, the covers and transitions in colour), how many slides and charts it has and **Default** on the default one, and **None — blank PPT** first; a click on a card chooses that template (**Esc** or **×** leaves the choice as it was).
3. Click **Create PPT Design**. The saved definition opens in PPT Scope & Filters; with **None — blank PPT** as its PPT Template, it opens in its [Designer](#designer) instead, with only its cover, where its slides are added (it follows no template; **More → Save as template…** makes one of it). **Import PPT Design** imports a PPT Design exported before.

Names are unique in the workspace, whatever the NR Mode each Design reads: an NSA and an SA Design of the same template need names of their own (for example **NSA - NetCheck CDR Report** and **SA - NetCheck CDR Report**). The library sorts NSA first, then by name.

### NSA & SA in one Design

A Design of NR Mode **NSA & SA** reads the CDRs of both NR Modes, so a slide can put NSA and SA charts side by side and a chart can draw NSA and SA series together. Every row of the combined CDR tables keeps the NR Mode of its CDR in the **NR Mode** field (NSA or SA), so the NSA and SA tests of an operator are never added together:

- **Campaign filters.** PPT Scope & Filters shows **Campaign (NSA)**, which chooses the NSA CDRs, and **Campaign (SA)**, which chooses the SA ones; each offers the campaigns of its NR Mode and its own Latest choices, resolved among them (for example Latest 3 campaigns in NSA and Latest campaign in SA). A Design saved without Campaign (SA), or generated by a Reporting Job, uses its Campaign filter for both NR Modes, each Latest choice among the campaigns of each NR Mode.
- **The NR Mode of a chart.** A template row keeps one NR Mode with the filter `NR Mode IN (SA)` (or `NSA`), and then reads only the CDRs of that NR Mode (an SA chart reads no NSA CDR); without it the chart reads every NR Mode the Design reads. The NR Mode of the Design decides: an NSA or SA Design only shows charts of its own NR Mode, and NSA and SA charts together need a Design of NSA & SA. In a Design that does not read the NR Mode of a chart, the chart says so instead of showing data, and its title names the NR Mode it shows where it writes `{NR Mode}`.
- **NR Mode in splits and legends.** **NR Mode** is a field of Rows Split, Columns Split, Legend and the Dynamic Rows/Columns Field (a dynamic grid can place the NSA chart above the SA one). A chart that reads both NR Modes and is split neither by NR Mode nor by Campaign (the SA campaigns name their mode, such as 2026-Q3-SA) gets NR Mode as the last level of the split that holds its legend, and of its legend.
- **Look of the series.** Each operator keeps its colour in both NR Modes: its SA series use a lighter tint of it, and SA lines are dashed when dashes do not already tell operators apart; the CDF campaign line widths are ranked inside each operator and NR Mode, so the newest NSA and the newest SA campaigns are both thick.
- **Fields of one NR Mode.** A chart that uses a KPI, filter or split field that only the CDRs of one NR Mode have shows a note naming the NR Mode without samples (*The SA CDRs have no Mean_Data_Rate: no SA samples.*), and the template editor warns about it.

The PPT file names and the viewer header name the NR Mode **NSA & SA**. Every workspace receives once the example template **FDFS DL (NSA & SA)** and its Design **NSA & SA - FDFS DL (NSA & SA)** (Latest 3 campaigns in NSA, Latest campaign in SA): a slide with the FDFS DL throughput CDF of NSA, that of SA and the FDFS DL transfer time of every campaign of both NR Modes.

An existing or imported Design **RF Quality (RSRP & SINR)** can use the workspace template **RF Quality (RSRP & SINR)**, with separate LTE and NR RSRP/SINR CDF, average, distribution, threshold and quality-map slides for Data, Voice and Speech, followed by the NSA NetCheck black-logo closing slide. Each chart family starts with an All CDR types slide pooling valid Data, Voice and Speech observations, followed by the separate types; LTE and NR remain separate. CDF slides use a two-by-two layout with LTE and NR above their contour histograms (5 dB RSRP bins; 1 dB SINR bins). Histograms show percentages per series, match CDF colours and campaign widths, and retain multivendor line patterns; red-to-green background bands match the quality-class slides. Grouped-bar histogram slides follow each CDF/contour slide for All CDR types, Data, Voice and Speech. Their `Title + 2 rows + dynamic columns + comments down` layout and `Dynamic Columns Field = Operator` create one column per selected Operator on the same slide, with LTE above NR and comments beneath. Every bin has one bar per Campaign, ordered oldest to newest: the newest uses the Operator colour and older Campaigns use progressively lighter shades. Percentages use the same valid-sample denominator and bin widths as the contour histograms. NR shares use valid NR measurements and do not measure availability across the entire route. Its NR Mode is NSA and its Campaign **Latest 2 campaigns**, so it uses the CDRs of the newest NSA campaigns; edit or delete it like any other Design. See [Network Insights](network-insights.md#rf-quality-template-and-design).

### Row actions

| Action | Effect |
| --- | --- |
| **View PPT** | Open the interactive slide viewer |
| **Edit Design** | Open the slide viewer in the [Designer](#designer), once the Design is prepared (users who can change Designs) |
| **Generate PPT** | Open the export selection dialog |
| **Duplicate** | Create an independent definition |
| **Export Design** | Download a versioned ZIP accepted by Admin Import |
| **Delete** | Remove the definition after confirmation; only admins, super-admins and the user who created the Design delete it |

**Close** leaves the active definition without deleting it. Deleting a Design does not delete its CDRs, template or generated PPT jobs.

### Change name, NR Mode or template

Edit the name in the table (column **PPT Name**) and confirm with the green check. NR Mode and **PPT Template** have their own selectors, independent of each other: the NR Mode chooses the CDRs the Design reads and keeps its template, and any template serves every NR Mode. A Design created blank shows **None — blank PPT**: choosing a template makes it follow that template, and its own slides are replaced by those of the template after a warning.

> [!WARNING]
> **Changing NR Mode or Template invalidates the prepared charts.** The application rebuilds them. An NR Mode change keeps the campaigns of an NR Mode the Design still reads (NSA to NSA & SA keeps the Campaign as Campaign (NSA)) and sets the others to the newest campaigns of the new mode (the campaigns of the other mode do not apply); the titles of the template name the new NR Mode. A template-only change keeps the Campaign.

The Scope, date settings, other filters, custom fields and comments are preserved. Only CDRs of the active NR Mode participate.

### Session and unsaved changes

The browser remembers the last open Design and page position during the authenticated session. The main filter panel starts collapsed for a new session; its open/closed state is remembered while that session remains active.

Leaving with unsaved Scope, date or filter changes requires **Save Filters**, **Discard** or **Cancel**; after **Save Filters** nothing is left unsaved or unapplied, also while the saved filters are still being applied (the Design is prepared), so closing the filters, opening the viewer or leaving asks nothing. Management-only name, NR Mode and Template inputs do not trigger false filter warnings.

Logging out clears temporary open-Design, preview and scroll state. Saved definitions remain in the workspace.

## PPT Scope & Filters

**PPT Filters**, at the top of the viewer of a Design, opens this panel over its slides; a Design just created, duplicated or imported opens in its viewer with it. The table of the Designs never opens the filters.

### How the CDRs are chosen

A Design has no CDR selector: the **Campaign** filter (the first Default Filter) and the Design's NR Mode choose its CDRs (with NSA & SA, Campaign (NSA) and Campaign (SA) choose those of each NR Mode). They are the CDRs of that NR Mode that the combined CDR tables include, for the chosen campaigns (every campaign when the Campaign filter is not restricted):

- the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains;
- or, when it was changed, the **Active?** choice of the CDR in Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

Besides the campaigns, the Campaign filter offers first four choices made again whenever the Design is prepared or exported, so it follows the campaigns that arrive later: **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** (the one before the latest) and **All available campaigns** (every campaign of the NR Mode at that moment, also those that arrive after it is saved, unlike every campaign checked by hand). With a single campaign, Previous campaign chooses none. None of them counts the [Flex campaigns](workspace-management.md#flex-campaigns) (local campaigns, complete but localised in one region, cluster or city, whose campaign or Campaign Maps label has the word Flex, such as `26-Q2-Flex`), nor does a Campaign filter without campaigns: a Flex campaign is used only when it is checked by hand. Each one stands alone: checking it clears the other one and the campaigns, checking a campaign clears it, and **Select All / None** checks or clears the campaigns only. A new Design compares its **Latest 2 campaigns** (**Latest campaign** in Multivendor Comparison with Operator_Vendor), as its newest CDRs did before; changing the Scope or vendor comparison updates a Campaign that still has the default of the former one. CDRs without Campaign values are used when no campaign is chosen.

**CDRs Used**, below the Scope, lists by type (Data, Voice and Speech, each showing about three CDRs and scrolling the rest) the CDRs the current selection chooses, newest campaign first, with their stage and campaigns (Weekly and Daily CDRs outlined). It follows every change of the NR Mode or filters at once, before they are applied, and says when the filters must be applied to use them. The Campaign, Operator, Vendor, Region, Cluster and City lists follow the selection the same way, and an open list stays open while values are checked.

Designs saved before chose their CDRs by hand: they take, once, the campaigns of those CDRs as their Campaign filter (keeping a Campaign filter they already had), and the Designs without saved CDRs (which used the newest ones) take **Latest 2 campaigns**, or **Latest campaign** for Multivendor Operator_Vendor.

### PPT Scope

| Scope | Comparison | Default Campaign |
| --- | --- | --- |
| **Operator Comparison** | Normalized Operator values | Latest 2 campaigns |
| **Multivendor Comparison** | Operator/vendor hierarchy | Latest 2 campaigns (Vendor Only), Latest campaign (Operator_Vendor) |

The Scope and vendor comparison are applied and saved with the filters. The viewer's Scope control asks for confirmation before rendering its charts again.

> [!IMPORTANT]
> **Multivendor requires mapped Vendors.** The workspace must have at least two distinct cached Vendors, and the chosen CDRs must satisfy the mapping/comparison requirements. A single-vendor selection cannot produce a Multivendor comparison.

Each row keeps the NR Mode of its CDR (its **NR Mode** field): a Design of an NR Mode reads every Data, Voice and Speech test of the CDRs of that NR Mode, whatever RAT or call mode it ran on (an EPS fallback call of an SA CDR is an SA test). Use the **RAT** filter for a narrower technology selection.

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
| **Filtered rows** | Rows remaining after dates and PPT filters |
| **Chart rows** | Rows remaining after that chart's template filters as well |

Without date or adaptive-filter restrictions, the ready summary reuses the effective Design count so both agree. When the chosen CDRs hold only the chosen campaigns, the Campaign filter needs no restriction on their rows, so the selection keeps these known counts.

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

Each multiselect supports search, individual values and **Select All / None**. City offers **Main Cities** first: saved as such (not as the cities of that moment), it is the Main Cities of Workspace Config whenever the Design is prepared, exported or generated by a Reporting Job, so changing the Main Cities changes the Design too (every city while the workspace has none). It stands alone: checking it clears the cities and checking a city clears it. Designs saved before with exactly the Main Cities of the workspace take the Main Cities choice once.

> [!NOTE]
> **The filters list the values of every CDR of the NR Mode and follow each other.** Campaign lists every campaign of the Design's NR Mode (with the labels of the Campaign Maps), and Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster and City the values of the chosen CDRs, each with the labels of the Operator and Vendor Maps and only those the other filters leave: choosing Vodafone as Operator leaves in Vendor only the Vendors of Vodafone. A filter's own choice does not narrow its list. These lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table), read once when the CDR is processed (or, for older CDRs, in the background the first time they are needed), so filling them never reads the rows of the CDRs; until a CDR has them, its catalogue values are offered.

> [!CAUTION]
> **Selecting no values returns no rows.** Selecting all values removes the restriction. This differs from modules where an empty filter means “all”. Use Clear Filters to remove restrictions deliberately.

Selecting every value individually also makes the field unrestricted, even when only one value is available. An unrestricted field includes new values from later-added CDRs automatically and displays **All values**.

Applying or saving a changed Campaign reloads the choices of its CDRs. Menus stay open while selecting and close after pointer exit. Older truncated catalogues are completed from source rows.

### Additional Filters

1. Search **Select field to add new filter**.
2. Choose a CDR column or an applicable workspace Auto-calculated Field.
3. Use **Add Filter**, then select its values.

Values load against the current CDRs, dates and other filters without preparing the whole Design. The circular **×** removes an additional filter or hides a default filter after confirmation; the field picker can restore a hidden default.

Auto-calculated Fields apply to their declared CDR types. They are materialized into the relevant combined CDR table when first needed.

### Apply, Save, Clear and Reload

| Action | Changes the current view | Persists defaults |
| --- | --- | --- |
| **Apply Filters** | Scope, vendor comparison, dates and filters | No |
| **Save Filters** | Scope, vendor comparison, dates, filters, additional and hidden fields, and applies them | Yes |
| **Clear Filters** | Removes every restriction but the Campaign, which returns to its default (Latest 2 campaigns) | No |
| **Reload Saved Filters** | Restores the saved Scope, dates and filters | No |

**Apply Filters** and **Save Filters** are enabled as soon as a filter changes, also while the Design is being prepared (when it opens, after its NR Mode changes or while other filters are applied): the new preparation replaces the one running.

> [!NOTE]
> **Apply is temporary; Save changes the PPT defaults.** You can preview or export an applied selection without saving it. Returning to an equivalent prepared selection reuses its cached charts.

If **View PPT** or **Generate PPT** encounters unapplied filter edits, choose:

| Dialog action | Outcome |
| --- | --- |
| **Apply Filters and Continue** | Prepare the edited filters, then continue |
| **Discard and Continue** | Restore the last applied filters, then continue |
| **Save and Continue** | Save, prepare and continue |
| **Cancel** | Leave the operation unchanged |

The Scope and dates are part of the filters, so they follow the same choice.

## Preparation lifecycle and cache

### What happens while preparing?

Preparations run in the background and the browser follows progress. A new request replaces the same user's previous request; stale responses are ignored. An equivalent selection prepared earlier in the session restores without recalculation.

The viewer opens immediately with a yellow **Preparing PPT dataset** card until its requested slides are ready. User-requested tasks appear in the floating task card and can provide **Interrupt task**.

| Status | Meaning |
| --- | --- |
| **Checking Cache** | Waiting for the server's status of the Design |
| **Loading data / Rendering** | The Design is being prepared or its charts rendered for a user |
| **Data Cached** | The open Design is prepared; its charts render as they are viewed |
| **Ready** | The Design has CDRs to show; it is prepared when it is opened, or by the warm-up |
| **Data needed** | No CDR matches the Design's selection |

View PPT, its PPT Filters and PPT export are available at any time.

### Warm-up while the server is idle

After 5 minutes without anyone using the application (and with no other background work), the server **warms up** the open workspace: one after another, every PPT Design, and every PPT Template as PPT Templates → **Edit** opens it (with the NR Mode and Campaign of each user who opened one, else NSA and Latest 2 campaigns), is prepared and the models of its charts are worked out and kept in the cache folder of the workspace, so after a restart they open at once with their charts drawn. A chart keeps its model while the chart, its CDR selection and the mappings stay the same: a Design or template that changed works out again only its changed charts, and one whose CDRs or filters changed all of them; with nothing changed since the last warm-up, there is nothing to do. **Warming up PPT Designs** shows in the floating task card with the Design or template and the chart it is at, and its **Interrupt task** button stops it after the chart it works out. It also pauses by itself as soon as someone uses the application or other background work starts, and it goes on from where it was the next time the server is idle (what it kept is not worked out again). Charts a selection cannot draw are left to the viewer, which says why, and Designs without CDRs of their selection are skipped. App Events record each warm-up (`design_warmup_started`, `design_warmup_finished` with its charts worked out and kept and the size of the cache folder) and each stop (`stop_design_warmup`).

Opening, refreshing or exporting a Design that was not warmed up (or whose CDRs, filters or template changed since) prepares it from the [columnar copies](workspace-management.md#columnar-copy-of-the-cdrs) of its CDRs. The charts that aggregate their rows (CDFs, histograms, averages, stacked and grouped bars) are grouped by DuckDB on the copies, each distinct combination of the chart's fields once with its number of rows; maps, scatter plots, tables and chart data views read their rows from the column cache in memory. Changing the Campaign, dates, filters or comparison mode recalculates the charts from the columns already in memory without reading the CDRs again.

### What Clear cache removes

Combined CDR tables remain the source for filters and chart data. Selection records keep counts, facets and reproducible predicates; the cache does not copy CDR rows into a separate projection database.

PPT charts read the materialized combined CDR tables through a per-CDR column cache kept in memory. Each column a chart needs is read once per CDR, together with the PPT filter columns (the default filters, the Design's custom fields and the event date): from the [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) of each CDR when every copy of the selection holds its CDR as it is, else from SQLite. A column worked out by an expression is worked out once per distinct value, giving the value SQLite gives: the day of each time is written directly where it is certain, and by SQLite in memory otherwise. The RF fields (coordinates, RSRP and SINR) are read as the numbers the CDRs hold, without turning them into text and back (a value that is no number stays text, without its spaces at both ends, and blank text is no value). Any combination of CDRs, dates, filters and comparison mode is then assembled in memory without querying the CDRs again. `CDR-All` pools the Data, Voice and Speech tables without rereading the original uploaded files.

Preparing a changed universe also counts its rows from these filter columns, and reuses the distinct filter values of each CDR until that CDR changes, instead of reading the CDRs again. The assembled rows are exactly the rows SQLite returns, with the same values and types. Maps, scatter plots, tables and chart data views also keep SQLite's row order. When SQLite would return them in an order the cache cannot reproduce, for example while filtering a single City, those charts read SQLite directly. Charts reading the same fields share one read, and charts with the same source, filters and measure share one filtering pass.

Preview manifests (the preparation of a Design) and Canvas models (the drawn data of each chart) are kept in memory and, as compressed files, in the `.cache/ppt-designer` folder of the workspace (`preparations/` and `charts/`), keyed by dataset revisions, selection, scope, template and format, mappings and renderer version: other sessions and PPT exports reuse them, and after a restart a Design already prepared opens at once with the charts already drawn, while anything that changed is worked out again. Each file is written under a temporary name and renamed once complete, so a chart is never kept half written; a file that cannot be read (cut by a crash or a full disk) is deleted and worked out again, and temporary files left by a write cut short are deleted. The folder keeps up to 1 GB, the least recently used files removed first (`DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB` changes this limit), and files nothing has used for 30 days are removed. The folder is left out of backups, exports and transfers, moves with its workspace when it is renamed and is deleted with it, and **Clear workspace cache** empties it (set aside at once, deleted in the background). What earlier versions kept in the workspace database (the PPT Preparation Cache and PPT Chart Models Cache tables) moves to the folder when the workspace opens (App Event `ppt_design_cache_moved_to_folder`), and the tables are dropped. The column cache keeps up to 1 GB in memory by default, removing the least recently used columns first, and `DRIVETEST_ANALYZER_COLUMN_CACHE_MEMORY_MB` changes this limit. The `.design-data-cache` and `.design-chart-cache` folders of earlier versions are removed when a workspace opens.

> [!WARNING]
> **Workspace Clear cache cancels active user-requested work and removes derived cache only.** It preserves PPT definitions, combined CDRs, templates and generated jobs. The warm-up rebuilds the cache the next time the server is idle.

Canvas models are created when a chart is viewed, refreshed or requested for PPT, or by the warm-up. The charts of the open slide are calculated first and appear as each one is ready. After they load, nearby slides silently prefetch one chart at a time in the order next, previous, two ahead, two behind. A prefetch waits while the charts of a newly opened slide are calculated, so moving to another slide never queues it behind prefetched charts. Opening an individual chart uses the chart sequence instead. Closing the viewer stops scheduling further work.

## View PPT

Open **View PPT** from the library or filter panel (**Edit Design** opens it in the Designer). It does not expand the main filters panel automatically; use **PPT Filters** for the floating controls.

### Read the header

The viewer preserves the template's 16:9 layout and uses approximately 96% of the viewport. Its header identifies NR Mode, Design and slide position.

- Slide titles and golden-yellow subtitles display in capitals.
- Campaigns, Scope, Regions and Cities identify the applied selection.
- Export snapshots show the selection captured by that PPT job.

Campaign labels are compact, such as **26-Q2**, **26-Q2-NSA** or **26-Q2-SA** (see [Campaign ordering](technical-considerations.md#campaign-ordering)). Older CDRs may populate cached campaign labels a few seconds after first opening.

### Slides and navigation

| Control | Use |
| --- | --- |
| Slide selector | Jump to a template slide; searchable choices show the number, a purple title and a teal subtitle separated by a bold ● |
| Slides at the left | Every slide in small, as in the presentations of the [Help](help.md#presentations): the covers and transitions as in the viewer and the charts of the others once calculated, with their number and title; the slide shown is marked, and choosing one shows it (on wide screens; phones keep the slide selector) |
| **Presentation**, **First / Previous / Next / Last** | Below the slide and its comments: play the slides or move through them |
| Keyboard and wheel | ← ↑ Page Up go back and → ↓ Page Down (or Space) go forward, Home and End go to the first and last slide, when focus is outside editable controls; the wheel over the slide goes to the previous or next slide, one per turn |
| **Scope** | Switch Operator/Multivendor after confirmation |
| **PPT Filters** | Edit the live selection in a floating panel |
| **Generate PPT** | Export the selection |
| **Refresh Design** | Refresh the PPT preparation |

On wide screens these controls share one row above the slide: the slide selector with the two image buttons of the slide beside it, then **Scope**, **PPT Filters** and **Open Designer** with their names, and **Generate PPT**, **Refresh Design**, **Auto-Calculated Fields** and **Edit PPT Template** as icons (point at one to read its name). While designing, the slides at the left take the place of the slide selector.

**Theme**, at the start of the floating section bar of the page, colours the charts and the slide titles of the viewer and of the PPTs with the colour themes of [Scoring & GAP Analysis](scoring-gap-analysis.md) (**Ericsson** by default, **NetCheck**, **Umlaut**, **Vodafone**, **Midnight**, **Paper** and **Heatmap**): the charts take its font and its colours for text, axes, grid lines, table headers and alternate rows (the colours of operators, vendors and thresholds stay as they are), and the slide title and subtitle of the viewer (still in capitals) and the titles and subtitles of the content slides of the PPT take its title style, the part that tells the slide apart in its focus style; **Midnight** paints the charts and the content slides night blue (with the logos in white) and turns their tables, text and comments light on dark. Title and Transition slides keep the template look. Each user keeps one theme per workspace for every themed module (choosing it here chooses it in Scoring & GAP Analysis, Network Insights and CDR Analysis too); changing it restyles the viewer and redraws the charts at once, is kept for the next visit and the PPTs generated afterwards (also from Reporting Jobs), and is recorded in the App Events log.

Changing Scope renders the charts again with the PPT filters (a Campaign that still has the default of the former Scope takes the default of the new one). Multivendor is unavailable when the workspace has fewer than two Vendors.

Title and Transition slides preserve the template text and look as in the exported PPT: the Vodafone-Three red with the Ericsson mark, the Vodafone-Three and Ericsson logos at the top right, light titles with the room of two lines and the yellow subtitle below them. A title cover shows Campaigns above its decorative divider, with Scope, Regions and Cities beneath it, in white with bold labels; each Title or Transition slide after it shows its counter (01, 02…), as in the PPT. An End Slide shows the Ericsson mark and name centred on white, as the closing slide of the PPT, without counter. Chart rows preserve template order and placeholder geometry.

In grids with three or more rows or four or more columns, each chart's title appears as text above the chart, in the viewer and in the PPT, so it stays readable in small cells. Dynamic grids show the row or column value (for example the Operator) in bold before the title, such as **EE** · LTE RSRP histogram.

Axis labels and aggregation headers are never truncated, in the viewer or in the PPT. Each axis level wraps onto two lines, uses a smaller size or turns vertical, and the chart reserves the room it needs.

Layouts ending in **comments right** place comments beside the charts; **comments down** places them below. Layouts without comments use the full chart area. Narrow screens wrap actions and adapt navigation to the available space.

### Live and expanded chart controls

Hover or focus a chart for **Dataset**, **Expand**, **Refresh** and **Zoom**; while the [Designer](#designer) is open only **Dataset** shows, and the chart itself is changed from its panel. The controls also remain accessible on touch devices.

| Gesture / action | Result |
| --- | --- |
| **Expand** or double-click | Open the focused chart in the expanded viewer |
| **− / + / 1:1** | Zoom between 100% and 400%, or reset |
| Ctrl/Cmd + wheel (or a pinch of the touchpad) | Zoom the chart under the pointer, at the pointer |
| Drag a rectangle at 100% | Zoom into the selected plot area |
| Drag when zoomed | Pan the chart |
| Direction arrows when zoomed | Move the camera; arrows disable at boundaries |
| Click a legend entry | Hide or show that value in every slide of the Design; a hidden entry stays faded and struck through |
| Right-click a legend entry or an axis label | **Keep only**, **Hide** or **Show**, **Hide All** and **Show All** for that legend or axis level; an axis menu also lists its hidden values, each opening a **Show** submenu when the pointer moves over it |

Hiding a value applies to the whole Design. Every series, bar, stacked segment, row, column and category where the value appears, at any aggregation level, disappears and the chart closes the gap: hiding Operator VF_SA also hides each VF_SA Campaign, for example. In dynamic grids, the cards of a hidden value (such as an Operator) leave the slide and the remaining cards fill a smaller grid. A slide whose cards are all hidden offers **Show hidden values** and is left out of the PPT.

The legend state lasts for the browser session and also applies in the expanded viewer. **Generate PPT** exports the charts as you see them, and the PPT job's viewer shows the same state. Relaunching a PPT job keeps the state it was created with. In Network Insights, clicking a legend entry hides or shows it in that chart only.

The slide of the viewer, each of its charts and the chart of the expanded viewer download as a PNG image or copy to the clipboard as a screenshot (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)): the whole slide from the two blue buttons beside the slide chooser, above the slide, with its comments below it when it has some (as plain text); each chart (also when it is the only one of its slide) from the floating buttons at the left of its controls, on the same row; the chart of the expanded viewer from the buttons above it. So do the Charts Panel and each of its thumbnails. App Events records each one as `export_design_image`, with the slide or the Design and date of the PowerPoint job.

The expanded viewer has the actions of the viewer above the chart (its image, **PPT Filters**, and **Auto-Calculated Fields** and **Edit PPT Template** as icons named by their tooltips), chart navigation and a red Close control. Compact portrait/landscape layouts fit navigation and the chart to the viewport; the Comments drawer stays accessible at the bottom.

### Edit a chart definition

The charts of a PPT Design are changed on screen in the [Designer](#designer) (**Open Designer**), for the Design or for its template; **Edit PPT Template**, the pencil at the top of the viewer and of the expanded viewer, opens its template as a table at the row of the chart. Template and calculated-field editing require **user-editor**, **admin** or **super-admin**.

The [Report Template reference](#report-template-reference) describes supported chart types, filters, aggregations, legends and layouts.

### Filtered Chart Dataset

**Dataset** opens rows after both the PPT filters and that chart's template filters. It is not every row of the chosen CDRs.

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
| Generated comments | The icons after the slide navigation: comments for the open slide from the figures of its charts (reviewed before they are added) or for all slides, and a menu with the writer and the Kiro brief |
| **Presentation** | Advance every 3, 5, 10 or 15 seconds, with Fade, Slide or no transition |
| Pause/Resume and Stop | Floating controls remain available in Presentation mode |
| **PPT Filters** | Change applied selection without automatically saving defaults |
| **Auto-Calculated Fields** | Open the shared workspace manager for permitted editors |

Manual navigation stops Presentation. Its settings adapt to compact landscape screens. Backdrop/Escape closes unchanged dialogs; pending Filters, Template or calculated-field edits require a decision first.

#### Generated comments

For editors, three icons follow the slide navigation, set apart like **Presentation** before it (on a phone, on a row of their own below it); hovering each one names it. **Generate comments for this slide** (the sparkle) writes analysis comments for the open slide from the same figures its charts draw: the filters, splits, PPT filters, dynamic grid cards and legend items hidden in the viewer apply, and the excluded operators are never named.

| Chart type | What the comments read |
| --- | --- |
| CDF Line, Multi KPI CDF Lines, Histogram Line and Histogram Bars | The exact median of each series, its tail (P10, or P90 when lower is better) and, with **Buckets**, the share of samples in the worst class |
| Average and Median Vertical Bars | The value of each bar |
| 100% Stacked Vertical Bars | The share of failures (Failed, Dropped, Cutoff…), or else of the largest class (RAT, CA state…) |
| Threshold Stacked Vertical Bars | The share reaching the threshold |
| Distribution Stacked Vertical Bars | The share in the worst bucket |
| Count Stacked Horizontal Bars | The share of failed and dropped tests among all the tests of each bar; when its filter keeps only the failed and dropped tests (such as `Call_Status IN (Failed, Dropped)` in **Voice failures** and **Voice failures per City**), the counts it draws: the operators from the one with the most in the latest campaign, the change since the previous campaign (a Flex campaign only against another Flex campaign; a change too small for its counts reads *stable*), the CDR type, city or other row with the most and the bar with the largest count, and the operators without any |
| Scatter | How the KPI follows the other measure (Spearman ρ) and its median in the lowest and highest quarter of it |
| Map | The share of the samples in the weakest class of its colour measure and, with City or Region in the rows, the area that holds more of it than its share of the samples |
| Table, Dynamic Table, Highlight Table and Bar Table | The highest and lowest rows of its first numeric columns |
| Horizontal Bars, Dot Plot, Bullet Graph, Heat Map and Lines | The value of each bar, dot, square or point, as Average and Median Vertical Bars (when the measure is averaged or a median) |
| Box Plot | The median of each box and its tail (P10, or P90 when lower is better), as a CDF |
| Pie, Donut, Areas and 100% Stacked Areas | The share of failures, or else of the largest slice or area, as 100% Stacked Vertical Bars |

Dual Lines, Bars and Line, Symbol Map, Filled Map, Treemap, Packed Bubbles, Sankey and Gantt get no generated comments: write theirs by hand.

The comments compare the latest campaign of each group with the previous one and every operator with the leader, from the point of view of the **Focus** operators of the [Operator Maps](workspace-config.md#operator-maps) (without Focus operators they follow the leader), compare the vendors of each operator in Multivendor and, in a chart split by NR Mode, each operator in SA with itself in NSA (the newest campaign of each NR Mode), and read the charts of a slide together: an NR KPI against the same LTE KPI for every operator, the KPI of a chart of SA against the same KPI of a chart of NSA (their titles name the NR Mode, such as CDF_NSA and CDF_SA), and the operators of a slide that gives each operator its own chart. Each KPI is read with its unit and its better side (RSRP and SINR in dB, higher LQ, Mean Data Rate and scores are better, lower durations, times, RTT and error ratios are better), a group with fewer than 10 samples is not named, and a difference too small to matter (1 dB for RSRP and SINR, 0.1 for LQ, 5% for the other KPIs, or a share difference that is not statistically significant) reads as *stable* or *on par*. A slide gets up to four comments (three in the **comments right** layouts), the best one of every chart first.

The suggestions replace the list of comments until you decide: untick or edit them, then **Add selected comments** adds them after the existing comments of the slide (saved at once, like the comments you write), or **Discard** leaves the slide as it was. Comments added from Generate comments keep a **Generated** tag (hover it to see when and by which writer); edited by hand, a comment is yours. When the slide is open with another selection (other campaigns, filters or CDRs, such as a new campaign with **Latest 2 campaigns**) than the one its generated comments were written for, the panel says they are out of date: generate them again. The CDRs count by what they hold (their type, stage, campaigns and rows), so a Design transferred to another server where the same CDRs were uploaded, or a CDR processed again, keeps its comments up to date.

**Generate comments for all slides** (the sparkle on a stack of slides) writes the comments of every slide in one go, in the background, following its progress slide by slide: on **Only Slides Without Comments**, in place of the generated comments keeping those written by hand (**Replace Generated Comments**), or in place of every comment (**Replace Every Comment**); a summary says how many slides were written and kept.

**Writers.** The rules always read the charts, on the server. When Super Admin enables them in [AI Comment Writers](super-admin.md#ai-comment-writers), the menu of the third icon (**⋯**) picks the writer, which the tooltips of the other two name: **Rules**, **Kiro CLI** (the default LLM) or **Claude**, each with the API key of the server or with your own (user menu → **API keys**), as Super Admin chooses; what it writes is charged to the account of the key. An LLM writer receives the facts of the charts and the rules comments, rewrites them in a more natural way and connects them; every figure it writes must be one of the facts and it must not name a hidden item, otherwise that comment is left out, and when none keeps to the facts, or the writer fails, the rules comments are shown with a note saying why. With the **Kiro Brief** enabled, the same menu offers **Download Kiro brief**, which downloads the facts of every slide for Kiro IDE (a folder with the facts, the style guide, also as a Kiro steering file, and the comments.json Kiro fills in) and **Import Kiro comments** reads back comments.json and facts.json (or the folder zipped again), checks every figure and writes the comments with the same three choices as Generate comments for all slides.

App Events records each generation (slide, writer asked and writer that wrote, model, charts read and skipped, suggestions, comments left out, tokens of Claude and time taken), the comments added from it, Generate comments for all slides, the Kiro briefs exported and the Kiro comments imported.

## Designer

**Open Designer**, at the top of the viewer, turns it into a slide editor (the button reads **Close Designer**, in amber, while it is open, and closes it; it asks about the changes only when something differs from what is saved, so changes undone or made back by hand leave nothing to save). While it is open, **Auto-Calculated Fields**, **Edit PPT Template**, **Generate PPT**, **Refresh Design** and the presentation wait for it to close, and the tools over the charts (images, expand, zoom) are hidden but View dataset; **PPT Filters**, the Scope and the theme stay, as they change what the slides are laid out on. The slides at the left become the slides being edited, the charts of the slide shown can be chosen and moved, and the panel at the right shows the slide or the chart chosen. Its head says where it is (**Slide 2 › Chart 1**: click the slide to see it again; the chart button, **Charts** while none is chosen, lists the charts of the slide to choose one), what a change reaches (**This Design** or the template) and how the slide or chart differs from the template; its **⋯** menu holds the actions of the slide or chart. Drag the left edge of the panel to widen it, or narrow it again (double-click gives it its usual width); a wide panel shows the fields of a chart beside its shelves. Every change is drawn at once on the CDRs the Design already prepared; nothing is stored until **Save**.

| From | To | How |
| --- | --- | --- |
| PPT Template | Each Design that follows it | Live: the template's slides and charts, plus the differences of each Design |
| A Design | Its template | **Apply to template** (a slide or chart), or Template scope |
| A Design | Slides of its own | **Detach from template** |

### Template or This Design

A Design does not copy its template: it follows it live and keeps only **what it changes**. Whatever it does not change comes from the template, so a change of the template reaches every Design that follows it.

| Scope (bar of the Designer) | What a change does |
| --- | --- |
| **This Design** | Changes this Design only, kept as its differences from the template: a slide hidden or added, a title, a layout, the place, type or any setting of a chart, the conditions added to or removed from its Filters |
| **Template · N Designs** | Changes the template: Save asks to confirm and names the other Designs that take the change |

A difference of a Design wins over the template. When the template changes the same thing afterwards, the slide or chart shows **Template changed**: **Differences** offers **Take template** or **Keep mine**. Conditions added to or removed from the Filters of a chart are kept one by one, so the other conditions of the template still reach the Design.

| Mark | Meaning |
| --- | --- |
| **This Design** (blue) | A slide or chart only this Design has |
| **Changed here** (amber) | The Design changes something of this slide or chart |
| **Template changed** (red) | The template changed what the Design had changed |
| **Hidden here**, **Optional · off** (grey) | A slide of the template this Design leaves out |

**Differences** shows a card for each slide and chart the Design changes, with a chip for each property it changes (its title, place, format, chart type, hidden…): the arrow of a chip takes the template back for it, **Reset all** for every one of the card; the menu of a slide or chart also has **Reset Slide to template** / **Reset Chart to template** and **Apply Slide to template** / **Apply Chart to template** (the template takes it, and every Design of the template with it).

### Slides

- The slides at the left show each slide in small as it is laid out (its charts, KPI cards, text boxes, pictures, or its cover), drawn again when the slide, the other slides or the data change; a slide left out of the Design shows its places only.
- Choose a slide at the left; its **⋯** menu (or a right click) offers **New Slide after**, **Duplicate Slide**, **Hide Slide in this Design** / **Show Slide again**, **Delete Slide** (Template scope, or a slide of this Design), **Make Slide optional (off by default)** and, for an optional slide, **Show Slide in this Design**. **+ New slide** adds a content, title, transition or end slide.
- Drag a slide to move it: in Template scope any slide, in This Design scope the slides of this Design (those of the template keep their order).
- The panel of a slide has three subpanels, **Titles**, **Layout** and **Elements** (its charts, KPI cards, text boxes and pictures, to choose one): it changes its title and subtitle (**{ }** inserts a field or a parameter, see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)) and the **layout**: a grid of up to 6 × 6 places, with comments below, to the right or none, and the other layouts of the slide master. A layout with fewer places than the slide has charts removes the last ones, after asking. **Adjust places…** starts from a layout ready to use (two above and one as wide as both below, one wide above and two or three below, a tall one beside two or three, three above and two below…), gives the grid rows and columns more or fewer (up to 6 rows and 12 columns), resizes its rows and columns by dragging the lines between them and merges neighbouring places into one (a chart over two columns) or splits them again; **Delete** (or the Delete key) empties the places chosen, leaving their cells empty (a **+** puts a place back in an empty cell), and **Center** puts the place chosen midway in the empty cells beside it, adding the lines of the grid it needs (a chart centred below two others: delete the place beside it, then Center); the elements keep their places in reading order, a place merged with a free one keeps its element, and the element of a place deleted goes to a free place (or, with none, is removed after a confirmation). **Reset places** gives the layout its places back. The **⋯** menu of a chart with free places beside it offers **Fill the free places beside the chart**: it spans them in its row (else in its column), as a chart below two others that takes the whole width.

### Fields in titles and text boxes

Slide titles, subtitles, chart titles and text boxes write these fields as each Design reads them (**{ }** beside them inserts one):

| Field | Writes |
| --- | --- |
| `{NR Mode}`, `{NR Mode Name}` | NSA, SA or NSA & SA; Non-Standalone, Standalone or Non-Standalone & Standalone (a chart title, the NR Mode the chart shows) |
| `{Design}` | The name of the Design (`{Dashboard}`, as titles of before PPT Designer wrote it, writes it too) |
| `{Scope}` | Operator Comparison or Multivendor Comparison |
| `{Campaigns}` | The Campaigns of the Design (*26-Q2, 26-Q3*) |
| `{Operators}`, `{Vendors}`, `{Regions}`, `{Clusters}`, `{Cities}` | The values the Design is filtered by (*London, Leeds*), or *All Operators*, *All Cities*… when it is not filtered by them or keeps every value of its CDRs |

The template keeps the fields, so each Design of it writes its own selection. Parameters of the template are written the same way (`{City}`), and their names cannot be those of the fields.

### Charts on the slide

- Click a chart to build it, as in Tableau: its title is written in the head of the panel (**{ }** inserts a field), and its **Data** has three subpanels, **Chart**, **Filters** and **Fields** (the fields to drag to the other two). It chooses its **Source** (Data, Voice, Speech or RF All: the CDRs the chart reads) and its **NR Mode**, one button per result: a PPT Design of NSA or SA reads only its CDRs, so its NR Mode is chosen and the other one is greyed until NR Mode NSA & SA is chosen in PPT Filters; one of NSA & SA offers **NSA & SA**, **NSA** or **SA**; in Template scope **PPT Mode** follows the NR Mode of each Design of the template (a chart that keeps **NSA** or **SA** has the filter `NR Mode IN (SA)`), then drag the fields of the source, grouped by the sections of the CDR Field Dictionary and told apart as dimensions (blue `Abc`) and measures (green `#`), to its shelves: **Measure** (its menu chooses the aggregation), **Rows**, **Columns**, **Legend**, **Filters** and **One chart per** (one chart for each value of a field, side by side in the place of this one: small multiples, in the viewer and in the PPT). A field dropped on the middle of a pill takes its place, and near its edges or between pills it goes there. A time (such as `Test_Start_Time`) dropped on Rows or Columns is grouped by day, `DAY(Test_Start_Time)`: its pill chooses **By hour**, **By day**, **By week**, **By month** or **Exact time**, and the chart types along time (Lines, Areas…) draw it as a time axis. A field dropped on Filters opens its values in the Design's selection with their samples (Include, Exclude, Contains), or a numeric condition, or a parameter of the template (**Use parameter**); the filters of the Design show first on the shelf, locked. **Chart Type**, the tab in the colour of the theme on the right edge of the chart chosen, inside its place on the slide (it pulses when the chart is chosen; while the chart is not drawn yet, it waits on the edge of the panel), opens the chart types over the slide beside the chart (over the whole slide when there is no room beside it for six types in a row, each picture as large as the room lets it) as pictures with their names, grouped by what they show, a row for each group (Distribution, Comparison, Trends, Composition, Hierarchies and flows, Tables, then Maps with Scorecards beside it: a group of one or two types goes on the row before it; see [Supported chart types](#supported-chart-types)): those the shelves cannot draw are greyed and cannot be chosen (a chart without a measure yet, such as a new one, takes any of them), the line above them says what the one pointed at needs (a Map, a latitude and a longitude on Measure, a third measure colouring its points), the **Chart** subpanel (and the form of a KPI card) says what the one chosen needs (ticked in green once it is given), and when the measures rule the chosen type out another one is proposed (a type chosen before its fields is kept while they are dropped); the settings of the chosen type are set under the types (Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort or Date Bin). Choosing a chart type closes it, as its tab, **×**, **Esc** or a click outside it do. **KPI Card**, under Scorecards, turns the chart into a [KPI card](#kpi-cards-text-boxes-and-pictures) of its first measure, with its source, title and filters (an average for a number, the share of a value otherwise); a KPI card has Chart Type too, and another chart type turns it back into a chart, its settings kept for a later return. The chart is drawn again a moment after each change.
- **Format** (beside **Data**) changes how the chart looks, in the viewer and in the PPT alike (the same renderer draws both), in four groups, open at first, that close and open on their own (a closed group says what it holds):
  - **Series:** click an entry of its legend on the chart, or the series in the list, to change its colour, line width, line (solid, dashed, dotted: its dashes and round dots grow with the line width) and opacity. The colours of Operator and Vendor Maps stay until a series is given one: **Default** gives one series its colour back, **Default colours** every series. **Copy line of this series** copies its line width, line and opacity (not its colour, which tells the series apart), and **Paste line of** *that series*, on another series of this chart or of another one, gives it the same.
  - **Legend:** its place (top, bottom, left, right or hidden) and the size, colour and bold of its text.
  - **Labels:** their place and the size, colour and bold of their text.
  - **Axes:** the titles of the X and Y axes and the decimals of the X axis of a CDF. Click the labels of an axis on the chart to change it there: a numeric axis opens a slider with two ends for its range (**Automatic** gives it back), a text axis the list of its values to untick those the chart leaves out (kept as a `NOT IN` condition of its Filters), **Only** one of them or **Show all**.
  - **Copy format of this chart** copies the format of the chart chosen (its series colours, legend, labels, axes and axis ranges); on another chart, **Paste format of** *that chart* gives it the same format.
- The **⋯** menu of a chart offers **New Chart**, **Duplicate Chart**, **Copy Chart** and **Delete Chart** (a KPI card, a text box or an image names itself the same way). **New Chart** puts an empty chart on the slide (the source of the chart chosen, no fields and no chart type, so any chart type can be chosen) and **Duplicate Chart** a copy of it; a slide without a free place gets one first, a column more on its adjusted places, else the layout of its kind with the fewest places that leaves one free (its rows when it can). Until its shelves can draw it (a measure, a chart type and a Rows or Columns split; a KPI card, its field), a chart reads no CDR: the slide shows its empty place, the PPT leaves it empty, and its row in the template is a `Chart in progress` that keeps what it has in its `Format` column; its **Filters** subpanel also leaves out the rows whose measure is empty (**Leave out empty values**) or 0 (**Leave out zeros**).
- Drag a chart by its **⠿** handle onto another chart to swap their places, or onto a free place to move it there. A free place of the layout shows **+ Add**: a chart (empty, as **New Chart**), a KPI card, a text box, a picture, or one copied before (**Copy Chart** in the menu of a chart).
- **Delete Chart** removes a chart (in This Design scope, a chart of the template is hidden in this Design).
- **Ctrl/Cmd+Z** and **Shift+Ctrl/Cmd+Z** undo and redo; **Delete** removes the chart chosen; **Esc** closes a menu or Chart Type, then leaves the chart chosen (in a field of the panel, it leaves the field), as a click anywhere in the viewer outside the charts, the panel and the bar of the Designer does.

A change the template cannot hold (a chart without a KPI or a split, for example) is refused with the reason and undone.

### KPI cards, text boxes and pictures

| Element | What it shows | In the PPT |
| --- | --- | --- |
| **KPI card** | One figure of the latest campaign of the Design: Average, Median, Percentile, Count of samples, Share of a value (%), or Share below / above a threshold (%), of a measure of a source with its filters; compared with the previous campaign, the best competitor (with **One card per** Operator, for example) or a target, green or red as it improves (**Higher is better**); its colour band (**Good from**, **Poor from**) and its **Trend over the campaigns** | Drawn by the same renderer as in the viewer |
| **Text box** | Text written with the editor of the tickets (bold, lists, headings), its size, alignment and colour, with fields and parameters | A text box of its own, bold, bullets and headings kept |
| **Image** | A PNG, JPEG or GIF picture of up to 8 MB (an SVG can be saved as PNG first), fitted in its place keeping its ratio | A picture of its own |

Pictures are kept in the table **PPT Images** and travel with the PPT Designs and PPT Templates whose slides use them, in exports, transfers and backups (an import adds those the workspace does not have; the CSV of a template downloaded alone names them only). Text boxes and pictures read no CDR; PPT Reporting (old) leaves them out (a slide with only them keeps its title).

### Save, drafts and the other actions

- **Save** stores the template (Template scope) and the differences of the Design. If another user saved the template since you opened the Designer, Save asks you to reload it first.
- What is not saved yet is kept on the server, for you only, as a draft (table **PPT Drafts**): opening the Designer again offers to restore it or discard it. **Discard** goes back to what is saved. Drafts are not part of exports, transfers or backups.
- **More** offers **Save Design as…** (a Design of your own that follows the same template with the changes shown), **Save as template…** (the slides shown as a new template) and **Detach from template…** (the Design keeps the slides it shows as its own and no longer follows its template; choosing a template for it again in PPT Designs follows that template as it is).
- Deleting a template that Designs follow detaches them first, so none of them breaks.
- Generate PPT, Reporting Jobs and Bundle Report Templates use the slides of the Design as saved. The comments of a slide stay with it when its title changes.

### Who can design

| Role | Slides of a Design (This Design) | Slides of a template (Template scope, parameters) |
| --- | --- | --- |
| **admin**, **super-admin** | Any Design | Any template |
| **user-editor** | The Designs they created | The templates they created; **Save Design as** for a variant of another one |
| **user-viewer** | — | — |

App Events record `design_slides_saved` (what changed: slides and charts of the template, differences of the Design), `report_template_saved_from_designer`, `report_template_slide_ids_assigned`, `design_detached`, `report_template_saved_from_design`, `design_draft_discarded` and `design_image_uploaded`.

### Template parameters

A template can declare **parameters**, so that Designs that differ only in a city, a call family or a threshold share one template with no difference of their own (a *City Report* template and its London, Manchester and Cardiff Designs).

- **Parameters** in the bar of the Designer (Template scope) lists them at the left, with their type and where they are used, and shows the one chosen at the right, where it is renamed and deleted; a template without parameters shows a card per type, which adds one, and **+ Add parameter** under the list asks for its type: **Field values** (the values of any field of the CDRs or an Auto-calculated Field, chosen from the groups of fields as in the chart builder, with a search; one or several; none chosen means All), **Number** (default, minimum, maximum, step) or **Text**. A parameter cannot take the name of a built-in token (`{Cities}`, `{Operators}`…): the first ones are named Chosen Cities, Threshold and Note. **How to use it** gives the condition to write (`City IN ({Chosen Cities})`), to copy or add to the filters of the chart chosen. A parameter in use cannot be deleted, and renaming one renames its uses.
- Write `{Name}` in a chart filter (`City IN ({City})`; with All the condition is left out), a numeric setting (`LQ < {Threshold}`, `Threshold = {Threshold}`, an axis range) or a title (`Voice quality in {City}`).
- Each Design chooses the values in **PPT Scope & Filters → Parameters**, applied and saved like its filters; until it chooses them, it uses their default values. The section shows only when the template has parameters: they are added in the Designer, never there.
- A [Reporting Job](reporting.md) gives each of its PPT Designs values of its own under **Template parameters** (those it does not change stay the Design's), and **One PPT per** a field-values parameter generates a PPT for each value chosen for it, named after the value (a *City Report* for London, Manchester and Cardiff in one run). A [Bundle Report Template](reporting.md) gives a field-values parameter on a field of its common filters (Operator, Vendor, Region, Cluster, City…) the values chosen there. With values other than the Design's, the PPT goes without its saved comments, written for its own values, unless Auto comments write them.

## Generate PPT

### Choose the export inputs

Open **Generate PPT** from the library, filter panel or viewer. **Select PPT Scope and Filters** controls the export's exact selection, which can differ from saved defaults.

| Export subpanel | Settings |
| --- | --- |
| **Scope** | Scope (and vendor comparison) |
| **Main PPT Filters** | Campaigns (which choose the CDRs) and the CDRs they choose, the dates below them (the whole width), then Operators and Vendors, Regions and Cities |
| **Show All Filters** | Reveal the remaining main filters and Additional Filters |

The export has no CDR selector: **Campaigns** lists every campaign of the Design's NR Mode (with NSA & SA, it chooses the NSA CDRs and the SA ones keep the Campaign (SA) of the Design), with **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** and **All available campaigns** first (each one alone), starts with the Design's Campaign and lists below it, by type, the CDRs it chooses now; both appear as soon as the dialog opens. The other choices load from those CDRs and start with saved filter values, or all available values when unrestricted or no saved values remain available.

Cities offers **Main Cities** first, exported as the Main Cities of the workspace. Changing campaigns or dates preserves selected values still available; an All selection includes new values. The browser remembers the dialog's last Scope, Campaigns and dates per Design/user.

**Auto comments**, in the Scope of the dialog (or a checkbox of the confirmation when the PPT is generated from the viewer), writes generated comments into this PPT only, with the writer the viewer generates comments with (the default one of Super Admin until it is changed in the menu of the comment tools; with more than one writer enabled, the dialog shows it as **Comment writer** beside Auto comments, and a change there is also the viewer's): on the slides without comments, in place of the generated ones or in place of every comment. The Design keeps its own comments; the job's viewer shows those of the PPT, a relaunched job keeps its choice, and App Events records how many slides they were written on.

### Save defaults only when intended

| Action | Effect |
| --- | --- |
| **Generate PPT** | Export the dialog's selection |
| **Save Filters** | Also persist its Scope, dates, Campaigns and other filters in the Design |

Save Filters is enabled when the dialog differs from the saved defaults (the vendor comparison counts only in Multivendor Comparison). A complete value selection equals an unrestricted field; saved values absent from the selected CDRs are ignored.

> [!IMPORTANT]
> **Export selections take precedence for that job.** You can export applied or dialog-specific filters without saving them as PPT defaults. The job's Filters snapshot records what was exported.

If required, the export prepares the CDRs of its campaigns first.

### Presentation contents and files

The PPT preserves template slides, layouts, chart proportions, titles, legends and saved comments. Chart subtitles use blue text; Title/Transition subtitles retain the template's yellow accent.

Title covers match the viewer: Campaigns appear in orange above the divider; Scope, Regions and Cities appear beneath in green, cyan and pink. Chart subtitles use normal letter spacing.

Generated PPTs, chart PNGs, tooltips and Canvas assets are stored under **output/reports/ppt-designs**.

| Filename part | Contents |
| --- | --- |
| Prefix | `yyyymmdd_HHMMSS` |
| Definition | NR Mode, PPT Name and Scope |
| Geography | Selected Regions joined by ` + `, or All Regions |
| Multiple campaigns | Campaigns joined by `_vs_` at the end |

Operators, Vendors and Cities remain in the job Filters snapshot and are omitted from filenames. Long names are shortened only for filesystem limits.

## PPT Generation Jobs

Jobs continue on the server after you leave the page. The table records ID, creator, local date/time, NR Mode, Design, Scope, filters, slide/chart counts, status and progress.

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

1. Filter by NR Mode, Design, Template, Scope, Region or City.
2. Select a **PowerPoint Job**.
3. Open a chart card in the expanded viewer, or use **View Filters** to inspect the snapshot.

Each filter offers only selections from jobs matching the other active filters. Choices describe complete exported selections. A job with seven cities contributes one City choice containing those seven cities; All Cities/All Regions appears only for jobs exported with those selections.

The job selector identifies its local date/time, NR Mode, Design, Scope and recorded geography. Long lists expose their full values on hover. Polling loads the newest matching completed job.

### Live Design versus saved snapshot

| View | Selection |
| --- | --- |
| **View PPT** | Current applied PPT inputs |
| **Charts Panel** | The generating PPT job's captured template and inputs |

Stored Canvas models repaint with the current renderer. Legacy jobs without models keep their PNG. The expanded viewer and Filtered Chart Dataset remain available.

> [!IMPORTANT]
> **Completed exports are immutable snapshots.** PPT Filters are hidden in Charts Panel. View Filters shows the exported selection; changing a live Design does not rewrite that job.

Permitted editors can open the generating template and Auto-Calculated Fields without changing the saved snapshot.

## PPT Templates

**PPT Templates**, at the top of the PPT Designs library (for `user-editor`, `admin` and `super-admin`), opens the **PPT Templates Library** of the workspace in a dialog: import, create, rename, duplicate, set the default, export, delete and edit its templates.

Templates belong to the active workspace and are stored in that workspace database's `report_templates` table. Import, export, backup and transfer packages serialize them as portable CSV files, but those files are package artifacts rather than the live source of record. Obsolete `slides-templates` directories are removed by the current migration and portability flows.

The library keeps the templates of the workspace, one of them the default. A template has no NR Mode of its own: it serves the CDRs of any NR Mode, and each Design (or Reporting job) chooses the NR Mode it reads. Its slide titles, subtitles and chart titles name that NR Mode where they write `{NR Mode}` (NSA, SA or NSA & SA) or `{NR Mode Name}` (Non-Standalone, Standalone or Non-Standalone & Standalone), so one template gives the NSA, the SA and the [NSA & SA](#nsa--sa-in-one-design) decks. PPT Designer also write the selection of each Design where they name it (`{Campaigns}`, `{Operators}`, `{Cities}`…, see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)). Every row has the **NR Mode** field (that of its CDR): a chart keeps one NR Mode with the filter `NR Mode IN (SA)` (its title's `{NR Mode}` then names that one), and NR Mode can split or label its series in Rows Split, Columns Split, Legend and the Dynamic Rows/Columns Field. Template names are unique in the workspace.

PPT Templates belong to PPT Designer, not to Config: their actions use the addresses of PPT Designer (`/ppt-designer/templates/…`; the former `/workspace-config/report-templates/…` ones lead there), need PPT Designer in the user's Modules Profile and are recorded in App Events under PPT Designer, and they follow its rights. Admins and super-admins change and delete any template; a user-editor changes (saves, renames, overwrites on import, receives copied slides or charts into) and deletes only the templates they created, as with Designs, and customizes the others from the [Designer](#designer) of their own Designs; a user-viewer sees and exports them. The slides of a template (with their charts, and its parameters) are edited from any Design that follows it, and kept in the template's CSV (its `Format` column).

The library is sorted by name (an NR Mode written in a name, such as `NSA - Report`, is ignored for the order); its columns show the creation and last update times and **Last Updated by**, the user who last imported, edited, renamed, duplicated or promoted the template.

Workspaces of earlier versions kept an NSA and an SA library: when they open, each pair of templates that only differed in the titles naming the mode (for example **NSA - NetCheck CDR Report** with *Non-Standalone* and **SA - NetCheck CDR Report** with *Standalone*) becomes one template named without the mode (**NetCheck CDR Report**) whose titles use the tokens, and the Designs, PPT jobs and Reporting (old) jobs that used either copy use it. A title only one copy named (such as *SA RF Quality Analysis* beside *RF Quality Analysis*) takes `{NR Mode}` in both. The other templates keep their names, an SA one named as an NSA one taking " (SA)". The App Events record it (`report_templates_nr_mode_merged`). Packages and backups of earlier versions are imported the same way.

Available actions:

- New
- Import CSV
- Edit
- Rename
- Duplicate
- Set Default
- Export
- Delete

**Edit** opens the template in the viewer and its [Designer](#designer) as a PPT of its own, never listed among the PPT Designs: it reads the CDRs of the NR Mode and Campaign it was last opened with (NSA and Latest 2 campaigns the first time; PPT Scope & Filters changes them), every change of the Designer goes to the template (its bar reads **PPT Template** with the number of Designs that follow it), **More** offers only **Save as template…**, and it makes no PPT of its own (its Designs do). **Edit PPT Template**, the pencil at the top of the viewer, shows the template as a table (see [Table view](#table-view-template-editor)), for Find & Replace for example.

**New Template** creates a template with its cover and opens it in its Designer, where its slides are added. Import accepts a CSV name or derives it from the filename, can convert a legacy catalogue when prompted and requires explicit overwrite confirmation for a case-insensitive name collision.

Renaming saves when you leave the name field or press Enter; the field keeps its previous name and shows an error if the save fails. Each template has an identity that never changes, and each Design refers to its template by it, so a renamed template stays the template of its Designs (whose names, when they repeat the template name, follow it too); a duplicate gets its own identity. Duplicate creates `- Copy`.

One template is the default within a workspace. Reporting initially selects that default but does not change it when a user chooses another template for one job. A default template cannot be deleted until another template becomes default. Only admins, super-admins and the user who created a template (with New Template, Import CSV or Duplicate; one brought by Admin Import / Transfer belongs to its creator on the source server when that user is active here, otherwise to whoever imports it) delete it; for the other users **Delete** is disabled and its tooltip says why. New workspaces start without templates.

The row Export action downloads that individual CSV; portable ZIP export is available under Import / Export / Transfer.

### Table view (Template Editor)

**Edit PPT Template**, the pencil at the top of the viewer, opens the template of the PPT as a table in a large dialog. The surrounding page controls are omitted from the embedded editor.

#### Grid behaviour

- The table scrolls vertically and horizontally inside its viewport.
- The bottom action bar remains visible.
- Shared slide cells are visually merged across charts on the same slide.
- Row controls add, remove, reorder and preview chart definitions.
- **Re-Enumerate Slides** rewrites slide numbers into their current visual order.
- Edited cells use a light pastel-yellow background.
- Newly inserted text is highlighted more strongly.
- A successful save resets all change highlighting.
- **Find & Replace** (or Ctrl/Cmd+F inside the editor) searches every editable cell of the template. Matching cells are outlined and the current one is highlighted; Enter and Shift+Enter (or Next and Previous) move between them. **Replace** changes every occurrence in the current cell and **Replace All** changes every occurrence in the template after a confirmation. Replacements are ordinary unsaved edits until **Save Template**; **Match case** restricts matching to the exact capitalization.

#### Validation

- Manual cell edits are validated after a short pause and when leaving the cell. Save revalidates the complete grid and stops if a row or filter is malformed.
- Every row error names the row as the editor shows it: `Slide: n - Chart: n` (the chart is the place of the row among the rows of its slide), or `Slide: n` for a Title, Transition or End Slide, followed by what to correct.
- Fixing the invalid cell clears the error message.
- Filter conditions render on separate lines with visual bullets; bullets are not stored in the cell.
- CSV filter cells retain one condition per line.

#### Assistance and previews

- Searchable single-select assistance for layouts, chart types, fields and positions.
- Ordered multi-select assistance for Rows, Columns and Legend.
- Cell Assistance writes a value to the cell as soon as it is chosen (and the KPI operation as soon as it is picked); the values of Rows, Columns and Legend follow what is ticked. **Close**, at its bottom, closes it.
- Shared Filter Builder with parsed-expression display. Its conditions reach the Filters cell when **Apply filter** is pressed, once the filter is complete.
- Chart Data Preview opens the full filtered dataset directly.
- Chart Preview reuses the shared Interactive Preview.
- **Preview NR Mode** (NSA by default, SA or NSA & SA), in the toolbar, chooses the CDRs the previews read: the ready CDRs of that NR Mode (of both for NSA & SA, as a Design of NSA & SA shows them), every Data, Voice and Speech test of them, and the titles of the preview name it (`{NR Mode}`, `{NR Mode Name}`).
- A note above the rows names the charts that use a KPI, filter or split field only the CDRs of one NR Mode have (they show no samples of the other one).
- **Update Template** applies preview values to the in-memory row; it does not save to disk.
- **Auto-calculated Fields** opens the shared active-workspace field manager.

**Save Template** validates and persists the complete grid atomically. Design comment reconciliation runs separately when slide identity changes; any required combined CDR update also runs after the save response. The PPT viewer refreshes the saved template when the editor closes. A combined CDR update is queued only when a template adds a source field missing from that CDR table.

Removing the last template reference leaves the existing column available for future reuse. Close, Escape and backdrop actions preserve the editor when unsaved changes still require a decision.

## Report Template reference

This is the canonical authoring reference for templates used by both [PPT Designer](ppt-designer.md) and [PPT Reporting (old)](ppt-reporting-old.md). The common `assets/powerpoint-templates/Template_VodafoneThree.pptx` supplies the masters, named layouts and placeholders. Each distinct `Slide` value creates one slide; chart rows sharing that value fill its chart placeholders in row order.

### Template columns

| Column | Purpose |
| --- | --- |
| `Slide` | Positive slide number. Rows are sorted by this value; rows with the same number form one slide. |
| `Slide Tittle` | Shared slide title. The historical `Tittle` spelling is part of the CSV schema. |
| `Slide Subtittle` | Optional shared slide subtitle. |
| `Layout` | Select `Title Page`, `Title Only`, or a grid named `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right`. Dynamic grids also appear in the selector. |
| `Chart Tittle` | Optional title drawn inside the chart. |
| `Source Dataset` | `CDR-Data`, `CDR-Voice`, `CDR-Speech` or `CDR-All`; leave blank for structural slides. `CDR-All` pools selected RF observations using `LTE_RSRP`, `NR_RSRP`, `LTE_SINR`, `NR_SINR`, `Latitude` and `Longitude`, retaining Operator/Campaign context. |
| `KPI` | Processed CDR field or metric expression to render. |
| `Chart type` | Automated chart type or structural slide type (`Text Box`, `Image` and `KPI Card` for the elements of the [Designer](#designer), and `Chart in progress` for a chart still being built, which reads no CDR). |
| `Filters` | Conditions applied before aggregation, one per line and terminated with `;`. |
| `Rows Split` | Category/table-row hierarchy. Separate dimensions with `×`. |
| `Columns Split` | Comparison-series/table-column hierarchy. Separate dimensions with `×`. |
| `Legend` | Optional field whose plotted or filtered values should be explained. Blank means no legend. |
| `Legend Position` | `Top`, `Bottom`, `Left` or `Right`; blank defaults to `Top`. |
| `Legend Format` | Optional list defining legend colour, font, styles and relative size. Blank retains automatic formatting. |
| `Label Position` | Optional value placement: `None`, `Top`, `Up`, `Middle` or `Down`. Blank retains automatic placement. |
| `Label Format` | Optional list defining label colour, font, styles and relative size. Blank retains automatic formatting. |
| `Axis X Range` | Optional CDF limits in KPI units: `[min,max]`, `[min,]` or `[,max]`. Blank keeps the automatic domain. |
| `Axis Y Range` | Optional CDF cumulative-percentage limits from 0 to 100, using the same syntax. Blank keeps 0–100%. |
| `Exclude Null/Empty` | `Yes` removes rows whose plotted value is null or empty before chart calculations. Blank keeps them. |
| `Exclude Zero` | `Yes` removes rows whose plotted numeric value is exactly zero before chart calculations. Blank keeps them. |
| `Format` | Optional, last. What the slides of the template ([Designer](#designer)) needs beyond the columns, as a JSON object per row: the ids of the slide and of the chart (`slide`, `id`), the place of the chart on its layout (`place`), its format (`style`: series colours, lines and opacity, legend, labels and axis titles), the kind of an element other than a chart (`kind`: `kpi`, `text` or `image`, whose Chart type is KPI Card, Text Box or Image) with the settings of a KPI card (`kpi`) or the text or picture of a text box or image (`content`), the field a chart is repeated by (`repeat`), the options of the slide (`slide_options`, such as `{"optional": true}` or the places adjusted on its layout, `geometry`) and, on the first row, the template parameters (`parameters`). A template gets it the first time someone opens Design on one of its Designs. Keep it when editing the CSV in Excel: Designs keep what they change of the template by these ids. A row copied, or added without it, gets ids of its own when saved. |

For multi-chart slides, the editor visually groups `Slide`, `Slide Tittle`, `Slide Subtittle` and `Layout`; the CSV still stores them on every row.

### Structural slides

Use one row without `Source Dataset` or KPI fields. A structural row cannot share its slide number with chart rows.

- `Title Slide` normally uses `Title Page` and fills title/subtitle placeholders.
- `Transition Slide` normally uses `Title Only` and creates a section divider.
- `End Slide` uses `Black logo end slide` and adds the closing slide of the template as it is, without title, subtitle or counter; its `Slide Tittle` is optional and only names the slide in the PPT Designer viewer.
- A row without `Source Dataset` or `Chart type` takes the structural type of its layout: `Title Page` is a Title Slide, `Transition` and `Title Only` a Transition Slide and `Black logo end slide` an End Slide. A row on `Black logo end slide` is an End Slide also when it still says `Title Slide` or `Transition Slide` (for example a transition moved to the closing layout). Saving the template writes that `Chart type` in the row.
- Title and Transition subtitles use the template's yellow accent (theme accent 4) in exported presentations, whatever layout hosts them.
- Every Title or Transition slide after the cover is a transition with its counter (01, 02…) above its title, with the sizes and places of every transition of the reports.
- In PPT Designer, a Title Slide that opens the Design also lists the Scope, Regions and Cities below its subtitle and decorative line, in the viewer and in the exported PPT.

```text
Slide: 1
Slide Tittle: NetCheck 5G Executive Design
Slide Subtittle: 2026-Q2 · Operator Comparison
Layout: Title Page
Chart type: Title Slide
```

```text
Slide: 6
Slide Tittle: Voice service analysis
Layout: Title Only
Chart type: Transition Slide
```

```text
Slide: 18
Layout: Black logo end slide
Chart type: End Slide
```

### Supported chart types

Automated rows support:

- `100% Stacked Vertical Bars`
- `Count Stacked Horizontal Bars`
- `CDF Line`
- `Histogram Line`
- `Histogram Bars`
- `Multi KPI CDF Lines`
- `Scatter`
- `Map`
- `Table`
- `Average Vertical Bars`
- `Median Vertical Bars`
- `Distribution Stacked Vertical Bars`
- `Threshold Stacked Vertical Bars`
- `Horizontal Bars`, `Dot Plot`, `Bullet Graph`
- `Highlight Table`, `Bar Table`, `Heat Map`
- `Pie`, `Donut`
- `Lines`, `Dual Lines`, `Areas`, `100% Stacked Areas`, `Bars and Line`
- `Box Plot`
- `Symbol Map`, `Filled Map`
- `Treemap`, `Packed Bubbles`, `Sankey`, `Gantt`

Choose a KPI and at least one Rows or Columns Split dimension. `CDF Line` creates one curve per complete aggregation combination. Count charts retain empty combinations where required so comparisons remain aligned.

The RF Quality template includes combined Data/Voice/Speech slides before each chart family. Its `CDR-All` source is virtual: it uses the selected physical datasets and creates no duplicate CDR dataset or database table. Templates containing this source are retained by JSON/CSV import/export, workspace transfers and backup/restore.

`Histogram Bars` uses the same bins as `Histogram Line`, with side-by-side Campaign bars and lighter shades for older Campaigns. Paired LTE/NR rows can use a dynamic layout with `Dynamic Columns Field = Operator` to show all selected Operators on one slide.

`Histogram Line` draws an unfilled step contour for each aggregation combination. Set `Bin Size = 5` in Filters for 5-unit bins, or `Bin Size = 1` for 1-unit bins. The vertical axis shows the percentage of valid samples in each bin, normalized independently per series; series models retain sample counts. Histograms reuse CDF colours, progressive campaign widths and multivendor operator line patterns. Add four `Buckets = ...` thresholds for five red-to-green quality background bands. Add `Class Colours = Quality` to matching distribution charts to use those same five class colours. The existing template/JSON export, import and backup workflows preserve these chart settings.

Axis ranges are visual settings, not data filters, and are available to every chart family with a numeric axis. For example, `Axis X Range: [0.01,]` starts the horizontal axis at `0.01` while retaining its automatically calculated maximum; `[,30]` retains the automatic minimum and fixes the maximum at `30`. Empty range cells preserve the existing automatic behaviour.

Percentage axes continue to use values from 0 to 100, while count, KPI, coordinate and scatter axes use their native units. Category axes and tables have no numeric domain to constrain.

`Label` is available to every chart family. For bars, `None` hides values, `Top` places them outside the bar, and `Up`, `Middle` and `Down` place them inside near the leading edge, centre or origin edge; horizontal bars map those directions to outside-right, inside-right, centre and inside-left.

For CDF, scatter and map charts the same setting places point or endpoint labels around the plotted mark. An empty cell preserves each renderer's existing automatic behaviour.

`Exclude Null/Empty` and `Exclude Zero` are independent and apply to every chart family. For scatter charts the exclusions are checked on both plotted axes; for CDF and Multi KPI CDF charts they are checked on each plotted metric before the cumulative distribution is calculated.

This allows a CDF to begin at its first non-zero observation instead of merely hiding the zero-valued section with an axis range.

The chart types of Tableau's Show Me that the list above adds after `Threshold Stacked Vertical Bars` read the shelves as follows. Their names carry no aggregation: the aggregation of the measure (`MEDIAN(Mean_Data_Rate)`, `COUNT(Test_ID)`…) chooses it, an average for a number and a count for a dimension when it has none. They draw a legend of what their colours mean (Format → Legend → Hidden hides it), and a time grouped by a period (`DAY(Test_Start_Time)`, `WEEK(…)`, `HOUR(…)`, `MONTH(…)`) on Columns gives Lines, Dual Lines and Areas a time axis.

| Chart type | Measure | Rows | Columns | Settings |
| --- | --- | --- | --- | --- |
| `Horizontal Bars` | One measure | The bars, one band per value | A bar per value inside each band, in its colour | `Sort = Descending` or `Ascending` orders the rows by their largest bar |
| `Dot Plot` | One numeric measure | The rows | A dot per value on each row, joined by a line | — |
| `Bullet Graph` | One numeric measure; a second one is the target of each bar | With Columns, a bullet per combination | | `Target = 20`, `Target = Previous campaign` (the latest campaign against the one before, Campaign on Rows or Columns) or `Target = Best competitor` (Operator on Rows or Columns); `Buckets` draw grey bands; `Direction` |
| `Highlight Table` | One measure | Table rows | Table columns | Cells coloured by their value: five ranges of the values, or the five classes of `Buckets` (four limits); `Direction` |
| `Bar Table` | One measure | Table rows | Table columns | Each cell has a bar as long as its share of the largest value of its column |
| `Heat Map` | One numeric measure; a second one sizes the squares (else their samples) | The rows of the grid | The columns of the grid | `Buckets`, `Direction` |
| `Pie`, `Donut` | A dimension (its values are the slices), or a measure counted (or summed with `SUM`) by the values of Columns | One pie per value | The slices of a measure | A Donut writes its samples in the middle |
| `Lines` | One numeric measure | One line per value | The horizontal axis | — |
| `Dual Lines` | Two numeric measures: the second one dashed, on the right axis | One line per value and measure | The horizontal axis | — |
| `Areas`, `100% Stacked Areas` | A dimension (an area per value, one chart per value of Rows) or a measure (an area per value of Rows) | See Measure | The horizontal axis | 100% draws the shares |
| `Bars and Line` | Two measures: the bars (left axis), then the line (right axis) | The bars side by side and one line per value | The horizontal axis | — |
| `Box Plot` | One numeric measure | With Columns, a box per combination | | `Whiskers = P10-P90` (default), `P5-P95`, `P25-P75`, `Min-Max` or `1.5 IQR`; the line is the median, ◇ the mean |
| `Symbol Map` | `Latitude vs Longitude`, and a third measure colouring the circles | A circle per value at the middle of its samples (without Rows, squares of a grid) | One map per value | `Buckets`, `Direction` |
| `Filled Map` | One numeric measure | | One map per value | The [Map Areas](workspace-config.md#map-areas) of the CDRs coloured by the measure of their tests; `Buckets`, `Direction` |
| `Treemap` | A measure: the samples size the rectangles (the measure with `SUM` or `COUNT`); a second measure, or an averaged one, colours them | The levels of the rectangles, then Columns | | `Buckets`, `Direction` |
| `Packed Bubbles` | As Treemap | A bubble per combination of Rows and Columns | | `Buckets`, `Direction` |
| `Sankey` | A measure: its samples (or `SUM`) are the width of each flow | The first levels | The last levels (two to five levels in all) | — |
| `Gantt` | A time, and a second one as its end (`Test_Start_Time vs Test_End_Time`) | One lane per value | A bar per value in each lane | `Date Bin = Day` (default), `Hour`, `Week` or `Month`: the periods with samples, joined while they follow one another |

`Direction` says which values the colours show as good: by default the KPI tells (lower is better for durations, latencies, errors and failures; higher for throughput, RSRP, SINR, MOS…), `Higher is better` or `Lower is better` say it, and `Neutral` (or a KPI without a direction, such as a count) uses blues. These settings are kept among the Filters of the row, as `Threshold`, `Buckets` and `Bin Size` are, and are set under the chart types.

### Chart recipes

The examples show chart-specific cells. Add the shared `Slide`, titles and `Layout` appropriate to the target layout.

#### 100% Stacked Vertical Bars

Use for proportions, success ratios and categorical quality splits. KPI categories become stack segments.

```text
Source Dataset: CDR-Voice
KPI: Call_Status
Chart type: 100% Stacked Vertical Bars
Filters: Call Family IN (VoLTE, MultiRAB); Operator IN (Vodafone, 3, EE)
Rows Split: Call Family
Columns Split: Operator × Campaign
Legend Position: Right
```

#### Count Stacked Horizontal Bars

Use for event or failure counts. Rows form horizontal categories and the KPI normally supplies statuses or causes.
Column hierarchy headers keep complete aggregation values in both the Design canvas and exported PowerPoint chart. Each successive level uses a smaller font, which can shrink further to fit narrow columns; the final header row has its own space above the data.

```text
Source Dataset: CDR-Data
KPI: Test_Result
Chart type: Count Stacked Horizontal Bars
Filters: Test Family IN (FDFS, FDTT); Test_Result IN (Failed, Dropped)
Rows Split: Test Family × City
Columns Split: Operator × Campaign
Legend Position: Bottom
```

#### CDF Line

Use for continuous metrics such as throughput, duration, latency or MOS.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: CDF Line
Filters: Test_Result = Completed; Test_Name CONTAINS FDFS; Direction = DL
Rows Split: Operator
Columns Split: Campaign
Legend Position: Bottom
```

With two operators and two campaigns this produces four curves. With multiple campaigns, the latest campaign is emphasised within each comparison family.

#### Multi KPI CDF Lines

Separate continuous KPI names with `|`. The renderer keeps the shared filters, Rows Split, Columns Split and legend and places one CDF panel per measure.

```text
Source Dataset: CDR-Data
KPI: NR_PCell_SINR_Avg | LTE_PCell_SINR_Avg
Chart type: Multi KPI CDF Lines
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT
Rows Split: Operator
Columns Split: Campaign
Legend Position: Right
```

#### Average Vertical Bars and Median Vertical Bars

Use Average for mean values or Median when outliers should have less influence.

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Average Vertical Bars
Filters: Call_Status = Completed; Call Family = WhatsApp
Rows Split: Operator
Columns Split: Campaign
Legend Position: Top
```

Change only `Chart type` to `Median Vertical Bars` for the median.

#### Distribution Stacked Vertical Bars

Use explicit numeric ranges with `Buckets = ...`, or ordered upper bounds with `Buckets < ...` / `Buckets <= ...`. Upper-bound mode generates `belowN` categories plus `Above`; use `Rate Bucket` as the final column aggregation.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: Distribution Stacked Vertical Bars
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT; Buckets < 2,5,20,100
Rows Split: Operator
Columns Split: Campaign × Rate Bucket
Legend Position: Right
```

With upper-bound mode, `Buckets < 2,5,20,100` evaluates each value against the limits in order and produces `below2`, `below5`, `below20`, `below100` or `Above`. Use `Buckets < 1,3,10,20` for the corresponding FDTT UDP UL distribution. `<=` is also accepted when boundary values must remain inside their named bucket.

Explicit ranges such as `Buckets = 1,5,20` produce `<1`, `1-5`, `5-20` and `20+`. Negative limits use `to`, so `Buckets = -110,-100,-90,-80` produces `< -110`, `-110 to -100`, `-100 to -90`, `-90 to -80` and `-80+` for RSRP. Stacked segments and legend entries always follow ascending numeric order, regardless of the order in which values appear in the CDR rows.

#### Threshold Stacked Vertical Bars

Use for a below/above distribution around one threshold.

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Threshold Stacked Vertical Bars
Filters: Call_Status = Completed; Call Family = VoLTE; Threshold = 1.6
Rows Split: Operator
Columns Split: Campaign
Legend Position: Right
```

The legend shows the configured threshold, for example `< 1.6` and `≥ 1.6`; `Threshold = -110` produces `< -110` and `≥ -110`.

#### Scatter

Use `Metric vs Dimension` to compare a KPI with a radio or quality dimension.

```text
Source Dataset: CDR-Speech
KPI: LQ vs Playing_RSRP_NR_Avg
Chart type: Scatter
Filters: Call_Status = Completed; Call Family = WhatsApp
Rows Split: Operator
Columns Split: Campaign
Legend Position: Bottom
```

#### Map

Use latitude and longitude in `Latitude vs Longitude` order. Rows Split, Columns Split and Legend determine point grouping and colour.

To colour a radio-quality map by a measured value, use `Latitude vs Longitude vs Measure`, set **Rows Split** and **Legend** to `Value Bucket`, and define four ascending thresholds with `Buckets = ...`. For example, RSRP uses `Buckets = -110,-100,-90,-80`, and SINR uses `Buckets = 0,5,13,20`. These five ranges use red, orange, yellow, light green and green. Missing measurements are excluded when **Exclude Null/Empty** is enabled. Two-field maps retain their existing grouping colours.

```text
Source Dataset: CDR-Data
KPI: Test_Start_Latitude vs Test_Start_Longitude
Chart type: Map
Filters: G_Level_4 = London
Rows Split: Operator
Columns Split: Campaign
Legend: Test_Result
Legend Position: Right
```

#### Table

Use when exact values are more useful than a chart. Rows and columns form the axes; KPI supplies the aggregated cell value.

```text
Source Dataset: CDR-Voice
KPI: Call_Setup_Time
Chart type: Table
Filters: Call_Status = Completed
Rows Split: City
Columns Split: Operator × Campaign
Legend Position: Top
```

#### Horizontal Bars

A ranking of cities by the median throughput of each operator.

```text
Source Dataset: CDR-Data
KPI: MEDIAN(Mean_Data_Rate)
Chart type: Horizontal Bars
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT; Sort = Descending
Rows Split: City
Columns Split: Operator
```

#### Bullet Graph

The latest campaign of each operator against the previous one, over grey bands.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: Bullet Graph
Filters: Test_Result = Completed; Target = Previous campaign; Buckets = 50, 100, 200, 300
Rows Split: Operator
Columns Split: Campaign
```

#### Lines over time

The weekly median throughput of each operator.

```text
Source Dataset: CDR-Data
KPI: MEDIAN(Mean_Data_Rate)
Chart type: Lines
Filters: Test_Result = Completed
Rows Split: Operator
Columns Split: WEEK(Test_Start_Time)
```

#### Box Plot

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: Box Plot
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT
Rows Split: Operator
Columns Split: Campaign
```

#### Filled Map

```text
Source Dataset: CDR-All
KPI: MEDIAN(NR_PCell_RSRP_Avg)
Chart type: Filled Map
Filters: Buckets = -110, -100, -90, -80
Columns Split: Operator
```

#### Sankey

How the tests of each operator flow through their RAT to their result.

```text
Source Dataset: CDR-Data
KPI: COUNT(Test_Result)
Chart type: Sankey
Rows Split: Operator × RAT
Columns Split: Test_Result
```

#### Gantt

The days each city was measured, by operator.

```text
Source Dataset: CDR-Data
KPI: Test_Start_Time vs Test_End_Time
Chart type: Gantt
Filters: Date Bin = Day
Rows Split: City
Columns Split: Operator
```

### Template filter language

Conditions are joined with logical AND and separated by `;`. Column matching is case-insensitive.

```text
Call Family IN (VoLTE, MultiRAB); Direction = DL; Vendor NOT CONTAINS (Mixed, Other)
```

| Operator | Example |
| --- | --- |
| Equals / not equal | `Call_Status = Completed`, `Operator != EE` |
| List inclusion / exclusion | `Operator IN (VF, O2, 3, EE)`, `Campaign NOT IN (2025-Q4)` |
| Contains / not contains | `Test_Name CONTAINS FDFS`, `Vendor NOT CONTAINS (Mixed, Other)` |
| Numeric comparison | `LQ < 1.6`, `Mean_Data_Rate >= 20` |

`Vendor` filters the vendor alone and `Operator_Vendor` the `<Operator>_<Vendor>` identity. Import accepts the former `Vendor_Only` and `Vendor V3` (as `Vendor`) and `OP_Vendor` (as `Operator_Vendor`) filter names, and templates written for earlier versions are converted once: their `Vendor` groupings and legends become `Operator_Vendor` and their `Vendor_Only` filters become `Vendor`, so their charts stay identical. Operator-prefixed filter values are resolved using workspace operator aliases when the report runs. This alias handling applies to filter fields, while aggregation fields keep their selected comparison semantics.

`IN`, `NOT IN`, `CONTAINS` and `NOT CONTAINS` accept comma-separated values. Parentheses are optional in Filter Builder input. A comma separates values within one condition; use `;` between independent conditions. `Threshold = 1.6` configures threshold charts and `Buckets = 1,5,20,100` configures distribution ranges.

### Rows Split, Columns Split and legends

Selection order defines the hierarchy:

```text
Rows Split: Call Family × G Level 4
Columns Split: Operator × Campaign
```

- Rows supplies chart categories or table rows.
- Column supplies comparison series or table columns.
- Blank Columns Split creates one `(all)` comparison.
- `Campaign` is ordered chronologically from oldest to newest.
- In Multivendor scope, `Operator` aggregation resolves to the mapped comparison field; an Operator filter still applies to the physical CDR Operator field.

Legend behaviour:

- Blank draws no legend.
- A KPI or aggregation dimension shows plotted values.
- A field used only by Filters shows its applied values as contextual text.
- CDF handles reproduce series colour and relative line width.
- Threshold legends show below/above colours and the configured value.
- Bucket legends show readable ranges derived from `Buckets`.

Top/Bottom produces a compact horizontal legend; Left/Right produces a vertical legend and reserves plot space.

### Multi-chart slides, operators and colours

Rows sharing a `Slide` number create separate charts on one slide. They must share `Slide Tittle`, `Slide Subtittle` and `Layout`, may use different sources, KPIs, filters and chart types, and require at least as many placeholders as chart rows.

Operator and Vendor aliases resolve to the canonical values configured in Workspace Config without changing the source workbook. Their table order controls Operator, Subscriber, Vendor and combined Operator_Vendor chart dimensions. Each canonical row defines its chart theme colour; multiple campaigns or operators using one identity receive contrasting shades derived from that colour.

### Chart layouts

The editor offers **121 layouts**: every combination of **1–6 rows × 1–6 columns**, each without comments, with comments below, or with comments to the right (108 fixed grids), plus nine dynamic layouts and `Title Page`, `Title Only`, `Transition` and `Black logo end slide`. The physical layouts appear immediately after `Black Title Page` in the same order as the selector, excluding the virtual dynamic options.

Names follow `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right`. The 108 fixed grids and four structural layouts exist physically in the reference PPT. `Source Dataset = CDR-All` exposes the union of Data, Voice and Speech fields, including normalized RF fields and `CDR_Type`, in cell assistance. The nine dynamic options are virtual: the renderer selects a fixed grid from the distinct values of their row and column fields. The widened Layout cell-assistance selector lists Title Page, Title Only, Transition and Black logo end slide first, followed by the nine dynamic grids and then the fixed grids. Long names stay on one line; narrow screens can scroll horizontally. Structural layouts have blue shading, dynamic layouts purple shading and the selected option yellow shading; selection retains its position without a duplicate at the top. Other native layouts remain internal to structural slides. Historic layout names are normalized on import and in stored templates; exports use the canonical names. Grids without comments use the full chart area.

### Dynamic chart grids

CSV imports identify columns by name and accept them in any order; duplicate names or aliases are rejected. The editor and exported CSV place **Dynamic Rows Field** and **Dynamic Columns Field** immediately after **Layout**. Use these fields to choose which source field creates the rows and columns. A dynamic layout requires a non-empty field for each dynamic axis; the parser rejects missing fields. Leave the field for a fixed axis empty. CSV exports include both columns; template import/export, transfers, backup and restore preserve them. Older CSVs with `Dynamic Field` remain importable: its value is assigned to the dynamic axis declared by the layout.

| Layout | Repeated dimension | Commentary |
|---|---|---|
| `Title + 2 rows + dynamic columns` | Columns | None |
| `Title + 2 rows + dynamic columns + comments down` | Columns | Below |
| `Title + 2 rows + dynamic columns + comments right` | Columns | Right |
| `Title + dynamic rows + 2 columns` | Rows | None |
| `Title + dynamic rows + 2 columns + comments down` | Rows | Below |
| `Title + dynamic rows + 2 columns + comments right` | Rows | Right |
| `Title + dynamic rows + dynamic columns` | Rows and columns | None |
| `Title + dynamic rows + dynamic columns + comments down` | Rows and columns | Below |
| `Title + dynamic rows + dynamic columns + comments right` | Rows and columns | Right |

- **Two fixed rows:** use two chart definitions on the slide with the same Layout and Dynamic Columns Field. The first fills the top row and the second the bottom row.
- **Two fixed columns:** use two chart definitions with the same Layout and Dynamic Rows Field. The first fills the left column and the second the right column.
- **Both axes dynamic:** use one chart definition and two different fields, for example `Region` for rows and `Operator` for columns. Each chart includes only samples matching both values.

Distinct values come from the selected, filtered CDR universe; empty values are excluded. Both-axis grids paginate at six rows and six columns. Multivendor grids also paginate at six repeated values, keeping operators of the same vendor together where possible. Larger ordinary single-axis grids can be derived from the native geometry; charts become smaller as the grid grows.

> [!TIP]
> **Readability:** a 6 × 6 grid fits 36 charts, but gives each chart little space. Prefer fewer charts when labels or distributions need close inspection.

For RF histograms, select **Operator**: the first definition is LTE and the second NR, so each Operator occupies one column. Campaigns remain grouped inside each chart. Changing filters changes the number of columns; LTE and NR keep their corresponding positions even when one technology has no valid samples.

> [!NOTE]
> **Vendor comparison:** When **Report type** is **Multivendor Comparison**, the **Vendor comparison** selector appears to its right. **Vendor Only (All Operators Combined)** is the first and default option when opening the export dialog; it pools selected operators using the same `Vendor` value. Choose **Operator - Vendor** to keep each operator separate. Campaigns remain separate. The job retains this choice for retries. Dynamic vendor grids use up to six columns per slide and keep operators of the same vendor together where possible.

## Portability and maintenance

**Export Design** creates a versioned ZIP accepted by Admin Import; imports also accept legacy standalone JSON definitions. A compatible destination template is required.

PPT Designer was called **PPT Dashboards**, and its Designs **Dashboards**. A workspace of before keeps them when it opens: its Designs, their PPT jobs and charts (moved to `output/reports/ppt-designs`), drafts, pictures and App Events take the new names, and the Modules Profiles, Interface Settings, tickets and scheduled backups name PPT Designer. Links to `/ppt-dashboards`, to this chapter and to the presentation of PPT Dashboards open those of PPT Designer, and packages, backups, transfers, Reporting Jobs and Bundle Report Templates of before are imported as Designs.

| Included in the definition | Not copied by PPT definition export |
| --- | --- |
| Name, NR Mode of its CDRs and template association | Source CDRs |
| Scope, dates, saved filters (Campaign included), hidden/additional fields, parameter values | Prepared cache files |
| Slide comments | Generated presentation assets |
| Its differences from the template, or its own slides once detached | Unsaved Designer drafts |

A Design chooses its CDRs from its NR Mode and Campaign in the workspace where it is opened, so an imported Design uses the CDRs of the destination with the same campaigns (Latest campaign, Latest 2, 3 and 4 campaigns and Previous campaign, among its newest ones). Designs exported by earlier versions with CDRs of their own take the campaigns of the CDRs of the destination with the same name and type, or else its newest two campaigns; check the inputs after import. Designs exported when templates had an NR Mode of their own read that NR Mode as part of their selection and use their template as the destination knows it now (its NSA and SA copies merged into one); an SA Design named as an NSA one takes " (SA)".

Designs have their own Admin export/import/transfer/backup/restore component: an import or transfer replaces the Designs the destination has (found by their identity, so one renamed on the source server is renamed there too, or by name) and adds the others, and so does a restore (see [Matching and creators](administrator-config.md#matching-and-creators)). Full Workspace and Full Environment include definitions from selected workspaces, with Designs listed after Application Config.

> [!TIP]
> Verify the template and Campaign after moving a Design to another workspace. Its CDRs do not travel with it: it uses the CDRs of the destination for its campaigns.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| View PPT or Generate PPT is disabled | Inspect its status badge and explicit preparation task |
| A filter has no choices | Verify source field/aliases and whether other filters leave matching rows |
| Chart says no CDR is selected | Choose a Campaign with a CDR of the type that chart needs, or check its Active? choice in Workspace |
| Filtered rows are zero | Check dates and empty value selections; use Clear Filters to remove restrictions |
| Chart is empty with nonzero rows | Check its source type, template filters, NR Mode and chart Dataset |
| Multivendor is unavailable | Check at least two Vendors and persist mappings for selected CDRs |
| Preparation failed or stays queued | Inspect App Logs and retry; clear derived PPT cache only if invalid |
| Viewer and old export differ | Compare applied live inputs with the completed job's saved snapshot |

> [!WARNING]
> Clear cache is a recovery action for derived artifacts, not a substitute for fixing missing source data, Vendor mappings or an invalid template. Inspect the cause first.

> [!NOTE]
> **Viewer comparison:** In the PPT viewer, selecting **Multivendor Comparison** reveals **Vendor comparison** to the right of Scope. Choose **Vendor Only (All Operators Combined)** to pool operators sharing a vendor, or **Operator - Vendor** to keep their results separate. Changing this selector renders the Design again immediately. Switching into multivendor scope defaults to Vendor Only; saved Designs retain their saved comparison. Use **Save Universe** to persist the choice.

> **Vendor comparison:** When **Report type** is **Multivendor Comparison**, the **Vendor comparison** selector appears to its right. **Vendor Only (All Operators Combined)** is the first and default option when opening the export dialog; it pools selected operators using the same `Vendor` value. Choose **Operator - Vendor** to keep each operator separate. Campaigns remain separate. The job retains this choice for retries. Dynamic vendor grids use up to six columns per slide and keep operators of the same vendor together where possible.

### Vendor-only report ordering

For **Vendor Only (All Operators Combined)**, web charts/tables and PowerPoint reports list actual vendors alphabetically, then Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operator-only identities labelled **Operator - All**, and finally Mixed (non-Ericsson). This order also applies to dynamic chart grids. Mixed/Other groups remain visible unless an explicit template filter excludes them. Vendor mapping persists `Operator - All` in `Operator_Vendor` and `Vendor` for operators without an assigned vendor. Existing values without the suffix remain compatible.

In multivendor charts, operator-only identities such as **EE - All** retain the colour assigned to that operator in Operator mappings. This applies to web and newly generated PPT charts; the display suffix does not create a new colour identity. Real vendors retain their configured vendor colours.

The default Campaign is **Latest 2 campaigns** for **Operator Comparison** and multivendor **Vendor Only**, and **Latest campaign** for multivendor **Operator - Vendor**. Changing the vendor comparison updates a Campaign that still has the default; a chosen Campaign is retained.
