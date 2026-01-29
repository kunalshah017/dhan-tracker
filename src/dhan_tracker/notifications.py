"""Email notification service using Gmail SMTP."""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Email configuration for Gmail SMTP."""

    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = ""
    sender_password: str = ""  # Gmail App Password
    recipient_email: str = ""

    @classmethod
    def from_env(cls) -> "EmailConfig":
        """Load email config from environment variables."""
        return cls(
            sender_email=os.getenv("GMAIL_SENDER_EMAIL", ""),
            sender_password=os.getenv("GMAIL_APP_PASSWORD", ""),
            recipient_email=os.getenv(
                "NOTIFICATION_EMAIL", os.getenv("GMAIL_SENDER_EMAIL", "")),
        )

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(self.sender_email and self.sender_password and self.recipient_email)


class EmailNotifier:
    """Send email notifications for portfolio events."""

    def __init__(self, config: EmailConfig | None = None):
        self.config = config or EmailConfig.from_env()

    def is_configured(self) -> bool:
        """Check if email notifications are enabled."""
        return self.config.is_configured()

    def send_email(
        self,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> bool:
        """
        Send an email notification.

        Args:
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional, derived from HTML if not provided)

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            logger.warning("Email not configured - notification skipped")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.sender_email
            msg["To"] = self.config.recipient_email

            # Add plain text version
            if body_text:
                msg.attach(MIMEText(body_text, "plain"))

            # Add HTML version
            msg.attach(MIMEText(body_html, "html"))

            # Connect and send
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.sender_email,
                             self.config.sender_password)
                server.sendmail(
                    self.config.sender_email,
                    self.config.recipient_email,
                    msg.as_string()
                )

            logger.info(f"Email sent: {subject}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e}")
            logger.error("Check your Gmail App Password is correct")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_sl_trigger_notification(
        self,
        trading_symbol: str,
        quantity: int,
        trigger_price: float,
        executed_price: float | None,
        cost_price: float | None,
        pnl_amount: float | None,
        pnl_percent: float | None,
        protection_tier: str | None,
        order_id: str,
        order_status: str,
    ) -> bool:
        """
        Send notification when a stop loss order is triggered.

        Args:
            trading_symbol: Stock/ETF symbol
            quantity: Number of units sold
            trigger_price: SL trigger price
            executed_price: Actual execution price
            cost_price: Original cost price
            pnl_amount: P&L in rupees
            pnl_percent: P&L percentage
            protection_tier: Which protection tier triggered
            order_id: Dhan order ID
            order_status: TRADED, REJECTED, etc.

        Returns:
            True if notification sent
        """
        now = datetime.now()

        # Determine if profit or loss
        if pnl_amount is not None:
            pnl_color = "#28a745" if pnl_amount >= 0 else "#dc3545"
            pnl_sign = "+" if pnl_amount >= 0 else ""
            outcome = "PROFIT PROTECTED" if pnl_amount >= 0 else "LOSS LIMITED"
        else:
            pnl_color = "#6c757d"
            pnl_sign = ""
            outcome = "TRIGGERED"

        exec_price_str = f"₹{executed_price:.2f}" if executed_price else "Market"
        cost_str = f"₹{cost_price:.2f}" if cost_price else "N/A"
        pnl_str = f"{pnl_sign}₹{pnl_amount:.2f}" if pnl_amount is not None else "N/A"
        pnl_pct_str = f"({pnl_sign}{pnl_percent:.1f}%)" if pnl_percent is not None else ""

        subject = f"🔔 SL {outcome}: {trading_symbol} @ ₹{trigger_price:.2f}"

        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1a73e8; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .highlight {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid {pnl_color}; }}
        .label {{ color: #6c757d; font-size: 12px; text-transform: uppercase; }}
        .value {{ font-size: 18px; font-weight: bold; color: #333; }}
        .pnl {{ color: {pnl_color}; font-size: 24px; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        .footer {{ text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px; }}
        .status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
        .status-traded {{ background: #d4edda; color: #155724; }}
        .status-rejected {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">🔔 Stop Loss Triggered</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">{trading_symbol}</p>
        </div>
        <div class="content">
            <div class="highlight">
                <div class="label">P&L Result</div>
                <div class="pnl">{pnl_str} {pnl_pct_str}</div>
            </div>
            
            <div class="grid">
                <div class="highlight">
                    <div class="label">Quantity Sold</div>
                    <div class="value">{quantity} units</div>
                </div>
                <div class="highlight">
                    <div class="label">Trigger Price</div>
                    <div class="value">₹{trigger_price:.2f}</div>
                </div>
                <div class="highlight">
                    <div class="label">Executed At</div>
                    <div class="value">{exec_price_str}</div>
                </div>
                <div class="highlight">
                    <div class="label">Cost Price</div>
                    <div class="value">{cost_str}</div>
                </div>
            </div>
            
            <div class="highlight">
                <div class="label">Protection Strategy</div>
                <div class="value">{protection_tier or 'Stop Loss'}</div>
            </div>
            
            <div class="highlight">
                <div class="label">Order Details</div>
                <div class="value">
                    Order ID: {order_id}<br>
                    Status: <span class="status status-{'traded' if order_status == 'TRADED' else 'rejected'}">{order_status}</span>
                </div>
            </div>
            
            <div class="footer">
                <p>Dhan Portfolio Tracker • {now.strftime('%d %b %Y, %I:%M %p IST')}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        body_text = f"""
🔔 STOP LOSS {outcome}: {trading_symbol}

Quantity: {quantity} units
Trigger Price: ₹{trigger_price:.2f}
Executed At: {exec_price_str}
Cost Price: {cost_str}
P&L: {pnl_str} {pnl_pct_str}

Strategy: {protection_tier or 'Stop Loss'}
Order ID: {order_id}
Status: {order_status}

---
Dhan Portfolio Tracker
{now.strftime('%d %b %Y, %I:%M %p IST')}
"""

        return self.send_email(subject, body_html, body_text)

    def send_daily_summary(
        self,
        triggers: list[dict],
        total_pnl: float,
    ) -> bool:
        """
        Send a daily summary of all triggered orders.

        Args:
            triggers: List of trigger records from database
            total_pnl: Total P&L from all triggers

        Returns:
            True if sent successfully
        """
        if not triggers:
            logger.info("No triggers to summarize")
            return False

        now = datetime.now()
        pnl_color = "#28a745" if total_pnl >= 0 else "#dc3545"
        pnl_sign = "+" if total_pnl >= 0 else ""

        # Build trigger rows
        rows_html = ""
        for t in triggers:
            pnl = t.get("pnl_amount", 0) or 0
            row_color = "#28a745" if pnl >= 0 else "#dc3545"
            rows_html += f"""
            <tr>
                <td>{t['trading_symbol']}</td>
                <td>{t['quantity']}</td>
                <td>₹{t['trigger_price']:.2f}</td>
                <td style="color: {row_color}">{"+" if pnl >= 0 else ""}₹{pnl:.2f}</td>
                <td>{t['order_status']}</td>
            </tr>
            """

        subject = f"📊 Daily SL Summary: {len(triggers)} triggers, {pnl_sign}₹{total_pnl:.2f}"

        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1a73e8; color: white; padding: 20px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f1f3f4; }}
        .total {{ font-size: 24px; color: {pnl_color}; font-weight: bold; text-align: center; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Daily SL Summary</h1>
            <p>{now.strftime('%d %b %Y')}</p>
        </div>
        
        <div class="total">
            Total P&L: {pnl_sign}₹{total_pnl:.2f}
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Trigger</th>
                    <th>P&L</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

        return self.send_email(subject, body_html)


# Singleton instance
_notifier: EmailNotifier | None = None


def get_notifier() -> EmailNotifier:
    """Get the singleton email notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = EmailNotifier()
    return _notifier


def send_sl_trigger_email(
    trading_symbol: str,
    quantity: int,
    trigger_price: float,
    order_id: str,
    order_status: str,
    executed_price: float | None = None,
    cost_price: float | None = None,
    pnl_amount: float | None = None,
    pnl_percent: float | None = None,
    protection_tier: str | None = None,
) -> bool:
    """
    Convenience function to send SL trigger notification.

    Returns:
        True if email sent successfully
    """
    notifier = get_notifier()
    return notifier.send_sl_trigger_notification(
        trading_symbol=trading_symbol,
        quantity=quantity,
        trigger_price=trigger_price,
        executed_price=executed_price,
        cost_price=cost_price,
        pnl_amount=pnl_amount,
        pnl_percent=pnl_percent,
        protection_tier=protection_tier,
        order_id=order_id,
        order_status=order_status,
    )
