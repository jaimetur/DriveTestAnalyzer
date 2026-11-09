# Application Config

Application Config stores application-wide runtime overrides. It is separate from Workspace Config, which groups the Main Cities, Mappings & Reference Data and scoring methodology panels for the active workspace.

> [!IMPORTANT]
> **Application-wide settings.** Saved values affect every workspace and take precedence over the corresponding environment defaults.

> [!TIP]
> **Choose the right configuration page.** Use Workspace Config for Main Cities, chart mappings and scoring methodologies; the PPT Templates are managed in [PPT Designer](ppt-designer.md#ppt-templates).

## Presentation

The presentation **Administration** sums up Admin and Super Admin: who sees and does what (roles, Modules Profiles, Workspace Groups and Access Requests) and the management of every account in Users, the application and workspace databases with the Database Viewer, the scheduled backups and their restore, the packages and transfers between servers, the configuration of the application at every level (Application Config, Admin Config, Super Admin Config and Workspace Config) and App Events. Select it to open it in the slide viewer, play it full screen or download its PowerPoint; every presentation is also in [Product Presentations](presentations.md).

```presentations
administration
```

## Access and location

Open **Config → Application Config** from the main navigation at `/application-config`. The page is available to `user-editor`, `admin` and `super-admin` roles. `user-viewer` accounts do not have access. Application Config applies across workspaces; it does not change workspace-owned templates or mapping groups.

Persisted values are stored in the application database and take precedence over environment and Docker settings until changed. Use environment variables for deployment paths and secrets; Application Config does not replace those deployment settings.

## Runtime settings

- **IANA Timezone** controls displayed timestamps and newly stored local timestamps. Choose a name such as `Europe/Madrid`. Without it, or the `TZ` environment variable, the server's own timezone is used (UTC when the server has none).
- **Report Chart Renderer** selects `canvas` or the legacy `pil` renderer.
- **Chromium Executable** optionally selects an executable browser for Canvas rendering. Leave it empty to use the deployment setting or automatic detection.
- **Ignore event time filtering** ignores date and template conditions based on `Event_Start_Time` or `Event_End_Time`.
- **Maximum simultaneous tasks** sets the background task limit from 1 to 32: the datasets of a workspace are processed in parallel up to this limit (the mappings of an upload first, which its CDRs wait for), while its combined tables, Auto-calculated Fields and Scoring jobs run one at a time. The effective limit reserves one logical CPU for interactive requests (with 8 CPUs, up to 7 tasks).
- **Public address of the server** (`https://name[:port]`, without a path) is the address of the links of the presentations that **Copy link** gives and of their previews, whatever address each user opened the application with (see [Product Presentations](presentations.md)), and of the links of the emails of the tool (see [Email Delivery](#email-delivery)). Give the name of the server rather than its IP: WhatsApp on Android opens no link with an IP. Leave it empty to use the address each user opened the application with; the emails of the reports generated on their schedule, which no user opens, then have no download links.

Select **Save Configuration** to persist the values. Saving restarts the shared Canvas renderer so later charts use the selected renderer and browser.

## Email Delivery

The **Email Delivery** panel sets how the tool sends its emails: the reports of [Reporting](reporting.md#email-delivery), the [access requests](super-admin.md#access-requests) of the login page and the activation of their users, the links to [choose a new password](super-admin.md#forgotten-passwords), and the [Ticket Center](ticket-center.md#email-updates) updates. It is available to the same roles as the rest of Application Config.

**Send Through** chooses one of two ways:

- **SMTP server**: a mail server and, if it needs one, its account.
- **Power Automate flow**: a flow of Microsoft Power Automate that sends each email with the Outlook of the Microsoft 365 account that owns it (yours). The emails leave from inside the company, as mail written from that mailbox, so the anti-spam filters of the company treat them as internal mail, and no SMTP server is needed. The flow runs in the cloud of Microsoft: the server only sends it each email over HTTPS, so it works from any server that reaches the Internet, also a Docker container without Teams or Outlook.

| Field | Meaning |
| --- | --- |
| Power Automate Flow Address | The **HTTP POST URL** of the trigger of the flow (see below). It is a secret: whoever has it sends emails from the mailbox of the flow. Leave it empty to keep the saved one |
| Report Links Valid For (days) | How long the **View Online** and **Download** links of each file of a report email work (60 by default, up to 90); they ask to sign in, with access to the workspace of the report. The files stay on the server, in the History of **Reporting**, while their run is kept |
| SMTP Server, Port, Encryption | Mail server and port, for example `smtp.example.com` and `587`; STARTTLS (usually port 587), SSL/TLS (usually 465) or none |
| Username, Password | Optional SMTP authentication. Leave the password empty to keep the saved one, or the `SMTP_PASSWORD` deployment value |
| Attachment Size Limit (MB) | Through SMTP, a report whose files exceed this total is emailed with their download links instead of attached (without the Public address of the server, it fails) |
| Sender Address, Sender Name | The `From` of every SMTP email. With a flow, the sender is its mailbox: give its address, where the replies go when nobody else should get them, and with which an email that mailbox also receives shows once (see below) |
| Access requests | Each access request goes to the administrator and the approvers, copied to the requester, and the requester is told when the user is activated |
| Ticket Center | The reporter of a ticket gets its confirmation and every change others make to it or to a ticket that mentions it |
| Users Told Of Their Own Changes | Nobody is emailed the changes they make to their own tickets, except the users chosen here (for example, when someone else works on their tickets with their user). Nobody is chosen by default |

The links of the emails (a ticket, the sign-in page, a password reset, a file of a report) use the **Public address of the server** of [Application Runtime](#runtime-settings), or else the address the user who caused the email opened the tool with. Every email of the tool starts its subject with `DT Analyzer - ` (for example `DT Analyzer - Ticket #12: …`), so a mail rule can find them. Select **Save Email Delivery**, then **Send Test Email** to check the settings. The deployment variables `EMAIL_TRANSPORT` (`smtp` or `webhook`), `EMAIL_WEBHOOK_URL`, `EMAIL_LINK_DAYS`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_FROM_NAME` and `SMTP_MAX_ATTACHMENTS_MB` provide defaults; saved values take precedence. App Events records every email sent or not sent (`email_sent`, `email_failed`), with its kind, subject, recipients and error.

### Create the Power Automate flow

1. Sign in to Power Automate (`make.powerautomate.com`) with the account that will send the emails and create an **Instant cloud flow** that starts with **When a Teams webhook request is received** (Microsoft Teams connector). In the trigger, choose **Anyone** in **Who can trigger the flow**. If the trigger is marked **Premium**, your licence does not include it.
2. Add the actions below, in this order. Each **Send an HTTP request** is the action of Office 365 Outlook (not Premium) that calls Microsoft Graph with the mailbox of the flow: give the ones that create, send or delete an email the header `Prefer: IdType="ImmutableId"` in **CustomHeader1**, so the email keeps its id once sent. The expressions go in the expression (**fx**) box, and a URI that ends with an expression is its fixed part followed by that expression; the names in quotes are the names to give the actions.
    1. **Compose** "Message": `setProperty(triggerBody()?['message'], 'body', addProperty(triggerBody()?['message']?['body'], 'content', triggerBody()?['html']))`.
    2. **Initialize variable** "Previous" and **Initialize variable** "Email", both of type String and empty.
    3. **Condition** `empty(triggerBody()?['find_previous_url'])` is equal to `false`. Under **True**: **Send an HTTP request** "Find previous", URI `triggerBody()?['find_previous_url']`, Method GET; then **Set variable** Previous to `coalesce(first(body('Find_previous')?['value'])?['id'], '')`.
    4. **Condition** `empty(variables('Previous'))` is equal to `true`. Under **True** (a new conversation): **Send an HTTP request** "Create email", Method POST, URI `https://graph.microsoft.com/v1.0/me/messages`, Body `outputs('Message')`; then **Set variable** Email to `body('Create_email')?['id']`. Under **False** (an answer): **Send an HTTP request** "Create answer", Method POST, URI `https://graph.microsoft.com/v1.0/me/messages/` + `variables('Previous')` + `/createReply`; **Set variable** Email to `body('Create_answer')?['id']`; **Send an HTTP request** "Fill answer", Method PATCH, URI `https://graph.microsoft.com/v1.0/me/messages/` + `variables('Email')`, Body `outputs('Message')`.
    5. **Send an HTTP request** "Send", Method POST, URI `https://graph.microsoft.com/v1.0/me/messages/` + `variables('Email')` + `/send`.
    6. **Condition** `triggerBody()?['delete_sent_copy']` is equal to `true`. Under **True**: **Delay** of 1 minute, then **Send an HTTP request** "Delete sent copy", Method POST, URI `https://graph.microsoft.com/v1.0/me/messages/` + `variables('Email')` + `/permanentDelete`.
3. Save the flow, copy the **HTTP POST URL** of its trigger to **Power Automate Flow Address**, choose **Power Automate flow** in **Send Through**, give the address of the mailbox of the flow in **Sender Address**, save and **Send Test Email**.

Outlook keeps the emails of one organization in one conversation when each answers the one before, not when they share a subject. So every email of a [ticket](ticket-center.md#email-updates) answers the email of the ticket the flow finds in its mailbox (sent or received), with the same subject, without quoting it and only to its own recipients; the other emails, and the first one of a ticket, start a conversation. When the mailbox of the flow (the **Sender Address**) also receives an email, the flow deletes its copy in Sent Items a minute after sending it, so the email shows once in the conversation.

A simpler flow with one action, **Send an email (V2)** (Office 365 Outlook), also works: **To** `triggerBody()?['to']`, **Subject** `triggerBody()?['subject']` and **Body** `triggerBody()?['html']`; under the advanced parameters, **CC** `triggerBody()?['cc']` and **Reply To** `triggerBody()?['reply_to']`. It sends every email as a new conversation and keeps its copy in Sent Items.

Each email reaches the flow as JSON: `kind` (`report`, `ticket`, `access_request`, `access_granted`, `password_reset` or `test`), `to` and `cc` (addresses separated by semicolons), `reply_to`, `subject` and `html`; `message`, the same email as a Microsoft Graph message without its HTML; `find_previous_url`, the Microsoft Graph request that finds the email it answers (empty when it answers none); and `delete_sent_copy`, whether the mailbox of the flow also receives it. A flow request takes about 28 KB, so a flow carries no attachments: the report emails give a download link of each file, the quoted text of a ticket is shortened (and goes without its formats when they would not fit) and an email that still does not fit is not sent (App Events says why).

> [!WARNING]
> **The SMTP password and the address of the flow are stored in the application database.** Configuration exports, transfers and backups include them. Use the `SMTP_PASSWORD` or `EMAIL_WEBHOOK_URL` deployment variables instead if they must not leave the server.

See [Deployment Configuration](configuration.md) for environment variables, storage roots, Docker settings and bootstrap accounts. See [Workspace Config](workspace-config.md) for settings and management panels owned by an active workspace.
