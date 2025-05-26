import os

import json

import logging

import smtplib

from datetime import datetime

from email.mime.text import MIMEText

from email.mime.multipart import MIMEMultipart

from flask import Flask, request, jsonify

import gspread

from google.oauth2.service_account import Credentials

from avantis_trading_module import AvantisTrader

 

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - [AVANTIS] %(message)s',

    handlers=[logging.StreamHandler()]

)

logger = logging.getLogger(__name__)

 

app = Flask(__name__)

 

WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-key')

NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL', '')

EMAIL_APP_PASSWORD = os.getenv('EMAIL_APP_PASSWORD', '')

RESERVE_WALLET_ADDRESS = os.getenv('RESERVE_WALLET_ADDRESS', '')

BTC_WALLET_ADDRESS = os.getenv('BTC_WALLET_ADDRESS', '')

 

trader = AvantisTrader()

 

def setup_google_sheets():

    try:

        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')

        if not credentials_json:

            logger.warning("No Google credentials found - sheet logging disabled")

            return None

           

        credentials_dict = json.loads(credentials_json)

        credentials = Credentials.from_service_account_info(

            credentials_dict,

            scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

        )

       

        gc = gspread.authorize(credentials)

        sheet_id = os.getenv('TRADE_LOG_SHEET_ID')

        tab_name = os.getenv('TRADE_LOG_TAB_NAME', 'Elite Trade Log')

       

        if sheet_id:

            sheet = gc.open_by_key(sheet_id).worksheet(tab_name)

            return sheet

    except Exception as e:

        logger.error(f"Google Sheets setup failed: {e}")

    return None

 

google_sheet = setup_google_sheets()

 

def log_to_sheet(data):

    if not google_sheet:

        return

       

    try:

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        row = [

            timestamp,

            data.get('action', ''),

            data.get('symbol', ''),

            data.get('direction', ''),

            data.get('collateral', ''),

            data.get('leverage', ''),

            data.get('position_size', ''),

            data.get('tier', ''),

            data.get('pnl', ''),

            data.get('balance', ''),

            'Avantis Finance'

        ]

        google_sheet.append_row(row)

        logger.info("✅ Trade logged to Google Sheets")

    except Exception as e:

        logger.error(f"❌ Sheet logging failed: {e}")

 

def send_email_notification(subject, html_content):

    if not NOTIFICATION_EMAIL or not EMAIL_APP_PASSWORD:

        logger.warning("Email credentials not configured - skipping notification")

        return

       

    try:

        msg = MIMEMultipart('alternative')

        msg['Subject'] = f"🔥 Avantis Trading Bot - {subject}"

        msg['From'] = NOTIFICATION_EMAIL

        msg['To'] = NOTIFICATION_EMAIL

       

        html_part = MIMEText(html_content, 'html')

        msg.attach(html_part)

       

        with smtplib.SMTP('smtp.gmail.com', 587) as server:

            server.starttls()

            server.login(NOTIFICATION_EMAIL, EMAIL_APP_PASSWORD)

            server.send_message(msg)

           

        logger.info("📧 Email notification sent successfully")

    except Exception as e:

        logger.error(f"❌ Email notification failed: {e}")

 

