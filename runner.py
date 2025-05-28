from flask import Flask, request, jsonify

from datetime import datetime

import json

import os

from avantis_trading_module import AvantisTrader

from profit_management import EnhancedProfitManager as ProfitManager

import logging

 

app = Flask(__name__)

 

# ========================================

# 🚀 PERFORMANCE OPTIMIZATIONS IMPLEMENTED

# ========================================

 

# Enhanced Trading Parameters

MAX_OPEN_POSITIONS = 4  # ⬆️ Increased from 2

POSITION_COOLDOWN = 2   # ⬇️ Reduced from 3 minutes for faster deployment

MIN_SIGNAL_QUALITY = 75 # ✅ Maintained high quality threshold

 

# Enhanced Position Sizing

TIER_1_POSITION_SIZE = 0.25  # ✅ 25% allocation maintained

TIER_2_POSITION_SIZE = 0.18  # ✅ 18% allocation maintained

 

# Optimized Take Profit Levels by Market Regime

TP_LEVELS = {

    'BULL': {

        'TP1': 0.025,  # 2.5%

        'TP2': 0.055,  # 5.5%

        'TP3': 0.12    # 12%

    },

    'BEAR': {

        'TP1': 0.015,  # 1.5%

        'TP2': 0.035,  # 3.5%

        'TP3': 0.05    # 🎯 Optimized: 5% instead of 12-15%

    },

    'NEUTRAL': {

        'TP1': 0.02,   # 2%

        'TP2': 0.045,  # 4.5%

        'TP3': 0.08    # 8%

    }

}

 

# ========================================

# 📊 ENHANCED TRADE LOGGING SYSTEM (ELITE TRADE LOG SHEET)

# ========================================

 

