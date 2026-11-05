"""Sends email: over SMTP (e.g. Gmail with an app password), or through Brevo's HTTP API.

SMTP settings (environment variables), used when SMTP_HOST is set:
  SMTP_HOST      e.g. smtp.gmail.com
  SMTP_PORT      587 (STARTTLS, the default) or 465 (SSL)
  SMTP_USER      the account to log in as, e.g. you@gmail.com
  SMTP_PASS      its password; for Gmail, an app password (not your normal password)
  MAIL_FROM      the sender address (default SMTP_USER; Gmail only allows your own address)
  MAIL_FROM_NAME the sender name shown in inboxes (default "ShelfEye")

Otherwise, with BREVO_API_KEY and MAIL_FROM set, it sends through Brevo over HTTPS,
which works on hosts that block SMTP ports.

With neither, nothing is sent and the message is written to the log instead,
which is handy when running the server on your own computer.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import requests

log = logging.getLogger("uvicorn.error")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(to_email, to_name, subject, text, html):
    if os.environ.get("SMTP_HOST"):
        _send_smtp(to_email, to_name, subject, text, html)
    elif os.environ.get("BREVO_API_KEY") and os.environ.get("MAIL_FROM"):
        _send_brevo(to_email, to_name, subject, text, html)
    else:
        log.warning("Email not configured (SMTP_HOST or BREVO_API_KEY); would have sent to %s:\n%s", to_email, text)


def _sender():
    return os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", ""), os.environ.get("MAIL_FROM_NAME", "ShelfEye")


def _send_smtp(to_email, to_name, subject, text, html):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    sender, sender_name = _sender()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, sender))
    message["To"] = formataddr((to_name, to_email))
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=context)
        with server:
            if user:
                server.login(user, password)
            server.send_message(message)
        log.info("Sent '%s' to %s", subject, to_email)
    except (OSError, smtplib.SMTPException) as exc:
        log.error("Couldn't send email to %s through %s:%d: %s", to_email, host, port, exc)


def _send_brevo(to_email, to_name, subject, text, html):
    sender, sender_name = _sender()
    try:
        response = requests.post(
            BREVO_URL,
            headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json"},
            json={
                "sender": {"email": sender, "name": sender_name},
                "to": [{"email": to_email, "name": to_name}],
                "subject": subject,
                "textContent": text,
                "htmlContent": html,
            },
            timeout=15,
        )
        if not response.ok:
            log.error("Brevo refused the email to %s: %s %s", to_email, response.status_code, response.text[:300])
    except requests.RequestException as exc:
        log.error("Couldn't reach Brevo to email %s: %s", to_email, exc)
