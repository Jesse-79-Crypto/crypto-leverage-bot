from flask import Flask, request, jsonify
from datetime import datetime
import json
import os
import asyncio
import logging
import traceback
import time
import inspect  # Add this for checking coroutines

try:
    from avantis_trader_sdk.client import TraderClient as SDKTraderClient
    from avantis_trader_sdk.signers.local_signer import LocalSigner
    REAL_SDK_AVAILABLE = True
    logging.info("✅ Real Avantis SDK imported successfully")
except ImportError as e:
    logging.warning(f"⚠️ Real Avantis SDK not found: {e}")
    logging.warning("📦 Install with: pip install git+https://github.com/Avantis-Labs/avantis_trader_sdk.git")
    REAL_SDK_AVAILABLE = False
    SDKTraderClient = None

# Try to import the custom AvantisTrader wrapper class
try:
    from avantis_trader import AvantisTrader as CustomAvantisTrader
    CUSTOM_TRADER_AVAILABLE = True
    logging.info("✅ Custom AvantisTrader wrapper imported successfully")
except ImportError as e:
    logging.warning(f"⚠️ Custom AvantisTrader wrapper not found: {e}")
    CUSTOM_TRADER_AVAILABLE = False
    CustomAvantisTrader = None

# Import profit_management with fallback
try:
    from profit_management import EnhancedProfitManager as ProfitManager
except ImportError as e:
    logging.warning(f"⚠️ profit_management module not found: {e}")
    # Create a fallback class
    class ProfitManager:
        def __init__(self):
            pass
        def get_allocation_ratios(self, balance):
            return {
                "reinvest": 0.70,
                "btc_stack": 0.20,
                "reserve": 0.10,
                "phase": "Default Phase"
            }

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
# 🔑 ENVIRONMENT VARIABLES & TRADER SETUP
# ========================================

# Load environment variables
API_KEY = os.getenv('AVANTIS_API_KEY')
PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY')
RPC_URL = os.getenv('BASE_RPC_URL')
AVANTIS_MODE = os.getenv('AVANTIS_MODE', 'TEST')  # Default to TEST if not set

# Validate required environment variables
if not PRIVATE_KEY:
    logger.error("❌ WALLET_PRIVATE_KEY environment variable is required")
    raise ValueError("WALLET_PRIVATE_KEY is required")

if not RPC_URL:
    logger.error("❌ BASE_RPC_URL environment variable is required") 
    raise ValueError("BASE_RPC_URL is required")

# Log the trading mode
logger.info(f"🚦 AVANTIS TRADING MODE: {AVANTIS_MODE}")
if AVANTIS_MODE == 'LIVE':
    logger.info("🔥 LIVE TRADING MODE ACTIVATED - REAL MONEY AT RISK!")
else:
    logger.info("🧪 TEST MODE - Using safe fallbacks")

