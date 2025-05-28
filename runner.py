from flask import Flask, request, jsonify
from datetime import datetime
import json
import os
import logging  # ⬅️ MOVE THIS UP
import traceback
import time

try:
    from avantis_trader_sdk.client import TraderClient as AvantisTrader
    import avantis_trader_sdk.signers as signers
    
    print("=== Available Signers ===")
    print("Signers module contents:", dir(signers))
    
    SDKTrader = AvantisTrader
    REAL_SDK_AVAILABLE = True
    logging.info("✅ Real Avantis SDK imported successfully")
except ImportError as e:
    logging.warning(f"⚠️ Real Avantis SDK not found: {e}")
    logging.warning("📦 Install with: pip install git+https://github.com/Avantis-Labs/avantis_trader_sdk.git")
    REAL_SDK_AVAILABLE = False
    SDKTrader = None

from profit_management import EnhancedProfitManager as ProfitManager

app = Flask(__name__)

# ========================================
# 🚀 ENHANCED LOGGING CONFIGURATION
# ========================================

# Setup comprehensive logging for Heroku visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # This shows in Heroku logs
    ]
)

# Create logger instance
logger = logging.getLogger(__name__)

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
        
        logger.info(f"📊 LOGGING TRADE ENTRY:")
        logger.info(f"   Trade ID: {trade_data.get('avantis_position_id', 'PENDING')}")
        logger.info(f"   Symbol: {trade_data['symbol']}")
        logger.info(f"   Direction: {trade_data['direction']}")
        logger.info(f"   Size: ${trade_data['position_size']:,.2f}")
        
        # Elite Trade Log entry (45 columns for actual trade tracking)
        trade_entry = {
            'Trade_ID': trade_data.get('avantis_position_id', 'PENDING'),
            'Timestamp': timestamp,
            'Symbol': trade_data['symbol'],
            'Direction': trade_data['direction'],
            'Entry_Price': trade_data.get('actual_entry_price', trade_data.get('entry_price', 0)),
            'Position_Size_USDC': trade_data['position_size'],
            'Leverage': trade_data.get('leverage', 6),
            'Collateral_Used': trade_data.get('collateral_used', 0),
            'Tier': trade_data['tier'],
            'Signal_Quality': trade_data.get('signal_quality', 0),
            'Market_Regime': trade_data.get('market_regime', 'UNKNOWN'),
            'Entry_Timestamp': timestamp,
            
            # Take Profit Levels (planned)
            'TP1_Price': trade_data.get('tp1_price', 0),
            'TP2_Price': trade_data.get('tp2_price', 0),
            'TP3_Price': trade_data.get('tp3_price', 0),
            'Stop_Loss_Price': trade_data.get('stop_loss', 0),
            
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
            'Manual_Notes': f'Tier {trade_data["tier"]} signal, Quality: {trade_data.get("signal_quality", "N/A")}'
        }
        
        # Log to Elite Trade Log sheet (not Signal Inbox)
        self._append_to_elite_trade_log(trade_entry)
        
        # Update Signal Inbox to mark signal as processed
        self._mark_signal_processed(trade_data.get('signal_timestamp'))
        
        return trade_entry

    def log_trade_exit(self, trade_id, exit_data):
        """Log trade exit with comprehensive TP3 tracking"""
        exit_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"📊 LOGGING TRADE EXIT:")
        logger.info(f"   Trade ID: {trade_id}")
        logger.info(f"   Exit Price: ${exit_data['exit_price']:,.2f}")
        logger.info(f"   P&L: ${exit_data['pnl']:,.2f}")
        logger.info(f"   Outcome: {exit_data['outcome']}")
        
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
            logger.info(f"🎯 TP3 HIT! Duration: {exit_data.get('duration_minutes', 0)} minutes")
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
            logger.info(f"📝 Elite Trade Log Entry: {trade_entry['Symbol']} {trade_entry['Direction']}")
            
            # TODO: Implement actual Google Sheets API call
            # For now, just logging the structure
            logger.info(f"📊 Trade Entry Data: {json.dumps(trade_entry, indent=2)}")
            
        except Exception as e:
            logger.error(f"❌ Elite Trade Log append error: {str(e)}")

    def _mark_signal_processed(self, signal_timestamp):
        """Mark signal in Signal Inbox as processed"""
        try:
            logger.info(f"✅ Marking signal processed: {signal_timestamp}")
            
            # TODO: Find row by timestamp and update Processed column to 'Yes'
            
        except Exception as e:
            logger.error(f"❌ Signal inbox update error: {str(e)}")

    def _update_trade_log_row(self, trade_id, exit_info):
        """Update existing trade row with exit information"""
        try:
            logger.info(f"📝 Updating trade {trade_id} with exit data")
            
            # TODO: Implement row finding and updating logic
            
        except Exception as e:
            logger.error(f"❌ Trade log update error: {str(e)}")

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
# 🤖 ENHANCED TRADING ENGINE WITH FULL LOGGING
# ========================================

