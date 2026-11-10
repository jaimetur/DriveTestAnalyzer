"""AI Assistant: questions about the workspace in natural language, answered in a chat.

The engine (Kiro CLI or Claude, those of Super Admin → AI Comment Writers, with the key of the server or of the user)
interprets the question and asks for the tools it needs (assistant_tools: the workspace, the Scoring and its Summary,
the Saved Filters, the Non-Qualified Calls, a read-only SQL query over the NQ Calls and the CDR rows, Network Insights,
the charts of PPT Designer, the Help and a calculator); the server runs them and the engine writes the answer.
Nothing it receives names a customer: the names of operators, vendors, areas, campaigns, methodologies and users are
codes (assistant_privacy), and the server puts the real names back in the answer. Every figure of an answer must come
from the results of the tools; a long result (a list of JOIN_IDs) is shown whole by the server, without the engine
copying it. The page shows how each answer was calculated and exactly what was sent to the engine.

The conversations of each user and the workspace glossary (terms the data does not tell, kept in Workspace
Configuration and fed by the suggestions users send from the chat) are kept in the workspace database. The glossary
travels with exports, transfers and backups; the conversations are personal and stay in the workspace (they go with a
full copy of its database only).
"""
from __future__ import annotations

import contextvars
import json
import re
import threading
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.modules.ppt_designer import comment_writers as writers
from src.modules.assistant.assistant_privacy import CODE, Pseudonymizer, dumps, workspace_pseudonymizer
from src.modules.assistant.assistant_tools import ToolContext, ToolError, catalog_text, result_size, run_tool, workspace_overview

CONVERSATIONS_TABLE = 'assistant_conversations'
MESSAGES_TABLE = 'assistant_messages'
GLOSSARY_TABLE = 'assistant_glossary'
TABLE_TITLES = {CONVERSATIONS_TABLE: 'AI Assistant Conversations', MESSAGES_TABLE: 'AI Assistant Messages',
                GLOSSARY_TABLE: 'AI Assistant Glossary'}
GLOSSARY_FORMAT = 'drivetest-analyzer-assistant-glossary'
GLOSSARY_VERSION = 1
MAX_QUESTION_LENGTH = 4000
MAX_STEPS = 10
MAX_TOOL_CALLS_PER_STEP = 6
MAX_TOOL_RESULT_CHARS = 40_000
# Kiro CLI takes the whole prompt as one argument, which Linux limits to 128 KiB.
MAX_PROMPT_CHARS = 110_000
HISTORY_EXCHANGES = 6
MAX_TERM_LENGTH = 120
MAX_MEANING_LENGTH = 2000
EXAMPLE_QUESTIONS = (
    'What is the scoring of each operator in the latest campaign?',
    'Break down the scoring of the latest campaign by Vendor for every operator.',
    'Where does the second operator lose most points against the leader in the latest campaign?',
    'How many Non-Qualified Calls of the latest campaign are there per operator and failure category?',
    'List the JOIN_IDs of the NQ Calls in a Cluster of at least 4 calls and in a Time-Window issue of at least 4 calls.',
    'Comment on the RSRP and SINR of each operator in the latest campaign (Network Insights).',
    'Analyse the first chart of the first PPT Design and give me your comments.',
    'How do I create a Saved Filter that follows the latest campaign?',
)

SYSTEM_PROMPT = '''You are the AI Assistant of DriveTest Analyzer, a tool that analyses drive-test benchmark measurements (the
CDRs of Data, Voice and Speech tests) of mobile operators: their scoring with benchmark methodologies (Scoring & GAP
Analysis), their Non-Qualified Calls and their network. The users are radio and benchmarking engineers.

Privacy. Every name of an operator, vendor, region, cluster, city, campaign, methodology or workspace reaches you as
a code: OP (operators), VN (vendors), RG (regions), CL (clusters), CT (cities), CP (campaigns), MT (methodologies),
WS (workspaces), US (users), followed by a number (OP1, VN2, CP3…), also inside identifiers (OP1_Voice). Use the codes
exactly as you receive them, in the arguments of the tools (also in SQL: operator = 'OP1') and in your answer: the
tool shows the user the real names. Never guess what a code stands for and never ask for the real names. Figures,
dates, quarters (2026-Q3) and identifiers such as JOIN_IDs are real.

How to work:
- Answer from the results of the tools only. Every figure of your answer must appear in a tool result; for a
  difference, a share or a ratio call the calculate tool first. Never estimate or invent a figure.
- Plan the fewest tool calls; call several tools in the same step when they do not depend on each other.
- Read the workspace context given with the question (campaigns of each NR Mode with their quarter, operators with
  their role, vendors, methodologies, Saved Filters) and the glossary before calling tools.
- A quarter (2026-Q3) is the campaign of that quarter; when the quarter has an NSA and an SA campaign, answer for the
  NSA one and say the SA one exists (or answer both when that is short). "Latest campaign" is newest_rank 1.
- To answer about some operators, split by Operator and use "only" in the scoring tool: an Operator filter changes the
  points the module shows.
- For a global commentary of the scoring (the campaigns, operators or vendors to compare), call scoring with detail
  ["insights", "environments", "categories", "gap"] (split_by Vendor to compare vendors, two campaigns to compare
  campaigns): say where each operator stands, what makes its GAP to the leader and the reference, its levers, where
  its points are lost and where to act.
- For questions beyond the other tools — lists of calls or tests (JOIN_IDs), counts, averages, percentiles or
  distributions by any column, failures over time, joins of the NQ Calls with the rows of their CDRs — use query
  (DuckDB SQL) on nq_calls, cdr_data, cdr_voice, cdr_speech or cdrs. Call table_columns first when you do not know the
  columns (search the CDR tables, they have hundreds). Aggregate in SQL; never estimate from some rows.
- The Hotspots (H-…), Time-Window issues (T-…) and Clusters of NQ Calls (C-…) of the panel NQ Hotspots, Time-Window &
  Clustered Issues are the columns hotspot_*, time_window_* and nq_cluster_* of nq_calls; the column cluster is an area.
- For Network Insights (radio coverage and quality, bands, bandwidths, latency), call network_insights: rf and findings
  by default, group by vendor to compare vendors, the latest and previous campaigns to see the change.
- To analyse or comment on the charts of PPT Designer, call ppt_designs (the Designs, then the slides of one) and
  ppt_design_charts for the slides you need. "The first Design" is the first one listed; "the first chart" is the first
  chart of its first slide with charts. Comment on the facts as an analyst would: what stands out, who leads, the gaps,
  the changes, with their figures.
- Operators with the role exclude are left out by the tool: never mention them. Focus operators are the ones the users
  care about most: lead with them when they are in the answer.
- When the question can be read in ways that change the answer (for example a word the glossary does not define), ask
  one short clarifying question as your answer instead of guessing.
- You only read: if the user asks you to change something, explain that the assistant cannot and name the module where
  it is done.

The answer:
- Write in the language of the question. Lead with the direct answer in one or two sentences, then the detail.
- Put comparisons of several figures in "tables" (columns and rows of strings), never as Markdown tables in the text.
- To show the rows of a query result (a list of JOIN_IDs, calls, tests), never copy them: add a table with its title,
  "result" set to the result_id of the query (R1) and empty columns and rows; the tool shows every row of the result
  (up to 5,000) and lets the user download it. Leave "result" empty in the tables you write yourself.
- Say which campaigns, NR Mode and methodology the figures come from, and the caveats the results give (incomplete
  coverage, few samples, the operators left out). Keep the text short: about 200 words unless the user asks for more.
- The text is Markdown: short paragraphs, bullets, **bold**; no headings above ###, no HTML.
- Offer up to three follow-up questions the user may ask next (in "follow_ups"), in the language of the question.

Reply with one JSON object only, every field present:
{"status": "tools" or "answer", "note": "what you do now, one short sentence in the language of the user",
 "tool_calls": [{"tool": "name", "arguments_json": "{...}"}], "answer": "Markdown text, empty while status is tools",
 "tables": [{"title": "", "columns": ["", ""], "rows": [["", ""]], "result": ""}], "follow_ups": ["", ""]}

Tools (arguments as a JSON object in arguments_json):
''' + catalog_text()

