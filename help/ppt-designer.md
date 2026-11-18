# PPT Designer

Build an interactive Design (a PPT Design) from processed Data, Voice and Speech CDRs and export it to PowerPoint.

- **Start:** follow a PPT Template of the workspace, or start blank.
- **Explore:** apply one dataset selection to every slide and explore the live charts.
- **Change:** edit slides and charts on screen in the [Designer](#designer).
- **Export:** generate the PowerPoint in the background.
- **Templates:** the PPT Templates themselves are managed and edited here too.

> [!NOTE]
> **A Design is a saved definition, not a copy of your data.** It stores its template, Scope, dates, filters, the values of the template parameters, comments and what it changes of its template's slides. Its CDRs are chosen from its NR Mode and Campaign filter each time it is prepared. Source CDRs and generated caches remain separate.

## Presentation

```presentations
ppt-designer
```

## Choose your task

| I want to… | Go to |
| --- | --- |
| Create a Design from a template | [PPT Designs](#ppt-designs) |
| Choose the campaigns, dates and operators of a Design | [PPT Scope & Filters](#ppt-scope-filters) |
| Browse the slides and the data behind a chart | [View PPT](#view-ppt) |
| Change the slides, charts and texts on screen | [Designer](#designer) · [Template parameters](#template-parameters) |
| Create or edit a PPT Template | [PPT Templates](#ppt-templates) · [Report Template reference](#report-template-reference) |
| Export the presentation to PowerPoint | [Generate PPT](#generate-ppt) · [PPT Generation Jobs](#ppt-generation-jobs) |
| Fix empty charts or a slow preparation | [Troubleshooting](#troubleshooting) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Before creating a Design

1. Open the correct workspace and process the required CDR types.
2. Create or import a **Report Template** in **PPT Templates**, at the top of the PPT Designs library. A template serves the CDRs of any NR Mode.
3. For Multivendor Comparison, persist Vendor mappings first.
4. Open **PPT Designer**.

| Role | What they can do |
| --- | --- |
| **user-editor**, **admin**, **super-admin** | Create, import, duplicate, edit and delete PPT Designs (within [Who changes a Design](#who-changes-a-design)), manage PPT Templates, and open **Edit PPT Template** and **Auto-Calculated Fields** from the viewer |
| **user-viewer** | Open a Design, apply other filters, generate its PPT and export the Design |

> [!TIP]
> **First comparison:** create a Design (it compares the newest two campaigns of its NR Mode), choose its Scope, Campaign and other filters, apply them, then open **View PPT**. Inspect the charts before generating a PPT.

Designs use the same template schema and renderer as Reporting. Detailed template authoring is covered in [Report Template reference](#report-template-reference).

## PPT Designs

The library of the workspace: create, open, export and order the Designs.

### Create a definition

1. Click **Create PPT Design**, above the list of the Designs.
2. Enter its **PPT Name** (**My New PPT Design** is offered).
3. Select the **NR Mode** of the CDRs it reads: **NSA**, **SA** or **NSA & SA** for both (see [NSA & SA in one Design](#nsa-sa-in-one-design)).
4. Select a **PPT Template**. The button beside it opens the **gallery** of the templates of the workspace (see below).
5. Click **Create**. **Cancel**, **×** or <kbd>Esc</kbd> close the dialog without creating it.

What happens next:

- **With a template:** the saved definition opens in PPT Scope & Filters.
- **With None — blank PPT:** it opens in its [Designer](#designer) with only its cover, where its slides are added. It follows no template; **More → Save as template…** makes one of it.

The template gallery:

- A card for each template, with its first slides in small as it lays them out (the picture of each chart type in its place, the covers and transitions in colour).
- Each card shows how many slides and charts it has, and **Default** on the default one; **None — blank PPT** comes first.
- A click on a card chooses that template; <kbd>Esc</kbd> or **×** leaves the choice as it was.

NR Mode and operators:

- **Out of scope operators:** when the NR Mode leaves operators out of scope (the **NR Modes** of their labels in the [Operator Maps](workspace-config.md#operator-maps), such as Three, which has no SA), their tests are left out of the Design. Its CDRs used and the viewer name them beside its Campaign and Scope (*Out of scope: SA · Three*).
- **Titles name the NR Mode:** any template serves every NR Mode. Its titles write the NR Mode of the Design where they use `{NR Mode}` (NSA, SA or NSA & SA) or `{NR Mode Name}` (Non-Standalone, Standalone or Non-Standalone & Standalone).

Importing:

- **Import PPT Design** imports a standalone JSON definition of a Design.
- The ZIP that **Export Design** downloads is imported through Admin Import (see [Portability and maintenance](#portability-and-maintenance)).

> [!NOTE]
> **Names are unique in the workspace**, whatever the NR Mode each Design reads: an NSA and an SA Design of the same template need names of their own (for example **NSA - NetCheck CDR Report** and **SA - NetCheck CDR Report**).

### NSA & SA in one Design

A Design of NR Mode **NSA & SA** reads the CDRs of both NR Modes, so a slide can put NSA and SA charts side by side and a chart can draw NSA and SA series together. Every row of the combined CDR tables keeps the NR Mode of its CDR in the **NR Mode** field (NSA or SA), so the NSA and SA tests of an operator are never added together.

- **Campaign filters:**
  - PPT Scope & Filters shows **Campaign (NSA)**, which chooses the NSA CDRs, and **Campaign (SA)**, which chooses the SA ones.
  - Each offers the campaigns of its NR Mode and its own Latest choices, resolved among them (for example Latest 3 campaigns in NSA and Latest campaign in SA).
  - A Design saved without Campaign (SA), or generated in a report of [Reporting](reporting.md), uses its Campaign filter for both NR Modes, each Latest choice among the campaigns of each NR Mode.
- **The NR Mode of a chart:**
  - A template row keeps one NR Mode with the filter `NR Mode IN (SA)` (or `NSA`), and then reads only the CDRs of that NR Mode (an SA chart reads no NSA CDR). Without it, the chart reads every NR Mode the Design reads.
  - The NR Mode of the Design decides: an NSA or SA Design only shows charts of its own NR Mode, and NSA and SA charts together need a Design of NSA & SA.
  - In a Design that does not read the NR Mode of a chart, the chart says so instead of showing data, and its title names the NR Mode it shows where it writes `{NR Mode}`.
- **NR Mode in splits and legends:**
  - **NR Mode** is a field of Rows Split, Columns Split, Legend and the Dynamic Rows/Columns Field (a dynamic grid can place the NSA chart above the SA one).
  - A chart that reads both NR Modes and is split neither by NR Mode nor by Campaign (the SA campaigns name their mode, such as 2026-Q3-SA) gets NR Mode as the last level of the split that holds its legend, and of its legend.
  - Lines, Dual Lines, Areas, 100% Stacked Areas and Bars and Line get it in Rows, as their series, since their Columns are the horizontal axis.
- **Look of the series:**
  - Each operator keeps its colour in both NR Modes: its SA series use a lighter tint of it, and SA lines are dashed when dashes do not already tell operators apart.
  - The CDF campaign line widths are ranked inside each operator and NR Mode, so the newest NSA and the newest SA campaigns are both thick.
- **Fields of one NR Mode:** a chart that uses a KPI, filter or split field that only the CDRs of one NR Mode have shows a note naming the NR Mode without samples (*The SA CDRs have no Mean_Data_Rate: no SA samples.*), and the template editor warns about it.

The PPT file names and the viewer header name the NR Mode **NSA & SA**.

**Example:** every workspace receives once the example template **DT Analyzer - FDFS DL (NSA & SA)** and its Design of the same name (Latest 3 campaigns in NSA, Latest campaign in SA): a slide with the FDFS DL throughput CDF of NSA, that of SA and the FDFS DL transfer time of every campaign of both NR Modes.

### RF Quality Design

An existing or imported Design **RF Quality (RSRP & SINR)** can use the workspace template **RF Quality (RSRP & SINR)**. Its NR Mode is NSA and its Campaign **Latest 2 campaigns**, so it uses the CDRs of the newest NSA campaigns; edit or delete it like any other Design. See [Network Insights](network-insights.md#rf-quality-template-and-design).

- **Slides:** separate LTE and NR RSRP/SINR CDF, average, distribution, threshold and quality-map slides for Data, Voice and Speech, followed by the NSA NetCheck black-logo closing slide.
- **All CDR types first:** each chart family starts with an All CDR types slide pooling valid Data, Voice and Speech observations, followed by the separate types; LTE and NR remain separate.
- **CDF slides:** a two-by-two layout with LTE and NR above their contour histograms (5 dB RSRP bins; 1 dB SINR bins).
- **Contour histograms:** percentages per series, the CDF colours and campaign widths, and the multivendor line patterns; red-to-green background bands match the quality-class slides.
- **Grouped-bar histogram slides:** follow each CDF/contour slide for All CDR types, Data, Voice and Speech.
  - Their `Title + 2 rows + dynamic columns + comments down` layout and `Dynamic Columns Field = Operator` create one column per selected Operator on the same slide, with LTE above NR and comments beneath.
  - Every bin has one bar per Campaign, ordered oldest to newest: the newest uses the Operator colour and older Campaigns use progressively lighter shades.
  - Percentages use the same valid-sample denominator and bin widths as the contour histograms.
- **NR shares** use valid NR measurements and do not measure availability across the entire route.

### Row actions

| Action | Effect |
| --- | --- |
| **View PPT** | Open the interactive slide viewer |
| **Edit Design** (pencil icon) | Open the slide viewer in the [Designer](#designer), once the Design is prepared (users who can change the Design or its template, see [Who changes a Design](#who-changes-a-design)) |
| **Generate PPT** (PPT icon) | Open the export selection dialog |
| **Duplicate** | Create an independent definition |
| **Export Design** | Download a versioned ZIP accepted by Admin Import |
| **Delete** | Remove the definition after confirmation; only the users who change the Design delete it (see [Who changes a Design](#who-changes-a-design)) |

**Close** leaves the active definition without deleting it. Deleting a Design does not delete its CDRs, template or generated PPT jobs.

**Order of the library:**

- The library lists the Designs in the order of the workspace.
- Users who can change Designs drag a Design by the tab on the left of its name (or press <kbd>↑</kbd> and <kbd>↓</kbd> on the tab) to move it. The new order is saved at once for every user of the workspace, without changing any Design.
- Until a Design is first moved, the library is sorted by NR Mode (NSA, NSA & SA, SA) and then by name (an NR Mode written in a name, such as `NSA - Report`, is ignored for the order).
- Designs created, duplicated or imported later go to the end.
- App Events record each new order (`reorder_designs`, with the names in the order before and after), and exports, transfers and backups of the Designs carry it (see [Import / Export / Transfer](administrator-config.md)).

**Created by, Last Updated by and Last Updated:**

- **Created by** and **Last Updated by** name the user who created each Design and the last one who changed it, by their first and last name (or their username when they have none).
- **Last Updated** shows the date and time of that change: a dash when no date is recorded, as in a starter Design of a new workspace that nobody has changed.
- **What counts as a change:** its name, NR Mode or template, its Scope and filters, its slides in the Designer or its comments, or a template renamed or deleted that changes it. Opening a Design, generating its PPT or moving it in the library is not.
- A Design changed before these columns existed shows the last change its App Events recorded, or its creator when they recorded none.
- Exports, transfers and backups carry both names, given the same way (see [Matching and creators](administrator-config.md#matching-and-creators)).

### Who changes a Design

A Design is changed and deleted only by the user who created it and by super-admins. A change is one to its name, NR Mode and template, its Scope and filters with **Save Filters**, its slides in the [Designer](#designer) or the comments saved in it.

| Role | Changes and deletes |
| --- | --- |
| **super-admin** | Every Design |
| **admin** | The Designs they created and those of user-editors; not those of another admin or super-admin, nor the starter Designs, which belong to `super` |
| **user-editor** | Only the Designs they created |
| **user-viewer** | None |

- **For the other users** those controls are disabled, with a tooltip that names who changes the Design. They still open it, apply other filters, generate its PPT and export it.
- **Duplicate:** a user-editor, admin or super-admin also duplicates it as a Design of their own.
- [PPT Templates](#ppt-templates) follow the same rule.
- App Events record each refused change as `ppt_designer_change_refused`, with the Design or template, the action, its creator and the reason.

### Change name, NR Mode or template

- **Name:** edit it in the table (column **PPT Name**) and confirm with the green check (on a phone, in **⋯ → Edit details** of its card).
- **NR Mode** and **PPT Template** have their own selectors, independent of each other: the NR Mode chooses the CDRs the Design reads and keeps its template, and any template serves every NR Mode.
- **A Design created blank** shows **None — blank PPT**: choosing a template makes it follow that template, and its own slides are replaced by those of the template after a warning.

> [!WARNING]
> **Changing NR Mode or Template invalidates the prepared charts.** The application rebuilds them.
> An NR Mode change keeps the campaigns of an NR Mode the Design still reads (NSA to NSA & SA keeps the Campaign as Campaign (NSA)) and sets the others to the newest campaigns of the new mode (the campaigns of the other mode do not apply); the titles of the template name the new NR Mode.
> A template-only change keeps the Campaign.

The Scope, date settings, other filters, custom fields and comments are preserved. Only CDRs of the active NR Mode participate.

### Session and unsaved changes

- **Remembered:** the browser remembers the last open Design and page position during the authenticated session.
- **Filter panel:** the main filter panel starts collapsed for a new session; its open/closed state is remembered while that session remains active.
- **Unsaved filters:** leaving with unsaved Scope, date or filter changes asks for **Save Filters**, **Discard** or **Cancel**.
- **After Save Filters** nothing is left unsaved or unapplied, also while the saved filters are still being applied (the Design is prepared), so closing the filters, opening the viewer or leaving asks nothing.
- Management-only name, NR Mode and Template inputs do not trigger false filter warnings.
- **Logging out** clears temporary open-Design, preview and scroll state. Saved definitions remain in the workspace.

## PPT Scope & Filters

Choose which CDRs, campaigns, dates and values the slides of a Design show.

**PPT Filters**, at the top of the viewer of a Design, opens this panel over its slides; a Design just created, duplicated or imported opens in its viewer with it. The table of the Designs never opens the filters.

### How the CDRs are chosen

A Design has no CDR selector: the **Campaign** filter (the first Default Filter) and the Design's NR Mode choose its CDRs (with NSA & SA, Campaign (NSA) and Campaign (SA) choose those of each NR Mode). They are the CDRs of that NR Mode that the combined CDR tables include, for the chosen campaigns (every campaign when the Campaign filter is not restricted):

- the **Final** CDR of a campaign before its **Weekly** and **Daily** CDRs, and a Weekly CDR before the Daily ones it contains;
- or, when it was changed, the **Active?** choice of the CDR in Workspace (see [CDR Stage](workspace-management.md#cdr-stage-final-weekly-and-daily)).

**Automatic campaign choices.** Besides the campaigns, the Campaign filter offers these choices first. They are made again whenever the Design is prepared or exported, so they follow the campaigns that arrive later:

| Choice | Chooses |
| --- | --- |
| **Latest campaign** | The newest campaign |
| **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns** | The newest two, three or four campaigns |
| **Previous campaign** | The one before the latest; with a single campaign, none |
| **All available campaigns** | Every campaign of the NR Mode at that moment, also those that arrive after it is saved (unlike every campaign checked by hand) |

- **Flex and in-progress campaigns are not counted:** none of these choices counts the [Flex campaigns](workspace-management.md#flex-campaigns) (local campaigns, complete but localised in one region, cluster or city, whose campaign or Campaign Maps label has the word Flex, such as `26-Q2-Flex`), nor the [campaigns in progress](workspace-management.md#campaigns-in-progress) (Weekly or Daily CDRs only, without a Final CDR yet). Nor does a Campaign filter without campaigns count the Flex ones: such a campaign is used only when it is checked by hand.
- **Each choice stands alone:** checking it clears the other one and the campaigns, checking a campaign clears it, and **Select All / None** checks or clears the campaigns only.
- **Default:** a new Design compares its **Latest 2 campaigns** (**Latest campaign** in Multivendor Comparison with Operator_Vendor), as its newest CDRs did before. Changing the Scope or vendor comparison updates a Campaign that still has the default of the former one.
- CDRs without Campaign values are used when no campaign is chosen.

**CDRs Used**, below the Scope:

- Lists by type (Data, Voice and Speech, each showing about three CDRs and scrolling the rest) the CDRs the current selection chooses, newest campaign first, with their stage and campaigns (Weekly and Daily CDRs outlined).
- Follows every change of the NR Mode or filters at once, before they are applied, and says when the filters must be applied to use them.
- The Campaign, Operator, Vendor, Region, Cluster and City lists follow the selection the same way, and an open list stays open while values are checked.

Designs saved before chose their CDRs by hand: they take, once, the campaigns of those CDRs as their Campaign filter (keeping a Campaign filter they already had). The Designs without saved CDRs (which used the newest ones) take **Latest 2 campaigns**, or **Latest campaign** for Multivendor Operator_Vendor.

### PPT Scope

| Scope | Comparison | Default Campaign |
| --- | --- | --- |
| **Operator Comparison** | Normalized Operator values | Latest 2 campaigns |
| **Multivendor Comparison** | Operator/vendor hierarchy | Latest 2 campaigns (Vendor Only), Latest campaign (Operator_Vendor) |

- **Saved with the filters:** the Scope and vendor comparison are applied and saved with the filters. The viewer's Scope control asks for confirmation before rendering its charts again.
- **Vendor comparison:** **Select Comparison Scope** shows **Vendor comparison** beside Scope when Multivendor Comparison is chosen. **Vendor (All Operators Combined)** is first and is the default when entering multivendor scope; **Operator_Vendor** keeps each operator separate.
- **Every test of the NR Mode:** each row keeps the NR Mode of its CDR (its **NR Mode** field). A Design of an NR Mode reads every Data, Voice and Speech test of the CDRs of that NR Mode, whatever RAT or call mode it ran on (an EPS fallback call of an SA CDR is an SA test). Use the **RAT** filter for a narrower technology selection.

> [!IMPORTANT]
> **Multivendor requires mapped Vendors.** The workspace must have at least two distinct cached Vendors, and the chosen CDRs must satisfy the mapping/comparison requirements. A single-vendor selection cannot produce a Multivendor comparison.

### Dates

**Date from** and **Date to** open the Default Filters and are applied and saved with them.

| Date setting | Meaning |
| --- | --- |
| **Oldest** | Resolve the first available date from the chosen CDRs during preparation |
| **Newest** | Resolve the last available date from the chosen CDRs during preparation |
| A chosen calendar day | Use that fixed date |

- **Use oldest** / **Use newest** restore automatic bounds. The fields display their resolved dates, such as `Oldest (2026-01-01)`.
- **Date to** includes the whole selected day.
- Navigating calendar months does not change the date until you select a day.

> [!TIP]
> Use automatic date bounds when you want the CDRs of new campaigns included without adjusting dates. Use fixed dates for a reproducible time window.

### Read the row counts

| Count | What it represents |
| --- | --- |
| **CDRs used** | Rows contributed by the chosen CDRs |
| **Filtered rows** | Rows remaining after dates and PPT filters |
| **Chart rows** | Rows remaining after that chart's template filters as well |

- Without date or adaptive-filter restrictions, the ready summary reuses the effective Design count so both agree.
- When the chosen CDRs hold only the chosen campaigns, the Campaign filter needs no restriction on their rows, so the selection keeps these known counts.
- An empty chart can coexist with nonempty Filtered rows: its source type or chart-specific filters may exclude the remaining rows.

### Default filters and aliases

**Order:** **Campaign → Operator → Operator_Vendor → Vendor_Operator → Vendor → Market → Region → Cluster → City → RAT → Session Type → Call Status**. Campaign comes first, after Date from and Date to, because it chooses the CDRs.

**Vendor filters:**

- **Operator_Vendor** filters the `<Operator>_<Vendor>` identity, **Vendor_Operator** the same identity as `<Vendor>_<Operator>` (both stay in sync) and **Vendor** the vendor alone, using cached per-CDR values.
- **Vendor choices** list real vendors first, followed by Ericsson (Mixed) (and the former Mixed Vendor), Mixed (non-Ericsson) (and the former Other Vendor), All Vendor(s), and operators without vendors labelled **Operator - All**. Operators without a vendor are stored as `Operator - All` in both columns.
- **Everywhere:** every vendor filter, including PPT export, expanded charts and template filters, uses these columns.
- **Aliases:** the former `Vendor_Only`, `Vendor V3` and `OP_Vendor` filter names are accepted, and operator-prefixed values in a Vendor filter are resolved to the vendor name using workspace operator aliases.
- The comparison mode still controls whether charts group by Operator_Vendor or by Vendor (All Operators Combined).
- Technology is not an adaptive filter because NR Mode belongs to the definition.

**Source columns of the filters:**

| Visible filter | Source columns in priority order |
| --- | --- |
| Region | `Region` → `G_Level_2` → `G Level 2` |
| City | `City` → `G_Level_4` → `G Level 4` |
| Campaign | `Campaign` → `campaign` |
| RAT | `RAT_A` → `RAT` → `Sample_RAT_A` |
| Call Status | `Call_Status` → `call_status` → `status` |

Aliases resolve per row: an empty higher-priority field falls back to the next column. Hover or keyboard-focus the filter to inspect its aliases.

**Choosing values:**

- Each multiselect supports search, individual values and **Select All / None**.
- **Main Cities:** City offers **Main Cities** first. It is saved as such (not as the cities of that moment) and is the Main Cities of Workspace Config whenever the Design is prepared, exported or generated in a report of [Reporting](reporting.md), so changing the Main Cities changes the Design too (every city while the workspace has none).
  - It stands alone: checking it clears the cities and checking a city clears it.
  - Designs saved before with exactly the Main Cities of the workspace take the Main Cities choice once.
- **Every value = unrestricted:** selecting every value individually also makes the field unrestricted, even when only one value is available. An unrestricted field includes new values from later-added CDRs automatically and displays **All values**.
- Applying or saving a changed Campaign reloads the choices of its CDRs.
- Menus stay open while selecting and close after pointer exit.
- Older truncated catalogues are completed from source rows.

> [!NOTE]
> **The filters list the values of every CDR of the NR Mode and follow each other.**
> Campaign lists every campaign of the Design's NR Mode (with the labels of the Campaign Maps).
> Operator, Operator_Vendor, Vendor_Operator, Vendor, Region, Cluster and City list the values of the chosen CDRs, each with the labels of the Operator and Vendor Maps and only those the other filters leave: choosing Vodafone as Operator leaves in Vendor only the Vendors of Vodafone. A filter's own choice does not narrow its list.
> These lists come from the combinations of values each CDR keeps (the **CDR Filter Facets** table), read once when the CDR is processed (or, for older CDRs, in the background the first time they are needed), so filling them never reads the rows of the CDRs; until a CDR has them, its catalogue values are offered.

> [!CAUTION]
> **Selecting no values returns no rows.** Selecting all values removes the restriction. This differs from modules where an empty filter means “all”. Use Clear Filters to remove restrictions deliberately.

### Additional Filters

1. Search **Select field to add new filter**.
2. Choose a CDR column or an applicable workspace Auto-calculated Field.
3. Use **Add Filter**, then select its values.

- Values load against the current CDRs, dates and other filters without preparing the whole Design.
- The circular **×** removes an additional filter or hides a default filter after confirmation; the field picker can restore a hidden default.
- Auto-calculated Fields apply to their declared CDR types. They are materialized into the relevant combined CDR table when first needed.

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

How a Design is prepared, kept in the cache and warmed up while the server is idle.

### What happens while preparing?

- **In the background:** preparations run in the background and the browser follows progress. A new request replaces the same user's previous request; stale responses are ignored.
- **Reuse:** an equivalent selection prepared earlier in the session restores without recalculation.
- **Viewer opens at once:** with a yellow **Preparing PPT dataset** card until its requested slides are ready.
- **Task card:** user-requested tasks appear in the floating task card and can provide **Interrupt task**.

| Status | Meaning |
| --- | --- |
| **Checking Cache** | Waiting for the server's status of the Design |
| **Loading data / Rendering** | The Design is being prepared or its charts rendered for a user |
| **Data Cached** | The open Design is prepared; its charts render as they are viewed |
| **Ready** | The Design has CDRs to show; it is prepared when it is opened, or by the warm-up |
| **Data needed** | No CDR matches the Design's selection |

View PPT, its PPT Filters and PPT export are available at any time.

### Warm-up while the server is idle

After 5 minutes without anyone using the application (and with no other background work), the server **warms up** the open workspace, so after a restart Designs open at once with their charts drawn.

- **What it prepares:** one after another, every PPT Design, and every PPT Template as PPT Templates → **Edit** opens it (with the NR Mode and Campaign of each user who opened one, else NSA and Latest 2 campaigns). The models of their charts are worked out and kept in the cache folder of the workspace.
- **Only what changed:** a chart keeps its model while the chart, its CDR selection and the mappings stay the same. A Design or template that changed works out again only its changed charts, and one whose CDRs or filters changed all of them; with nothing changed since the last warm-up, there is nothing to do.
- **Progress:** **Warming up PPT Designs** shows in the floating task card with the Design or template and the chart it is at. Its **Interrupt task** button stops it after the chart it works out.
- **Pauses by itself** as soon as someone uses the application or other background work starts, and goes on from where it was the next time the server is idle (what it kept is not worked out again).
- **Skipped:** charts a selection cannot draw are left to the viewer, which says why, and Designs without CDRs of their selection are skipped.
- **App Events:** each warm-up (`design_warmup_started`, `design_warmup_finished` with its charts worked out and kept and the size of the cache folder) and each stop (`stop_design_warmup`).

**Without warm-up:** opening, refreshing or exporting a Design that was not warmed up (or whose CDRs, filters or template changed since) prepares it from the [columnar copies](workspace-management.md#columnar-copy-of-the-cdrs) of its CDRs.

- The charts that aggregate their rows (CDFs, histograms, averages, stacked and grouped bars) are grouped by DuckDB on the copies, each distinct combination of the chart's fields once with its number of rows.
- Maps, scatter plots, tables and chart data views read their rows from the column cache in memory.
- Changing the Campaign, dates, filters or comparison mode recalculates the charts from the columns already in memory without reading the CDRs again.

### What Clear cache removes

Combined CDR tables remain the source for filters and chart data. Selection records keep counts, facets and reproducible predicates; the cache does not copy CDR rows into a separate projection database.

**Column cache in memory:**

- PPT charts read the materialized combined CDR tables through a per-CDR column cache kept in memory.
- Each column a chart needs is read once per CDR, together with the PPT filter columns (the default filters, the Design's custom fields and the event date): from the [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) of each CDR when every copy of the selection holds its CDR as it is, else from SQLite.
- A column worked out by an expression is worked out once per distinct value, giving the value SQLite gives: the day of each time is written directly where it is certain, and by SQLite in memory otherwise.
- The RF fields (coordinates, RSRP and SINR) are read as the numbers the CDRs hold, without turning them into text and back (a value that is no number stays text, without its spaces at both ends, and blank text is no value).
- Any combination of CDRs, dates, filters and comparison mode is then assembled in memory without querying the CDRs again. `CDR-All` pools the Data, Voice and Speech tables without rereading the original uploaded files.
- Preparing a changed universe also counts its rows from these filter columns, and reuses the distinct filter values of each CDR until that CDR changes, instead of reading the CDRs again.
- The assembled rows are exactly the rows SQLite returns, with the same values and types. Maps, scatter plots, tables and chart data views also keep SQLite's row order. When SQLite would return them in an order the cache cannot reproduce, for example while filtering a single City, those charts read SQLite directly.
- Charts reading the same fields share one read, and charts with the same source, filters and measure share one filtering pass.
- The column cache keeps up to 1 GB in memory by default, removing the least recently used columns first; `DRIVETEST_ANALYZER_COLUMN_CACHE_MEMORY_MB` changes this limit.

**Cache folder of the workspace:**

- Preview manifests (the preparation of a Design) and Canvas models (the drawn data of each chart) are kept in memory and, as compressed files, in the `.cache/ppt-designer` folder of the workspace (`preparations/` and `charts/`).
- They are keyed by dataset revisions, selection, scope, template and format, mappings and renderer version: other sessions and PPT exports reuse them, and after a restart a Design already prepared opens at once with the charts already drawn, while anything that changed is worked out again.
- Each file is written under a temporary name and renamed once complete, so a chart is never kept half written. A file that cannot be read (cut by a crash or a full disk) is deleted and worked out again, and temporary files left by a write cut short are deleted.
- The folder keeps up to 1 GB, the least recently used files removed first (`DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB` changes this limit), and files nothing has used for 30 days are removed.
- The folder is left out of backups, exports and transfers, moves with its workspace when it is renamed and is deleted with it.
- **Clear workspace cache** empties it (set aside at once, deleted in the background).
- **Earlier versions:** what they kept in the workspace database (the PPT Preparation Cache and PPT Chart Models Cache tables) moves to the folder when the workspace opens (App Event `ppt_design_cache_moved_to_folder`), and the tables are dropped. The `.design-data-cache` and `.design-chart-cache` folders of earlier versions are removed when a workspace opens.

> [!WARNING]
> **Workspace Clear cache cancels active user-requested work and removes derived cache only.** It preserves PPT definitions, combined CDRs, templates and generated jobs. The warm-up rebuilds the cache the next time the server is idle.

**When charts are calculated:**

- Canvas models are created when a chart is viewed, refreshed or requested for PPT, or by the warm-up.
- The charts of the open slide are calculated first and appear as each one is ready.
- After they load, nearby slides silently prefetch one chart at a time in the order next, previous, two ahead, two behind. A prefetch waits while the charts of a newly opened slide are calculated, so moving to another slide never queues it behind prefetched charts.
- Opening an individual chart uses the chart sequence instead. Closing the viewer stops scheduling further work.

## View PPT

Explore the slides and charts of a Design, live on its CDRs.

Open **View PPT** from the library or filter panel (**Edit Design** opens it in the Designer). It does not expand the main filters panel automatically; use **PPT Filters** for the floating controls.

### Read the header

The viewer preserves the template's 16:9 layout and uses approximately 96% of the viewport. Its header identifies NR Mode, Design and slide position.

- Slide titles and golden-yellow subtitles display in capitals.
- Campaigns, Scope, Regions and Cities identify the applied selection.
- Export snapshots show the selection captured by that PPT job.
- Campaign labels are compact, such as **26-Q2**, **26-Q2-NSA** or **26-Q2-SA** (see [Campaign ordering](technical-considerations.md#campaign-ordering)). Older CDRs may populate cached campaign labels a few seconds after first opening.

### Slides and navigation

| Control | Use |
| --- | --- |
| Slide selector | Jump to a template slide; searchable choices show the number, a purple title and a teal subtitle separated by a bold ● |
| Slides at the left | Every slide in small, as in the presentations of the [Help](help.md#presentations): the covers and transitions as in the viewer and the charts of the others once calculated, with their number and title; the slide shown is marked, and choosing one shows it (on wide screens; phones keep the slide selector) |
| **Presentation**, **First / Previous / Next / Last** | Below the slide and its comments: play the slides or move through them |
| Keyboard, wheel and swipe | <kbd>←</kbd> <kbd>↑</kbd> <kbd>Page Up</kbd> go back and <kbd>→</kbd> <kbd>↓</kbd> <kbd>Page Down</kbd> (or <kbd>Space</kbd>) go forward, <kbd>Home</kbd> and <kbd>End</kbd> go to the first and last slide, when focus is outside editable controls; the wheel over the slide goes to the previous or next slide, one per turn; on touch, a swipe left or right goes to the next or previous slide (not on a zoomed chart) |
| **Scope** | Switch Operator/Multivendor after confirmation |
| **PPT Filters** | Edit the live selection in a floating panel |
| **Generate PPT** | Export the selection |
| **Refresh Design** | Refresh the PPT preparation |

- **On wide screens** these controls share one row above the slide: the slide selector with the two image buttons of the slide beside it, then **Scope**, **PPT Filters** and **Open Designer** with their names, and **Refresh Design**, **Auto-Calculated Fields**, **Edit PPT Template** and, the last one, **Generate PPT** as icons (point at one to read its name).
- **While designing**, the slides at the left take the place of the slide selector.
- **Changing Scope** renders the charts again with the PPT filters (a Campaign that still has the default of the former Scope takes the default of the new one). Multivendor is unavailable when the workspace has fewer than two Vendors.
- **Narrow screens** wrap actions and adapt navigation to the available space.

**Theme**, at the start of the floating section bar of the page, colours the charts and the slide titles of the viewer and of the PPTs with the colour themes of [Scoring & GAP Analysis](scoring-gap-analysis.md): **Ericsson** by default, **NetCheck**, **Umlaut**, **Vodafone**, **Midnight**, **Paper** and **Heatmap**.

- **Charts** take its font and its colours for text, axes, grid lines, table headers and alternate rows; the colours of operators, vendors and thresholds stay as they are.
- **Titles:** the slide title and subtitle of the viewer (still in capitals) and the titles and subtitles of the content slides of the PPT take its title style, the part that tells the slide apart in its focus style.
- **Midnight** paints the charts and the content slides night blue (with the logos in white) and turns their tables, text and comments light on dark.
- Title and Transition slides keep the template look.
- **One theme per workspace:** each user keeps one theme per workspace for every themed module (choosing it here chooses it in Scoring & GAP Analysis, Network Insights and CDR Analysis too). Changing it restyles the viewer and redraws the charts at once, is kept for the next visit and the PPTs generated afterwards, and is recorded in the App Events log.

**How slides look:**

- **Title and Transition slides** preserve the template text and look as in the exported PPT: the Vodafone-Three red with the Ericsson mark, the Vodafone-Three and Ericsson logos at the top right, light titles with the room of two lines and the yellow subtitle below them.
- **Title cover:** Campaigns above its decorative divider, with Scope, Regions and Cities beneath it, in white with bold labels. Each Title or Transition slide after it shows its counter (01, 02…), as in the PPT.
- **End Slide:** the Ericsson mark and name centred on white, as the closing slide of the PPT, without counter.
- **Chart rows** preserve template order and placeholder geometry.
- **Large grids:** in grids with three or more rows or four or more columns, each chart's title appears as text above the chart, in the viewer and in the PPT, so it stays readable in small cells. Dynamic grids show the row or column value (for example the Operator) in bold before the title, such as **EE** · LTE RSRP histogram.
- **Axis labels** and aggregation headers are never truncated, in the viewer or in the PPT. Each axis level wraps onto two lines, uses a smaller size or turns vertical, and the chart reserves the room it needs.

**Comments area:**

- Layouts ending in **comments right** place comments beside the charts; **comments down** places them below. Their comments area is always kept in the PPT.
- When the slide leaves places of its grid free (for example three charts on a 2 x 2 grid, or a **New chart** not finished yet, which the PPT leaves empty), the comments take the largest block of free places (the lowest, then the rightmost) and the charts take the same grid without comments, so they also use the room of the comments.
- A slide without comments shows the area with a dashed frame and a muted *Comments* prompt to write over.
- Layouts without comments use the full chart area and have no comments: the viewer and the Designer show no Comments panel on their slides, and generated comments (for one slide, all slides, the Kiro brief or the Auto comments of the PPT) leave them out.

### Live and expanded chart controls

Point at or focus a chart for **Dataset**, **Expand** and **Zoom** (on touch, a tap shows them for 3 seconds). While the [Designer](#designer) is open only **Dataset** and **Refresh chart** show, and the chart itself is changed from its panel.

| Gesture / action | Result |
| --- | --- |
| **Expand** or double-click | Open the focused chart in the expanded viewer |
| <kbd>←</kbd> / <kbd>→</kbd> in the expanded viewer (on touch, a swipe) | The previous or next chart |
| **− / + / 1:1** | Zoom between 100% and 400%, or reset |
| <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + wheel (or a pinch of the touchpad) | Zoom the chart under the pointer, at the pointer |
| Drag a rectangle at 100% (with the mouse) | Zoom into the selected plot area |
| Drag when zoomed | Pan the chart |
| Direction arrows when zoomed | Move the camera; arrows disable at boundaries |
| Point at a data point | A tooltip with its label, series and value |
| Click a legend entry | Hide or show that value in every slide of the Design; a hidden entry stays faded and struck through |
| Right-click a legend entry or an axis label | **Keep only**, **Hide** or **Show**, **Hide All** and **Show All** for that legend or axis level; the menu also lists the values hidden in the rest of the Design (an axis menu, those of its level too), each opening a **Show** submenu when the pointer moves over it (or with <kbd>→</kbd>; <kbd>←</kbd> goes back) |
| **Hidden (N)**, in the viewer | Shown while a value is hidden: lists every hidden value of the Design to **Show** it, **Show all** and **Undo** the last hide or show, even when nothing is left on the chart to click |
| <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd> | Undoes the last hide or show; in the Designer, its **Undo** does so when it was the last change |

**Hidden values:**

- **Whole Design:** hiding a value applies to the whole Design. Every series, bar, stacked segment, row, column and category where the value appears, at any aggregation level, disappears and the chart closes the gap: hiding Operator VF_SA also hides each VF_SA Campaign, for example.
- **Dynamic grids:** the cards of a hidden value (such as an Operator) leave the slide and the remaining cards fill a smaller grid. A slide whose cards are all hidden offers **Show hidden values** and is left out of the PPT.
- **How long:** the legend state lasts for the browser session and also applies in the expanded viewer.
- **In the PPT:** **Generate PPT** exports the charts as you see them, and the PPT job's viewer shows the same state. Relaunching a PPT job keeps the state it was created with.
- In Network Insights, clicking a legend entry hides or shows it in that chart only.

**Images:** the slide of the viewer, each of its charts and the chart of the expanded viewer download as a PNG image or copy to the clipboard as a screenshot (see [Images of charts and tables](web-interface.md#images-of-charts-and-tables)).

- **The whole slide:** from the two blue buttons beside the slide chooser, above the slide, with its comments below it when it has some (as plain text).
- **Each chart** (also when it is the only one of its slide): from the floating buttons at the left of its controls, on the same row.
- **The chart of the expanded viewer:** from the buttons above it.
- So do the Charts Panel and each of its thumbnails.
- App Events records each one as `export_design_image`, with the slide or the Design and date of the PowerPoint job.

**The expanded viewer:**

- Has the actions of the viewer above the chart: its image, **PPT Filters**, and **Auto-Calculated Fields** and **Edit PPT Template** as icons named by their tooltips.
- Has chart navigation and a red Close control; <kbd>Esc</kbd> or a click on the backdrop also closes it. Opening it stops a running Presentation.
- Compact portrait/landscape layouts fit navigation and the chart to the viewport; the Comments drawer stays accessible at the bottom.

### Edit a chart definition

- **On screen:** the charts of a PPT Design are changed in the [Designer](#designer) (**Open Designer**), for the Design or for its template.
- **As a table:** **Edit PPT Template**, the pencil at the top of the viewer and of the expanded viewer, opens its template as a table at the row of the chart.
- Template and calculated-field editing require **user-editor**, **admin** or **super-admin**.

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
| Slide comments | Add, edit or remove; <kbd>Enter</kbd> or leaving an edit saves immediately |
| Generated comments | The icons after the slide navigation: comments for the open slide from the figures of its charts (reviewed before they are added) or for all slides, and a menu with the writer and the Kiro brief |
| **Presentation** | Opens the **Presentation mode** settings, then **Start presentation** advances the slides on its own; **Stop presentation** ends it (see below) |
| Pause/Resume and Stop | Floating controls remain available in Presentation mode |
| **PPT Filters** | Change applied selection without automatically saving defaults |
| **Auto-Calculated Fields** | Open the shared workspace manager for permitted editors |

**Presentation mode settings:**

| Setting | Values |
| --- | --- |
| **Seconds per slide** | 1 to 300, 5 by default |
| **Transition duration (seconds)** | 0.1 to 10, 1 by default |
| **Transition effect** | None, Random, Blinds, Blur, Bounce, Curtain, Fade, Flip (default), Mosaic, Rise, Slide from left, Slide from right, Soft rotate, Wipe or Zoom |
| **Show comments** | Yes (default) or No |

- **Keys:** <kbd>F8</kbd> starts the Presentation with these settings, or pauses and resumes it; <kbd>Space</kbd> also pauses and resumes it; <kbd>F7</kbd> and <kbd>F9</kbd> (or the arrow keys, the wheel and swipes) go to the previous and next slide while it keeps playing; <kbd>Esc</kbd> stops it.
- **What stops it:** the **First / Previous / Next / Last** buttons, the slide selector and opening a chart larger.
- Its settings adapt to compact landscape screens.
- Backdrop/Escape closes unchanged dialogs; pending Filters, Template or calculated-field edits require a decision first.

#### Generated comments

For editors, three icons follow the slide navigation, set apart like **Presentation** before it (on a phone, on a row of their own below it); hovering each one names it.

**Generate comments for this slide** (the sparkle) writes analysis comments for the open slide from the same figures its charts draw: the filters, splits, PPT filters, dynamic grid cards and legend items hidden in the viewer apply, and the excluded operators are never named.

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

**What the comments compare:**

- **Campaigns and leader:** the latest campaign of each group with the previous one, and every operator with the leader, from the point of view of the **Focus** operators of the [Operator Maps](workspace-config.md#operator-maps) (without Focus operators they follow the leader).
- **Vendors:** the vendors of each operator in Multivendor.
- **NR Modes:** in a chart split by NR Mode, each operator in SA with itself in NSA (the newest campaign of each NR Mode).
- **Charts of a slide together:** an NR KPI against the same LTE KPI for every operator, the KPI of a chart of SA against the same KPI of a chart of NSA (their titles name the NR Mode, such as CDF_NSA and CDF_SA), and the operators of a slide that gives each operator its own chart.
- **Units and better side:** each KPI is read with its unit and its better side (RSRP and SINR in dB; higher LQ, Mean Data Rate and scores are better; lower durations, times, RTT and error ratios are better).
- **Small groups and small differences:** a group with fewer than 10 samples is not named, and a difference too small to matter (1 dB for RSRP and SINR, 0.1 for LQ, 5% for the other KPIs, or a share difference that is not statistically significant) reads as *stable* or *on par*.
- **How many:** a slide gets up to four comments (three in the **comments right** layouts), the best one of every chart first.

**Review the suggestions:**

1. The suggestions replace the list of comments until you decide.
2. Untick or edit them.
3. **Add selected comments** adds them after the existing comments of the slide (saved at once, like the comments you write), or **Discard** leaves the slide as it was.

- **Generated tag:** comments added from Generate comments keep a **Generated** tag (hover it to see when and by which writer); edited by hand, a comment is yours.
- **Out of date:** when the slide is open with another selection (other campaigns, filters or CDRs, such as a new campaign with **Latest 2 campaigns**) than the one its generated comments were written for, the panel says they are out of date: generate them again.
- The CDRs count by what they hold (their type, stage, campaigns and rows), so a Design transferred to another server where the same CDRs were uploaded, or a CDR processed again, keeps its comments up to date.

**Generate comments for all slides** (the sparkle on a stack of slides) writes the comments of every slide in one go, in the background, following its progress slide by slide. A summary says how many slides were written and kept.

| Choice | Writes |
| --- | --- |
| **Only Slides Without Comments** | Only the slides without comments |
| **Replace Generated Comments** | In place of the generated comments, keeping those written by hand |
| **Replace Every Comment** | In place of every comment |

**Writers:**

- **Rules** always read the charts, on the server.
- **LLM writers:** when Super Admin enables them in [AI Comment Writers](super-admin.md#ai-comment-writers), the menu of the third icon (**⋯**) picks the writer, which the tooltips of the other two name: **Rules**, **Kiro CLI** (the default LLM) or **Claude**. Each uses the API key of the server or your own (user menu → **API keys**), as Super Admin chooses; what it writes is charged to the account of the key.
- **How an LLM writer works:** it receives the facts of the charts and the rules comments, rewrites them in a more natural way and connects them. Every figure it writes must be one of the facts and it must not name a hidden item, otherwise that comment is left out. When none keeps to the facts, or the writer fails, the rules comments are shown with a note saying why.
- **Kiro Brief:** when enabled, the same menu offers:
  - **Download Kiro brief:** downloads the facts of every slide for Kiro IDE (a folder with the facts, the style guide, also as a Kiro steering file, and the comments.json Kiro fills in).
  - **Import Kiro comments:** reads back comments.json and facts.json (or the folder zipped again), checks every figure and writes the comments with the same three choices as Generate comments for all slides.

App Events records each generation (slide, writer asked and writer that wrote, model, charts read and skipped, suggestions, comments left out, tokens of Claude and time taken), the comments added from it, Generate comments for all slides, the Kiro briefs exported and the Kiro comments imported.

## Designer

Change the slides, layouts and charts of a Design on screen, for this Design or for its template.

**Open and close:**

- **Open Designer**, at the top of the viewer, turns it into a slide editor. The button reads **Close Designer**, in amber, while it is open, and closes it.
- Closing asks about the changes only when something differs from what is saved, so changes undone or made back by hand leave nothing to save.
- Every change is drawn at once on the CDRs the Design already prepared; nothing is stored until **Save**.

**What changes in the viewer while designing:**

- **Generate PPT** and the presentation wait for it to close.
- The tools over the charts (images, expand, zoom) are hidden but **Refresh chart**, shown only while designing, which works that chart out again from its CDRs and draws it again, and View dataset.
- **PPT Filters**, the Scope, the theme, **Refresh Design** (which lays the slides being edited out again on the charts it renders again), **Auto-Calculated Fields** and **Edit PPT Template** stay.
- The slides at the left become the slides being edited, and the charts of the slide shown can be chosen and moved.
- The slide title and subtitle in the header can be clicked to edit them in place (<kbd>Enter</kbd> or leaving keeps, <kbd>Esc</kbd> cancels).

**The panel at the right** shows the slide or the chart chosen:

- **Its head** says where it is (**Slide 2 › Chart 1**: click the slide to see it again; the chart button, **Charts** while none is chosen, lists the charts of the slide to choose one), what a change reaches (**This Design** or the template) and how the slide or chart differs from the template.
- **Its ⋯ menu** holds the actions of the slide or chart (a right click on a chart or a slide thumbnail opens the same menu).
- **Its width:** drag the left edge of the panel to widen it, or narrow it again; double-click gives it its usual width, and <kbd>←</kbd>/<kbd>→</kbd> on the focused edge change it by 24 px. The width is kept for your next visits. A wide panel shows the fields of a chart beside its shelves.

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

- **A difference of a Design wins** over the template.
- **Template changed:** when the template changes the same thing afterwards, the slide or chart shows **Template changed**: **Differences** offers **Take template** or **Keep mine**.
- **Filters one by one:** conditions added to or removed from the Filters of a chart are kept one by one, so the other conditions of the template still reach the Design.

| Mark | Meaning |
| --- | --- |
| **This Design** (blue) | A slide or chart only this Design has |
| **Changed here** (amber) | The Design changes something of this slide or chart |
| **Template changed** (red) | The template changed what the Design had changed |
| **Hidden here**, **Optional · off** (grey) | A slide of the template this Design leaves out |

**Differences** shows a card for each slide and chart the Design changes, with a chip for each property it changes (its title, place, format, chart type, hidden…):

- The arrow of a chip takes the template back for it; **Reset all** for every one of the card.
- The menu of a slide or chart also has **Reset Slide to template** / **Reset Chart to template** and **Apply Slide to template** / **Apply Chart to template** (the template takes it, and every Design of the template with it).

### Slides

- **Thumbnails:** the slides at the left show each slide in small as it is laid out (its charts, KPI cards, text boxes, pictures, or its cover), drawn again when the slide, the other slides or the data change; a slide left out of the Design shows its places only.
- **Slide menu:** choose a slide at the left; its **⋯** menu (or a right click) offers:
  - **New Slide after**, **Duplicate Slide**;
  - **Hide Slide in this Design** / **Show Slide again**;
  - **Delete Slide** (Template scope, or a slide of this Design);
  - **Make Slide optional (off by default)** and, for an optional slide, **Show Slide in this Design**.
- **+ New slide** adds a content, title, transition or end slide.
- **Move a slide:** drag it. In Template scope any slide; in This Design scope the slides of this Design (those of the template keep their order).

**The panel of a slide** has three subpanels:

- **Titles:** its title and subtitle (**{ }** inserts a field or a parameter, see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)). You can also click them in the header of the viewer to edit them in place.
- **Layout:** a grid of up to 6 × 6 places (point at the cells to preview it), with comments below, to the right or none, and the other layouts of the slide master. A layout with fewer places than the slide has charts removes the last ones, after asking.
- **Elements:** its charts, KPI cards, text boxes and pictures, to choose one.

**Adjust places…** changes the places of the layout:

- **Start from a ready layout:** two above and one as wide as both below, one wide above and two or three below, a tall one beside two or three, three above and two below…
- **Rows and columns:** give the grid more or fewer (up to 6 rows and 12 columns), and resize them by dragging the lines between them.
- **Merge and Split:** click a place, then <kbd>Shift</kbd>+click another to choose the places between them, then **Merge** them into one (a chart over two columns); **Split** gives a merged place its cells back.
- **Delete** (or <kbd>Delete</kbd> / <kbd>Backspace</kbd>) empties the places chosen, leaving their cells empty; a **+** puts a place back in an empty cell.
- **Center** puts the place chosen midway in the empty cells beside it, adding the lines of the grid it needs (a chart centred below two others: delete the place beside it, then Center).
- **Where the elements go:** they keep their places in reading order, a place merged with a free one keeps its element, and the element of a place deleted goes to a free place (or, with none, is removed after a confirmation).
- **Reset places** gives the layout its places back.
- **Fill the free places beside the chart**, in the **⋯** menu of a chart with free places beside it, spans them in its row (else in its column), as a chart below two others that takes the whole width.

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

Click a chart to build it, as in Tableau. Its title is written in the head of the panel (**{ }** inserts a field).

#### Data: source, NR Mode and shelves

Its **Data** has three subpanels: **Chart**, **Filters** and **Fields** (the fields to drag to the other two).

1. **Source:** Data, Voice, Speech or RF All (the CDRs the chart reads).
2. **NR Mode**, one button per result:
   - A PPT Design of NSA or SA reads only its CDRs, so its NR Mode is chosen and the other one is greyed until NR Mode NSA & SA is chosen in PPT Filters.
   - One of NSA & SA offers **NSA & SA**, **NSA** or **SA**.
   - In Template scope, **PPT Mode** follows the NR Mode of each Design of the template (a chart that keeps **NSA** or **SA** has the filter `NR Mode IN (SA)`).
3. **Drag the fields** of the source to its shelves. They are grouped by the sections of the CDR Field Dictionary and told apart as dimensions (blue `Abc`) and measures (green `#`), with **NR_Mode** (the NR Mode of the CDR of each row, NSA or SA) beside Campaign.

| Shelf | Use |
| --- | --- |
| **Measure** | The KPI; its menu chooses the aggregation |
| **Rows**, **Columns** | The splits of the chart |
| **Legend** | The fields the legend explains |
| **Filters** | A field dropped here opens its values in the Design's selection with their samples (Include, Exclude, Contains), or a numeric condition, or a parameter of the template (**Use parameter**); the filters of the Design show first on the shelf, locked |
| **One chart per** | One chart for each value of a field, side by side in the place of this one: small multiples, in the viewer and in the PPT |

- **Where a field goes:** dropped on the middle of a pill it takes its place; near its edges or between pills it goes there. While dragging, a bar between the pills shows where it will go (or the pill it replaces is outlined).
- **Times:** a time (such as `Test_Start_Time`) dropped on Rows or Columns is grouped by day, `DAY(Test_Start_Time)`. Its pill chooses **By hour**, **By day**, **By week**, **By month** or **Exact time**, and the chart types along time (Lines, Areas…) draw it as a time axis.
- The chart is drawn again a moment after each change.

#### Chart Type

**Chart Type** is the tab in the colour of the theme on the right edge of the chart chosen, inside its place on the slide. It pulses when the chart is chosen; while the chart is not drawn yet, it waits on the edge of the panel.

- **Where it opens:** over the slide beside the chart (over the whole slide when there is no room beside it for six types in a row).
- **How it looks:** the chart types as pictures with their names on a lilac panel, grouped by what they show, each group a card with its name (Distribution, Comparison, Trends, Composition, Hierarchies and flows, Tables, Maps and Scorecards; see [Supported chart types](#supported-chart-types)). As many cards fit on a row as possible, the cards of a row fill it and are as tall as its tallest one, the pictures are as large as show every type without scrolling and the panel is as wide as its rows. The wheel over it scrolls it instead of going through the slides.
- **Greyed types:** those the shelves cannot draw are greyed and cannot be chosen. A chart without a measure yet, such as a new one, takes any of them.
- **What a type needs:** the line above them says what the one pointed at needs (a Map, a latitude and a longitude on Measure, a third measure colouring its points). The **Chart** subpanel (and the form of a KPI card) says what the one chosen needs, ticked in green once it is given.
- **Proposed type:** when the measures rule the chosen type out, another one is proposed (a type chosen before its fields is kept while they are dropped).
- **Settings of the type** are set under the types: Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort or Date Bin.
- **Closing:** choosing a chart type closes it, as its tab, **×**, <kbd>Esc</kbd> or a click outside it do.
- **KPI Card**, under Scorecards, turns the chart into a [KPI card](#kpi-cards-text-boxes-and-pictures) of its first measure, with its source, title and filters (an average for a number, the share of a value otherwise). A KPI card has Chart Type too, and another chart type turns it back into a chart, its settings kept for a later return.

#### Format

**Format** (beside **Data**) changes how the chart looks, in the viewer and in the PPT alike (the same renderer draws both). It has four groups, open at first, that close and open on their own (a closed group says what it holds).

- **Series:** click an entry of its legend on the chart already chosen, or the series in the list, to change its colour, line width, line (solid, dashed, dotted: its dashes and round dots grow with the line width) and opacity.
  - On a chart not chosen yet, a click on its legend hides the series in the whole Design, as in the viewer.
  - The colours of Operator and Vendor Maps stay until a series is given one: **Default** gives one series its colour back, **Default colours** every series.
  - **Copy line of this series** copies its line width, line and opacity (not its colour, which tells the series apart), and **Paste line of** *that series*, on another series of this chart or of another one, gives it the same.
- **Legend:** its place (top, bottom, left, right or hidden) and the size, colour and bold of its text.
- **Labels:** their place and the size, colour and bold of their text.
- **Axes:** the titles of the X and Y axes and the decimals of the X axis of a CDF.
  - **Click the labels of an axis** on the chart to change it there: a numeric axis opens a slider with two ends for its range (**Automatic** gives it back); a text axis the list of its values to untick those the chart leaves out (kept as a `NOT IN` condition of its Filters), **Only** one of them or **Show all**.
  - **Drag to reorder (as in Tableau):** drag a value of the Rows or Columns on the chart (an axis label, a header, a row label or a row of a table) before or after another value of its field. A bar shows where it goes; the order applies to every level and pane where the field is, in the viewer and the PPT, and it is kept in the Format of the chart (values that appear later go after those ordered). **Default order**, in the card of the values of that field, gives it its own order back.
- **Copy format of this chart** copies the format of the chart chosen (its series colours, legend, labels, axes and axis ranges); on another chart, **Paste format of** *that chart* gives it the same format.

#### Add, move, copy and delete charts

- **⋯ menu of a chart** (or a right click on it): **New Chart**, **Duplicate Chart**, **Copy Chart**, **Cut Chart**, **Paste Chart on this slide** and **Delete Chart**. A KPI card, a text box or an image names itself the same way.
- **New Chart** puts an empty chart on the slide (the source of the chart chosen, no fields and no chart type, so any chart type can be chosen); **Duplicate Chart** puts a copy of it. A slide without a free place gets one first: a column more on its adjusted places, else the layout of its kind with the fewest places that leaves one free (its rows when it can).
- **Chart in progress:** until its shelves can draw it (a measure, a chart type and a Rows or Columns split; a KPI card, its field), a chart reads no CDR. The slide shows its empty place, the PPT leaves it empty, and its row in the template is a `Chart in progress` that keeps what it has in its `Format` column.
- **Empty values and zeros:** its **Filters** subpanel also leaves out the rows whose measure is empty (**Leave out empty values**) or 0 (**Leave out zeros**).
- **Move or swap:** drag a chart by its **⠿** handle onto another chart to swap their places, or onto a free place to move it there.
- **Free places** of the layout show **+ Add**: a chart (empty, as **New Chart**), a KPI card, a text box, a picture, or one copied or cut before (**Paste Chart**).
- **To another slide:**
  1. Copy it (**Copy Chart**, or choose it and press <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>C</kbd>) or cut it (**Cut Chart** or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>X</kbd>: it leaves its slide, which keeps at least one element).
  2. Choose the other slide.
  3. Paste it: **Paste Chart** in the **⋯** menu of the slide or of a chart of it, **+ Add** on a free place, or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>V</kbd>. It goes on the first free place, or on a place more as with **New Chart**, with its fields, filters and format, as an element of its own (only in this Design in This Design scope).
- **Delete Chart** (or <kbd>Delete</kbd> / <kbd>Backspace</kbd>) removes a chart; in This Design scope, a chart of the template is hidden in this Design.
- **Undo and redo:** <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd> undoes; <kbd>Shift</kbd>+<kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd> or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Y</kbd> redoes.
- **Esc** closes a menu or Chart Type, then leaves the chart chosen (in a field of the panel, it leaves the field), as a click anywhere in the viewer outside the charts, the panel and the bar of the Designer does.

A change the template cannot hold (a chart without a KPI or a split, for example) is refused with the reason and undone.

### KPI cards, text boxes and pictures

| Element | What it shows | In the PPT |
| --- | --- | --- |
| **KPI card** | One figure of the latest campaign of the Design (see below) | Drawn by the same renderer as in the viewer |
| **Text box** | Text written with the editor of the tickets (bold, lists, headings), its size, alignment and colour, with fields and parameters | A text box of its own, bold, bullets and headings kept |
| **Image** | A PNG, JPEG or GIF picture of up to 8 MB (an SVG can be saved as PNG first), fitted in its place keeping its ratio | A picture of its own |

**KPI card:**

- **Figure:** Average, Median, Percentile, Count of samples, Share of a value (%), or Share below / above a threshold (%), of a measure of a source with its filters.
- **Compared with:** the previous campaign, the best competitor (with **One card per** Operator, for example) or a target, green or red as it improves (**Higher is better**).
- **Colour band** (**Good from**, **Poor from**) and **Trend over the campaigns**.
- **Shape:** the cards keep their shape in a place of any proportions: a wide place shows one row of up to four cards, a tall or square one the columns that give the largest cards.

Pictures are kept in the table **PPT Images** and travel with the PPT Designs and PPT Templates whose slides use them, in exports, transfers and backups (an import adds those the workspace does not have; the CSV of a template downloaded alone names them only). Text boxes and pictures read no CDR.

### Save, drafts and the other actions

- **Save** stores the template (Template scope) and the differences of the Design. If another user saved the template since you opened the Designer, Save asks you to reload it first.
- **Drafts:** what is not saved yet is kept on the server, for you only, as a draft (table **PPT Drafts**): opening the Designer again offers to restore it or discard it. **Discard** goes back to what is saved. Drafts are not part of exports, transfers or backups.
- **More** offers:
  - **Save Design as…**: a Design of your own that follows the same template with the changes shown.
  - **Save as template…**: the slides shown as a new template.
  - **Detach from template…**: the Design keeps the slides it shows as its own and no longer follows its template; choosing a template for it again in PPT Designs follows that template as it is.
- Deleting a template that Designs follow detaches them first, so none of them breaks.
- Generate PPT and the reports of [Reporting](reporting.md) use the slides of the Design as saved. The comments of a slide stay with it when its title changes.

### Who can design

| Role | Slides of a Design (This Design) | Slides of a template (Template scope, parameters) |
| --- | --- | --- |
| **super-admin** | Any Design | Any template |
| **admin** | The Designs they created and those of user-editors | The templates they created and those of user-editors |
| **user-editor** | The Designs they created | The templates they created; **Save Design as** for a variant of another one |
| **user-viewer** | — | — |

The Designs and templates of another admin or super-admin (and the starter ones, which belong to `super`) are changed only by their creator and super-admins (see [Who changes a Design](#who-changes-a-design)).

App Events record what each user does in the Designer, each event read as a sentence:

- `design_designer_opened`: the Designer opened on a Design, with its template and what the user can change (This Design, its Template).
- `design_edited`: the edits not saved yet, without recording each one: the first edit after opening the Designer, then at most one event every 5 minutes with everything changed since the previous one (the save or the discard records the rest): slides added, removed, moved, hidden or shown, their title, subtitle and layout; charts, tables, KPI cards, texts and pictures added, removed and moved; and each property from what to what (chart type, KPI, filters, splits, legend, labels, axes, style, text). For example *slide 2 "Voice": chart "CSSR" chart type bar → line*.
- `design_slides_saved`: the slides saved, with every change against what was saved before (of the Design, and of its template when the Template scope was saved too); `report_template_saved_from_designer` names the Designs that follow that template.
- `design_draft_discarded`, with the changes discarded; `report_template_slide_ids_assigned`, `design_detached`, `report_template_saved_from_design` and `design_image_uploaded`.

The other changes of a Design are recorded with what they changed as well:

- `save_design` (Save Filters: each part of its selection from what to what, such as its NR Mode, Campaign, filters and dates);
- `rename_design` (the name before and after), `change_design_template`, `delete_design` (its name and template);
- `design_chart_added`, `design_chart_refreshed` and `save_design_comments` (the comments added and removed on each slide);
- opening a Design in the viewer is recorded as `design_opened`.

### Template parameters

A template can declare **parameters**, so that Designs that differ only in a city, a call family or a threshold share one template with no difference of their own (a *City Report* template and its London, Manchester and Cardiff Designs).

**Declare them** with **Parameters** in the bar of the Designer (Template scope):

- It lists them at the left, with their type and where they are used, and shows the one chosen at the right, where it is renamed and deleted.
- A template without parameters shows a card per type, which adds one; **+ Add parameter** under the list asks for its type:

| Type | Values |
| --- | --- |
| **Field values** | The values of any field of the CDRs or an Auto-calculated Field, chosen from the groups of fields as in the chart builder, with a search; one or several; none chosen means All |
| **Number** | Default, minimum, maximum, step |
| **Text** | Any text |

- **Names:** a parameter cannot take the name of a built-in token (`{Cities}`, `{Operators}`…): the first ones are named Chosen Cities, Threshold and Note.
- **How to use it** gives the condition to write (`City IN ({Chosen Cities})`), to copy or add to the filters of the chart chosen.
- A parameter in use cannot be deleted, and renaming one renames its uses.

**Use them:** write `{Name}` in a chart filter (`City IN ({City})`; with All the condition is left out), a numeric setting (`LQ < {Threshold}`, `Threshold = {Threshold}`, an axis range) or a title (`Voice quality in {City}`).

**Give them values:**

- Each Design chooses the values in **PPT Scope & Filters → Parameters**, applied and saved like its filters; until it chooses them, it uses their default values.
- The section shows only when the template has parameters: they are added in the Designer, never there.
- A report of [Reporting](reporting.md) gives a field-values parameter on a field of its common filters (Operator, Vendor, Region, Cluster, City…) the values chosen there. With values other than the Design's, the PPT goes without its saved comments, written for its own values.

## Generate PPT

Export the slides of a Design to PowerPoint, with the selection you choose.

### Choose the export inputs

Open **Generate PPT** from the library, filter panel or viewer. **Select PPT Scope and Filters** controls the export's exact selection, which can differ from saved defaults.

| Export subpanel | Settings |
| --- | --- |
| **Scope** | Scope (and vendor comparison) |
| **Main PPT Filters** | Campaigns (which choose the CDRs) and the CDRs they choose, the dates below them (the whole width), then Operators and Vendors, Regions and Cities |
| **Show All Filters** | Reveal the remaining main filters and Additional Filters |

- **Campaigns, no CDR selector:** **Campaigns** lists every campaign of the Design's NR Mode (with NSA & SA, it chooses the NSA CDRs and the SA ones keep the Campaign (SA) of the Design), with **Latest campaign**, **Latest 2 campaigns**, **Latest 3 campaigns**, **Latest 4 campaigns**, **Previous campaign** and **All available campaigns** first (each one alone).
- It starts with the Design's Campaign and lists below it, by type, the CDRs it chooses now; both appear as soon as the dialog opens.
- **Other choices** load from those CDRs and start with saved filter values, or all available values when unrestricted or no saved values remain available.
- **Cities** offers **Main Cities** first, exported as the Main Cities of the workspace.
- Changing campaigns or dates preserves selected values still available; an All selection includes new values.
- The browser remembers the dialog's last Scope, Campaigns and dates per Design/user.

**Auto comments**, in the Scope of the dialog (or a checkbox of the confirmation when the PPT is generated from the viewer), writes generated comments into this PPT only:

- **Writer:** the one the viewer generates comments with (the default one of Super Admin until it is changed in the menu of the comment tools). With more than one writer enabled, the dialog shows it as **Comment writer** beside Auto comments, and a change there is also the viewer's.
- **Where:** on the slides without comments, in place of the generated ones or in place of every comment.
- The Design keeps its own comments; the job's viewer shows those of the PPT, a relaunched job keeps its choice, and App Events records how many slides they were written on.

### Save defaults only when intended

| Action | Effect |
| --- | --- |
| **Generate PPT** | Export the dialog's selection |
| **Save Filters** | Also persist its Scope, dates, Campaigns and other filters in the Design |

- Save Filters is enabled when the dialog differs from the saved defaults (the vendor comparison counts only in Multivendor Comparison).
- A complete value selection equals an unrestricted field; saved values absent from the selected CDRs are ignored.
- If required, the export prepares the CDRs of its campaigns first.

> [!IMPORTANT]
> **Export selections take precedence for that job.** You can export applied or dialog-specific filters without saving them as PPT defaults. The job's Filters snapshot records what was exported.

### Follow the export

As soon as the job is queued, from the library or from the viewer, a progress panel follows it: its progress bar and stage (waiting in the queue, preparing the data, building the chart models, rendering the charts, writing the PowerPoint), its status, the charts and slides done and the time it has taken.

| Button | Effect |
| --- | --- |
| **Cancel Job** | Stop the job, as **Stop export** in [PPT Generation Jobs](#ppt-generation-jobs) |
| **Run in Background** (or ×, <kbd>Esc</kbd>) | Close the panel: the job keeps running and stays in PPT Generation Jobs and Background Tasks |
| **Download Again** | Download the PPT once more after it is ready |

When the job ends while the panel is open, the PPT downloads by itself and the panel says it is ready (or why it failed or was cancelled); a job left to run in the background is downloaded from its row in PPT Generation Jobs.

### Presentation contents and files

The PPT preserves template slides, layouts, chart proportions, titles, legends and saved comments.

- **Shape of each place:** every chart and table is laid out in the shape of its place, whatever the layout (one wide chart, four in two rows and two columns, a tall one beside two…), in the PPT, the Word and the viewer alike.
  - Nothing is stretched; pies, donuts and bubbles stay round; the maps fill their place showing more around their places.
  - KPI cards take the grid that makes them largest (four cards: two rows of two in a 16:9 place, one row in a wide one, one column in a tall one).
  - Multi KPI CDF Lines places its CDFs side by side or one above the other.
- **Subtitles:** chart subtitles use blue text and normal letter spacing; Title/Transition subtitles retain the template's yellow accent.
- **Title covers** match the viewer: Campaigns appear in orange above the divider; Scope, Regions and Cities appear beneath in green, cyan and pink.
- **Where:** generated PPTs, chart PNGs, tooltips and Canvas assets are stored under **output/reports/ppt-designs**.

| Filename part | Contents |
| --- | --- |
| Prefix | `yyyymmdd_HHMMSS` |
| Definition | NR Mode, PPT Name and Scope |
| Geography | Selected Regions joined by ` + `, or All Regions |
| Multiple campaigns | Campaigns joined by `_vs_` at the end |

Operators, Vendors and Cities remain in the job Filters snapshot and are omitted from filenames. Long names are shortened only for filesystem limits.

## PPT Generation Jobs

Follow, download and manage the PowerPoint exports.

Jobs continue on the server after you leave the page or close the [progress panel](#follow-the-export). The table records ID, creator, local date/time, NR Mode, Design, Scope, filters, slide/chart counts, status and progress.

| Action | Availability / purpose |
| --- | --- |
| **Download PPT** | Download an available completed presentation |
| **View PPT snapshot** | Open the job in the viewer with the template and inputs it was generated with |
| Chart actions | **Open PPT charts** in the [Charts Panel](#charts-panel), or download them |
| **Stop export**, **Retry export** / **Relaunch Job** | Manage work when the job's state permits (a ready job is relaunched) |
| Filter action | Inspect sources, dates, campaigns and filters in a tooltip/dialog |
| **Delete export** / **Delete All PPTs** | Remove jobs/files; requires user-editor, admin or super-admin. A PPT being generated is not deleted: stop it first (Delete All PPTs leaves it in the list) |

Excel-style header filters search job columns. The filter snapshot groups CDRs by Data/Voice/Speech and shows Campaigns above Operators.

> [!NOTE]
> **All Operators / Vendors / Regions / Cities refers to the job's selected CDRs.** Other workspace CDRs do not expand that selection. Saved values absent from those CDRs are not listed.

## Charts Panel

Browse the charts of the exported PowerPoint jobs.

### Find an exported chart

1. Filter by NR Mode, Design, Template, Scope, Region or City.
2. Select a **PowerPoint Job**.
3. Open a chart card in the expanded viewer, use **View Filters** to inspect the snapshot, or **View as Design** to open the job in the viewer.

- **Filters follow each other:** each filter offers only selections from jobs matching the other active filters.
- **Complete selections:** choices describe complete exported selections. A job with seven cities contributes one City choice containing those seven cities; All Cities/All Regions appears only for jobs exported with those selections.
- **Job selector:** identifies its local date/time, NR Mode, Design, Scope and recorded geography. Long lists expose their full values on hover.
- **Loading:** polling loads the newest matching completed job; each chart is read and drawn when it comes near the screen, so opening the page reads none of them.
- Each thumbnail opens in the expanded viewer with <kbd>Enter</kbd> or <kbd>Space</kbd> as well.

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

The reusable slide definitions that Designs follow.

**PPT Templates**, at the top of the PPT Designs library (for `user-editor`, `admin` and `super-admin`), opens the **PPT Templates Library** of the workspace in a dialog.

- **What you do there:** order, import, create, rename, duplicate, set the default, export, delete and edit its templates.
- **Saved at once:** each action is saved without leaving the dialog, which shows the list updated at once (its message, such as an import done or refused, in a window over it).
- **New Template** opens the new template in its [Designer](#designer).

| Action | What it does |
| --- | --- |
| **New Template** | Creates a template with its cover and opens it in its Designer, where its slides are added |
| **Import** | Imports a template CSV, with an optional template name (see below) |
| **Edit** (✎) | Opens the template in the viewer and its [Designer](#designer) (see below) |
| Rename | The name field of the row |
| **Duplicate** | Creates `- Copy`, with its own identity |
| **Set default** (★) | Makes it the default of the workspace |
| **Export** (⬇) | Downloads that individual CSV; portable ZIP export is available under Import / Export / Transfer |
| **Delete** (×) | Deletes it (see who can, below) |

**Where templates live:**

- Templates belong to the active workspace and are stored in that workspace database's `report_templates` table.
- Import, export, backup and transfer packages serialize them as portable CSV files, but those files are package artifacts rather than the live source of record.
- Obsolete `slides-templates` directories are removed by the current migration and portability flows.
- New workspaces start without templates.

**One template for every NR Mode:**

- The library keeps the templates of the workspace, one of them the default. A template has no NR Mode of its own: it serves the CDRs of any NR Mode, and each Design (or report of [Reporting](reporting.md)) chooses the NR Mode it reads.
- Its slide titles, subtitles and chart titles name that NR Mode where they write `{NR Mode}` (NSA, SA or NSA & SA) or `{NR Mode Name}` (Non-Standalone, Standalone or Non-Standalone & Standalone), so one template gives the NSA, the SA and the [NSA & SA](#nsa-sa-in-one-design) decks.
- PPT Designer also writes the selection of each Design where they name it (`{Campaigns}`, `{Operators}`, `{Cities}`…, see [Fields in titles and text boxes](#fields-in-titles-and-text-boxes)).
- Every row has the **NR Mode** field (that of its CDR): a chart keeps one NR Mode with the filter `NR Mode IN (SA)` (its title's `{NR Mode}` then names that one), and NR Mode can split or label its series in Rows Split, Columns Split, Legend and the Dynamic Rows/Columns Field.
- Template names are unique in the workspace.

**Rights:**

- PPT Templates belong to PPT Designer, not to Config: their actions use the addresses of PPT Designer (`/ppt-designer/templates/…`; the former `/workspace-config/report-templates/…` ones lead there), need PPT Designer in the user's Modules Profile and are recorded in App Events under PPT Designer, and they follow its rights.
- A template is changed (saved, renamed, overwritten on import, given copied slides or charts, edited in the [Designer](#designer) or from Chart Builder) and deleted as a Design (see [Who changes a Design](#who-changes-a-design)): by the user who created it and super-admins, and by admins too when a user-editor created it.
- **Owner:** it belongs to the user who created it (with New Template, Import CSV, Duplicate or **Save as template**); one brought by Admin Import / Transfer belongs to its creator on the source server when that user is active here, otherwise to whoever imports it.
- **The other users** customize it from the [Designer](#designer) of their own Designs; for them its name, **Delete** and **Edit PPT Template** are disabled, with a tooltip that says why. A user-viewer sees and exports them.
- The slides of a template (with their charts, and its parameters) are edited from any Design that follows it, and kept in the template's CSV (its `Format` column).

**Order and columns:**

- The library lists the templates in the order of the workspace: drag a template by the tab on the left of its name (or press <kbd>↑</kbd> and <kbd>↓</kbd> on the tab) to move it. The new order is saved at once for every user of the workspace and followed by the **Template** of a new Design.
- Until a template is first moved the library is sorted by name (an NR Mode written in a name, such as `NSA - Report`, is ignored for the order); templates created, duplicated or imported later go to the end.
- App Events record each new order (`reorder_report_templates`, with the order before and after), and exports, transfers and backups carry it (see [Import / Export / Transfer](administrator-config.md)).
- Its columns show the creation and last update times and **Last Updated by**, the user who last imported, edited, renamed, duplicated or promoted the template.

**Edit** opens the template in the viewer and its [Designer](#designer) as a PPT of its own, never listed among the PPT Designs:

- It reads the CDRs of the NR Mode and Campaign it was last opened with (NSA and Latest 2 campaigns the first time; PPT Scope & Filters changes them).
- Every change of the Designer goes to the template (its bar reads **PPT Template** with the number of Designs that follow it).
- **More** offers only **Save as template…**, and it makes no PPT of its own (its Designs do).
- **Edit PPT Template**, the pencil at the top of the viewer, shows the template as a table (see [Table view](#table-view-template-editor)), for Find & Replace for example.

**Import** accepts a CSV name or derives it from the filename, can convert a legacy catalogue when prompted and requires explicit overwrite confirmation for a case-insensitive name collision.

**Rename:** renaming saves when you leave the name field or press <kbd>Enter</kbd>; the field keeps its previous name and shows an error if the save fails. Each template has an identity that never changes, and each Design refers to its template by it, so a renamed template stays the template of its Designs (whose names, when they repeat the template name, follow it too); a duplicate gets its own identity.

**Default:** one template is the default within a workspace. Reporting initially selects that default but does not change it when a user chooses another template for one job. A default template cannot be deleted until another template becomes default.

**Delete:** only the users who change a template delete it (see [Who changes a Design](#who-changes-a-design)); for the other users **Delete** is disabled and its tooltip says why.

**Templates of earlier versions:** workspaces of earlier versions kept an NSA and an SA library. When they open:

- Each pair of templates that only differed in the titles naming the mode (for example **NSA - NetCheck CDR Report** with *Non-Standalone* and **SA - NetCheck CDR Report** with *Standalone*) becomes one template named without the mode (**NetCheck CDR Report**) whose titles use the tokens, and the Designs and PPT jobs that used either copy use it.
- A title only one copy named (such as *SA RF Quality Analysis* beside *RF Quality Analysis*) takes `{NR Mode}` in both.
- The other templates keep their names, an SA one named as an NSA one taking " (SA)".
- The App Events record it (`report_templates_nr_mode_merged`). Packages and backups of earlier versions are imported the same way.

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
- **Find & Replace** (or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>F</kbd> inside the editor) searches every editable cell of the template.
  - Matching cells are outlined and the current one is highlighted; <kbd>Enter</kbd> and <kbd>Shift</kbd>+<kbd>Enter</kbd> (or Next and Previous) move between them.
  - **Replace** changes every occurrence in the current cell and **Replace All** changes every occurrence in the template after a confirmation.
  - Replacements are ordinary unsaved edits until **Save Template**; **Match case** restricts matching to the exact capitalization.

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

**Saving:**

- **Save Template** validates and persists the complete grid atomically.
- Design comment reconciliation runs separately when slide identity changes; any required combined CDR update also runs after the save response. A combined CDR update is queued only when a template adds a source field missing from that CDR table.
- The PPT viewer refreshes the saved template when the editor closes.
- Removing the last template reference leaves the existing column available for future reuse.
- Close, Escape and backdrop actions preserve the editor when unsaved changes still require a decision.

## Report Template reference

This is the canonical authoring reference for the templates used by [PPT Designer](ppt-designer.md). The common `assets/powerpoint-templates/Template_VodafoneThree.pptx` supplies the masters, named layouts and placeholders. Each distinct `Slide` value creates one slide; chart rows sharing that value fill its chart placeholders in row order.

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

> [!TIP]
> **See every chart type built:** open the Designer of the example Design **DT Analyzer - All Supported Chart Types** to see how each chart is built.

Every workspace receives once the example template **DT Analyzer - All Supported Chart Types** and its Design of the same name (NR Mode **NSA & SA**, the latest 2 campaigns of each NR Mode):

- **Slides:** after its title slide, eight slides of four charts, a slide with the two maps side by side and a slide of four KPI cards (DL and UL throughput, call setup time and LQ, each one card per operator).
- **What they draw:** every chart type above on the CDRs of the workspace, never more than two columns a slide (wider frames would stretch the charts), each with the measure and shelves it suits: the CDF of the DL throughput of the latest two campaigns, NR MCS against NR CQI for Scatter, the hour of the day for Lines, Dual Lines, Areas and Bars and Line, and the CDRs of NSA for the charts that compare the campaigns of one NR Mode (`NR Mode IN (NSA)`: CDF Line, Bullet Graph, Symbol Map and the KPI cards).
- The charts split by Region leave out the tests of no Region (`Region != (blank)`).
- Deleted, it is not added again.
- **Earlier names:** a workspace that received it before as **All Chart Types** (with its Design **NSA - All Chart Types**) or **DT Analyzer - All Chart Types** has them replaced in place when they are as they were shipped (App Event `starter_examples_replaced`); changed, they stay beside the new ones.

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

`Direction` says which values the colours show as good: by default the KPI tells (lower is better for durations, latencies, errors and failures; higher for throughput, RSRP, SINR, MOS…), `Higher is better` or `Lower is better` say it, and `Neutral` (or a KPI without a direction, such as a count) uses blues. These settings are kept among the Filters of the row, as `Threshold`, `Buckets` and `Bin Size` are, and are set under the chart types.

### Chart recipes

The examples show chart-specific cells. Add the shared `Slide`, titles and `Layout` appropriate to the target layout.

#### 100% Stacked Vertical Bars

Use for proportions, success ratios and categorical quality splits. KPI categories become stack segments. A KPI of vendors (`Vendor`) takes the colours of the [Vendor Maps](workspace-config.md); the Format of the chart can change the colour of any segment.

```text
Source Dataset: CDR-Voice
KPI: Call_Status
Chart type: 100% Stacked Vertical Bars
Filters: Call Family IN (VoLTE, MultiRAB); Operator IN (Vodafone, 3, EE)
Rows Split: Call Family
Columns Split: Operator × Campaign
Legend Position: Right
```

A second measure `COUNTD(field)` makes the bars share out the distinct values of that field instead of the rows, each value once per bar and segment. The share of the cells of each Vendor per campaign, for example, counts the tests served by one cell, where `Cell_ID` is that cell and `Vendor` its vendor (`Cell_ID_A` in Voice CDRs and `Cell_IDs_A` in Speech CDRs):

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

In the [Designer](#designer) and in [Chart Builder](chart-builder.md), `Rate Bucket` and `Buckets` are in the **Distribution classes** group of **Fields**, although they are not columns of the CDRs:

- **Where they go:** drag `Rate Bucket` to the end of **Columns** and `Rate Bucket` or `Buckets` to **Legend**. `Rate Bucket` also goes on **Rows**, and `Buckets` goes only on **Legend**.
- **The limits:** write them by clicking either pill (with more pills on its shelf, **Limits of the classes…** in its menu) or in the **Buckets** box of **Chart Type**: `1,5,20` for ranges, `< 2,5,20,100` or `<= 2,5,20,100` for `belowN` categories.

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
| Tests without a value | `Region != (blank)`, `City = (blank)`: `=`, `!=`, `IN` and `NOT IN` read a missing value as the charts show it, (blank) |

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

- **Names** follow `Title + N rows + M columns`, optionally followed by `+ comments down` or `+ comments right`.
- **Physical and virtual:** the 108 fixed grids and four structural layouts exist physically in the reference PPT. The nine dynamic options are virtual: the renderer selects a fixed grid from the distinct values of their row and column fields.
- **Layout selector:** the widened Layout cell-assistance selector lists Title Page, Title Only, Transition and Black logo end slide first, followed by the nine dynamic grids and then the fixed grids. Long names stay on one line; narrow screens can scroll horizontally. Structural layouts have blue shading, dynamic layouts purple shading and the selected option yellow shading; selection retains its position without a duplicate at the top.
- Other native layouts remain internal to structural slides.
- **Historic names** are normalized on import and in stored templates; exports use the canonical names.
- Grids without comments use the full chart area.
- `Source Dataset = CDR-All` exposes the union of Data, Voice and Speech fields, including normalized RF fields and `CDR_Type`, in cell assistance.

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
> **Vendor comparison:** When **Report type** is **Multivendor Comparison**, the **Vendor comparison** selector appears to its right. **Vendor (All Operators Combined)** is the first and default option when opening the export dialog; it pools selected operators using the same `Vendor` value. Choose **Operator_Vendor** to keep each operator separate. Campaigns remain separate. The job retains this choice for retries. Dynamic vendor grids use up to six columns per slide and keep operators of the same vendor together where possible.

## Portability and maintenance

**Export Design** creates a versioned ZIP accepted by Admin Import; imports also accept legacy standalone JSON definitions. A compatible destination template is required.

PPT Designer was called **PPT Dashboards**, and its Designs **Dashboards**. A workspace of before keeps them when it opens: its Designs, their PPT jobs and charts (moved to `output/reports/ppt-designs`), drafts, pictures and App Events take the new names, and the Modules Profiles, Interface Settings, tickets and scheduled backups name PPT Designer. Links to `/ppt-dashboards`, to this chapter and to the presentation of PPT Dashboards open those of PPT Designer, and packages, backups, transfers and the reports of [Reporting](reporting.md) of before are imported as Designs.

| Included in the definition | Not copied by PPT definition export |
| --- | --- |
| Name, NR Mode of its CDRs and template association | Source CDRs |
| Scope, dates, saved filters (Campaign included), hidden/additional fields, parameter values | Prepared cache files |
| Slide comments | Generated presentation assets |
| Its differences from the template, or its own slides once detached | Unsaved Designer drafts |

- **CDRs of the destination:** a Design chooses its CDRs from its NR Mode and Campaign in the workspace where it is opened, so an imported Design uses the CDRs of the destination with the same campaigns (Latest campaign, Latest 2, 3 and 4 campaigns and Previous campaign, among its newest ones).
- **Designs with CDRs of their own** (exported by earlier versions) take the campaigns of the CDRs of the destination with the same name and type, or else its newest two campaigns; check the inputs after import.
- **Designs exported when templates had an NR Mode of their own** read that NR Mode as part of their selection and use their template as the destination knows it now (its NSA and SA copies merged into one); an SA Design named as an NSA one takes " (SA)".

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
> **Viewer comparison:** In the PPT viewer, selecting **Multivendor Comparison** reveals **Vendor comparison** to the right of Scope. Choose **Vendor (All Operators Combined)** to pool operators sharing a vendor, or **Operator_Vendor** to keep their results separate. Changing this selector renders the Design again immediately. Switching into multivendor scope defaults to Vendor (All Operators Combined); saved Designs retain their saved comparison. Use **Save Filters** to persist the choice.

### Vendor-only report ordering

For **Vendor (All Operators Combined)**, web charts/tables and PowerPoint reports list actual vendors alphabetically, then Ericsson (Mixed) (and the former Mixed Vendor), the former Other Vendor, All Vendor(s), operator-only identities labelled **Operator - All**, and finally Mixed (non-Ericsson). This order also applies to dynamic chart grids. Mixed/Other groups remain visible unless an explicit template filter excludes them. Vendor mapping persists `Operator - All` in `Operator_Vendor` and `Vendor` for operators without an assigned vendor. Existing values without the suffix remain compatible.

In multivendor charts, operator-only identities such as **EE - All** retain the colour assigned to that operator in Operator mappings. This applies to web and newly generated PPT charts; the display suffix does not create a new colour identity. Real vendors retain their configured vendor colours.

The default Campaign is **Latest 2 campaigns** for **Operator Comparison** and multivendor **Vendor (All Operators Combined)**, and **Latest campaign** for multivendor **Operator_Vendor**. Changing the vendor comparison updates a Campaign that still has the default; a chosen Campaign is retained.

## Tips & shortcuts

Gestures and keys that save time. Keys work while the viewer has the focus and you are not typing in a field.

### Viewer and larger view

| To… | Do this |
| --- | --- |
| Go to the next slide | <kbd>→</kbd>, <kbd>↓</kbd>, <kbd>Page Down</kbd> or <kbd>Space</kbd>, or turn the mouse wheel down over the slide (one slide per turn). On touch: swipe left. |
| Go to the previous slide | <kbd>←</kbd>, <kbd>↑</kbd> or <kbd>Page Up</kbd>, or turn the wheel up over the slide. On touch: swipe right. |
| Go to the first or last slide | <kbd>Home</kbd> or <kbd>End</kbd> |
| Read the value of a point | Point at it: a tooltip names its label, series and value (on a CDF, its cumulative %) |
| See the tools of a chart (**Dataset**, **Expand**, **Zoom**) | Point at the chart or focus it. On touch: tap it; they show for 3 seconds. |
| Open a chart larger | Double-click it, or **Expand** |
| Go to the next or previous chart of the larger view | <kbd>→</kbd> or <kbd>←</kbd>. On touch: swipe left or right. |
| Close the larger view or a dialog | <kbd>Esc</kbd>, or click the dark backdrop around it |
| Zoom a chart at the pointer | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + mouse wheel, or pinch on the touchpad |
| Zoom into one area of a chart | With the mouse, drag a rectangle over the plot (at 100%; not from the title or the legend) |
| Move around a zoomed chart | Drag it, or use its direction arrows |
| Hide or show a value on every slide | Click its entry in the legend |
| Keep only, hide or show values of a legend or an axis | Right-click a legend entry or an axis label. In the menu, <kbd>→</kbd> opens a **Show** submenu, <kbd>←</kbd> goes back and <kbd>Esc</kbd> closes it. |
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
| Choose a chart, KPI card, text box or picture | Click it |
| Open its menu (Duplicate, Copy, Cut, Paste, Delete, Fill the free places…) | Right-click it, or its **⋯** menu in the panel |
| Open the menu of a slide | Right-click its thumbnail at the left, or its **⋯** menu |
| Move a slide | Drag its thumbnail |
| Move a chart, or swap two charts | Drag its **⠿** handle onto a free place or onto another chart |
| Copy, cut or paste the element chosen | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>C</kbd>, <kbd>X</kbd>, <kbd>V</kbd> (it is pasted on the first free place of the slide shown, also on another slide) |
| Delete the element chosen | <kbd>Delete</kbd> or <kbd>Backspace</kbd> |
| Undo or redo | <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd>; <kbd>Shift</kbd>+<kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Z</kbd> or <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>Y</kbd> |
| Edit the slide title or subtitle in place | Click it in the header of the viewer; <kbd>Enter</kbd> or leaving it keeps it, <kbd>Esc</kbd> cancels |
| Widen or narrow the panel | Drag its left edge (kept for your next visits); double-click the edge for its usual width; with the edge focused, <kbd>←</kbd>/<kbd>→</kbd> change it by 24 px |
| Pick a grid layout | Point at the cells of **Grid** to preview its rows × columns, then click |
| Step back | <kbd>Esc</kbd> leaves a field, then closes a menu, then Chart Type, then leaves the element chosen; a click outside the charts and the panel also leaves it |

### Charts in the Designer

These work on the chart already chosen.

| To… | Do this |
| --- | --- |
| Change the colour, width, line or opacity of a series | Click its entry in the legend. On a chart not chosen, the click hides the series in the whole Design, as in the viewer. |
| Change the range of a numeric axis | Click its labels: drag the two ends of the slider (**Automatic** gives it back) |
| Choose the values of a text axis | Click its labels: untick values, **Only** one, or **Show all** |
| Change the order of the values of Rows or Columns | Drag an axis label, header or row label before or after another; a purple bar shows where it goes (**Default order** gives it back) |
| Put a field before, after or in place of a pill | Drop it near the edge of the pill, or on its middle to replace it |
| Choose the chart type | Click the **Chart Type** tab on the right edge of the chart; <kbd>Esc</kbd> or a click outside closes it, and the wheel scrolls it |
| Draw the chart again from its CDRs | **Refresh chart**, shown over the chart while designing |

### Adjust places

| To… | Do this |
| --- | --- |
| Resize rows or columns | Drag the lines between them |
| Choose several places (to **Merge** them) | Click a place, then <kbd>Shift</kbd>+click another: the places between them are chosen |
| Empty the places chosen | <kbd>Delete</kbd> or <kbd>Backspace</kbd>, or **Delete** |
| Put a place back in an empty cell | Click its **+** |