class EnhancedAvantisEngine:
    def __init__(self):
        logger.info("🚀 INITIALIZING ENHANCED AVANTIS ENGINE...")
        
        try:
            if SDKTrader is None:
                raise RuntimeError("❌ SDKTrader not initialized. Real Avantis SDK is missing.")
            self.trader = SDKTrader(
            
                private_key=os.getenv('WALLET_PRIVATE_KEY'),
                rpc_url=os.getenv('BASE_RPC_URL')
            )
            logger.info("✅ AvantisTrader initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize AvantisTrader: {str(e)}")
            raise
        
        self.profit_manager = DynamicProfitManager()
        self.trade_logger = EnhancedTradeLogger()
        self.open_positions = {}
        
        # Enhanced tracking
        self.supported_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT']
        
        logger.info(f"✅ Engine initialized with {len(self.supported_symbols)} supported symbols")
        logger.info(f"📊 Max positions: {MAX_OPEN_POSITIONS}")

    def can_open_position(self):
        """Check if we can open a new position"""
        can_open = len(self.open_positions) < MAX_OPEN_POSITIONS
        logger.info(f"📊 Position check: {len(self.open_positions)}/{MAX_OPEN_POSITIONS} - Can open: {can_open}")
        return can_open

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
        
        final_size = balance * base_size * multiplier
        
        logger.info(f"💰 Position sizing:")
        logger.info(f"   Balance: ${balance:,.2f}")
        logger.info(f"   Tier {tier} base: {base_size*100:.1f}%")
        logger.info(f"   {market_regime} multiplier: {multiplier}x")
        logger.info(f"   Final size: ${final_size:,.2f}")
        
        return final_size

    def get_tp_levels(self, entry_price, direction, market_regime):
        """Get optimized TP levels based on market regime"""
        levels = TP_LEVELS.get(market_regime, TP_LEVELS['NEUTRAL'])
        
        logger.info(f"🎯 Calculating TP levels for {market_regime} market:")
        logger.info(f"   TP1: {levels['TP1']*100:.1f}%")
        logger.info(f"   TP2: {levels['TP2']*100:.1f}%")
        logger.info(f"   TP3: {levels['TP3']*100:.1f}%")
        
        if direction.upper() == 'LONG':
            tp_prices = {
                'TP1': entry_price * (1 + levels['TP1']),
                'TP2': entry_price * (1 + levels['TP2']),
                'TP3': entry_price * (1 + levels['TP3'])
            }
        else:  # SHORT
            tp_prices = {
                'TP1': entry_price * (1 - levels['TP1']),
                'TP2': entry_price * (1 - levels['TP2']),
                'TP3': entry_price * (1 - levels['TP3'])
            }
        
        logger.info(f"   TP1 Price: ${tp_prices['TP1']:,.2f}")
        logger.info(f"   TP2 Price: ${tp_prices['TP2']:,.2f}")
        logger.info(f"   TP3 Price: ${tp_prices['TP3']:,.2f}")
        
        return tp_prices

    def process_signal(self, signal_data):
        """Process trading signal with enhanced logic and FULL LOGGING"""
        
        logger.info("=" * 60)
        logger.info("🎯 PROCESSING NEW TRADING SIGNAL")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        try:
            # Log incoming signal data
            logger.info(f"📊 SIGNAL DATA RECEIVED:")
            logger.info(f"   Symbol: {signal_data.get('symbol', 'N/A')}")
            logger.info(f"   Direction: {signal_data.get('direction', 'N/A')}")
            logger.info(f"   Tier: {signal_data.get('tier', 'N/A')}")
            logger.info(f"   Entry Price: ${signal_data.get('entry', 0):,.2f}")
            logger.info(f"   Signal Quality: {signal_data.get('signal_quality', 'N/A')}")
            logger.info(f"   Market Regime: {signal_data.get('market_regime', 'N/A')}")
            
            # Validate signal quality
            signal_quality = signal_data.get('signal_quality', 0)
            if signal_quality < MIN_SIGNAL_QUALITY:
                reason = f"Signal quality {signal_quality} below threshold {MIN_SIGNAL_QUALITY}"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Signal quality check passed: {signal_quality}")
            
            # Check position limits
            if not self.can_open_position():
                reason = f"Maximum positions reached ({len(self.open_positions)}/{MAX_OPEN_POSITIONS})"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Position limit check passed")
            
            # Validate symbol
            symbol = signal_data.get('symbol', '')
            if symbol not in self.supported_symbols:
                reason = f"Unsupported symbol: {symbol}"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Symbol validation passed: {symbol}")
            
            # Get account balance
            logger.info(f"💰 CHECKING ACCOUNT BALANCE...")
            try:
                balance = self.trader.get_balance()
                logger.info(f"✅ Account balance: ${balance:,.2f}")
            except Exception as e:
                logger.error(f"❌ Failed to get balance: {str(e)}")
                return {"status": "error", "reason": f"Balance check failed: {str(e)}"}
            
            # Calculate position parameters
            tier = signal_data.get('tier', 2)
            market_regime = signal_data.get('market_regime', 'NEUTRAL')
            position_size = self.calculate_position_size(balance, tier, market_regime)
            
            # Get TP levels
            entry_price = signal_data.get('entry', signal_data.get('entry_price', 0))
            direction = signal_data.get('direction', '')
            tp_levels = self.get_tp_levels(entry_price, direction, market_regime)
            
            # Prepare trade data
            trade_data = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'position_size': position_size,
                'leverage': signal_data.get('leverage', 6),
                'tp1_price': tp_levels['TP1'],
                'tp2_price': tp_levels['TP2'],
                'tp3_price': tp_levels['TP3'],
                'stop_loss': signal_data.get('stopLoss', signal_data.get('stop_loss', 0)),
                'market_regime': market_regime,
                'tier': tier,
                'signal_quality': signal_quality,
                'timestamp': datetime.now().isoformat(),
                **signal_data  # Include all original signal data
            }
            
            logger.info(f"📋 PREPARED TRADE DATA:")
            logger.info(f"   Position Size: ${position_size:,.2f}")
            logger.info(f"   Leverage: {trade_data['leverage']}x")
            logger.info(f"   Stop Loss: ${trade_data['stop_loss']:,.2f}")
            
            # Execute trade
            logger.info(f"⚡ EXECUTING TRADE...")
            logger.info(f"🔗 Calling AvantisTrader.open_position()...")
            
            try:
                trade_result = self.trader.open_position(trade_data)
                
                logger.info(f"📤 Trade execution result received:")
                logger.info(f"   Success: {trade_result.get('success', False)}")
                logger.info(f"   Result data: {json.dumps(trade_result, indent=2)}")
                
            except Exception as e:
                logger.error(f"💥 TRADE EXECUTION FAILED: {str(e)}")
                logger.error(f"   Error type: {type(e).__name__}")
                logger.error(f"   Traceback: {traceback.format_exc()}")
                return {"status": "error", "reason": f"Trade execution failed: {str(e)}"}
            
            if trade_result.get('success', False):
                logger.info(f"🎉 TRADE EXECUTION SUCCESSFUL!")
                
                # Log trade entry with enhanced tracking
                try:
                    trade_data['avantis_position_id'] = trade_result.get('position_id', 'UNKNOWN')
                    trade_data['actual_entry_price'] = trade_result.get('entry_price', entry_price)
                    trade_data['tx_hash'] = trade_result.get('tx_hash', 'UNKNOWN')
                    
                    log_entry = self.trade_logger.log_trade_entry(trade_data)
                    logger.info(f"✅ Trade logged to Elite Trade Log")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to log trade: {str(e)}")
                
                # Store position
                position_id = trade_result.get('position_id', f"temp_{int(time.time())}")
                self.open_positions[position_id] = {
                    **trade_data,
                    'position_id': position_id,
                    'opened_at': datetime.now(),
                    'tx_hash': trade_result.get('tx_hash', 'UNKNOWN')
                }
                
                processing_time = time.time() - start_time
                
                success_response = {
                    "status": "success",
                    "position_id": position_id,
                    "tx_hash": trade_result.get('tx_hash', 'UNKNOWN'),
                    "message": f"Position opened: {symbol} {direction}",
                    "trade_data": trade_data,
                    "processing_time": f"{processing_time:.2f}s"
                }
                
                logger.info(f"✅ FINAL SUCCESS RESPONSE:")
                logger.info(f"   Position ID: {position_id}")
                logger.info(f"   TX Hash: {trade_result.get('tx_hash', 'UNKNOWN')}")
                logger.info(f"   Processing Time: {processing_time:.2f}s")
                logger.info("=" * 60)
                
                return success_response
            
            else:
                error_reason = trade_result.get('error', trade_result.get('reason', 'Unknown error'))
                logger.error(f"❌ TRADE EXECUTION FAILED: {error_reason}")
                logger.error(f"   Full result: {json.dumps(trade_result, indent=2)}")
                
                return {"status": "failed", "reason": error_reason}
                
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Error processing signal: {str(e)}"
            
            logger.error(f"💥 CRITICAL ERROR IN SIGNAL PROCESSING:")
            logger.error(f"   Error: {error_msg}")
            logger.error(f"   Type: {type(e).__name__}")
            logger.error(f"   Processing Time: {processing_time:.2f}s")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            logger.info("=" * 60)
            
            return {"status": "error", "reason": error_msg}