def format_trade_opened_email(trade_data):

    return f"""

    <!DOCTYPE html>

    <html>

    <head>

        <meta charset="utf-8">

        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>Trade Opened</title>

        <style>

            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background: #f8f9fa; }}

            .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}

            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}

            .content {{ padding: 30px; }}

            .trade-details {{ background: #f8f9ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}

            .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #e9ecef; }}

            .label {{ font-weight: 600; color: #495057; }}

            .value {{ color: #212529; font-weight: 500; }}

            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 14px; }}

            .logo {{ font-size: 24px; margin-bottom: 10px; }}

        </style>

    </head>

    <body>

        <div class="container">

            <div class="header">

                <div class="logo">🚀</div>

                <h1 style="margin: 0; font-size: 28px;">Trade Opened</h1>

                <p style="margin: 10px 0 0 0; opacity: 0.9;">Avantis Finance • Base Network</p>

            </div>

            <div class="content">

                <div class="trade-details">

                    <div class="detail-row">

                        <span class="label">Symbol:</span>

                        <span class="value">{trade_data.get('symbol', 'N/A')}</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Direction:</span>

                        <span class="value">{"🟢 LONG" if trade_data.get('direction') == 'long' else "🔴 SHORT"}</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Collateral:</span>

                        <span class="value">${trade_data.get('collateral', 0):.2f} USDC</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Leverage:</span>

                        <span class="value">{trade_data.get('leverage', 1)}x</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Position Size:</span>

                        <span class="value">${trade_data.get('position_size', 0):.2f}</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Signal Tier:</span>

                        <span class="value">Tier {trade_data.get('tier', 'N/A')}</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">Market Regime:</span>

                        <span class="value">{trade_data.get('regime', 'Normal')}</span>

                    </div>

                </div>

                <p><strong>🎯 Position active with multiple take-profit levels</strong></p>

                <p>⚡ Zero fees during Season 2<br>

                🛡️ Up to 20% loss protection rebate<br>

                📊 XP farming for future airdrops</p>

            </div>

            <div class="footer">

                <p>Elite Trading • Capital Efficiency Revolution • 60/20/20 Wealth Strategy</p>

            </div>

        </div>

    </body>

    </html>

    """

 

def format_trade_closed_email(trade_data, is_profit=True):

    pnl = float(trade_data.get('pnl', 0))

   

    if is_profit and pnl > 0:

        reinvest_amount = pnl * 0.60

        btc_amount = pnl * 0.20

        reserve_amount = pnl * 0.20

       

        profit_breakdown = f"""

        <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px; padding: 20px; margin: 20px 0;">

            <h3 style="color: #155724; margin-top: 0;">💰 Elite Profit Management (60/20/20)</h3>

            <div class="detail-row">

                <span class="label">🔁 Reinvest (60%):</span>

                <span class="value" style="color: #28a745; font-weight: bold;">${reinvest_amount:.2f}</span>

            </div>

            <div class="detail-row">

                <span class="label">₿ BTC Stack (20%):</span>

                <span class="value" style="color: #f57c00; font-weight: bold;">${btc_amount:.2f}</span>

            </div>

            <div class="detail-row">

                <span class="label">🏦 Reserve (20%):</span>

                <span class="value" style="color: #6f42c1; font-weight: bold;">${reserve_amount:.2f}</span>

            </div>

        </div>

        <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 15px; margin: 15px 0;">

            <h4 style="color: #856404; margin-top: 0;">📋 Action Items:</h4>

            <ul style="margin: 10px 0; padding-left: 20px; color: #856404;">

                <li><strong>${reinvest_amount:.2f}</strong> stays in account for compounding</li>

                <li>Convert <strong>${btc_amount:.2f}</strong> to Bitcoin weekly</li>

                <li>Transfer <strong>${reserve_amount:.2f}</strong> to backup wallet</li>

            </ul>

        </div>

        """

        header_color = "linear-gradient(135deg, #28a745 0%, #20c997 100%)"

        status_emoji = "🎉"

        status_text = "PROFIT"

    else:

        profit_breakdown = f"""

        <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 20px; margin: 20px 0;">

            <h3 style="color: #721c24; margin-top: 0;">📊 Loss Information</h3>

            <p style="color: #721c24; margin: 10px 0;">

                🛡️ Check if you're eligible for Avantis loss protection rebate (up to 20%)<br>

                💪 Your BTC stack and reserve funds remain protected<br>

                🔄 Ready for the next opportunity

            </p>

        </div>

        """

        header_color = "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"

        status_emoji = "📊"

        status_text = "CLOSED"

   

    return f"""

    <!DOCTYPE html>

    <html>

    <head>

        <meta charset="utf-8">

        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>Trade Closed</title>

        <style>

            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background: #f8f9fa; }}

            .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}

            .header {{ background: {header_color}; color: white; padding: 30px; text-align: center; }}

            .content {{ padding: 30px; }}

            .trade-details {{ background: #f8f9ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}

            .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #e9ecef; }}

            .label {{ font-weight: 600; color: #495057; }}

            .value {{ color: #212529; font-weight: 500; }}

            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 14px; }}

            .logo {{ font-size: 24px; margin-bottom: 10px; }}

        </style>

    </head>

    <body>

        <div class="container">

            <div class="header">

                <div class="logo">{status_emoji}</div>

                <h1 style="margin: 0; font-size: 28px;">Trade {status_text}</h1>

                <p style="margin: 10px 0 0 0; opacity: 0.9;">Avantis Finance • Base Network</p>

            </div>

            <div class="content">

                <div class="trade-details">

                    <div class="detail-row">

                        <span class="label">Symbol:</span>

                        <span class="value">{trade_data.get('symbol', 'N/A')}</span>

                    </div>

                    <div class="detail-row">

                        <span class="label">P&L:</span>

                        <span class="value" style="color: {'#28a745' if pnl > 0 else '#dc3545'}; font-weight: bold; font-size: 18px;">

                            ${pnl:+.2f} USDC

                        </span>

                    </div>

                    <div class="detail-row">

                        <span class="label">New Balance:</span>

                        <span class="value">${trade_data.get('balance', 0):.2f} USDC</span>

                    </div>

                </div>

                {profit_breakdown}

            </div>

            <div class="footer">

                <p>Elite Trading • Capital Efficiency Revolution • Building Unstoppable Wealth</p>

            </div>

        </div>

    </body>

    </html>

    """

 