# Create trader client
logger.info("🔑 Setting up trader client...")
try:
    if not REAL_SDK_AVAILABLE:
        raise RuntimeError("❌ Real Avantis SDK is not available")
    
    # Use the custom AvantisTrader wrapper if available
    if CUSTOM_TRADER_AVAILABLE:
        logger.info("✅ Using custom AvantisTrader wrapper")
        trader = CustomAvantisTrader(
            api_key=API_KEY,
            private_key=PRIVATE_KEY,
            rpc_url=RPC_URL
        )
        logger.info("✅ Custom AvantisTrader wrapper created successfully")
    else:
        # Create a basic wrapper around the SDK client
        logger.info("⚠️ Custom wrapper not found, creating basic wrapper")
        
        class BasicAvantisTrader:
            def __init__(self, provider_url, private_key, api_key=None):
                self.provider_url = provider_url
                self.private_key = private_key
                self.api_key = api_key
                self.signer = None
                self.sdk_client = None
                self.trading_mode = AVANTIS_MODE
                
                logger.info(f"🚦 Initializing trader in {self.trading_mode} mode")
                
                # Initialize based on trading mode
                if self.trading_mode == 'LIVE':
                    logger.info("🔥 LIVE MODE - Initializing real SDK client")
                    self._initialize_real_sdk()
                else:
                    logger.info("🧪 TEST MODE - Using mock client")
                    self._initialize_mock_client()
                
            def _initialize_real_sdk(self):
                """Initialize real Avantis SDK for live trading"""
                try:
                    logger.info("🛠 Creating real SDK client...")
                    
                    # Create the SDK client
                    self.sdk_client = SDKTraderClient(provider_url=self.provider_url)
                    logger.info("✅ SDK TraderClient created")
                    
                    # Set up signer
                    from web3 import Web3
                    from web3.providers.async_rpc import AsyncHTTPProvider
                    
                    if not self.private_key or len(self.private_key) < 60:
                        raise ValueError(f"Invalid private key for LIVE mode")
                    
                    async_web3 = Web3(AsyncHTTPProvider(self.provider_url))
                    self.signer = LocalSigner(private_key=self.private_key, async_web3=async_web3)
                    logger.info("✅ Real signer created for LIVE trading")
                    
                    # Test connection
                    if hasattr(self.signer, 'get_ethereum_address'):
                        address = self.signer.get_ethereum_address()
                        logger.info(f"✅ Connected to wallet: {address}")
                    
                    # Log available methods
                    methods = [m for m in dir(self.sdk_client) if not m.startswith('_')]
                    logger.info(f"🔍 Real SDK methods available: {len(methods)}")
                    logger.info(f"   Methods: {methods}")
                    
                except Exception as e:
                    logger.error(f"❌ Real SDK initialization failed: {e}")
                    logger.error(f"   Falling back to mock mode for safety")
                    self.trading_mode = 'MOCK'
                    self._initialize_mock_client()
            
            def _initialize_mock_client(self):
                """Initialize mock client for testing"""
                logger.info("🧪 Creating mock SDK client")
                self.sdk_client = SDKTraderClient(provider_url=self.provider_url)
                self.signer = None
                logger.info("✅ Mock client ready - no real trades will execute")
            
            async def open_position_async(self, trade_data):
                """Execute trade using async SDK client"""
                logger.info("🔗 Executing REAL trade via async SDK client")
                
                # Convert trade_data to SDK format
                trade_params = {
                    'asset': trade_data.get('symbol', 'BTC/USDT').replace('USDT', 'USD'),
                    'is_long': trade_data.get('direction', 'LONG').upper() == 'LONG',
                    'margin': trade_data.get('position_size', 100),
                    'leverage': trade_data.get('leverage', 10)
                }
                
                logger.info(f"📋 SDK Trade Params: {trade_params}")
                
                try:
                    # Get all available methods for real-time inspection
                    available_methods = [m for m in dir(self.sdk_client) if not m.startswith('_')]
                    logger.info(f"🔍 REAL-TIME SDK Methods: {available_methods}")
                    
                    # Try multiple possible method names based on common SDK patterns
                    method_attempts = [
                        'open_position',
                        'create_position', 
                        'place_order',
                        'submit_order',
                        'open_trade',
                        'execute_trade',
                        'new_position',
                        'add_position'
                    ]
                    
                    for method_name in method_attempts:
                        if hasattr(self.sdk_client, method_name):
                            logger.info(f"✅ Found SDK method: {method_name}")
                            method = getattr(self.sdk_client, method_name)
                            
                            # Try to call it
                            try:
                                logger.info(f"🚀 Calling {method_name} with params: {trade_params}")
                                trade_result = await method(**trade_params)
                                logger.info(f"🎉 REAL TRADE EXECUTED via {method_name}: {trade_result}")
                                return trade_result
                            except Exception as method_error:
                                logger.warning(f"⚠️ {method_name} failed: {method_error}")
                                continue
                    
                    # If no standard methods work, try to find ANY method that might work
                    logger.warning("⚠️ No standard trading methods found")
                    logger.info("🔍 Inspecting SDK client for ANY callable methods...")
                    
                    callable_methods = []
                    for method_name in available_methods:
                        try:
                            method = getattr(self.sdk_client, method_name)
                            if callable(method):
                                callable_methods.append(method_name)
                        except:
                            pass
                    
                    logger.info(f"📞 Callable methods: {callable_methods}")
                    
                    # Return structured response for debugging
                    return {
                        'success': True,
                        'position_id': f'DEBUG_{int(time.time())}',
                        'entry_price': trade_data.get('entry_price', 0),
                        'tx_hash': f'0x{"DEBUG"}{"0"*36}',
                        'message': f'SDK inspection complete - Available methods: {len(available_methods)}',
                        'debug_info': {
                            'available_methods': available_methods,
                            'callable_methods': callable_methods,
                            'trade_params_attempted': trade_params
                        }
                    }
                
                except Exception as e:
                    logger.error(f"❌ Real trade execution failed: {e}")
                    logger.error(f"   Traceback: {traceback.format_exc()}")
                    return {
                        'success': False,
                        'error': str(e),
                        'message': 'Real trade attempt failed'
                    }
            
            def open_position(self, trade_data):
                """Execute trade - LIVE or TEST mode based on AVANTIS_MODE"""
                if self.trading_mode == 'LIVE':
                    logger.info("🔥 EXECUTING REAL LIVE TRADE")
                    return self._execute_live_trade(trade_data)
                else:
                    logger.info("🧪 EXECUTING TEST TRADE (Mock)")
                    return self._execute_test_trade(trade_data)
            
            def _execute_live_trade(self, trade_data):
                """Execute real trade with real money"""
                logger.info("💰 LIVE TRADE EXECUTION - REAL MONEY AT RISK!")
                
                try:
                    # Run the async live trade
                    result = asyncio.run(self._execute_live_trade_async(trade_data))
                    return result
                except Exception as e:
                    logger.error(f"❌ LIVE trade execution failed: {e}")
                    return {
                        'success': False,
                        'error': str(e),
                        'message': 'LIVE trade failed'
                    }
            
            async def _execute_live_trade_async(self, trade_data):
                """Async live trade execution"""
                logger.info("🚀 Executing async LIVE trade...")
                
                # Convert to SDK format
                trade_params = {
                    'asset': trade_data.get('symbol', 'BTC/USDT').replace('USDT', 'USD'),
                    'is_long': trade_data.get('direction', 'LONG').upper() == 'LONG',
                    'margin': trade_data.get('position_size', 100),
                    'leverage': trade_data.get('leverage', 10)
                }
                
                logger.info(f"📋 LIVE Trade Params: {trade_params}")
                
                # Try all possible trading methods for LIVE execution
                methods_to_try = [
                    'open_position',
                    'create_position', 
                    'place_order',
                    'submit_order',
                    'open_trade',
                    'execute_trade',
                    'new_position'
                ]
                
                for method_name in methods_to_try:
                    if hasattr(self.sdk_client, method_name):
                        logger.info(f"✅ Found LIVE method: {method_name}")
                        method = getattr(self.sdk_client, method_name)
                        
                        try:
                            logger.info(f"🔥 CALLING LIVE {method_name}...")
                            result = await method(**trade_params)
                            logger.info(f"🎉 LIVE TRADE SUCCESS via {method_name}!")
                            logger.info(f"   Result: {result}")
                            return result
                        except Exception as e:
                            logger.warning(f"⚠️ LIVE {method_name} failed: {e}")
                            continue
                
                # If no methods worked
                logger.error("❌ No LIVE trading methods worked")
                return {
                    'success': False,
                    'error': 'No working LIVE trading methods found',
                    'message': 'Check SDK documentation for correct method names'
                }
            
            def _execute_test_trade(self, trade_data):
                """Execute test trade (mock)"""
                logger.info("🧪 TEST TRADE - No real money involved")
                
                return {
                    'success': True,
                    'position_id': f'TEST_{int(time.time())}',
                    'entry_price': trade_data.get('entry_price', 0),
                    'tx_hash': f'0x{"TEST"}{"0"*36}',
                    'message': f'TEST trade executed in {self.trading_mode} mode',
                    'test_mode': True
                }
            
            async def get_balance_async(self):
                """Get account balance using async SDK"""
                logger.info("💰 Attempting real balance check...")
                
                try:
                    # Check signer first
                    if not self.signer:
                        logger.warning("⚠️ No signer available for balance check")
                        return 1000.0
                    
                    # Check if signer has required method
                    if not hasattr(self.signer, 'get_ethereum_address'):
                        logger.warning("⚠️ Signer missing get_ethereum_address method")
                        return 1000.0
                    
                    # Get available balance methods
                    balance_methods = [m for m in dir(self.sdk_client) if 'balance' in m.lower()]
                    logger.info(f"🔍 Available balance methods: {balance_methods}")
                    
                    # Try different balance method names
                    for method_name in ['get_balance', 'get_account_balance', 'balance', 'account_balance']:
                        if hasattr(self.sdk_client, method_name):
                            logger.info(f"✅ Trying balance method: {method_name}")
                            method = getattr(self.sdk_client, method_name)
                            
                            try:
                                # REAL ASYNC CALL for balance
                                balance = await method()
                                logger.info(f"💰 REAL balance retrieved via {method_name}: {balance}")
                                return float(balance) if balance is not None else 1000.0
                            except Exception as method_error:
                                logger.warning(f"⚠️ {method_name} failed: {method_error}")
                                continue
                    
                    logger.warning("⚠️ No working balance methods found")
                    return 1000.0
                    
                except Exception as e:
                    logger.warning(f"⚠️ Real balance check failed: {e}")
                    logger.warning(f"   Error type: {type(e).__name__}")
                    return 1000.0
            
            def get_balance(self):
                """Get account balance - LIVE or TEST mode"""
                if self.trading_mode == 'LIVE':
                    logger.info("💰 Getting LIVE account balance")
                    return self._get_live_balance()
                else:
                    logger.info("🧪 Using TEST balance")
                    return 1000.0  # Test balance
            
            def _get_live_balance(self):
                """Get real account balance"""
                try:
                    # Run async balance check
                    balance = asyncio.run(self._get_live_balance_async())
                    return balance
                except Exception as e:
                    logger.warning(f"⚠️ LIVE balance check failed: {e}")
                    return 1000.0  # Fallback
            
            async def _get_live_balance_async(self):
                """Async live balance check"""
                try:
                    if not self.signer:
                        logger.warning("⚠️ No signer for LIVE balance")
                        return 1000.0
                    
                    # Try balance methods
                    balance_methods = ['get_balance', 'get_account_balance', 'balance']
                    
                    for method_name in balance_methods:
                        if hasattr(self.sdk_client, method_name):
                            logger.info(f"✅ Trying LIVE balance method: {method_name}")
                            method = getattr(self.sdk_client, method_name)
                            
                            try:
                                balance = await method()
                                logger.info(f"💰 LIVE balance via {method_name}: {balance}")
                                return float(balance) if balance is not None else 1000.0
                            except Exception as e:
                                logger.warning(f"⚠️ {method_name} failed: {e}")
                                continue
                    
                    logger.warning("⚠️ No working LIVE balance methods")
                    return 1000.0
                    
                except Exception as e:
                    logger.warning(f"⚠️ LIVE balance error: {e}")
                    return 1000.0
        
        # Create the basic wrapper
        trader = BasicAvantisTrader(
            provider_url=RPC_URL,
            private_key=PRIVATE_KEY,
            api_key=API_KEY
        )
        logger.info("✅ Basic AvantisTrader wrapper created successfully")
    
    logger.info("✅ Trader client configured successfully")
    
