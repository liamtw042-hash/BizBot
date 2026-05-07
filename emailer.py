"""Send cold emails to businesses via Gmail SMTP."""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SUBJECT = "I built your business a free website"

EMAIL_BODY_TEMPLATE = """\
Hi {business_name} team,

I was recently searching for local {category} businesses in {city} and noticed that \
{business_name} doesn't have a website yet.

I went ahead and built one for you — completely free, no strings attached. You can \
view it here:

  {website_url}

The site includes your contact information, a services section, and a clean modern \
design that looks great on mobile too.

If you'd like to use it, update it, or just have a chat about your online presence, \
feel free to reply to this email.

Warm regards,
{sender_name}
{sender_phone}
{sender_website}
"""


def _build_message(business: dict, website_url: str, config: dict) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"] = config["gmail_address"]
    msg["To"] = business["email"]

    body = EMAIL_BODY_TEMPLATE.format(
        business_name=business.get("name", ""),
        category=business.get("category", "").replace("_", " "),
        city=business.get("city", ""),
        website_url=website_url,
        sender_name=config.get("sender_name", ""),
        sender_phone=config.get("sender_phone", ""),
        sender_website=config.get("sender_website", ""),
    ).strip()

    msg.attach(MIMEText(body, "plain"))
    return msg


def send_email(business: dict, website_url: str, config: dict) -> bool:
    """
    Send a cold email to the business. Returns True on success.
    Requires business['email'] to be non-empty.
    """
    if not business.get("email"):
        logger.warning(f"No email for {business['name']}, skipping send")
        return False

    msg = _build_message(business, website_url, config)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config["gmail_address"], config["gmail_app_password"])
            server.sendmail(
                config["gmail_address"],
                business["email"],
                msg.as_string(),
            )
        logger.info(f"Email sent to {business['name']} <{business['email']}>")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail authentication failed — check gmail_address and gmail_app_password in config.yaml")
        raise
    except Exception as e:
        logger.error(f"Failed to send email to {business['name']}: {e}")
        return False
