# PPT Designer

Build an interactive Design (a PPT Design) from processed Data, Voice and Speech CDRs and export it to PowerPoint.

- **Start:** follow a PPT Template of the workspace, or start blank.
- **Explore:** apply one dataset selection to every slide and explore the live charts.
- **Change:** edit slides and charts on screen in the [Designer](#designer).
- **Export:** generate the PowerPoint in the background.
- **Templates:** the PPT Templates themselves are managed and edited here too.

> [!NOTE]
> **A Design is a saved definition, not a copy of your data.** It stores its template, Scope, dates, filters, the values of the template parameters, comments and what it changes of its template's slides. Its CDRs are chosen from its NR Mode and Campaign filter each time it is prepared. Source CDRs and generated caches remain separate.

## Presentation & Guide

```presentations
ppt-designer
guide:ppt-designer.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Check what a Design needs first | [Before creating a Design](#before-creating-a-design) |
| Create and manage Designs | [PPT Designs](#ppt-designs) |
| <span class="guide-sub">↳ Create a Design from a template</span> | <span class="guide-sub">↳ [Create a definition](#create-a-definition)</span> |
| <span class="guide-sub">↳ Show NSA and SA in one Design</span> | <span class="guide-sub">↳ [NSA & SA in one Design](#nsa-sa-in-one-design)</span> |
| Choose the campaigns, dates and operators of a Design | [PPT Scope & Filters](#ppt-scope-filters) |
| <span class="guide-sub">↳ Choose the scope of the CDRs</span> | <span class="guide-sub">↳ [PPT Scope](#ppt-scope)</span> |
| Understand the preparation and the cache | [Preparation lifecycle and cache](#preparation-lifecycle-and-cache) |
| <span class="guide-sub">↳ Know what Clear cache removes</span> | <span class="guide-sub">↳ [What Clear cache removes](#what-clear-cache-removes)</span> |
| Browse the slides and the data behind a chart | [View PPT](#view-ppt) |
| <span class="guide-sub">↳ Comment, present and use the floating tools</span> | <span class="guide-sub">↳ [Comments, Presentation and floating tools](#comments-presentation-and-floating-tools)</span> |
| Change the slides, charts and texts on screen | [Designer](#designer) |
| <span class="guide-sub">↳ Edit the template or only this Design</span> | <span class="guide-sub">↳ [Template or This Design](#template-or-this-design)</span> |
| <span class="guide-sub">↳ Add and change the charts of a slide</span> | <span class="guide-sub">↳ [Charts on the slide](#charts-on-the-slide)</span> |
| <span class="guide-sub">↳ Change the parameters of the template</span> | <span class="guide-sub">↳ [Template parameters](#template-parameters)</span> |
| Export the presentation to PowerPoint | [Generate PPT](#generate-ppt) |
| Follow the exports running and done | [PPT Generation Jobs](#ppt-generation-jobs) |
| Pick charts from the Charts Panel | [Charts Panel](#charts-panel) |
| Create or edit a PPT Template | [PPT Templates](#ppt-templates) |
| <span class="guide-sub">↳ Edit a template as a table</span> | <span class="guide-sub">↳ [Table view (Template Editor)](#table-view-template-editor)</span> |
| Look up the template columns and chart recipes | [Report Template reference](#report-template-reference) |
| <span class="guide-sub">↳ See the supported chart types</span> | <span class="guide-sub">↳ [Supported chart types](#supported-chart-types)</span> |
| <span class="guide-sub">↳ Copy a chart recipe</span> | <span class="guide-sub">↳ [Chart recipes](#chart-recipes)</span> |
| Move, copy and maintain Designs and Templates | [Portability and maintenance](#portability-and-maintenance) |
| Fix empty charts or a slow preparation | [Troubleshooting](#troubleshooting) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Before creating a Design

1. Open the correct workspace and process the required CDR types.
2. Create or import a **Report Template** in **PPT Templates**, at the top of the PPT Designs library. A template serves the CDRs of any NR Mode.
3. For Multivendor Comparison, persist Vendor mappings first.
4. Open **PPT Designer**.

What each role can do is in [Who changes a Design](#who-changes-a-design). Designs use the same template schema and renderer as Reporting; template authoring is in the [Report Template reference](#report-template-reference).

> [!TIP]
> **First comparison:** create a Design (it compares the newest two campaigns of its NR Mode), choose its Scope, Campaign and other filters, apply them, then open **View PPT**. Inspect the charts before generating a PPT.

## PPT Designs

The library of the workspace: create, open, export and order the Designs.

### Create a definition

1. Click **Create PPT Design**, above the list of the Designs.
2. Enter its **PPT Name** (**My New PPT Design** is offered).
3. Select the **NR Mode** of the CDRs it reads: **NSA**, **SA** or **NSA & SA** (see [NSA & SA in one Design](#nsa-sa-in-one-design)).
4. Select a **PPT Template**, or open the **gallery** with the button beside it: a card per template with its first slides in small (chart pictures in their places, covers and transitions in colour), its number of slides and charts and **Default** on the default one; **None — blank PPT** comes first. A click chooses; <kbd>Esc</kbd> or **×** keeps the former choice.
5. Click **Create**. **Cancel**, **×** or <kbd>Esc</kbd> close the dialog without creating it.

- **With a template:** the Design opens in PPT Scope & Filters.
- **With None — blank PPT:** it opens in its [Designer](#designer) with only its cover, where its slides are added. It follows no template; **More → Save as template…** makes one of it.
- **Out of scope operators:** when the NR Mode leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), their tests are left out of the Design. Its CDRs Used and the viewer name them beside its Campaign and Scope (*Out of scope: SA · Three*).
- **Titles:** any template serves every NR Mode; its `{NR Mode}` and `{NR Mode Name}` titles name the NR Mode of the Design (see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)).
- **Import:** **Import PPT Design** imports a standalone JSON definition; the ZIP of **Export Design** goes through Admin Import (see [Portability and maintenance](#portability-and-maintenance)).

> [!NOTE]
> **Names are unique in the workspace**, whatever the NR Mode each Design reads: an NSA and an SA Design of the same template need names of their own (for example **NSA - NetCheck CDR Report** and **SA - NetCheck CDR Report**).

### NSA & SA in one Design

A Design of NR Mode **NSA & SA** reads the CDRs of both NR Modes, so a slide can put NSA and SA charts side by side and a chart can draw NSA and SA series together. Every row of the combined CDR tables keeps the NR Mode of its CDR in the **NR Mode** field (NSA or SA), so the NSA and SA tests of an operator are never added together.

- **Campaign filters:** **Campaign (NSA)** chooses the NSA CDRs and **Campaign (SA)** the SA ones, each with the campaigns and Latest choices of its NR Mode (for example Latest 3 campaigns in NSA and Latest campaign in SA). A Design saved without Campaign (SA), or generated in a report of [Reporting](reporting.md), uses its Campaign filter for both, each Latest choice resolved per NR Mode.
- **The NR Mode of a chart:**
  - A template row keeps one NR Mode with the filter `NR Mode IN (SA)` (or `NSA`) and then reads only those CDRs; without it, the chart reads every NR Mode the Design reads.
  - An NSA or SA Design only shows charts of its own NR Mode; NSA and SA charts together need a Design of NSA & SA. In a Design that does not read the NR Mode of a chart, the chart says so instead of showing data, and its `{NR Mode}` title names the NR Mode it shows.
- **NR Mode in splits and legends:**
  - **NR Mode** is a field of Rows Split, Columns Split, Legend and the Dynamic Rows/Columns Field (a dynamic grid can place the NSA chart above the SA one).
  - A chart that reads both NR Modes and is split neither by NR Mode nor by Campaign (the SA campaigns name their mode, such as 2026-Q3-SA) gets NR Mode as the last level of the split that holds its legend, and of its legend. Lines, Dual Lines, Areas, 100% Stacked Areas and Bars and Line get it in Rows, as their series, since their Columns are the horizontal axis.
- **Look of the series:** each operator keeps its colour in both NR Modes: its SA series use a lighter tint, and SA lines are dashed when dashes do not already tell operators apart. CDF campaign line widths are ranked inside each operator and NR Mode, so the newest NSA and SA campaigns are both thick.
- **Fields of one NR Mode:** a chart using a KPI, filter or split field that only the CDRs of one NR Mode have shows a note naming the NR Mode without samples (*The SA CDRs have no Mean_Data_Rate: no SA samples.*), and the template editor warns about it.
- The PPT file names and the viewer header name the NR Mode **NSA & SA**.

**Example:** every workspace receives once the example template **DT Analyzer - FDFS DL (NSA & SA)** and its Design of the same name (Latest 3 campaigns in NSA, Latest campaign in SA): a slide with the FDFS DL throughput CDF of NSA, that of SA and the FDFS DL transfer time of every campaign of both NR Modes.

### RF Quality Design

An existing or imported Design **RF Quality (RSRP & SINR)** can use the workspace template **RF Quality (RSRP & SINR)**: NR Mode NSA, Campaign **Latest 2 campaigns**; edit or delete it like any other Design. See [Network Insights](network-insights.md#rf-quality-template-and-design).

- **Slides:** separate LTE and NR RSRP/SINR CDF, average, distribution, threshold and quality-map slides for Data, Voice and Speech, followed by the NSA NetCheck black-logo closing slide. Each chart family starts with an **All CDR types** slide pooling valid Data, Voice and Speech observations (source `CDR-All`); LTE and NR remain separate.
- **CDF slides:** a two-by-two layout with LTE and NR above their contour histograms (5 dB RSRP bins; 1 dB SINR bins), with percentages per series, the CDF colours and campaign widths, the multivendor line patterns and red-to-green background bands matching the quality-class slides.
- **Grouped-bar histogram slides** follow each CDF/contour slide: `Title + 2 rows + dynamic columns + comments down` with `Dynamic Columns Field = Operator` gives one column per selected Operator, LTE above NR, comments beneath. Every bin has one bar per Campaign, oldest to newest, the newest in the Operator colour and older ones lighter; percentages use the same valid-sample denominator and bins as the contour histograms.
- **NR shares** use valid NR measurements and do not measure availability across the entire route.

### Row actions

| Action | Effect |
| --- | --- |
| **View PPT** | Open the interactive slide viewer |
| **Edit Design** (pencil icon) | Open the viewer in the [Designer](#designer), once the Design is prepared (users who can change the Design or its template) |
| **Generate PPT** (PPT icon) | Open the export selection dialog |
| **Duplicate** | Create an independent definition |
| **Export Design** | Download a versioned ZIP accepted by Admin Import |
| **Delete** | Remove the definition after confirmation (see [Who changes a Design](#who-changes-a-design)); its CDRs, template and PPT jobs stay |

**Close** leaves the active definition without deleting it.

**Order of the library:**

- Users who can change Designs drag a Design by the tab on the left of its name (or press <kbd>↑</kbd>/<kbd>↓</kbd> on the tab). The order is saved at once for every user of the workspace, without changing any Design.
- Until a Design is first moved, the library is sorted by NR Mode (NSA, NSA & SA, SA), then by name (an NR Mode written in a name, such as `NSA - Report`, is ignored). Designs created, duplicated or imported later go to the end.
- App Events record each new order (`reorder_designs`, names before and after); exports, transfers and backups carry it (see [Import / Export / Transfer](administrator-config.md)).

**Created by, Last Updated by and Last Updated:**

- The users who created and last changed each Design (first and last name, or username), and the date and time of that change (a dash when none is recorded, as in an unchanged starter Design).
- **A change** is one to its name, NR Mode or template, its Scope and filters, its slides or comments, or a template renamed or deleted that changes it; opening, generating its PPT or moving it in the library is not.
- A Design changed before these columns existed shows the last change its App Events recorded, or its creator.
- Exports, transfers and backups carry both names (see [Matching and creators](administrator-config.md#matching-and-creators)).

### Who changes a Design

A Design or a PPT Template is changed and deleted only by the user who created it and by super-admins, and by admins when a user-editor created it.

- **A change of a Design:** its name, NR Mode and template, its Scope and filters with **Save Filters**, its slides in the [Designer](#designer) or the comments saved in it.
- **A change of a template:** saved, renamed, overwritten on import, given copied slides or charts, edited in the Designer (Template scope, parameters) or from Chart Builder.

| Role | Changes and deletes (Designs and templates) |
| --- | --- |
| **super-admin** | Every one |
| **admin** | Those they created and those of user-editors; not those of another admin or super-admin, nor the starter ones, which belong to `super` |
| **user-editor** | Only those they created; **Save Design as** makes a variant of another one |
| **user-viewer** | None |

- **user-editor, admin and super-admin** also create, import and duplicate Designs (a duplicate is their own), open **PPT Templates**, and open **Edit PPT Template** and **Auto-Calculated Fields** from the viewer.
- **The other users** see those controls disabled, with a tooltip naming who changes it. They still open a Design, apply other filters, generate its PPT and export it; a user-viewer sees and exports templates. They customize a template from the Designer of their own Designs.
- **Owner of a template:** the user who created it (New Template, Import CSV, Duplicate or **Save as template**); one brought by Admin Import / Transfer belongs to its creator on the source server when that user is active here, otherwise to the importer.
- App Events record each refused change as `ppt_designer_change_refused`, with the Design or template, the action, its creator and the reason.

### Change name, NR Mode or template

- **Name:** edit it in the column **PPT Name** and confirm with the green check (on a phone, **⋯ → Edit details** of its card).
- **NR Mode** and **PPT Template** have independent selectors: the NR Mode chooses the CDRs the Design reads and keeps its template.
- **A blank Design** shows **None — blank PPT**: choosing a template makes it follow it, its own slides replaced by those of the template after a warning.

> [!WARNING]
> **Changing NR Mode or Template invalidates the prepared charts.** The application rebuilds them.
> An NR Mode change keeps the campaigns of an NR Mode the Design still reads (NSA to NSA & SA keeps the Campaign as Campaign (NSA)) and sets the others to the newest campaigns of the new mode; the titles name the new NR Mode. A template-only change keeps the Campaign.

The Scope, dates, other filters, custom fields and comments are preserved. Only CDRs of the active NR Mode participate.

### Session and unsaved changes

- **Remembered:** the last open Design and page position during the authenticated session, and the open/closed state of the main filter panel (collapsed in a new session).
- **Unsaved filters:** leaving with unsaved Scope, date or filter changes asks for **Save Filters**, **Discard** or **Cancel**. After **Save Filters** nothing is left unsaved, also while the saved filters are being applied, so closing, opening the viewer or leaving asks nothing. The name, NR Mode and Template inputs never raise filter warnings.
- **Logging out** clears the open-Design, preview and scroll state; saved definitions remain.

## PPT Scope & Filters

Choose which CDRs, campaigns, dates and values the slides of a Design show.

**PPT Filters**, at the top of the viewer, opens this panel over the slides; a Design just created, duplicated or imported opens in its viewer with it. The table of the Designs never opens the filters.

### How the CDRs are chosen

A Design has no CDR selector: the **Campaign** filter (the first Default Filter) and its NR Mode choose its CDRs (with NSA & SA, Campaign (NSA) and Campaign (SA)). They are the CDRs of that NR Mode that the combined CDR tables include for the chosen campaigns (every campaign when Campaign is not restricted): the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains, or the **Active?** choice of the CDR in Workspace when it was changed (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

**Automatic campaign choices**, offered first and made again whenever the Design is prepared or exported, so they follow the campaigns that arrive later:

| Choice | Chooses |
| --- | --- |
| **Latest campaign** | The newest campaign |
| **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns** | The newest two, three or four campaigns |
| **Previous campaign** | The one before the latest; with a single campaign, none |
| **All available campaigns** | Every campaign of the NR Mode at that moment, also those that arrive after it is saved (unlike every campaign checked by hand) |

- **Not counted:** [Flex campaigns](workspace-management.md#flex-campaigns) (local campaigns, complete but localised in one region, cluster or city, whose campaign or Campaign Maps label has the word Flex, such as `26-Q2-Flex`) and [campaigns in progress](workspace-management.md#campaigns-in-progress) (Weekly or Daily CDRs only, no Final yet). A Campaign filter without campaigns does not count Flex ones either: they are used only when checked by hand.
- **Each choice stands alone:** checking it clears the other one and the campaigns, checking a campaign clears it, and **Select All / None** checks or clears the campaigns only.
- **Default:** see [PPT Scope](#ppt-scope). CDRs without Campaign values are used when no campaign is chosen.
- **Earlier Designs** that chose their CDRs by hand take, once, the campaigns of those CDRs as their Campaign filter (keeping one they already had); those without saved CDRs take the default of their Scope.

**CDRs Used**, below the Scope, lists by type (Data, Voice and Speech, about three each, the rest scrolling) the CDRs the current selection chooses, newest campaign first, with stage and campaigns (Weekly and Daily outlined). It follows every change of the NR Mode or filters at once, before they are applied, and says when they must be applied. The Campaign, Operator, Vendor, Region, Cluster and City lists follow the same way, and an open list stays open while values are checked.

### PPT Scope

| Scope | Comparison | Default Campaign |
| --- | --- | --- |
| **Operator Comparison** | Normalized Operator values | Latest 2 campaigns |
| **Multivendor Comparison** | Operator/vendor hierarchy | Latest 2 campaigns (Vendor (All Operators Combined)), Latest campaign (Operator_Vendor) |

- **Saved with the filters:** the Scope and vendor comparison are applied and saved with the filters (**Save Filters** persists them). Changing the Scope or vendor comparison updates a Campaign that still has the former default; a chosen Campaign is kept.
- **Vendor comparison** shows beside Scope with Multivendor Comparison (in **Select Comparison Scope**, the viewer and the export dialog). **Vendor (All Operators Combined)**, first and the default when switching into multivendor or opening the export dialog, pools the operators sharing a vendor; **Operator_Vendor** keeps each operator separate. Campaigns remain separate; saved Designs keep their saved comparison, and a PPT job keeps its choice for retries.
- **In the viewer,** the Scope control asks for confirmation, then renders the charts again with the PPT filters; a change of the vendor comparison renders the Design again at once.
- **Vendor order:** with Vendor (All Operators Combined), charts, tables, PPTs and dynamic grids list real vendors alphabetically, then Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operator-only identities **Operator - All**, and last Mixed (non-Ericsson). Mixed/Other groups stay visible unless a template filter excludes them.
- **Colours:** an operator-only identity such as **EE - All** keeps the colour of that operator in Operator mappings (the suffix creates no new colour); real vendors keep their vendor colours.
- **Every test of the NR Mode:** a Design reads every Data, Voice and Speech test of the CDRs of its NR Mode, whatever RAT or call mode it ran on (an EPS fallback call of an SA CDR is an SA test). Use the **RAT** filter for a narrower technology selection.

> [!IMPORTANT]
> **Multivendor requires mapped Vendors.** The workspace must have at least two distinct cached Vendors (otherwise Multivendor is unavailable), and the chosen CDRs must satisfy the mapping/comparison requirements. A single-vendor selection cannot produce a Multivendor comparison.

### Dates

**Date from** and **Date to** open the Default Filters and are applied and saved with them.

- **Oldest** / **Newest** resolve the first or last available date of the chosen CDRs during preparation (**Use oldest** / **Use newest** restore them; the fields show the resolved date, such as `Oldest (2026-01-01)`); a chosen calendar day is fixed.
- **Date to** includes the whole day. Navigating calendar months changes nothing until you select a day.

> [!TIP]
> Use automatic bounds to include new campaigns without adjusting dates; use fixed dates for a reproducible time window.

### Read the row counts

- **CDRs used:** rows contributed by the chosen CDRs. **Filtered rows:** after dates and PPT filters. **Chart rows:** after that chart's template filters as well.
- Without date or adaptive-filter restrictions, the ready summary reuses the Design count so both agree; when the chosen CDRs hold only the chosen campaigns, Campaign needs no row restriction and the counts are kept.
- An empty chart can coexist with nonempty Filtered rows: its source type or chart filters may exclude the remaining rows.

### Default filters and aliases

**Order:** **Campaign → Operator → Operator_Vendor → Vendor_Operator → Vendor → Market → Region → Cluster → City → RAT → Session Type → Call Status**, after Date from and Date to. Technology is not an adaptive filter because NR Mode belongs to the definition.

**Vendor filters:**

- **Operator_Vendor** filters the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` (both in sync) and **Vendor** the vendor alone, from cached per-CDR values. Every vendor filter (PPT export, expanded charts and template filters included) uses these columns; the comparison mode still decides whether charts group by Operator_Vendor or by Vendor.
- **Vendor choices** list real vendors first, then Ericsson (Mixed) (and the former Mixed Vendor), Mixed (non-Ericsson) (and the former Other Vendor), All Vendor(s), and operators without vendors as **Operator - All** (stored so in both columns; older values without the suffix remain compatible).
- **Aliases:** the former `Vendor_Only`, `Vendor V3` and `OP_Vendor` names are accepted, and operator-prefixed values in a Vendor filter resolve to the vendor through the workspace operator aliases.

**Source columns** (per row, an empty higher-priority field falls back to the next; hover or focus the filter to see them):

| Visible filter | Source columns in priority order |
| --- | --- |
| Region | `Region` → `G_Level_2` → `G Level 2` |
| City | `City` → `G_Level_4` → `G Level 4` |
| Campaign | `Campaign` → `campaign` |
| RAT | `RAT_A` → `RAT` → `Sample_RAT_A` |
| Call Status | `Call_Status` → `call_status` → `status` |

**Choosing values:**

- Each multiselect has search, individual values and **Select All / None**; menus stay open while selecting and close after pointer exit.
- **Main Cities**, first in City, is saved as such and is the Main Cities of Workspace Config whenever the Design is prepared, exported or generated in a report of [Reporting](reporting.md) (every city while the workspace has none). It stands alone like the campaign choices. Designs saved before with exactly the Main Cities take it once.
- **Every value = unrestricted:** selecting every value (even the only one) makes the field unrestricted: it shows **All values** and includes new values of later CDRs.
- Applying or saving a changed Campaign reloads the choices of its CDRs; older truncated catalogues are completed from source rows.

> [!NOTE]
> **The filters follow each other.** Campaign lists every campaign of the NR Mode (with Campaign Maps labels); Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster and City list the values of the chosen CDRs (with Operator and Vendor Maps labels) that the other filters leave (Vodafone as Operator leaves only its Vendors), never narrowed by their own choice. They come from the **CDR Filter Facets** table, filled once per CDR when processed (older CDRs in the background when first needed), so they never read CDR rows; until then the catalogue values are offered.

> [!CAUTION]
> **Selecting no values returns no rows.** Selecting all values removes the restriction. This differs from modules where an empty filter means “all”. Use Clear Filters to remove restrictions deliberately.

### Additional Filters

1. Search **Select field to add new filter**.
2. Choose a CDR column or an applicable workspace Auto-calculated Field (it applies to its declared CDR types and is materialized into the combined CDR table when first needed).
3. Use **Add Filter**, then select its values; they load against the current CDRs, dates and filters without preparing the whole Design.

The circular **×** removes an additional filter or hides a default one after confirmation; the field picker restores a hidden default.

### Apply, Save, Clear and Reload

| Action | Changes the current view | Persists defaults |
| --- | --- | --- |
| **Apply Filters** | Scope, vendor comparison, dates and filters | No |
| **Save Filters** | Scope, vendor comparison, dates, filters, additional and hidden fields, and applies them | Yes |
| **Clear Filters** | Removes every restriction but the Campaign, which returns to its default | No |
| **Reload Saved Filters** | Restores the saved Scope, dates and filters | No |

**Apply Filters** and **Save Filters** are enabled as soon as a filter changes, also while the Design is being prepared: the new preparation replaces the running one.

> [!NOTE]
> **Apply is temporary; Save changes the PPT defaults.** You can preview or export an applied selection without saving it. Returning to an equivalent prepared selection reuses its cached charts.

When **View PPT** or **Generate PPT** finds unapplied edits (Scope and dates included): **Apply Filters and Continue**, **Discard and Continue** (back to the last applied filters), **Save and Continue**, or **Cancel**.

## Preparation lifecycle and cache

How a Design is prepared, kept in the cache and warmed up while the server is idle.

### What happens while preparing?

- **In the background:** the browser follows progress; a new request replaces the same user's previous one and stale responses are ignored. An equivalent selection prepared earlier in the session restores without recalculation.
- **The viewer opens at once,** with a yellow **Preparing PPT dataset** card until its requested slides are ready. View PPT, PPT Filters and PPT export are available at any time.
- **Task card:** user-requested tasks show in the floating task card, with **Interrupt task** when possible.

| Status | Meaning |
| --- | --- |
| **Checking Cache** | Waiting for the server's status of the Design |
| **Loading data / Rendering** | The Design is being prepared or its charts rendered for a user |
| **Data Cached** | The open Design is prepared; its charts render as they are viewed |
| **Ready** | The Design has CDRs to show; it is prepared when it is opened, or by the warm-up |
| **Data needed** | No CDR matches the Design's selection |

**When charts are calculated:** when viewed, refreshed or requested for PPT, or by the warm-up. The open slide comes first, each chart appearing when ready; then nearby slides prefetch one chart at a time (next, previous, two ahead, two behind), waiting while a newly opened slide is calculated. Opening one chart uses the chart sequence; closing the viewer stops further work.

### Warm-up while the server is idle

After 5 minutes without anyone using the application (and no other background work), the server **warms up** the open workspace, so after a restart Designs open at once with their charts drawn.

- **What:** one after another, every PPT Design and every PPT Template as **Edit** opens it (with the NR Mode and Campaign of each user who opened one, else NSA and Latest 2 campaigns); the chart models are kept in the cache folder.
- **Only what changed:** a chart keeps its model while the chart, its CDR selection and the mappings stay the same; a changed Design or template redoes only its changed charts, and all of them when its CDRs or filters changed.
- **Progress:** **Warming up PPT Designs** in the floating task card, with the Design or template and chart; **Interrupt task** stops it after that chart. It pauses as soon as someone uses the application or other work starts, and resumes where it was at the next idle time.
- **Skipped:** charts a selection cannot draw (the viewer says why) and Designs without CDRs.
- **App Events:** `design_warmup_started`, `design_warmup_finished` (charts worked out and kept, cache folder size) and `stop_design_warmup`.

**Without warm-up,** a Design not warmed up (or whose CDRs, filters or template changed) is prepared from the [columnar copies](workspace-management.md#columnar-copy-of-the-cdrs) of its CDRs: aggregating charts (CDFs, histograms, averages, stacked and grouped bars) are grouped by DuckDB on the copies, each distinct combination once with its row count; maps, scatter plots, tables and chart data views read their rows from the column cache. Changing Campaign, dates, filters or comparison recalculates from the columns in memory.

### What Clear cache removes

The combined CDR tables remain the source for filters and chart data; selection records keep counts, facets and reproducible predicates, and no CDR rows are copied into a separate projection database.

**Column cache in memory:**

- Each column a chart needs is read once per CDR, with the PPT filter columns (default filters, custom fields, event date), from the columnar copy when every copy of the selection holds its CDR as it is, else from SQLite; `CDR-All` pools Data, Voice and Speech without rereading the uploaded files.
- Any combination of CDRs, dates, filters and comparison is assembled in memory with exactly the rows, values, types and (for maps, scatter plots, tables and data views) order SQLite returns; when that order cannot be reproduced (filtering a single City, for example) those charts read SQLite directly. Row counts and distinct filter values are reused until a CDR changes, and charts sharing fields, or source, filters and measure, share one read and one filtering pass.
- Up to 1 GB by default, least recently used columns removed first (`DRIVETEST_ANALYZER_COLUMN_CACHE_MEMORY_MB`).

**Cache folder of the workspace** (`.cache/ppt-designer`, with `preparations/` and `charts/`):

- Preview manifests and Canvas chart models, in memory and as compressed files, keyed by dataset revisions, selection, scope, template and format, mappings and renderer version: other sessions and PPT exports reuse them, and after a restart prepared Designs open with their charts drawn.
- Files are written under a temporary name and renamed when complete; an unreadable file (crash, full disk) is deleted and worked out again, as are leftover temporary files.
- Up to 1 GB, least recently used first (`DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB`); files unused for 30 days are removed.
- Left out of backups, exports and transfers; moves with its workspace when renamed and is deleted with it. **Clear workspace cache** empties it (set aside at once, deleted in the background).
- **Earlier versions:** the PPT Preparation Cache and PPT Chart Models Cache tables move to the folder when the workspace opens (App Event `ppt_design_cache_moved_to_folder`) and are dropped; the `.design-data-cache` and `.design-chart-cache` folders are removed.

> [!WARNING]
> **Workspace Clear cache cancels active user-requested work and removes derived cache only.** It preserves PPT definitions, combined CDRs, templates and generated jobs. The warm-up rebuilds the cache the next time the server is idle.

## View PPT

Explore the slides and charts of a Design, live on its CDRs.

Open **View PPT** from the library or filter panel (**Edit Design** opens it in the Designer). It does not expand the main filters panel; use **PPT Filters**.

### Read the header

The viewer keeps the template's 16:9 layout in about 96% of the viewport; its header names the NR Mode, Design and slide position.

- Slide titles and golden-yellow subtitles display in capitals.
- Campaigns, Scope, Regions and Cities identify the applied selection; export snapshots show the selection of their PPT job.
- Campaign labels are compact, such as **26-Q2**, **26-Q2-NSA** or **26-Q2-SA** (see [Campaign ordering](technical-considerations.md#campaign-ordering)); older CDRs may fill them a few seconds after first opening.

### Slides and navigation

- **Slide selector:** jump to a slide; searchable, each choice with its number, purple title and teal subtitle separated by a bold ●.
- **Slides at the left** (wide screens; phones keep the selector): every slide in small, as in the [Help presentations](help.md#presentations), covers and transitions as in the viewer and charts once calculated, with number and title; the slide shown is marked. While designing they replace the slide selector.
- **Below the slide and its comments:** **Presentation** and **First / Previous / Next / Last**. Keys, the wheel over the slide and swipes also move through the slides (see [Tips & shortcuts](#tips-shortcuts)).
- **Top row** (wide screens): the slide selector with the two image buttons of the slide, **Scope**, **PPT Filters** and **Open Designer** with their names, then **Refresh Design** (refresh the preparation), **Auto-Calculated Fields**, **Edit PPT Template** and last **Generate PPT** as icons (point at one for its name). Narrow screens wrap the actions.
- **Scope** switches Operator/Multivendor after confirmation (see [PPT Scope](#ppt-scope)).

**Theme**, at the start of the floating section bar, colours the charts and slide titles of the viewer and of the PPTs with the themes of [Scoring & GAP Analysis](scoring-gap-analysis.md): **Ericsson** (default), **NetCheck**, **Umlaut**, **Vodafone**, **Midnight**, **Paper** and **Heatmap**.

- Charts take its font and colours for text, axes, grid lines, table headers and alternate rows; operator, vendor and threshold colours stay.
- The viewer's slide title and subtitle (still in capitals) and the titles of the PPT content slides take its title style, the distinguishing part in its focus style. Title and Transition slides keep the template look.
- **Midnight** paints the charts and content slides night blue (white logos), with tables, text and comments light on dark.
- **One theme per workspace** for each user and every themed module (also Scoring & GAP Analysis, Network Insights and CDR Analysis): a change restyles and redraws at once, is kept for the next visit and later PPTs, and is recorded in App Events.

**How slides look** (as in the exported PPT):

- **Title and Transition slides** keep the template look: Vodafone-Three red with the Ericsson mark, both logos top right, light two-line titles and the yellow subtitle; after the cover each shows its counter (01, 02…). The **Title cover** shows Campaigns above its divider and Scope, Regions and Cities beneath, in white with bold labels. The **End Slide** is the Ericsson mark and name centred on white (see [Structural slides](#structural-slides)).
- **Chart rows** keep template order and placeholder geometry. In grids of three or more rows or four or more columns each chart title is text above the chart; dynamic grids prefix it with the row or column value in bold (**EE** · LTE RSRP histogram).
- **Axis labels** and aggregation headers are never truncated: each level wraps onto two lines, shrinks or turns vertical, and the chart reserves the room.

**Comments area:**

- **comments right** layouts place comments beside the charts, **comments down** below; the area is always kept in the PPT. Without comments it shows a dashed frame and a muted *Comments* prompt.
- When the grid has free places (three charts on a 2 x 2 grid, or an unfinished **New chart**, which the PPT leaves empty), the comments take the largest free block (lowest, then rightmost) and the charts the same grid without comments.
- Layouts without comments use the full chart area: no Comments panel, and generated comments (one slide, all slides, Kiro brief, Auto comments) skip them.

### Live and expanded chart controls

Point at or focus a chart for **Dataset**, **Expand** and **Zoom** (on touch, a tap shows them for 3 seconds). While the [Designer](#designer) is open only **Dataset** and **Refresh chart** show. The gestures (larger view, zoom, pan, legend and axis clicks, undo) are listed in [Tips & shortcuts](#tips-shortcuts).

**Hidden values:**

- **Whole Design:** a value hidden from a legend or axis disappears from every series, bar, segment, row, column and category of every slide, at any level, and the chart closes the gap (hiding Operator VF_SA also hides each VF_SA Campaign). A hidden legend entry stays faded and struck through.
- **Right-click menus** of a legend entry or axis label offer **Keep only**, **Hide** or **Show**, **Hide All** and **Show All** for that legend or axis level, and list the values hidden elsewhere in the Design (an axis menu, those of its level too), each with a **Show** submenu.
- **Hidden (N)**, in the viewer while a value is hidden, lists them to **Show** one, **Show all** or **Undo** the last hide or show, even when nothing is left to click. In the Designer, **Undo** does so when it was the last change.
- **Dynamic grids:** the cards of a hidden value leave the slide and the rest fill a smaller grid; a slide with every card hidden offers **Show hidden values** and is left out of the PPT.
- **How long:** for the browser session, also in the expanded viewer. **Generate PPT** exports the charts as you see them, its job's viewer shows that state, and a relaunched job keeps it. (In Network Insights a legend click hides the entry in that chart only.)

**Images** (PNG download or clipboard screenshot, see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)): the whole slide from the two blue buttons beside the slide chooser (with its comments below as plain text), each chart (also a slide's only one) from the floating buttons left of its controls, the expanded chart from the buttons above it, and the Charts Panel and its thumbnails. App Events records each as `export_design_image`, with the slide or the Design and date of the PowerPoint job.

**The expanded viewer** has the viewer's actions above the chart (its image, **PPT Filters**, **Auto-Calculated Fields** and **Edit PPT Template** as icons), chart navigation and a red Close; <kbd>Esc</kbd> or the backdrop closes it, and opening it stops a running Presentation. Compact portrait/landscape layouts fit it to the viewport with the Comments drawer at the bottom.

**Edit a chart:** on screen in the [Designer](#designer) (**Open Designer**), for the Design or its template; as a table with **Edit PPT Template**, the pencil at the top of the viewer and expanded viewer, which opens the [table view](#table-view-template-editor) at the row of the chart.

### Filtered Chart Dataset

**Dataset** opens the rows left after both the PPT filters and that chart's template filters, not every row of the chosen CDRs.

- Server-side pages of 100 rows, with First/Previous/Next/Last.
- Excel-style value filters over the whole chart dataset, the active columns highlighted and their choices following the other column filters.
- A filtered-row count, **Clear N filters** and full CSV download, keeping the same selection.

> [!TIP]
> Open Dataset on an unexpected chart to see exactly which rows contributed. Compare its row count with Filtered rows before changing the chart formula.

### Comments, Presentation and floating tools

- **Slide comments:** add, edit or remove; <kbd>Enter</kbd> or leaving an edit saves at once.
- **Generated comments:** the icons after the slide navigation (see [Generated comments](#generated-comments)).
- **PPT Filters** changes the applied selection without saving defaults; **Auto-Calculated Fields** opens the shared workspace manager for permitted editors.
- **Presentation** opens the **Presentation mode** settings; **Start presentation** advances the slides on its own, with floating Pause/Resume and Stop; **Stop presentation** ends it. <kbd>F8</kbd> starts it directly (other keys in [Tips & shortcuts](#tips-shortcuts)). The buttons **First / Previous / Next / Last**, the slide selector and opening a chart larger stop it.

| Setting | Values |
| --- | --- |
| **Seconds per slide** | 1 to 300, 5 by default |
| **Transition duration (seconds)** | 0.1 to 10, 1 by default |
| **Transition effect** | None, Random, Blinds, Blur, Bounce, Curtain, Fade, Flip (default), Mosaic, Rise, Slide from left, Slide from right, Soft rotate, Wipe or Zoom |
| **Show comments** | Yes (default) or No |

The settings adapt to compact landscape screens. Backdrop/<kbd>Esc</kbd> close unchanged dialogs; pending Filters, Template or calculated-field edits need a decision first.

#### Generated comments

For editors, three icons follow the slide navigation, set apart like **Presentation** (on a phone, on their own row); hovering names each.

**Generate comments for this slide** (the sparkle) writes analysis comments for the open slide from the figures its charts draw: their filters, splits, PPT filters, dynamic grid cards and hidden legend items apply, and excluded operators are never named.

| Chart type | What the comments read |
| --- | --- |
| CDF Line, Multi KPI CDF Lines, Histogram Line and Histogram Bars | The exact median of each series, its tail (P10, or P90 when lower is better) and, with **Buckets**, the share of samples in the worst class |
| Average and Median Vertical Bars | The value of each bar |
| 100% Stacked Vertical Bars | The share of failures (Failed, Dropped, Cutoff…), or else of the largest class (RAT, CA state…) |
| Threshold Stacked Vertical Bars | The share reaching the threshold |
| Distribution Stacked Vertical Bars | The share in the worst bucket |
| Count Stacked Horizontal Bars | The share of failed and dropped tests among all tests of each bar; when its filter keeps only failed and dropped tests (such as `Call_Status IN (Failed, Dropped)` in **Voice failures** and **Voice failures per City**), the counts it draws: operators from the one with the most in the latest campaign, the change since the previous campaign (a Flex campaign only against another Flex one; a change too small for its counts reads *stable*), the CDR type, city or row with the most, the bar with the largest count, and the operators without any |
| Scatter | How the KPI follows the other measure (Spearman ρ) and its median in the lowest and highest quarter of it |
| Map | The share of samples in the weakest class of its colour measure and, with City or Region in the rows, the area holding more of it than its share of samples |
| Table, Dynamic Table, Highlight Table and Bar Table | The highest and lowest rows of its first numeric columns |
| Horizontal Bars, Dot Plot, Bullet Graph, Heat Map and Lines | The value of each bar, dot, square or point (when the measure is averaged or a median) |
| Box Plot | The median of each box and its tail, as a CDF |
| Pie, Donut, Areas and 100% Stacked Areas | The share of failures, or else of the largest slice or area |

Dual Lines, Bars and Line, Symbol Map, Filled Map, Treemap, Packed Bubbles, Sankey and Gantt get no generated comments: write theirs by hand.

**What the comments compare:**

- **Campaigns and leader:** the latest campaign of each group with the previous one, and every operator with the leader, from the point of view of the **Focus** operators of the [Operator Maps](workspace-config.md#operator-maps) (without them, the leader's).
- **Vendors:** the vendors of each operator in Multivendor. **NR Modes:** in a chart split by NR Mode, each operator in SA with itself in NSA (newest campaign of each).
- **Charts of a slide together:** an NR KPI against the same LTE KPI for every operator, an SA chart's KPI against the same NSA chart's (titles naming the NR Mode, such as CDF_NSA and CDF_SA), and the operators of a slide giving each operator its own chart.
- **Units and better side:** RSRP and SINR in dB; higher LQ, Mean Data Rate and scores are better; lower durations, times, RTT and error ratios are better.
- **Small groups and differences:** a group under 10 samples is not named; a difference under 1 dB (RSRP, SINR), 0.1 (LQ), 5% (other KPIs), or a share difference not statistically significant reads *stable* or *on par*.
- **How many:** up to four comments a slide (three in **comments right** layouts), the best of every chart first.

**Review the suggestions:**

1. The suggestions replace the list of comments until you decide.
2. Untick or edit them.
3. **Add selected comments** adds them after the existing ones (saved at once), or **Discard** leaves the slide as it was.

- **Generated tag:** added comments keep a **Generated** tag (hover: when and which writer); edited by hand, a comment is yours.
- **Out of date:** when the slide is open with another selection (campaigns, filters or CDRs, such as a new campaign with **Latest 2 campaigns**) than its generated comments were written for, the panel says so: generate them again. CDRs count by what they hold (type, stage, campaigns, rows), so a Design transferred to a server with the same CDRs, or a CDR processed again, keeps its comments up to date.

**Generate comments for all slides** (the sparkle on a stack of slides) writes every slide in the background, slide by slide, then says how many slides were written and kept: **Only Slides Without Comments**, **Replace Generated Comments** (keeping those written by hand) or **Replace Every Comment**.

**Writers:**

- **Rules** always read the charts, on the server.
- **LLM writers:** when Super Admin enables them in [AI Comment Writers](super-admin.md#ai-comment-writers), the third icon (**⋯**) picks the writer, named in the tooltips of the other two: **Rules**, **Kiro CLI** (the default LLM) or **Claude**. Each uses the server's API key or your own (user menu → **API keys**), as Super Admin chooses; usage is charged to the key's account.
- **How an LLM writer works:** it rewrites the facts of the charts and the rules comments more naturally and connects them. A comment with a figure that is not a fact, or naming a hidden item, is left out; when none keeps to the facts or the writer fails, the rules comments show with a note saying why.
- **Kiro Brief** (when enabled, same menu): **Download Kiro brief** downloads the facts of every slide for Kiro IDE (a folder with the facts, the style guide, also as a Kiro steering file, and the comments.json Kiro fills in); **Import Kiro comments** reads back comments.json and facts.json (or the folder zipped again), checks every figure and writes the comments with the same three choices.

App Events records each generation (slide, writer asked and writer that wrote, model, charts read and skipped, suggestions, comments left out, Claude tokens and time), the comments added, Generate comments for all slides, the Kiro briefs exported and the Kiro comments imported.

## Designer

Change the slides, layouts and charts of a Design on screen, for this Design or for its template.

**Open and close:** **Open Designer**, at the top of the viewer, turns it into a slide editor; the button reads **Close Designer**, in amber, while open. Every change is drawn at once on the CDRs already prepared and nothing is stored until **Save**; closing asks only when something differs from what is saved (changes undone or made back by hand leave nothing).

**While designing:**

- **Generate PPT** and the Presentation wait for it to close.
- The chart tools (images, expand, zoom) are hidden except View dataset and **Refresh chart** (shown only now), which works the chart out again from its CDRs.
- **PPT Filters**, the Scope, the theme, **Refresh Design** (lays out the edited slides again on the charts it redraws), **Auto-Calculated Fields** and **Edit PPT Template** stay.
- The slides at the left become the slides being edited, and the charts of the slide shown can be chosen and moved. The slide title and subtitle in the header are edited in place with a click.

**The panel at the right** shows the slide or chart chosen:

- **Its head** says where it is (**Slide 2 › Chart 1**: click the slide to see it again; the chart button, **Charts** while none is chosen, lists the charts to choose one), what a change reaches (**This Design** or the template) and how it differs from the template.
- **Its ⋯ menu** holds the actions of the slide or chart (a right click on a chart or slide thumbnail opens it too).
- **Its width:** drag its left edge (kept for your next visits); a wide panel shows the fields of a chart beside its shelves.

### Template or This Design

A Design does not copy its template: it follows it live and keeps only **what it changes**, so a change of the template reaches every Design that follows it.

- **This Design** (scope in the bar of the Designer) changes this Design only, as differences from the template: a slide hidden or added, a title, a layout, the place, type or any setting of a chart, conditions added to or removed from its Filters (kept one by one, so the template's other conditions still reach the Design).
- **Template · N Designs** changes the template: Save asks to confirm and names the other Designs that take the change.
- **A difference of a Design wins** over the template. When the template later changes the same thing, the slide or chart shows **Template changed**, and **Differences** offers **Take template** or **Keep mine**.
- **Apply to template** sends a slide or chart of a Design to its template; **Detach from template** gives the Design slides of its own (see [Save, drafts and the other actions](#save-drafts-and-the-other-actions)).

| Mark | Meaning |
| --- | --- |
| **This Design** (blue) | A slide or chart only this Design has |
| **Changed here** (amber) | The Design changes something of this slide or chart |
| **Template changed** (red) | The template changed what the Design had changed |
| **Hidden here**, **Optional · off** (grey) | A slide of the template this Design leaves out |

**Differences** shows a card per slide and chart the Design changes, with a chip per changed property (title, place, format, chart type, hidden…): the chip's arrow takes the template back for it, **Reset all** for the whole card. The menu of a slide or chart also has **Reset Slide to template** / **Reset Chart to template** and **Apply Slide to template** / **Apply Chart to template** (the template takes it, and every Design of the template with it).

### Slides

- **Thumbnails** at the left show each slide as laid out (charts, KPI cards, text boxes, pictures, or its cover), redrawn when it, the other slides or the data change; a slide left out of the Design shows its places only.
- **Slide menu** (**⋯** or right click): **New Slide after**, **Duplicate Slide**, **Hide Slide in this Design** / **Show Slide again**, **Delete Slide** (Template scope, or a slide of this Design), **Make Slide optional (off by default)** and, for an optional slide, **Show Slide in this Design**.
- **+ New slide** adds a content, title, transition or end slide.
- **Move a slide:** drag it; in Template scope any slide, in This Design scope those of this Design (the template's keep their order).

**The panel of a slide:**

- **Titles:** title and subtitle (**{ }** inserts a field or parameter, see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)).
- **Layout:** a grid of up to 6 × 6 places (point at the cells to preview), with comments below, to the right or none, and the other layouts of the slide master. A layout with fewer places than the slide has charts removes the last ones, after asking.
- **Elements:** its charts, KPI cards, text boxes and pictures, to choose one.

**Adjust places…** changes the places of the layout:

- **Ready layouts:** two above and one as wide as both below, one wide above and two or three below, a tall one beside two or three, three above and two below…
- **Rows and columns:** more or fewer (up to 6 rows and 12 columns), resized by dragging the lines between them.
- **Merge and Split:** click a place, <kbd>Shift</kbd>+click another to choose those between, then **Merge** them (a chart over two columns); **Split** gives a merged place its cells back.
- **Delete** (or <kbd>Delete</kbd> / <kbd>Backspace</kbd>) empties the places chosen; a **+** puts a place back in an empty cell. **Center** puts the place chosen midway in the empty cells beside it, adding grid lines as needed (a chart centred below two others: delete the place beside it, then Center). **Reset places** gives the layout its places back.
- **Where the elements go:** they keep their places in reading order, a place merged with a free one keeps its element, and the element of a deleted place goes to a free place (with none, it is removed after confirmation).
- **Fill the free places beside the chart**, in the **⋯** menu of a chart, spans them in its row (else its column), as a chart below two others taking the whole width.

### Fields in titles and text boxes

Slide titles, subtitles, chart titles and text boxes write these fields as each Design reads them (**{ }** beside them inserts one); the template keeps the fields, so each Design writes its own selection.

| Field | Writes |
| --- | --- |
| `{NR Mode}`, `{NR Mode Name}` | NSA, SA or NSA & SA; Non-Standalone, Standalone or Non-Standalone & Standalone (in a chart title, the NR Mode the chart shows) |
| `{Design}` | The name of the Design (`{Dashboard}`, written by titles before PPT Designer, writes it too) |
| `{Scope}` | Operator Comparison or Multivendor Comparison |
| `{Campaigns}` | The Campaigns of the Design (*26-Q2, 26-Q3*) |
| `{Operators}`, `{Vendors}`, `{Regions}`, `{Clusters}`, `{Cities}` | The values the Design is filtered by (*London, Leeds*), or *All Operators*, *All Cities*… when not filtered by them or keeping every value of its CDRs |

[Template parameters](#template-parameters) are written the same way (`{City}`); their names cannot be those of the fields.

### Charts on the slide

Click a chart to build it, as in Tableau. Its title is written in the head of the panel (**{ }** inserts a field).

#### Data: source, NR Mode and shelves

**Data** has three subpanels: **Chart**, **Filters** and **Fields** (the fields to drag to the other two).

1. **Source:** Data, Voice, Speech or RF All.
2. **NR Mode**, one button per result: a Design of NSA or SA has its NR Mode chosen and the other greyed until NSA & SA is chosen in PPT Filters; one of NSA & SA offers **NSA & SA**, **NSA** or **SA**; in Template scope, **PPT Mode** follows each Design (a chart keeping **NSA** or **SA** has the filter `NR Mode IN (SA)`).
3. **Drag the fields** to the shelves. They are grouped by the sections of the CDR Field Dictionary, as dimensions (blue `Abc`) and measures (green `#`), with **NR_Mode** (NSA or SA, from the CDR of each row) beside Campaign.

| Shelf | Use |
| --- | --- |
| **Measure** | The KPI; its menu chooses the aggregation |
| **Rows**, **Columns** | The splits of the chart, in order (`Operator` then `Campaign` gives `Operator × Campaign`) |
| **Legend** | The fields the legend explains |
| **Filters** | A field's values in the Design's selection with their samples (Include, Exclude, Contains), a numeric condition, or a template parameter (**Use parameter**); the Design's own filters show first, locked. The subpanel also has **Leave out empty values** and **Leave out zeros** (rows whose measure is empty or 0) |
| **One chart per** | One chart per value of a field, side by side in the place of this one (small multiples), in the viewer and the PPT |

- **Where a field goes:** on the middle of a pill it replaces it; near its edges or between pills it goes there. While dragging, a bar shows where (or the replaced pill is outlined).
- **Times:** a time (such as `Test_Start_Time`) on Rows or Columns is grouped by day, `DAY(Test_Start_Time)`; its pill chooses **By hour**, **By day**, **By week**, **By month** or **Exact time**, and chart types along time (Lines, Areas…) draw a time axis.
- The chart is drawn again a moment after each change.

#### Chart Type

**Chart Type** is the tab in the theme colour on the right edge of the chosen chart (it pulses when chosen; while the chart is not drawn yet, it waits on the edge of the panel).

- **The panel** opens over the slide beside the chart (over the whole slide when six types in a row do not fit): pictures of the types on lilac, in cards by what they show (Distribution, Comparison, Trends, Composition, Hierarchies and flows, Tables, Maps and Scorecards; see [Supported chart types](#supported-chart-types)), sized to show every type without scrolling. Choosing a type closes it.
- **Greyed types** cannot be drawn by the shelves; a chart without a measure yet takes any type. The line above them says what the type pointed at needs: one numeric measure; two for Scatter or Dual Lines; a dimension as measure for 100% Stacked Vertical Bars; a latitude and a longitude on Measure for a Map or Symbol Map (a third measure colours the points); a Columns split for Lines and Areas; two to five fields on Rows and Columns for a Sankey; a time for a Gantt. The **Chart** subpanel (and the KPI card form) ticks in green what the chosen type needs once given.
- **Proposed type:** when the measures rule the chosen type out, another is proposed (a type chosen before its fields is kept while they are dropped).
- **Settings of the type**, under the types: Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort or Date Bin.
- **KPI Card**, under Scorecards, turns the chart into a [KPI card](#kpi-cards-text-boxes-and-pictures) of its first measure, source, title and filters (an average for a number, the share of a value otherwise); another type turns it back, its settings kept.

#### Format

**Format** (beside **Data**) changes the look in the viewer and the PPT alike. Its four groups, open at first, close and open on their own (a closed group says what it holds).

- **Series:** a legend entry of the chosen chart, or the series in the list: colour, line width, line (solid, dashed, dotted, growing with the width) and opacity. Operator and Vendor Maps colours stay until a series gets one (**Default** for one series, **Default colours** for all). **Copy line of this series** / **Paste line of** *that series* copy width, line and opacity, not colour, to a series of any chart.
- **Legend** and **Labels:** place (legend: top, bottom, left, right or hidden) and size, colour and bold of the text.
- **Axes:** X and Y titles and the decimals of a CDF's X axis. On the chart, the labels of a numeric axis open a two-ended range slider (**Automatic** resets); those of a text axis its values to untick (kept as a `NOT IN` filter condition), **Only** one or **Show all**.
- **Order of values (as in Tableau):** a value of Rows or Columns dragged on the chart (axis label, header, row label or table row) before or after another sets the order for every level and pane of that field, in viewer and PPT; it is kept in the Format (later values go after) and **Default order**, in the card of that field's values, resets it.
- **Copy format of this chart** / **Paste format of** *that chart*: series colours, legend, labels, axes and axis ranges.

#### Add, move, copy and delete charts

- **⋯ menu of a chart** (or right click): **New Chart**, **Duplicate Chart**, **Copy Chart**, **Cut Chart**, **Paste Chart on this slide** and **Delete Chart** (a KPI card, text box or image names itself the same way).
- **New Chart** puts an empty chart (the source of the chart chosen, no fields and no type) on the slide; **Duplicate Chart** a copy. A slide without a free place gets one first: a column more on its adjusted places, else the layout of its kind with the fewest places that leaves one free (its rows when it can).
- **Free places** show **+ Add**: a chart (as **New Chart**), a KPI card, a text box, a picture, or one copied or cut before (**Paste Chart**).
- **Chart in progress:** until its shelves can draw it (a measure, a type and a Rows or Columns split; for a KPI card, its field), a chart reads no CDR; the slide shows its empty place, the PPT leaves it empty and its template row is a `Chart in progress` keeping what it has in `Format`.
- **Move or swap:** drag a chart by its **⠿** handle onto another chart (swap) or a free place (move).
- **To another slide:** copy (**Copy Chart** or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>C</kbd>) or cut it (**Cut Chart** or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>X</kbd>; its slide keeps at least one element), choose the other slide and paste (**Paste Chart** in the **⋯** menu of the slide or a chart of it, **+ Add**, or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>V</kbd>). It goes on the first free place, or a place more as with **New Chart**, with its fields, filters and format, as an element of its own (only in this Design in This Design scope).
- **Delete Chart** (or <kbd>Delete</kbd> / <kbd>Backspace</kbd>); in This Design scope a template chart is hidden in this Design.
- **Undo, redo and Esc:** see [Tips & shortcuts](#tips-shortcuts). A change the template cannot hold (a chart without a KPI or a split, for example) is refused with the reason and undone.

### KPI cards, text boxes and pictures

| Element | What it shows | In the PPT |
| --- | --- | --- |
| **KPI card** | One figure of the latest campaign of the Design (see below) | Drawn by the same renderer as in the viewer |
| **Text box** | Text written with the editor of the tickets (bold, lists, headings), its size, alignment and colour, with fields and parameters | A text box of its own, bold, bullets and headings kept |
| **Image** | A PNG, JPEG or GIF picture of up to 8 MB (an SVG can be saved as PNG first), fitted in its place keeping its ratio | A picture of its own |

**KPI card:**

- **Figure:** Average, Median, Percentile, Count of samples, Share of a value (%), or Share below / above a threshold (%), of a measure of a source with its filters.
- **Compared with:** the previous campaign, the best competitor, a target or nothing, green or red as it improves (**Higher is better**). **One card per:** none, Operator, Vendor, Region or City.
- **Colour band** (**Good from**, **Poor from**) and **Trend over the campaigns**.
- **Shape:** cards keep their shape in any place: a wide place shows one row of up to four cards, a tall or square one the columns that give the largest cards.

Pictures are kept in the table **PPT Images** and travel with the Designs and templates whose slides use them in exports, transfers and backups (an import adds those missing; the CSV of a template downloaded alone only names them). Text boxes and pictures read no CDR.

### Save, drafts and the other actions

- **Save** stores the template (Template scope) and the differences of the Design. If another user saved the template since you opened the Designer, Save asks you to reload it first.
- **Drafts:** unsaved work is kept on the server for you only (table **PPT Drafts**): opening the Designer again offers to restore or discard it. **Discard** goes back to what is saved. Drafts are not exported, transferred or backed up.
- **More:** **Save Design as…** (a Design of your own following the same template with the changes shown), **Save as template…** (the slides shown as a new template), **Detach from template…** (the Design keeps its slides as its own; choosing a template again in PPT Designs follows it as it is).
- Deleting a template that Designs follow detaches them first, so none breaks.
- Generate PPT and the reports of [Reporting](reporting.md) use the slides as saved. Slide comments stay with a slide when its title changes.

**App Events** (each read as a sentence):

- `design_designer_opened`: the Designer opened, with the template and what the user can change (This Design, its Template).
- `design_edited`: the unsaved edits, the first after opening then at most one event every 5 minutes with everything since (save or discard records the rest): slides added, removed, moved, hidden or shown, their title, subtitle and layout; elements added, removed and moved; each property from what to what (*slide 2 "Voice": chart "CSSR" chart type bar → line*).
- `design_slides_saved`: every change against what was saved (of the Design, and of its template in Template scope); `report_template_saved_from_designer` names the Designs following that template.
- `design_draft_discarded` (with the changes), `report_template_slide_ids_assigned`, `design_detached`, `report_template_saved_from_design` and `design_image_uploaded`.
- Other changes: `save_design` (each part of the selection from what to what, such as NR Mode, Campaign, filters and dates), `rename_design` (before and after), `change_design_template`, `delete_design` (name and template), `design_chart_added`, `design_chart_refreshed`, `save_design_comments` (comments added and removed per slide) and `design_opened`.

### Template parameters

A template can declare **parameters**, so Designs that differ only in a city, a call family or a threshold share one template without differences of their own (a *City Report* template and its London, Manchester and Cardiff Designs).

**Declare them** with **Parameters** in the bar of the Designer (Template scope): the list at the left shows their type and where they are used; the one chosen, at the right, is renamed and deleted there. A template without parameters shows a card per type; otherwise **+ Add parameter** asks for the type:

- **Field values:** values of any CDR field or Auto-calculated Field, chosen from the groups of fields with a search; one or several; none chosen means All.
- **Number:** default, minimum, maximum, step. **Text:** any text.

- **Names:** not those of a built-in token (`{Cities}`, `{Operators}`…); the first ones are named Chosen Cities, Threshold and Note.
- **How to use it** gives the condition to write (`City IN ({Chosen Cities})`), to copy or add to the chart chosen. A parameter in use cannot be deleted; renaming one renames its uses.

**Use them:** write `{Name}` in a chart filter (`City IN ({City})`; with All the condition is left out), a numeric setting (`LQ < {Threshold}`, `Threshold = {Threshold}`, an axis range) or a title (`Voice quality in {City}`).

**Give them values:** each Design chooses them in **PPT Scope & Filters → Parameters** (shown only when the template has some), applied and saved like its filters, using the defaults until then. A report of [Reporting](reporting.md) gives a field-values parameter on a field of its common filters (Operator, Vendor, Region, Cluster, City…) the values chosen there; with values other than the Design's, the PPT goes without its saved comments.

## Generate PPT

Export the slides of a Design to PowerPoint, with the selection you choose.

### Choose the export inputs

Open **Generate PPT** from the library, filter panel or viewer. **Select PPT Scope and Filters** sets the export's exact selection, which can differ from the saved defaults:

- **Scope:** Scope and vendor comparison (see [PPT Scope](#ppt-scope)).
- **Main PPT Filters:** **Campaigns** (the [campaigns and automatic choices](#how-the-cdrs-are-chosen) of the NR Mode; with NSA & SA it chooses the NSA CDRs and the SA ones keep the Design's Campaign (SA)), the CDRs they choose listed by type below, the dates (full width), then Operators and Vendors, Regions and Cities (**Main Cities** first). Campaigns and CDRs show as soon as the dialog opens.
- **Show All Filters** reveals the other main filters and Additional Filters.

- **Starting values:** the Design's Campaign; the other choices load from its CDRs, starting with the saved values, or all when unrestricted or none remain available. Changing campaigns or dates keeps the values still available; an All selection includes new values.
- The browser remembers the dialog's last Scope, Campaigns and dates per Design and user.
- **Save Filters** also persists the dialog's Scope, dates, Campaigns and filters in the Design; it is enabled when the dialog differs from the saved defaults (the vendor comparison counts only in Multivendor). A complete value selection equals an unrestricted field; saved values absent from the selected CDRs are ignored.
- If required, the export prepares the CDRs of its campaigns first.

**Auto comments**, in the Scope of the dialog (or a checkbox of the confirmation from the viewer), writes [generated comments](#generated-comments) into this PPT only: on slides without comments, in place of the generated ones or in place of every comment. It uses the viewer's writer (Super Admin's default until changed); with several writers enabled the dialog shows **Comment writer**, whose change is also the viewer's. The Design keeps its own comments, the job's viewer shows those of the PPT, a relaunched job keeps the choice, and App Events records the number of slides written.

> [!IMPORTANT]
> **Export selections take precedence for that job.** You can export applied or dialog-specific filters without saving them as PPT defaults. The job's Filters snapshot records what was exported.

### Follow the export

Once the job is queued, from the library or the viewer, a progress panel shows its progress bar and stage (waiting in the queue, preparing the data, building the chart models, rendering the charts, writing the PowerPoint), status, charts and slides done and time taken.

- **Cancel Job** stops it, as **Stop export** in [PPT Generation Jobs](#ppt-generation-jobs).
- **Run in Background** (or ×, <kbd>Esc</kbd>) closes the panel; the job keeps running in PPT Generation Jobs and Background Tasks, and is downloaded from its row there.
- When the job ends with the panel open, the PPT downloads by itself and the panel says it is ready (or why it failed or was cancelled); **Download Again** downloads it once more.

### Presentation contents and files

The PPT keeps template slides, layouts, chart proportions, titles, legends and saved comments.

- **Shape of each place:** every chart and table is laid out in the shape of its place, in the PPT, the Word and the viewer alike: nothing is stretched, pies, donuts and bubbles stay round, maps show more around their places, KPI cards take the grid that makes them largest (four cards: two rows of two in a 16:9 place, one row in a wide one, one column in a tall one), and Multi KPI CDF Lines places its CDFs side by side or stacked.
- **Subtitles:** chart subtitles in blue with normal letter spacing; Title/Transition subtitles keep the template's yellow accent.
- **Title covers** match the viewer: Campaigns in orange above the divider; Scope, Regions and Cities beneath in green, cyan and pink.
- **Files:** PPTs, chart PNGs, tooltips and Canvas assets are stored under **output/reports/ppt-designs**, named `yyyymmdd_HHMMSS`, then NR Mode, PPT Name and Scope, then the selected Regions joined by ` + ` (or All Regions), and with several campaigns, the Campaigns joined by `_vs_` at the end. Operators, Vendors and Cities stay in the job Filters snapshot only; long names are shortened only for filesystem limits.

## PPT Generation Jobs

Follow, download and manage the PowerPoint exports.

Jobs continue on the server after you leave the page or close the [progress panel](#follow-the-export). The table records ID, creator, local date/time, NR Mode, Design, Scope, filters, slide/chart counts, status and progress; Excel-style header filters search its columns.

| Action | Availability / purpose |
| --- | --- |
| **Download PPT** | Download an available completed presentation |
| **View PPT snapshot** | Open the job in the viewer with the template and inputs it was generated with |
| Chart actions | **Open PPT charts** in the [Charts Panel](#charts-panel), or download them |
| **Stop export**, **Retry export** / **Relaunch Job** | Manage work when the job's state permits (a ready job is relaunched) |
| Filter action | Inspect sources, dates, campaigns and filters (CDRs grouped by Data/Voice/Speech, Campaigns above Operators) |
| **Delete export** / **Delete All PPTs** | Remove jobs/files; requires user-editor, admin or super-admin. A PPT being generated is not deleted: stop it first (Delete All PPTs leaves it in the list) |

> [!NOTE]
> **All Operators / Vendors / Regions / Cities refers to the job's selected CDRs.** Other workspace CDRs do not expand that selection. Saved values absent from those CDRs are not listed.

## Charts Panel

Browse the charts of the exported PowerPoint jobs.

1. Filter by NR Mode, Design, Template, Scope, Region or City.
2. Select a **PowerPoint Job**.
3. Open a chart card in the expanded viewer (or <kbd>Enter</kbd>/<kbd>Space</kbd> on a thumbnail), use **View Filters** to inspect the snapshot, or **View as Design** to open the job in the viewer.

- **Filters follow each other** and describe complete exported selections: a job with seven cities gives one City choice with those seven; All Cities/All Regions appears only for jobs exported so.
- **Job selector:** local date/time, NR Mode, Design, Scope and recorded geography; long lists show their values on hover.
- **Loading:** the newest matching completed job loads; each chart is read and drawn when it nears the screen, so opening the page reads none.
- **Snapshot, not live:** **View PPT** shows the current applied inputs, the Charts Panel the job's captured template and inputs. Stored Canvas models repaint with the current renderer; legacy jobs without models keep their PNG. The expanded viewer and Filtered Chart Dataset remain available, and permitted editors can open the generating template and Auto-Calculated Fields without changing the snapshot.

> [!IMPORTANT]
> **Completed exports are immutable snapshots.** PPT Filters are hidden in Charts Panel. View Filters shows the exported selection; changing a live Design does not rewrite that job.

## PPT Templates

The reusable slide definitions that Designs follow.

**PPT Templates**, at the top of the PPT Designs library (for `user-editor`, `admin` and `super-admin`), opens the **PPT Templates Library** of the workspace in a dialog. Each action is saved at once without leaving it (its message, such as an import done or refused, in a window over it).

| Action | What it does |
| --- | --- |
| **New Template** | Creates a template with its cover and opens it in its [Designer](#designer), where its slides are added |
| **Import** | Imports a template CSV (see below) |
| **Edit** (✎) | Opens the template in the viewer and its Designer (see below) |
| Rename | The name field of the row |
| **Duplicate** | Creates `- Copy`, with its own identity |
| **Set default** (★) | Makes it the default of the workspace |
| **Export** (⬇) | Downloads that individual CSV; portable ZIP export is under Import / Export / Transfer |
| **Delete** (×) | Deletes it ([Who changes a Design](#who-changes-a-design) applies; for others it is disabled with a tooltip) |

**Where templates live:** in the active workspace's `report_templates` table. Import, export, backup and transfer packages carry them as portable CSV files, which are package artifacts, not the live record. Obsolete `slides-templates` directories are removed by migration and portability flows. New workspaces start without templates; names are unique in the workspace.

**One template for every NR Mode:** a template has no NR Mode; each Design (or report of [Reporting](reporting.md)) chooses the one it reads, and its titles name it with `{NR Mode}` / `{NR Mode Name}` and the selection with the [fields](#fields-in-titles-and-text-boxes), so one template gives the NSA, SA and [NSA & SA](#nsa-sa-in-one-design) decks.

**Rights:** PPT Templates belong to PPT Designer, not to Config: their actions use `/ppt-designer/templates/…` (the former `/workspace-config/report-templates/…` lead there), need PPT Designer in the user's Modules Profile, are recorded in App Events under PPT Designer, and follow [Who changes a Design](#who-changes-a-design). For the other users the name, **Delete** and **Edit PPT Template** are disabled, with a tooltip saying why. The slides of a template (with charts and parameters) are edited from any Design following it and kept in its CSV (`Format` column).

**Order and columns:**

- Drag a template by the tab left of its name (or <kbd>↑</kbd>/<kbd>↓</kbd> on the tab): the order is saved at once for every user and followed by the **Template** of a new Design. Until first moved, the library is sorted by name (an NR Mode in a name, such as `NSA - Report`, is ignored); new, duplicated or imported templates go to the end.
- App Events record each order (`reorder_report_templates`, before and after); exports, transfers and backups carry it (see [Import / Export / Transfer](administrator-config.md)).
- Columns show creation and last update times and **Last Updated by**, the user who last imported, edited, renamed, duplicated or promoted it.

**Edit** opens the template in the viewer and its [Designer](#designer) as a PPT of its own, never listed among the Designs:

- It reads the CDRs of the NR Mode and Campaign it was last opened with (NSA and Latest 2 campaigns the first time; PPT Scope & Filters changes them).
- Every Designer change goes to the template (its bar reads **PPT Template** with the number of Designs following it). **More** offers only **Save as template…**; it makes no PPT of its own (its Designs do).
- **Edit PPT Template**, the pencil, shows it as a [table](#table-view-template-editor), for Find & Replace for example.

**Import** takes the CSV name or derives it from the filename, can convert a legacy catalogue when prompted, and asks to confirm overwriting a case-insensitive name collision.

**Rename** saves when you leave the field or press <kbd>Enter</kbd>; on failure the field keeps its former name and shows an error. Each template has a fixed identity by which Designs refer to it, so a renamed template stays theirs (Design names repeating the template name follow it); a duplicate gets its own identity.

**Default:** one per workspace. Reporting preselects it but a choice for one job does not change it. It cannot be deleted until another template becomes default.

**Templates of earlier versions** (an NSA and an SA library), when the workspace opens:

- Each pair differing only in titles naming the mode (**NSA - NetCheck CDR Report** with *Non-Standalone* and **SA - NetCheck CDR Report** with *Standalone*) becomes one template without the mode (**NetCheck CDR Report**) using the tokens, and the Designs and PPT jobs of either copy use it.
- A title only one copy named (such as *SA RF Quality Analysis* beside *RF Quality Analysis*) takes `{NR Mode}` in both.
- The other templates keep their names, an SA one named as an NSA one taking " (SA)".
- App Event `report_templates_nr_mode_merged`. Packages and backups of earlier versions are imported the same way.

### Table view (Template Editor)

**Edit PPT Template**, the pencil at the top of the viewer, opens the template of the PPT as a table in a large dialog, without the surrounding page controls.

**Grid:**

- Scrolls both ways inside its viewport; the bottom action bar stays visible. Shared slide cells are merged across the charts of a slide.
- Row controls add, remove, reorder and preview chart definitions; **Re-Enumerate Slides** renumbers slides in their visual order.
- Edited cells turn light pastel yellow, newly inserted text stronger; a successful save resets the highlighting.
- **Find & Replace** (or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>F</kbd>) searches every editable cell: matches outlined, the current one highlighted, <kbd>Enter</kbd> / <kbd>Shift</kbd>+<kbd>Enter</kbd> (or Next/Previous) move between them. **Replace** changes the current cell, **Replace All** the whole template after confirmation; **Match case** matches exact capitalization. Replacements are unsaved edits until **Save Template**.

**Validation:**

- Cell edits are validated after a short pause and on leaving the cell; Save revalidates the whole grid and stops on a malformed row or filter.
- Each row error names the row as `Slide: n - Chart: n` (the place of the row in its slide), or `Slide: n` for a Title, Transition or End Slide, then what to correct; fixing the cell clears it.
- Filter conditions show on separate lines with visual bullets (not stored); CSV filter cells keep one condition per line.

**Assistance and previews:**

- Searchable single-select assistance for layouts, chart types, fields and positions; ordered multi-select for Rows, Columns and Legend. It writes the value as soon as chosen (the KPI operation as soon as picked; Rows, Columns and Legend follow what is ticked); **Close** at its bottom closes it.
- The shared Filter Builder shows the parsed expression; its conditions reach the Filters cell with **Apply filter** once complete.
- Chart Data Preview opens the full filtered dataset; Chart Preview reuses the shared Interactive Preview.
- **Preview NR Mode** (NSA by default, SA or NSA & SA), in the toolbar, chooses the CDRs the previews read (every Data, Voice and Speech test of the ready CDRs of that mode, of both for NSA & SA) and the NR Mode their titles name. A note above the rows names charts using a field only one NR Mode's CDRs have.
- **Update Template** applies preview values to the in-memory row, not to disk. **Auto-calculated Fields** opens the shared field manager.

**Saving:** **Save Template** validates and saves the whole grid atomically. Design comment reconciliation runs separately when slide identity changes; a combined CDR update is queued after the save only when the template adds a source field missing from that table (removing the last reference keeps the column for reuse). The viewer refreshes the template when the editor closes; Close, <kbd>Esc</kbd> and backdrop keep the editor while unsaved changes need a decision.

## Report Template reference

The canonical authoring reference for PPT Designer templates. The common `assets/powerpoint-templates/Template_VodafoneThree.pptx` supplies the masters, named layouts and placeholders. Each distinct `Slide` value creates one slide; chart rows sharing it fill its placeholders in row order.

### Template columns

| Column | Purpose |
| --- | --- |
| `Slide` | Positive slide number. Rows are sorted by this value; rows with the same number form one slide. |
| `Slide Tittle` | Shared slide title. The historical `Tittle` spelling is part of the CSV schema. |
| `Slide Subtittle` | Optional shared slide subtitle. |
| `Layout` | `Title Page`, `Title Only`, or a grid named `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right` (see [Chart layouts](#chart-layouts)). |
| `Dynamic Rows Field`, `Dynamic Columns Field` | Right after `Layout`: the fields that repeat the rows and columns of a [dynamic grid](#dynamic-chart-grids). |
| `Chart Tittle` | Optional title drawn inside the chart. |
| `Source Dataset` | `CDR-Data`, `CDR-Voice`, `CDR-Speech` or `CDR-All`; blank for structural slides. |
| `KPI` | Processed CDR field or metric expression to render. |
| `Chart type` | Automated chart type or structural slide type (`Text Box`, `Image` and `KPI Card` for the elements of the [Designer](#designer), and `Chart in progress` for a chart still being built, which reads no CDR). |
| `Filters` | Conditions applied before aggregation, one per line and terminated with `;`. |
| `Rows Split` | Category/table-row hierarchy. Separate dimensions with `×`. |
| `Columns Split` | Comparison-series/table-column hierarchy. Separate dimensions with `×`. |
| `Legend` | Optional field whose plotted or filtered values should be explained. Blank means no legend. |
| `Legend Position` | `Top`, `Bottom`, `Left` or `Right`; blank defaults to `Top`. |
| `Legend Format`, `Label Format` | Optional lists defining colour, font, styles and relative size. Blank keeps automatic formatting. |
| `Label Position` | Optional value placement: `None`, `Top`, `Up`, `Middle` or `Down`. Blank keeps automatic placement. |
| `Axis X Range` | Optional limits in KPI units: `[min,max]`, `[min,]` or `[,max]`. Blank keeps the automatic domain. |
| `Axis Y Range` | Optional CDF cumulative-percentage limits from 0 to 100, same syntax. Blank keeps 0–100%. |
| `Exclude Null/Empty` | `Yes` removes rows whose plotted value is null or empty before chart calculations. |
| `Exclude Zero` | `Yes` removes rows whose plotted numeric value is exactly zero before chart calculations. |
| `Format` | Optional, last: a JSON object per row with what the [Designer](#designer) needs: slide and chart ids (`slide`, `id`), place on the layout (`place`), format (`style`), the kind of a non-chart element (`kind`: `kpi`, `text`, `image`) with its `kpi` settings or `content`, the repeat field (`repeat`), slide options (`slide_options`: `{"optional": true}`, adjusted places `geometry`) and, on the first row, the template `parameters`. Added the first time a Design of the template opens in the Designer. Keep it when editing in Excel: Designs keep their changes by these ids; rows copied or added without it get new ids when saved. |

The editor visually groups `Slide`, `Slide Tittle`, `Slide Subtittle` and `Layout` on multi-chart slides; the CSV stores them on every row. CSV imports identify columns by name in any order and reject duplicate names or aliases.

### Structural slides

Use one row without `Source Dataset` or KPI fields; it cannot share its slide number with chart rows.

- `Title Slide` normally uses `Title Page`; `Transition Slide` normally uses `Title Only` and makes a section divider.
- `End Slide` uses `Black logo end slide` and adds the template's closing slide as it is, without title, subtitle or counter; its `Slide Tittle` only names it in the viewer.
- A row without `Source Dataset` or `Chart type` takes the type of its layout: `Title Page` a Title Slide, `Transition` and `Title Only` a Transition Slide, `Black logo end slide` an End Slide (also when it still says Title or Transition Slide). Saving writes that `Chart type`.
- Title and Transition subtitles use the template's yellow accent (theme accent 4) whatever the layout. Every Title or Transition slide after the cover is a transition with its counter above its title, sized and placed as in every report; a Title Slide opening the Design lists Scope, Regions and Cities below its subtitle and line.

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

Automated rows support `100% Stacked Vertical Bars`, `Count Stacked Horizontal Bars`, `CDF Line`, `Histogram Line`, `Histogram Bars`, `Multi KPI CDF Lines`, `Scatter`, `Map`, `Table`, `Average Vertical Bars`, `Median Vertical Bars`, `Distribution Stacked Vertical Bars`, `Threshold Stacked Vertical Bars`, and the Show Me types of the table below: `Horizontal Bars`, `Dot Plot`, `Bullet Graph`, `Highlight Table`, `Bar Table`, `Heat Map`, `Pie`, `Donut`, `Lines`, `Dual Lines`, `Areas`, `100% Stacked Areas`, `Bars and Line`, `Box Plot`, `Symbol Map`, `Filled Map`, `Treemap`, `Packed Bubbles`, `Sankey` and `Gantt`.

> [!TIP]
> **See every chart type built:** open the Designer of the example Design **DT Analyzer - All Supported Chart Types**.

Every workspace receives once the example template **DT Analyzer - All Supported Chart Types** and its Design (NR Mode **NSA & SA**, latest 2 campaigns of each NR Mode):

- **Slides:** after the title slide, eight slides of four charts, one with the two maps side by side and one of four KPI cards (DL and UL throughput, call setup time and LQ, one card per operator).
- **What they draw:** every chart type on the workspace CDRs, at most two columns a slide (wider frames would stretch the charts), each with the measure and shelves it suits: the DL throughput CDF of the latest two campaigns, NR MCS against NR CQI for Scatter, the hour of the day for Lines, Dual Lines, Areas and Bars and Line, and NSA CDRs for the charts comparing the campaigns of one NR Mode (`NR Mode IN (NSA)`: CDF Line, Bullet Graph, Symbol Map and KPI cards). Charts split by Region leave out tests of no Region (`Region != (blank)`).
- Deleted, it is not added again. A workspace that received it as **All Chart Types** (Design **NSA - All Chart Types**) or **DT Analyzer - All Chart Types** has them replaced in place when unchanged (App Event `starter_examples_replaced`); changed ones stay beside the new ones.

**Common rules:**

- Choose a KPI and at least one Rows or Columns Split dimension. `CDF Line` draws one curve per complete aggregation combination; count charts keep empty combinations where needed so comparisons stay aligned.
- **`CDR-All`** pools the selected Data, Voice and Speech RF observations (`LTE_RSRP`, `NR_RSRP`, `LTE_SINR`, `NR_SINR`, `Latitude`, `Longitude`) with their Operator/Campaign context. It is virtual: no duplicate CDR dataset or table. Its cell assistance offers the union of Data, Voice and Speech fields, including normalized RF fields and `CDR_Type`. Templates using it are kept by JSON/CSV import/export, transfers and backup/restore.
- **`Histogram Line`** draws an unfilled step contour per aggregation combination; `Bin Size = 5` or `Bin Size = 1` in Filters sets the bins. The vertical axis is the percentage of valid samples per bin, per series (series models keep sample counts). Histograms reuse CDF colours, progressive campaign widths and multivendor line patterns. Four `Buckets = ...` thresholds add five red-to-green background bands; `Class Colours = Quality` gives matching distribution charts the same five colours.
- **`Histogram Bars`** uses the same bins with side-by-side Campaign bars, older Campaigns lighter; paired LTE/NR rows can use `Dynamic Columns Field = Operator` to show every selected Operator on one slide.
- **Axis ranges** are visual, not filters, for every chart with a numeric axis: `Axis X Range: [0.01,]` starts at `0.01` keeping the automatic maximum, `[,30]` fixes the maximum. Percentage axes stay 0–100; count, KPI, coordinate and scatter axes use native units; category axes and tables have no numeric domain.
- **Labels** apply to every chart: for bars `None` hides values, `Top` places them outside, `Up`, `Middle` and `Down` inside near the leading edge, centre or origin (horizontal bars: outside-right, inside-right, centre, inside-left). For CDF, scatter and map charts they place point or endpoint labels around the mark.
- **`Exclude Null/Empty` and `Exclude Zero`** are independent and apply to every chart: on both axes of a scatter, on each metric of a CDF or Multi KPI CDF before the distribution, so a CDF can start at its first non-zero observation instead of hiding zeros with an axis range.
- These settings are kept by the template/JSON export, import and backup workflows.

**Show Me chart types** (from `Horizontal Bars` on) carry no aggregation in their names: the aggregation of the measure (`MEDIAN(Mean_Data_Rate)`, `COUNT(Test_ID)`…) chooses it, by default an average for a number and a count for a dimension. They draw a legend of their colours (Format → Legend → Hidden hides it), and a time grouped by a period (`DAY(Test_Start_Time)`, `WEEK(…)`, `HOUR(…)`, `MONTH(…)`) on Columns gives Lines, Dual Lines and Areas a time axis.

| Chart type | Measure | Rows | Columns | Settings |
| --- | --- | --- | --- | --- |
| `Horizontal Bars` | One measure | The bars, one band per value | A bar per value inside each band, in its colour | `Sort = Descending` or `Ascending` orders the rows by their largest bar |
| `Dot Plot` | One numeric measure | The rows | A dot per value on each row, joined by a line | — |
| `Bullet Graph` | One numeric measure; a second one is the target of each bar | With Columns, a bullet per combination | | `Target = 20`, `Target = Previous campaign` (the latest campaign against the one before, Campaign on Rows or Columns) or `Target = Best competitor` (Operator on Rows or Columns); `Buckets` draw grey bands; `Direction` |
| `Highlight Table` | One measure | Table rows | Table columns | Cells coloured by their value: five ranges of the values, or the five classes of `Buckets` (four limits); `Direction` |
| `Bar Table` | One measure | Table rows | Table columns | Each cell has a bar as long as its share of the largest value of its column |
| `Heat Map` | One numeric measure; a second one sizes the squares (else their samples) | The rows of the grid | The columns of the grid | `Buckets`, `Direction` |
| `Pie`, `Donut` | A dimension (its values are the slices), or a measure counted (or summed with `SUM`) by the values of Columns | One pie per value (a row of the grid of pies per value with a dimension measured) | With a dimension measured, a column of the grid of pies per value, named above it; with a measure, its slices | A Donut writes its samples in the middle |
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

`Direction` says which values the colours show as good: by default the KPI decides (lower is better for durations, latencies, errors and failures; higher for throughput, RSRP, SINR, MOS…), `Higher is better` or `Lower is better` say it, and `Neutral` (or a KPI without a direction, such as a count) uses blues. Like `Threshold`, `Buckets` and `Bin Size`, these settings are kept among the Filters of the row and set under the chart types.

### Chart recipes

The examples show chart-specific cells; add the `Slide`, titles and `Layout` of the target slide.

#### 100% Stacked Vertical Bars

Proportions, success ratios and categorical quality splits: KPI categories become stack segments. A KPI of vendors (`Vendor`) takes the colours of the [Vendor Maps](workspace-config.md); Format can change any segment's colour.

```text
Source Dataset: CDR-Voice
KPI: Call_Status
Chart type: 100% Stacked Vertical Bars
Filters: Call Family IN (VoLTE, MultiRAB); Operator IN (Vodafone, 3, EE)
Rows Split: Call Family
Columns Split: Operator × Campaign
Legend Position: Right
```

A second measure `COUNTD(field)` shares out the distinct values of that field instead of the rows, each value once per bar and segment. The share of the cells of each Vendor per campaign counts the tests served by one cell, where `Cell_ID` is that cell and `Vendor` its vendor (`Cell_ID_A` in Voice CDRs and `Cell_IDs_A` in Speech CDRs):

```text
Source Dataset: CDR-Data
KPI: Vendor | COUNTD(Cell_ID)
Chart type: 100% Stacked Vertical Bars
Filters: Operator IN (VF); Cell_ID NOT CONTAINS ->
Columns Split: Campaign
Legend: Vendor
Legend Position: Right
```

#### Count Stacked Horizontal Bars

Event or failure counts: Rows form horizontal categories and the KPI normally supplies statuses or causes. Column hierarchy headers keep complete values in the viewer and the PPT, each level in a smaller font that can shrink to fit, the last header row with its own space above the data.

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

Continuous metrics such as throughput, duration, latency or MOS. Two operators and two campaigns give four curves; with several campaigns the latest is emphasised within each comparison family.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: CDF Line
Filters: Test_Result = Completed; Test_Name CONTAINS FDFS; Direction = DL
Rows Split: Operator
Columns Split: Campaign
Legend Position: Bottom
```

#### Multi KPI CDF Lines

Separate continuous KPIs with `|`: one CDF panel per measure, sharing filters, splits and legend.

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

Average for mean values; change only `Chart type` to `Median Vertical Bars` when outliers should weigh less.

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Average Vertical Bars
Filters: Call_Status = Completed; Call Family = WhatsApp
Rows Split: Operator
Columns Split: Campaign
Legend Position: Top
```

#### Distribution Stacked Vertical Bars

Explicit ranges with `Buckets = ...`, or ordered upper bounds with `Buckets < ...` / `Buckets <= ...`; use `Rate Bucket` as the last Columns level.

- **Ranges:** `Buckets = 1,5,20` gives `<1`, `1-5`, `5-20` and `20+`; negative limits use `to` (`Buckets = -110,-100,-90,-80` gives `< -110`, `-110 to -100`, `-100 to -90`, `-90 to -80` and `-80+` for RSRP).
- **Upper bounds:** `Buckets < 2,5,20,100` checks each value against the limits in order: `below2`, `below5`, `below20`, `below100` or `Above` (`Buckets < 1,3,10,20` for FDTT UDP UL); `<=` keeps boundary values inside their bucket.
- Segments and legend entries always follow ascending numeric order, whatever the order of the rows.
- **In the [Designer](#designer) and [Chart Builder](chart-builder.md),** `Rate Bucket` and `Buckets` are in the **Distribution classes** group of **Fields** (they are not CDR columns): `Rate Bucket` goes at the end of **Columns**, on **Rows** or on **Legend**; `Buckets` only on **Legend**. Write the limits by clicking either pill (with more pills on its shelf, **Limits of the classes…** in its menu) or in the **Buckets** box of **Chart Type**: `1,5,20`, `< 2,5,20,100` or `<= 2,5,20,100`.

```text
Source Dataset: CDR-Data
KPI: Mean_Data_Rate
Chart type: Distribution Stacked Vertical Bars
Filters: Test_Result = Completed; Test_Name = FDTT http DL MT; Buckets < 2,5,20,100
Rows Split: Operator
Columns Split: Campaign × Rate Bucket
Legend Position: Right
```

#### Threshold Stacked Vertical Bars

A below/above split around one threshold; the legend shows it (`< 1.6` and `≥ 1.6`; `Threshold = -110` gives `< -110` and `≥ -110`).

```text
Source Dataset: CDR-Speech
KPI: LQ
Chart type: Threshold Stacked Vertical Bars
Filters: Call_Status = Completed; Call Family = VoLTE; Threshold = 1.6
Rows Split: Operator
Columns Split: Campaign
Legend Position: Right
```

#### Scatter

`Metric vs Dimension` compares a KPI with a radio or quality dimension.

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

`Latitude vs Longitude`, in that order; Rows Split, Columns Split and Legend decide point grouping and colour. To colour by a measured value, use `Latitude vs Longitude vs Measure`, set **Rows Split** and **Legend** to `Value Bucket` and four ascending `Buckets = ...` thresholds (RSRP `-110,-100,-90,-80`, SINR `0,5,13,20`): five ranges in red, orange, yellow, light green and green. **Exclude Null/Empty** removes missing measurements; two-field maps keep their grouping colours.

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

Exact values: rows and columns form the axes, the KPI the aggregated cell value.

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

Conditions are joined with AND and separated by `;`; a comma separates values within one condition. Column matching is case-insensitive.

```text
Call Family IN (VoLTE, MultiRAB); Direction = DL; Vendor NOT CONTAINS (Mixed, Other)
```

| Operator | Example |
| --- | --- |
| Equals / not equal | `Call_Status = Completed`, `Operator != EE` |
| List inclusion / exclusion | `Operator IN (VF, O2, 3, EE)`, `Campaign NOT IN (2025-Q4)` |
| Contains / not contains | `Test_Name CONTAINS FDFS`, `Vendor NOT CONTAINS (Mixed, Other)` |
| Numeric comparison | `LQ < 1.6`, `Mean_Data_Rate >= 20` |
| Tests without a value | `Region != (blank)`, `City = (blank)`: `=`, `!=`, `IN` and `NOT IN` read a missing value as the charts show it, (blank) |

- `IN`, `NOT IN`, `CONTAINS` and `NOT CONTAINS` take comma-separated values; parentheses are optional in Filter Builder input. `Threshold = 1.6` configures threshold charts and `Buckets = 1,5,20,100` distribution ranges.
- `Vendor` filters the vendor alone and `Operator_Vendor` the `<Operator>_<Vendor>` identity. Import accepts the former `Vendor_Only` and `Vendor V3` (as `Vendor`) and `OP_Vendor` (as `Operator_Vendor`); templates of earlier versions are converted once (their `Vendor` groupings and legends become `Operator_Vendor`, their `Vendor_Only` filters `Vendor`), so their charts stay identical.
- Operator-prefixed filter values resolve through workspace operator aliases when the report runs; aggregation fields keep their comparison semantics.

### Rows Split, Columns Split and legends

Selection order defines the hierarchy:

```text
Rows Split: Call Family × G Level 4
Columns Split: Operator × Campaign
```

- Rows supplies chart categories or table rows; Columns comparison series or table columns. A blank Columns Split creates one `(all)` comparison.
- `Campaign` is ordered oldest to newest.
- In Multivendor scope, `Operator` aggregation resolves to the mapped comparison field; an Operator filter still applies to the CDR Operator field.

**Legends:** blank draws none; a KPI or aggregation dimension shows plotted values; a field used only by Filters shows its applied values as text. CDF handles reproduce series colour and relative line width, threshold legends the below/above colours and value, bucket legends readable ranges from `Buckets`. Top/Bottom give a compact horizontal legend, Left/Right a vertical one with reserved plot space.

### Multi-chart slides, operators and colours

Rows sharing a `Slide` number create separate charts on one slide. They must share `Slide Tittle`, `Slide Subtittle` and `Layout`, may use different sources, KPIs, filters and chart types, and need at least as many placeholders as chart rows.

Operator and Vendor aliases resolve to the canonical values of Workspace Config without changing the source workbook. Their table order sets the order of Operator, Subscriber, Vendor and Operator_Vendor dimensions, and each canonical row its chart colour; several campaigns or operators of one identity get contrasting shades of it.

### Chart layouts

The editor offers **121 layouts**: every grid of **1–6 rows × 1–6 columns** without comments, with comments below or to the right (108 fixed grids), nine dynamic layouts, and `Title Page`, `Title Only`, `Transition` and `Black logo end slide`.

- **Physical and virtual:** the 108 grids and four structural layouts exist in the reference PPT (after `Black Title Page`, in selector order); the nine dynamic ones are virtual: the renderer picks a fixed grid from the distinct values of their fields. Other native layouts stay internal to structural slides.
- **Layout selector:** structural layouts first (blue), then dynamic (purple), then fixed grids; the selected one is yellow and keeps its position. Long names stay on one line; narrow screens scroll horizontally.
- **Historic names** are normalized on import and in stored templates; exports use the canonical names. Grids without comments use the full chart area.

### Dynamic chart grids

The dynamic layouts are `Title + 2 rows + dynamic columns`, `Title + dynamic rows + 2 columns` and `Title + dynamic rows + dynamic columns`, each also with `+ comments down` or `+ comments right`. **Dynamic Rows Field** and **Dynamic Columns Field** choose the fields that repeat the rows and columns: a dynamic axis needs one (the parser rejects it otherwise), a fixed axis leaves it empty. CSV exports include both columns and every workflow (template import/export, transfers, backup, restore) keeps them; an older `Dynamic Field` is assigned to the dynamic axis of the layout.

- **Two fixed rows:** two chart definitions with the same Layout and Dynamic Columns Field; the first fills the top row, the second the bottom.
- **Two fixed columns:** two definitions with the same Layout and Dynamic Rows Field; the first fills the left column, the second the right.
- **Both axes dynamic:** one definition and two fields (for example `Region` for rows, `Operator` for columns); each chart keeps only samples matching both values.
- **Values** come from the selected, filtered CDRs, empty ones excluded. Both-axis grids paginate at six rows and six columns; Multivendor grids at six repeated values per slide, keeping operators of one vendor together where possible. Larger single-axis grids derive from the native geometry, with smaller charts.
- **RF histograms:** select **Operator**; the first definition is LTE and the second NR, so each Operator is one column with its Campaigns grouped inside. Filters change the number of columns; LTE and NR keep their positions even when one has no valid samples.

> [!TIP]
> **Readability:** a 6 × 6 grid fits 36 charts, but gives each chart little space. Prefer fewer charts when labels or distributions need close inspection.

## Portability and maintenance

**Export Design** creates a versioned ZIP accepted by Admin Import; imports also accept legacy standalone JSON definitions. A compatible destination template is required.

| Included in the definition | Not copied by PPT definition export |
| --- | --- |
| Name, NR Mode of its CDRs and template association | Source CDRs |
| Scope, dates, saved filters (Campaign included), hidden/additional fields, parameter values | Prepared cache files |
| Slide comments | Generated presentation assets |
| Its differences from the template, or its own slides once detached | Unsaved Designer drafts |

- **CDRs of the destination:** a Design uses the CDRs of the workspace where it is opened, for the same campaigns (Latest and Previous choices among its newest ones).
- **Designs with CDRs of their own** (earlier versions) take the destination campaigns of the CDRs with the same name and type, or else its newest two; check the inputs after import.
- **Designs exported when templates had an NR Mode** read it as part of their selection and use their template as the destination knows it (NSA and SA copies merged); an SA Design named as an NSA one takes " (SA)".
- **Admin component:** Designs have their own export/import/transfer/backup/restore component: an import, transfer or restore replaces the Designs the destination has (found by identity, so a rename on the source follows, or by name) and adds the others (see [Matching and creators](administrator-config.md#matching-and-creators)). Full Workspace and Full Environment include them, listed after Application Config.
- **Former name:** PPT Designer was **PPT Dashboards** and its Designs **Dashboards**. Workspaces of before keep them when they open: Designs, PPT jobs and charts (moved to `output/reports/ppt-designs`), drafts, pictures and App Events take the new names, and Modules Profiles, Interface Settings, tickets and scheduled backups name PPT Designer. Links to `/ppt-dashboards`, this chapter and the PPT Dashboards presentation open those of PPT Designer; older packages, backups, transfers and reports of [Reporting](reporting.md) are imported as Designs.

> [!TIP]
> Verify the template and Campaign after moving a Design to another workspace. Its CDRs do not travel with it.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| View PPT or Generate PPT is disabled | Inspect its status badge and explicit preparation task |
| A filter has no choices | Verify source field/aliases and whether other filters leave matching rows |
| Chart says no CDR is selected | Choose a Campaign with a CDR of the type that chart needs, or check its Active? choice in Workspace |
| Filtered rows are zero | Check dates and empty value selections; use Clear Filters to remove restrictions |
| Chart is empty with nonzero rows | Check its source type, template filters, NR Mode and chart Dataset |
| Chart says *No samples: the chart filter Campaign IN (…) keeps none of the campaigns chosen* | Its own filter names campaigns the selection does not have (for example campaigns written when the template was made). Remove that condition so the chart follows the Campaigns chosen, or split NSA and SA with `NR Mode IN (NSA)` / `NR Mode IN (SA)` instead of campaign names |
| Multivendor is unavailable | Check at least two Vendors and persist mappings for selected CDRs |
| Preparation failed or stays queued | Inspect App Logs and retry; clear derived PPT cache only if invalid |
| Viewer and old export differ | Compare applied live inputs with the completed job's saved snapshot |

> [!WARNING]
> Clear cache is a recovery action for derived artifacts, not a substitute for fixing missing source data, Vendor mappings or an invalid template. Inspect the cause first.

## Tips & shortcuts

Gestures and keys that save time. Keys work while the viewer has the focus and you are not typing in a field.

### Viewer and larger view

| To… | Do this |
| --- | --- |
| Go to the next slide | <kbd>→</kbd>, <kbd>↓</kbd>, <kbd>Page Down</kbd> or <kbd>Space</kbd>, or turn the mouse wheel down over the slide (one slide per turn). On touch: swipe left (not on a zoomed chart). |
| Go to the previous slide | <kbd>←</kbd>, <kbd>↑</kbd> or <kbd>Page Up</kbd>, or turn the wheel up over the slide. On touch: swipe right. |
| Go to the first or last slide | <kbd>Home</kbd> or <kbd>End</kbd> |
| Read the value of a point | Point at it: a tooltip names its label, series and value (on a CDF, its cumulative %) |
| See the tools of a chart (**Dataset**, **Expand**, **Zoom**) | Point at the chart or focus it. On touch: tap it; they show for 3 seconds. |
| Open a chart larger | Double-click it, or **Expand** |
| Go to the next or previous chart of the larger view | <kbd>→</kbd> or <kbd>←</kbd>. On touch: swipe left or right. |
| Close the larger view or a dialog | <kbd>Esc</kbd>, or click the dark backdrop around it |
| Zoom a chart | **− / + / 1:1** (100% to 400%, or reset), or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + mouse wheel (or a touchpad pinch) at the pointer |
| Zoom into one area of a chart | With the mouse, drag a rectangle over the plot (at 100%; not from the title or the legend) |
| Move around a zoomed chart | Drag it, or use its direction arrows (disabled at the edges) |
| Hide or show a value on every slide | Click its entry in the legend |
| Keep only, hide or show values of a legend or an axis | Right-click a legend entry or an axis label. In the menu, <kbd>→</kbd> (or pointing) opens a **Show** submenu, <kbd>←</kbd> goes back and <kbd>Esc</kbd> closes it. |
| Undo the last hide or show | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd>, or **Hidden (N)** → **Undo** |
| Copy or download a chart or the slide as an image | Point at the chart for its copy and download buttons; the slide has two blue buttons beside the slide selector. On touch: tap; the buttons show for 5 seconds. |
| Add a slide comment | Type it and press <kbd>Enter</kbd>; an edited comment is saved with <kbd>Enter</kbd> or by leaving it |
| Close the viewer | <kbd>Esc</kbd>, when no Presentation runs and no dialog is open |

### During a Presentation

| To… | Do this |
| --- | --- |
| Start the Presentation at once | <kbd>F8</kbd> (with the settings of the **Presentation mode** dialog) |
| Pause or resume it | <kbd>F8</kbd> or <kbd>Space</kbd>, or the floating Pause/Resume button |
| Go to the previous or next slide and keep playing | <kbd>F7</kbd> or <kbd>F9</kbd>, the arrow and Page keys, the wheel or a swipe |
| Stop it | <kbd>Esc</kbd> or **Stop presentation** |

> [!TIP]
> **Buttons stop, keys do not.** **First / Previous / Next / Last**, the slide selector and opening a chart larger stop the Presentation; keys, the wheel and swipes move through it while it keeps playing.

### In the Designer

| To… | Do this |
| --- | --- |
| Open the menu of an element or a slide | Right-click it (a slide: its thumbnail at the left), or its **⋯** menu in the panel |
| Move a slide; move or swap charts | Drag its thumbnail; drag a chart's **⠿** handle onto a free place or another chart |
| Copy, cut or paste the element chosen | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>C</kbd>, <kbd>X</kbd>, <kbd>V</kbd> (pasted on the first free place of the slide shown, also on another slide) |
| Delete the element or places chosen | <kbd>Delete</kbd> or <kbd>Backspace</kbd> |
| Undo or redo | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd>; <kbd>Shift</kbd>+<kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd> or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Y</kbd> |
| Edit the slide title or subtitle in place | Click it in the header of the viewer; <kbd>Enter</kbd> or leaving keeps it, <kbd>Esc</kbd> cancels |
| Widen or narrow the panel | Drag its left edge (kept for your next visits); double-click it for the usual width; focused, <kbd>←</kbd>/<kbd>→</kbd> change it by 24 px |
| Pick a grid layout | Point at the cells of **Grid** to preview its rows × columns, then click |
| Step back | <kbd>Esc</kbd> leaves a field, then closes a menu, then Chart Type, then leaves the element chosen; a click in the viewer outside the charts, the panel and the bar of the Designer also leaves it |
| Format a series of the chosen chart | Click its legend entry (on a chart not chosen, the click hides the series in the whole Design) |
| Set the range or the values of an axis | Click its labels on the chosen chart |
| Reorder the values of Rows or Columns | Drag an axis label, header or row label before or after another (a purple bar shows where) |
| Put a field before, after or in place of a pill | Drop it near the edge of the pill, or on its middle |
| Choose the chart type | Click the **Chart Type** tab on the right edge of the chart; the wheel scrolls it, <kbd>Esc</kbd> or a click outside closes it |
| Choose several places in **Adjust places…** | Click one, then <kbd>Shift</kbd>+click another; drag the grid lines to resize rows and columns |
