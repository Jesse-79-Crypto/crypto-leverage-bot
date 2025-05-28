import smtplib
import os
import json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

class EnhancedProfitManager:
    def __init__(self):
        self.notification_email = os.getenv('NOTIFICATION_EMAIL')
        self.email_password = os.getenv('EMAIL_APP_PASSWORD')
        self.reserve_wallet = os.getenv('RESERVE_WALLET_ADDRESS')
        self.btc_wallet = os.getenv('BTC_WALLET_ADDRESS')
        self.system_start_date = self._get_system_start_date()
        self.performance_history = []

        self.allocation_phases = {
            "growth_focus": {"reinvest": 0.80, "btc_stack": 0.15, "reserve": 0.05},
            "balanced_growth": {"reinvest": 0.70, "btc_stack": 0.20, "reserve": 0.10},
            "wealth_protection": {"reinvest": 0.60, "btc_stack": 0.20, "reserve": 0.20}
        }

    def _get_system_start_date(self):
        try:
            start_date_str = os.getenv('SYSTEM_START_DATE')
            if start_date_str:
                return datetime.fromisoformat(start_date_str)
            else:
                return datetime.now()
        except:
            return datetime.now()

    def get_months_running(self):
        delta = datetime.now() - self.system_start_date
        return delta.days // 30

    def get_current_phase(self, account_balance):
        months = self.get_months_running()
        if months <= 6:
            return "growth_focus", "Phase 1: Aggressive Growth"
        elif months <= 12:
            return "balanced_growth", "Phase 2: Balanced Approach"
        else:
            return "wealth_protection", "Phase 3: Wealth Protection"

    def get_dynamic_allocation(self, account_balance):
        phase_key, phase_name = self.get_current_phase(account_balance)
        allocation = self.allocation_phases[phase_key].copy()
        if account_balance > 50000:
            allocation["reinvest"] -= 0.05
            allocation["reserve"] += 0.05
        return {
            **allocation,
            "phase": phase_name,
            "phase_key": phase_key,
            "months_running": self.get_months_running()
        }

    def process_enhanced_profit(self, profit_amount, account_balance, trade_data=None):
        try:
            if profit_amount <= 0:
                return self._handle_loss(profit_amount, account_balance, trade_data)
            allocation = self.get_dynamic_allocation(account_balance)
            reinvest_amount = profit_amount * allocation["reinvest"]
            btc_amount = profit_amount * allocation["btc_stack"]
            reserve_amount = profit_amount * allocation["reserve"]
            profit_data = {
                "total_profit": profit_amount,
                "reinvest_amount": reinvest_amount,
                "btc_amount": btc_amount,
                "reserve_amount": reserve_amount,
                "allocation_ratios": allocation,
                "new_balance": account_balance + reinvest_amount,
                "cumulative_btc": self._get_cumulative_btc() + btc_amount,
                "cumulative_reserve": self._get_cumulative_reserve() + reserve_amount,
                "trade_data": trade_data,
                "timestamp": datetime.now().isoformat()
            }
            self._send_enhanced_profit_notification(profit_data)
            self._update_performance_history(profit_data)
            self._check_strategy_evolution(profit_data)
            return profit_data
        except Exception as e:
            logging.error(f"Enhanced profit processing error: {str(e)}")
            return None

    def _handle_loss(self, loss_amount, account_balance, trade_data):
        loss_data = {
            "loss_amount": abs(loss_amount),
            "remaining_balance": account_balance,
            "protected_wealth": {
                "btc_stack": self._get_cumulative_btc(),
                "reserve_fund": self._get_cumulative_reserve(),
                "total_protected": self._get_cumulative_btc() + self._get_cumulative_reserve()
            },
            "trade_data": trade_data,
            "avantis_rebate_eligible": self._check_rebate_eligibility(loss_amount),
            "timestamp": datetime.now().isoformat()
        }
        self._send_enhanced_loss_notification(loss_data)
        return loss_data

    def _send_enhanced_profit_notification(self, profit_data):
        subject = f"🚀 Elite Profit Alert: ${profit_data['total_profit']:.2f} - {profit_data['allocation_ratios']['phase']}"
        html_body = "<html><body><h1>Profit Notification</h1></body></html>"
        self._send_email(subject, html_body)

    def _send_enhanced_loss_notification(self, loss_data):
        subject = f"⚠️ Trade Loss: ${loss_data['loss_amount']:.2f} - Wealth Protected"
        html_body = "<html><body><h1>Loss Notification</h1></body></html>"
        self._send_email(subject, html_body)

    def _send_email(self, subject, html_body):
        try:
            if not self.notification_email or not self.email_password:
                logging.warning("Email credentials not configured")
                return
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.notification_email
            msg['To'] = self.notification_email
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.notification_email, self.email_password)
                server.send_message(msg)
            logging.info("✅ Email notification sent successfully")
        except Exception as e:
            logging.error(f"Email notification error: {str(e)}")

    def _get_cumulative_btc(self):
        return 0.0

    def _get_cumulative_reserve(self):
        return 0.0

    def _update_performance_history(self, profit_data):
        self.performance_history.append(profit_data)

    def _check_strategy_evolution(self, profit_data):
        allocation = profit_data['allocation_ratios']
        if allocation['phase_key'] != self.get_current_phase(profit_data['new_balance'])[0]:
            logging.info(f"🔄 Strategy evolution: Moving to {allocation['phase']}")

    def _check_rebate_eligibility(self, loss_amount):
        return abs(loss_amount) >= 10

    def get_performance_summary(self):
        return {
            "system_age_days": (datetime.now() - self.system_start_date).days,
            "current_phase": self.get_current_phase(1500)[1],
            "total_trades": len(self.performance_history),
            "total_btc_accumulated": self._get_cumulative_btc(),
            "total_reserve_accumulated": self._get_cumulative_reserve(),
            "last_updated": datetime.now().isoformat()
        }
