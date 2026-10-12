import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Optional

from core.config import env, env_int
from core.db import get_store

log = logging.getLogger("talentscope")


def configured() -> bool:
    return bool(env("SMTP_USER") and env("SMTP_PASS"))


def _from_address() -> str:
    return env("SMTP_FROM") or (f'"TalentScope" <{env("SMTP_USER")}>' if env("SMTP_USER") else "")


def send(to: str, subject: str, html: str) -> None:
    host = env("SMTP_HOST") or "smtp.gmail.com"
    port = env_int("SMTP_PORT", 465)
    message = EmailMessage()
    message["From"] = _from_address()
    message["To"] = to
    message["Subject"] = subject
    message.set_content("This message requires an HTML capable mail client.")
    message.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(env("SMTP_USER"), env("SMTP_PASS"))
            server.send_message(message)
        return
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        server.login(env("SMTP_USER"), env("SMTP_PASS"))
        server.send_message(message)


def dispatch(to: str, subject: str, html: str) -> tuple[str, Optional[str]]:
    if not configured():
        return "simulated", None
    try:
        send(to, subject, html)
        return "sent", None
    except Exception as err:
        log.error("SMTP delivery failed, recording as simulated: %s", err)
        return "failed_real_fallback_simulated", str(err) or "SMTP delivery failed"


def record(to: str, full_name: str, subject: str, html: str, status: str, rm_email: str) -> dict:
    row = {"id": str(uuid.uuid4()), "candidate_email": to, "full_name": full_name, "subject": subject,
           "body": html, "status": status, "rm_email": rm_email}
    try:
        get_store().insert("simulated_emails", row)
    except Exception as err:
        log.error("Failed to write to simulated_emails table: %s", err)
    return row
