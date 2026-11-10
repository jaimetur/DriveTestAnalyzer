# AI Assistant

Use the **AI Assistant** to ask the active workspace questions in your own words, in any language, and get the answer in the same chat. For example:

- the scoring of an operator broken down by vendor, where it loses points against the leader, or a global commentary of the scoring of the campaigns, operators or vendors you name;
- how many Non-Qualified Calls each operator has and why, or the list of their JOIN_IDs by any condition (in a Cluster and a Time-Window issue of at least 4 calls);
- any count, average or distribution of the rows of the CDRs;
- the radio coverage and quality of Network Insights;
- a commentary on the charts of a PPT Designer Design;
- a chart of the scoring of the operators, of a PPT Designer Design or of any result, drawn in the chat;
- which campaigns and methodologies there are, or how to do something in the tool.

The assistant reads the workspace with the same calculations as its modules, answers with tables and charts when they help, says how it calculated every figure and proposes the next questions to ask.

> [!IMPORTANT]
> **No customer name leaves the server.** Before a question, the workspace context or the result of a calculation is sent to the AI engine, every name of an operator, vendor, region, cluster, city, campaign, methodology, workspace or user is replaced by a code (`OP1`, `VN2`, `RG3`, `CL4`, `CT5`, `CP6`, `MT7`, `WS1`, `US1`), also in the words of your question and inside identifiers (`OP1_Voice`). The engine reasons on the codes; the tool puts the real names back in the answer you read. Only codes, figures, dates, the words of the question and the values a calculation needs (such as JOIN_IDs, KPI values or site IDs, at most 200 rows of a query) travel. Coordinates, subscriber identifiers (IMSI, IMEI, MSISDN, dialled number), IP addresses and the paths of the files never do: no table of the assistant holds them. A long list of an answer is shown by the tool itself, without passing through the engine. **What was sent**, below every answer, shows exactly what the engine received and what it replied.