except Exception as e:
    logger.error(f"❌ Failed to create trader client: {str(e)}")
    logger.error(f"   Error details: {traceback.format_exc()}")
    raise

# ========================================
# 🚀 PERFORMANCE OPTIMIZATIONS IMPLEMENTED
# ========================================

# Enhanced Trading Parameters
MAX_OPEN_POSITIONS = 4  # ⬆️ Increased from 2
POSITION_COOLDOWN = 2   # ⬇️ Reduced from 3 minutes for faster deployment
MIN_SIGNAL_QUALITY = 0  # 🔓 Allow all signals for now

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
    def __init__(self, trader_client):
        logger.info("🚀 INITIALIZING ENHANCED AVANTIS ENGINE...")
        
        # Use the provided trader client instead of creating a new one
        self.trader_client = trader_client
        logger.info("✅ Trader client assigned successfully")
        
        # Debug: Log trader client structure
        try:
            trader_methods = [method for method in dir(self.trader_client) if not method.startswith('_')]
            logger.info(f"📋 Trader client methods: {trader_methods}")
            logger.info(f"📋 Trader client type: {type(self.trader_client)}")
        except Exception as e:
            logger.warning(f"⚠️ Could not inspect trader client: {e}")
        
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
                # Use the trader client's get_balance method
                if hasattr(self.trader_client, 'get_balance'):
                    get_balance_method = getattr(self.trader_client, 'get_balance')
                    if asyncio.iscoroutinefunction(get_balance_method):
                        balance = asyncio.run(get_balance_method())
                    else:
                        balance = get_balance_method()
                else:
                    logger.warning("⚠️ No get_balance method found, using default")
                    balance = 1000.0  # Default balance
                
                # Ensure balance is a float, not a coroutine
                if asyncio.iscoroutine(balance):
                    logger.warning("⚠️ Balance returned coroutine, awaiting it...")
                    balance = asyncio.run(balance)
                
                # Final safety check - ensure it's a number
                if not isinstance(balance, (int, float)):
                    logger.warning(f"⚠️ Balance type issue: {type(balance)}, using default")
                    balance = 1000.0
                
                balance = float(balance)  # Ensure it's a float
                logger.info(f"💰 Balance: {balance}")            
            except Exception as e:
                logger.error(f"❌ Failed to get balance: {e}")
                logger.warning("⚠️ Using default balance due to balance check failure")
                balance = 1000.0  # Fallback balance
            
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
            logger.info(f"⚡ EXECUTING REAL TRADE...")
            logger.info(f"🔗 Calling AvantisTrader with proper async handling...")
            
            try:
                # Log available methods for debugging
                available_methods = [method for method in dir(self.trader_client) if not method.startswith('_')]
                logger.info(f"📋 Available trader methods: {available_methods}")
                
                # Execute the trade with async support
                logger.info("🚀 CALLING REAL TRADE METHOD...")
                trade_result = self.trader_client.open_position(trade_data)
                
                logger.info(f"📤 Trade execution result received:")
                logger.info(f"   Success: {trade_result.get('success', False)}")
                logger.info(f"   Position ID: {trade_result.get('position_id', 'N/A')}")
                logger.info(f"   TX Hash: {trade_result.get('tx_hash', 'N/A')}")
                logger.info(f"   Entry Price: {trade_result.get('entry_price', 'N/A')}")
                
                # Show debug info if available
                debug_info = trade_result.get('debug_info', {})
                if debug_info:
                    logger.info(f"🔍 DEBUG INFO:")
                    logger.info(f"   Available methods: {len(debug_info.get('available_methods', []))}")
                    logger.info(f"   Callable methods: {debug_info.get('callable_methods', [])}")
                    logger.info(f"   Trade params: {debug_info.get('trade_params_attempted', {})}")
                else:
                    logger.info(f"   Full result: {json.dumps(trade_result, indent=2)}")
                
                # Check if this was a real trade or debug
                position_id = trade_result.get('position_id', '')
                if 'DEBUG' in position_id:
                    logger.info("🔍 This was a DEBUG response - check available methods above")
                elif 'MOCK' in position_id or 'mock' in trade_result.get('message', '').lower():
                    logger.warning("⚠️ This was a mock trade - SDK methods may need verification")
                elif trade_result.get('success'):
                    logger.info("🎉 REAL TRADE EXECUTED SUCCESSFULLY!")
                    logger.info(f"   🔗 Transaction Hash: {trade_result.get('tx_hash')}")
                else:
                    logger.warning(f"⚠️ Trade execution failed: {trade_result.get('error', 'Unknown error')}")
                
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

