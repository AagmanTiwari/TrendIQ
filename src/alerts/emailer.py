"""
src/alerts/emailer.py
Sends price-drop alert emails via Gmail SMTP (or any SMTP server).

Required .env keys:
    ALERT_EMAIL_FROM   – sender Gmail address
    ALERT_EMAIL_PASS   – Gmail App Password (not your login password)
    ALERT_EMAIL_TO     – recipient email address (can be same as FROM)
"""
import os
import sys
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.exception import CustomException

logger = logging.getLogger(__name__)


class PriceAlertEmailer:

    def __init__(self):
        self.sender = os.getenv("ALERT_EMAIL_FROM", "")
        self.password = os.getenv("ALERT_EMAIL_PASS", "")
        self.recipient = os.getenv("ALERT_EMAIL_TO", self.sender)

    def is_configured(self) -> bool:
        return bool(self.sender and self.password)

    def send_alert(self, product_name: str, alert: dict) -> bool:
        """
        Send a price-drop alert email.
        Returns True on success, False on failure (never raises).
        """
        if not self.is_configured():
            logger.warning("Email not configured — skipping alert.")
            return False

        try:
            subject = f"TrendIQ Price Drop Alert: {product_name}"
            html = self._build_html(product_name, alert)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = self.recipient
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())

            logger.info(f"Alert email sent for '{product_name}' to {self.recipient}.")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    @staticmethod
    def _build_html(product_name: str, alert: dict) -> str:
        return f"""
        <html><body style="font-family:sans-serif;max-width:480px;margin:auto">
          <h2 style="color:#e05c2a">TrendIQ — Price Drop Alert</h2>
          <p>Good news! Our forecast predicts a price drop for:</p>
          <h3 style="color:#1a1a2e">{product_name}</h3>
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f5f5f5"><b>Current price</b></td>
                <td style="padding:8px">₹{alert.get('current_price', 'N/A')}</td></tr>
            <tr><td style="padding:8px;background:#f5f5f5"><b>Predicted low</b></td>
                <td style="padding:8px;color:#2a9d8f"><b>₹{alert.get('predicted_low', 'N/A')}</b></td></tr>
            <tr><td style="padding:8px;background:#f5f5f5"><b>Drop</b></td>
                <td style="padding:8px;color:#e76f51"><b>{alert.get('drop_pct', 0):.1f}%</b></td></tr>
            <tr><td style="padding:8px;background:#f5f5f5"><b>Expected by</b></td>
                <td style="padding:8px">{alert.get('expected_date', 'N/A')}</td></tr>
          </table>
          <p style="color:#888;font-size:12px;margin-top:24px">
            This is a machine-learning forecast and not a guarantee.<br>TrendIQ
          </p>
        </body></html>
        """