> [!NOTE]
> **Module access.** The AI Assistant is in every Modules Profile and needs a workspace: each workspace has its own conversations and glossary. Super-admins choose who sees it in **Super Admin → Modules Profiles** and can rename it in **Super Admin → Interface Settings**. It answers only once a super-admin enables an AI engine (see [Engines](#engines)).

## Presentation

The presentation **AI Assistant** sums the module up. Ask the workspace in your own words and get the answer in seconds, calculated by the tool itself, with every figure traced and no customer name sent to the AI engine. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
assistant
```

## In this guide

| Task or topic | Go to |
| --- | --- |
| Ask a question | [Open section](#ask-a-question) |
| Read an answer | [Open section](#read-an-answer) |
| Charts | [Open section](#charts) |
| What the assistant can read | [Open section](#what-the-assistant-can-read) |
| Privacy: the names sent as codes | [Open section](#privacy-the-names-sent-as-codes) |
| The glossary of the workspace | [Open section](#the-glossary-of-the-workspace) |
| Conversations | [Open section](#conversations) |
| Engines | [Open section](#engines) |
| App Events | [Open section](#app-events) |

## Ask a question

Write the question in the box at the bottom of the chat and press **Ask** (or Enter; Shift+Enter starts a new line), or choose one of the examples of a new conversation. While the assistant works, the chat shows its steps (reading the workspace, calculating the scoring, checking the figures); **Stop** ends it. A question usually takes from a few seconds to a minute, depending on the engine and on how many calculations it needs.

Ask as you would ask a colleague, for example:

- *What is the scoring of Vodafone in 2026-Q3 broken down by Vendor?*
- *Where does Three lose most points against EE in the latest campaign?*
- *Compare the NSA and SA campaigns of the last quarter for every operator.*
- *How many Non-Qualified Calls of the latest campaign are there per operator and failure category?*
- *List the JOIN_IDs of the NQ Calls in a Cluster of at least 4 calls and in a Time-Window issue of at least 4 calls.*
- *What is the median DL throughput of each operator by environment in the latest campaign?*
- *Comment globally on the scoring of 2026-Q3 against 2026-Q2 for Vodafone and EE, by Vendor.*
- *Comment on the RSRP and SINR of each vendor in the latest campaign (Network Insights).*
- *Analyse the first chart of the first PPT Design and give me your comments.*
- *Draw a chart with the scoring of each operator of the latest campaign.*
- *Show the charts of the second slide of the first PPT Design.*
- *Show the DL throughput CDF of the last two NSA campaigns, with the lines of the latest campaign thicker.*
- *How do I create a Saved Filter that follows the latest campaign?*

A quarter (2026-Q3) stands for the campaign of that quarter; when the quarter has an NSA and an SA campaign, the assistant answers for the NSA one and says that the SA one exists, or answers both. When a question can be read in ways that change the answer, it asks one short question back instead of guessing. Follow-up questions keep the context of the conversation (*and in SA?*).

## Read an answer

Each answer starts with the direct answer and then the detail, with its [charts](#charts) and tables. Each table says how many rows it has and has **Download CSV**, which saves it as a CSV file that Excel opens. A long table, such as a list of JOIN_IDs, scrolls inside the answer with its header in sight. The tool fills a table of a query result itself, with every row of the result (up to 5,000), so the engine never copies, cuts or changes a list. Below the answer:

- **Follow-up questions**: the next questions the assistant proposes; select one to ask it.
- The engine, its model, how long the answer took and the tokens it used.
- 👍 / 👎: tell whether the answer was useful; 👎 asks, optionally, what was wrong. Your feedback is recorded with the answer (and in App Events) to improve the answers and the glossary.
- **What was sent**: every request the engine received for this answer, exactly as it was sent, with what it replied, the instructions of the assistant and the real names of the codes (shown only on this page).
- **Suggest a glossary term**: teach the assistant something the data does not tell (see [The glossary of the workspace](#the-glossary-of-the-workspace)).
- **How it was calculated**: every tool the assistant used, with its arguments (the campaigns, NR Mode, split and filters), what it gave and how long it took.

> [!TIP]
> **Every figure is checked.** Every figure of an answer must come from the results of the tools: differences, shares and ratios are calculated by the tool, not by the engine. When the engine writes a figure that is in no result, it is asked once to correct it; if it cannot, the answer shows a warning with the figures that could not be traced.

## Charts

Ask for a chart (*draw*, *plot*, *show a chart of…*) and the answer shows it above its tables; the assistant also adds one when a chart says more than a table, such as the points of several operators. The charts are drawn by the same chart painter as PPT Designer and Network Insights: hover a bar, a point or a slice to read its value, drag a rectangle to zoom, select a legend entry to hide its series. Above each chart, **Expand** opens it larger and **Download PNG** saves it as a picture.

The engine never gives the figures of a chart: it only names the data the tools gave for the question and how to draw it, and the tool draws it from that data, with the real names. A chart can show:

| Chart | What it draws |
| --- | --- |
| Scoring | A result of the scoring tool as Scoring & GAP Analysis shows it, in the colours of the Operator Maps and the order of their operators: the points of each group (by the split asked, such as Vendor or Region), the points per environment or per category, the GAP to the reference operator, the points of each operator over several campaigns (a trend) or the KPIs that lose most points. |
| PPT Designer | A chart of a Design read for the question, exactly as the viewer of the Design draws it (its chart type, format, colours and legend), named after its Design and slide. |
| Query | The rows of a query result: the categories of some columns, the values of others, a bar, line or pie per value of a column (one line per operator over the campaigns, for example). |
| Table | A table of the answer (whose figures are checked as those of the text), as bars, horizontal bars, lines or a pie. |
| Earlier chart | A chart of an earlier answer of the conversation, drawn again with another style or title without calculating anything. |

Each operator keeps its colour of the Operator Maps, also when its name is part of the name of a series (*EE UK_Q3_NSA_2026*): when an operator has several lines, the one of its latest campaign is solid and the earlier ones dashed, then dotted.

**Style a chart in your own words**, in the question or afterwards (*make the lines of the latest campaign thicker*, *VF in blue*, *the 2026-Q2 lines dotted*, *legend at the bottom*, *call the axis Share of tests*):

- the **colour** of a series (a colour name or `#RRGGBB`), the **width** of its line (1 to 14; 4 by default) and its **dash** (solid, dashed or dotted), for one series or for every series whose name holds a word, such as a campaign or an operator;
- the place of the **legend** (top, bottom, left, right or none);
- the **titles of the axes**: both in line charts, the axis of the values in bar charts, those of the Format of PPT Designer in the charts of a Design.

A style asked after the chart is drawn draws it again from the earlier answer: the assistant does not calculate it again.

An answer has up to four charts, and a chart up to 160 bars or 24 lines. A chart that cannot be drawn (a column the data does not have, a trend of one campaign, a style for a series the chart does not have) is sent back to the engine once to correct it; if it still cannot be drawn, the answer shows a warning with the reason. The charts are kept with the answer and drawn again when the conversation is opened.

## What the assistant can read

The assistant only reads; it changes nothing in the workspace. When asked to change something, it says which module does it. Its tools:

| Tool | What it reads |
| --- | --- |
| Workspace overview | The campaigns of each NR Mode, newest first, with their quarter, CDR types and methodology (Flex campaigns marked as such); the operators with their role in the Operator Maps (Focus or not); the vendors, regions and clusters; how many cities; the scoring methodologies with their environments and points; the Saved Filters. It is given with every question. |
| Values | Every Operator, Vendor, Region, Cluster, City or Campaign of the CDRs. |
| Scoring | The Scoring & GAP Analysis points of the operators for any campaigns (or Latest, Previous, Latest 2… campaigns), NR Mode (NSA, SA or NSA vs SA), split (Operator, Campaign, Vendor, Region, Cluster, City, Dataset Type) and filters, calculated exactly as a Saved Filter of the same selection: each campaign with the methodology that applies to it, the operators the Operator Maps exclude left out, the Scoring History used when it covers the selection. With the points per environment and category, the KPIs that lose most points and the GAP to the reference operator. For a global commentary it also reads the **Summary** of the module for that selection: where each operator stands, its GAP by parts, its levers, the points at stake, the campaign comparisons and trends, and Where to act. |
| Saved Filters | The Saved Filters of Scoring & GAP Analysis and the totals of a saved result, without calculating anything. |
| Non-Qualified Calls | The number of Non-Qualified Calls grouped and filtered by campaign, operator, vendor, area, service, NR Mode, technology, environment, failure category, classification and phase, the status and root cause of the analysts and the DT Analyzer RCA. |
| Query | One read-only SQL query (DuckDB) for any other question, over these tables: **nq_calls** (one row per Non-Qualified Call, as the list of the module shows it, with its follow-up, DT Analyzer RCA, scoring impact, priority, queue and its Hotspot, Time-Window and Cluster: their IDs `H-…`, `T-…`, `C-…` and how many calls each holds); **cdr_data**, **cdr_voice** and **cdr_speech** (every row of the CDRs, from their columnar copies); **cdrs** (the CDRs). It lists calls or tests, counts, averages, percentiles and distributions by any column, and joins the calls with the rows of their CDRs. Only one SELECT runs, on those tables only; it cannot change anything or read any file. It stops after 90 seconds and keeps up to 5,000 rows. |
| Columns | The columns of each table of the query, with what each column of nq_calls holds, so the engine finds the fields it needs among the hundreds of the CDRs. |
| Network Insights | The analysis of [Network Insights](network-insights.md) as its page shows it (the stored one when it was made before), for the campaigns, NR Mode, technology (LTE, NR or both), grouping (Operator, Vendor, Region…) and filters of the question: the RSRP and SINR of each group with their change against the previous campaign, the Key Findings with their headlines, and on request the spectrum, bandwidths, latency, NR carriers and serving cells. |
| PPT Designer | The Designs of [PPT Designer](ppt-designer.md) in the order of their library, the slides of one with their charts, and the charts of up to four slides read as the [Auto comments](ppt-designer.md) read them: the value of every group of each chart with its samples, which direction is better and the comments the rules write. The Design is prepared as its viewer prepares it, with its saved selection and filters, and any of its charts can be [drawn in the answer](#charts). |
| Help | The passages of this Help that best answer a question about the tool. |
| Calculator | Differences, shares and ratios of figures of the results. |

> [!NOTE]
> **About some operators.** To answer about some operators the assistant calculates the scoring of every operator and lists only theirs: some KPIs (the Ultra thresholds) are scored against the best operator of the calculation, so the points match those of Scoring & GAP Analysis with all the operators. The operators with the role **Exclude** in the Operator Maps are never named, and the tables of the query leave their calls and rows out. In those tables, the operator columns hold the names of the Operator Maps.

> [!NOTE]
> **The modules each user sees.** The assistant reads Network Insights and PPT Designer only for the users whose Modules Profile includes them. A CDR whose columnar copy is still being written is not in the CDR tables of the query yet, and its results say so.

## Privacy: the names sent as codes

The names of the workspace — those of its Operator Maps (with their aliases), CDRs (operators, vendors, regions, clusters, cities and campaigns), methodologies and the workspace itself — the user names and full names of the users of the tool, and the names of well-known operators and vendors are replaced by codes everywhere: in the question, the workspace context, the glossary, the conversation so far and every result, also inside identifiers joined by underscores (a test name `Vodafone_Voice_MO` is sent as `OP1_Voice_MO`). A campaign is shown in the answers, their tables (also inside a value such as *EE - UK_Q2_2026*) and their charts with its label of the Campaign Maps, as in every module; its label is another spelling of it in the questions, unless it is written as a quarter (2026-Q3), which is sent as it is. Two-letter names (EE, O2, VF) are taken as names only in capitals, and names that are also common words (Three) only with a capital. The user names that are also words (generic accounts such as *super* or *demo*) are coded only as the values of user columns, such as the assignee of a call. The codes of a conversation never change: a name that appears later takes the next free code, so earlier answers keep meaning the same thing. Before every request the tool checks that no known name is left; if one were, nothing is sent and the chat says so.

What still travels: the words of the question that are not names (a name the workspace does not have, or a misspelled one, travels as written), figures, dates, quarters, KPI and category names of the methodology, the instructions of the assistant, and the values a query or a chart reads that are not names (JOIN_IDs, site and cell IDs, test names without the names of the workspace, KPI values). Which provider receives them, and under which terms, is chosen by the super-admins of the deployment (see [Engines](#engines)).

## The glossary of the workspace

The glossary holds what the assistant needs to know about the workspace that its data does not tell: what a Region, a label or a word of the team means (for example *Vendor A: the Region of the tests whose network Ericsson operates*). Every question of the workspace takes its terms; their names are sent as codes like any other. The Operator Maps, Campaign Maps and methodologies are read from the workspace and need no entry.

Users teach it from the chat: **Suggest a glossary term**, below an answer, sends a term and its meaning to the editors of the workspace. They accept it (correcting it first if needed) or dismiss it in **Workspace Config → AI Assistant Glossary** (see [Workspace Config](workspace-config.md)), where they also add, edit and delete terms. The glossary is not a training of the AI model: it is text given with every question, which anyone can read and correct, and which changes the answers from the next question on.

The terms travel with **Admin → Import / Export** and **Transfers** (element *AI Assistant Glossary*, by workspace), with full workspace packages and with backups; an imported term replaces the one with the same identity, or else the same term, and nothing is deleted. Suggestions not accepted stay in their workspace.

## Conversations

While a question is answered you can scroll up to read the conversation: the chat stays where you leave it, and the round arrow at its bottom right (marked with a dot when the answer arrives) takes you back to the last line. While you are at the last line, the chat follows the steps and the answer.

The list on the left holds your conversations of the active workspace, the latest first; only you see them. **New conversation** starts another one (the first question names it); **Rename** and **Delete**, above the chat, rename it or delete it with its answers. The page reopens the conversation you had open. Conversations stay in the workspace database: they are not exported, transferred or backed up on their own, only with a full copy of the workspace database.

## Engines

The assistant answers with the AI engines a super-admin enables in **Super Admin → AI Comment Writers**, the same ones that write the comments of PPT Designer: **Kiro CLI** (run on the server, headless and without tools of its own) and **Claude**, each with the API key of the server or of each user, as the super-admin chooses (users save theirs in the user menu, **API keys**). The engine selector beside **Ask** offers the enabled ones, the default one first. Without an enabled engine the chat explains it and asks nothing. The engine never reads the workspace: it asks for the tools above, the tool runs them on the server and sends back their results with the names as codes. Another engine, such as a model of the organisation run on its own servers, plugs into the same interface.

## App Events

Every action is recorded in App Events (module AI Assistant): each question (with its conversation, engine and text), each answer (its duration, steps, the tools used with their duration and errors, the tokens, the size of what was sent any figure that could not be traced and the charts it drew), each failed or stopped question with its reason, the feedback, the suggestions and the changes of the glossary, and the conversations renamed and deleted.
