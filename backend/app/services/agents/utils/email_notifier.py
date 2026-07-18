import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import aiosmtplib

from app.utils.config import settings

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self):
        pass

    async def send_email_with_attachment(self, 
                                         to_email: str, 
                                         subject: str, 
                                         body: str, 
                                         attachment_bytes: bytes, 
                                         attachment_filename: str) -> bool:
        """Sends an HTML/Text email with a PDF attachment asynchronously."""
        # 1. Validation & Fallback Simulation mode for local development
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            logger.info("--- SMTP Credentials Missing: Running in EMAIL SIMULATION MODE ---")
            logger.info(f"To: {to_email}")
            logger.info(f"Subject: {subject}")
            logger.info(f"Attachment name: {attachment_filename} ({len(attachment_bytes)} bytes)")
            
            # Save mock email to a local workspace folder for review
            mock_dir = settings.BASE_DIR.parent / "temp_emails"
            mock_dir.mkdir(exist_ok=True)
            
            # Save PDF file locally
            pdf_path = mock_dir / attachment_filename
            with open(pdf_path, "wb") as f:
                f.write(attachment_bytes)
                
            # Write email metadata text file
            meta_path = mock_dir / f"{attachment_filename.replace('.pdf', '_email.txt')}"
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(f"TO: {to_email}\n")
                f.write(f"FROM: {settings.SMTP_FROM_EMAIL}\n")
                f.write(f"SUBJECT: {subject}\n")
                f.write(f"DATE: {datetime_now_str()}\n\n")
                f.write(body)
                
            logger.info(f"Simulated email and PDF saved to local temp directory: {mock_dir}")
            return True

        # 2. Real SMTP Delivery Flow
        try:
            logger.info(f"Connecting to SMTP Server {settings.SMTP_HOST}:{settings.SMTP_PORT} as {settings.SMTP_USERNAME}...")
            
            # Build MIME Message
            message = MIMEMultipart()
            message["From"] = settings.SMTP_FROM_EMAIL
            message["To"] = to_email
            message["Subject"] = subject
            message.attach(MIMEText(body, "plain"))

            # Attach PDF binary payload
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {attachment_filename}",
            )
            message.attach(part)

            # Connect and send
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME,
                password=settings.SMTP_PASSWORD,
                use_tls=(settings.SMTP_PORT == 465),
                start_tls=(settings.SMTP_PORT == 587)
            )
            logger.info(f"Email successfully dispatched to: {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to deliver SMTP email to {to_email}: {e}", exc_info=True)
            raise e

def datetime_now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

email_notifier = EmailNotifier()