# ========================================
# 📡 ENHANCED FLASK ENDPOINTS WITH FULL LOGGING
# ========================================

# Initialize enhanced engine
logger.info("🚀 INITIALIZING FLASK APPLICATION...")

try:
    engine = EnhancedAvantisEngine()
    logger.info("✅ Enhanced engine initialized successfully")
except Exception as e:
    logger.error(f"💥 FAILED TO INITIALIZE ENGINE: {str(e)}")
    raise

@app.route('/webhook', methods=['POST'])
def process_webhook():
    """🔥 ENHANCED WEBHOOK WITH COMPLETE LOGGING"""
    
    webhook_start_time = time.time()
    request_id = int(time.time() * 1000)  # Unique request ID
    
    logger.info(f"🌟 ========== WEBHOOK REQUEST #{request_id} ==========")
    logger.info(f"⏰ Request received at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Parse incoming data
        logger.info(f"📥 PARSING INCOMING WEBHOOK DATA...")
        
        try:
            signal_data = request.get_json()
            
            if not signal_data:
                logger.error(f"❌ No JSON data received in webhook")
                return jsonify({"status": "error", "message": "No JSON data received"}), 400
            
            logger.info(f"✅ JSON data parsed successfully")
            logger.info(f"📊 Raw signal data: {json.dumps(signal_data, indent=2)}")
            
        except Exception as e:
            logger.error(f"❌ Failed to parse JSON: {str(e)}")
            return jsonify({"status": "error", "message": f"Invalid JSON: {str(e)}"}), 400
        
        # Step 2: Validate required fields
        logger.info(f"🔍 VALIDATING SIGNAL DATA...")
        
        required_fields = ['symbol', 'direction', 'tier']
        missing_fields = [field for field in required_fields if field not in signal_data]
        
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            logger.error(f"❌ {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400
        
        logger.info(f"✅ All required fields present")
        
        # Step 3: Process with enhanced engine
        logger.info(f"⚡ PROCESSING SIGNAL WITH ENHANCED ENGINE...")
        
        try:
            result = engine.process_signal(signal_data)
            
            processing_time = time.time() - webhook_start_time
            
            logger.info(f"📤 ENGINE PROCESSING COMPLETE:")
            logger.info(f"   Status: {result.get('status', 'unknown')}")
            logger.info(f"   Processing Time: {processing_time:.2f}s")
            
            if result.get('status') == 'success':
                logger.info(f"🎉 WEBHOOK SUCCESS:")
                logger.info(f"   Position ID: {result.get('position_id', 'N/A')}")
                logger.info(f"   TX Hash: {result.get('tx_hash', 'N/A')}")
            else:
                logger.warning(f"⚠️ WEBHOOK NOT SUCCESSFUL:")
                logger.warning(f"   Status: {result.get('status')}")
                logger.warning(f"   Reason: {result.get('reason', 'No reason provided')}")
            
            # Add metadata to response
            result['request_id'] = request_id
            result['processing_time'] = f"{processing_time:.2f}s"
            result['timestamp'] = datetime.now().isoformat()
            
            logger.info(f"🌟 ========== WEBHOOK #{request_id} COMPLETE ==========")
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"💥 ENGINE PROCESSING ERROR: {str(e)}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return jsonify({"status": "error", "message": f"Engine error: {str(e)}"}), 500
        
    except Exception as e:
        processing_time = time.time() - webhook_start_time
        
        logger.error(f"💥 CRITICAL WEBHOOK ERROR:")
        logger.error(f"   Error: {str(e)}")
        logger.error(f"   Type: {type(e).__name__}")
        logger.error(f"   Processing Time: {processing_time:.2f}s")
        logger.error(f"   Traceback: {traceback.format_exc()}")
        logger.info(f"🌟 ========== WEBHOOK #{request_id} FAILED ==========")
        
        return jsonify({
            "status": "error", 
            "message": str(e),
            "request_id": request_id,
            "processing_time": f"{processing_time:.2f}s"
        }), 500

@app.route('/status', methods=['GET'])
def get_status():
    """Enhanced status endpoint with optimization info"""
    try:
        logger.info(f"📊 STATUS CHECK REQUESTED")
        
        balance = engine.trader.get_balance()
        allocation = engine.profit_manager.get_allocation_ratios(balance)
        
        status_data = {
            "status": "operational",
            "version": "Enhanced v2.0 with Full Logging",
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
        }
        
        logger.info(f"✅ Status check complete: {len(engine.open_positions)} open positions")
        
        return jsonify(status_data)
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trade-summary', methods=['GET'])
def get_trade_summary():
    """Enhanced trade summary with TP3 performance metrics"""
    try:
        logger.info(f"📈 TRADE SUMMARY REQUESTED")
        
        summary_data = {
            "summary": "Enhanced trade tracking active",
            "new_metrics": {
                "tp3_hit_rate": "Tracking TP3 success rate",
                "tp3_timing": "Average time to TP3", 
                "bear_market_performance": "Optimized TP3 levels active",
                "multi_position_efficiency": f"Max {MAX_OPEN_POSITIONS} positions"
            },
            "supported_symbols": engine.supported_symbols,
            "open_positions": list(engine.open_positions.keys()),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Trade summary complete")
        
        return jsonify(summary_data)
        
    except Exception as e:
        logger.error(f"❌ Trade summary failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "engine_initialized": hasattr(engine, 'trader'),
            "open_positions": len(engine.open_positions) if hasattr(engine, 'open_positions') else 0,
            "max_positions": MAX_OPEN_POSITIONS
        }
        
        logger.info(f"💚 Health check: All systems operational")
        
        return jsonify(health_data)
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 ENHANCED TRADING BOT STARTING UP")
    logger.info("=" * 60)
    logger.info(f"⏰ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🔧 Configuration:")
    logger.info(f"   Max Positions: {MAX_OPEN_POSITIONS}")
    logger.info(f"   Min Signal Quality: {MIN_SIGNAL_QUALITY}")
    logger.info(f"   Supported Symbols: {', '.join(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT'])}")
    logger.info(f"   Bear Market TP3: 5% (optimized)")
    
    try:
        # Startup validation
        logger.info(f"🔍 STARTUP VALIDATION:")
        
        # Check environment variables
        required_env_vars = ['WALLET_PRIVATE_KEY', 'BASE_RPC_URL']
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_env_vars:
            logger.error(f"❌ Missing environment variables: {missing_env_vars}")
        else:
            logger.info(f"✅ All required environment variables present")
        
        # Test engine initialization
        if hasattr(engine, 'trader'):
            logger.info(f"✅ Trading engine initialized successfully")
        else:
            logger.error(f"❌ Trading engine not properly initialized")
        
        logger.info("=" * 60)
        logger.info("🏆 ENHANCED TRADING BOT READY FOR ACTION!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"💥 STARTUP VALIDATION FAILED: {str(e)}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