@app.route('/health', methods=['GET'])

def health_check():

    return jsonify({

        'status': 'healthy',

        'platform': 'Avantis Finance',

        'network': 'Base',

        'features': [

            '20x better capital efficiency',

            'Zero fees (Season 2)',

            'Multiple take-profit levels',

            '22+ trading assets',

            'XP farming active',

            'Loss protection rebates'

        ],

        'timestamp': datetime.now().isoformat()

    })

 

@app.route('/webhook', methods=['POST'])

def handle_webhook():

    try:

        provided_secret = request.headers.get('X-Webhook-Secret', '')

        if provided_secret != WEBHOOK_SECRET:

            logger.warning(f"❌ Invalid webhook secret: {provided_secret}")

            return jsonify({'error': 'Invalid webhook secret'}), 401

       

        data = request.get_json()

        if not data:

            return jsonify({'error': 'No data provided'}), 400

           

        logger.info(f"🎯 [AVANTIS] Received signal: {data}")

       

        action = data.get('action', '').lower()

       

        if action == 'open':

            result = handle_open_trade(data)

        elif action == 'close':

            result = handle_close_trade(data)

        else:

            logger.warning(f"❌ Unknown action: {action}")

            return jsonify({'error': f'Unknown action: {action}'}), 400

           

        return jsonify(result)

       

    except Exception as e:

        logger.error(f"❌ Webhook error: {e}")

        return jsonify({'error': str(e)}), 500

 

def handle_open_trade(data):

    try:

        symbol = data.get('symbol', '').upper()

        direction = data.get('direction', '').lower()

        tier = data.get('tier', 2)

        regime = data.get('regime', 'normal')

       

        logger.info(f"🚀 [AVANTIS] Opening {direction} position on {symbol} (Tier {tier}, {regime} regime)")

       

        balance = trader.get_balance()

       

        if tier == 1:

            size_percentage = 0.25

        else:

            size_percentage = 0.18

           

        if regime.lower() == 'bear':

            size_percentage *= 0.8

        elif regime.lower() == 'bull':

            size_percentage *= 1.1

           

        collateral = balance * size_percentage

       

        if collateral < 10:

            logger.warning(f"⚠️ Collateral ${collateral:.2f} below $10 minimum")

            return {'status': 'skipped', 'reason': 'Insufficient collateral for minimum trade'}

       

        if symbol in ['BTC', 'ETH', 'BTCUSD', 'ETHUSD']:

            leverage = 5 if tier == 1 else 7

        elif symbol.endswith('USD') and len(symbol) == 6:

            leverage = 10 if tier == 1 else 15

        else:

            leverage = 5 if tier == 1 else 10

           

        result = trader.open_position(

            symbol=symbol,

            direction=direction,

            collateral=collateral,

            leverage=leverage

        )

       

        if result.get('success'):

            trade_data = {

                'action': 'OPEN',

                'symbol': symbol,

                'direction': direction.upper(),

                'collateral': f"{collateral:.2f}",

                'leverage': leverage,

                'position_size': f"{collateral * leverage:.2f}",

                'tier': tier,

                'regime': regime,

                'balance': f"{balance:.2f}"

            }

           

            log_to_sheet(trade_data)

           

            send_email_notification(

                f"{direction.upper()} {symbol} Opened",

                format_trade_opened_email({

                    'symbol': symbol,

                    'direction': direction,

                    'collateral': collateral,

                    'leverage': leverage,

                    'position_size': collateral * leverage,

                    'tier': tier,

                    'regime': regime

                })

            )

           

            logger.info(f"✅ [AVANTIS] Position opened successfully: {symbol} {direction} ${collateral:.2f} @ {leverage}x")

            return {

                'status': 'success',

                'message': f"Opened {direction} {symbol} position",

                'collateral': collateral,

                'leverage': leverage,

                'position_size': collateral * leverage,

                'platform': 'Avantis Finance'

            }

        else:

            logger.error(f"❌ [AVANTIS] Failed to open position: {result.get('error')}")

            return {'status': 'error', 'message': result.get('error')}

           

    except Exception as e:

        logger.error(f"❌ [AVANTIS] Open trade error: {e}")

        return {'status': 'error', 'message': str(e)}

 