STEP_SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['tools', 'answer']},
        'note': {'type': 'string'},
        'tool_calls': {'type': 'array', 'items': {
            'type': 'object', 'properties': {'tool': {'type': 'string'}, 'arguments_json': {'type': 'string'}},
            'required': ['tool', 'arguments_json'], 'additionalProperties': False}},
        'answer': {'type': 'string'},
        'tables': {'type': 'array', 'items': {
            'type': 'object', 'properties': {
                'title': {'type': 'string'}, 'columns': {'type': 'array', 'items': {'type': 'string'}},
                'rows': {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'string'}}},
                'result': {'type': 'string'}},
            'required': ['title', 'columns', 'rows', 'result'], 'additionalProperties': False}},
        'follow_ups': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['status', 'note', 'tool_calls', 'answer', 'tables', 'follow_ups'],
    'additionalProperties': False,
}


class AssistantError(RuntimeError):
    """A question could not be answered: the reason is shown in the chat."""


# -- storage ----------------------------------------------------------------------------------------------------------

def ensure_tables(repository: Any) -> None:
    with repository.connection() as connection:
        connection.executescript(f'''
            CREATE TABLE IF NOT EXISTS {CONVERSATIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                pseudonyms_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_{CONVERSATIONS_TABLE}_user ON {CONVERSATIONS_TABLE}(username, updated_at);
            CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES {CONVERSATIONS_TABLE}(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL DEFAULT '',
                tables_json TEXT NOT NULL DEFAULT '[]',
                follow_ups_json TEXT NOT NULL DEFAULT '[]',
                trace_json TEXT NOT NULL DEFAULT '[]',
                sent_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'done',
                warning TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                feedback TEXT NOT NULL DEFAULT '',
                feedback_comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_{MESSAGES_TABLE}_conversation ON {MESSAGES_TABLE}(conversation_id, id);
            CREATE TABLE IF NOT EXISTS {GLOSSARY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL UNIQUE,
                term TEXT NOT NULL,
                meaning TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'suggested')),
                source TEXT NOT NULL DEFAULT 'manual',
                message_id INTEGER,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
        ''')


def _now() -> str:
    from src.modules.core.repository import local_now_iso
    return local_now_iso()


def _loads(value: Any, default: Any) -> Any:
    try:
        loaded = json.loads(value) if value else default
    except (TypeError, ValueError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


def list_conversations(repository: Any, username: str) -> list[dict[str, Any]]:
    ensure_tables(repository)
    with repository.connection() as connection:
        rows = connection.execute(
            f'SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS messages FROM {CONVERSATIONS_TABLE} c '
            f'LEFT JOIN {MESSAGES_TABLE} m ON m.conversation_id = c.id WHERE c.username = ? GROUP BY c.id '
            'ORDER BY c.updated_at DESC, c.id DESC', (username,)).fetchall()
    return [dict(row) for row in rows]


def get_conversation(repository: Any, conversation_id: int, username: str) -> dict[str, Any] | None:
    ensure_tables(repository)
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {CONVERSATIONS_TABLE} WHERE id = ? AND username = ?',
                                 (int(conversation_id), username)).fetchone()
    return dict(row) if row else None


def create_conversation(repository: Any, username: str, title: str = '') -> int:
    ensure_tables(repository)
    now = _now()
    with repository.connection() as connection:
        cursor = connection.execute(
            f'INSERT INTO {CONVERSATIONS_TABLE} (username, title, pseudonyms_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
            (username, title[:120], '{}', now, now))
        return int(cursor.lastrowid)


def rename_conversation(repository: Any, conversation_id: int, username: str, title: str) -> bool:
    with repository.connection() as connection:
        cursor = connection.execute(f'UPDATE {CONVERSATIONS_TABLE} SET title = ? WHERE id = ? AND username = ?',
                                    (title.strip()[:120], int(conversation_id), username))
        return cursor.rowcount > 0


def delete_conversation(repository: Any, conversation_id: int, username: str) -> int:
    """Delete a conversation of the user and its messages; the number of messages deleted (-1: not found)."""
    ensure_tables(repository)
    with repository.connection() as connection:
        if not connection.execute(f'SELECT 1 FROM {CONVERSATIONS_TABLE} WHERE id = ? AND username = ?',
                                  (int(conversation_id), username)).fetchone():
            return -1
        count = connection.execute(f'SELECT COUNT(*) FROM {MESSAGES_TABLE} WHERE conversation_id = ?',
                                   (int(conversation_id),)).fetchone()[0]
        connection.execute(f'DELETE FROM {MESSAGES_TABLE} WHERE conversation_id = ?', (int(conversation_id),))
        connection.execute(f'DELETE FROM {CONVERSATIONS_TABLE} WHERE id = ?', (int(conversation_id),))
    return int(count)


def _message(row: Any, include_sent: bool = False) -> dict[str, Any]:
    item = dict(row)
    message = {
        'id': item['id'], 'conversation_id': item['conversation_id'], 'role': item['role'], 'content': item['content'],
        'tables': _loads(item.get('tables_json'), []), 'follow_ups': _loads(item.get('follow_ups_json'), []),
        'trace': _loads(item.get('trace_json'), []), 'status': item['status'], 'warning': item['warning'],
        'engine': item['engine'], 'engine_label': writers.ENGINE_LABELS.get(item['engine'], item['engine']), 'model': item['model'],
        'input_tokens': item['input_tokens'], 'output_tokens': item['output_tokens'], 'duration_ms': item['duration_ms'],
        'feedback': item['feedback'], 'feedback_comment': item['feedback_comment'], 'created_at': item['created_at'],
    }
    if include_sent:
        message['sent'] = _loads(item.get('sent_json'), [])
    return message


def list_messages(repository: Any, conversation_id: int) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {MESSAGES_TABLE} WHERE conversation_id = ? ORDER BY id',
                                  (int(conversation_id),)).fetchall()
    return [_message(row) for row in rows]


def get_message(repository: Any, message_id: int, username: str, include_sent: bool = False) -> dict[str, Any] | None:
    ensure_tables(repository)
    with repository.connection() as connection:
        row = connection.execute(
            f'SELECT m.* FROM {MESSAGES_TABLE} m JOIN {CONVERSATIONS_TABLE} c ON c.id = m.conversation_id '
            'WHERE m.id = ? AND c.username = ?', (int(message_id), username)).fetchone()
    return _message(row, include_sent) if row else None


def add_message(repository: Any, conversation_id: int, role: str, content: str, **fields: Any) -> int:
    now = _now()
    values = {
        'tables_json': dumps(fields.get('tables') or []), 'follow_ups_json': dumps(fields.get('follow_ups') or []),
        'trace_json': dumps(fields.get('trace') or []), 'sent_json': dumps(fields.get('sent') or []),
        'status': fields.get('status') or 'done', 'warning': fields.get('warning') or '', 'engine': fields.get('engine') or '',
        'model': fields.get('model') or '', 'input_tokens': int(fields.get('input_tokens') or 0),
        'output_tokens': int(fields.get('output_tokens') or 0), 'duration_ms': int(fields.get('duration_ms') or 0),
    }
    with repository.connection() as connection:
        cursor = connection.execute(
            f'INSERT INTO {MESSAGES_TABLE} (conversation_id, role, content, {", ".join(values)}, created_at) '
            f'VALUES (?, ?, ?, {", ".join("?" for _ in values)}, ?)',
            (int(conversation_id), role, content, *values.values(), now))
        connection.execute(f'UPDATE {CONVERSATIONS_TABLE} SET updated_at = ? WHERE id = ?', (now, int(conversation_id)))
        return int(cursor.lastrowid)


