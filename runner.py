import os

import json

import logging

from datetime import datetime

from flask import Flask, request, jsonify

import gspread

from google.oauth2.service_account import Credentials

from avantis_trading_module import AvantisTrader

from profit_management import create_elite_profit_manager

 

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - [AVANTIS] %(message)s',

    handlers=[logging.StreamHandler()]

)

logger = logging.getLogger(__name__)

 

app = Flask(__name__)

 

WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-key')

 

trader = AvantisTrader()

profit_manager = create_elite_profit_manager(trader)

 

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

 

@app.route('/health', methods=['GET'])

def health_check():

    return jsonify({

        'status': 'healthy',

        'platform': 'Avantis Finance',

        'network': 'Base',

        'features': [

            '20x better capital efficiency',

            'Zero fees (Season 2)',

            'Elite profit management',

            '22+ trading assets',

            'XP farming active',

            'Dynamic strategy scaling'

        ],

        'profit_management': profit_manager.get_elite_summary(),

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

           

            elite_trade_result = {

                'pair': symbol,

                'direction': direction.upper(),

                'collateral': collateral,

                'leverage': leverage,

                'notional_value': collateral * leverage,

                'tier': tier,

                'regime': regime

            }

           

            profit_manager.notify_trade_opened(elite_trade_result)

           

            logger.info(f"✅ [AVANTIS] Position opened successfully: {symbol} {direction} ${collateral:.2f} @ {leverage}x")

            return {

                'status': 'success',

                'message': f"Opened {direction} {symbol} position",

                'collateral': collateral,

                'leverage': leverage,

                'position_size': collateral * leverage,

                'platform': 'Avantis Finance',

                'profit_strategy': profit_manager.get_elite_summary()['current_strategy']

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

           

            position_data = {

               'symbol': symbol,

                'direction': target_position.get('direction', 'UNKNOWN')

            }

           

            profit_manager.notify_trade_closed(position_data, pnl)

           

            logger.info(f"✅ [AVANTIS] Position closed: {symbol} P&L: ${pnl:+.2f}")

            return {

                'status': 'success',

                'message': f"Closed {symbol} position",

                'pnl': pnl,

                'balance': new_balance,

                'platform': 'Avantis Finance',

                'elite_summary': profit_manager.get_elite_summary()

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

        elite_summary = profit_manager.get_elite_summary()

       

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

            'elite_profit_management': elite_summary,

            'capital_efficiency_improvement': '2000% vs Gains Network',

            'timestamp': datetime.now().isoformat()

        })

    except Exception as e:

        logger.error(f"❌ Status error: {e}")

        return jsonify({'error': str(e)}), 500

 

@app.route('/elite-summary', methods=['GET'])

def get_elite_summary():

    try:

        return jsonify({

            'elite_profit_management': profit_manager.get_elite_summary(),

            'setup_status': 'Complete - Elite System Active',

            'wealth_building_features': [

                'Dynamic strategy scaling by balance',

                'BTC stack building automation',

                'Reserve wallet protection',

                'Emotional trading protection',

                'Zero-fee compounding on Avantis'

            ]

        })

    except Exception as e:

        logger.error(f"❌ Elite summary error: {e}")

        return jsonify({'error': str(e)}), 500

 

if __name__ == '__main__':

    logger.info("🔥 Starting Elite Avantis Trading Bot...")

    logger.info("🚀 Capital Efficiency: 2000% improvement vs Gains Network")

    logger.info("💰 Fees: $0 vs $5-20 per trade")

    logger.info("📊 Assets: 22+ vs 2 assets")

    logger.info("🏆 Elite Profit Management: Active")

   

    elite_summary = profit_manager.get_elite_summary()

    logger.info(f"💎 Strategy: {elite_summary['current_strategy']}")

    logger.info(f"🎯 Wealth Protection: {elite_summary['wealth_protection_rate']}")

   

    port = int(os.environ.get('PORT', 5000))

    app.run(host='0.0.0.0', port=port, debug=False)

