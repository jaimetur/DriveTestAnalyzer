# AI Assistant

Use the **AI Assistant** to ask the active workspace questions in your own words, in any language, and get the answer in the same chat: the scoring of an operator broken down by vendor, where it loses points against the leader, how many Non-Qualified Calls each operator has and why, which campaigns and methodologies there are, or how to do something in the tool. The assistant reads the workspace with the same calculations as its modules, answers with tables when they help, says how it calculated every figure and proposes the next questions to ask.

> [!IMPORTANT]
> **No customer name leaves the server.** Before a question, the workspace context or the result of a calculation is sent to the AI engine, every name of an operator, vendor, region, cluster, city, campaign, methodology or workspace is replaced by a code (`OP1`, `VN2`, `RG3`, `CL4`, `CT5`, `CP6`, `MT7`, `WS1`), also in the words of your question. The engine reasons on the codes; the tool puts the real names back in the answer you read. Only codes, figures, dates and the words of the question travel; never the rows of the CDRs, coordinates, call identifiers or user names. **What was sent**, below every answer, shows exactly what the engine received and what it replied.

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
- *How do I create a Saved Filter that follows the latest campaign?*

A quarter (2026-Q3) stands for the campaign of that quarter; when the quarter has an NSA and an SA campaign, the assistant answers for the NSA one and says that the SA one exists, or answers both. When a question can be read in ways that change the answer, it asks one short question back instead of guessing. Follow-up questions keep the context of the conversation (*and in SA?*).

## Read an answer

Each answer starts with the direct answer and then the detail, with its tables. Below it:

- **Follow-up questions**: the next questions the assistant proposes; select one to ask it.
- The engine, its model, how long the answer took and the tokens it used.
- 👍 / 👎: tell whether the answer was useful; 👎 asks, optionally, what was wrong. Your feedback is recorded with the answer (and in App Events) to improve the answers and the glossary.
- **What was sent**: every request the engine received for this answer, exactly as it was sent, with what it replied, the instructions of the assistant and the real names of the codes (shown only on this page).
- **Suggest a glossary term**: teach the assistant something the data does not tell (see [The glossary of the workspace](#the-glossary-of-the-workspace)).
- **How it was calculated**: every tool the assistant used, with its arguments (the campaigns, NR Mode, split and filters), what it gave and how long it took.

> [!TIP]
> **Every figure is checked.** Every figure of an answer must come from the results of the tools: differences, shares and ratios are calculated by the tool, not by the engine. When the engine writes a figure that is in no result, it is asked once to correct it; if it cannot, the answer shows a warning with the figures that could not be traced.

## What the assistant can read

The assistant only reads; it changes nothing in the workspace. When asked to change something, it says which module does it. Its tools:

| Tool | What it reads |
| --- | --- |
| Workspace overview | The campaigns of each NR Mode, newest first, with their quarter, CDR types and methodology (Flex campaigns marked as such); the operators with their role in the Operator Maps (Focus or not); the vendors, regions and clusters; how many cities; the scoring methodologies with their environments and points; the Saved Filters. It is given with every question. |
| Values | Every Operator, Vendor, Region, Cluster, City or Campaign of the CDRs. |
| Scoring | The Scoring & GAP Analysis points of the operators for any campaigns (or Latest, Previous, Latest 2… campaigns), NR Mode (NSA, SA or NSA vs SA), split (Operator, Campaign, Vendor, Region, Cluster, City, Dataset Type) and filters, calculated exactly as a Saved Filter of the same selection: each campaign with the methodology that applies to it, the operators the Operator Maps exclude left out, the Scoring History used when it covers the selection. With the points per environment and category, the KPIs that lose most points and the GAP to the reference operator. |
| Saved Filters | The Saved Filters of Scoring & GAP Analysis and the totals of a saved result, without calculating anything. |
| Non-Qualified Calls | The number of Non-Qualified Calls grouped and filtered by campaign, operator, vendor, area, service, NR Mode, technology, environment, failure category, classification and phase, the status and root cause of the analysts and the DT Analyzer RCA. |
| Help | The passages of this Help that best answer a question about the tool. |
| Calculator | Differences, shares and ratios of figures of the results. |

> [!NOTE]
> **About some operators.** To answer about some operators the assistant calculates the scoring of every operator and lists only theirs: some KPIs (the Ultra thresholds) are scored against the best operator of the calculation, so the points match those of Scoring & GAP Analysis with all the operators. The operators with the role **Exclude** in the Operator Maps are never named.

## Privacy: the names sent as codes

The names of the workspace — those of its Operator Maps (with their aliases), CDRs (operators, vendors, regions, clusters, cities and campaigns), methodologies and the workspace itself — and the names of well-known operators and vendors are replaced by codes everywhere: in the question, the workspace context, the glossary, the conversation so far and every result. Two-letter names (EE, O2, VF) are taken as names only in capitals, and names that are also common words (Three) only with a capital. The codes of a conversation never change: a name that appears later takes the next free code, so earlier answers keep meaning the same thing. Before every request the tool checks that no known name is left; if one were, nothing is sent and the chat says so.

What still travels: the words of the question that are not names (a name the workspace does not have, or a misspelled one, travels as written), figures, dates, quarters, KPI and category names of the methodology and the instructions of the assistant. Which provider receives them, and under which terms, is chosen by the super-admins of the deployment (see [Engines](#engines)).

## The glossary of the workspace

The glossary holds what the assistant needs to know about the workspace that its data does not tell: what a Region, a label or a word of the team means (for example *Vendor A: the Region of the tests whose network Ericsson operates*). Every question of the workspace takes its terms; their names are sent as codes like any other. The Operator Maps, Campaign Maps and methodologies are read from the workspace and need no entry.

Users teach it from the chat: **Suggest a glossary term**, below an answer, sends a term and its meaning to the editors of the workspace. They accept it (correcting it first if needed) or dismiss it in **Workspace Config → AI Assistant Glossary** (see [Workspace Config](workspace-config.md)), where they also add, edit and delete terms. The glossary is not a training of the AI model: it is text given with every question, which anyone can read and correct, and which changes the answers from the next question on.

The terms travel with **Admin → Import / Export** and **Transfers** (element *AI Assistant Glossary*, by workspace), with full workspace packages and with backups; an imported term replaces the one with the same identity, or else the same term, and nothing is deleted. Suggestions not accepted stay in their workspace.

## Conversations

The list on the left holds your conversations of the active workspace, the latest first; only you see them. **New conversation** starts another one (the first question names it); **Rename** and **Delete**, above the chat, rename it or delete it with its answers. The page reopens the conversation you had open. Conversations stay in the workspace database: they are not exported, transferred or backed up on their own, only with a full copy of the workspace database.

## Engines

The assistant answers with the AI engines a super-admin enables in **Super Admin → AI Comment Writers**, the same ones that write the comments of PPT Designer: **Kiro CLI** (run on the server, headless and without tools of its own) and **Claude**, each with the API key of the server or of each user, as the super-admin chooses (users save theirs in the user menu, **API keys**). The engine selector beside **Ask** offers the enabled ones, the default one first. Without an enabled engine the chat explains it and asks nothing. The engine never reads the workspace: it asks for the tools above, the tool runs them on the server and sends back their results with the names as codes. Another engine, such as a model of the organisation run on its own servers, plugs into the same interface.

## App Events

Every action is recorded in App Events (module AI Assistant): each question (with its conversation, engine and text), each answer (its duration, steps, the tools used with their duration and errors, the tokens, the size of what was sent and any figure that could not be traced), each failed or stopped question with its reason, the feedback, the suggestions and the changes of the glossary, and the conversations renamed and deleted.