def set_feedback(repository: Any, message_id: int, username: str, value: str, comment: str) -> dict[str, Any] | None:
    message = get_message(repository, message_id, username)
    if message is None or message['role'] != 'assistant':
        return None
    if value not in {'', 'up', 'down'}:
        raise ValueError('Feedback is up, down or none.')
    with repository.connection() as connection:
        connection.execute(f'UPDATE {MESSAGES_TABLE} SET feedback = ?, feedback_comment = ? WHERE id = ?',
                           (value, comment.strip()[:MAX_MEANING_LENGTH], int(message_id)))
    return get_message(repository, message_id, username)


def _save_pseudonyms(repository: Any, conversation_id: int, pseudonyms: Pseudonymizer) -> None:
    with repository.connection() as connection:
        connection.execute(f'UPDATE {CONVERSATIONS_TABLE} SET pseudonyms_json = ? WHERE id = ?',
                           (dumps(pseudonyms.state()), int(conversation_id)))


# -- glossary ---------------------------------------------------------------------------------------------------------

def list_glossary(repository: Any, status: str | None = None) -> list[dict[str, Any]]:
    ensure_tables(repository)
    query = f'SELECT * FROM {GLOSSARY_TABLE}'
    parameters: tuple[Any, ...] = ()
    if status:
        query += ' WHERE status = ?'
        parameters = (status,)
    with repository.connection() as connection:
        rows = connection.execute(query + ' ORDER BY status, term COLLATE NOCASE, id', parameters).fetchall()
    return [dict(row) for row in rows]


def _clean_entry(term: str, meaning: str) -> tuple[str, str]:
    term, meaning = re.sub(r'\s+', ' ', str(term or '')).strip(), str(meaning or '').strip()
    if not term or not meaning:
        raise ValueError('A glossary entry needs a term and its meaning.')
    if len(term) > MAX_TERM_LENGTH or len(meaning) > MAX_MEANING_LENGTH:
        raise ValueError(f'A term has at most {MAX_TERM_LENGTH} characters and a meaning at most {MAX_MEANING_LENGTH}.')
    return term, meaning


