from flask import Flask, request, jsonify
from datetime import datetime
import json
import os
import asyncio
import logging
import traceback
import time
import inspect

# SDK Import with error handling
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

class BasicAvantisTrader:
    def __init__(self, provider_url, private_key, api_key=None):
        # IMMEDIATE DEBUG LOGGING
        print("🚨 BASICAVANTIS INITIALIZATION STARTING...")
        logger.info("🚨 BASICAVANTIS INITIALIZATION STARTING...")
        
        self.provider_url = provider_url
        self.private_key = private_key
        self.api_key = api_key
        self.signer = None
        self.sdk_client = None
        self.trading_mode = AVANTIS_MODE
        self.available_methods = []
        self.available_properties = []
        self.working_methods = {}
        
        print(f"🔍 BASIC DEBUG INFO:")
        print(f"   Provider URL: {provider_url}")
        print(f"   Private Key Length: {len(private_key) if private_key else 0}")
        print(f"   API Key Available: {api_key is not None}")
        print(f"   Trading Mode: {self.trading_mode}")
        print(f"   REAL_SDK_AVAILABLE: {REAL_SDK_AVAILABLE}")
        print(f"   SDKTraderClient: {SDKTraderClient}")
        
        logger.info(f"🔍 BASIC DEBUG INFO:")
        logger.info(f"   Provider URL: {provider_url}")
        logger.info(f"   Private Key Length: {len(private_key) if private_key else 0}")
        logger.info(f"   API Key Available: {api_key is not None}")
        logger.info(f"   Trading Mode: {self.trading_mode}")
        logger.info(f"   REAL_SDK_AVAILABLE: {REAL_SDK_AVAILABLE}")
        logger.info(f"   SDKTraderClient: {SDKTraderClient}")
        
        logger.info(f"🚦 Initializing trader in {self.trading_mode} mode")
        
        # Initialize based on trading mode
        if self.trading_mode == 'LIVE':
            print("🔥 LIVE MODE - Initializing real SDK client")
            logger.info("🔥 LIVE MODE - Initializing real SDK client")
            self._initialize_real_sdk()
        else:
            print("🧪 TEST MODE - Using mock client")
            logger.info("🧪 TEST MODE - Using mock client")
            self._initialize_mock_client()
        
        print(f"✅ INITIALIZATION COMPLETE - SDK Client: {self.sdk_client is not None}")
        logger.info(f"✅ INITIALIZATION COMPLETE - SDK Client: {self.sdk_client is not None}")

    def _initialize_real_sdk(self):
        print("🛠 _initialize_real_sdk() CALLED")
        logger.info("🛠 _initialize_real_sdk() CALLED")
        
        try:
            print("🛠 Creating real SDK client...")
            logger.info("🛠 Creating real SDK client...")
            
            print(f"🔍 Available SDK classes: SDKTraderClient={SDKTraderClient is not None}")
            logger.info(f"🔍 Available SDK classes: SDKTraderClient={SDKTraderClient is not None}")
            
            if not SDKTraderClient:
                print("❌ SDKTraderClient is None - SDK not imported properly")
                logger.error("❌ SDKTraderClient is None - SDK not imported properly")
                raise ImportError("SDK not available")
            
            # Log what we're working with
            print(f"🔧 Initialization parameters:")
            print(f"   Provider URL: {self.provider_url}")
            print(f"   Private Key Length: {len(self.private_key) if self.private_key else 0}")
            print(f"   API Key Available: {self.api_key is not None}")
            
            logger.info(f"🔧 Initialization parameters:")
            logger.info(f"   Provider URL: {self.provider_url}")
            logger.info(f"   Private Key Length: {len(self.private_key) if self.private_key else 0}")
            logger.info(f"   API Key Available: {self.api_key is not None}")
            
            # Try different initialization approaches with better error handling
            initialization_attempts = [
                {
                    'name': 'Provider URL Only',
                    'func': lambda: SDKTraderClient(provider_url=self.provider_url),
                    'description': 'Basic initialization with RPC URL'
                },
                {
                    'name': 'Empty Constructor',
                    'func': lambda: SDKTraderClient(),
                    'description': 'Default constructor'
                },
                {
                    'name': 'With Private Key',
                    'func': lambda: SDKTraderClient(private_key=self.private_key),
                    'description': 'Initialize with wallet'
                },
                {
                    'name': 'Full Parameters',
                    'func': lambda: SDKTraderClient(
                        provider_url=self.provider_url,
                        private_key=self.private_key
                    ),
                    'description': 'All available parameters'
                }
            ]
            
            for i, attempt in enumerate(initialization_attempts, 1):
                try:
                    print(f"🔧 SDK Attempt {i}: {attempt['name']}")
                    print(f"   Description: {attempt['description']}")
                    logger.info(f"🔧 SDK Attempt {i}: {attempt['name']}")
                    logger.info(f"   Description: {attempt['description']}")
                    
                    self.sdk_client = attempt['func']()
                    
                    if self.sdk_client:
                        print(f"✅ SUCCESS! SDK Client created with {attempt['name']}")
                        print(f"   SDK Client Type: {type(self.sdk_client)}")
                        logger.info(f"✅ SUCCESS! SDK Client created with {attempt['name']}")
                        logger.info(f"   SDK Client Type: {type(self.sdk_client)}")
                        
                        # ========== DEBUGGING CODE ==========
                        print("🧪 ========== IMMEDIATE SDK METHOD DUMP ==========")
                        
                        # Check if 'trade' property exists and what's inside it
                        if hasattr(self.sdk_client, 'trade'):
                            print("✅ Found 'trade' property on SDK client!")
                            logger.info("✅ Found 'trade' property on SDK client!")
                            
                            trade_obj = getattr(self.sdk_client, 'trade')
                            print(f"🔍 Type of trade object: {type(trade_obj)}")
                            logger.info(f"🔍 Type of trade object: {type(trade_obj)}")
                            
                            print(f"📋 Methods/attributes under 'trade': {dir(trade_obj)}")
                            logger.info(f"📋 Methods/attributes under 'trade': {dir(trade_obj)}")
                            
                            # Check for specific trading methods under trade
                            print("🔍 Checking for trading methods under client.trade:")
                            logger.info("🔍 Checking for trading methods under client.trade:")
                            
                            for method in dir(trade_obj):
                                if not method.startswith('_'):  # Skip private methods
                                    attr = getattr(trade_obj, method)
                                    if callable(attr):
                                        print(f"   📞 trade.{method} - CALLABLE")
                                        logger.info(f"   📞 trade.{method} - CALLABLE")
                        else:
                            print("❌ No 'trade' property found on SDK client")
                            logger.info("❌ No 'trade' property found on SDK client")
                        
                        print("🧪 ========== END SDK METHOD DUMP ==========")
                        logger.info("🧪 ========== END SDK METHOD DUMP ==========")
                        # ========== END OF DEBUGGING CODE ==========
                        
                        # CRITICAL: Always run method discovery
                        print("🔍 Running method discovery...")
                        logger.info("🔍 Running method discovery...")
                        self._discover_available_methods()
                        
                        # Set up signer after successful SDK creation
                        print("🔑 Setting up signer...")
                        logger.info("🔑 Setting up signer...")
                        self._setup_signer()
                        return  # Exit successfully
                    else:
                        print(f"⚠️ {attempt['name']} returned None")
                        logger.warning(f"⚠️ {attempt['name']} returned None")
                        
                except Exception as e:
                    print(f"❌ {attempt['name']} failed: {str(e)}")
                    print(f"   Error type: {type(e).__name__}")
                    logger.warning(f"❌ {attempt['name']} failed: {str(e)}")
                    logger.warning(f"   Error type: {type(e).__name__}")
                    continue
            
            # If we get here, all attempts failed
            print("❌ All SDK initialization attempts failed")
            print("🔄 Creating mock SDK client for method discovery")
            logger.error("❌ All SDK initialization attempts failed")
            logger.warning("🔄 Creating mock SDK client for method discovery")
            
            # Create a mock SDK client but still try to discover methods
            print("🎭 Creating mock client...")
            logger.info("🎭 Creating mock client...")
            self.sdk_client = self._create_mock_sdk_client()
            
            print("✅ Mock SDK client created for testing")
            logger.info("✅ Mock SDK client created for testing")
            self._discover_available_methods()
            
        except Exception as e:
            print(f"❌ Complete SDK initialization failure: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            logger.error(f"❌ Complete SDK initialization failure: {e}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            self.sdk_client = None
            self.trading_mode = 'MOCK'

    def _setup_signer(self):
        try:
            if not self.private_key or len(self.private_key) < 60:
                logger.warning(f"⚠️ Invalid private key length: {len(self.private_key) if self.private_key else 0}")
                return

            logger.info("🔐 Setting up signer...")
            from web3 import Web3
            from web3.providers.async_rpc import AsyncHTTPProvider
            
            async_web3 = Web3(AsyncHTTPProvider(self.provider_url))
            self.signer = LocalSigner(private_key=self.private_key, async_web3=async_web3)
            logger.info("✅ Real signer created for LIVE trading")
            
            # Test signer connection
            if hasattr(self.signer, 'get_ethereum_address'):
                try:
                    address = self.signer.get_ethereum_address()
                    logger.info(f"✅ Connected to wallet: {address}")
                except Exception as addr_error:
                    logger.warning(f"⚠️ Could not get wallet address: {addr_error}")
            
        except Exception as signer_error:
            logger.error(f"❌ Signer setup failed: {signer_error}")
            self.signer = None

    def _discover_available_methods(self):
        print("🔍 _discover_available_methods() CALLED")
        logger.info("🔍 _discover_available_methods() CALLED")
        
        try:
            print("🔍 ========== DISCOVERING AVAILABLE SDK METHODS ==========")
            logger.info("🔍 ========== DISCOVERING AVAILABLE SDK METHODS ==========")
            
            if not self.sdk_client:
                print("❌ No SDK client to discover methods on")
                logger.error("❌ No SDK client to discover methods on")
                self.available_methods = []
                self.available_properties = []
                self.working_methods = {}
                return
            
            print(f"✅ SDK Client available: {type(self.sdk_client)}")
            logger.info(f"✅ SDK Client available: {type(self.sdk_client)}")
            
            # Get all attributes
            try:
                all_attributes = dir(self.sdk_client)
                print(f"📋 Total attributes found: {len(all_attributes)}")
                logger.info(f"📋 Total attributes found: {len(all_attributes)}")
            except Exception as e:
                print(f"❌ Could not get SDK attributes: {e}")
                logger.error(f"❌ Could not get SDK attributes: {e}")
                return
            
            methods = []
            properties = []
            
            for attr in all_attributes:
                if not attr.startswith('_'):  # Skip private attributes
                    try:
                        attr_obj = getattr(self.sdk_client, attr)
                        if callable(attr_obj):
                            methods.append(attr)
                            print(f"   📞 Method: {attr}")
                            logger.debug(f"   📞 Method: {attr}")
                        else:
                            properties.append(attr)
                            print(f"   📋 Property: {attr}")
                            logger.debug(f"   📋 Property: {attr}")
                    except Exception as attr_error:
                        print(f"   ⚠️ Could not access {attr}: {attr_error}")
                        logger.debug(f"   ⚠️ Could not access {attr}: {attr_error}")
                        pass
            
            print(f"📋 SDK Client Type: {type(self.sdk_client)}")
            print(f"📋 Available Methods ({len(methods)}): {methods}")
            print(f"📋 Available Properties ({len(properties)}): {properties}")
            
            logger.info(f"📋 SDK Client Type: {type(self.sdk_client)}")
            logger.info(f"📋 Available Methods ({len(methods)}): {methods}")
            logger.info(f"📋 Available Properties ({len(properties)}): {properties}")
            
            # Store working methods for later use
            self.available_methods = methods
            self.available_properties = properties
            
            # Test specific methods we need
            print("🧪 Testing required methods...")
            logger.info("🧪 Testing required methods...")
            self._test_required_methods()
            
            print("🔍 ========== END METHOD DISCOVERY ==========")
            logger.info("🔍 ========== END METHOD DISCOVERY ==========")
            
        except Exception as e:
            print(f"❌ Method discovery failed: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            logger.error(f"❌ Method discovery failed: {e}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            self.available_methods = []
            self.available_properties = []
            self.working_methods = {}

    def _test_required_methods(self):
        print("🧪 _test_required_methods() CALLED")
        logger.info("🧪 _test_required_methods() CALLED")
        
        required_methods = {
            'balance_methods': ['get_balance', 'get_account_balance', 'balance', 'account_balance'],
            'address_methods': ['get_ethereum_address', 'get_address', 'address', 'wallet_address'],
            'trading_methods': ['open_position', 'place_order', 'create_position', 'execute_trade', 'trade', 'submit_order', 'new_position']
        }
        
        self.working_methods = {}
        
        for category, method_list in required_methods.items():
            print(f"🧪 Testing {category}...")
            logger.info(f"🧪 Testing {category}...")
            working_in_category = []
            
            for method_name in method_list:
                if method_name in self.available_methods:
                    print(f"   ✅ {method_name} is available")
                    logger.info(f"   ✅ {method_name} is available")
                    working_in_category.append(method_name)
                    
                    # Try to get more info about the method
                    try:
                        method_obj = getattr(self.sdk_client, method_name)
                        if hasattr(method_obj, '__doc__') and method_obj.__doc__:
                            print(f"      📝 Doc: {method_obj.__doc__[:100]}...")
                            logger.debug(f"      📝 Doc: {method_obj.__doc__[:100]}...")
                        
                        # Check if it's async
                        if asyncio.iscoroutinefunction(method_obj):
                            print(f"      ⚡ {method_name} is async")
                            logger.debug(f"      ⚡ {method_name} is async")
                        else:
                            print(f"      🔄 {method_name} is sync")
                            logger.debug(f"      🔄 {method_name} is sync")
                            
                    except Exception as inspect_error:
                        print(f"      ⚠️ Could not inspect {method_name}: {inspect_error}")
                        logger.debug(f"      ⚠️ Could not inspect {method_name}: {inspect_error}")
                else:
                    print(f"   ❌ {method_name} not found")
                    logger.debug(f"   ❌ {method_name} not found")
            
            self.working_methods[category] = working_in_category
            print(f"   📋 Working {category}: {working_in_category}")
            logger.info(f"   📋 Working {category}: {working_in_category}")
            
            if not working_in_category:
                print(f"   ⚠️ NO WORKING METHODS found for {category}!")
                logger.warning(f"   ⚠️ NO WORKING METHODS found for {category}!")
        
        # SPECIAL: Check for Avantis SDK trade interface methods
        print("🔍 CHECKING AVANTIS SDK TRADE INTERFACE...")
        logger.info("🔍 CHECKING AVANTIS SDK TRADE INTERFACE...")
        
        avantis_trading_methods = []
        
        if hasattr(self.sdk_client, 'trade'):
            trade_interface = getattr(self.sdk_client, 'trade')
            print(f"✅ Found trade interface: {type(trade_interface)}")
            logger.info(f"✅ Found trade interface: {type(trade_interface)}")
            
            # Check for specific Avantis trading methods
            avantis_methods_to_check = [
                'build_trade_open_tx',
                'build_trade_close_tx', 
                'build_trade_margin_update_tx',
                'build_trade_tp_sl_update_tx',
                'get_trade_execution_fee',
                'get_trades'
            ]
            
            for method_name in avantis_methods_to_check:
                if hasattr(trade_interface, method_name):
                    print(f"   ✅ trade.{method_name} is available")
                    logger.info(f"   ✅ trade.{method_name} is available")
                    avantis_trading_methods.append(f"trade.{method_name}")
                    
                    # Check if it's async
                    try:
                        method_obj = getattr(trade_interface, method_name)
                        if asyncio.iscoroutinefunction(method_obj):
                            print(f"      ⚡ trade.{method_name} is async")
                            logger.debug(f"      ⚡ trade.{method_name} is async")
                        else:
                            print(f"      🔄 trade.{method_name} is sync")
                            logger.debug(f"      🔄 trade.{method_name} is sync")
                    except Exception as inspect_error:
                        print(f"      ⚠️ Could not inspect trade.{method_name}: {inspect_error}")
                        logger.debug(f"      ⚠️ Could not inspect trade.{method_name}: {inspect_error}")
                else:
                    print(f"   ❌ trade.{method_name} not found")
                    logger.debug(f"   ❌ trade.{method_name} not found")
        else:
            print("❌ No trade interface found")
            logger.warning("❌ No trade interface found")
        
        # Add Avantis methods to trading_methods if found
        if avantis_trading_methods:
            self.working_methods['avantis_trading_methods'] = avantis_trading_methods
            print(f"   🎯 Avantis trading methods found: {avantis_trading_methods}")
            logger.info(f"   🎯 Avantis trading methods found: {avantis_trading_methods}")
        
        # Check for transaction signing methods
        signing_methods = []
        signing_methods_to_check = ['sign_and_get_receipt', 'write_contract', 'send_and_get_transaction_hash']
        
        for method_name in signing_methods_to_check:
            if hasattr(self.sdk_client, method_name):
                print(f"   ✅ {method_name} is available")
                logger.info(f"   ✅ {method_name} is available")
                signing_methods.append(method_name)
        
        if signing_methods:
            self.working_methods['signing_methods'] = signing_methods
            print(f"   📝 Signing methods found: {signing_methods}")
            logger.info(f"   📝 Signing methods found: {signing_methods}")
        
        # Log summary
        total_working = sum(len(methods) for methods in self.working_methods.values())
        print(f"🎯 METHOD DISCOVERY SUMMARY:")
        print(f"   Total working methods: {total_working}")
        print(f"   Working methods by category: {self.working_methods}")
        
        logger.info(f"🎯 METHOD DISCOVERY SUMMARY:")
        logger.info(f"   Total working methods: {total_working}")
        logger.info(f"   Working methods by category: {self.working_methods}")

    def _initialize_mock_client(self):
        print("🧪 _initialize_mock_client() CALLED")
        logger.info("🧪 _initialize_mock_client() CALLED")
        
        print("🧪 Creating mock SDK client")
        print(f"   REAL_SDK_AVAILABLE: {REAL_SDK_AVAILABLE}")
        print(f"   SDKTraderClient: {SDKTraderClient}")
        logger.info("🧪 Creating mock SDK client")
        logger.info(f"   REAL_SDK_AVAILABLE: {REAL_SDK_AVAILABLE}")
        logger.info(f"   SDKTraderClient: {SDKTraderClient}")
        
        try:
            if SDKTraderClient:
                # Try to create a real SDK client even in mock mode for method discovery
                print("🔍 Attempting to create real SDK client for method discovery...")
                logger.info("🔍 Attempting to create real SDK client for method discovery...")
                try:
                    self.sdk_client = SDKTraderClient(provider_url=self.provider_url)
                    print("✅ Real SDK client created for method discovery")
                    logger.info("✅ Real SDK client created for method discovery")
                    self._discover_available_methods()
                except Exception as e:
                    print(f"⚠️ Could not create real SDK client: {e}")
                    logger.warning(f"⚠️ Could not create real SDK client: {e}")
                    print("🎭 Creating mock client instead...")
                    logger.info("🎭 Creating mock client instead...")
                    self.sdk_client = self._create_mock_sdk_client()
            else:
                print("⚠️ SDKTraderClient not available, creating complete mock")
                logger.warning("⚠️ SDKTraderClient not available, creating complete mock")
                self.sdk_client = self._create_mock_sdk_client()
                
        except Exception as e:
            print(f"❌ Mock client creation failed: {e}")
            logger.error(f"❌ Mock client creation failed: {e}")
            self.sdk_client = self._create_mock_sdk_client()
        
        self.signer = None
        print("✅ Mock client ready - no real trades will execute")
        logger.info("✅ Mock client ready - no real trades will execute")

    def _create_mock_sdk_client(self):
        print("🎭 Creating mock SDK client with common methods")
        logger.info("🎭 Creating mock SDK client with common methods")
        
        class MockSDKClient:
            def __init__(self):
                self.mock_balance = 1000.0
                print("🎭 MockSDKClient initialized")
                
            def get_balance(self, token='USDC'):
                print(f"🎭 MockSDKClient.get_balance({token}) called")
                return self.mock_balance
                
            def get_account_balance(self):
                print("🎭 MockSDKClient.get_account_balance() called")
                return self.mock_balance
                
            def balance(self):
                print("🎭 MockSDKClient.balance() called")
                return self.mock_balance
                
            def open_position(self, **kwargs):
                print(f"🎭 MockSDKClient.open_position({kwargs}) called")
                return {
                    'success': True,
                    'position_id': f'mock_{int(time.time())}',
                    'tx_hash': f'0x{"mock"}{"0"*36}',
                    'entry_price': kwargs.get('price', 50000),
                    'note': 'Mock trade - no real execution'
                }
                
            def place_order(self, **kwargs):
                print(f"🎭 MockSDKClient.place_order({kwargs}) called")
                return self.open_position(**kwargs)
                
            def create_position(self, **kwargs):
                print(f"🎭 MockSDKClient.create_position({kwargs}) called")
                return self.open_position(**kwargs)
                
            def execute_trade(self, **kwargs):
                print(f"🎭 MockSDKClient.execute_trade({kwargs}) called")
                return self.open_position(**kwargs)
                
            def trade(self, **kwargs):
                print(f"🎭 MockSDKClient.trade({kwargs}) called")
                return self.open_position(**kwargs)
        
        mock_client = MockSDKClient()
        print("✅ Mock SDK client created with standard methods")
        logger.info("✅ Mock SDK client created with standard methods")
        return mock_client

    def get_balance(self):
        try:
            logger.info("💰 Getting balance with discovered methods...")
            logger.info(f"   SDK Client available: {self.sdk_client is not None}")
            logger.info(f"   Signer available: {self.signer is not None}")
            logger.info(f"   Trading mode: {self.trading_mode}")
            
            # If no SDK client, use fallback
            if not self.sdk_client:
                logger.warning("⚠️ No SDK client, using fallback balance")
                return 1000.0
            
            # Get balance methods we discovered
            balance_methods = getattr(self, 'working_methods', {}).get('balance_methods', [])
            
            logger.info(f"🔍 Discovered balance methods: {balance_methods}")
            
            if not balance_methods:
                logger.warning("⚠️ No balance methods discovered, trying common ones...")
                balance_methods = ['get_balance', 'get_account_balance', 'balance', 'account_balance']
            
            # Try each balance method
            for method_name in balance_methods:
                if hasattr(self.sdk_client, method_name):
                    try:
                        method = getattr(self.sdk_client, method_name)
                        logger.info(f"🔧 Trying {method_name}...")
                        logger.info(f"   Method type: {type(method)}")
                        logger.info(f"   Is async: {asyncio.iscoroutinefunction(method)}")
                        
                        # Try different parameter combinations
                        param_attempts = [
                            {'params': ('USDC',), 'name': 'USDC token'},
                            {'params': ('usdc',), 'name': 'lowercase usdc'},
                            {'params': (), 'name': 'no parameters'}
                        ]
                        
                        for attempt in param_attempts:
                            try:
                                logger.info(f"   🎯 Trying {attempt['name']}...")
                                
                                if asyncio.iscoroutinefunction(method):
                                    if attempt['params']:
                                        balance = asyncio.run(method(*attempt['params']))
                                    else:
                                        balance = asyncio.run(method())
                                else:
                                    if attempt['params']:
                                        balance = method(*attempt['params'])
                                    else:
                                        balance = method()
                                
                                logger.info(f"   📤 Raw result: {balance} (type: {type(balance)})")
                                
                                if balance is not None:
                                    # Try to convert to float
                                    try:
                                        balance_float = float(balance)
                                        logger.info(f"✅ Balance from {method_name}({attempt['name']}): ${balance_float}")
                                        return balance_float
                                    except (ValueError, TypeError) as convert_error:
                                        logger.warning(f"⚠️ Could not convert balance to float: {convert_error}")
                                        continue
                                else:
                                    logger.warning(f"   ⚠️ {method_name}({attempt['name']}) returned None")
                                    
                            except Exception as param_error:
                                logger.warning(f"   ❌ {method_name}({attempt['name']}) failed: {param_error}")
                                continue
                        
                    except Exception as method_error:
                        logger.error(f"❌ {method_name} method completely failed: {method_error}")
                        continue
                else:
                    logger.debug(f"   ❌ {method_name} not available on SDK client")
            
            logger.warning("⚠️ No working balance methods succeeded, using fallback")
            return 1000.0
            
        except Exception as e:
            logger.error(f"❌ Balance check error: {e}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return 1000.0

    def open_position(self, trade_data):
        if self.trading_mode == 'LIVE':
            logger.info("🔥 EXECUTING REAL LIVE TRADE")
            return self._execute_live_trade(trade_data)
        else:
            logger.info("🧪 EXECUTING TEST TRADE (Mock)")
            return self._execute_test_trade(trade_data)

    def _execute_live_trade(self, trade_data):
        logger.info("💰 LIVE TRADE EXECUTION - REAL MONEY AT RISK!")
        
        try:
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
        logger.info("🚀 Executing async LIVE trade with HYBRID Avantis approach...")
        logger.info(f"   SDK Client available: {self.sdk_client is not None}")
        
        if not self.sdk_client:
            logger.error("❌ No SDK client available")
            return {
                'success': False,
                'error': "SDK client not initialized",
                'message': 'No SDK client available for LIVE trading'
            }
        
        # Check if trade property exists (we know it does from our discovery)
        if not hasattr(self.sdk_client, 'trade'):
            logger.error("❌ No 'trade' property found on SDK client")
            return {
                'success': False,
                'error': "SDK trade interface not available",
                'message': 'trade property missing from SDK client'
            }
        
        # Check if we discovered the required Avantis methods
        avantis_methods = getattr(self, 'working_methods', {}).get('avantis_trading_methods', [])
        signing_methods = getattr(self, 'working_methods', {}).get('signing_methods', [])
        
        if 'trade.build_trade_open_tx' not in avantis_methods:
            logger.error("❌ build_trade_open_tx not discovered")
            return {
                'success': False,
                'error': "Required Avantis trading method not available",
                'message': 'build_trade_open_tx method not found'
            }
        
        if 'sign_and_get_receipt' not in signing_methods:
            logger.error("❌ sign_and_get_receipt not discovered") 
            return {
                'success': False,
                'error': "Required signing method not available",
                'message': 'sign_and_get_receipt method not found'
            }
        
        # Prepare trade parameters using ChatGPT's cleaner approach
        symbol = trade_data.get('symbol', 'BTC/USDT')
        direction = trade_data.get('direction', 'LONG').upper()
        position_size = trade_data.get('position_size', 100)
        leverage = trade_data.get('leverage', 10)
        
        # Convert to Avantis format
        asset_symbol = symbol.replace("/", "")  # "BTC/USDT" -> "BTCUSDT"
        direction_clean = direction.lower()     # "LONG" -> "long"
        collateral = position_size              # Use direct USDC amount
        
        # Optional TP/SL (simplified)
        tp_price = trade_data.get('tp1_price', 0)
        sl_price = trade_data.get('stop_loss', 0)
        
        logger.info(f"📋 HYBRID Trade Parameters:")
        logger.info(f"   Symbol: {symbol} → {asset_symbol}")
        logger.info(f"   Direction: {direction} → {direction_clean}")
        logger.info(f"   Collateral: ${collateral}")
        logger.info(f"   Leverage: {leverage}x")
        logger.info(f"   TP: ${tp_price}, SL: ${sl_price}")
        
        try:
            # Step 1: Check balance first (good practice)
            logger.info("💰 Checking account balance before trade...")
            try:
                balance = await self.sdk_client.get_balance()
                logger.info(f"   Account balance: {balance}")
                
                # Basic balance check (assuming balance is in ETH, convert to USD estimate)
                if isinstance(balance, (int, float)):
                    estimated_usd = balance * 2500  # Rough ETH to USD conversion
                    if estimated_usd < collateral:
                        logger.warning(f"⚠️ Potentially insufficient balance: ~${estimated_usd} vs ${collateral} needed")
                
            except Exception as balance_error:
                logger.warning(f"⚠️ Balance check failed: {balance_error}, proceeding anyway...")
            
            # Step 2: Build trade transaction (ChatGPT's clean approach)
            logger.info("🧱 Building trade transaction with Avantis SDK...")
            
            trade_interface = self.sdk_client.trade
            
            # Primary approach: Clean parameter format
            primary_params = {
                'symbol': asset_symbol,
                'direction': direction_clean,
                'collateral': collateral,
                'leverage': leverage
            }
            
            # Add TP/SL if provided
            if tp_price > 0:
                primary_params['tp'] = tp_price
            if sl_price > 0:
                primary_params['sl'] = sl_price
            
            logger.info(f"🎯 Primary params: {primary_params}")
            
            try:
                tx_data = await trade_interface.build_trade_open_tx(**primary_params)
                logger.info(f"✅ Trade transaction built successfully!")
                logger.info(f"   TX Data type: {type(tx_data)}")
                logger.info(f"   TX Data: {tx_data}")
                
            except Exception as primary_error:
                logger.warning(f"⚠️ Primary approach failed: {primary_error}")
                
                # Fallback: Try alternative parameter formats
                logger.info("🔄 Trying alternative parameter formats...")
                
                fallback_attempts = [
                    {
                        'name': 'Pair Index Format',
                        'params': {
                            'pair_index': 0,  # BTC usually 0
                            'collateral': collateral,
                            'long': direction_clean == 'long',
                            'leverage': leverage
                        }
                    },
                    {
                        'name': 'Full Contract Format', 
                        'params': {
                            'pair_index': 0,
                            'collateral': int(collateral * 1e6),  # USDC decimals
                            'long': direction_clean == 'long',
                            'leverage': leverage,
                            'tp': int(tp_price * 1e10) if tp_price > 0 else 0,
                            'sl': int(sl_price * 1e10) if sl_price > 0 else 0
                        }
                    },
                    {
                        'name': 'Minimal Format',
                        'params': {
                            'pair_index': 0,
                            'collateral': collateral,
                            'long': direction_clean == 'long'
                        }
                    }
                ]
                
                tx_data = None
                for attempt in fallback_attempts:
                    try:
                        logger.info(f"   🎯 Trying {attempt['name']}: {attempt['params']}")
                        tx_data = await trade_interface.build_trade_open_tx(**attempt['params'])
                        logger.info(f"   ✅ {attempt['name']} succeeded!")
                        break
                    except Exception as fallback_error:
                        logger.warning(f"   ❌ {attempt['name']} failed: {fallback_error}")
                        continue
                
                if not tx_data:
                    raise Exception("All parameter formats failed")
            
            # Step 3: Sign and execute transaction
            logger.info("📝 Signing and executing trade transaction...")
            
            receipt = await self.sdk_client.sign_and_get_receipt(tx_data)
            
            logger.info(f"🎉 REAL AVANTIS TRADE EXECUTED SUCCESSFULLY!")
            logger.info(f"   Receipt type: {type(receipt)}")
            logger.info(f"   Receipt: {receipt}")
            
            # Extract key information from receipt
            tx_hash = 'unknown'
            gas_used = 0
            
            if isinstance(receipt, dict):
                tx_hash = receipt.get('transactionHash', receipt.get('hash', 'unknown'))
                gas_used = receipt.get('gasUsed', 0)
            else:
                tx_hash = str(receipt) if receipt else 'unknown'
            
            logger.info(f"   🔗 Transaction Hash: {tx_hash}")
            logger.info(f"   ⛽ Gas Used: {gas_used}")
            
            return {
                'success': True,
                'position_id': f'avantis_{int(time.time())}',
                'avantis_position_id': f'avantis_{int(time.time())}', 
                'transaction_hash': str(tx_hash),
                'actual_entry_price': trade_data.get('entry_price', 0),
                'collateral_used': collateral,
                'leverage': leverage,
                'gas_used': gas_used,
                'note': 'Real Avantis trade executed via hybrid approach',
                'method_used': 'build_trade_open_tx + sign_and_get_receipt',
                'approach': 'Hybrid (ChatGPT clean params + robust framework)',
                'receipt': receipt
            }
            
        except Exception as e:
            logger.error(f"💥 HYBRID trade execution error: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            
            return {
                'success': False,
                'error': f'Hybrid Avantis trade execution failed: {str(e)}',
                'message': 'Error in hybrid Avantis SDK trade execution',
                'approach': 'Hybrid approach failed',
                'available_methods': {
                    'avantis_methods': avantis_methods,
                    'signing_methods': signing_methods
                }
            }

    def _execute_test_trade(self, trade_data):
        logger.info("🧪 TEST TRADE - No real money involved")
        
        return {
            'success': True,
            'position_id': f'TEST_{int(time.time())}',
            'entry_price': trade_data.get('entry_price', 0),
            'tx_hash': f'0x{"TEST"}{"0"*36}',
            'message': f'TEST trade executed in {self.trading_mode} mode',
            'test_mode': True
        }


# Create trader client
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
        # Create the basic wrapper around the SDK client
        logger.info("⚠️ Custom wrapper not found, creating basic wrapper")
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

# Enhanced Trading Parameters
MAX_OPEN_POSITIONS = 4
POSITION_COOLDOWN = 2
MIN_SIGNAL_QUALITY = 0

TIER_1_POSITION_SIZE = 0.25
TIER_2_POSITION_SIZE = 0.18

TP_LEVELS = {
    'BULL': {
        'TP1': 0.025,
        'TP2': 0.055,
        'TP3': 0.12
    },
    'BEAR': {
        'TP1': 0.015,
        'TP2': 0.035,
        'TP3': 0.05
    },
    'NEUTRAL': {
        'TP1': 0.02,
        'TP2': 0.045,
        'TP3': 0.08
    }
}


class EnhancedTradeLogger:
    def __init__(self):
        self.trade_log_sheet_id = os.getenv('ELITE_TRADE_LOG_SHEET_ID')
        self.trade_log_tab_name = os.getenv('ELITE_TRADE_LOG_TAB_NAME', 'Elite Trade Log')
        self.signal_inbox_sheet_id = os.getenv('SIGNAL_INBOX_SHEET_ID')
        self.signal_inbox_tab_name = os.getenv('SIGNAL_INBOX_TAB_NAME', 'Signal Inbox')

    def log_trade_entry(self, trade_data):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"📊 LOGGING TRADE ENTRY:")
        logger.info(f"   Trade ID: {trade_data.get('avantis_position_id', 'PENDING')}")
        logger.info(f"   Symbol: {trade_data['symbol']}")
        logger.info(f"   Direction: {trade_data['direction']}")
        logger.info(f"   Size: ${trade_data['position_size']:,.2f}")
        
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
            'TP1_Price': trade_data.get('tp1_price', 0),
            'TP2_Price': trade_data.get('tp2_price', 0),
            'TP3_Price': trade_data.get('tp3_price', 0),
            'Stop_Loss_Price': trade_data.get('stop_loss', 0),
            'TP1_Hit': 'Pending',
            'TP1_Hit_Time': 'N/A',
            'TP2_Hit': 'Pending',
            'TP2_Hit_Time': 'N/A',
            'TP3_Hit': 'Pending',
            'TP3_Actual_Price': 'N/A',
            'TP3_Hit_Time': 'N/A',
            'TP3_Duration_Minutes': 'N/A',
            'Exit_Price': 'OPEN',
            'Exit_Timestamp': 'OPEN',
            'Total_Duration_Minutes': 'OPEN',
            'PnL_USDC': 'OPEN',
            'PnL_Percentage': 'OPEN',
            'Final_Outcome': 'OPEN',
            'Fees_Paid': trade_data.get('estimated_fees', 0),
            'Net_Profit': 'OPEN',
            'Market_Session': self._get_market_session(),
            'Day_of_Week': datetime.now().weekday(),
            'Manual_Notes': f'Tier {trade_data["tier"]} signal, Quality: {trade_data.get("signal_quality", "N/A")}'
        }
        
        self._append_to_elite_trade_log(trade_entry)
        self._mark_signal_processed(trade_data.get('signal_timestamp'))
        
        return trade_entry

    def _append_to_elite_trade_log(self, trade_entry):
        try:
            logger.info(f"📝 Elite Trade Log Entry: {trade_entry['Symbol']} {trade_entry['Direction']}")
            logger.info(f"📊 Trade Entry Data: {json.dumps(trade_entry, indent=2)}")
        except Exception as e:
            logger.error(f"❌ Elite Trade Log append error: {str(e)}")

    def _mark_signal_processed(self, signal_timestamp):
        try:
            logger.info(f"✅ Marking signal processed: {signal_timestamp}")
        except Exception as e:
            logger.error(f"❌ Signal inbox update error: {str(e)}")

    def _get_market_session(self):
        hour = datetime.now().hour
        if 0 <= hour < 8:
            return 'Asian'
        elif 8 <= hour < 16:
            return 'European'
        else:
            return 'American'


class DynamicProfitManager(ProfitManager):
    def __init__(self):
        super().__init__()
        self.system_start_date = datetime.now()

    def get_months_running(self):
        delta = datetime.now() - self.system_start_date
        return delta.days // 30

    def get_allocation_ratios(self, account_balance):
        months = self.get_months_running()
        
        if months <= 6:
            return {
                "reinvest": 0.80,
                "btc_stack": 0.15,
                "reserve": 0.05,
                "phase": "Growth Focus"
            }
        elif months <= 12:
            return {
                "reinvest": 0.70,
                "btc_stack": 0.20,
                "reserve": 0.10,
                "phase": "Balanced Growth"
            }
        else:
            return {
                "reinvest": 0.60,
                "btc_stack": 0.20,
                "reserve": 0.20,
                "phase": "Wealth Protection"
            }


class EnhancedAvantisEngine:
    def __init__(self, trader_client):
        logger.info("🚀 INITIALIZING ENHANCED AVANTIS ENGINE...")
        
        self.trader_client = trader_client
        logger.info("✅ Trader client assigned successfully")
        
        try:
            trader_methods = [method for method in dir(self.trader_client) if not method.startswith('_')]
            logger.info(f"📋 Trader client methods: {trader_methods}")
            logger.info(f"📋 Trader client type: {type(self.trader_client)}")
        except Exception as e:
            logger.warning(f"⚠️ Could not inspect trader client: {e}")
        
        self.profit_manager = DynamicProfitManager()
        self.trade_logger = EnhancedTradeLogger()
        self.open_positions = {}
        
        self.supported_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT']
        
        logger.info(f"✅ Engine initialized with {len(self.supported_symbols)} supported symbols")
        logger.info(f"📊 Max positions: {MAX_OPEN_POSITIONS}")

    def can_open_position(self):
        can_open = len(self.open_positions) < MAX_OPEN_POSITIONS
        logger.info(f"📊 Position check: {len(self.open_positions)}/{MAX_OPEN_POSITIONS} - Can open: {can_open}")
        return can_open

    def calculate_position_size(self, balance, tier, market_regime):
        base_size = TIER_1_POSITION_SIZE if tier == 1 else TIER_2_POSITION_SIZE
        
        if market_regime == 'BEAR':
            multiplier = 0.8
        elif market_regime == 'BULL':
            multiplier = 1.1
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
        else:
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
        logger.info("=" * 60)
        logger.info("🎯 PROCESSING NEW TRADING SIGNAL")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        try:
            logger.info(f"📊 SIGNAL DATA RECEIVED:")
            logger.info(f"   Symbol: {signal_data.get('symbol', 'N/A')}")
            logger.info(f"   Direction: {signal_data.get('direction', 'N/A')}")
            logger.info(f"   Tier: {signal_data.get('tier', 'N/A')}")
            logger.info(f"   Entry Price: ${signal_data.get('entry', 0):,.2f}")
            logger.info(f"   Signal Quality: {signal_data.get('signal_quality', 'N/A')}")
            logger.info(f"   Market Regime: {signal_data.get('market_regime', 'N/A')}")
            
            signal_quality = signal_data.get('signal_quality', 0)
            if signal_quality < MIN_SIGNAL_QUALITY:
                reason = f"Signal quality {signal_quality} below threshold {MIN_SIGNAL_QUALITY}"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Signal quality check passed: {signal_quality}")
            
            if not self.can_open_position():
                reason = f"Maximum positions reached ({len(self.open_positions)}/{MAX_OPEN_POSITIONS})"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Position limit check passed")
            
            symbol = signal_data.get('symbol', '')
            if symbol not in self.supported_symbols:
                reason = f"Unsupported symbol: {symbol}"
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                return {"status": "rejected", "reason": reason}
            
            logger.info(f"✅ Symbol validation passed: {symbol}")
            
            logger.info(f"💰 CHECKING ACCOUNT BALANCE...")
            try:
                if hasattr(self.trader_client, 'get_balance'):
                    get_balance_method = getattr(self.trader_client, 'get_balance')
                    if asyncio.iscoroutinefunction(get_balance_method):
                        balance = asyncio.run(get_balance_method())
                    else:
                        balance = get_balance_method()
                else:
                    logger.warning("⚠️ No get_balance method found, using default")
                    balance = 1000.0
                
                if asyncio.iscoroutine(balance):
                    logger.warning("⚠️ Balance returned coroutine, awaiting it...")
                    balance = asyncio.run(balance)
                
                if not isinstance(balance, (int, float)):
                    logger.warning(f"⚠️ Balance type issue: {type(balance)}, using default")
                    balance = 1000.0
                
                balance = float(balance)
                logger.info(f"💰 Balance: {balance}")            
            except Exception as e:
                logger.error(f"❌ Failed to get balance: {e}")
                logger.warning("⚠️ Using default balance due to balance check failure")
                balance = 1000.0
            
            tier = signal_data.get('tier', 2)
            market_regime = signal_data.get('market_regime', 'NEUTRAL')
            position_size = self.calculate_position_size(balance, tier, market_regime)
            
            entry_price = signal_data.get('entry', signal_data.get('entry_price', 0))
            direction = signal_data.get('direction', '')
            tp_levels = self.get_tp_levels(entry_price, direction, market_regime)
            
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
                **signal_data
            }
            
            logger.info(f"📋 PREPARED TRADE DATA:")
            logger.info(f"   Position Size: ${position_size:,.2f}")
            logger.info(f"   Leverage: {trade_data['leverage']}x")
            logger.info(f"   Stop Loss: ${trade_data['stop_loss']:,.2f}")
            
            logger.info(f"⚡ EXECUTING REAL TRADE...")
            logger.info(f"🔗 Calling AvantisTrader with proper async handling...")
            
            try:
                available_methods = [method for method in dir(self.trader_client) if not method.startswith('_')]
                logger.info(f"📋 Available trader methods: {available_methods}")
                
                logger.info("🚀 CALLING REAL TRADE METHOD...")
                trade_result = self.trader_client.open_position(trade_data)
                
                logger.info(f"📤 Trade execution result received:")
                logger.info(f"   Success: {trade_result.get('success', False)}")
                logger.info(f"   Position ID: {trade_result.get('position_id', 'N/A')}")
                logger.info(f"   TX Hash: {trade_result.get('tx_hash', 'N/A')}")
                logger.info(f"   Entry Price: {trade_result.get('entry_price', 'N/A')}")
                
                debug_info = trade_result.get('debug_info', {})
                if debug_info:
                    logger.info(f"🔍 DEBUG INFO:")
                    logger.info(f"   Available methods: {len(debug_info.get('available_methods', []))}")
                    logger.info(f"   Callable methods: {debug_info.get('callable_methods', [])}")
                    logger.info(f"   Trade params: {debug_info.get('trade_params_attempted', {})}")
                else:
                    logger.info(f"   Full result: {json.dumps(trade_result, indent=2)}")
                
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
                
                try:
                    trade_data['avantis_position_id'] = trade_result.get('position_id', 'UNKNOWN')
                    trade_data['actual_entry_price'] = trade_result.get('entry_price', entry_price)
                    trade_data['tx_hash'] = trade_result.get('tx_hash', 'UNKNOWN')
                    
                    log_entry = self.trade_logger.log_trade_entry(trade_data)
                    logger.info(f"✅ Trade logged to Elite Trade Log")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to log trade: {str(e)}")
                
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


logger.info("🚀 INITIALIZING FLASK APPLICATION...")

try:
    engine = EnhancedAvantisEngine(trader)
    logger.info("✅ Enhanced engine initialized successfully")
except Exception as e:
    logger.error(f"💥 FAILED TO INITIALIZE ENGINE: {str(e)}")
    raise


@app.route('/webhook', methods=['POST'])
def process_webhook():
    webhook_start_time = time.time()
    request_id = int(time.time() * 1000)
    
    logger.info(f"🌟 ========== WEBHOOK REQUEST #{request_id} ==========")
    logger.info(f"⏰ Request received at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
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
        
        logger.info(f"🔍 VALIDATING SIGNAL DATA...")
        
        required_fields = ['symbol', 'direction', 'tier']
        missing_fields = [field for field in required_fields if field not in signal_data]
        
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            logger.error(f"❌ {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400
        
        logger.info(f"✅ All required fields present")
        
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
    try:
        logger.info(f"📊 STATUS CHECK REQUESTED")
        
        try:
            if hasattr(engine.trader_client, 'get_balance'):
                get_balance_method = getattr(engine.trader_client, 'get_balance')
                if asyncio.iscoroutinefunction(get_balance_method):
                    balance = asyncio.run(get_balance_method())
                else:
                    balance = get_balance_method()
                
                if asyncio.iscoroutine(balance):
                    logger.warning("⚠️ Balance returned coroutine, awaiting it...")
                    balance = asyncio.run(balance)
                
                if not isinstance(balance, (int, float)):
                    logger.warning(f"⚠️ Balance type issue: {type(balance)}, using default")
                    balance = 1000.0
                
                balance = float(balance)
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


@app.route('/health', methods=['GET'])
def health_check():
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
        logger.info(f"🔍 STARTUP VALIDATION:")
        
        required_env_vars = ['WALLET_PRIVATE_KEY', 'BASE_RPC_URL']
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_env_vars:
            logger.error(f"❌ Missing environment variables: {missing_env_vars}")
        else:
            logger.info(f"✅ All required environment variables present")
        
        if hasattr(engine, 'trader_client'):
            logger.info(f"✅ Trading engine initialized successfully")
        else:
            logger.error(f"❌ Trading engine not properly initialized")
        
        logger.info("=" * 60)
        logger.info("🏆 ENHANCED TRADING BOT READY FOR ACTION!")
        logger.info("=" * 60)
        
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
        
    except Exception as e:
        logger.error(f"💥 STARTUP ERROR: {str(e)}")
        logger.error(f"   Traceback: {traceback.format_exc()}")
        raise