class EnhancedTradeLogger:

    def __init__(self):

        # Elite Trade Log Sheet (separate from Signal Inbox)

        self.trade_log_sheet_id = os.getenv('ELITE_TRADE_LOG_SHEET_ID')

        self.trade_log_tab_name = os.getenv('ELITE_TRADE_LOG_TAB_NAME', 'Elite Trade Log')

       

        # Signal Inbox Sheet (for updating processed status)

        self.signal_inbox_sheet_id = os.getenv('SIGNAL_INBOX_SHEET_ID')

        self.signal_inbox_tab_name = os.getenv('SIGNAL_INBOX_TAB_NAME', 'Signal Inbox')

   

    def log_trade_entry(self, trade_data):

        """Log actual executed trade to Elite Trade Log sheet"""

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

       

        # Elite Trade Log entry (45 columns for actual trade tracking)

        trade_entry = {

            'Trade_ID': trade_data.get('avantis_position_id', 'PENDING'),

            'Timestamp': timestamp,

            'Symbol': trade_data['symbol'],

            'Direction': trade_data['direction'],

            'Entry_Price': trade_data['actual_entry_price'],  # Real fill price

            'Position_Size_USDC': trade_data['position_size'],

            'Leverage': trade_data['leverage'],

            'Collateral_Used': trade_data.get('collateral_used', 0),

            'Tier': trade_data['tier'],

            'Signal_Quality': trade_data['signal_quality'],

            'Market_Regime': trade_data['market_regime'],

            'Entry_Timestamp': timestamp,

           

            # Take Profit Levels (planned)

            'TP1_Price': trade_data['tp1_price'],

            'TP2_Price': trade_data['tp2_price'],

            'TP3_Price': trade_data['tp3_price'],

            'Stop_Loss_Price': trade_data['stop_loss'],

           

            # TP Tracking (initialized as pending)

            'TP1_Hit': 'Pending',

            'TP1_Hit_Time': 'N/A',

            'TP2_Hit': 'Pending',

            'TP2_Hit_Time': 'N/A',

            'TP3_Hit': 'Pending',           # 🆕 Enhanced TP3 tracking

            'TP3_Actual_Price': 'N/A',      # 🆕 Actual TP3 price

            'TP3_Hit_Time': 'N/A',          # 🆕 TP3 timestamp

            'TP3_Duration_Minutes': 'N/A',  # 🆕 Time to TP3

           

            # Performance metrics (to be updated on exit)

            'Exit_Price': 'OPEN',

            'Exit_Timestamp': 'OPEN',

            'Total_Duration_Minutes': 'OPEN',

            'PnL_USDC': 'OPEN',

            'PnL_Percentage': 'OPEN',

            'Final_Outcome': 'OPEN',

            'Fees_Paid': trade_data.get('estimated_fees', 0),

            'Net_Profit': 'OPEN',

           

            # Context

            'Market_Session': self._get_market_session(),

            'Day_of_Week': datetime.now().weekday(),

            'Manual_Notes': f'Tier {trade_data["tier"]} signal, Quality: {trade_data["signal_quality"]}'

        }

       

        # Log to Elite Trade Log sheet (not Signal Inbox)

        self._append_to_elite_trade_log(trade_entry)

       

        # Update Signal Inbox to mark signal as processed

        self._mark_signal_processed(trade_data.get('signal_timestamp'))

       

        return trade_entry

   

    def log_trade_exit(self, trade_id, exit_data):

        """Log trade exit with comprehensive TP3 tracking"""

        exit_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

       

        exit_info = {

            'Exit_Price': exit_data['exit_price'],

            'Exit_Timestamp': exit_timestamp,

            'PnL_USDC': exit_data['pnl'],

            'PnL_Percentage': exit_data.get('pnl_percentage', 0),

            'Final_Outcome': exit_data['outcome'],  # 'TP1', 'TP2', 'TP3', 'SL'

            'Fees_Paid': exit_data.get('actual_fees', 0),

            'Net_Profit': exit_data['pnl'] - exit_data.get('actual_fees', 0),

            'Total_Duration_Minutes': exit_data.get('duration_minutes', 0)

        }

       

        # 🆕 Enhanced TP3 tracking

        if exit_data['outcome'] == 'TP3':

            exit_info.update({

                'TP3_Hit': '✅',

                'TP3_Actual_Price': exit_data['exit_price'],

                'TP3_Hit_Time': exit_timestamp,

                'TP3_Duration_Minutes': exit_data.get('duration_minutes', 0)

            })

        elif exit_data['outcome'] == 'TP2':

            exit_info.update({

                'TP2_Hit': '✅',

                'TP2_Hit_Time': exit_timestamp,

                'TP3_Hit': '❌'  # Didn't reach TP3

            })

        elif exit_data['outcome'] == 'TP1':

            exit_info.update({

                'TP1_Hit': '✅',

                'TP1_Hit_Time': exit_timestamp,

                'TP2_Hit': '❌',

                'TP3_Hit': '❌'

            })

        elif 'partial' in exit_data.get('outcome', '').lower():

            exit_info.update({

                'TP3_Hit': 'Partial',

                'TP3_Actual_Price': exit_data.get('partial_exit_price', ''),

                'TP3_Hit_Time': exit_timestamp

            })

        else:

            # Stop loss or manual exit

            exit_info.update({

                'TP1_Hit': '❌',

                'TP2_Hit': '❌',

                'TP3_Hit': '❌'

            })

       

        # Update Elite Trade Log row

        self._update_trade_log_row(trade_id, exit_info)

       

        return exit_info

   

    def _append_to_elite_trade_log(self, trade_entry):

        """Append new trade to Elite Trade Log sheet"""

        try:

            # This would integrate with your Google Sheets API

            # For now, logging the structure

            logging.info(f"Elite Trade Log Entry: {trade_entry['Symbol']} {trade_entry['Direction']}")

           

            # TODO: Implement actual Google Sheets API call

            # self.sheets_client.values().append(

            #     spreadsheetId=self.trade_log_sheet_id,

            #     range=f"{self.trade_log_tab_name}!A:AX",  # 45 columns

            #     body={'values': [list(trade_entry.values())]},

            #     valueInputOption='RAW'

            # ).execute()

           

        except Exception as e:

            logging.error(f"Elite Trade Log append error: {str(e)}")

   

    def _mark_signal_processed(self, signal_timestamp):

        """Mark signal in Signal Inbox as processed"""

        try:

            # Update Signal Inbox sheet to mark signal as processed

            logging.info(f"Marking signal processed: {signal_timestamp}")

           

            # TODO: Find row by timestamp and update Processed column to 'Yes'

           

        except Exception as e:

            logging.error(f"Signal inbox update error: {str(e)}")

   

    def _update_trade_log_row(self, trade_id, exit_info):

        """Update existing trade row with exit information"""

        try:

            # Find and update the trade row in Elite Trade Log

            logging.info(f"Updating trade {trade_id} with exit data")

           

            # TODO: Implement row finding and updating logic

           

        except Exception as e:

            logging.error(f"Trade log update error: {str(e)}")

   

    def _get_market_session(self):

        """Determine current market session"""

        hour = datetime.now().hour

        if 0 <= hour < 8:

            return 'Asian'

        elif 8 <= hour < 16:

            return 'European'

        else:

            return 'American'

 