def handle_close_trade(data):

    try:

        symbol = data.get('symbol', '').upper()

        reason = data.get('reason', 'signal')

       

        logger.info(f"🎯 [AVANTIS] Closing position on {symbol} (reason: {reason})")

       

        positions = trader.get_positions()

        target_position = None

       

        for pos in positions:

            if pos.get('symbol') == symbol:

                target_position = pos

                break

               

        if not target_position:

            logger.warning(f"⚠️ No open position found for {symbol}")

            return {'status': 'skipped', 'reason': f'No open position for {symbol}'}

       

        result = trader.close_position(symbol)

       

        if result.get('success'):

            pnl = result.get('pnl', 0)

            new_balance = trader.get_balance()

           

            trade_data = {

                'action': 'CLOSE',

                'symbol': symbol,

                'pnl': f"{pnl:.2f}",

                'balance': f"{new_balance:.2f}",

                'reason': reason

            }

           

            log_to_sheet(trade_data)

           

            send_email_notification(

                f"{symbol} Closed - ${pnl:+.2f}",

                format_trade_closed_email({

                    'symbol': symbol,

                    'pnl': pnl,

                    'balance': new_balance

                }, is_profit=(pnl > 0))

            )

           

            logger.info(f"✅ [AVANTIS] Position closed: {symbol} P&L: ${pnl:+.2f}")

            return {

                'status': 'success',

                'message': f"Closed {symbol} position",

                'pnl': pnl,

                'balance': new_balance,

                'platform': 'Avantis Finance'

            }

        else:

            logger.error(f"❌ [AVANTIS] Failed to close position: {result.get('error')}")

            return {'status': 'error', 'message': result.get('error')}

           

    except Exception as e:

        logger.error(f"❌ [AVANTIS] Close trade error: {e}")

        return {'status': 'error', 'message': str(e)}

 

@app.route('/status', methods=['GET'])

def get_status():

    try:

        balance = trader.get_balance()

        positions = trader.get_positions()

       

        return jsonify({

            'platform': 'Avantis Finance',

            'network': 'Base',

            'balance': f"${balance:.2f} USDC",

            'open_positions': len(positions),

            'positions': positions,

            'features': {

                'minimum_trade': '$10 (vs $200+ on Gains)',

                'trading_fees': '$0 (Season 2)',

                'assets': '22+ (crypto, forex, commodities)',

                'take_profits': 'TP1, TP2, TP3',

                'loss_protection': 'Up to 20% rebate',

                'xp_farming': 'Active for airdrops'

            },

            'profit_strategy': '60/20/20 Elite Wealth Management',

            'timestamp': datetime.now().isoformat()

        })

    except Exception as e:

        logger.error(f"❌ Status error: {e}")

        return jsonify({'error': str(e)}), 500

 

if __name__ == '__main__':

    logger.info("🚀 Starting Avantis Trading Bot...")

    logger.info("🔥 Capital Efficiency: 2000% improvement vs Gains Network")

    logger.info("💰 Fees: $0 vs $5-20 per trade")

    logger.info("📊 Assets: 22+ vs 2 assets")

    logger.info("🎯 Strategy: 60/20/20 Elite Wealth Management")

   

    port = int(os.environ.get('PORT', 5000))

   app.run(host='0.0.0.0', port=port, debug=False)

