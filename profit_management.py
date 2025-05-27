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

       

        # 🆕 Enhanced tracking

        self.system_start_date = self._get_system_start_date()

        self.performance_history = []

        

        # 🎯 Dynamic allocation phases

        self.allocation_phases = {

            "growth_focus": {"reinvest": 0.80, "btc_stack": 0.15, "reserve": 0.05},

            "balanced_growth": {"reinvest": 0.70, "btc_stack": 0.20, "reserve": 0.10},

            "wealth_protection": {"reinvest": 0.60, "btc_stack": 0.20, "reserve": 0.20}

        }

   

    def _get_system_start_date(self):

        """Get system start date (store in file or env var)"""

        try:

            start_date_str = os.getenv('SYSTEM_START_DATE')

            if start_date_str:

                return datetime.fromisoformat(start_date_str)

            else:

                # Default to today if not set

                return datetime.now()

       except:

            return datetime.now()

   

    def get_months_running(self):

        """Calculate how many months the system has been running"""

        delta = datetime.now() - self.system_start_date

        return delta.days // 30

   

    def get_current_phase(self, account_balance):

        """Determine current profit allocation phase"""

        months = self.get_months_running()

       

        if months <= 6:

            return "growth_focus", "Phase 1: Aggressive Growth"

        elif months <= 12:

            return "balanced_growth", "Phase 2: Balanced Approach"

        else:

            return "wealth_protection", "Phase 3: Wealth Protection"

   

    def get_dynamic_allocation(self, account_balance):

        """Get dynamic allocation ratios based on account size and time"""

        phase_key, phase_name = self.get_current_phase(account_balance)

        allocation = self.allocation_phases[phase_key].copy()

       

        # Add account size adjustments for very large accounts

        if account_balance > 50000:

            # More conservative for large accounts

            allocation["reinvest"] -= 0.05

            allocation["reserve"] += 0.05

       

        return {

            **allocation,

            "phase": phase_name,

            "phase_key": phase_key,

            "months_running": self.get_months_running()

        }

   

    def process_enhanced_profit(self, profit_amount, account_balance, trade_data=None):

        """Process profits with enhanced dynamic allocation"""

        try:

            if profit_amount <= 0:

                return self._handle_loss(profit_amount, account_balance, trade_data)

           

            # Get dynamic allocation

            allocation = self.get_dynamic_allocation(account_balance)

           

            # Calculate amounts

            reinvest_amount = profit_amount * allocation["reinvest"]

            btc_amount = profit_amount * allocation["btc_stack"]

            reserve_amount = profit_amount * allocation["reserve"]

           

            # Enhanced profit data

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

           

            # Send enhanced notifications

            self._send_enhanced_profit_notification(profit_data)

           

            # Update tracking

            self._update_performance_history(profit_data)

           

            # Check for strategy evolution

            self._check_strategy_evolution(profit_data)

           

            return profit_data

           

        except Exception as e:

            logging.error(f"Enhanced profit processing error: {str(e)}")

            return None

   

    def _handle_loss(self, loss_amount, account_balance, trade_data):

        """Handle losses with enhanced emotional support"""

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

        """Send enhanced profit notification with dynamic insights"""

       

        subject = f"🚀 Elite Profit Alert: ${profit_data['total_profit']:.2f} - {profit_data['allocation_ratios']['phase']}"

       

        html_body = f"""

       <!DOCTYPE html>

        <html>

        <head>

            <style>

                .profit-container {{

                    background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);

                    color: white; padding: 30px; border-radius: 15px; font-family: Arial; margin: 20px 0;

                }}

                .allocation-card {{

                    background: rgba(255,255,255,0.1); padding: 15px; margin: 10px 0; border-radius: 8px;

                }}

                .phase-banner {{

                    background: linear-gradient(90deg, #FF6B6B, #4ECDC4);

                    padding: 15px; text-align: center; border-radius: 10px; margin: 15px 0;

                    font-size: 18px; font-weight: bold;

                }}

                .metrics {{ display: flex; justify-content: space-between; margin: 20px 0; }}

                .metric {{ text-align: center; }}

                .metric-value {{ font-size: 24px; font-weight: bold; }}

                .progress-bar {{

                    background: rgba(255,255,255,0.3); height: 10px; border-radius: 5px; overflow: hidden;

                }}

                .progress-fill {{ background: #FFD700; height: 100%; transition: width 0.3s ease; }}

            </style>

        </head>

        <body>

            <div class="profit-container">

                <h2>🎯 Elite Profit Management System</h2>

                <div class="phase-banner">

                    {profit_data['allocation_ratios']['phase']}

                    (Month {profit_data['allocation_ratios']['months_running']})

                </div>

               

                <h3>💰 Profit Breakdown: ${profit_data['total_profit']:.2f}</h3>

               

                <div class="allocation-card">

                    <h4>🔄 Reinvest ({profit_data['allocation_ratios']['reinvest']*100:.0f}%)</h4>

                    <div class="metric-value">${profit_data['reinvest_amount']:.2f}</div>

                    <p>Automatically compounding for accelerated growth</p>

                    <div class="progress-bar">

                        <div class="progress-fill" style="width: {profit_data['allocation_ratios']['reinvest']*100}%"></div>

                    </div>

                </div>

               

                <div class="allocation-card">

                    <h4>₿ BTC Stack ({profit_data['allocation_ratios']['btc_stack']*100:.0f}%)</h4>

                    <div class="metric-value">${profit_data['btc_amount']:.2f}</div>

                    <p>Building permanent wealth - NEVER lost to trading</p>

                    <p><strong>Total BTC Stack: ${profit_data['cumulative_btc']:.2f}</strong></p>

                    <div class="progress-bar">

                        <div class="progress-fill" style="width: {profit_data['allocation_ratios']['btc_stack']*100}%"></div>

                    </div>

                </div>

               

                <div class="allocation-card">

                    <h4>🏦 Reserve Fund ({profit_data['allocation_ratios']['reserve']*100:.0f}%)</h4>

                    <div class="metric-value">${profit_data['reserve_amount']:.2f}</div>

                    <p>Emotional protection - confidence during drawdowns</p>

                    <p><strong>Total Reserve: ${profit_data['cumulative_reserve']:.2f}</strong></p>

                    <div class="progress-bar">

                        <div class="progress-fill" style="width: {profit_data['allocation_ratios']['reserve']*100}%"></div>

                    </div>

                </div>

               

                <div style="margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.1); border-radius: 8px;">

                    <h4>📊 Wealth Summary</h4>

                    <p><strong>New Trading Balance:</strong> ${profit_data['new_balance']:.2f}</p>

                    <p><strong>Protected Wealth:</strong> ${profit_data['cumulative_btc'] + profit_data['cumulative_reserve']:.2f}</p>

                    <p><strong>Total Portfolio:</strong> ${profit_data['new_balance'] + profit_data['cumulative_btc'] + profit_data['cumulative_reserve']:.2f}</p>

                </div>

            </div>

        </body>

        </html>

        """

       

        self._send_email(subject, html_body)

   

    def _send_enhanced_loss_notification(self, loss_data):

        """Send enhanced loss notification with emotional support"""

       

        subject = f"⚠️ Trade Loss: ${loss_data['loss_amount']:.2f} - Wealth Protected"

        

        html_body = f"""

        <!DOCTYPE html>

        <html>

        <head>

            <style>

                .loss-container {{

                    background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%);

                    color: white; padding: 30px; border-radius: 15px; font-family: Arial; margin: 20px 0;

                }}

                .protection-card {{

                    background: rgba(255,255,255,0.1); padding: 15px; margin: 10px 0; border-radius: 8px;

                }}

                .protected-wealth {{

                    background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);

                    padding: 20px; border-radius: 10px; margin: 15px 0;

                }}

            </style>

        </head>

        <body>

            <div class="loss-container">

                <h2>⚠️ Trade Loss Alert</h2>

                <p><strong>Loss Amount:</strong> ${loss_data['loss_amount']:.2f}</p>

                <p><strong>Remaining Balance:</strong> ${loss_data['remaining_balance']:.2f}</p>

               

                <div class="protected-wealth">

                    <h3>🛡️ Your Wealth is PROTECTED</h3>

                    <p><strong>BTC Stack:</strong> ${loss_data['protected_wealth']['btc_stack']:.2f} (NEVER lost to trading)</p>

                    <p><strong>Reserve Fund:</strong> ${loss_data['protected_wealth']['reserve_fund']:.2f} (Emergency protection)</p>

                    <p><strong>Total Protected:</strong> ${loss_data['protected_wealth']['total_protected']:.2f}</p>

                </div>

               

                <div class="protection-card">

                    <h4>💪 Stay Strong - This is Why We Have Elite Risk Management</h4>

                    <p>• Your permanent wealth (BTC + Reserve) is untouchable</p>

                    <p>• This loss cannot affect your long-term wealth building</p>

                    <p>• The system continues working for your financial freedom</p>

                    {f"<p>• Avantis rebate eligible: {loss_data['avantis_rebate_eligible']}</p>" if loss_data.get('avantis_rebate_eligible') else ""}

                </div>

            </div>

        </body>

        </html>

        """

       

        self._send_email(subject, html_body)

   

    def _send_email(self, subject, html_body):

        """Send email notification"""

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

        """Get total BTC stack accumulated (implement storage)"""

        # TODO: Implement persistent storage

        return 0.0

   

    def _get_cumulative_reserve(self):

        """Get total reserve fund accumulated (implement storage)"""

        # TODO: Implement persistent storage 

        return 0.0

   

    def _update_performance_history(self, profit_data):

        """Update performance tracking"""

        self.performance_history.append(profit_data)

        # TODO: Implement persistent storage

    

    def _check_strategy_evolution(self, profit_data):

        """Check if strategy should evolve to next phase"""

        allocation = profit_data['allocation_ratios']

       

        if allocation['phase_key'] != self.get_current_phase(profit_data['new_balance'])[0]:

            logging.info(f"🔄 Strategy evolution: Moving to {allocation['phase']}")

            # TODO: Send evolution notification

   

    def _check_rebate_eligibility(self, loss_amount):

        """Check if loss qualifies for Avantis rebate"""

        return abs(loss_amount) >= 10  # Example threshold

   

    def get_performance_summary(self):

        """Get comprehensive performance summary"""

        return {

            "system_age_days": (datetime.now() - self.system_start_date).days,

            "current_phase": self.get_current_phase(1500)[1],  # Default balance

            "total_trades": len(self.performance_history),

            "total_btc_accumulated": self._get_cumulative_btc(),

            "total_reserve_accumulated": self._get_cumulative_reserve(),

            "last_updated": datetime.now().isoformat()

        }

 

# Export main class
