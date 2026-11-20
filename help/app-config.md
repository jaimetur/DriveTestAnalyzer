# Application Config

Application Config stores application-wide runtime overrides. It is separate from Workspace Config, which groups the Main Cities, Mappings & Reference Data and scoring methodology panels for the active workspace.

> [!IMPORTANT]
> **Application-wide settings.** Saved values affect every workspace and take precedence over the corresponding environment defaults.

> [!TIP]
> **Choose the right configuration page.** Use Workspace Config for Main Cities, chart mappings and scoring methodologies; the PPT Templates are managed in [PPT Designer](ppt-designer.md#ppt-templates).

## Presentation & Guide

```presentations
administration
guide:app-config.md
```

## Main topics in this guide

| Task or topic | Go to |
| --- | --- |
| Open Application Config | [Access and location](#access-and-location) |
| Change the runtime settings | [Runtime settings](#runtime-settings) |
| Set up the email delivery | [Email Delivery](#email-delivery) |
| <span class="guide-sub">↳ Create the Power Automate flow</span> | <span class="guide-sub">↳ [Create the Power Automate flow](#create-the-power-automate-flow)</span> |

## Access and location

Open **Config → Application Config** (`/application-config`).

- **Who:** `user-editor`, `admin` and `super-admin`; `user-viewer` accounts have no access.
- **Admins and super-admins only:** **Email Delivery** (a `user-editor` sees only whether it is configured), **Chromium Executable** and **Public address of the server** (shown, not editable, to a `user-editor`), because they decide what the server runs and where its emails lead.
- **Scope:** values are stored in the application database, apply to every workspace and take precedence over environment and Docker settings until changed. They do not change workspace-owned templates or mapping groups, nor replace the deployment paths and secrets of the environment variables (see [Deployment Configuration](configuration.md)).

## Runtime settings

- **IANA Timezone:** displayed timestamps and newly stored local timestamps, for example `Europe/Madrid`. Without it, or the `TZ` environment variable, the server's own timezone is used (UTC when the server has none).
- **Report Chart Renderer:** `canvas` or the legacy `pil` renderer.
- **Chromium Executable:** optional absolute path of the browser for Canvas rendering. Empty uses the deployment setting or automatic detection.
- **Ignore event time filtering:** ignores the Design, CDR Analysis, date and template conditions based on `Event_Start_Time` or `Event_End_Time`. Use it when source timestamps are incomplete and must not exclude valid rows.
- **Maximum simultaneous tasks:** the background task limit, 1 to 32.
  - The datasets of a workspace are processed in parallel up to this limit (the mappings of an upload first, which its CDRs wait for); its combined tables, Auto-calculated Fields and Scoring jobs run one at a time.
  - The effective limit reserves one logical CPU for interactive requests (with 8 CPUs, up to 7 tasks).
- **Public address of the server** (`https://name[:port]`, without a path): the address of the links that **Copy link** gives for the presentations and of their previews (see [Product Presentations](presentations.md)), and of the links of the emails of the tool, whatever address each user opened the application with.
  - Give the name of the server rather than its IP: WhatsApp on Android opens no link with an IP.
  - Empty, presentation links use the address each user opened the application with. Email links (a ticket, the sign-in page, a password reset, a file of a report) use the address the request came with only when a super-admin has signed in at that address, otherwise the latest address a super-admin signed in at, so a password reset asked for with a made-up address cannot lead its reader to another server. Set it on a server reached through several names.
  - Empty, the emails of the reports generated on their schedule, which no user opens, have no download links.

Select **Save Configuration** to persist the values. Saving restarts the shared Canvas renderer so later charts use the selected renderer and browser.

## Email Delivery

The **Email Delivery** panel sets how the tool sends its emails: the reports of [Reporting](reporting.md#email-delivery), the [access requests](super-admin.md#access-requests) and the activation of their users, the links to [choose a new password](super-admin.md#forgotten-passwords) and the [Ticket Center](ticket-center.md#email-updates) updates.

**Send Through** chooses one of two ways:

- **SMTP server:** a mail server and, if it needs one, its account.
- **Power Automate flow:** a Microsoft Power Automate flow sends each email with the Outlook of the Microsoft 365 account that owns it (yours).
  - The emails leave from inside the company, as mail written from that mailbox, so the company's anti-spam filters treat them as internal mail; no SMTP server is needed.
  - The flow runs in Microsoft's cloud: the server only sends it each email over HTTPS, so it works from any server that reaches the Internet, also a Docker container without Teams or Outlook.

The fields:

- **Power Automate Flow Address:** the **HTTP POST URL** of the trigger of the flow (see below). It is a secret: whoever has it sends emails from the mailbox of the flow. Empty keeps the saved one; **Remove the saved flow address** deletes it.
- **SMTP Server**, **Port**, **Encryption:** for example `smtp.example.com` and `587`; STARTTLS (usually port 587), SSL/TLS (usually 465) or none.
- **Username**, **Password:** optional SMTP authentication. An empty password keeps the saved one, or the `SMTP_PASSWORD` deployment value; **Remove the saved password** deletes it.
- **Sender Address**, **Sender Name:** the `From` of every SMTP email. With a flow the sender is its mailbox: give its address, where the replies go when nobody else should get them.
  - An SMTP sender outside Ericsson (not `ericsson.com` nor one of its subdomains) may land in the **Junk Email** folder of Ericsson's mailboxes: the access request and **Forgot your password?** dialogs of the login page then tell, once they emailed, to look there and add the sender to **Safe senders**.
- **Report Links Valid For (days):** how long the **View Online** and **Download** links of a report email work (60 by default, up to 90); see [Reporting](reporting.md#email-delivery).
- **Attachment Size Limit (MB):** 20 by default. Through SMTP, a report whose files exceed this total is emailed with download links instead of attachments (without the Public address of the server, it fails).
- **Access requests:** emails each access request and the activation of its user (who receives them: [Access Requests](super-admin.md#access-requests)).
- **Ticket Center:** emails the ticket updates (who receives them: [Email updates](ticket-center.md#email-updates)), at once or in the summary each user chooses in **Email preferences** of the user badge.
- **Email Every Ticket To:** users who get an email of every new ticket and every change to any ticket, even when they did not open or comment it. Nobody by default.
- **Non-Qualified Calls:** emails the reviewer of an NQ call when all its analyst fields are filled and when its NQ Call Status or the status of a phase (Analysis, Implementation, Planned) changes, with the fields filled by section, those still empty and a link to the call. Each user chooses in **Email preferences** of the user badge how often it gets them:
  - **Daily at 17:00** (the default), **Every hour** or **Weekly on Friday at 17:00:** one summary of the calls changed since the previous one, each call once, with each status from its value before the first change to its value after the last one (a status back to its value is left out); one email per workspace.
  - **Immediately:** one email per change. The emails of a call keep its subject (`NQ Call <JOIN_ID> · …`), one conversation in Outlook; a bulk change or a copy to a group lists its calls in one email.
  - **Never:** none.
  - **Own changes:** nobody is emailed the changes it makes itself unless it checks **Also email me the changes I make**.
  - The changes waiting for a summary are kept in the **NQ Email Queue** table, so a restart loses none; the summaries go at the time of the server (Application Runtime timezone).
- **Email Every NQ Call Change To:** users who get those emails of every NQ call of every workspace, even when they are not its reviewer. Nobody by default.

Every email of the tool starts its subject with `DT Analyzer - ` (for example `DT Analyzer - Ticket #12: …`), so a mail rule can find it. Its links use the [Public address of the server](#runtime-settings).

Select **Save Email Delivery**, then type an address in **Send a test email to** and select **Send Test Email** to check the settings (disabled until the SMTP server or the flow is saved). The `EMAIL_*` and `SMTP_*` deployment variables provide defaults (see [Deployment Configuration](configuration.md#runtime-settings)); saved values take precedence. App Events records every email sent or not sent (`email_sent`, `email_failed`), with its kind, subject, recipients and error.

### Create the Power Automate flow

1. Sign in to Power Automate (`make.powerautomate.com`) with the account that will send the emails and create an **Instant cloud flow** that starts with **When a Teams webhook request is received** (Microsoft Teams connector). In the trigger, choose **Anyone** in **Who can trigger the flow**. If the trigger is marked **Premium**, your licence does not include it.
2. Add the action **Send an email (V2)** (Office 365 Outlook) and fill it with expressions: **To** `triggerBody()?['to']`, **Subject** `triggerBody()?['subject']` and **Body** `triggerBody()?['html']`; under the advanced parameters, **CC** `triggerBody()?['cc']` and **Reply To** `triggerBody()?['reply_to']`.
3. Save the flow, copy the **HTTP POST URL** of its trigger to **Power Automate Flow Address**, choose **Power Automate flow** in **Send Through**, save and **Send Test Email**.

Each email reaches the flow as JSON: `kind` (`report`, `ticket`, `access_request`, `access_granted`, `password_reset` or `test`), `to` and `cc` (addresses separated by semicolons), `reply_to`, `subject` and `html`. A flow request takes about 28 KB, so a flow carries no attachments: report emails give a download link of each file, the quoted text of a ticket is shortened (and goes without its formats when they would not fit), and an email that still does not fit is not sent (App Events says why).

> [!WARNING]
> **The SMTP password and the address of the flow are stored in the application database.** Configuration exports, transfers and backups include them. Use the `SMTP_PASSWORD` or `EMAIL_WEBHOOK_URL` deployment variables instead if they must not leave the server.

See [Deployment Configuration](configuration.md) for environment variables, storage roots, Docker settings and bootstrap accounts, and [Workspace Config](workspace-config.md) for the settings of the active workspace.
