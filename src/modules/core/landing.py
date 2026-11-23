"""The public landing page of DriveTest Analyzer (served at ``/`` to visitors): what each module does, the latest
releases of the changelog, and links to the presentations, the guide and the Help, which the page reads live from the
server (the presentations and the figures of their slides from ``/api/presentations``, the guide from
``/api/help/guide``)."""
from __future__ import annotations

import re
from typing import Any

# Each module on the landing page: the main module it is (its title follows Interface Settings) or an administrative
# area, its presentation (its slides are the module's carousel), its Help chapter and its selling points.
MODULES: tuple[dict[str, Any], ...] = (
    {'key': 'workspace', 'title': 'Workspace', 'presentation': 'workspace', 'chapter': 'workspace-management.md',
     'accent': '#2f7df6', 'headline': 'Every input, ready in minutes',
     'text': 'Upload the CDRs, logs, inventories and mappings of each campaign: the tool recognises them, processes them '
             'and keeps a columnar copy that answers in seconds.',
     'points': ('Data, Voice and Speech CDRs, drive test logs, cells, vendors and the Master Grid',
                'One isolated workspace per country or customer',
                'Parquet and DuckDB copies: minutes became seconds')},
    {'key': 'workspace-config', 'title': 'Workspace Config', 'presentation': 'workspace-config',
     'chapter': 'workspace-config.md', 'accent': '#22b8cf', 'headline': 'Set it once, every module follows',
     'text': 'Operators, vendors, campaigns, regions, methodologies and auto-calculated fields, named once and shared by '
             'every analysis, report and export.',
     'points': ('One name, colour and place per operator', 'Regions, clusters and cities from your own areas',
                'Scoring methodologies and calculated fields of your own')},
    {'key': 'datasets-analysis', 'title': 'CDR Analysis', 'presentation': 'cdr-analysis',
     'chapter': 'datasets-analysis.md', 'accent': '#14b8a6', 'headline': 'One CDR, answered fast',
     'text': 'Distributions, benchmarks and every KPI of a CDR in figures, with only the metrics that matter for each '
             'kind of test.',
     'points': ('KPI tables and distributions per operator', 'Benchmarks between operators at a glance',
                'Inspect the rows, export them or schedule them')},
    {'key': 'scoring', 'title': 'Scoring & GAP Analysis', 'presentation': 'scoring-gap-analysis',
     'chapter': 'scoring-gap-analysis.md', 'accent': '#f59e0b', 'headline': 'Who wins, and where to win the points back',
     'text': 'Score every operator with your methodology, find the GAP to the leader KPI by KPI and see on the map where '
             'the points are lost.',
     'points': ('Best Network and Most Reliable, NSA and SA', 'GAP per KPI, per Region, per city and per campaign',
                'Points Lost Map, Trends, Country Areas and NNS Break-down')},
    {'key': 'network-insights', 'title': 'Network Insights', 'presentation': 'network-insights',
     'chapter': 'network-insights.md', 'accent': '#8b5cf6', 'headline': 'The radio behind every score',
     'text': 'Radio quality, coverage holes, serving distance, bands and vendors of every operator, from the samples to '
             'the sites.',
     'points': ('RSRP, RSRQ, SINR and throughput at a glance', 'Where it is weak and who served, from how far',
                'Key findings that write themselves')},
    {'key': 'non-qualified-calls', 'title': 'Non-Qualified Calls', 'presentation': 'non-qualified-calls',
     'chapter': 'non-qualified-calls.md', 'accent': '#ef4444', 'headline': 'No failed call left behind',
     'text': 'Every failed or degraded call with its map, its log, its root cause and its follow-up, shared by the whole '
             'team until it is closed.',
     'points': ('Six sections per call, with its map and its Layer 3 log', 'Every NQ call on one map, with the cells around',
                'Assign, comment, prioritise and track the progress')},
    {'key': 'dt-analyzer-rca', 'title': 'DT Analyzer RCA', 'presentation': 'dt-analyzer-rca',
     'chapter': 'non-qualified-calls.md', 'accent': '#f97316', 'headline': 'Every call says why it failed',
     'text': 'Four sources, one decision per call: the CDR, the log of the call, the network inventory and the rules of '
             'your team find the root cause.',
     'points': ('The first rule that holds decides the cause', 'Inter-site distance, overshooting and capacity checks',
                'Editable rules that travel between workspaces')},
    {'key': 'ppt-designer', 'title': 'PPT Designer', 'presentation': 'ppt-designer', 'chapter': 'ppt-designer.md',
     'accent': '#ec4899', 'headline': 'Decks that build themselves',
     'text': 'Lay a report out like PowerPoint and build its charts like Tableau: one Design, every campaign, with live '
             'charts and comments that write themselves.',
     'points': ('Templates that every Design inherits', 'Live, editable charts in the PowerPoint',
                'Automatic comments and exports that keep the design')},
    {'key': 'reporting', 'title': 'Reporting', 'presentation': 'reporting', 'chapter': 'reporting.md',
     'accent': '#06b6d4', 'headline': 'One report, every module, on time',
     'text': 'Combine Scoring, Network Insights, NQ Calls and Designs in one report, generate it when you want or on a '
             'schedule, and share it safely.',
     'points': ('PowerPoint and Word from every module', 'Schedules and History of every run',
                'Links and emails that are safe to share')},
    {'key': 'builders', 'title': 'Builders', 'presentation': 'builders', 'chapter': 'query-builder.md',
     'accent': '#84cc16', 'headline': 'Ask the CDRs anything',
     'text': 'Any chart in seconds with the Chart Builder, and exact numbers with SQL in the Query Builder, over every '
             'CDR of the workspace.',
     'points': ('Drag-and-drop charts on every field', 'Exact numbers with SQL over every CDR',
                'Saved queries that travel between workspaces')},
    {'key': 'assistant', 'title': 'AI Assistant', 'presentation': 'assistant', 'chapter': 'assistant.md',
     'accent': '#a855f7', 'headline': 'A question in, the answer with its figures out',
     'text': 'Ask the workspace in plain words: the assistant plans, the server calculates with the tools of the '
             'application, and every figure shows its source.',
     'points': ('The AI engine never sees a customer name', 'The calculations of the tool, on demand',
                'Under control from Super Admin to App Events')},
    {'key': 'ticket-center', 'title': 'Ticket Center', 'presentation': 'ticket-center', 'chapter': 'ticket-center.md',
     'accent': '#10b981', 'headline': 'From report to fix, in the open',
     'text': 'Report a bug or an idea with its screenshots, follow it to the fix and see how the tickets are going.',
     'points': ('Report it well, the first time', 'Dashboards of the time to resolve',
                'Emails as often as each user chooses')},
    {'key': 'administration', 'title': 'Administration', 'presentation': 'administration',
     'chapter': 'administrator-config.md', 'accent': '#64748b', 'headline': 'Safe, shared, under control',
     'text': 'Roles and profiles per user, scheduled backups, transfers between servers and every action on record.',
     'points': ('Who sees and does what, per module and workspace', 'Full and light backups, restored part by part',
                'Transfers between workspaces and servers, App Events of everything')},
)

