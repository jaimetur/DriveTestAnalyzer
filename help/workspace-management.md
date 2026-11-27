# Workspace Management

Workspace Management is the first operational module. It controls isolated workspaces, their storage, dataset ingestion, processing queue and vendor mapping workflows.

> [!IMPORTANT]
> **Ready data first.** Wait for CDR processing to finish before analysis. A detected input type and a completed upload do not mean the dataset is ready.

## Presentations & Guide

```presentations
workspace
workspace-config
guide:workspace-management.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Create, open, rename or delete a workspace | [Workspace Lifecycle](#workspace-lifecycle) |
| Upload CDRs, mappings, inventories and polygons | [Data Ingestion](#data-ingestion) |
| <span class="guide-sub">↳ Follow an upload step by step</span> | <span class="guide-sub">↳ [Upload Workflow](#upload-workflow)</span> |
| <span class="guide-sub">↳ Name the campaign of a CDR</span> | <span class="guide-sub">↳ [Campaign](#campaign)</span> |
| <span class="guide-sub">↳ Choose a Final, Weekly or Daily CDR</span> | <span class="guide-sub">↳ [CDR Stage: Final, Weekly and Daily](#cdr-stage-final-weekly-and-daily)</span> |
| <span class="guide-sub">↳ Upload the vendor of each cell</span> | <span class="guide-sub">↳ [Multivendor Mappings](#multivendor-mappings)</span> |
| Understand how the NetCheck CDRs are processed | [NetCheck CDR Support](#netcheck-cdr-support) |
| <span class="guide-sub">↳ Read the cards of the datasets</span> | <span class="guide-sub">↳ [Datasets cards](#datasets-cards)</span> |
| <span class="guide-sub">↳ Use the combined CDR tables</span> | <span class="guide-sub">↳ [Combined CDR Tables](#combined-cdr-tables)</span> |
| <span class="guide-sub">↳ Map the vendor of each row</span> | <span class="guide-sub">↳ [Vendor Mapping](#vendor-mapping)</span> |
| Look at the rows of a CDR and enrich it | [Dataset Inspection and Enrichment](#dataset-inspection-and-enrichment) |
| <span class="guide-sub">↳ Preview the rows of a dataset</span> | <span class="guide-sub">↳ [Dataset Preview](#dataset-preview)</span> |
| <span class="guide-sub">↳ Add the Layer3 Logs of a campaign</span> | <span class="guide-sub">↳ [Layer3 Logs](#layer3-logs)</span> |
| <span class="guide-sub">↳ Add the carrier aggregation appendix</span> | <span class="guide-sub">↳ [CA Appendix](#ca-appendix)</span> |
| <span class="guide-sub">↳ Add the Master Grid of the sites</span> | <span class="guide-sub">↳ [Master Grid](#master-grid)</span> |
| Fix a failed upload | [Troubleshooting](#troubleshooting) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Workspace Lifecycle

Create, open, close, rename, duplicate and delete workspaces; each keeps its databases, uploaded files and generated output isolated. Open a workspace before using Design, Reporting or Chart Builder.

- **One open workspace for the server:** opening another one changes it for everybody. A user the open workspace was not given to (by name or through a Workspace Group; super-admins open every one) sees **Workspace** as with none open, to open one of theirs, and is refused its data everywhere else: its modules, datasets and previews, Workspace Config, Datasets Management and App Logs.
- **New workspace:** a dialog asks for the name, the **CDR type** (NetCheck CDR by default; Umlaut CDR, P3 CDR and RootMetrics CDR are coming soon, see [CDR type](workspace-config.md#cdr-type)), the **Country** and, for super-admins, the **Access**; **Create and open** creates it. A country of the 50 listed gives it the [Operator Maps](workspace-config.md#operator-maps) of its mobile operators, in their corporate colours; **None** starts without Operator Maps.
- **Workspaces table:** shows the CDR type, country, access and size of each workspace, in that order after its name, and changes them; **✓** saves the row.
  - **CDR Type** changes only while the workspace has no Data, Voice or Speech CDRs.
  - A new **Country** adds its operators that the Operator Maps do not have yet and keeps the existing labels.
  - **Access** (super-admins) chooses the Workspace Groups that open it and the users it is granted to individually. Super-admins also give workspaces to groups in [Super Admin → Workspace Groups](super-admin.md#workspace-groups).
- **Starter content:** a new workspace, and every existing workspace once the first time it opens after an update, receives the starter content shipped with the application that it does not have yet, matched by name so nothing of its own is replaced; deleted or renamed starter content is not added again. It is the content of the UK workspace without what only fits the UK (its regions, London, its cities one by one and its operators):
  - **Scoring methodologies:** **NetCheck 2025**, **NetCheck 2026** (active) and **NetCheck 2026-Q3**; a methodology shipped later reaches every existing workspace once, without changing its active methodology. Every Scoring section scores each campaign with its own methodology.
  - **Report Templates:** eight, each serving every NR Mode: *NetCheck CDR Report* and *NetCheck CDR Report (Main Cities)*, titled *NetCheck CDR Analysis*, *RF Quality (RSRP & SINR)* (see [RF Quality template and Design](network-insights.md#rf-quality-template-and-design)) and the examples *DT Analyzer - Tableau Dashboards*, *DT Analyzer - Tableau Charts*, *DT Analyzer - Tableau Charts - Only Maps*, *DT Analyzer - FDFS DL (NSA & SA)* and *DT Analyzer - All Supported Chart Types*.
  - **Designs:** one per NR Mode for each of the first three templates (*NSA - NetCheck CDR Report*, *SA - NetCheck CDR Report*…), on the Latest 2 campaigns, the *(Main Cities)* ones on the Main Cities of the workspace; and one [NSA & SA](ppt-designer.md#nsa-sa-in-one-design) Design for each example but *Only Maps*: *DT Analyzer - Tableau Dashboards*, *DT Analyzer - Tableau Charts* and *DT Analyzer - All Supported Chart Types* (an [example of every chart type](ppt-designer.md#supported-chart-types)) on the Latest 2 campaigns of each NR Mode, and *DT Analyzer - FDFS DL (NSA & SA)* on the Latest 3 campaigns in NSA and the Latest campaign in SA. The *FDFS DL (NSA & SA)* and *All Supported Chart Types* examples reach every existing workspace once too, replacing in place their earlier versions (*FDFS DL (NSA & SA)*, *All Chart Types* and *DT Analyzer - All Chart Types*) where they are as they were shipped.
  - **Auto-calculated Fields:** `Call_Family`, `Test_Family`, `Test_Result_Group`, `RAT_Group` and `NR_Mode_from_RAT` (see [Auto-calculated Fields](#auto-calculated-fields)).
  - **Scoring report configurations:** *National*, *National - Best Network Only*, *National - Most Reliable Network Only*, *National & Main Cities* and *National per Vendor*, with Country Areas of the Regions and the Main Cities.
  - **Query Builder queries:** seven (calls, failures, setup time, POLQA, data tests, tests per city and the FDTT throughput of n78 with and without another operator on the same NR-ARFCN).
  - **Favourite Scorings:** 18 (*Latest Campaign*, *Latest 2*, *3* or *4 Campaigns*, *Previous Campaign* and *All Campaigns* of *All Regions*, in NSA, SA and NSA vs SA, with the *Country Areas: Regions & Main Cities*), which take the CDRs of their Campaign choice once the workspace has them.
  - **Reports:** 12 reports of [Reporting](reporting.md), each in NSA and SA for the whole country, with the shipped Designs of their NR Mode checked and no schedule: *SCO (@All Campaigns)* and *SCO (@Lastest 4 campaigns)* (Scoring), *SCO+NI+NQ (@Latest 4 campaigns)* (with Network Insights and Non-Qualified Calls), *SCO+NI+NQ+PPT+CDR (@Latest 2 campaigns)* (with the Designs and CDR Analysis too), and *Weekly PPT (@Latest campaing)* and *(@Latest 2 campaings)* (with the Designs).
  - **Operators:** the Favourite Scorings and the reports choose every operator (their Focus and excluded operators are those of the Operator Maps); no template, Design or report filters an Operator, nor Vendors by their operator.
  - **Vendor and Campaign Maps:** the default [Vendor Maps](workspace-config.md#vendor-maps) and [Campaign Maps](workspace-config.md#campaign-maps).

## Data Ingestion

> [!IMPORTANT]
> **Who changes datasets.** Only admins and super-admins upload datasets: the other roles see a card in **Data Ingestion** that says so, and the server rejects their uploads; `user-editor` accounts still manage the datasets of the workspace. `user-viewer` accounts only see them: uploading, deleting, reprocessing, stopping, mapping or clearing datasets, changing their Campaign, NR Mode, CDR Type, CDR Stage or Active? choice and recreating combined tables are hidden and rejected by the server.

Only successfully processed datasets can be used by Design, Chart Builder or Reporting.

### Supported Input Types

- **CDR-Data**, **CDR-Voice**, **CDR-Speech:** `CSV`, `XLS`, `XLSX` or `XLSM`.
- **Multivendor Mapping:** the cells that give the CDRs their Vendor, for one or several Operators (tabular).
- **Network Inventory:** the cell inventory of any Operator, in any tabular layout or as a Cell Configuration `KMZ`/`KML` package (alone or in a `ZIP`).
- **Regions**, **Clusters**, **Vendors — Geospatial:** `GeoJSON`, `JSON` or a zipped shapefile (see [Cluster polygons](#cluster-polygons)).
- **Layer3 Logs:** `CSV` files or their `ZIP`; see [Layer3 Logs](#layer3-logs).
- **CA Appendix:** an `XLSX` workbook, `CSV` files or their `ZIP`; see [CA Appendix](#ca-appendix).
- **Master Grid:** the `XLSX` Master Grid List of the sites; see [Master Grid](#master-grid).
- **Other supported dataset:** offered on upload, and as **Other Datasets** in the Dataset Type filter, only while the workspace has such datasets.

### Upload Workflow

1. Open the target workspace (as an admin or super-admin).
2. Select one or more files in **Data Ingestion**, or drop them on its **Drop workbooks or browse** zone.
3. Review the proposed type of every file, proposed from its name (for example `NetCheck_CDR_Data_2026_Q2.xlsx` → CDR-Data, `NetCheck_CDR_Voice_2026_Q2.xlsx` → CDR-Voice, `VF3_All_Vendor_Week41.xlsx` → Multivendor Mapping) and editable.
   - The CDR types carry the CDR type of the workspace (*NetCheck CDR — Data*, *Umlaut CDR — Voice*...).
   - In an Umlaut workspace each service workbook is proposed its type from its service (SQ_Samples workbooks are Speech, Calls workbooks Voice, data services Data); the All_Data and All_Voice workbooks, which summarise the others, ask for a type and offer **Leave out**, which removes them from the batch.
4. Review the details of each file:
   - **CDRs:** the proposed [NR Mode](#nr-mode), [CDR Stage](#cdr-stage-final-weekly-and-daily) and **Flex campaign** (see [Flex campaigns](#flex-campaigns)), and optionally the Vendor source and the ready Regions and Clusters mappings (see [During Upload](#during-upload)).
   - **Vendor polygons and Network Inventories:** their **Operator**, proposed from the file name.
   - **Multivendor Mappings:** their **Operators** (or leave them to be read from their cells) and their **Snapshot date**.
5. Confirm the batch with **Upload and process**. The files upload in the background, in chunks, to the workspace where the upload started.
   - **Keep working:** change page, module or workspace; the upload continues (the floating background task card shows its progress) and its datasets are processed in that workspace.
   - **Order:** mappings, polygons and inventories upload first; each file starts processing as soon as it is uploaded, up to **Maximum simultaneous tasks** ([Application Config](app-config.md)) in parallel, and the CDRs wait for the mappings of their batch.
   - **Closing the browser:** the browser keeps a copy of the chosen files until the upload ends, so an interrupted upload continues the next time the application is opened. When it cannot keep them (for example a very large batch over its storage quota), the card asks you to keep the page open, and leaving the page asks first.
   - **Stop** on its card cancels it.
6. Follow every item in the **Datasets** panel (Data Processing) and continue only when the status is **Processed**.

### Cluster polygons

Regions, Clusters and Vendors polygons share the geospatial formats: `.geojson`, `.json` or a `.zip` with exactly one `.shp` and its companion files (`.shx`, `.dbf`, and `.prj` to declare its coordinate reference system). The upload proposes Clusters for geospatial filenames containing `cluster`.

- **Content:** non-empty, valid Polygon or MultiPolygon geometries with a coordinate reference system, and non-blank names in `Cluster`, `Cluster_ID`, `Cluster_Name`, `ClusterName` or `Name`.
- **After validation:** the dataset is Processed, with no CDR NR Mode or KPI analysis; Preview draws its polygons on a map (see [Dataset Preview](#dataset-preview)), the original file stays in the workspace input directory, it appears in the Dataset Type filter and its metadata table in Database Management.
- **Where it is used:** the required input of **Network Insights → Cluster Sites Density** (importing it does not calculate site density yet), and the **Points Lost Map** of Scoring & GAP Analysis per Cluster (and per Region with Regions) on the polygons applied to the scored CDRs.
- **Applying to CDRs:** like Regions, through the **Cluster mapping** selector beside each CDR when importing (the newest ready Clusters dataset is proposed) or the **Cluster Mapping** field of the Map dialog (disabled, with a note, until the workspace has a ready Clusters dataset; Regions behave the same way). Each sample's `Cluster` takes the name of the polygon containing it; existing non-empty source `Cluster` values are kept, and samples without coordinates or outside every polygon stay empty.
- **Transfers:** kept by workspace duplication, export/import, transfer and backup/restore when workspace data and input files are included. Database-only backups keep the registration metadata but need the original input files to recover the polygons.

### Multivendor Mappings

Choose **Multivendor Mapping** for a file whose only purpose is to give the CDRs their Vendor: a CSV or Excel file with a Vendor column and a cell identifier as in a [Network Inventory](#network-inventories) and, for several Operators, a `Network` column. It is proposed for tabular files whose name contains `Multivendor`, `Vendor Mapping`, `All Vendor`, `VFUK`, `Vodafone`, `3UK` or `Three`.

- **Not a network source:** Network Insights, Non-Qualified Calls and the DT Analyzer RCA keep reading the Network Inventories, however recent the mapping is and whichever cells it leaves out (a file with only LTE cells, for example).
- **Operators:** the Operators it gives a Vendor to, chosen in the upload or, when none is chosen, read from its cells once processed: the Operators that the networks of its `Network` column serve, according to the [Serving Networks](workspace-config.md#serving-networks). A file without a `Network` column belongs to the one Operator chosen for it. They are shown and changed in its row of the **Multivendor Mappings** card (recorded in App Events); map the CDRs again to apply a change.
  - Only the Operators of the Multivendor Mappings receive a Vendor: an Operator left out of all of them keeps `<Operator> - All` (no Network Inventory gives it one either), but every source still gives it its serving cell (`Serving_Network`, `Serving_Host_Network`, `Serving_Site_ID`…).
  - Leave out an Operator whose cells are only partly known, for example O2, whose cells are in the files only where Vodafone hosts them: Scoring then shows it as one **All** bar in every split by Vendor, as EE.
- **Snapshot date:** as for a [Network Inventory](#network-inventories): chosen, else in its file name (also a week such as `Week41` or `2026_W41`, which gives the Monday of that week), else its upload date.
- **Storage:** its cells are kept apart, in the **Multivendor Mapping Cells** and **Multivendor Mapping Snapshots** tables of Database Management.

### Network Inventories

Choose **Network Inventory** for the cell inventory of any Operator, whatever its layout. It is proposed for tabular filenames containing `inventory` and for every KMZ or KML file and ZIP package of them.

- **Operator:** proposed from the file name (`O2_Network_Inventory.csv` → O2) and changeable in the **Network Inventories** card. **Multi-operator (Network column)** takes the owner of each cell from its `Network` column, so one inventory can describe several networks (Vodafone, H3G and Telefonica cells, for example). The VFUK and 3UK files of earlier versions are listed here too, with the same choice of Operator, and keep mapping the Vendor.
- **Used for Vendor Mapping:** the tag on the rows of the Network Inventories and Multivendor Mappings from which CDRs took their Vendor the last time they were mapped.
- **Cell Configuration KMZ/KML packages:** one `.kmz` or `.kml` file, or a `.zip` with several (also in folders or nested `.zip` files), whose Placemarks describe one cell each with `Key: Value` lines (Network, Host Network, Vendor or OP/ Vendor, Site ID, eNodeB/gNodeB ID, Cell ID, ECI/NCI, Band, PCI, EARFCN/ARFCN, coordinates, azimuth, tilts, status…).
  - Every cell becomes a row with its `Technology` (LTE or NR), `Source_File` and `Folder`; keys spelt differently in LTE and NR files (`Cell_name` and `Cell Name`, `Site_ID` and `Site ID`) share one column.
  - Placemarks without a cell identity, such as site-vendor points, are skipped, and sector shapes are not stored: Network Insights draws the sectors from each cell's position and azimuth.
- **Snapshot date:** each inventory is a **snapshot** of the network on that date: the date in its file name (`260917_…` → 2026-09-17, `YYYYMMDD` or `YYYY-MM-DD`), else its upload date until one is chosen.
  - On upload, its **Snapshot date** field is already filled from the file name (*From the file name* below it) and can be changed or cleared before processing.
  - Afterwards it is changed in its row of the card; clearing it returns to the date of the file name or the upload. The upload and every change are recorded in App Events.
- **Inventory Cells:** when processed, its cells are normalised once into the **Inventory Cells** table (with the **Inventory Snapshots** summary, both in Database Management): technology, owner `Network`, the `Host Network` whose equipment carries them (hence their vendor), site, cell identity, band, channel, PCI, position (the British National Grid position when the coordinates are rounded to 3 decimals), azimuth, configuration and status. Network Insights and the Vendor mapping read this table, so changing snapshot is immediate. Owner and host network are kept apart because an Operator's samples can be served by the cells of another network (shared Beacon sites or eMOCN).
- **Vendor:** with a Vendor column (`Vendor`, `OP/ Vendor`, `OP_Vendor`, `OEM`, `Manufacturer` or `Supplier`) and a cell identifier, it also maps the Vendor of its Operator's CDR samples (see [Vendor Mapping](#vendor-mapping)). The identifier is a global one (`GCID`, `Global Cell ID`, `ECI`, `NCI`, `ECGI`, `NCGI`, `CGI`, `Cell Identity` or `Cell ID`) or an `eNodeB ID`/`gNodeB ID` with its `Cell ID`: `eNodeB × 256 + Cell ID`, `gNodeB × 16384 + Cell ID` for 22-bit gNodeB IDs or the length of a `gNodeB ID Length` column; the `Local Cell ID` only for rows without a `Cell ID`. Each row takes the identity of its eNodeB, else of its gNodeB, else its global identifier, so one inventory can hold LTE and NR cells.

### Vendor polygons

Choose **Vendors — Geospatial** for polygons that give the Vendor of an area, so CDRs of any Operator can be mapped to Vendors without a Network Inventory. They use the formats of [Cluster polygons](#cluster-polygons), need a non-blank `Vendor`, `OP_Vendor`, `OP/ Vendor` or `Name` attribute, and are proposed for geospatial filenames containing `vendor`.

- **Operator of each polygon:** the **Operator** chosen on upload, proposed from the file name (`O2_Vendor_Polygons.geojson` → O2), one file per Operator; or, with **Multi-operator**, the `Operator` (or `MNO`, `Network`) attribute of each polygon, so one file holds every Operator.
- **Geographic Datasets card:** shows the **Type** of every shape (Regions, Clusters or Vendors) and, for Vendors, their Operator in a pill that changes it when it was assigned wrongly; map the CDRs again to apply the change.
- Preview draws them on a map named `<Operator> · <Vendor>`; how a CDR takes its Vendor from them is in [Vendor Mapping](#vendor-mapping).

### NR Mode

Every CDR (Data, Voice or Speech) belongs to one NR Mode, **NSA** or **SA**; other dataset types have none. It is proposed from the filename and can be changed per file before processing:

- `SA`, `5G SA`, `5GSA` or `Standalone` in the name (`UK_Q2_2026_SA_Data.xlsx`) → SA.
- `NSA`, `Non-Standalone` or no NR indication (`NetCheck_CDR_Data_2026_Q2.xlsx`) → NSA.

In the CDR tables of Datasets, **NR Mode** follows the Campaign, before **CDR Type** (Data in orange, Voice in raspberry, Speech in violet) and **CDR Stage**.

- **NR Mode selector:** corrects the NR Mode of an existing CDR without reprocessing it, recorded in App Logs. CDRs created before this column existed received the filename proposal automatically. PPT Designer only uses CDRs of its own NR Mode.
- **CDR Type selector:** changes a processed CDR between Data, Voice and Speech after a confirmation: its rows leave the combined table of its former type at once and it is reprocessed from its source file (which it needs) as the new type, recorded in App Events.

### Campaign

Every CDR shows its **Campaign** right after its name in the CDR tables, as `YYYY-Qn` (`2026-Q2`), followed by a name when the campaign has one (`2025-Q2-Flex`); whether it is NSA or SA is its NR Mode.

- **Proposed from the filename:** the quarter is its `Q1`–`Q4`; the year is a year of the name (`NetCheck_UK_CDR_Data_2026_Q2_SA.xlsx` → `2026-Q2`) or, without one, that of its dates: the first date in the quarter, else the first measurement date (`20260623 Final Data CDR UK Q2 20260512 - 20260613.xlsx` → `2026-Q2`).
- **Else from the rows:** a filename without a quarter or year takes the campaign of the rows as [Campaign Maps](workspace-config.md#campaign-maps) reads it, including the name an exception adds (rows of `UK_Flex_2026` with the exception `25-Q2-Flex` propose `2025-Q2-Flex`). Rows without a year and quarter, or of several campaigns, leave it blank.
- **Editing:** write any campaign, also one no CDR has yet, or clear it; the field suggests the campaigns of the other CDRs. Any spelling with a year and quarter is saved as `YYYY-Qn` (`2026 q3` → `2026-Q3`), and a name after them is kept as a campaign of its own (`2025-Q2 Flex` → `2025-Q2-Flex`). The change is saved without reprocessing, recorded in App Events, and travels with the datasets in packages, transfers and backups.
- **Colours:** each campaign has its own colour, taken in turn, so consecutive campaigns never share one.

The Final, Weekly and Daily CDR cards show beside their icon their number of campaigns, CDRs and size. Their tables are grouped by campaign (newest first, CDRs without a campaign last under **No campaign**), each group with its number of CDRs and the MB of their source files; a CDR whose campaign changes moves to its group at once.

- **Weeks and days:** within each campaign, Weekly CDRs are grouped by the ISO week of their last call (`2026-W37`, with its Monday to Sunday dates) and Daily CDRs by the day of their last call (`2026-09-09`, with its weekday), newest first; a CDR without calls read yet goes under **No week** or **No day**.
- **Folding:** each group folds from its header; every table (Flex CDRs included) opens with only its latest campaign unfolded and, within it, its latest week or day, and a group you fold or unfold stays so while the browser tab is open.
- **Sorting:** by Campaign, then NR Mode, then CDR Type; any column header sorts the CDRs within each group instead.

#### Flex campaigns

A **Flex campaign** is a local campaign: complete, but localised in one geographic area (a region, cluster or city). Its Campaign values, or their label in [Campaign Maps](workspace-config.md#campaign-maps), have the word Flex (`UK_Flex_2026`, `26-Q2-Flex`, `2025-Q2-Flex`); a CDR whose rows have no Campaign yet is Flex when its Campaign here is. As it covers only that area, it is used only where it is checked by hand:

- **Latest campaign**, **Latest 2, 3 and 4 campaigns**, **Previous campaign** and **All available campaigns** never count it, in Scoring & GAP Analysis, PPT Designer, CDR Analysis, Network Insights, Non-Qualified Calls and the reports of [Reporting](reporting.md) (a workspace with only Flex campaigns gets no campaign from them).
- A Campaign filter without campaigns (every campaign, such as **All complete campaigns** of Scoring) leaves its CDRs out. The list of [Non-Qualified Calls](non-qualified-calls.md) still shows its calls when no campaign is filtered, as they must be analysed too.
- The [NQ Prioritization](non-qualified-calls.md#nq-prioritization) never takes it as the campaign whose Final CDR gives the Expected Gain of the calls of other campaigns.
- Checking it in a Campaign filter uses it like any other campaign.

The Final, Weekly and Daily CDR cards list their Flex CDRs apart, in a **Flex CDRs** card inside them, dashed in amber, with its count, badges and a notice of how they are used; it shows only when the stage has such CDRs, and a CDR moves in or out of it at once.

**Suggested Flex CDRs.** Ad-hoc campaigns do not always say Flex, so a CDR that is not Flex yet is suggested when:

- its file name has the name of an area of the workspace (any `City`, `Cluster` or `Region` value of its CDRs, such as `London`), unless it is a Final CDR whose tests cover 60% or more of the area of the other Final CDRs; or
- it is a Final CDR whose tests cover 35% or less of the area of the other non-Flex Final CDRs of its type and NR Mode, measured in cells of a quarter of a degree (one city, several cities of one zone or a whole region).

Weekly and Daily CDRs do not cover their whole area yet, so only an area in their file name suggests them (`20261112 Daily Data NSA CDR UK London 20261024-20261111.xlsx`). The coverage of each Final CDR is read once it is processed (earlier ones while the tool is idle) and again only when it changes; suggestions show once every Final CDR has been read.

The Campaign cell of a suggested CDR says why, in amber (*Looks local (London): its tests cover 3% of the area of the other Final CDRs*), and names the other CDRs with the same Campaign values, which would be Flex too. Its answers (user-editors, admins and super-admins), recorded in App Events:

- **Mark as Flex** (after a confirmation) labels its Campaign values in Campaign Maps with a Flex label of their year and quarter, their NR Mode when the Campaign Maps format shows it, and the area (`26-Q4-London-Flex`, `26-Q4-SA-London-Flex`, or `…-Local-Flex` without a main area); values that already have an exception take the Flex label in it.
  - The year and quarter come from the Campaign values, else the Campaign of the CDR, else the dates of its file name (`UK_London_SA_2026` in a file of `20261024-20261111` is `26-Q4-SA-London-Flex`).
  - A CDR whose rows have no Campaign values takes the Flex campaign as its Campaign (`2026-Q4-London-Flex`). The CDR moves to the **Flex CDRs** card and the combined tables follow.
- **Not local** hides the suggestion until the CDR changes.

Every other non-Flex CDR has a **Mark as Flex** button under its Campaign, which does the same with or without a campaign, whatever its stage. On upload, the **Flex campaign** choice of each CDR (*Flex (local)* or *Not Flex*) is preselected from its file name (an area of the workspace or the word Flex, as its note says), can be changed whatever the tool suggests, and is applied once the CDR is processed; *Not Flex* against a suggestion hides it for good. Both are recorded in App Events.

A campaign can still be made Flex by hand, with Flex in its Campaign values or its Campaign Maps label; editing the label takes it out of Flex again. As Flex is a property of the Campaign values, a local CDR whose rows carry the same Campaign value as the CDRs of the whole country cannot be told apart from them: its tests count in that campaign.

#### Campaigns in progress

A campaign whose CDRs are all Weekly or Daily, without a Final CDR yet (a quarter that has just started, such as `26-Q4` with its first Daily CDRs), is **in progress**. So that its few days of tests do not replace the latest complete campaign:

- **Latest campaign**, **Latest 2, 3 and 4 campaigns**, **Previous campaign** and **All available campaigns** never count it, in every module and in the reports of [Reporting](reporting.md), until its first Final CDR arrives (a campaign that never gets one is used only when checked by hand).
- The Campaign lists of [Scoring & GAP Analysis](scoring-gap-analysis.md) tag it **In progress**, and checking it in any Campaign filter uses it like any other campaign (to follow its calls in [Non-Qualified Calls](non-qualified-calls.md), for example).

### CDR Stage: Final, Weekly and Daily

A **Final** CDR is delivered after its measurement campaign; a **Weekly** or **Daily** CDR arrives every week or day while it runs, either incremental (the calls of one week or day) or cumulative (every call so far). The stage is proposed from the filename and can be changed per file before processing:

- `Final` in the name → Final, even with a date.
- `Weekly`, `Week`, `Semanal`, `Semana` or `Wk` → Weekly.
- `Daily`, `Diario`, `Day`, `Incremental` or `Cumulative` → Daily.
- A date range (two different dates, such as `20250903-20251011`) → Final.
- A single date that is not the export date at the start of the name (`UK_Voice_CDR_20260921.xlsx`) → Daily; `20260921_UK_Voice.xlsx` → Final. In an Umlaut workspace the export stamp that ends the name (`…_2025-07-30_16-05-07`) is not a measurement date either.
- Anything else → Final. CDRs uploaded before Daily CDRs existed are Final.

The **CDR Stage** selector (Final in teal, Weekly in violet, Daily in orange) changes it without reprocessing, moves the CDR to the table of its stage and is recorded in App Logs. The CDRs used lists of Scoring & GAP Analysis, Network Insights and PPT Designer, like the upload, outline Weekly (violet) and Daily (orange) CDRs dashed.

**Active?** holds the choice **Auto** (default), **Yes** or **No** and, below it, whether the combined CDR tables include the CDR (**Yes** or **No**) and why. Only admins and super-admins change it, because it recalculates the combined tables and indexes the calls again; for the other roles it is locked, with the reason as its tooltip. Each CDR shows the first reason that applies:

| Reason | When it applies | Included |
|---|---|---|
| *Included manually* / *Excluded manually* | The choice is **Yes** or **No**. It overrides every other rule, for every stage. | As chosen |
| *Final CDRs are always included* | A Final CDR set to **Auto**. A Final CDR only leaves the combined tables when set to **No**. | Yes |
| *Replaced by the Final CDR …* | A Weekly or Daily CDR set to **Auto** covered by an included Final CDR (not set to **No**) of the same type, of the same NR Mode (or either has none), Flex or not like it, sharing at least one `Campaign` value with it. The reason names that Final CDR. | No |
| *Its dates (… to …) are covered by the Final CDR …* | A Weekly or Daily CDR set to **Auto** whose first and last call dates are within those of such a Final CDR, whatever its `Campaign` values (a Weekly CDR from 1 to 20 October and a Final CDR from 1 to 30 October). | No |
| *Every call is in the newer Weekly CDR …* / *… Daily CDR …*, or *Every call but 11 is in the newer …* | A Weekly or Daily CDR set to **Auto** with no Final CDR yet, whose calls (`JOIN_ID`) the newest Weekly or Daily CDR of the same type, NR Mode and campaign (by the date of its data), or a newer Weekly CDR, contains. A newer cumulative CDR may leave out a few calls the provider invalidated: it still contains the older CDR when at most 5 % of its calls are missing, and the reason says how many. So a cumulative CDR replaces the previous ones and a Weekly CDR the Daily CDRs of its week, also when newer Daily CDRs follow it; incremental CDRs are all included. | No |
| *Its dates (…) are covered by the Weekly CDR …* | A Daily CDR set to **Auto** whose dates are within those of a Weekly CDR (not set to **No**) of the same type, NR Mode and Flex or not. | No |
| *No Final CDR of its campaign yet* | Any other Weekly or Daily CDR set to **Auto**: the best data available while the campaign runs. | Yes |

- **Flex apart:** a Flex CDR never replaces a non-Flex CDR, nor the other way round, whatever their dates.
- **Partial overlap:** a Weekly or Daily CDR that stays included while some of its days are in an included Final CDR adds them to its reason (*…; 6 days of its dates are also in the Final CDR …*): those calls are counted twice unless one of the two is set to **No**.
- **Left out is not deleted:** the CDR stays in the Workspace and in CDR Analysis. Setting a Final CDR to **No** stops it covering its Weekly and Daily CDRs, which take the next reason that applies.

For example, the Voice SA CDRs of UK Q3, with cumulative Daily CDRs, before and after the Final CDR arrives:

| CDR | CDR Stage | Active? | Before the Final CDR | After it arrives |
|---|---|---|---|---|
| `UK_Voice_Q3_Final.xlsx` | Final | Auto | — | Yes: *Final CDRs are always included* |
| `UK_Voice_20260921.xlsx` | Daily | Auto | No: *Every call is in the newer Daily CDR UK_Voice_20260922.xlsx* | No: *Replaced by the Final CDR UK_Voice_Q3_Final.xlsx* |
| `UK_Voice_20260922.xlsx` | Daily | Auto | Yes: *No Final CDR of its campaign yet* | No: *Replaced by the Final CDR UK_Voice_Q3_Final.xlsx* |
| `UK_Voice_20260923.xlsx` | Daily | Yes | — | Yes: *Included manually* |

The rows the combined tables include have a light green background, the others a light grey one. The answer and colour change at once, and the combined tables follow every change (a new CDR, a CDR Stage, NR Mode or Active? choice, or a deleted CDR; deleting a Final CDR brings back the Daily CDRs it replaced) in a background job listed in [CDR Tables Updates](#cdr-tables-updates). So the modules use the Daily CDRs while the campaign runs and the Final CDRs when they arrive:

- Scoring & GAP Analysis, PPT Designer, Network Insights and their sections in the reports of [Reporting](reporting.md) have no CDR selector: they use the CDRs the combined tables include for their NR Mode and Campaign filter.
- CDR Analysis opens any CDR, and [Non-Qualified Calls](non-qualified-calls.md#daily-and-final-cdrs) reads every CDR and lists each call once, with the version the combined tables include.

### Background Processing

Ready CDRs queue default Operator scoring when compatible companion CDRs are available; open [Scoring & GAP Analysis](scoring-gap-analysis.md) to choose the NR Mode and Campaign, filter, aggregate, consult saved results and export.

- A queued import keeps its target workspace even if the user switches workspace, and processing continues after sign-out.
- Stop requests are cooperative; failed or stopped work can be retried.
- Re-uploading the same stored dataset keeps its original upload date; Updated records the latest processing operation.
- **Task cards:** the global floating task cards stay visible while work continues: the open workspace at the lower right, other accessible workspaces at the lower left. **Interrupt task** (■), or **Stop all** for every interruptible task of a workspace, asks for confirmation: a stopped duplication removes the incomplete copy, and a stopped import is rejected once file import has started.

## NetCheck CDR Support

### Source File and Worksheet Processing

- Every dataset keeps one CDR type (Data, Voice or Speech); rows of different CDR types are never combined in one CDR table.
- The contiguous block of operator worksheets is read and stacked by rows; identically named fields of different sheets align in one column.
- Known summary, ranking, definition, list and helper worksheets are ignored. `Source_File`, `Source_Sheet` and `Dataset_Kind` record the origin of every row.
- Source headers are preserved; field resolution ignores letter case and spaces, underscores and hyphens, and `Subscriber` and legacy `Suscriber` are the same field.
- A header repeated within one worksheet becomes `_Duplicate_2`, `_Duplicate_3`…; an empty header becomes `Unnamed_N`. Technical SQLite collision suffixes such as `__2` are not kept.

### Datasets cards

The **Datasets** panel header, before Collapse, counts the campaigns (of the Final, Weekly and Daily CDRs together), CDRs, Multivendor Mappings, Network Inventories and Geographic Datasets, and the size of every source file (in MB, or GB from 1 GB). The datasets are grouped in cards, each with its icon, count and sortable table; times of dates are shown in blue. The **Dataset Type** filter and the bulk actions above them apply to every card, and a filter hides the cards without datasets of that type.

- **Final CDRs**, **Weekly CDRs** and **Daily CDRs** (the last two fold and show only when they have CDRs), full width, grouped by campaign (see [Campaign](#campaign)), with the Campaign, NR Mode, CDR Type, CDR Stage and Active? columns; Rows sit above Columns and Uploaded above Updated, each with its own sort button.
- **Multivendor Mappings** (with **Operators** and **Snapshot**), **Network Inventories** (with **Operator** and **Snapshot**; the VFUK and 3UK files too) and **Geographic Datasets** (Region, Cluster and Vendor polygons, with their **Type**), in one row on a wide window, with compact rows: the dataset with its type and rows, its status with progress and last update, and its actions. These reference datasets have no analysis or mappings, so their actions are **Preview**, **Reprocess** and **Delete**.
- **Layer3 Logs**, full width: one dataset per campaign and NR Mode, with its Campaign (and that of its rows), NR Mode, Operators, Sessions (over its JoinIDs and the NQ calls of the workspace with a session in it), Rows, Size, status, last update and actions, sized to fit a laptop window; the header counts their campaigns and sessions and gives their size.
- **CA Appendix**, beside the reference cards: each with its tests, fields and operators; its note says how many tests of how many CDRs have its fields now.
- **Master Grid**, beside it: the sites, Keep sites and week of the newest one.
- **Other Datasets**, when there are any.
- **Combined CDR tables** (see [Combined CDR Tables](#combined-cdr-tables)), with Rows over Columns, status (**Ready**, **Updating**, **Recalculating**, **Queued**, **Missing Rows** or **Recalc Needed**), progress and last update; they mix NR Modes and come from no file, so they have no NR Mode, Size or Uploaded columns.

#### Selecting several datasets

Users who can edit the workspace select datasets with the box beside the ID of each row (before the name in the reference cards), the box in the ID header of a table (every dataset of it the Dataset Type filter shows) or the box of a campaign, week or day group (every CDR of it, folded or not). A floating bar counts them and offers the actions they share, each applied only to the selected datasets it is available for (as the buttons of their rows; its tooltip says how many):

- **Map Vendor, Region & Cluster**, **Clear Mapping** and **Reprocess** open their usual dialog with the selected datasets checked.
- **Active?** **Auto**, **Yes** or **No** (admins and super-admins) changes the selected CDRs at once, with a single update of the combined tables.
- **Stop** stops those queued or processing; **Delete** removes them and their source files after a confirmation that lists them.
- **×** clears the selection.

Every change is recorded in App Events for each dataset, as the action of its row, marked as made on a selection.

### Combined CDR Tables

`CDR-Data (combined)`, `CDR-Voice (combined)` and `CDR-Speech (combined)` are the generated read-only query sources of each CDR type, made by CDR processing from the ready individual CDRs they include (see [CDR Stage](#cdr-stage-final-weekly-and-daily)); they cannot be imported separately. They are filtered by the type selector and previewed with the normal CDR preview.

The circular **Recreate combined table** action runs in the background (see [CDR Tables Updates](#cdr-tables-updates)): it checks every ready individual CDR the table includes, recovers an empty or inconsistent individual row store from its uploaded source file when available, and verifies each dataset's contribution and the final row count. An individual table of an older normalization version is first migrated from its original source file, so one recreation each for Data, Voice and Speech upgrades both individual and combined tables. The task detail names the table being migrated; opening a combined preview runs the same check, and its Loading Dataset panel explains when the individual tables may need migration.

### CDR Tables Updates

The **CDR Tables Updates** card, below the Datasets cards, lists the background jobs that rewrite the CDR tables, each with its label, message and progress bar:

- **Auto-calculated Fields:** saving, importing or rematerializing [Auto-calculated Fields](workspace-config.md#auto-calculated-fields); their cards in Workspace Config show the progress on the CDR types of each field and link to this card.
- **Combined CDR-DATA**, **-VOICE** or **-SPEECH:** recreating a combined table after a CDR is processed or mapped, or with **Recreate combined table**.
- **Combined CDR tables:** following a CDR Stage, NR Mode or Active? change or a deleted CDR.
- **CDR tables reconciliation:** the automatic check when a workspace opens with pending work or a report template needs new columns.

Its pills sum up the state (**Up to date**, **N in progress**, **N queued**); with nothing to do it reads *All CDR tables are up to date*. Whenever a job starts, changes state or ends, the Datasets cards, combined tables included, refresh their counts, status, progress and Updated values in place.

### Fixed CDR Fields

Every fixed field is materialised even when all its values are empty, and Dataset Preview shows them after `Source_File`, `Source_Sheet` and `Dataset_Kind` in this order. "When empty" means when its complete column is absent or empty.

| Field | Stored value / fallback rule |
| --- | --- |
| `Operator` | The source `Operator`, `Operator_A`, `Home_Operator_A` or `Home_Operator` value. Every filter, table, chart and report shows it with its Operator Maps label, and a mapped selection matches every source spelling; only Dataset Preview and the stored CDR tables keep the source value. |
| `Subscriber` | The source `Subscriber` or legacy `Suscriber` value; when empty, a copy of `Operator`. |
| `Operator_Vendor` | The `<Operator>_<Vendor>` identity from the source CDR or the vendor mapping (`<Operator> - All` for operators without a vendor). |
| `Vendor` | The vendor alone: `Operator_Vendor` without a recognised operator prefix, including the configured Vodafone/VF, Three/3/H3G, O2 and EE aliases (`<Operator> - All` for operators without a vendor). |
| `Campaign` | The exact source value. Comparisons and chart labels recognise reordered country, year, quarter and SA/NSA tokens and can present `YYYY-Qn`, `YYYY-Qn_SA` or `YYYY-Qn_NSA`; a mode-free equality filter does not merge SA and NSA records. |
| `Benchmark` | The source value; when empty, a copy of `Campaign`. |
| `Campaign_Year`, `Campaign_Quarter` | The first four-digit year, and `Q1`–`Q4`, of `Campaign`, with `Benchmark` as the per-row fallback. |
| `Period` | `Campaign_Year` and `Campaign_Quarter` as `YYYY-Qn`. |
| `Market` | The two-letter code of a delimited ISO country code or English country name in `Campaign`, then in `Benchmark`. |
| `Region` | The source value, empty when absent. |
| `Zone`, `City` | The source value, else `G_Level_3` (Zone) or `G_Level_4` (City), else empty. |
| `Technology`, `RAT`, `RAT_A`, `L2_Call_Mode_A`, `Playing_Technology` | Each keeps its source values; when empty, the first populated of `Technology`, `RAT`, `RAT_A`, `L2_Call_Mode_A` and `Playing_Technology`, in that order. |
| `Session_Type`, `Type_Of_Test` | Each keeps its source values; when empty, the first populated of `Session_Type` and `Type_Of_Test`. |
| `Test_Name` | The source value unchanged. |
| `Test_Result`, `Call_Status`, `Status`, `Result` | Each keeps its source values; when empty, the first populated of `Call_Status`, `Status`, `Result` and `Test_Result`. Never converted into a boolean. |
| `Event_Start_Time`, `Event_End_Time` | The first available call, test or data start (end) field, valid timestamps stored as `YYYY-MM-DD HH:MM:SS.ffffff`. |
| `Hour_Bucket`, `Day_Bucket` | The hour, and the day of the month, of `Event_Start_Time`. |

### Derived Analysis Fields

These ingestion fields give common names across CDR formats and are available to filters, chart definitions and Auto-calculated Fields:

| Field | Materialisation rule |
| --- | --- |
| `Direction` | First available `Direction_A`, `Direction` or `Call_Direction`. |
| `Disturbed`, `Impaired` | True when `Disturbed_Call` (`Impaired_Call`) is `Yes`. |
| `Dropped` | True when status contains `drop` or `Dropped_in_first_70s` is `Yes`. |
| `Unsustainable_Call` | True when `Unsustainable_Call` is `Yes`; otherwise false. |
| `Success` | True for normalized status `completed`, `success`, `ok` or `passed`. |
| `Failure` | True when status is present and `Success` is false. |
| `Setup_Time_Seconds` | First available `Call_Setup_Time`, `Transfer_Access_Duration`, `http_Browser_Access_Duration` or `VideoStream_Time_To_Start_Buffering`, as a number. |
| `Duration_Seconds` | First available `Call_Duration`, `Test_Duration`, `Data_Test_Duration`, `Transfer_Duration` or `VideoStream_Video_Stream_Duration`, as a number. |
| `Quality_Score` | First available numeric `POLQA_LQ_Avg`, `LQ` or `Mean_Data_Rate`. |
| `Throughput_Mbps` | First available numeric `Mean_Data_Rate`, `TCP_Throughput` or `Data_Throughput`. |
| `Latency_Ms` | First available numeric `Receive_Delay`, `TCP_RTT_Service_Access_Delay` or `DNS_Service_Access_Delay`. |
| `Packet_Loss_Pct` | Row mean of the available `RTP_Packet_Loss_A`, `RTP_Packet_Loss_B` and `Packet_Loss_Score`. |
| `Jitter_Ms` | Row mean of the available `RTP_Jitter_Avg_A` and `RTP_Jitter_Avg_B`. |
| `Handovers` | Item count of the first available `Handovers_Info`, `Handovers_Info_A` or `Playing_Handovers`. |
| `Technology_Primary` | First available `RAT`, `RAT_A`, `L2_Call_Mode_A` or `Playing_Technology`. |
| `Technology_Secondary` | First available `L2_Call_Mode_B`, `RAT_B`, `Recording_Technology` or `RAT_Timeline`. |
| `Attempt_Count` | Integer `1` per row, to count categorical attempts when no numeric KPI exists. |

- **Consumers:** analytics uses the flags and the normalized metrics directly, and template charts use them as fallbacks for heterogeneous CDR layouts; `Technology_Primary` drives filters and grouping, `Vendor` multivendor comparisons, and `Attempt_Count` a stable row count.
- `Technology_Secondary` and `Unsustainable_Call` have fewer built-in consumers but stay addressable by templates, filters and Auto-calculated Fields: do not remove them without checking workspace definitions and migrating the model.
- **Normalization version 13** rematerialises version-11 and version-12 CDRs once from their uploaded source, restoring `Operator` values a canonical mapping had replaced (also in datasets a Vendor-only update had wrongly marked as version 12). It keeps the version-11 cleanup of obsolete `__N` collision columns and of the former `Report_Vendor` duplicate, without deleting the uploaded source; genuine duplicate headers keep their `_Duplicate_N` names. Vendor mapping changes no longer advance the normalization version.

### Columnar Copy of the CDRs

Every ready Data, Voice and Speech CDR is kept in its columnar copy: a folder of Parquet files per CDR (one per batch of 50,000 rows) in the `.cdr-store` folder beside the workspace database, read with DuckDB. It holds every column, the SQLite row id (`__rowid`), the dataset id and the NR Mode of the CDR; a column keeps numbers when every value is a number, and text (as SQLite writes it) otherwise.

The copies are the only store of the CDR rows:

- **Emptied tables:** once its copy holds the CDR, its table in the workspace database is emptied but keeps its columns and indexes (listed in **CDR Store Shadows**). Every SQL of the application that reads it, Query Builder and Database Management included, gets its rows from the copy, with the same row ids and order, so every module gives the same results. The combined tables are emptied the same way once the copies hold all their CDRs (at server start, or when nobody uses the application and no combined-table update runs); **CDR Store Combined Rows** keeps the CDR row of each of their rows.
- **Changes in the copy:** a change of the rows of a CDR is made in its copy, never by putting the rows back in its table. An Auto-calculated Field, the Map Areas of its tests, its NR Mode, its new name (`source_file`) and its Vendor worked out from `Operator_Vendor` read only the columns they need and rewrite only their own (seconds per CDR: 10 to 15 for a Data CDR of 450,000 rows). Mapping a CDR (Vendor, Region, Cluster) types and rewrites only the changed columns (about a minute for a Data CDR of 450,000 rows, four before). Processing it again with other rows writes them to its table, copied again in the background.
- **Read-only:** Database Management shows the rows of a CDR in its copy, and of an emptied combined table, read-only: CDRs stay as they were imported.
- **When it is copied:** in the background, one CDR at a time, after the other background work: when a CDR finishes processing, when the workspace opens and once nobody has used the application for two minutes (self-refreshing pages do not count). The first opening of a workspace copies all its CDRs: about three minutes for a Data CDR of 350,000 rows, under a minute for a Speech or Voice CDR.
- **When it is copied again:** when the CDR is processed again with other rows, or its rows change while its table still holds them (before its first copy): triggers count every insert, update and delete in **CDR Store Versions**, which also counts the changes made in the copy. The copy of a deleted CDR is removed.
- **Disk space:** a copy waits while the disk would keep less than 1 GB free after it, as the file system reports free space (on macOS, space a local Time Machine snapshot still holds does not count); it writes batch after batch and never needs more room than the copy itself. The background task then says *Waiting for free disk space to copy <CDR>* and App Events records `cdr_store_waiting_for_space` once.
- **Server start:** it empties the tables of the active workspace that the copies hold (the first start of this version, those of every CDR already copied), then compacts its database (SQLite `VACUUM`) when a quarter of it, and at least 1 GB, is room left by emptied tables; the startup page shows both steps, and a large workspace takes a few minutes. Compacting needs free space for twice the data that stays in the database, else it waits for a later start. A workspace opened later empties its tables in the background and is compacted at the next start.
- **Background task and App Events:** **CDR columnar copy** shows the CDR being copied and how many are left; `cdr_store_synced` records copies made and removed, `cdr_store_tables_emptied` and `cdr_store_combined_emptied` the emptied tables, and `workspace_database_compacted` the database size before and after (or the room it needed).
- **Who reads it:** [Network Insights](network-insights.md) (samples), [Scoring & GAP Analysis](scoring-gap-analysis.md) and its Points Lost Map (rows), [Non-Qualified Calls](non-qualified-calls.md) (call indexing, the rows of the NQ Prioritization and the tests around a call on its Map) and [PPT Designer](ppt-designer.md) (chart columns and preparation counts), with the same rows in the same order as the CDR tables gave. A filtered read lets SQLite apply its filters to the few columns it reads, with the same index, and reads the other columns of the selected rows from the copy. A CDR not copied yet (just processed, or changed) is read from its table.
- **Catalog for other tools:** `.cdr-store/catalog.duckdb` holds the views `cdr_data`, `cdr_voice` and `cdr_speech` over the CDRs the combined tables include (**Active?**), with every column plus `dataset_id`, `source_row_id` and `NR_Mode`. Tableau opens it on the machine of the workspace with the DuckDB JDBC driver and the *DuckDB by MotherDuck* connector. `.cdr-store/postgres-views.json` holds the same views for PostgreSQL with pg_duckdb (their SELECT over the files, with `{root}` for the folder of the copies), which a PostgreSQL server beside the deployment can keep as materialized views, made again whenever the file changes, for Tableau to read as plain tables.
- **Backups and transfers:** backups with the workspace database, complete workspace and Full Environment packages, transfers and workspace duplicates take the copies as they were at the database snapshot (those of emptied tables and those matching the database; the others are copied again where they arrive). Restoring or importing a workspace database replaces the workspace's copies; backups and packages of earlier versions, which carry the rows in the CDR tables, have their copies made again.

### Vendor Mapping

> [!WARNING]
> **Remapping.** Map a CDR again to apply a newer inventory, other Serving Networks or a newer mapping rule; it replaces the previous result without a prior Clear. The Map dialog marks the CDRs whose Vendor was mapped under other conditions as **Vendor mapping outdated** and selects them when it opens. Vendor Comparison requires persisted mapping on every selected CDR.

Vendor mapping is required only for Vendor Comparison. The Vendor comes from one of two sources; the Map dialog asks for it when the workspace has both, and its Vendor mapping rule follows the chosen source:

- **Cell inventories:** the [Multivendor Mappings](#multivendor-mappings) and [Network Inventories](#network-inventories) (Cell Configuration KMZ packages included), by the cells that served each sample. With a Multivendor Mapping, the mappings give the Vendor, each for its Operators, and where several have a cell, the one whose Snapshot date is closest to the CDR. The other sources (VFUK, 3UK and the Network Inventories), whatever their date, only complete the cells the mappings do not have: a Vendor a mapping gives is never kept from an older file. Without any mapping, the Network Inventories map the Vendors.
- **Vendor Polygons (Geographic Datasets):** the [Vendor polygons](#vendor-polygons) of each sample's Operator, by its position; every Operator that has polygons.

The Vendor polygons are proposed when they cover every Operator of the cell inventories (polygons of that Operator, or multi-operator polygons whose Operator attribute includes it), the Cell inventories otherwise; with a single source, that one is used.

#### Supported Mapping Files

- **VFUK** workbooks: a `4G` worksheet with `eNodeB ID`, `Cell ID` and `OP/ Vendor`, and a `5G` worksheet with `gNodeB ID`, `Cell ID` and the vendor field, mapped by the ECI and NCI the CDRs report (see [Network Inventories](#network-inventories)).
- **3UK** files: `Cid__ECI` (or `CId___ECI`) and `Vendor`; the ECI becomes the mapping `GCID` directly.
- Headers are resolved without regard to case, spaces, underscores and hyphens. Rows without a valid cell identifier or vendor create no mapping entry.

#### Assignment Rule

The lookup is detailed in [Technical Considerations](technical-considerations.md#multivendor-calculation-and-remapping): the formulas of each file, the serving-cell fields of the CDR (`Cell_ID_A`, `Cell_IDs_A`, `Cell_ID`, `Global CI`, `GCID`…, beside `Operator`) and how cells are resolved. In short:

- **Which cells:** every cell of the sample (its first cell, those it changed to and its last, placed along the way from its start to its end) is looked up among the cells of the networks that can serve its Operator, its own first, as set in the [Serving Networks](workspace-config.md#serving-networks). Every selected mapping and inventory is a [snapshot](#network-inventories) whose cells belong to their owner network and have the vendor of their `Host Network`; the spellings of an Operator (Vodafone UK, VF, Vodafone SA, Vodafone SM, VF_SA…) share its network.
- **Which technology:** by the NR Mode of the CDR. An **NSA** CDR is served by its LTE anchor (EN-DC), so its cells are looked up only among the LTE cells (the `4G` sheet of a Multivendor Mapping, and 3G/2G cells), never among the NR cells, whose NCIs can be the same numbers as LTE ECIs. An **SA** CDR looks up its cells among the NR cells (`5G` sheet) first, and among the LTE cells only for a cell no NR row has (a fallback to LTE). Changing the NR Mode of a mapped CDR marks its Vendor mapping outdated.
- **Which snapshot:** the one whose Snapshot date is closest to when the CDR was measured (the median start time of its samples, else the date in its file name), the newest on a tie, so a CDR measured before a vendor swap keeps the vendor it measured.
- **Distance:** a cell farther from the sample than the maximum serving distance (30 km by default) is ignored, as cell identities repeat across Operators.
- **Result** (every Operator, with its own name as prefix: `Vodafone_`, `3_`, `Vodafone VoNR_`, `O2 (UK)_`…):
  - the same non-empty Vendor at all its cells → `<Operator>_<Vendor>`;
  - Ericsson at one cell and a different or missing Vendor (a cell not in the snapshots) at another → `<Operator>_Ericsson (Mixed)`;
  - any other different or missing combination → `<Operator>_Mixed (non-Ericsson)`;
  - no cell in the snapshots → `<Operator>_Unknown` (Vendor `Unknown`), so an Operator whose inventories cover only part of its network (O2, whose Vodafone-hosted cells are in the Vodafone inventories) is not shown as Mixed;
  - Operators no selected snapshot serves (EE without a Network Inventory), and, beside a Multivendor Mapping, the Operators left out of every selected mapping → `<Operator> - All` (they still get their serving cell).
- **Serving cell columns:** the cell that served the start of each sample (its end when the start has none) fills `Serving_Network` (owner), `Serving_Host_Network`, `Serving_Site_ID`, `Serving_eMOCN_Scenario`, `Serving_Distance_km` (from the sample's position) and `Serving_Inventory_Snapshot` (its Snapshot date), empty when no cell matched. From all its cells, like the Vendor (the same class at all, else `MIX`; empty when none matched):
  - `Serving_RAN_Vendor`: the RAN Vendor with the network that hosts it (`VF_Hosted_Ericsson`, `VMO2_Hosted_Nokia`, `3UK_Hosted_Huawei`), only for the Operators that receive a Vendor;
  - `Serving_Site_Class`: the owner network with its eMOCN scenario (`VF_eMOCN_S1`), `<network>_NNS`, or `<network>_Legacy` without a scenario, with VF, 3UK and VMO2 for the Vodafone, Three and Telefonica networks.
- **Vendor polygons:** the same rule compares the polygon of the sample's own Operator at its start and end positions (`Call_Start_Latitude_A`/`Call_Start_Longitude_A` and `Call_End_Latitude_A`/`Call_End_Longitude_A` in Voice CDRs; Data CDRs, `Test_Start_*`, and Speech CDRs, `Recording_*`, record only the start, used as the end too). A sample outside every polygon of its Operator, or without coordinates, gets `<Operator>_Unknown` and Vendor `Unknown`; Operators without polygons get `<Operator> - All`. Vodafone and Three spellings share the polygons of their network.
- **Stored identities:** `Operator_Vendor` holds `<Operator>_<Vendor>` and `Vendor` the vendor alone (the recognised operator prefix removed), so physical vendors count independently of the operator; both hold `<Operator> - All` for operators without a vendor, retained in individual and combined CDRs and their exports. `Vendor_Operator` (`<Vendor>_<Operator>`) is derived when the CDRs are read, so every CDR has it without being mapped again. Every filter that offers both identities keeps them in sync.
- **Older CDRs:** CDRs processed before these names are migrated once when the workspace opens (the former `Vendor` becomes `Operator_Vendor`, the former `Vendor_Only` becomes `Vendor`). CDRs mapped before this rule keep `Vodafone_Mixed Vendor`, `Vodafone_Other Vendor` or `3_Mixed Vendor`, and show Vendor mapping outdated, until mapped again.

#### During Upload

- The ready VFUK and 3UK Network Inventories appear beside each CDR row, the newest of each proposed; either, both or neither may be selected.
- Every Multivendor Mapping of the workspace and of the upload is applied, with every ready Network Inventory that can map Vendors (which only completes the cells the mappings lack).
- **Vendor source** is offered only when the CDRs have both sources, in the workspace or the same upload: **Cell inventories** or **Vendor polygons** (every Vendor polygons dataset), proposed as above.

#### After Upload

1. Click **Map** on a CDR (or **Map Vendor, Region & Cluster** for several).
2. Select one or more ready CDRs, mapped or not, in CDR Data, Voice and Speech cards side by side, each with **Select All/None** (each list scrolls on its own when the dialog would not fit). The CDRs marked **Vendor mapping outdated** are selected when it opens.
3. In **Mappings to apply**, one card per mapping, each with **How each mapping works** below it:
   - **Vendor:** choose **Cell inventories** / **Vendor polygons** when the workspace has both. For the cell inventories, tick the **Multivendor Mappings** (each with its Operators, date and LTE and NR cells, and a warning when it has no NR cells), confirm the **Vodafone UK** (VFUK) and **Three UK** (3UK) Network Inventories of earlier versions, and tick the **Cell Configuration and other Network Inventories** to use (unticked when there are Multivendor Mappings), each with its networks (its Operator, or Multi-operator) and snapshot date. For the polygons, tick those to apply (all selected).
   - **Region** and **Cluster:** optionally choose their polygons.
4. Click **Map** in the bar at the bottom of the dialog (always visible; it counts the selected CDRs) and wait for processing to finish.

- **Clear** is only needed to remove mappings; a mapping left as "No … mapping" keeps its previous result. **Clear Mappings** and **Reprocess Datasets** use the same wide dialog, with CDR Data, Voice and Speech panels (and Other Datasets for Reprocess), each with **Select All/None**.
- **Speed:** re-mapping only the Vendor takes seconds: it reads only the columns it needs and rewrites only the Vendor and serving-cell columns (unless an Auto-calculated Field reads them, which recalculates the CDR), also when the dialog proposes Region and Cluster mappings the CDR already has with unchanged polygons. Region and Cluster mappings rebuild the CDR from its source file.

## Dataset Inspection and Enrichment

### Dataset Preview

**Preview** (also **Preview Dataset** of [CDR Analysis](datasets-analysis.md#preview-and-export)) opens the persisted rows in a separate view. Regions, Clusters and Vendors datasets open a map instead: their polygons, each in its own colour and named on the map and in the legend, over the grey outline of their countries (see [Tips & shortcuts](#tips-shortcuts)).

- **Pages:** 100 rows, navigating the complete persisted table; wide tables scroll sideways with <kbd>Shift</kbd> and the mouse wheel. A searchable Dataset selector changes the dataset.
- **Columns:** column-name and label selectors hide fields without filtering rows. **Filter Labels** shows only the columns of one or more labels (Derived, Auto-calculated, CDR-Main or the source CDR type); **All Labels** restores every column.
- **Value filters:** every column menu loads its complete distinct-value list; filters on several columns combine, Excel-style. **Clear N Filters** removes them.
- **Export CSV** (CDR previews) downloads every row matching the value filters, with all its columns, as `dataset-<id>-preview.csv`, recorded in App Events (`export_dataset_preview_csv`).
- **Column order and colours:** origin fields (`Source_File`, `Source_Sheet`, `Dataset_Kind`, yellow), main CDR fields (blue, `CDR-Main`), Auto-calculated Fields (purple), the other derived fields (light green, `Operator_Vendor` and `Vendor` among them) and then the source fields. Empty fixed, derived and Auto-calculated fields stay visible, and stronger header colours set labels apart from values.
- **Labels:** `CDR-Main` marks the source fields used most by filters and charts, `Derived` the normalized ingestion fields, `Auto-calculated` the workspace rules, `Analysis-derived` the other shared analytical calculations, and `CDR-Data`, `CDR-Voice` or `CDR-Speech` the other source fields of that type, each in its own colour. `PINNED` marks origin, Main, Derived and Auto-calculated fields, available across dataset views; `UN_PINNED` marks source-only fields present only when the dataset supplies them.
- **Field rules:** hover a `Derived`, `Auto-calculated` or `Analysis-derived` badge for a tooltip with its calculation rule; select it for the complete rule in a floating panel (<kbd>Esc</kbd> or a click outside closes it).
- **`NR_Mode`:** the NR Mode of the CDR of each row, a `PINNED` `Derived` field right after Campaign in every table of rows (CDR and combined previews, the rows of a chart in PPT Designer and Chart Builder), filtered and exported like the others although the CDRs do not store it.
- **Mapping previews** highlight `GCID` and vendor fields. Their vendor selector uses the vendor alone; inventories keep their source columns and derive it from the mapped Vendor values and the workspace operator aliases. Column filters offer **Operator_Vendor** and **Vendor**, listing real vendors first, then Mixed, Other and All groups, then operator-only identities as **Operator - All**. The derived column travels with the dataset rows in workspace transfers and backups.

### Layer3 Logs

The **Layer3 Logs** are the parsed drivetest logs of the tests of each campaign, as a log parser delivers them: one or more CSV files (`Consolidated_Dataset_1.csv`, `Consolidated_Dataset_2.csv`…) or their ZIP, one row per record of the log of every test: radio samples of the LTE and NR serving, secondary and neighbour cells, events, RRC, NAS and SIP messages (L3), RRC states, PDSCH and PUSCH statistics and the call session. Each session is identified by its **JoinID** (the `JOIN_ID` of the CDRs) and its **UE**: `A` and `B` are the two ends of a voice call, `Data` a data test.

- **Upload:** the files or the ZIP as they come, type **Layer3 Logs**; names with `Consolidated_Dataset`, `DT Log`, `Layer3` or `L3` are proposed with that type.
- **Columns:** at least `Campaign`, `JoinID`, `UE`, `EventFullDate`, `Latitude`, `Longitude` and `SourceTable`; any other column keeps the name the parser gave it.
- **One dataset per campaign:** every value of its `Campaign` column becomes a dataset, named after the delivery and its campaign (`Consolidated_Dataset_3 - UK_Q3_SA_2026`), with its **Campaign** read as the CDRs read theirs (`UK_Q3_SA_2026` → `2026-Q3`) and its NR Mode from the same value (`SA`).
- **Storage:** the rows never go through the workspace database: each campaign is written, in delivery order, to a Parquet file in the input folder (the source of its dataset), and the delivery file is removed once written. The UK Q3 2026 delivery (a 48 MB ZIP of 1.5 GB of CSV, 1.86 million rows and 370 columns) takes about a minute and keeps 45 MB.
- **Sessions:** each session (JoinID and UE) is summarised in the **Layer3 Log Sessions** table: operator, service, status, start, end and duration, records, positions, area and RAN Configurations.
- **New deliveries:** the same name replaces its campaigns; another name adds its datasets, and a session in several of them is read from the newest.
- **Actions:** **Preview** shows the rows read-only from the Parquet source, **Reprocess** reads it again, **Delete** removes the dataset, its source and its sessions.
- **Transfers:** like the CDRs: full backups, full workspace packages and transfers of the workspace database and input files, not light backups.

### CA Appendix

The **CA Appendix** is the quarterly NetCheck file with the Carrier Aggregation details of each test (`20261017_NET CHECK_DATA CA Appendix_Q3 2026.xlsx`): one row per test, keyed by its `JOIN_ID`.

- **What it has:** the aggregated LTE and NR bandwidth, DL and UL carriers and band combinations of the test; per carrier (LTE PCC, SCC1–4; NR PCC, SCC1–5) its band, bandwidth, channel, PCI and radio and scheduling statistics; the eNodeBs and gNodeBs that served it.
- **What it lacks:** Campaign, cell identities and positions. Each test takes Campaign, NR Mode, Operator and every other field from the CDR test with the same `JOIN_ID`.
- **Upload:** the file as it comes (one per quarter, NSA and SA together), type **CA Appendix**; a name with `Appendix` (or `Apendix`) is proposed with that type.
- **Storage:** read as it streams (a quarter is over 1 GB and about 700,000 tests: around 6 minutes) and kept as Parquet in the input folder, never in the workspace database.
- **Fields of the CDRs:** every column except the identity of the test becomes a `CA_` field of the CDR tests with its `JOIN_ID` (`CA_Main_Total_Bandwidth_DL`, `CA_NR_SCC1_Main_Band`…):
  - `Main` values (`value(seconds)`, held longest) become their value; numeric columns are numbers; timelines stay text.
  - `CA_eNodeB_ID` and `CA_gNodeB_ID` are the first nodes of the test; `CA_eNodeB_Changes` and `CA_gNodeB_Changes` count its node changes.
  - Written in the background (**CA Appendix fields of the CDRs** in the background tasks card) when a CA Appendix or CDR is processed, reprocessed or deleted. CDRs without matching tests keep no `CA_` column; for a `JOIN_ID` in several files the newest wins.
- **Where it is used:** **PPT Designer** (section *CA Appendix* in Chart Builder), Query Builder, CDR Analysis and the AI Assistant, with the filters of the CDR; Network Insights → [Spectrum](network-insights.md#spectrum).
- **Actions:** **Preview** reads its Parquet source; **Reprocess** reads it again; **Delete** removes it, and the CDRs lose its fields in the background.
- **Transfers:** like the CDRs and Layer3 Logs: full backups, full workspace packages and transfers, not light backups.

### Master Grid

The weekly **Master Grid List** of the VodafoneThree sites gives the [NNS Break-down](scoring-gap-analysis.md#nns-break-down) of Scoring & GAP Analysis the capacity of the NNS sites and the NNS sites planned.

- **Upload:** the workbook as it comes (`RED_PINK_MasterGridList V1.5 2026_Wk46 ….xlsx`), type **Master Grid**; a name with `Master Grid` is proposed with that type.
- **What is kept:** from its `MasterSiteGridList` sheet (the header row with `Site ID` and `Keep / Remove Status`, below its notes), one row per site in the table **Master Grid Sites** (`master_grid_sites`): Site ID, SITE ID + Pairing, SiteRef2, JVCO_ID, Operator, Latitude, Longitude, Rural / Urban, Keep / Remove Status, High/Med/Low config, Target Deployment FY, CMA Year, NNS Vendor, Region and Vodafone Region. The week of its file name (`2026-W46`) is shown in its card. About 44,000 sites are read in a few seconds.
- **Which one is used:** the newest ready Master Grid of the workspace; uploading a new one calculates the NNS Break-downs again.
- **Actions:** **Preview** shows its sites; **Reprocess** reads the workbook again; **Delete** removes it and its sites.
- **Transfers:** its sites travel with the workspace database and its workbook with the input files (backups, workspace packages and transfers).

### Auto-calculated Fields

The Auto-calculated Fields of the workspace, fields worked out for every CDR row from its other fields, are managed in Workspace Config: see [Auto-calculated Fields](workspace-config.md#auto-calculated-fields). Their updates of the CDR tables show in [CDR Tables Updates](#cdr-tables-updates).

## Troubleshooting

- Dataset not offered in Reporting: confirm its assigned type and **Processed** status.
- PPT button missing: only ready Data, Voice and Speech CDRs are eligible.
- Vendor Comparison disabled: every selected CDR must have mapping applied.
- Expected campaign missing: inspect the resolved `Campaign` field in Preview.
- Expected city missing: check both the source geographic columns and the normalised field used by the template.

## Tips & shortcuts

These gestures save clicks while loading and inspecting data. The shortcuts that work everywhere are in [Web Interfaces](web-interface.md#tips-shortcuts); those of the mappings and Auto-calculated Fields are in [Workspace Config](workspace-config.md#tips-shortcuts).

**Loading data**

| To… | Do this |
| --- | --- |
| Add files to upload | Drop them on the **Drop workbooks or browse** zone of Data Ingestion, or click it to choose them |
| Select every CDR of a campaign, week or day | Tick the box of its group in the CDR tables (folded or not) |
| Select every dataset of a table | Tick the box in its ID header |

**Map of Regions, Clusters and Vendors** (their Preview)

| To… | Do this |
| --- | --- |
| Zoom in or out | Mouse wheel |
| Move the map | Drag it |
| See every polygon again | Double-click the map |
| Find a polygon on the map | Hover its name in the legend: its polygon is highlighted |

**Dataset Preview** (also in CDR Analysis)

| To… | Do this |
| --- | --- |
| Scroll a wide table sideways | <kbd>Shift</kbd> + mouse wheel over the table |
| Read how a field is calculated | Hover its `Derived`, `Auto-calculated` or `Analysis-derived` badge |
| See the complete rule of a field | Click its badge; <kbd>Esc</kbd>, its close button or a click outside closes the panel |
