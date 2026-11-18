# Query Builder

Query Builder runs read-only SQL against selected, processed Data, Voice and Speech CDRs in the active workspace. Use **Assistance Mode** to assemble common queries with form controls, or **SQL Mode** to edit SQL directly.

> [!IMPORTANT]
> **Read-only queries.** Run a single SELECT statement, optionally with WITH. Query Builder does not support database writes.

> [!TIP]
> **Preview is not execution.** Changing Assistance controls updates the SQL; **Run query** refreshes the results.

## Presentation & Guide

```presentations
builders
guide:query-builder.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Build a query without writing SQL | [Assistance Mode](#assistance-mode) |
| <span class="guide-sub">↳ Read and export the results</span> | <span class="guide-sub">↳ [Results](#results)</span> |
| Write the SQL myself | [SQL Mode](#sql-mode) |
| Save a query and reuse it | [Saved queries](#saved-queries) |
| Learn the tips and shortcuts | [Tips & shortcuts](#tips-shortcuts) |

## Assistance Mode

1. Open **Query Builder** with a workspace active.
2. Select one or more ready source datasets in the **Data**, **Voice** and **Speech** panels (each with its count, **Select All / None**, and the campaigns and NR Mode of every CDR; Weekly and Daily CDRs are highlighted) and one or more **CDR types to use** represented by those sources. At least one CDR type stays selected: clearing the last one restores it and the assistant explains why.
3. Choose the fields. By default **Show all fields** is off and `source_dataset_name` and `cdr_type` are preselected; enable it to include every available column.
4. Add filter conditions: a column, a comparison (**Is**, **Is not**, **Contains**, **Starts with**, **Greater than (number)**, **Less than (number)**, **Is empty** or **Is not empty**) and a value. For `source_dataset_name` with **Is** or **Is not**, choose a name among the selected source datasets that match the selected CDR types; other comparisons take a text value. Choose **AND** or **OR** for each condition after the first: mixed connectors are evaluated from top to bottom and grouped with parentheses.
5. Choose the sort order and the maximum rows (1 to 100,000, 100 by default), or **All rows** to omit the SQL `LIMIT`.
6. Review the generated SQL, then **Run query**.

How the SQL is built:

- **Live preview:** the read-only SQL preview updates as you change the controls; the results update only after **Run query**. An incomplete filter does not erase it: completed filters and other valid selections still appear, and the assistant explains what needs attention. Without a source or output field, the preview says what is needed.
- **Several CDR types:** their results are combined with `UNION ALL` and a `cdr_type` column identifies each row's type. Each type contributes its own `SELECT` against its temporary view (`selected_data`, `selected_voice` or `selected_speech`); output fields stay aligned, unavailable fields returned as `NULL`. Filters apply to the combined results.
- **Enabled buttons:** **Run query**, **Save query** and **Export CSV** wait for a valid selection with every filter complete; **Copy** and **Export CSV** also wait for a query to have run.
- **SQL Mode:** switch to it to adjust the statement or write joins, common table expressions, aggregates or other SQL the controls do not represent. You can switch back while the preview still holds its initial guidance.
- **Clear Query:** after confirmation, clears the SQL, source selections, filters, field selection, sorting, limit and results; Cancel keeps the query. Saved queries are not deleted.

### Results

- **Pages:** up to 50 rows each, with First, Previous, Next and Last above and below the table; the panel reports the page's rows and columns and the total of matching rows. With **All rows** the pages cover every matching row.
- **Column filters:** the filter button of a column header searches its distinct values (up to 200 shown at a time; search to find more); select the values to keep and apply or clear. Filters of several columns combine, apply to the whole result, later pages included, and reset with a new run.
- **Copy:** the column headers and rows of the visible filtered page, as tab-separated text.
- **Export CSV:** every row and column of the filtered result, without a row cap.
- **Vendor columns:** CDR rows have **`Operator_Vendor`** (`<Operator>_<Vendor>`) and **`Vendor`** (the vendor alone). A column filter on the former `Vendor_Only` name targets `Vendor`, and one on `OP_Vendor` targets `Operator_Vendor`; include that column in the result to use it. Saved SQL that names `Vendor_Only` must be updated to `Vendor`; manually written SQL is kept as authored.

## SQL Mode

Enter manual SQL in the **SQL Query** editor: a single read-only `SELECT`, optionally beginning with `WITH`. Select at least one ready source dataset before running or saving it; results work as in [Assistance Mode](#results).

- **Views:** `selected_data`, `selected_voice` and `selected_speech` hold the selected source datasets, with their original columns plus `source_dataset_id`, `source_dataset_name` and `source_row_id`.
- **Columnar copy:** the views read each CDR from its [columnar copy](workspace-management.md#columnar-copy-of-the-cdrs) (a query that names a CDR table, such as `dataset_rows_12`, reads the copy too), with the same values, row ids and order as the CDR tables gave.
- **Speed:** a query gets only the columns it reads; a page of a query that reads the CDRs in one pass, without sorting, grouping or joining, reads only the rows that page needs; a query that sorts every column of many rows (`SELECT * … ORDER BY`) takes longer than one that selects the columns it needs.
- **Running:** runs and page changes continue in the background while Query Builder checks their status, so a long query does not hold one HTTP request open. **Cancel query** in the running dialog stops it. Only one Query Builder run can be active at a time across the server.

## Saved queries

- **Saving:** give the query a name and optional description to save it in the active workspace database. Saving checks the SQL and selected source columns without running the full query. Removed or built-in examples are not recreated.
- **Loading:** restores its SQL and source selections; a query without CDRs (such as an imported one) keeps the CDRs chosen in the panels, so they can be chosen before or after loading it. SQL that matches the Assistance Mode controls restores those controls; custom or unsupported SQL stays in **SQL Mode**. Queries saved before Assistance Mode remain available.
- **The Saved queries library** lists each query with its name, description and sources, and **Use query** (loads it), the edit button (**Edit saved query**: name, description and source CDRs; the SQL stays as saved), the export button (JSON) and the delete button (after confirmation; the library and load picker refresh).
- **Rights:** saving, editing and deleting need a user-editor, admin or super-admin; a user-viewer loads, runs and exports queries.
- **Moving them:** a Query Builder Queries package or a workspace backup/export ZIP imports saved queries into another workspace: the import replaces the queries the workspace has (by identity, so a query renamed on the source server is renamed here too, or by name) and adds the others, see [Matching and creators](administrator-config.md#matching-and-creators). Exported, transferred and backed-up queries carry their name, description and SQL without CDRs: choose the CDRs when using an imported query. Conditions on `source_dataset_name` use the file names of the CDRs chosen, so review them in another workspace.

## Tips & shortcuts

Query Builder has no shortcut of its own to run a query: use **Run query**. The shortcuts that work everywhere, such as typing letters to jump in a dropdown, are in [Web Interfaces](web-interface.md#tips-shortcuts).

| To… | Do this |
| --- | --- |
| Filter a result column | Its filter button in the header: search its values, tick those to keep and apply |
| Close a column filter without applying it | <kbd>Esc</kbd>, or click outside it |
| Copy the page shown to paste it in Excel | **Copy** (tab-separated text) |
