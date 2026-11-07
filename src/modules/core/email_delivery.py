"""Email delivery of the tool, configured in Application Config: through an SMTP server, or through a Power Automate flow
(a webhook) that sends the message from a Microsoft 365 mailbox, so it arrives as internal mail.

It sends the artifacts of Reporting Jobs, the access requests of the login page, the password resets and the updates of
Ticket Center. The links an email carries (a Reporting file, a password reset) are signed and expire."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Any

EMAIL_DELIVERY_STATE_KEY = 'email_delivery_v1'
# The key that signs the links of the emails, created once per deployment.
EMAIL_LINK_SECRET_STATE_KEY = 'email_link_secret_v1'
EMAIL_SECURITY_MODES = ('starttls', 'ssl', 'none')
# smtp: an SMTP server; webhook: a Power Automate flow (or any HTTPS endpoint) that receives the message as JSON.
EMAIL_TRANSPORTS = ('smtp', 'webhook')
EMAIL_ADDRESS_PATTERN = re.compile(r'^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$')
DEFAULT_MAX_ATTACHMENTS_MB = 20
DEFAULT_LINK_DAYS = 60
MAX_LINK_DAYS = 90
SMTP_TIMEOUT_SECONDS = 60
WEBHOOK_TIMEOUT_SECONDS = 30
# A Teams webhook request of a flow takes about 28 KB: a larger message is refused before it is sent.
WEBHOOK_MAX_BYTES = 27_000
# Every email of the tool starts its subject with it, so mail clients and rules can tell them apart.
SUBJECT_PREFIX = 'DT Analyzer - '

# Deployment defaults; values saved in Application Config take precedence.
EMAIL_ENVIRONMENT_DEFAULTS = {
    'host': 'SMTP_HOST', 'port': 'SMTP_PORT', 'security': 'SMTP_SECURITY', 'username': 'SMTP_USERNAME',
    'password': 'SMTP_PASSWORD', 'from_address': 'SMTP_FROM', 'from_name': 'SMTP_FROM_NAME',
    'max_attachments_mb': 'SMTP_MAX_ATTACHMENTS_MB', 'transport': 'EMAIL_TRANSPORT', 'webhook_url': 'EMAIL_WEBHOOK_URL',
    'link_days': 'EMAIL_LINK_DAYS',
}
# Saved switches (no deployment default): which emails the tool sends on its own.
EMAIL_SWITCHES = {'notify_access_requests': True, 'notify_tickets': True}
# The values that are secrets: never shown, kept when the form leaves them empty.
EMAIL_SECRETS = ('password', 'webhook_url')


def parse_recipients(value: str | list[str] | None) -> list[str]:
    """Split a comma, semicolon or line separated recipient list, keeping order."""
    items = value if isinstance(value, list) else re.split(r'[,;\n]+', str(value or ''))
    return list(dict.fromkeys(item.strip() for item in items if str(item).strip()))


def invalid_recipients(recipients: list[str]) -> list[str]:
    return [item for item in recipients if not EMAIL_ADDRESS_PATTERN.match(item)]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _switch(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == '':
        return default
    return str(value).strip().casefold() in {'1', 'true', 'yes', 'on'}


def _stored(repository: Any) -> dict[str, Any]:
    try:
        stored = json.loads(repository.get_application_state(EMAIL_DELIVERY_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        stored = {}
    return stored if isinstance(stored, dict) else {}


def email_delivery_settings(repository: Any, *, include_password: bool = False) -> dict[str, Any]:
    """Saved settings over environment defaults; the secrets (the SMTP password and the address of the flow) are only
    returned on request."""
    values: dict[str, Any] = {key: os.environ.get(variable, '') for key, variable in EMAIL_ENVIRONMENT_DEFAULTS.items()}
    stored = _stored(repository)
    for key, value in stored.items():
        # An empty saved secret keeps the deployment one, if any.
        if key in EMAIL_ENVIRONMENT_DEFAULTS and (key not in EMAIL_SECRETS or value):
            values[key] = value
    security = str(values.get('security') or 'starttls').strip().casefold()
    transport = str(values.get('transport') or 'smtp').strip().casefold()
    settings = {
        'transport': transport if transport in EMAIL_TRANSPORTS else 'smtp',
        'host': str(values.get('host') or '').strip(),
        'port': _int(values.get('port'), 465 if security == 'ssl' else 587 if security == 'starttls' else 25),
        'security': security if security in EMAIL_SECURITY_MODES else 'starttls',
        'username': str(values.get('username') or '').strip(),
        'from_address': str(values.get('from_address') or '').strip(),
        'from_name': str(values.get('from_name') or 'DriveTest Analyzer').strip(),
        'max_attachments_mb': max(1, _int(values.get('max_attachments_mb'), DEFAULT_MAX_ATTACHMENTS_MB)),
        'password_configured': bool(values.get('password')),
        'webhook_configured': bool(str(values.get('webhook_url') or '').strip()),
        'link_days': min(MAX_LINK_DAYS, max(1, _int(values.get('link_days'), DEFAULT_LINK_DAYS))),
        **{key: _switch(stored.get(key), default) for key, default in EMAIL_SWITCHES.items()},
    }
    settings['configured'] = (settings['webhook_configured'] if settings['transport'] == 'webhook'
                              else bool(settings['host'] and settings['from_address']))
    if include_password:
        settings['password'] = str(values.get('password') or '')
        settings['webhook_url'] = str(values.get('webhook_url') or '').strip()
    return settings


def save_email_delivery_settings(repository: Any, values: dict[str, Any], *, keep_password: bool,
                                 keep_webhook_url: bool = True) -> dict[str, Any]:
    """Validate and persist the settings; keep_password and keep_webhook_url retain the saved secrets."""
    previous = _stored(repository)
    transport = str(values.get('transport') or 'smtp').strip().casefold()
    if transport not in EMAIL_TRANSPORTS:
        raise ValueError('Choose an SMTP server or a Power Automate flow.')
    security = str(values.get('security') or 'starttls').strip().casefold()
    if security not in EMAIL_SECURITY_MODES:
        raise ValueError('Choose STARTTLS, SSL/TLS or no encryption.')
    port = _int(values.get('port'), 0)
    if not 1 <= port <= 65535:
        raise ValueError('The SMTP port must be between 1 and 65535.')
    from_address = str(values.get('from_address') or '').strip()
    if from_address and not EMAIL_ADDRESS_PATTERN.match(from_address):
        raise ValueError('Enter a valid sender address.')
    max_attachments_mb = _int(values.get('max_attachments_mb'), DEFAULT_MAX_ATTACHMENTS_MB)
    if not 1 <= max_attachments_mb <= 500:
        raise ValueError('The attachment size limit must be between 1 and 500 MB.')
    webhook_url = str(previous.get('webhook_url') or '') if keep_webhook_url else str(values.get('webhook_url') or '').strip()
    if webhook_url and not webhook_url.casefold().startswith('https://'):
        raise ValueError('The address of the Power Automate flow must start with https://.')
    link_days = _int(values.get('link_days'), DEFAULT_LINK_DAYS)
    if not 1 <= link_days <= MAX_LINK_DAYS:
        raise ValueError(f'The download links must be valid between 1 and {MAX_LINK_DAYS} days.')
    stored = {
        'transport': transport,
        'host': str(values.get('host') or '').strip(), 'port': port, 'security': security,
        'username': str(values.get('username') or '').strip(),
        'password': str(previous.get('password') or '') if keep_password else str(values.get('password') or ''),
        'from_address': from_address, 'from_name': str(values.get('from_name') or '').strip(),
        'max_attachments_mb': max_attachments_mb, 'webhook_url': webhook_url, 'link_days': link_days,
        # (A switch the values leave out keeps its saved state.)
        **{key: _switch(values[key], False) if key in values else _switch(previous.get(key), default)
           for key, default in EMAIL_SWITCHES.items()},
    }
    repository.set_application_state(EMAIL_DELIVERY_STATE_KEY, json.dumps(stored, sort_keys=True))
    return email_delivery_settings(repository)


# -- signed links ------------------------------------------------------------------------------------------------------
def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _link_secret(repository: Any) -> bytes:
    secret = repository.get_application_state(EMAIL_LINK_SECRET_STATE_KEY) or ''
    if not re.fullmatch(r'[0-9a-f]{64}', secret):
        secret = secrets.token_hex(32)
        repository.set_application_state(EMAIL_LINK_SECRET_STATE_KEY, secret)
    return bytes.fromhex(secret)


def sign_link(repository: Any, payload: dict[str, Any], *, seconds: int) -> str:
    """A token for a link of an email: the payload, when it expires and their signature."""
    body = _encode(json.dumps({**payload, 'exp': int(time.time()) + int(seconds)}, separators=(',', ':'), sort_keys=True).encode())
    signature = hmac.new(_link_secret(repository), body.encode(), hashlib.sha256).digest()
    return f'{body}.{_encode(signature)}'


def read_link(repository: Any, token: str, kind: str) -> dict[str, Any] | None:
    """The payload of a token of ``kind`` signed here; None when it is not valid or it expired."""
    body, _, signature = str(token or '').partition('.')
    if not body or not signature:
        return None
    try:
        expected = hmac.new(_link_secret(repository), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            return None
        payload = json.loads(_decode(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get('k') != kind or int(payload.get('exp') or 0) < time.time():
        return None
    return payload


# -- sending -----------------------------------------------------------------------------------------------------------
def subject_line(subject: str) -> str:
    """The subject an email of the tool is sent with: ``subject`` after the prefix of the tool (once)."""
    subject = str(subject or '').strip()
    return subject if subject.startswith(SUBJECT_PREFIX) else f'{SUBJECT_PREFIX}{subject}'


def build_email(settings: dict[str, Any], recipients: list[str], subject: str, text: str, html: str,
                attachments: list[tuple[str, Path]], *, cc: list[str] | None = None, reply_to: str = '') -> EmailMessage:
    message = EmailMessage()
    message['Subject'] = subject_line(subject)
    message['From'] = formataddr((settings.get('from_name') or '', settings['from_address']))
    message['To'] = ', '.join(recipients)
    if cc:
        message['Cc'] = ', '.join(cc)
    if reply_to:
        message['Reply-To'] = reply_to
    message['Message-ID'] = make_msgid(domain=settings['from_address'].rsplit('@', 1)[-1])
    message.set_content(text)
    message.add_alternative(html, subtype='html')
    for file_name, path in attachments:
        content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        maintype, subtype = content_type.split('/', 1)
        message.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=file_name)
    return message


def webhook_payload(settings: dict[str, Any], recipients: list[str], subject: str, html: str, *, cc: list[str] | None = None,
                    reply_to: str = '', kind: str = 'message') -> dict[str, Any]:
    """The JSON the Power Automate flow receives: the fields of its Send an email (V2) action (recipients separated by
    semicolons, as Outlook takes them)."""
    payload: dict[str, Any] = {
        'kind': kind, 'to': ';'.join(recipients), 'cc': ';'.join(cc or []),
        # Replies go to whoever the message is for (a requester), else to the sender address of Email Delivery.
        'reply_to': reply_to or settings.get('from_address') or '', 'subject': subject_line(subject), 'html': html,
    }
    return payload


def post_webhook(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if len(data) > WEBHOOK_MAX_BYTES:
        raise RuntimeError(f'The email takes {len(data) / 1024:.0f} KB, above the {WEBHOOK_MAX_BYTES // 1000} KB a '
                           'Power Automate flow request takes.')
    request = urllib.request.Request(url, data=data, method='POST', headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, 'status', 200) or 200)
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode('utf-8', 'replace').strip()
        raise RuntimeError(f'The Power Automate flow answered {exc.code}{f": {detail}" if detail else ""}.') from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f'The Power Automate flow could not be reached: {getattr(exc, "reason", exc)}.') from exc
    if not 200 <= status < 300:
        raise RuntimeError(f'The Power Automate flow answered {status}.')


def send_email(settings: dict[str, Any], recipients: list[str], subject: str, text: str, html: str,
               attachments: list[tuple[str, Path]] | None = None, *, cc: list[str] | None = None, reply_to: str = '',
               kind: str = 'message') -> None:
    """Send one message through the configured SMTP server or Power Automate flow; raises on failure."""
    if not settings.get('configured'):
        raise RuntimeError('Email delivery is not configured. Set the SMTP server or the Power Automate flow in Application Config.')
    if not recipients:
        raise RuntimeError('The email has no recipients.')
    attachments = attachments or []
    if settings.get('transport') == 'webhook':
        if attachments:
            raise RuntimeError('A Power Automate flow sends no attachments: the email gives links to the files instead.')
        post_webhook(str(settings.get('webhook_url') or ''), webhook_payload(
            settings, recipients, subject, html, cc=cc, reply_to=reply_to, kind=kind))
        return
    total_bytes = sum(path.stat().st_size for _name, path in attachments)
    limit_bytes = int(settings.get('max_attachments_mb') or DEFAULT_MAX_ATTACHMENTS_MB) * 1024 * 1024
    if total_bytes > limit_bytes:
        raise RuntimeError(
            f'The attachments total {total_bytes / 1024 / 1024:.1f} MB, above the '
            f'{settings.get("max_attachments_mb")} MB limit set in Application Config.'
        )
    message = build_email(settings, recipients, subject, text, html, attachments, cc=cc, reply_to=reply_to)
    host, port, security = settings['host'], int(settings['port']), settings['security']
    context = ssl.create_default_context()
    if security == 'ssl':
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)
    with server:
        server.ehlo()
        if security == 'starttls':
            server.starttls(context=context)
            server.ehlo()
        if settings.get('username'):
            server.login(settings['username'], settings.get('password') or '')
        server.send_message(message)