def save_glossary_entry(repository: Any, username: str, term: str, meaning: str, entry_id: int | None = None,
                        status: str = 'active', source: str = 'manual', message_id: int | None = None) -> dict[str, Any]:
    """Add an entry (or change one with ``entry_id``); a changed suggestion becomes an active entry."""
    ensure_tables(repository)
    term, meaning = _clean_entry(term, meaning)
    now = _now()
    with repository.connection() as connection:
        if entry_id:
            row = connection.execute(f'SELECT * FROM {GLOSSARY_TABLE} WHERE id = ?', (int(entry_id),)).fetchone()
            if row is None:
                raise ValueError('That glossary entry no longer exists.')
            connection.execute(f'UPDATE {GLOSSARY_TABLE} SET term = ?, meaning = ?, status = ?, updated_by = ?, updated_at = ? '
                               'WHERE id = ?', (term, meaning, status, username, now, int(entry_id)))
            return {**dict(row), 'term': term, 'meaning': meaning, 'status': status, 'previous_term': row['term'],
                    'previous_meaning': row['meaning'], 'previous_status': row['status']}
        cursor = connection.execute(
            f'INSERT INTO {GLOSSARY_TABLE} (uid, term, meaning, status, source, message_id, created_by, created_at, updated_by, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (uuid.uuid4().hex, term, meaning, status, source, message_id, username, now, username, now))
        return {'id': int(cursor.lastrowid), 'term': term, 'meaning': meaning, 'status': status, 'source': source}


def delete_glossary_entry(repository: Any, entry_id: int) -> dict[str, Any] | None:
    ensure_tables(repository)
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {GLOSSARY_TABLE} WHERE id = ?', (int(entry_id),)).fetchone()
        if row is None:
            return None
        connection.execute(f'DELETE FROM {GLOSSARY_TABLE} WHERE id = ?', (int(entry_id),))
    return dict(row)


def glossary_document(repository: Any) -> dict[str, Any]:
    """The active glossary entries, for exports, transfers and backups (suggestions stay in the workspace)."""
    return {'format': GLOSSARY_FORMAT, 'version': GLOSSARY_VERSION, 'items': [
        {'uid': row['uid'], 'term': row['term'], 'meaning': row['meaning'], 'created_by': row['created_by'],
         'created_at': row['created_at'], 'updated_by': row['updated_by'], 'updated_at': row['updated_at']}
        for row in list_glossary(repository, 'active')]}


def export_glossary(repository: Any) -> bytes:
    return json.dumps(glossary_document(repository), ensure_ascii=False, indent=2).encode('utf-8')


def import_glossary(repository: Any, content: bytes | str | dict[str, Any], username: str,
                    creator: Callable[[Any, Any], str] | None = None, summary: list[str] | None = None) -> dict[str, int]:
    """Add the entries of a glossary document and replace those it has (by uid, then by term), never deleting one.

    A new entry belongs to ``creator(package creator, None)`` (Import and Transfers: its creator when that user is active
    here, else the importing user), or to its creator in the document; ``summary`` gets the terms renamed by it."""
    document = content if isinstance(content, dict) else json.loads(content.decode('utf-8') if isinstance(content, bytes) else content)
    if not isinstance(document, dict) or document.get('format') != GLOSSARY_FORMAT:
        raise ValueError('This file is not an AI Assistant Glossary of DriveTest Analyzer.')
    ensure_tables(repository)
    added = replaced = 0
    existing = list_glossary(repository)
    by_uid = {row['uid']: row for row in existing}
    by_term = {row['term'].casefold(): row for row in existing}
    now = _now()
    with repository.connection() as connection:
        for item in document.get('items') or []:
            if not isinstance(item, dict):
                continue
            try:
                term, meaning = _clean_entry(item.get('term'), item.get('meaning'))
            except ValueError:
                continue
            owner = str(item.get('created_by') or '')
            owner = creator(owner, None) if creator else (owner if owner and owner != 'system' else username)
            match = by_uid.get(str(item.get('uid') or '')) or by_term.get(term.casefold())
            if match:
                connection.execute(
                    f'UPDATE {GLOSSARY_TABLE} SET term = ?, meaning = ?, status = ?, updated_by = ?, updated_at = ? WHERE id = ?',
                    (term, meaning, 'active', username, now, match['id']))
                if summary is not None and match['term'] != term:
                    summary.append(f'{match["term"]} → {term}')
                replaced += 1
            else:
                connection.execute(
                    f'INSERT INTO {GLOSSARY_TABLE} (uid, term, meaning, status, source, created_by, created_at, updated_by, updated_at) '
                    "VALUES (?, ?, ?, 'active', 'import', ?, ?, ?, ?)",
                    (str(item.get('uid') or uuid.uuid4().hex), term, meaning, owner or username, str(item.get('created_at') or now),
                     username, now))
                added += 1
    return {'added': added, 'replaced': replaced}


# -- engines ----------------------------------------------------------------------------------------------------------

class Engine(Protocol):
    id: str
    label: str

    def step(self, system: str, transcript: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
        """The next step (a document of STEP_SCHEMA) for the transcript, and the model and tokens it took."""


class ClaudeEngine:
    id, label = writers.ENGINE_CLAUDE, writers.ENGINE_LABELS[writers.ENGINE_CLAUDE]

    def __init__(self, settings: dict[str, Any], api_key: str, source: str) -> None:
        self.settings, self.api_key, self.source = settings, api_key, source

    def step(self, system: str, transcript: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
        messages: list[dict[str, str]] = []
        for turn in transcript:
            if messages and messages[-1]['role'] == turn['role']:
                messages[-1] = {'role': turn['role'], 'content': messages[-1]['content'] + '\n\n' + turn['content']}
            else:
                messages.append({'role': turn['role'], 'content': turn['content']})
        return writers.run_claude(system, messages, STEP_SCHEMA, self.settings, self.api_key, self.source,
                                  purpose='ask the AI Assistant with Claude', refused='answer this question')


class KiroCliEngine:
    id, label = writers.ENGINE_KIRO_CLI, writers.ENGINE_LABELS[writers.ENGINE_KIRO_CLI]

    def __init__(self, settings: dict[str, Any], cli: Path | None, api_key: str, config_dir: Path, source: str) -> None:
        self.settings, self.cli, self.api_key, self.config_dir, self.source = settings, cli, api_key, config_dir, source

    def step(self, system: str, transcript: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
        parts = [system, '# Conversation']
        for turn in transcript:
            parts.append(('## User\n' if turn['role'] == 'user' else '## Assistant (your earlier JSON)\n') + turn['content'])
        parts.append('Reply now with the JSON object of your next step only.')
        output = writers.run_kiro_cli('\n\n'.join(parts), self.settings, self.cli, self.api_key, self.config_dir,
                                      self.source, purpose='ask the AI Assistant with Kiro')
        return writers._json_reply(output, key='status', what='the next step'), {'model': str(self.settings.get('kiro_model') or '')}


# Engines a later version adds (an internal model of the organisation): id -> (label, factory(settings, core, username)).
EXTRA_ENGINES: dict[str, tuple[str, Callable[[dict[str, Any], Any, str], Engine]]] = {}


def available_engines(repository: Any) -> dict[str, Any]:
    """The engines a user can ask with: the server engines Super Admin enabled (and any registered one), the default
    first."""
    settings = writers.load_settings(repository)
    engines = [engine for engine in writers.SERVER_ENGINES if engine in settings['enabled']]
    labels = {**writers.ENGINE_LABELS, **{key: value[0] for key, value in EXTRA_ENGINES.items()}}
    engines += list(EXTRA_ENGINES)
    default = settings['default'] if settings['default'] in engines else (engines[0] if engines else '')
    return {'engines': [{'id': engine, 'label': labels[engine]} for engine in engines], 'default': default}


def build_engine(engine_id: str, core: Any, username: str) -> Engine:
    settings = writers.load_settings(core.repository)
    if engine_id in EXTRA_ENGINES:
        return EXTRA_ENGINES[engine_id][1](settings, core, username)
    if engine_id not in writers.SERVER_ENGINES or engine_id not in settings['enabled']:
        raise AssistantError('No AI engine is enabled for the AI Assistant: a super-admin enables Kiro CLI or Claude '
                             'in Super Admin → AI Comment Writers.')
    api_key, source = writers.writer_key(settings, core.application_config_dir, engine_id, username)
    if engine_id == writers.ENGINE_CLAUDE:
        return ClaudeEngine(settings, api_key, source)
    return KiroCliEngine(settings, writers.kiro_cli_path(core.repository), api_key, core.application_config_dir, source)


# -- figures ----------------------------------------------------------------------------------------------------------

_NUMBER = re.compile(r'(?<![\w.,])[−-]?\d[\d.,  ]*\d(?![\w])|(?<![\w.,])[−-]?\d(?![\w])')


def _numbers_in(document: Any, found: set[float]) -> None:
    if isinstance(document, bool) or document is None:
        return
    if isinstance(document, (int, float)):
        found.add(abs(float(document)))
        return
    if isinstance(document, str):
        for token in _NUMBER.findall(CODE.sub(' ', document)):
            found.update(_readings(token))
        return
    if isinstance(document, dict):
        for value in document.values():
            _numbers_in(value, found)
    elif isinstance(document, (list, tuple)):
        for value in document:
            _numbers_in(value, found)


def _readings(token: str) -> set[float]:
    """Every value a written figure can stand for: 1,234.5 and 1.234,5 alike, 921,81 as 921.81."""
    text = re.sub(r'[  ]', '', token.replace('−', '-')).lstrip('-')
    readings = set()
    for thousands, decimal in ((',', '.'), ('.', ','), ('', '.'), ('', ',')):
        candidate = text.replace(thousands, '') if thousands else text
        if decimal == ',':
            candidate = candidate.replace(',', '.')
        try:
            readings.add(abs(float(candidate)))
        except ValueError:
            continue
    return readings


def _decimals(token: str) -> int:
    match = re.search(r'[.,](\d+)$', token.strip())
    return len(match.group(1)) if match and len(match.group(1)) != 3 else 0


def untraced_figures(text: str, tables: list[dict[str, Any]], allowed: set[float]) -> list[str]:
    """The figures of an answer that come from no tool result (nor from the question): small counts, years and the
    figures of the results written with fewer decimals, or as percentages of a share, are accepted."""
    rounded = {(digits, round(value, digits)) for value in allowed for digits in range(0, 5)}
    rounded |= {(digits, round(value * 100, digits)) for value in allowed if value <= 1 for digits in range(0, 3)}
    problems = []
    cells = [text, *(str(cell) for table in tables for row in table.get('rows') or [] for cell in row),
             *(str(table.get('title') or '') for table in tables)]
    for cell in cells:
        for token in _NUMBER.findall(CODE.sub(' ', cell)):
            values = _readings(token)
            if not values:
                continue
            if any(value <= 12 and value == int(value) for value in values) or any(1990 <= value <= 2100 for value in values):
                continue
            digits = _decimals(token)
            if any((digits, round(value, digits)) in rounded for value in values):
                continue
            problems.append(token.strip())
    return list(dict.fromkeys(problems))


# -- the conversation with the engine --------------------------------------------------------------------------------

def _fit(document: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> Any:
    """A tool result within the size the engine receives: its longest lists are cut, with a note."""
    if result_size(document) <= limit or not isinstance(document, dict):
        return document
    fitted = dict(document)
    while result_size(fitted) > limit:
        lists = [(key, value) for key, value in fitted.items() if isinstance(value, list) and len(value) > 1]
        if not lists:
            return {'note': 'The result was too large to send; ask for less (filter, split less or use only).'}
        key, value = max(lists, key=lambda item: result_size(item[1]))
        fitted[key] = value[:max(1, len(value) // 2)]
        fitted['truncated'] = f'Lists were cut to fit; ask for less to see everything ({key} first).'
    return fitted


def _history(repository: Any, conversation_id: int, pseudonyms: Pseudonymizer, before_id: int) -> str:
    """The earlier questions and answers of the conversation, masked and short."""
    turns = [message for message in list_messages(repository, conversation_id) if message['id'] < before_id
             and message['status'] == 'done'][-2 * HISTORY_EXCHANGES:]
    lines = []
    for message in turns:
        if message['role'] == 'user':
            lines.append(f'User: {pseudonyms.mask_text(message["content"])[:1500]}')
        else:
            tables = '; '.join(f'{table.get("title")}: {dumps(table.get("rows"))[:600]}' for table in message['tables'])
            lines.append(f'Assistant: {pseudonyms.mask_text(message["content"])[:1500]}'
                         + (f' [tables: {pseudonyms.mask_text(tables)}]' if tables else ''))
    return '\n'.join(lines)


def _glossary_text(repository: Any) -> str:
    return '\n'.join(f'- {row["term"]}: {row["meaning"]}' for row in list_glossary(repository, 'active'))


def _trim_transcript(transcript: list[dict[str, str]]) -> None:
    """Keep the prompt within what an engine takes: the oldest tool results go first."""
    while sum(len(turn['content']) for turn in transcript) > MAX_PROMPT_CHARS:
        index = next((position for position, turn in enumerate(transcript[1:-1], start=1)
                      if turn['role'] == 'user' and turn['content'].startswith('Results of the tools')
                      and not turn['content'].endswith('[removed to keep the prompt short]')), None)
        if index is None:
            break
        transcript[index] = {'role': 'user', 'content': 'Results of the tools: [removed to keep the prompt short]'}


def answer_question(*, engine: Engine, repository: Any, workspace_name: str, username: str, conversation_id: int,
                    question: str, question_id: int, progress: Callable[[str], None] = lambda _message: None,
                    cancelled: Callable[[], bool] = lambda: False,
                    services: dict[str, Callable[..., Any]] | None = None) -> dict[str, Any]:
    """Answer a question with the engine and the tools; the answer with the real names, its tables, follow-ups, the
    trace of the tools it used and what was sent to the engine. ``services``: what the modules give the tools
    (module_services)."""
    context = ToolContext(repository=repository, workspace_name=workspace_name, username=username,
                          progress=progress, cancelled=cancelled, services=dict(services or {}))
    try:
        return _answer(engine, context, conversation_id, question, question_id)
    finally:
        context.close()


def _answer(engine: Engine, context: ToolContext, conversation_id: int, question: str, question_id: int) -> dict[str, Any]:
    repository, username, progress, cancelled = context.repository, context.username, context.progress, context.cancelled
    started = time.monotonic()
    conversation = get_conversation(repository, conversation_id, username) or {}
    pseudonyms = workspace_pseudonymizer(repository, context.workspace_name, _loads(conversation.get('pseudonyms_json'), {}))
    progress('Reading the workspace')
    overview = workspace_overview(context)
    glossary = _glossary_text(repository)
    history = _history(repository, conversation_id, pseudonyms, question_id)
    opening = '\n\n'.join(part for part in (
        f'Today is {date.today().isoformat()}.',
        'Workspace context (JSON):\n' + dumps(pseudonyms.mask(overview)),
        'Workspace glossary:\n' + (pseudonyms.mask_text(glossary) or '(empty)'),
        'Earlier in this conversation:\n' + history if history else '',
        'Question:\n' + pseudonyms.mask_text(question),
    ) if part)
    transcript = [{'role': 'user', 'content': opening}]
    sent: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    allowed: set[float] = set()
    for source in (overview, question, glossary):
        _numbers_in(source, allowed)
    tokens = {'input_tokens': 0, 'output_tokens': 0}
    model = ''
    repaired = False
    final: dict[str, Any] | None = None
    for step in range(MAX_STEPS + 1):
        if cancelled():
            raise AssistantError('Stopped.')
        if step == MAX_STEPS:
            transcript.append({'role': 'user', 'content': 'You have used every step: answer now with what the tools gave.'})
        _trim_transcript(transcript)
        leaks = pseudonyms.leaks(transcript[-1]['content'])
        if leaks:
            # Never sent: a name found here would be a fault of the masking.
            raise AssistantError('The question could not be sent without naming the workspace data; nothing was sent.')
        sent.append({'step': step + 1, 'sent': transcript[-1]['content']})
        try:
            document, details = engine.step(SYSTEM_PROMPT, transcript)
        except writers.WriterError as exc:
            raise AssistantError(str(exc)) from exc
        model = details.get('model') or model
        for key in tokens:
            tokens[key] += int(details.get(key) or 0)
        if not isinstance(document, dict):
            raise AssistantError(f'{engine.label} did not reply with the JSON of a step.')
        sent[-1]['received'] = dumps(document)
        transcript.append({'role': 'assistant', 'content': dumps(document)})
        calls = [call for call in document.get('tool_calls') or [] if isinstance(call, dict)]
        if document.get('status') == 'tools' and calls and step < MAX_STEPS:
            if document.get('note'):
                progress(pseudonyms.unmask_text(document['note']))
            results = []
            for call in calls[:MAX_TOOL_CALLS_PER_STEP]:
                if cancelled():
                    raise AssistantError('Stopped.')
                name = str(call.get('tool') or '')
                try:
                    masked_arguments = json.loads(call.get('arguments_json') or '{}')
                except ValueError:
                    masked_arguments = None
                arguments = pseudonyms.unmask(masked_arguments) if isinstance(masked_arguments, dict) else None
                began = time.monotonic()
                entry: dict[str, Any] = {'tool': name, 'arguments': arguments if arguments is not None else call.get('arguments_json')}
                try:
                    if arguments is None:
                        raise ToolError('arguments_json is not a JSON object.')
                    result = run_tool(context, name, arguments)
                    _numbers_in(result, allowed)
                    masked = _fit(pseudonyms.mask(result))
                    results.append({'tool': name, 'result': masked})
                    entry['summary'] = _summary(name, result)
                except ToolError as exc:
                    results.append({'tool': name, 'error': pseudonyms.mask_text(str(exc))})
                    entry['error'] = str(exc)
                entry['duration_ms'] = round((time.monotonic() - began) * 1000)
                trace.append(entry)
            transcript.append({'role': 'user', 'content': 'Results of the tools (JSON):\n' + dumps(results)})
            continue
        answer = str(document.get('answer') or '').strip()
        tables = _tables(document.get('tables'), context.cache.get('query_results') or {})
        if not answer and not tables:
            if step >= MAX_STEPS:
                raise AssistantError(f'{engine.label} gave no answer.')
            transcript.append({'role': 'user', 'content': 'Your answer is empty: write it now in "answer".'})
            continue
        # The rows of a query result come from the tool itself: only the tables the engine wrote are checked.
        problems = untraced_figures(answer, [table for table in tables if not table.get('result')], allowed)
        if problems and not repaired and step < MAX_STEPS:
            repaired = True
            progress('Checking the figures of the answer')
            transcript.append({'role': 'user', 'content': (
                'These figures of your answer appear in no tool result: ' + ', '.join(problems[:15])
                + '. Copy every figure from the results (call calculate for differences, shares and ratios) or leave it '
                  'out, and reply with the whole answer again.')})
            continue
        final = {'answer': answer, 'tables': tables,
                 'follow_ups': [str(item).strip()[:300] for item in document.get('follow_ups') or [] if str(item).strip()][:3],
                 'problems': problems}
        break
    if final is None:
        raise AssistantError(f'{engine.label} gave no answer.')
    _save_pseudonyms(repository, conversation_id, pseudonyms)
    warning = (f'{len(final["problems"])} figure(s) of this answer could not be traced to the results of the tools: '
               + ', '.join(final['problems'][:8]) + '.') if final['problems'] else ''
    return {
        'content': pseudonyms.unmask_text(final['answer']), 'tables': [_shown_table(table, pseudonyms) for table in final['tables']],
        'follow_ups': pseudonyms.unmask(final['follow_ups']), 'trace': trace, 'warning': warning,
        'sent': sent, 'legend': pseudonyms.legend(), 'engine': engine.id, 'model': model,
        'duration_ms': round((time.monotonic() - started) * 1000), 'untraced': final['problems'], **tokens,
    }


MAX_RESULT_TABLE_COLUMNS = 40


def _cell(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float):
        return f'{value:g}' if abs(value) >= 1e15 or value == int(value) else str(round(value, 4))
    return str(value)


def _tables(value: Any, results: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The tables of an answer: those the engine wrote, and those that show a query result (``result``: its id), whose
    columns and rows the tool fills from the result itself (with the real values, up to 5,000 rows)."""
    tables = []
    for table in value if isinstance(value, list) else []:
        if not isinstance(table, dict):
            continue
        title = str(table.get('title') or '')[:200]
        result = (results or {}).get(str(table.get('result') or '').strip().upper())
        if result is not None:
            columns = [str(column) for column in result['columns']][:MAX_RESULT_TABLE_COLUMNS]
            tables.append({'title': title, 'columns': columns, 'result': str(table['result']).strip().upper(),
                           'rows': [[_cell(cell) for cell in row[:len(columns)]] for row in result['rows']],
                           'truncated': bool(result.get('more'))})
            continue
        columns = [str(column) for column in table.get('columns') or []][:12]
        rows = [[str(cell) for cell in row][:len(columns) or 12] for row in table.get('rows') or [] if isinstance(row, list)][:200]
        if columns or rows:
            tables.append({'title': title, 'columns': columns, 'rows': rows})
    return tables[:6]


def _shown_table(table: dict[str, Any], pseudonyms: Pseudonymizer) -> dict[str, Any]:
    """A table with the real names: a query result already holds them (only its title has codes)."""
    if table.get('result'):
        return {**table, 'title': pseudonyms.unmask_text(table['title'])}
    return pseudonyms.unmask(table)


def _summary(name: str, result: dict[str, Any]) -> str:
    """One line of the trace: what a tool gave."""
    if name == 'scoring' or ('groups' in result and 'split_by' in result):
        return (f'{result.get("group_count", len(result.get("groups") or []))} groups of {", ".join(result.get("campaigns") or [])} '
                f'({result.get("nr_mode")}, split by {", ".join(result.get("split_by") or [])}; {result.get("methodology") or "default methodology"}; '
                f'{result.get("cdrs", 0)} CDRs, from {result.get("calculated_from")})')
    if name == 'nq_calls':
        return f'{result.get("total_calls", 0)} calls in {result.get("groups", 0)} groups'
    if name == 'query':
        return (f'{result.get("result_id")}: {result.get("row_count", 0)} rows'
                f'{" (more not kept)" if result.get("note", "").startswith("The query gives more") else ""} of '
                f'{", ".join(str(column) for column in (result.get("columns") or [])[:8])}')
    if name == 'table_columns':
        return (f'{result.get("column_count", 0)} columns of {result["table"]}' if result.get('table') else
                f'{len(result.get("tables") or [])} tables')
    if name == 'network_insights':
        selection = result.get('selection') or {}
        return (f'{", ".join(selection.get("campaigns") or [])} ({selection.get("nr_mode")}, {result.get("technology")}, '
                f'by {result.get("group_label")}; {result.get("cdrs", 0)} CDRs)')
    if name == 'ppt_designs':
        return (f'{result.get("name")}: {len(result.get("slides") or [])} slides' if result.get('design') else
                f'{len(result.get("designs") or [])} Designs')
    if name == 'ppt_design_charts':
        slides = [item for item in result.get('slides') or [] if isinstance(item, dict)]
        return (f'{result.get("name")}: slides {", ".join(str(item.get("slide")) for item in slides)} '
                f'({sum(len(item.get("charts") or []) for item in slides)} charts)')
    if name == 'workspace_overview':
        return 'Campaigns, operators, vendors, areas, methodologies and Saved Filters of the workspace'
    if name == 'list_values':
        return f'{result.get("count", 0)} values of {result.get("field")}'
    if name == 'saved_filters':
        return f'Saved Filter {result.get("id")}: {result.get("name")}' if 'id' in result else \
            f'{len(result.get("saved_filters") or [])} Saved Filters'
    if name == 'help_search':
        return '; '.join(f'{item["chapter"]} › {item["section"]}' for item in result.get('passages') or [])
    if name == 'calculate':
        return '; '.join(f'{item["expression"]} = {item.get("result", item.get("error"))}' for item in result.get('results') or [])
    return ''


# -- background questions ---------------------------------------------------------------------------------------------

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
JOB_KEEP_SECONDS = 3600


def _prune_jobs() -> None:
    now = time.monotonic()
    for job_id in [job_id for job_id, job in _JOBS.items()
                   if job['status'] != 'running' and now - job.get('finished', now) > JOB_KEEP_SECONDS]:
        _JOBS.pop(job_id, None)


def running_job(username: str, database: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        return next((job for job in _JOBS.values() if job['username'] == username and job['database'] == database
                     and job['status'] == 'running'), None)


def job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job.get(key) for key in ('id', 'status', 'steps', 'conversation_id', 'message_id', 'error', 'engine')}


def module_services(core: Any, user: Any, repository: Any, cancelled: Callable[[], bool],
                    progress: Callable[[str], None]) -> dict[str, Callable[..., Any]]:
    """What the modules the user sees give the tools: the analyses of Network Insights and the Designs of PPT Designer
    with the facts of their charts."""
    services: dict[str, Callable[..., Any]] = {}
    if user is None:
        return services
    sees = getattr(core, 'user_has_feature', lambda _user, _feature: True)
    workspace = Path(repository.db_path).resolve()

    def same_workspace() -> None:
        # Network Insights reads the active workspace: the question must still be about it.
        if not core.active_workspace or Path(core.repository.db_path).resolve() != workspace:
            raise ValueError('Another workspace was opened while answering: open this workspace again and ask again.')

    analysis = getattr(core, 'network_insights_analysis', None)
    if analysis is not None and sees(user, 'network-insights'):
        def network_insights(selection: dict[str, Any]) -> dict[str, Any]:
            same_workspace()
            return analysis(selection)
        services['network_insights'] = network_insights
    designs = getattr(core, 'design_reporting', None)
    if designs is not None and hasattr(designs, 'chart_facts') and sees(user, 'ppt-designer'):
        services['design_outline'] = lambda design=None: designs.outline(repository, design)
        services['design_charts'] = lambda design, slides: designs.chart_facts(
            repository, design, user, slides, cancelled=cancelled, progress=lambda _percent, detail: progress(str(detail)))
    return services


def start_question(core: Any, *, repository_factory: Callable[[], Any], workspace: Any, username: str, conversation_id: int,
                   question: str, question_id: int, engine: Engine, user: Any = None) -> dict[str, Any]:
    """Answer a question in the background: the page follows its steps and reads its answer when done."""
    job = {'id': uuid.uuid4().hex, 'username': username, 'database': str(workspace.database_path), 'status': 'running',
           'steps': [], 'conversation_id': conversation_id, 'message_id': None, 'error': '', 'engine': engine.id,
           'cancel': threading.Event(), 'started': time.monotonic()}
    with _JOBS_LOCK:
        _prune_jobs()
        _JOBS[job['id']] = job

    def progress(message: str) -> None:
        text = str(message or '').strip()
        if text and (not job['steps'] or job['steps'][-1] != text):
            job['steps'].append(text[:300])

    def work() -> None:
        from src.modules.core.repository import APP_EVENT_ORIGIN
        APP_EVENT_ORIGIN.set(lambda: 'module:assistant')
        repository = repository_factory()
        details: dict[str, Any] = {'conversation_id': conversation_id, 'question_id': question_id,
                                   'engine': writers.ENGINE_LABELS.get(engine.id, engine.id)}
        try:
            services = module_services(core, user, repository, job['cancel'].is_set, progress)
            answer = answer_question(engine=engine, repository=repository, workspace_name=workspace.name, username=username,
                                     conversation_id=conversation_id, question=question, question_id=question_id,
                                     progress=progress, cancelled=job['cancel'].is_set, services=services)
            message_id = add_message(repository, conversation_id, 'assistant', answer['content'],
                                     **{key: value for key, value in answer.items() if key != 'content'})
            job.update(status='done', message_id=message_id)
            repository.try_add_log(username, 'assistant_answered', json.dumps({
                **details, 'message_id': message_id, 'model': answer['model'], 'duration_ms': answer['duration_ms'],
                'steps': len(answer['sent']), 'tools': [{'tool': entry['tool'], 'error': entry.get('error', ''),
                                                          'duration_ms': entry['duration_ms']} for entry in answer['trace']],
                'input_tokens': answer['input_tokens'], 'output_tokens': answer['output_tokens'],
                'untraced_figures': answer['untraced'], 'sent_characters': sum(len(item['sent']) for item in answer['sent']),
            }, ensure_ascii=False), timeout_seconds=5)
        except Exception as exc:  # noqa: BLE001 - every failure is told in the chat and recorded
            stopped = job['cancel'].is_set()
            reason = 'Stopped before the answer.' if stopped else (str(exc) if isinstance(exc, AssistantError) else
                                                                   f'The question could not be answered: {exc}')
            # The job ends whatever happens next: one left as running would refuse the next questions of the user.
            job.update(status='stopped' if stopped else 'failed', error=reason)
            message_id = add_message(repository, conversation_id, 'assistant', '', status='stopped' if stopped else 'failed',
                                     warning=reason, engine=engine.id)
            job.update(message_id=message_id)
            repository.try_add_log(username, 'assistant_stopped' if stopped else 'assistant_failed', json.dumps({
                **details, 'message_id': message_id, 'error': reason, 'error_type': type(exc).__name__,
                'steps': list(job['steps']),
            }, ensure_ascii=False), timeout_seconds=5)
        finally:
            job['finished'] = time.monotonic()

    thread = threading.Thread(target=contextvars.Context().run, args=(work,), name=f'assistant-{job["id"][:8]}', daemon=True)
    thread.start()
    job['thread'] = thread
    return job


def get_job(job_id: str, username: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        job = _JOBS.get(str(job_id))
    return job if job and job['username'] == username else None


# -- routes -----------------------------------------------------------------------------------------------------------

def glossary_context(core: Any, request: Any) -> dict[str, Any]:
    """What the AI Assistant Glossary card of Workspace Configuration shows."""
    entries = list_glossary(core.repository) if core.active_workspace else []
    return {
        'assistant_glossary': [entry for entry in entries if entry['status'] == 'active'],
        'assistant_glossary_suggestions': [entry for entry in entries if entry['status'] == 'suggested'],
        'assistant_glossary_notice': request.query_params.get('assistant_glossary_notice') or None,
        'assistant_glossary_error': request.query_params.get('assistant_glossary_error') or None,
    }


class AskRequest(BaseModel):
    question: str
    conversation_id: int | None = None
    engine: str = ''


class TitleRequest(BaseModel):
    title: str = ''


class FeedbackRequest(BaseModel):
    value: str = ''
    comment: str = ''


class SuggestionRequest(BaseModel):
    term: str
    meaning: str


def install_assistant_routes(core: Any) -> None:
    """Register the AI Assistant page, its JSON API and the Glossary forms of Workspace Configuration."""
    # The FastAPI names are imported with the module: its annotations are strings (``from __future__ import annotations``)
    # that FastAPI resolves from the module globals.
    from urllib.parse import urlencode

    app = core.app

    def assistant_user(user=Depends(core.current_user)):
        if not core.active_workspace:
            raise HTTPException(400, 'Open a workspace before using the AI Assistant.')
        if user.role != 'super-admin' and not core.repository.user_has_workspace_access(user.username, core.active_workspace.id):
            raise HTTPException(403, 'You do not have access to the active workspace.')
        return user

    def bound_repository():
        return core.Repository(Path(core.repository.db_path), core.repository.global_db_path)

    def log(repository: Any, user: Any, action: str, details: dict[str, Any]) -> None:
        repository.try_add_log(user.username, action, json.dumps(details, ensure_ascii=False))

    def engines_view(username: str) -> dict[str, Any]:
        choices = available_engines(core.repository)
        settings = writers.load_settings(core.repository)
        missing = [item['label'] for item in choices['engines'] if item['id'] in writers.SERVER_ENGINES
                   and writers.key_source(settings, item['id']) == 'user'
                   and not writers.user_key(core.application_config_dir, item['id'], username)]
        return {**choices, 'missing_user_keys': missing}

    @app.get('/assistant', response_class=HTMLResponse)
    def assistant_page(request: Request, user=Depends(assistant_user)):
        task_repository = bound_repository()
        return core.render_template(request, 'assistant.html', {
            'user': user,
            'assistant_config': {
                'workspace': core.active_workspace.name,
                'conversations': list_conversations(task_repository, user.username),
                'engines': engines_view(user.username),
                'examples': list(EXAMPLE_QUESTIONS),
                'max_question_length': MAX_QUESTION_LENGTH,
                'can_edit_glossary': user.role in {'user-editor', 'admin', 'super-admin'},
                'glossary_count': len(list_glossary(task_repository, 'active')),
            },
        })

    @app.get('/api/assistant/conversations')
    def assistant_conversations(user=Depends(assistant_user)):
        return {'conversations': list_conversations(bound_repository(), user.username)}

    @app.get('/api/assistant/conversations/{conversation_id}')
    def assistant_conversation(conversation_id: int, user=Depends(assistant_user)):
        task_repository = bound_repository()
        conversation = get_conversation(task_repository, conversation_id, user.username)
        if conversation is None:
            raise HTTPException(404, 'Conversation not found.')
        job = running_job(user.username, str(core.active_workspace.database_path))
        return {'conversation': {key: conversation[key] for key in ('id', 'title', 'created_at', 'updated_at')},
                'messages': list_messages(task_repository, conversation_id),
                'job': job_view(job) if job and job['conversation_id'] == conversation_id else None}

    @app.post('/api/assistant/conversations/{conversation_id}/rename')
    def assistant_rename(conversation_id: int, payload: TitleRequest, user=Depends(assistant_user)):
        task_repository = bound_repository()
        title = payload.title.strip()
        if not title:
            raise HTTPException(400, 'Give the conversation a name.')
        before = get_conversation(task_repository, conversation_id, user.username)
        if before is None or not rename_conversation(task_repository, conversation_id, user.username, title):
            raise HTTPException(404, 'Conversation not found.')
        log(task_repository, user, 'assistant_conversation_renamed',
            {'conversation_id': conversation_id, 'from': before['title'], 'to': title[:120]})
        return {'ok': True, 'title': title[:120]}

    @app.delete('/api/assistant/conversations/{conversation_id}')
    def assistant_delete(conversation_id: int, user=Depends(assistant_user)):
        task_repository = bound_repository()
        job = running_job(user.username, str(core.active_workspace.database_path))
        if job and job['conversation_id'] == conversation_id:
            raise HTTPException(409, 'Stop the question being answered before deleting its conversation.')
        conversation = get_conversation(task_repository, conversation_id, user.username)
        deleted = delete_conversation(task_repository, conversation_id, user.username)
        if deleted < 0:
            raise HTTPException(404, 'Conversation not found.')
        log(task_repository, user, 'assistant_conversation_deleted',
            {'conversation_id': conversation_id, 'title': (conversation or {}).get('title', ''), 'messages': deleted})
        return {'ok': True}

    @app.post('/api/assistant/ask')
    def assistant_ask(payload: AskRequest, user=Depends(assistant_user)):
        question = payload.question.strip()
        if not question:
            raise HTTPException(400, 'Write a question.')
        if len(question) > MAX_QUESTION_LENGTH:
            raise HTTPException(400, f'A question has at most {MAX_QUESTION_LENGTH} characters.')
        workspace = core.active_workspace
        if running_job(user.username, str(workspace.database_path)):
            raise HTTPException(409, 'Wait for the answer to your previous question, or stop it.')
        choices = available_engines(core.repository)
        engine_id = payload.engine if payload.engine in {item['id'] for item in choices['engines']} else choices['default']
        try:
            engine = build_engine(engine_id, core, user.username)
        except AssistantError as exc:
            raise HTTPException(400, str(exc)) from exc
        task_repository = bound_repository()
        conversation_id = payload.conversation_id
        created = False
        if conversation_id is None or get_conversation(task_repository, conversation_id, user.username) is None:
            conversation_id = create_conversation(task_repository, user.username, re.sub(r'\s+', ' ', question)[:80])
            created = True
        question_id = add_message(task_repository, conversation_id, 'user', question, engine=engine.id)
        log(task_repository, user, 'assistant_question', {
            'conversation_id': conversation_id, 'new_conversation': created, 'question_id': question_id,
            'engine': engine.label, 'question': question[:500], 'characters': len(question)})
        workspace_path = Path(workspace.database_path)
        job = start_question(core, repository_factory=lambda: core.Repository(workspace_path, core.repository.global_db_path),
                             workspace=workspace, username=user.username, conversation_id=conversation_id,
                             question=question, question_id=question_id, engine=engine, user=user)
        return {'job': job_view(job), 'conversation_id': conversation_id, 'question_id': question_id,
                'conversations': list_conversations(task_repository, user.username)}

    @app.get('/api/assistant/jobs/{job_id}')
    def assistant_job(job_id: str, user=Depends(core.current_user)):
        job = get_job(job_id, user.username)
        if job is None:
            raise HTTPException(404, 'This question is no longer being followed: open its conversation again.')
        view = job_view(job)
        if job['status'] != 'running' and job.get('message_id'):
            view['message'] = get_message(core.Repository(Path(job['database']), core.repository.global_db_path),
                                          job['message_id'], user.username)
        return view

    @app.post('/api/assistant/jobs/{job_id}/stop')
    def assistant_stop(job_id: str, user=Depends(core.current_user)):
        job = get_job(job_id, user.username)
        if job is None:
            raise HTTPException(404, 'This question is no longer being answered.')
        if job['status'] == 'running':
            job['cancel'].set()
            log(core.Repository(Path(job['database']), core.repository.global_db_path), user, 'assistant_stop_requested',
                {'conversation_id': job['conversation_id'], 'steps': list(job['steps'])})
        return job_view(job)

    @app.get('/api/assistant/messages/{message_id}/sent')
    def assistant_sent(message_id: int, user=Depends(assistant_user)):
        """What was sent to the engine for an answer, and the real names of its codes (only shown on this page)."""
        task_repository = bound_repository()
        message = get_message(task_repository, message_id, user.username, include_sent=True)
        if message is None:
            raise HTTPException(404, 'Message not found.')
        conversation = get_conversation(task_repository, message['conversation_id'], user.username) or {}
        legend = Pseudonymizer(_loads(conversation.get('pseudonyms_json'), {}))
        used = set(CODE.findall(json.dumps(message.get('sent') or [])))
        return {'sent': message.get('sent') or [], 'system_prompt': SYSTEM_PROMPT,
                'legend': [item for item in legend.legend() if tuple(CODE.fullmatch(item['code']).groups()) in used]}

    @app.post('/api/assistant/messages/{message_id}/feedback')
    def assistant_feedback(message_id: int, payload: FeedbackRequest, user=Depends(assistant_user)):
        task_repository = bound_repository()
        try:
            message = set_feedback(task_repository, message_id, user.username, payload.value, payload.comment)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if message is None:
            raise HTTPException(404, 'Answer not found.')
        log(task_repository, user, 'assistant_feedback', {'message_id': message_id, 'conversation_id': message['conversation_id'],
                                                          'feedback': payload.value or 'none', 'comment': payload.comment[:500]})
        return {'message': message}

    @app.post('/api/assistant/messages/{message_id}/suggest')
    def assistant_suggest(message_id: int, payload: SuggestionRequest, user=Depends(assistant_user)):
        """Suggest a glossary entry from an answer: an editor of Workspace Configuration accepts or dismisses it."""
        task_repository = bound_repository()
        message = get_message(task_repository, message_id, user.username)
        if message is None:
            raise HTTPException(404, 'Answer not found.')
        try:
            entry = save_glossary_entry(task_repository, user.username, payload.term, payload.meaning, status='suggested',
                                        source='chat', message_id=message_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        log(task_repository, user, 'assistant_glossary_suggested', {'entry_id': entry['id'], 'term': entry['term'],
                                                                     'meaning': entry['meaning'][:500], 'message_id': message_id})
        return {'entry': entry}

    def back(**query: str) -> RedirectResponse:
        return RedirectResponse(f'/workspace-config?{urlencode(query)}#assistant-glossary', status_code=303)

    @app.post('/workspace-config/assistant-glossary/save')
    def save_assistant_glossary(term: str = Form(''), meaning: str = Form(''), entry_id: str = Form(''),
                                user=Depends(core.config_editor_user)):
        if not core.active_workspace:
            return back(assistant_glossary_error='Open a workspace first.')
        task_repository = bound_repository()
        try:
            entry = save_glossary_entry(task_repository, user.username, term, meaning, int(entry_id) if entry_id.strip() else None)
        except ValueError as exc:
            return back(assistant_glossary_error=str(exc))
        details = {'entry_id': entry['id'], 'term': entry['term'], 'meaning': entry['meaning'][:500]}
        if entry_id.strip():
            details.update({'previous_term': entry.get('previous_term'), 'previous_meaning': str(entry.get('previous_meaning') or '')[:500],
                            'accepted_suggestion': entry.get('previous_status') == 'suggested'})
        log(task_repository, user, 'assistant_glossary_saved', details)
        verb = 'Accepted' if entry.get('previous_status') == 'suggested' else 'Saved'
        return back(assistant_glossary_notice=f'{verb} "{entry["term"]}".')

    @app.post('/workspace-config/assistant-glossary/{entry_id}/delete')
    def delete_assistant_glossary(entry_id: int, user=Depends(core.config_editor_user)):
        if not core.active_workspace:
            return back(assistant_glossary_error='Open a workspace first.')
        task_repository = bound_repository()
        entry = delete_glossary_entry(task_repository, entry_id)
        if entry is None:
            return back(assistant_glossary_error='That glossary entry no longer exists.')
        log(task_repository, user, 'assistant_glossary_deleted', {'entry_id': entry_id, 'term': entry['term'],
                                                                   'meaning': entry['meaning'][:500], 'status': entry['status']})
        what = 'Dismissed the suggestion' if entry['status'] == 'suggested' else 'Deleted'
        return back(assistant_glossary_notice=f'{what} "{entry["term"]}".')

    @app.get('/api/assistant/glossary/export')
    def export_assistant_glossary(user=Depends(assistant_user)):
        task_repository = bound_repository()
        document = glossary_document(task_repository)
        log(task_repository, user, 'assistant_glossary_exported', {'entries': len(document['items'])})
        return JSONResponse(document, headers={'Content-Disposition': 'attachment; filename="ai-assistant-glossary.json"'})