# ========================================

# 🎯 DYNAMIC PROFIT ALLOCATION SYSTEM

# ========================================

 

class DynamicProfitManager(ProfitManager):

    def __init__(self):

        super().__init__()

        self.system_start_date = datetime.now()

   

    def get_months_running(self):

        """Calculate how many months the system has been running"""

        delta = datetime.now() - self.system_start_date

        return delta.days // 30

   

    def get_allocation_ratios(self, account_balance):

        """Dynamic allocation based on system maturity and balance"""

        months = self.get_months_running()

       

        # Phase 1: Aggressive Growth (Months 1-6)

        if months <= 6:

            return {

                "reinvest": 0.80,

                "btc_stack": 0.15,

                "reserve": 0.05,

                "phase": "Growth Focus"

            }

        

        # Phase 2: Balanced Approach (Months 7-12)

        elif months <= 12:

            return {

                "reinvest": 0.70,

                "btc_stack": 0.20,

                "reserve": 0.10,

                "phase": "Balanced Growth"

            }

       

        # Phase 3: Wealth Protection (Months 13+)

        else:

            return {

                "reinvest": 0.60,

                "btc_stack": 0.20,

                "reserve": 0.20,

                "phase": "Wealth Protection"

            }

 

# ========================================

# 🤖 ENHANCED TRADING ENGINE

# ========================================

 

