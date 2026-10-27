# DriveTestAnalyzer Instructions

## Language
- Always respond to me in Spanish unless I explicitly request another language in the chat.
- All source code must be written in English, including:
  - variable and function names;
  - class and module names;
  - comments and docstrings;
  - UI labels and dialog messages;
  - log messages;
  - warnings and error messages;
  - configuration keys and other developer-facing text.

## Scoring Export Panels
- When you change any panel in Scoring & GAP Analysis module, make sure that the Scoring Export Panels in Workspace Configuration is updated with the right info.

## Changelog
- When editing the changelog, always update the section for the current version of the tool.
- If a release contains `Breaking Changes`, that section must always be the first section immediately after the release date.
- Add new changelog entries as the last bullet of the appropriate section, such as `New Features`, `Enhancements`, `Bug Fixes`, or `Documentation`.
- Keep the changelog concise and describe the final state of the implementation rather than the sequence of intermediate changes.
- Within the same current/unreleased version, do not create multiple changelog bullets for incremental changes, fixes, or refinements to the same functionality.
- If an existing changelog bullet already describes the same functionality, update or rewrite that bullet so it reflects the final behavior.
- Do not add changelog entries for internal implementation changes that have no relevant user-facing or developer-facing impact.
- Do not create blank lines between bullets on the same section and also under the section name and the first bullet.

## Documentation
- Whenever implementing or modifying a feature, review all documentation related to that feature.
- Update any documentation that is no longer accurate after the change.
- Documentation must describe the final supported behavior, not intermediate implementation attempts or temporary states.
- Main modules can be renamed in Admin → Interface Settings, and the Help shows their new title. Write module titles of several words (for example `Network Insights`) as they are; in section headings they keep their name. Write the one-word modules (`Workspace`, `Reporting`, `Builders`) as a link to their chapter (`[Reporting](reporting.md)`, `[Workspace Management](workspace-management.md)`) or in bold (`**Reporting**`) when they name the module, and plainly when the word means something else (for example Reporting Jobs or Reporting (old)).

## Ticket Center
- When any bug, big enhancement or new request is address, create a new ticket in AWS server (https://108.132.147.165:8443/tickets) with the description of the issue and the resolution proposal.
- When the solution is implemented, close the ticket with the implemented solution description.
- The ticket priority by default is P3, but you can increase or decrease it if you consideer that the issue is relevant or not.
- By default the ticket should be created and assigned to me (EJAITUR) and the date and versions of the ticket should match the current one.
- If the issue already has a ticket, don't create a new one, just comment on it.

## Import, Export, Transfers, Backup and Restore
- Preserve compatibility with existing supported formats unless a breaking change is explicitly requested.
- When modifying the behavior, consider both sides of the workflow and verify round-trip compatibility when applicable.
- Do not silently change column names, field meanings, identifiers, data types, file structure, or exported semantics.
- Whenever a new feature introduces persistent or user-configurable data that is reasonably transferable or exportable — such as templates, queries, vendor/operator mappings, or similar entities — integrate that data into the relevant import/export and transfer workflows, as well as backup and restore.
- When extending an existing exportable data model, verify whether the corresponding importers, exporters, transfer mechanisms, backup, and restore logic also need to be updated.
- New exportable data should not remain available only inside the local application state unless there is a deliberate and documented reason to exclude it from import/export, transfers, backup, or restore.

## Default assets templates for new workspaces
- Update the default templates to apply to new workspace (contained in /assets) with the current UK workspace ones such as:
  - Auto-calculated fields
  - Bundle-report-template-favourites
  - labels-campaigns
  - labels-operator
  - labels-vendors
  - ppt-dashboards
  - ppt-templates
  - query-builder-queries
  - reporting-jobs
  - scoring-favourite-filters
  - scoring-methodologies
  - scoring-report-configurations
- Skip those templates created by other users rather tan me (EJAITUR) or system.
- Skip, rename or adapt those very workspace-specific templates, for instance if one template contains references to operators of the current workspace, don't include it by default or adapt it to remove the workspace-specific values.

## Database Management
- When any new table is created, it has to be visible in the Database Management selector and the tittle should have the same format than the others (Uppercase the First Letter of each Word).

## App Events
- Make sure that all the actions carried-out by any user are registered in the App Events Log with enough details to do a troubleshooting in case of any error..

## Tests and Pending Requests
- Do not run tests while there are pending requests from me; finish processing every queued request first and run the tests only when nothing else is left to do.
- If tests are running and I send a new request, stop the tests immediately and work on the new request; run the tests again once there are no pending requests.
- Do not run a complete test unless the change have been significative to break the behavior of the tool or unless the user request it.