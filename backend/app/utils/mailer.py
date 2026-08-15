import logging
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.utils.config import settings

logger = logging.getLogger(__name__)

def _send_sync_email(to_email: str, subject: str, html_content: str) -> None:
    """Synchronous SMTP email delivery function."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise ValueError("SMTP credentials are not configured in environment variables.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"ProcureIQ Auth <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    part = MIMEText(html_content, "html")
    msg.attach(part)

    # Connect to SMTP server and send email
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()  # Upgrade connection to secure STARTTLS
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())

async def send_otp_email(to_email: str, otp_code: str) -> None:
    """Asynchronous SMTP email delivery runner using a thread pool."""
    subject = "Verify Your ProcureIQ Account"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1px solid #e5e7eb; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <h2 style="color: #4F46E5; text-align: center; margin-top: 0; font-size: 24px;">Welcome to ProcureIQ</h2>
          <p style="font-size: 16px; color: #374151;">Hello,</p>
          <p style="font-size: 16px; color: #374151; margin-bottom: 24px;">Thank you for signing up. Please verify your email address by entering the following 6-digit verification code:</p>
          
          <div style="font-size: 32px; font-weight: 700; text-align: center; margin: 30px 0; padding: 15px; border-radius: 8px; background-color: #EEF2F6; border: 1px dashed #4F46E5; letter-spacing: 6px; color: #4F46E5;">
            {otp_code}
          </div>
          
          <p style="font-size: 14px; color: #6B7280; margin-bottom: 24px;">This code will expire in 15 minutes. If you did not request this code, please ignore this email.</p>
          <hr style="border: 0; border-top: 1px solid #E5E7EB; margin: 24px 0;" />
          <p style="font-size: 12px; color: #9CA3AF; text-align: center; margin: 0;">ProcureIQ AI-Powered Purchase Intelligence System</p>
        </div>
      </body>
    </html>
    """
    logger.info(f"Asynchronously dispatching OTP email to: {to_email}")
    # Offload the blocking smtplib operations to a worker thread
    await asyncio.to_thread(_send_sync_email, to_email, subject, html_content)