# The Help chapters the landing page points to, by topic.
HELP_TOPICS: tuple[dict[str, str], ...] = (
    {'title': 'Getting started', 'text': 'The whole workflow, from the CDRs to the report.', 'chapter': 'overview.md',
     'accent': '#2f7df6'},
    {'title': 'Scoring methodology', 'text': 'How every KPI turns into points.', 'chapter': 'scoring-methodology.md',
     'accent': '#f59e0b'},
    {'title': 'Benchmarking providers', 'text': 'NetCheck today, Umlaut, P3 and RootMetrics next.',
     'chapter': 'benchmarking-providers.md', 'accent': '#8b5cf6'},
    {'title': 'Architecture', 'text': 'How the solution is built and deployed.', 'chapter': 'technical-considerations.md',
     'accent': '#14b8a6'},
    {'title': 'Deployment', 'text': 'Docker, AWS and the updates of the server.', 'chapter': 'docker-deployment.md',
     'accent': '#06b6d4'},
    {'title': 'Roadmap', 'text': 'What comes next.', 'chapter': 'roadmap.md', 'accent': '#ec4899'},
)

_RELEASE = re.compile(r'^##\s+Release:\s+v(\S+)', re.MULTILINE)
_DATE = re.compile(r'^###\s+Release Date:\s*(\S+)', re.MULTILINE)
_SECTION = re.compile(r'^####\s+(.+?):?\s*$', re.MULTILINE)
_HEADLINE = re.compile(r'^-\s+\*\*(.+?):?\*\*:?\s*(.*)$')
_KINDS = {'new features': 'New', 'enhancements': 'Improved', 'breaking changes': 'Breaking'}


def module_cards(labels: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """The modules of the landing page, the main ones with their titles of Interface Settings."""
    return [{**module, 'title': str((labels.get(module['key']) or {}).get('title') or module['title'])}
            for module in MODULES]


def _plain(text: str) -> str:
    """Markdown of a changelog line as plain text: no links, emphasis or code marks."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return re.sub(r'[*`_]', '', text).strip()


def latest_news(changelog: str, releases: int = 2, limit: int = 12) -> list[dict[str, Any]]:
    """The newest releases of the changelog, each with its version, date and the headlines of its new features and
    enhancements (at most ``limit`` in all): the module, the title and the start of its text."""
    headers = list(_RELEASE.finditer(changelog))[:releases]
    news, left = [], limit
    for index, match in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(changelog)
        body = changelog[match.end():end]
        date = _DATE.search(body)
        items = []
        sections = list(_SECTION.finditer(body))
        for position, section in enumerate(sections):
            kind = next((label for name, label in _KINDS.items() if name in section.group(1).casefold()), None)
            if kind is None:
                continue
            stop = sections[position + 1].start() if position + 1 < len(sections) else len(body)
            for line in body[section.end():stop].splitlines():
                headline = _HEADLINE.match(line.strip())
                if not headline or left <= 0:
                    continue
                title = _plain(headline.group(1))
                module, _, name = title.partition(' — ')
                summary = _plain(headline.group(2))
                summary = summary[:1].upper() + summary[1:]
                items.append({'kind': kind, 'module': module if name else '', 'title': name or title,
                              'summary': summary if len(summary) <= 180 else summary[:177].rsplit(' ', 1)[0] + '…'})
                left -= 1
        if items:
            news.append({'version': match.group(1), 'date': date.group(1) if date else '', 'items': items,
                         'anchor': f'release-v{match.group(1)}'})
    return news