class EnhancedAvantisEngine:

    def __init__(self):

        self.trader = AvantisTrader(

            private_key=os.getenv('WALLET_PRIVATE_KEY'),

            rpc_url=os.getenv('BASE_RPC_URL')

        )

        self.profit_manager = DynamicProfitManager()

        self.trade_logger = EnhancedTradeLogger()

        self.open_positions = {}

        

        # Enhanced tracking

        self.supported_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT']  # 🆕 Added SOL & AVAX

       

    def can_open_position(self):

        """Check if we can open a new position"""

        return len(self.open_positions) < MAX_OPEN_POSITIONS

   

    def calculate_position_size(self, balance, tier, market_regime):

        """Calculate position size with market regime adjustments"""

        base_size = TIER_1_POSITION_SIZE if tier == 1 else TIER_2_POSITION_SIZE

       

        # Market regime adjustments

        if market_regime == 'BEAR':

            multiplier = 0.8  # Reduce size in bear markets

        elif market_regime == 'BULL':

            multiplier = 1.1  # Slightly increase in bull markets

        else:

            multiplier = 1.0

       

        return balance * base_size * multiplier

   

    def get_tp_levels(self, entry_price, direction, market_regime):

        """Get optimized TP levels based on market regime"""

        levels = TP_LEVELS.get(market_regime, TP_LEVELS['NEUTRAL'])

       

        if direction.upper() == 'LONG':

            return {

                'TP1': entry_price * (1 + levels['TP1']),

                'TP2': entry_price * (1 + levels['TP2']),

                'TP3': entry_price * (1 + levels['TP3'])

            }

        else:  # SHORT

            return {

                'TP1': entry_price * (1 - levels['TP1']),

                'TP2': entry_price * (1 - levels['TP2']),

                'TP3': entry_price * (1 - levels['TP3'])

            }

   

    def process_signal(self, signal_data):

        """Process trading signal with enhanced logic"""

       

        # Validate signal quality

        if signal_data.get('signal_quality', 0) < MIN_SIGNAL_QUALITY:

            return {"status": "rejected", "reason": "Signal quality below threshold"}

       

        # Check position limits

        if not self.can_open_position():

            return {"status": "rejected", "reason": "Maximum positions reached"}

       

        # Validate symbol

        if signal_data['symbol'] not in self.supported_symbols:

            return {"status": "rejected", "reason": "Unsupported symbol"}

       

        try:

            # Get account balance

            balance = self.trader.get_balance()

           

            # Calculate position parameters

            tier = signal_data.get('tier', 2)

            market_regime = signal_data.get('market_regime', 'NEUTRAL')

            position_size = self.calculate_position_size(balance, tier, market_regime)

           

            # Get TP levels

            tp_levels = self.get_tp_levels(

                signal_data['entry_price'],

                signal_data['direction'],

                market_regime

            )

           

            # Prepare trade data

            trade_data = {

                **signal_data,

                'position_size': position_size,

                'tp1_price': tp_levels['TP1'],

                'tp2_price': tp_levels['TP2'],

                'tp3_price': tp_levels['TP3'],

                'market_regime': market_regime,

                'tier': tier

            }

           

            # Execute trade

            trade_result = self.trader.open_position(trade_data)

           

            if trade_result['success']:

                # Log trade entry with enhanced tracking

                log_entry = self.trade_logger.log_trade_entry(trade_data)

               

                # Store position

                self.open_positions[trade_result['position_id']] = {

                    **trade_data,

                    'position_id': trade_result['position_id'],

                    'opened_at': datetime.now()

                }

               

                return {

                    "status": "success",

                    "position_id": trade_result['position_id'],

                    "message": f"Position opened: {signal_data['symbol']} {signal_data['direction']}",

                    "trade_data": trade_data

                }

           

            else:

                return {"status": "failed", "reason": trade_result.get('error', 'Unknown error')}

               

        except Exception as e:

            logging.error(f"Error processing signal: {str(e)}")

            return {"status": "error", "reason": str(e)}

 

# ========================================

# 📡 FLASK ENDPOINTS

# ========================================

 

# Initialize enhanced engine

engine = EnhancedAvantisEngine()

 

@app.route('/webhook', methods=['POST'])

def process_webhook():

    """Enhanced webhook processing with optimized parameters"""

    try:

        signal_data = request.get_json()

       

        # Process with enhanced engine

        result = engine.process_signal(signal_data)

        

        return jsonify(result)

       

    except Exception as e:

        logging.error(f"Webhook error: {str(e)}")

        return jsonify({"status": "error", "message": str(e)}), 500

 

@app.route('/status', methods=['GET'])

def get_status():

    """Enhanced status endpoint with optimization info"""

    try:

        balance = engine.trader.get_balance()

        allocation = engine.profit_manager.get_allocation_ratios(balance)

       

        return jsonify({

            "status": "operational",

            "version": "Enhanced v2.0",

            "optimizations": {

                "max_positions": MAX_OPEN_POSITIONS,

                "supported_symbols": engine.supported_symbols,

                "bear_market_tp3": "5% (optimized)",

                "profit_allocation_phase": allocation["phase"]

            },

            "performance": {

                "open_positions": len(engine.open_positions),

                "available_slots": MAX_OPEN_POSITIONS - len(engine.open_positions),

                "account_balance": balance,

                "allocation_ratios": allocation

            },

            "timestamp": datetime.now().isoformat()

        })

       

    except Exception as e:

        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trade-summary', methods=['GET'])
def get_trade_summary():
    """Enhanced trade summary with TP3 performance metrics"""
    try:
        return jsonify({
            "summary": "Enhanced trade tracking active",
            "new_metrics": {
                "tp3_hit_rate": "Tracking TP3 success rate",
                "tp3_timing": "Average time to TP3",
                "bear_market_performance": "Optimized TP3 levels active",
                "multi_position_efficiency": f"Max {MAX_OPEN_POSITIONS} positions"
            },
            "supported_symbols": engine.supported_symbols,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