# Initialize enhanced engine with trader client
logger.info("🚀 INITIALIZING FLASK APPLICATION...")

try:
    engine = EnhancedAvantisEngine(trader)
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
            logger.info(f"🏁 ENGINE PROCESSING COMPLETE:")
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
        
        # Try to get balance, fallback if not available
        try:
            if hasattr(engine.trader_client, 'get_balance'):
                get_balance_method = getattr(engine.trader_client, 'get_balance')
                if asyncio.iscoroutinefunction(get_balance_method):
                    balance = asyncio.run(get_balance_method())
                else:
                    balance = get_balance_method()
                
                # Ensure balance is a float, not a coroutine
                if asyncio.iscoroutine(balance):
                    logger.warning("⚠️ Balance returned coroutine, awaiting it...")
                    balance = asyncio.run(balance)
                
                # Final safety check - ensure it's a number
                if not isinstance(balance, (int, float)):
                    logger.warning(f"⚠️ Balance type issue: {type(balance)}, using default")
                    balance = 1000.0
                
                balance = float(balance)  # Ensure it's a float
            else:
                logger.warning("⚠️ No get_balance method found")
                balance = 1000.0
        except Exception as e:
            logger.warning(f"⚠️ Balance check failed: {e}, using default")
            balance = 1000.0
        
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
                "allocation_ratios": allocation,
                "trader_type": "custom_wrapper" if CUSTOM_TRADER_AVAILABLE else "basic_wrapper"
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
            "engine_initialized": hasattr(engine, 'trader_client'),
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
        if hasattr(engine, 'trader_client'):
            logger.info(f"✅ Trading engine initialized successfully")
        else:
            logger.error(f"❌ Trading engine not properly initialized")
        
        logger.info("=" * 60)
        logger.info("🏆 ENHANCED TRADING BOT READY FOR ACTION!")
        logger.info("=" * 60)
        
        # Start Flask app
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
        
    except Exception as e:
        logger.error(f"💥 STARTUP ERROR: {str(e)}")
        logger.error(f"   Traceback: {traceback.format_exc()}")
        raise
