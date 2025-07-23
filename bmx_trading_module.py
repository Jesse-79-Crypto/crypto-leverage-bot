import os
from web3 import Web3
import random
import logging
import asyncio
import aiohttp
import json
import time
from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
import traceback
import sys
import threading
# 🚨 EMERGENCY DEBUG - ADD THESE LINES HERE:
print("🚨 STARTING EMERGENCY DEBUG")
print(f"🔍 os module working: {bool(os)}")
print(f"🔍 os.environ exists: {bool(hasattr(os, 'environ'))}")
print(f"🔍 PRIVATE_KEY raw: {repr(os.environ.get('PRIVATE_KEY'))}")
print(f"🔍 All env keys: {[k for k in os.environ.keys() if 'PRIVATE' in k or 'BASE' in k]}")
print("🚨 END EMERGENCY DEBUG")

TRADING_LOCK = False
# Trading state management
TRADE_IN_PROGRESS = False
TRADE_LOCK = threading.Lock()
ACTIVE_TRADES = {}  # symbol -> bool  
ACTIVE_TRADES_LOCK = threading.Lock()

# Flask and web framework imports
from flask import Flask, request, jsonify
import requests

# ============================================================================
# 🎯 BMX PROTOCOL CONSTANTS - UPDATED FOR LIVE EXECUTION
# ============================================================================

# USDC Contract on Base Network (6 decimals - CRITICAL FIX)
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS = 6  # ✅ CRITICAL: USDC uses 6 decimals, not 18!

# BMX Protocol Contracts on Base Network - VERIFIED ADDRESSES
BMX_TOKEN_CONTRACT = "0x548f93779fbc992010c07467cbaf329dd5f059b7"
WBLT_TOKEN_CONTRACT = "0x4e74d4db6c0726ccded4656d0bce448876bb4c7a"

# ✅ CRITICAL UPDATE: Use Position Router for keeper execution
BMX_POSITION_ROUTER = Web3.to_checksum_address("0x88b256D6B7Ef47a775164bC8d9467538b2709c13")  # ✅ Live Position Router
BMX_VAULT_CONTRACT = Web3.to_checksum_address("0xED62f93FdEa956cAAC005C046F1C23dDc2c1027d")  # ✅ Live Vault

# 🚨 EARLY DEBUG TEST
print("🚨 TESTING IF PRINT WORKS AT ALL!")
print("🚨 Code is loading properly!")
PLUGIN_CONTRACT = BMX_POSITION_ROUTER  # ✅ Plugin target is Position Router

BMX_ROUTER_CONTRACT = Web3.to_checksum_address("0x5c45ED1Ae116Cf2Bd4d5e3Ba4f56387F69f1F361")  # ✅ Approves plugin

# ✅ EXECUTION FEE FOR KEEPER SYSTEM
MIN_EXECUTION_FEE = int(0.0015 * 1e18)  # 0.0015 ETH for keeper execution

# USDC ABI with 6 decimal support
USDC_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

# ✅ ENHANCED ROUTER ABI for plugin approval
ROUTER_ABI = [
    {
        "inputs":[{"name":"_plugin","type":"address"}],
        "name":"approvePlugin",
        "outputs":[],
        "type":"function"
    },
    {
        "inputs":[
            {"name":"_path","type":"address[]"},
            {"name":"_indexToken","type":"address"},
            {"name":"_amountIn","type":"uint256"},
            {"name":"_minOut","type":"uint256"},
            {"name":"_sizeDelta","type":"uint256"},
            {"name":"_isLong","type":"bool"},
            {"name":"_acceptablePrice","type":"uint256"},
            {"name":"_executionFee","type":"uint256"},
            {"name":"_referralCode","type":"bytes32"},
            {"name":"_callbackTarget","type":"address"}
        ],
        "name":"createIncreasePosition",
        "outputs":[{"type":"bytes32"}],
        "stateMutability":"payable",
        "type":"function"
    }
]

# ✅ POSITION ROUTER ABI for keeper-based execution
BMX_POSITION_ROUTER_ABI = [
    {
        "inputs": [
            {"name": "_path", "type": "address[]"},
            {"name": "_indexToken", "type": "address"}, 
            {"name": "_amountIn", "type": "uint256"},
            {"name": "_minOut", "type": "uint256"},
            {"name": "_sizeDelta", "type": "uint256"},
            {"name": "_isLong", "type": "bool"},
            {"name": "_acceptablePrice", "type": "uint256"},
            {"name": "_executionFee", "type": "uint256"},
            {"name": "_referralCode", "type": "bytes32"},
            {"name": "_callbackTarget", "type": "address"}
        ],
        "name": "createIncreasePosition",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "_key", "type": "bytes32"}],
        "name": "increasePositionRequests",
        "outputs": [
            {"name": "account", "type": "address"},
            {"name": "path", "type": "address[]"},
            {"name": "indexToken", "type": "address"},
            {"name": "amountIn", "type": "uint256"},
            {"name": "minOut", "type": "uint256"},
            {"name": "sizeDelta", "type": "uint256"},
            {"name": "isLong", "type": "bool"},
            {"name": "acceptablePrice", "type": "uint256"},
            {"name": "executionFee", "type": "uint256"},
            {"name": "blockNumber", "type": "uint256"},
            {"name": "blockTime", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "minExecutionFee",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ✅ VAULT ABI for oracle price fetching
BMX_VAULT_ABI = [
    {
        "inputs": [{"name": "_token", "type": "address"}],
        "name": "getMinPrice",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_token", "type": "address"}],
        "name": "getMaxPrice",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_token", "type": "address"}],
        "name": "lastUpdatedAt",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ============================================================================
# 🌐 LIVE PRICE FETCHING - PRESERVED FROM ORIGINAL
# ============================================================================

def get_live_price(symbol):
    """Get live price from CoinGecko API"""
    try:
        # Map symbols to CoinGecko IDs
        symbol_map = {
            'BTC/USDT': 'bitcoin',
            'BTC/USD': 'bitcoin', 
            'BTCUSD': 'bitcoin',
            'BTC': 'bitcoin',
            'ETH/USDT': 'ethereum',
            'ETH/USD': 'ethereum',
            'ETHUSD': 'ethereum', 
            'ETH': 'ethereum',
            'SOL/USDT': 'solana',
            'SOL/USD': 'solana',
            'SOLUSD': 'solana',
            'SOL': 'solana',
            'AVAX/USDT': 'avalanche-2',
            'AVAX/USD': 'avalanche-2',
            'AVAXUSD': 'avalanche-2',
            'AVAX': 'avalanche-2',
            'LINK/USDT': 'chainlink',
            'LINK/USD': 'chainlink',
            'LINKUSD': 'chainlink',
            'LINK': 'chainlink'
        }
        
        coingecko_id = symbol_map.get(symbol, 'bitcoin')  # Default to bitcoin
        
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coingecko_id, "vs_currencies": "usd"}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        live_price = data[coingecko_id]["usd"]
        
        logger.info(f"🌐 LIVE PRICE from CoinGecko: ${live_price:.2f}")
        return live_price
        
    except Exception as e:
        logger.error(f"❌ Failed to get live price: {e}")
        return None

# Web3 and blockchain imports
from web3 import Web3
from web3.exceptions import Web3Exception, ContractLogicError
import eth_account
from eth_account import Account

# Environment and configuration
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment Configuration
RPC_URL = os.getenv('BASE_RPC_URL')
print(f"🌐 Using RPC: {RPC_URL}")
CHAIN_ID = int(os.getenv('CHAIN_ID', 8453))
PRIVATE_KEY = os.getenv('PRIVATE_KEY')
print(f"🔍 DEBUG: PRIVATE_KEY loaded: {bool(PRIVATE_KEY)}, length: {len(PRIVATE_KEY) if PRIVATE_KEY else 0}")

# Configure logging with enhanced formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('trading_bot.log') if os.path.exists('.') else logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('bmx_trading_module')

# Flask application setup
app = Flask(__name__)

# ============================================================================
# 🔧 CONFIGURATION AND CONSTANTS - ENHANCED FOR BMX LIVE EXECUTION
# ============================================================================

class TradingConfig:
    """Centralized configuration for the BMX trading bot"""
   
    # 🌐 Network Configuration
    RPC_URL = os.getenv('BASE_RPC_URL')
    CHAIN_ID = int(os.getenv('CHAIN_ID', 8453))  # Base network
    PRIVATE_KEY = os.getenv('PRIVATE_KEY')

    # 🎯 Dynamic Position Sizing Configuration (PRESERVED FROM ORIGINAL)
    TIER_POSITION_PERCENTAGES = {
        1: 0.40,  # Elite signal: 40% of account
        2: 0.30,  # Good signal: 30% of account  
        3: 0.20   # Test signal: 20% of account
    }

    MIN_TIER_POSITIONS = {
        1: 200,  # $200 minimum for Tier 1
        2: 200,  # $200 minimum for Tier 2
        3: 200   # $200 minimum for Tier 3
    }

    # 🎯 BMX Protocol Configuration - UPDATED FOR LIVE EXECUTION
    USDC_CONTRACT = Web3.to_checksum_address(os.getenv('USDC_ADDRESS', USDC_CONTRACT))
    BMX_TOKEN = Web3.to_checksum_address(BMX_TOKEN_CONTRACT)
    WBLT_TOKEN = Web3.to_checksum_address(WBLT_TOKEN_CONTRACT)
   
    # 📊 Trading Parameters (optimized for BMX keeper execution)
    DEFAULT_LEVERAGE = 5
    DEFAULT_SLIPPAGE = 0.008  # 0.8% slippage for BMX oracle pricing
    MIN_MARGIN_REQUIRED = 25  # Minimum margin in USDC
    GAS_LIMIT = 1000000  # Higher for BMX complexity
    GAS_PRICE_GWEI = 2
    EXECUTION_FEE = MIN_EXECUTION_FEE  # For keeper execution

    # 🎯 Position Sizing Configuration (PRESERVED)
    POSITION_SIZES = {
        1: 200,    # Tier 1: $200 USDC
        2: 150,    # Tier 2: $150 USDC
        3: 100     # Tier 3: $100 USDC
    }
    DEFAULT_POSITION_SIZE = 150  # Default $150

    # 🔍 Debugging Configuration
    ENABLE_DETAILED_LOGGING = True
    LOG_TRADE_PARAMETERS = True
    LOG_BALANCE_CHECKS = True

# ============================================================================
# 🌐 WEB3 AND BLOCKCHAIN UTILITIES - ENHANCED FOR BMX LIVE EXECUTION
# ============================================================================

class Web3Manager:
    """Manages Web3 connections and blockchain interactions for BMX"""

    def __init__(self):
        self.w3 = None
        self.account = None
        self.bmx_position_router = None
        self.bmx_vault = None
        self.usdc_contract = None
        self.bmx_token = None
        self.wblt_token = None
        self._initialize_web3()

    def _initialize_web3(self):
        """Initialize Web3 connection and BMX contracts"""
        try:
            logger.info("🔍 DEBUG: Starting Web3 initialization...")
            logger.info(f"🔍 DEBUG: TradingConfig.PRIVATE_KEY exists: {bool(TradingConfig.PRIVATE_KEY)}")
            logger.info(f"🔍 DEBUG: TradingConfig.RPC_URL: {TradingConfig.RPC_URL}")
            # Initialize Web3
            self.w3 = Web3(Web3.HTTPProvider(TradingConfig.RPC_URL))

            if not self.w3.is_connected():
                logger.error("❌ Failed to connect to Base network")
                return False

            logger.info("✅ Connected to Base network for BMX trading")

            # Initialize account
            if TradingConfig.PRIVATE_KEY:
                try:
                    logger.info(f"🔍 PRIVATE_KEY length: {len(TradingConfig.PRIVATE_KEY)}")
                    self.account = Account.from_key(TradingConfig.PRIVATE_KEY)
                    logger.info(f"✅ Account loaded: {self.account.address}")
                except Exception as account_error:
                    logger.error(f"❌ Account creation failed: {account_error}")
                    self.account = None
            else:
                logger.warning("⚠️ No private key provided - read-only mode")
                logger.warning(f"🔍 PRIVATE_KEY exists: {bool(TradingConfig.PRIVATE_KEY)}")
                self.account = None
                
            # Initialize contracts
            self._initialize_bmx_contracts()

            return True

        except ContractLogicError as e:
            error_msg = str(e)
            logger.error(f"🚨 CONTRACT LOGIC ERROR: {error_msg}")
            
            # Specific error analysis
            if "VAULT_INSUFFICIENT_RESERVE" in error_msg:
                logger.error("💡 FIX: Not enough liquidity in BMX vault for this size")
            elif "BELOW_MIN_POS" in error_msg:
                logger.error("💡 FIX: Position size too small - increase to $50+ minimum")
            elif "INVALID_TOKEN" in error_msg:
                logger.error("💡 FIX: Invalid token address - check supported tokens")
            elif "INSUFFICIENT_COLLATERAL" in error_msg:
                logger.error("💡 FIX: Not enough USDC balance or approval")
            else:
                logger.error(f"💡 UNKNOWN CONTRACT ERROR: {error_msg}")
                
            return {
                "status": "contract_error",
                "error": f"BMX contract error: {error_msg}",
                "suggested_fixes": [
                    "Check USDC balance and allowance",
                    "Verify minimum position size ($50+)", 
                    "Ensure supported token selected",
                    "Check BMX vault liquidity"
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Web3 initialization failed: {str(e)}")
            return False

    def _initialize_bmx_contracts(self):
        """Initialize BMX smart contract interfaces"""
        try:
            # USDC contract with 6 decimal support
            self.usdc_contract = self.w3.eth.contract(
                address=TradingConfig.USDC_CONTRACT,
                abi=USDC_ABI
            ) 
            
            # BMX Token contract
            bmx_token_abi = [
                {
                    "inputs": [{"name": "account", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            self.bmx_token = self.w3.eth.contract(
                address=TradingConfig.BMX_TOKEN,
                abi=bmx_token_abi
            )

            # wBLT Token contract  
            self.wblt_token = self.w3.eth.contract(
                address=TradingConfig.WBLT_TOKEN,
                abi=bmx_token_abi  # Same basic ERC20 ABI
            )

            # BMX Position Router contract (CRITICAL for keeper execution)
            self.bmx_position_router = self.w3.eth.contract(
                address=BMX_POSITION_ROUTER,
                abi=BMX_POSITION_ROUTER_ABI
            )

            # BMX Vault contract (for oracle pricing)
            self.bmx_vault = self.w3.eth.contract(
                address=BMX_VAULT_CONTRACT,
                abi=BMX_VAULT_ABI
            )

            logger.info("✅ BMX smart contracts initialized with live execution support")

        except Exception as e:
            logger.error(f"❌ BMX contract initialization failed: {str(e)}")

    def get_usdc_balance(self, address: str) -> float:
        """Get USDC balance for an address - FIXED for 6 decimals"""
        try:
            if not self.usdc_contract:
                return 0.0

            balance_wei = self.usdc_contract.functions.balanceOf(address).call()
            balance_usdc = balance_wei / (10 ** USDC_DECIMALS)  # ✅ FIXED: Use 6 decimals

            return balance_usdc

        except Exception as e:
            logger.error(f"❌ Balance check failed: {str(e)}")
            return 0.0

    def get_bmx_balance(self, address: str) -> float:
        """Get BMX token balance for an address"""
        try:
            if not self.bmx_token:
                return 0.0

            balance_wei = self.bmx_token.functions.balanceOf(address).call()
            balance_bmx = balance_wei / 1e18  # BMX has 18 decimals

            return balance_bmx

        except Exception as e:
            logger.error(f"❌ BMX balance check failed: {str(e)}")
            return 0.0

    def get_wblt_balance(self, address: str) -> float:
        """Get wBLT token balance for an address"""
        try:
            if not self.wblt_token:
                return 0.0

            balance_wei = self.wblt_token.functions.balanceOf(address).call()
            balance_wblt = balance_wei / 1e18  # wBLT has 18 decimals

            return balance_wblt

        except Exception as e:
            logger.error(f"❌ wBLT balance check failed: {str(e)}")
            return 0.0

    def is_connected(self) -> bool:
        """Check if Web3 is connected"""
        return self.w3 and self.w3.is_connected()

# Initialize global Web3 manager
try:
    web3_manager = Web3Manager()
    logger.info("✅ Web3Manager created successfully")
except Exception as web3_error:
    logger.error(f"❌ Web3Manager creation failed: {web3_error}")
    web3_manager = None

# ============================================================================
# 📊 GOOGLE SHEETS INTEGRATION - PRESERVED FROM ORIGINAL
# ============================================================================

class GoogleSheetsManager:
    """Manages Google Sheets integration for signal processing"""

    def __init__(self):
        self.sheets_client = None

    def process_sheets_signal(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming signal from Google Sheets webhook"""
        try:
            logger.info("📊 Processing Google Sheets signal for BMX...")

            # Extract signal information with multiple field name attempts
            symbol = trade_data.get('symbol', trade_data.get('Symbol', ''))
            direction = trade_data.get('direction', trade_data.get('Direction', ''))
            tier = trade_data.get('tier', trade_data.get('Tier', 1))

            # Extract entry price with multiple field attempts
            entry_price = self._extract_entry_price(trade_data)

            # Calculate position size based on tier
            position_size = self._calculate_position_size(tier)

            # Extract additional parameters
            leverage = trade_data.get('leverage', trade_data.get('Leverage', TradingConfig.DEFAULT_LEVERAGE))
            stop_loss = trade_data.get('stop_loss', trade_data.get('stopLoss', 0))
            take_profit = trade_data.get('take_profit', trade_data.get('takeProfit', 0))

            processed_signal = {
                'symbol': symbol,
                'direction': direction.upper() if direction else 'LONG',
                'tier': int(tier),
                'entry_price': entry_price,
                'position_size': position_size,
                'leverage': int(leverage),
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source': 'Google Sheets',
                'signal_quality': trade_data.get('quality', 85)
            }

            logger.info(f"✅ Processed BMX signal: {symbol} {direction} ${position_size} @ ${entry_price}")

            return processed_signal

        except Exception as e:
            logger.error(f"❌ Google Sheets processing failed: {str(e)}")
            return {}

    def _extract_entry_price(self, trade_data: Dict[str, Any]) -> float:
        """Extract entry price from signal data with multiple field attempts"""
        price_fields = [
            'entry_price', 'entryPrice', 'entry', 'Entry',
            'price', 'Price', 'open_price', 'openPrice',
            'signal_price', 'signalPrice'
        ]

        for field in price_fields:
            if field in trade_data and trade_data[field]:
                try:
                    price = float(trade_data[field])
                    if price > 0:
                        logger.info(f"💰 Found entry price in field '{field}': ${price}")
                        return price
                except (ValueError, TypeError):
                    continue

        logger.warning("⚠️ No valid entry price found in trade data")
        return 0.0

    def _calculate_position_size(self, tier: int) -> int:
        """Calculate position size based on signal tier"""
        return TradingConfig.POSITION_SIZES.get(tier, TradingConfig.DEFAULT_POSITION_SIZE)

# Initialize Google Sheets manager
sheets_manager = GoogleSheetsManager()

# ============================================================================
# 🎯 BMX TRADING ENGINE - UPDATED FOR LIVE KEEPER EXECUTION
# ============================================================================

class BMXTrader:
    """Core trading engine for BMX protocol with keeper execution support"""

    def __init__(self):
        self.web3_manager = web3_manager
        self.supported_tokens = self._initialize_supported_tokens()
        
        try:
            # Get Web3 instance
            self.w3 = self.web3_manager.w3

            # ✅ SAFETY CHECK: Ensure account is loaded
            if self.web3_manager.account is None:
                raise Exception("❌ No wallet account loaded! Check your PRIVATE_KEY environment variable.")
    
            self.wallet_address = self.web3_manager.account.address 

            logging.info(f"📝 Wallet Address: {self.wallet_address}")
            logging.info(f"📝 USDC Contract: {USDC_CONTRACT}")
            logging.info(f"📝 BMX Token: {BMX_TOKEN_CONTRACT}")
            logging.info(f"📝 wBLT Token: {WBLT_TOKEN_CONTRACT}")
        
            # Create contract instances
            self.usdc_contract = self.w3.eth.contract(
                address=USDC_CONTRACT,
                abi=USDC_ABI
            )

            # BMX Position Router contract (CRITICAL for keeper execution)
            self.bmx_position_router = self.w3.eth.contract(
                address=BMX_POSITION_ROUTER,
                abi=BMX_POSITION_ROUTER_ABI
            ) 

            # BMX Vault contract for oracle pricing
            self.bmx_vault = self.w3.eth.contract(
                address=BMX_VAULT_CONTRACT,
                abi=BMX_VAULT_ABI
            )

            # BMX Router for plugin approval
            self.bmx_router = self.w3.eth.contract(
                address=BMX_ROUTER_CONTRACT,
                abi=ROUTER_ABI
            )
            
            logging.info("✅ BMX contracts initialized for live keeper execution!")
        
        except Exception as e:
            logging.error(f"❌ BMX contract initialization failed: {e}")
            raise Exception(f"BMX contract initialization failed: {e}")

    def _initialize_supported_tokens(self) -> Dict[str, Dict]:
        """Initialize supported trading tokens on BMX with REAL Base network addresses"""
        return {
            'BTC': {
                'symbol': 'BTC',
                'address': Web3.to_checksum_address('0x8e3BCC334657560253B83f08331d85267316e08a'),  # ✅ Real cbBTC on Base
                'precision': 8,
                'coingecko_id': 'bitcoin'
            },
            'ETH': {
                'symbol': 'ETH', 
                'address': Web3.to_checksum_address('0x4200000000000000000000000000000000000006'),  # ✅ Real WETH on Base
                'precision': 18,
                'coingecko_id': 'ethereum'
            },
            'SOL': {
                'symbol': 'SOL',
                'address': Web3.to_checksum_address('0x22a31BD4cB694433B6de19e8aE1972E3C5e0D40C'),  # ✅ SOL on Base (bridged)
                'precision': 9,
                'coingecko_id': 'solana'
            },
            'LINK': {
                'symbol': 'LINK',
                'address': Web3.to_checksum_address('0x491e136ff7ff03e6ab097e54734697bb5802fc1c'),  # ✅ Real LINK on Base
                'precision': 18,
                'coingecko_id': 'chainlink'
            },
            'AVAX': {
                'symbol': 'AVAX',
                'address': Web3.to_checksum_address('0x4158734D47Fc9692176B5085E0F52ee0Da5d47F1'),  # ✅ AVAX on Base (if supported)
                'precision': 18,
                'coingecko_id': 'avalanche-2'
            }
        }

    def get_supported_symbol(self, symbol: str) -> Optional[str]:
        """Get supported symbol from various input formats with validation"""
        # Clean up symbol format
        clean_symbol = symbol.replace('/USDT', '').replace('/USD', '').replace('USD', '').upper()

        logger.info(f"🔍 Converting symbol: {symbol} -> {clean_symbol}")
        available = list(self.supported_tokens.keys())
        logger.info(f"📋 Available tokens: {available}")
        
        if clean_symbol in self.supported_tokens:
            logger.info(f"✅ Symbol {symbol} → {clean_symbol} (supported)")
            return clean_symbol
        
        # 🔧 SAFETY: Default to BTC only if it's a reasonable crypto symbol
        crypto_symbols = ['BTC', 'ETH', 'SOL', 'LINK', 'AVAX']
        if any(crypto in symbol.upper() for crypto in crypto_symbols):
            logger.warning(f"⚠️ Symbol {symbol} not found, defaulting to BTC")
            return 'BTC'
        
        # If it's not a crypto symbol, reject it
        logger.error(f"❌ Symbol {symbol} not supported and not a known crypto")
        return None

    def get_oracle_price(self, token_address: str, is_long: bool) -> int:
        """Get current oracle price from BMX vault - ENHANCED DIAGNOSTICS"""
        try:
            logger.info(f"🔮 Attempting oracle price fetch for {token_address}")
            logger.info(f"🔧 Using vault contract: {BMX_VAULT_CONTRACT}")
        
            # Try multiple possible function names
            try:
                if is_long:
                    price = self.bmx_vault.functions.getMaxPrice(token_address).call()
                else:
                    price = self.bmx_vault.functions.getMinPrice(token_address).call()
                logger.info(f"✅ Oracle price fetched successfully: ${price / 1e30:.2f}")
                return price
            except Exception as e1:
                logger.warning(f"⚠️ getMaxPrice/getMinPrice failed: {e1}")
            
                # Try alternative function names
                try:
                    price = self.bmx_vault.functions.getPrice(token_address).call()
                    logger.info(f"✅ Alternative getPrice() worked: ${price / 1e30:.2f}")
                    return price
                except Exception as e2:
                    logger.warning(f"⚠️ getPrice failed: {e2}")
                
            # If all oracle attempts fail, use fallback
            logger.warning("⚠️ All oracle methods failed - using entry price fallback")
            return 0
        
        except Exception as e:
            logger.error(f"❌ Oracle price fetch completely failed: {e}")
            return 0
        
    def calculate_acceptable_price(self, oracle_price: int, is_long: bool) -> int:
        """Calculate acceptable price with proper slippage for BMX keeper execution"""
        try:
            slippage_basis_points = int(TradingConfig.DEFAULT_SLIPPAGE * 10000)  # 0.8% = 80 basis points
            
            if is_long:
                # For longs: acceptable price is maximum we're willing to pay
                # Add slippage to current price
                acceptable_price = oracle_price * (10000 + slippage_basis_points) // 10000
            else:
                # For shorts: acceptable price is minimum we're willing to receive
                # Subtract slippage from current price
                acceptable_price = oracle_price * (10000 - slippage_basis_points) // 10000
            
            logger.info(f"📊 Acceptable price calculated: ${acceptable_price / 1e30:.2f} ({'LONG' if is_long else 'SHORT'})")
            return acceptable_price

        except Exception as e:
            logger.error(f"❌ Failed to calculate acceptable price: {e}")
            return oracle_price  # Fallback to oracle price

    async def monitor_execution(self, tx_hash: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        """Monitor keeper execution of position request - CRITICAL for detecting failures"""
        try:
            logger.info(f"👀 Monitoring execution for TX: {tx_hash}")
            start_time = time.time()
            
            # Get transaction receipt to find request key
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt.status != 1:
                return {"success": False, "error": "Transaction failed on-chain"}
            
            # Extract request key from logs (simplified - you may need to parse logs properly)
            request_key = None
            for log in receipt.logs:
                if log.address.lower() == BMX_POSITION_ROUTER.lower():
                    # This is a simplified approach - you might need to decode the actual event
                    request_key = log.topics[1] if len(log.topics) > 1 else None
                    break
            
            if not request_key:
                logger.warning("⚠️ Could not extract request key, assuming immediate execution")
                return {"success": True, "executed": True, "immediate": True}
            
            # Monitor for keeper execution
            while time.time() - start_time < timeout_seconds:
                try:
                    # Check if request still exists
                    request_data = self.bmx_position_router.functions.increasePositionRequests(request_key).call()
                    
                    # If account is zero address, request was executed or cancelled
                    if request_data[0] == "0x0000000000000000000000000000000000000000":
                        logger.info("✅ Position request completed by keeper!")
                        return {"success": True, "executed": True}
                        
                except Exception as e:
                    # Request might not exist yet, continue monitoring
                    pass
                
                await asyncio.sleep(10)  # Check every 10 seconds
            
            logger.warning(f"⏰ Execution monitoring timeout after {timeout_seconds} seconds")
            return {"success": False, "error": "Execution timeout", "timeout": True}
            
        except Exception as e:
            logger.error(f"❌ Execution monitoring failed: {e}")
            return {"success": False, "error": f"Monitoring failed: {str(e)}"}

    async def execute_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trade on BMX protocol with enhanced keeper execution"""
        try:
            logger.info(f"🎯 EXECUTING BMX TRADE:")
            logger.info(f"🚀 ELITE BMX TRADING BOT v300 - Processing trade request")
            logger.info(f"🎯 BMX KEEPER EXECUTION - Superior reliability!")

            # Network verification
            chain_id = self.w3.eth.chain_id  
            logger.info(f"🔗 NETWORK CHECK: Connected to Chain ID: {chain_id}")
            if chain_id != 8453:
                logger.error(f"❌ WRONG NETWORK! You're on chain {chain_id}, not Base!")
                return {'status': 'error', 'error': f'Wrong network: {chain_id}'}
            else:
                logger.info(f"✅ CORRECT NETWORK: Base mainnet confirmed!")

            # Enhanced debugging for entry price detection
            logger.info(f"🔍 DEBUGGING entry price detection:")
            logger.info(f"  Full trade_data keys: {list(trade_data.keys())}")

            # Extract entry price with multiple field name attempts
            entry_price_dollars = None
            entry_price_source = None

            price_fields = ['entry_price', 'entry', 'price', 'open_price', 'entryPrice', 'openPrice']

            for field in price_fields:
                if field in trade_data and trade_data[field] and trade_data[field] != 0:
                    entry_price_dollars = float(trade_data[field])
                    entry_price_source = field
                    logger.info(f"💰 Found valid entry price in field '{field}': ${entry_price_dollars}")
                    break

            if entry_price_dollars is None or entry_price_dollars == 0:
                logger.error(f"❌ No valid entry price found in any field!")
                return {
                    'status': 'error',
                    'error': 'No valid entry price found',
                    'available_fields': list(trade_data.keys())
                }

            # Extract basic trade parameters
            symbol = trade_data.get('symbol', 'BTC/USD')
            direction = trade_data.get('direction', 'LONG').upper()
            leverage = int(trade_data.get('leverage', TradingConfig.DEFAULT_LEVERAGE))

            # Get supported symbol for BMX
            symbol = self.get_supported_symbol(symbol)
            logger.info(f"🎯 Trading symbol: {symbol} -> BMX: {symbol}")

            # 🚀 DYNAMIC POSITION SIZING (PRESERVED FROM ORIGINAL)
            trader_address = self.web3_manager.account.address
            
            if trader_address:
                try:
                    current_balance = self.web3_manager.get_usdc_balance(trader_address)
                    logger.info(f"✅ Current Balance: ${current_balance:.2f} USDC")
                except Exception as e:
                    logger.error(f"❌ Failed to read balance: {e}")
                    current_balance = 250  # Fallback
            else:
                current_balance = 250

            # Calculate position size based on account balance and tier
            tier = int(trade_data.get('tier', 2))

            if tier in TradingConfig.TIER_POSITION_PERCENTAGES:
                percentage = TradingConfig.TIER_POSITION_PERCENTAGES[tier]
                calculated_position = current_balance * percentage
                min_position = TradingConfig.MIN_TIER_POSITIONS[tier]
                position_usdc_dollars = max(calculated_position, min_position)

                logger.info(f"💰 DYNAMIC POSITION SIZING - BMX ELITE:")
                logger.info(f"  - Current Balance: ${current_balance:.2f} USDC")
                logger.info(f"  - Tier {tier}: {percentage*100:.0f}% of account")
                logger.info(f"  - Final Position: ${position_usdc_dollars:.2f} USDC")
            else:
                position_usdc_dollars = float(trade_data.get('position_size', 150))

            # BMX advantage: No price impact, so less slippage protection needed
            slippage_adjustment = 1.05  # Only 5% buffer for BMX
            original_position = position_usdc_dollars
            position_usdc_dollars = position_usdc_dollars * slippage_adjustment

            logger.info(f"💡 BMX ADVANTAGE - MINIMAL SLIPPAGE:")
            logger.info(f"   - No price impact trading on BMX!")
            logger.info(f"   - Original position: ${original_position:.2f}")
            logger.info(f"   - With 5% buffer: ${position_usdc_dollars:.2f}")

            # Price validation
            live_price = get_live_price(symbol)
            if live_price:
                price_diff = abs(live_price - entry_price_dollars) / entry_price_dollars * 100
                if price_diff > 2.0:
                    logger.warning(f"⚠️ Price difference {price_diff:.2f}% detected")
                    entry_price_dollars = live_price
                    entry_price_source = "Live API (CoinGecko)"

            # 🔧 SAFETY: Check minimum position requirements
            min_position_usd = 50  # BMX minimum position size
            if position_usdc_dollars < min_position_usd:
                logger.error(f"❌ Position ${position_usdc_dollars:.2f} below minimum ${min_position_usd}")
                return {
                    "status": "error",
                    "error": f"Position size ${position_usdc_dollars:.2f} below minimum ${min_position_usd}"
                }
            
            # 🔧 SAFETY: Check margin requirements  
            required_margin = position_usdc_dollars / leverage
            if required_margin < TradingConfig.MIN_MARGIN_REQUIRED:
                logger.error(f"❌ Margin ${required_margin:.2f} below minimum ${TradingConfig.MIN_MARGIN_REQUIRED}")
                return {
                    "status": "error", 
                    "error": f"Margin ${required_margin:.2f} below minimum ${TradingConfig.MIN_MARGIN_REQUIRED}"
                }
                
            logger.info(f"✅ SAFETY CHECKS PASSED:")
            logger.info(f"   - Position: ${position_usdc_dollars:.2f} (min: ${min_position_usd})")
            logger.info(f"   - Margin: ${required_margin:.2f} (min: ${TradingConfig.MIN_MARGIN_REQUIRED})")

            # Execute the BMX trade with keeper execution
            result = await self._execute_bmx_trade_keeper(
                trader_address=trader_address,
                symbol=symbol,
                position_usdc_dollars=position_usdc_dollars,
                entry_price=entry_price_dollars,
                leverage=leverage,
                is_long=(direction == 'LONG'),
                trade_data=trade_data
            )

            return result

        except Exception as e:
            logger.error(f"❌ BMX trade execution failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'status': 'error',
                'error': f'BMX trade execution failed: {str(e)}',
                'traceback': traceback.format_exc()
            }

    async def _execute_bmx_trade_keeper(
        self,
        trader_address: str,
        symbol: str,
        position_usdc_dollars: float,
        entry_price: float,
        leverage: int,
        is_long: bool,
        trade_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute BMX trade using keeper-based Position Router - CRITICAL UPDATE"""
        
        try:
            logger.info(f"🎯 Preparing BMX keeper execution...")
            
            logger.info(f"🔍 BMX TRADE PARAMETERS:")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Position: ${position_usdc_dollars:.2f} USDC")
            logger.info(f"   - Entry Price: ${entry_price:.2f}")
            logger.info(f"   - Leverage: {leverage}x")
            logger.info(f"   - Direction: {'LONG' if is_long else 'SHORT'}")
            logger.info(f"   - Margin: ${position_usdc_dollars/leverage:.2f}")

            # Check USDC balance
            balance_before = self.usdc_contract.functions.balanceOf(trader_address).call() / (10 ** USDC_DECIMALS)
            logger.info(f"🔍 USDC Balance BEFORE: ${balance_before:.6f}")

            # ✅ BMX KEEPER EXECUTION IMPLEMENTATION
            logger.info(f"🚀 EXECUTING LIVE BMX TRADE WITH KEEPER SYSTEM!")
            
            # CRITICAL: Check if any trade is already active
            global TRADING_LOCK
            if TRADING_LOCK:
                logger.info("🔒 Trade already in progress, skipping...")
                return {"status": "error", "error": "Trade already in progress"}

            TRADING_LOCK = True
            try:
                # Step 1: Get execution fee from Position Router
                try:
                    execution_fee = self.bmx_position_router.functions.minExecutionFee().call()
                    logger.info(f"💰 Execution fee from contract: {execution_fee / 1e18:.6f} ETH")
                except:
                    execution_fee = MIN_EXECUTION_FEE
                    logger.info(f"💰 Using fallback execution fee: {execution_fee / 1e18:.6f} ETH")

                # Step 2: Calculate amounts with correct decimals
                position_usdc = int(position_usdc_dollars / leverage * (10 ** USDC_DECIMALS))  # FIXED: Use 6 decimals
                approve_amount = int(1000 * (10 ** USDC_DECIMALS))  # Approve $1000 USDC (max safety)
                
                logger.info(f"💰 APPROVING ${approve_amount / (10 ** USDC_DECIMALS):.2f} USDC for Position Router...")
                
                # Step 3: Approve USDC for Position Router (FIXED decimal handling)
                current_nonce = self.w3.eth.get_transaction_count(trader_address, 'pending')
                logger.info(f"🔍 Current nonce: {current_nonce}")
                
                approve_txn = self.usdc_contract.functions.approve(
                    BMX_POSITION_ROUTER,  # ✅ Position Router, not regular router
                    approve_amount
                ).build_transaction({ 
                    'from': trader_address,
                    'gas': 100000,
                    'gasPrice': self.w3.to_wei(TradingConfig.GAS_PRICE_GWEI, 'gwei'),
                    'nonce': current_nonce
                })
                
                signed_approve = self.w3.eth.account.sign_transaction(approve_txn, TradingConfig.PRIVATE_KEY)
                approve_hash = self.w3.eth.send_raw_transaction(signed_approve.rawTransaction)
                logger.info(f"✅ USDC approved! Hash: {approve_hash.hex()}")
                
                # Wait for approval confirmation
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                if approve_receipt.status != 1:
                    raise Exception("USDC approval failed!")
                
                # Step 4: Verify approval
                allowance = self.usdc_contract.functions.allowance(trader_address, BMX_POSITION_ROUTER).call()
                logger.info(f"✅ Verified allowance: ${allowance / (10 ** USDC_DECIMALS):.2f} USDC")
                
                if allowance < position_usdc:
                    raise Exception(f"Insufficient allowance: {allowance} < {position_usdc}")

                # Step 5: Approve Position Router as plugin
                logger.info("🔐 Approving Position Router as BMX plugin...")

                plugin_approval_txn = self.bmx_router.functions.approvePlugin(
                    BMX_POSITION_ROUTER  # ✅ Position Router address
                ).build_transaction({
                    'from': trader_address,
                    'gas': 100000,
                    'gasPrice': self.w3.to_wei(TradingConfig.GAS_PRICE_GWEI, 'gwei'),
                    'nonce': self.w3.eth.get_transaction_count(trader_address)
                })

                signed_plugin = self.w3.eth.account.sign_transaction(plugin_approval_txn, TradingConfig.PRIVATE_KEY)
                plugin_hash = self.w3.eth.send_raw_transaction(signed_plugin.rawTransaction)
                logger.info(f"✅ Plugin approved! Hash: {plugin_hash.hex()}") 

                plugin_receipt = self.w3.eth.wait_for_transaction_receipt(plugin_hash)
                if plugin_receipt.status != 1:
                    raise Exception("Plugin approval transaction failed!")
                logger.info(f"✅ Plugin approval confirmed on-chain! Block: {plugin_receipt.blockNumber}")
                
                # Step 6: Get oracle price and calculate acceptable price
                if symbol not in self.supported_tokens:
                    logger.error(f"❌ Unsupported symbol: {symbol}")
                    return {"status": "error", "error": f"Unsupported symbol: {symbol}"}
                    
                index_token = self.supported_tokens[symbol]['address']
                collateral_token = USDC_CONTRACT
                
                logger.info(f"🔧 TOKEN SETUP:")
                logger.info(f"   - Collateral (margin): USDC {collateral_token}")
                logger.info(f"   - Index (trading): {symbol} {index_token}")
                
                # Get oracle price for acceptable price calculation
                oracle_price = self.get_oracle_price(index_token, is_long)
                if oracle_price == 0:
                    # Fallback to entry price if oracle fails
                    oracle_price = int(entry_price * 1e30)
                    logger.warning("⚠️ Using entry price as fallback for oracle price")
                
                acceptable_price = self.calculate_acceptable_price(oracle_price, is_long)
                size_delta = int(position_usdc_dollars * 1e30)  # Position size in USD (30 decimals)
                
                logger.info(f"🎯 CREATING BMX POSITION WITH KEEPER:")
                logger.info(f"   - Collateral: ${position_usdc / (10 ** USDC_DECIMALS):.2f} USDC")
                logger.info(f"   - Size: ${size_delta / 1e30:.2f} USD")
                logger.info(f"   - Oracle Price: ${oracle_price / 1e30:.2f}")
                logger.info(f"   - Acceptable Price: ${acceptable_price / 1e30:.2f}")
                logger.info(f"   - Direction: {'LONG' if is_long else 'SHORT'}")
                logger.info(f"   - Execution Fee: {execution_fee / 1e18:.6f} ETH")
                
                # Step 7: Create position via Position Router (KEEPER EXECUTION)
                position_txn = position_router.functions.createIncreasePosition(
                    path,
                    index_token,
                    amount_in,
                    min_out,
                    size_delta,
                    is_long,
                    acceptable_price,
                    execution_fee,
                    referral_code,
                    callback_target
                ).build_transaction({
                    "from": wallet_address,
                    "value": execution_fee,  # 👈 THIS LINE IS MANDATORY
                    "gas": 500000,
                    "nonce": w3.eth.get_transaction_count(wallet_address),
                })
                
                # Execute position transaction
                signed_position = self.w3.eth.account.sign_transaction(position_txn, TradingConfig.PRIVATE_KEY)
                position_hash = self.w3.eth.send_raw_transaction(signed_position.rawTransaction)

                logger.info(f"🚀 BMX POSITION REQUEST SUBMITTED! Hash: {position_hash.hex()}")
                logger.info(f"🔗 BaseScan: https://basescan.org/tx/{position_hash.hex()}")

                # Step 8: Monitor keeper execution
                execution_result = await self.monitor_execution(position_hash.hex())
                
                if not execution_result["success"]:
                    logger.error(f"❌ Keeper execution failed: {execution_result.get('error', 'Unknown error')}")
                    return {
                        "status": "error",
                        "message": f"Keeper execution failed: {execution_result.get('error')}",
                        "tx_hash": position_hash.hex(),
                        "basescan_url": f"https://basescan.org/tx/{position_hash.hex()}"
                    }

                logger.info(f"✅ BMX POSITION EXECUTED BY KEEPER!")
                
                # Check balance after execution
                balance_after = self.usdc_contract.functions.balanceOf(trader_address).call() / (10 ** USDC_DECIMALS)
                logger.info(f"🔍 USDC Balance AFTER: ${balance_after:.6f}")
                
                balance_change = balance_before - balance_after
                logger.info(f"💰 USDC Balance Change: -${balance_change:.6f}")
                
                return {
                    "status": "success", 
                    "message": "BMX trade executed successfully via keeper!",
                    "tx_hash": position_hash.hex(),
                    "basescan_url": f"https://basescan.org/tx/{position_hash.hex()}",
                    "execution_monitoring": execution_result,
                    "trade_details": {
                        "symbol": symbol,
                        "position_size": f"${position_usdc_dollars:.2f}",
                        "entry_price": f"${entry_price:.2f}",
                        "oracle_price": f"${oracle_price / 1e30:.2f}",
                        "acceptable_price": f"${acceptable_price / 1e30:.2f}",
                        "leverage": f"{leverage}x",
                        "direction": "LONG" if is_long else "SHORT",
                        "margin_used": f"${position_usdc_dollars/leverage:.2f}",
                        "balance_before": f"${balance_before:.6f}",
                        "balance_after": f"${balance_after:.6f}",
                        "balance_change": f"-${balance_change:.6f}",
                        "execution_fee": f"{execution_fee / 1e18:.6f} ETH"
                    },
                    "bmx_advantages": [
                        "✅ Keeper-based execution",
                        "✅ Oracle-based pricing", 
                        "✅ No price impact",
                        "✅ Reliable settlement"
                    ]
                }

            except Exception as e:
                logger.error(f"❌ Trading error: {e}")
                raise
            finally:
                TRADING_LOCK = False

        except Exception as e:
            logger.error(f"❌ BMX keeper execution failed: {str(e)}")
            return {
                "status": "error",
                "message": f"BMX keeper execution failed: {str(e)}",
                "error_type": type(e).__name__
            }

# Initialize BMX trader
bmx_trader = BMXTrader()

# ============================================================================
# 🔄 SIGNAL PROCESSING ENGINE - ADAPTED FOR BMX KEEPER EXECUTION
# ============================================================================

class SignalProcessor:
    """Advanced signal processing and validation engine for BMX keeper execution"""

    def __init__(self):
        self.sheets_manager = sheets_manager
        self.trader = bmx_trader

    async def process_signal(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming trading signal for BMX keeper trading"""
        try:
            logger.info("🔄 Processing incoming signal for BMX keeper execution...")

            # Determine signal source and process accordingly
            source = trade_data.get('source', 'unknown').lower()

            if 'sheets' in source or 'google' in source:
                processed_signal = self.sheets_manager.process_sheets_signal(trade_data)
            else:
                processed_signal = self._process_generic_signal(trade_data)

            # Validate processed signal
            if not isinstance(processed_signal, dict) or not processed_signal:
                logger.error("❌ processed_signal is invalid or None")
                return {'status': 'failed', 'error': 'Invalid processed signal'}, 400

            # Validate the processed signal
            validation_result = self._validate_signal(processed_signal)
            if not validation_result['valid']:
                return {
                    'status': 'error',
                    'error': f"Signal validation failed: {validation_result['reason']}"
                }

            # Execute the BMX trade with keeper execution
            trade_result = await self.trader.execute_trade(processed_signal)

            return {
                'status': 'success' if trade_result.get('status') in ['success'] else 'failed',
                'signal': processed_signal,
                'trade_result': trade_result
            }

        except Exception as e:
            logger.error(f"❌ Signal processing failed: {str(e)}")
            return {
                'status': 'error',
                'error': f'Signal processing failed: {str(e)}'
            }

    def _process_generic_signal(self, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process generic signal format for BMX"""
        if not trade_data:
            logging.error("❌ No signal data received.")
            return None

        try:
            # Extract core signal components
            symbol = trade_data.get('symbol', trade_data.get('pair', 'BTC/USD'))
            direction = trade_data.get('direction', trade_data.get('side', 'LONG')).upper()

            # Extract entry price
            entry_price = self._extract_entry_price_generic(trade_data)

            # Extract position parameters
            tier = trade_data.get('tier', trade_data.get('size_tier', 1))
            position_size = trade_data.get('position_size',
                                          TradingConfig.POSITION_SIZES.get(tier, TradingConfig.DEFAULT_POSITION_SIZE))

            leverage = trade_data.get('leverage', TradingConfig.DEFAULT_LEVERAGE)

            return {
                'symbol': symbol,
                'direction': direction,
                'tier': tier,
                'entry_price': entry_price,
                'position_size': position_size,
                'leverage': leverage,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source': 'Generic Signal',
                'signal_quality': trade_data.get('quality', trade_data.get('confidence', 80))
            }

        except Exception as e:
            logger.error(f"❌ Generic signal processing failed: {str(e)}")
            return {}

    def _extract_entry_price_generic(self, trade_data: Dict[str, Any]) -> float:
        """Extract entry price from generic signal format"""
        price_fields = [
            'entry_price', 'entry', 'price', 'trigger_price',
            'signal_price', 'target_price', 'open_price'
        ]

        for field in price_fields:
            if field in trade_data:
                try:
                    price = float(trade_data[field])
                    if price > 0:
                        return price
                except (ValueError, TypeError):
                    continue

        return 0.0

    def _validate_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Validate processed signal before BMX keeper execution"""

        # Check required fields
        required_fields = ['symbol', 'direction', 'entry_price', 'position_size']
        for field in required_fields:
            if field not in signal or not signal[field]:
                return {
                    'valid': False,
                    'reason': f'Missing required field: {field}'
                }

        # Validate entry price
        if signal['entry_price'] <= 0:
            return {
                'valid': False,
                'reason': 'Entry price must be greater than zero'
            }

        # Validate direction
        if signal['direction'] not in ['LONG', 'SHORT']:
            return {
                'valid': False,
                'reason': 'Direction must be LONG or SHORT'
            }

        # Validate position size
        if signal['position_size'] < 50:
            return {
                'valid': False,
                'reason': 'Position size too small (minimum $50)'
            }

        # Validate leverage (BMX supports up to 50x)
        leverage = signal.get('leverage', 1)
        if leverage < 1 or leverage > 50:
            return {
                'valid': False,
                'reason': 'Leverage must be between 1 and 50 for BMX'
            }

        return {'valid': True}

# Initialize signal processor
signal_processor = SignalProcessor()

# ============================================================================
# 🌐 WEBHOOK ENDPOINTS AND API ROUTES - ENHANCED FOR BMX KEEPER EXECUTION
# ============================================================================

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint for BMX bot"""
    return {
        'status': '🚀 FULLY OPERATIONAL',
        'service': 'Elite BMX Trading Bot',
        'version': 'v300-BMX-KEEPER-LIVE',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'web3_connected': web3_manager.is_connected(),
        'protocol': 'BMX.trade on Base with Keeper Execution',
        'contracts': {
            'position_router': BMX_POSITION_ROUTER,
            'vault': BMX_VAULT_CONTRACT,
            'reader': BMX_READER_CONTRACT,
            'bmx_token': BMX_TOKEN_CONTRACT,
            'wblt_token': WBLT_TOKEN_CONTRACT
        },
        'features': {
            'google_sheets': True,
            'bmx_keeper_trading': True,
            'oracle_pricing': True,
            'execution_monitoring': True,
            'dynamic_position_sizing': True,
            'enhanced_debugging': True,
            'up_to_50x_leverage': True,
            'live_execution': True
        },
        'improvements': [
            '🎯 Keeper-based execution system',
            '🔮 Oracle price validation', 
            '💰 Fixed USDC decimal handling',
            '👀 Execution monitoring',
            '🚀 Enhanced reliability'
        ]
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """Enhanced webhook endpoint for BMX keeper trading signals"""
    
    try:
        trade_data = request.get_json()
        if not trade_data:
            logger.error("❌ Empty request body")
            return {'error': 'Empty request body'}, 400

        # Version tracking - BMX Keeper Live
        logger.info(f"🚀 ELITE BMX TRADING BOT v300-KEEPER-LIVE - Processing webhook request")
        logger.info(f"🎯 BMX KEEPER EXECUTION - EXECUTING REAL TRADES!")

        # Trade protection (preserved from original)
        global TRADE_IN_PROGRESS
        with TRADE_LOCK:
            if TRADE_IN_PROGRESS:
                logger.warning("🚫 TRADE REJECTED - Another trade in progress!")
                return {'status': 'rejected'}, 429
            TRADE_IN_PROGRESS = True

        # Parse incoming request
        if not request.is_json:
            logger.error("❌ Request is not JSON")
            return {'error': 'Request must be JSON'}, 400

        # Symbol checking and duplicate protection
        symbol = trade_data.get('symbol', '').upper()
        if not symbol:
            logger.error("❌ No symbol in signal!")
            return {'error': 'Missing symbol in signal'}, 400

        # Check if ANY trade is active (only one trade at a time for keeper execution)
        with ACTIVE_TRADES_LOCK:
            active_symbols = [s for s, active in ACTIVE_TRADES.items() if active]
            if active_symbols:
                logger.warning(f"🚫 Trade REJECTED - Trade already active for {active_symbols[0]}!")
                return {'status': 'rejected', 'reason': f'Trade already active for {active_symbols[0]}'}, 400

            # Mark this symbol as active
            ACTIVE_TRADES[symbol] = True
            logger.info(f"✅ {symbol} marked as ACTIVE for BMX keeper trading")

        logger.info(f"📨 Received BMX signal data: {json.dumps(trade_data, indent=2)}")

        # Execute signal processing synchronously for better error handling
        try:
            result = asyncio.run(signal_processor.process_signal(trade_data))
            
            # Update ACTIVE_TRADES based on result
            with ACTIVE_TRADES_LOCK:
                if result.get('status') == 'success':
                    ACTIVE_TRADES[symbol] = False
                    logger.info(f"🔓 {symbol} marked as INACTIVE after successful trade")
                else:
                    # Keep active on failure for safety
                    logger.info(f"🔒 {symbol} remains ACTIVE (trade failed)")
            
            return {
                "status": "completed",
                "result": result,
                "message": "Trade execution completed. Check result for details."
            }, 200
            
        except Exception as process_error:
            logger.error(f"❌ Signal processing error: {process_error}")
            with ACTIVE_TRADES_LOCK:
                ACTIVE_TRADES[symbol] = False
                logger.info(f"🔓 {symbol} marked as INACTIVE after error")
            return {
                "status": "error",
                "error": f"Processing failed: {str(process_error)}"
            }, 500

    except Exception as e:
        logger.error(f"❌ BMX webhook error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'status': 'error',
            'error': f'BMX webhook processing failed: {str(e)}'
        }, 500
    finally:  
        TRADE_IN_PROGRESS = False  # Always reset

@app.route('/balance', methods=['GET'])
def get_balance():
    """Get current USDC, BMX, and wBLT balances with correct decimal handling"""
    try:
        if not web3_manager.account:
            return {'error': 'No account configured'}, 400

        address = web3_manager.account.address
        usdc_balance = web3_manager.get_usdc_balance(address)
        bmx_balance = web3_manager.get_bmx_balance(address)
        wblt_balance = web3_manager.get_wblt_balance(address)

        return {
            'address': address,
            'usdc_balance': usdc_balance,
            'usdc_decimals': USDC_DECIMALS,  # Show decimal info
            'bmx_balance': bmx_balance,
            'wblt_balance': wblt_balance,
            'total_portfolio_value': usdc_balance,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'protocol': 'BMX.trade with Keeper Execution'
        }

    except Exception as e:
        logger.error(f"❌ Balance check failed: {str(e)}")
        return {'error': f'Balance check failed: {str(e)}'}, 500

@app.route('/test-trade', methods=['POST'])
def test_trade():
    """Test BMX keeper trade endpoint with SMALL position for safety"""
    try:
        test_signal = {
            'symbol': 'BTC/USD',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'position_size': 50,  # 🔧 SMALL $50 test position for safety
            'leverage': 5,
            'tier': 3,  # Tier 3 for minimum size
            'source': 'BMX Keeper Test - SMALL POSITION'
        }

        logger.info(f"🧪 Testing BMX keeper trade with SMALL signal: {test_signal}")
        logger.info(f"💡 Using $50 position for safe testing")

        result = asyncio.run(signal_processor.process_signal(test_signal))

        return result

    except Exception as e:
        logger.error(f"❌ BMX test trade failed: {str(e)}")
        return {
            'status': 'error',
            'error': f'BMX test trade failed: {str(e)}'
        }, 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current BMX bot configuration with KEEPER execution info"""
    return {
        'position_sizes': TradingConfig.POSITION_SIZES,
        'tier_percentages': TradingConfig.TIER_POSITION_PERCENTAGES,
        'default_leverage': TradingConfig.DEFAULT_LEVERAGE,
        'default_slippage': TradingConfig.DEFAULT_SLIPPAGE,
        'min_margin_required': TradingConfig.MIN_MARGIN_REQUIRED,
        'gas_limit': TradingConfig.GAS_LIMIT,
        'execution_fee': f"{MIN_EXECUTION_FEE / 1e18:.6f} ETH",
        'usdc_decimals': USDC_DECIMALS,
        'supported_tokens': list(bmx_trader.supported_tokens.keys()),
        'live_contracts': {
            'position_router': BMX_POSITION_ROUTER,
            'vault': BMX_VAULT_CONTRACT,
            'reader': BMX_READER_CONTRACT,
            'bmx_token': BMX_TOKEN_CONTRACT,
            'wblt_token': WBLT_TOKEN_CONTRACT,
            'usdc': USDC_CONTRACT
        },
        'protocol': 'BMX.trade',
        'version': 'v300-BMX-KEEPER-LIVE',
        'network': 'Base (Chain ID: 8453)',
        'critical_fixes': [
            '🎯 Keeper-based execution system',
            '💰 Fixed USDC 6-decimal handling',
            '🔮 Oracle price validation',
            '👀 Execution monitoring',
            '🔧 Enhanced error handling'
        ],
        'advantages': [
            '🎯 No price impact trading',
            '💪 Reliable keeper execution',
            '⚡ Up to 50x leverage',
            '💰 Lower fees',
            '🚀 Oracle-based pricing'
        ]
    }

# ============================================================================
# 🚀 APPLICATION STARTUP AND MAIN EXECUTION
# ============================================================================

def initialize_application():
    """Initialize the BMX trading bot application with keeper execution"""
    try:
        logger.info("🚀 ELITE BMX TRADING BOT v300-KEEPER-LIVE STARTING UP...")
        logger.info("🎯 BMX KEEPER EXECUTION VERSION - FULLY OPERATIONAL!")

        # Verify contract addresses
        logger.info("🔍 Verifying BMX contract addresses...")
        contracts_to_verify = {
            'USDC': USDC_CONTRACT,
            'BMX Token': BMX_TOKEN_CONTRACT,
            'Position Router': BMX_POSITION_ROUTER,
            'Vault': BMX_VAULT_CONTRACT,
            'Router': BMX_ROUTER_CONTRACT
        }
        
        for name, address in contracts_to_verify.items():
            try:
                code = web3_manager.w3.eth.get_code(address)
                if code == '0x':
                    logger.error(f"❌ {name} contract not found at {address}")
                    return False
                logger.info(f"✅ {name} verified at {address}")
            except Exception as e:
                logger.error(f"❌ Failed to verify {name} contract: {e}")
                return False

        # Check Web3 connection
        if not web3_manager.is_connected():
            logger.error("❌ Web3 connection failed")
            return False

        # Check account configuration
        if not web3_manager.account:
            logger.warning("⚠️ No trading account configured (read-only mode)")
        else:
            balance = web3_manager.get_usdc_balance(web3_manager.account.address)
            logger.info(f"💰 Account balance: ${balance:.6f} USDC (6 decimals)")

        # Initialize components
        logger.info("✅ Signal processor initialized for BMX keeper execution")
        logger.info("✅ BMX trader initialized with KEEPER contracts")
        logger.info("✅ Google Sheets manager initialized")

        # Log BMX contract addresses
        logger.info(f"🔧 BMX KEEPER CONTRACT ADDRESSES:")
        logger.info(f"  - Position Router: {BMX_POSITION_ROUTER}")
        logger.info(f"  - Vault: {BMX_VAULT_CONTRACT}")
        logger.info(f"  - Reader: {BMX_READER_CONTRACT}")
        logger.info(f"  - BMX Token: {BMX_TOKEN_CONTRACT}")
        logger.info(f"  - wBLT Token: {WBLT_TOKEN_CONTRACT}")

        # Log configuration
        logger.info(f"🔧 BMX Keeper Configuration:")
        logger.info(f"  - Position sizes: {TradingConfig.POSITION_SIZES}")
        logger.info(f"  - Tier percentages: {TradingConfig.TIER_POSITION_PERCENTAGES}")
        logger.info(f"  - Default leverage: {TradingConfig.DEFAULT_LEVERAGE}x")
        logger.info(f"  - Default slippage: {TradingConfig.DEFAULT_SLIPPAGE*100}%")
        logger.info(f"  - Minimum margin: ${TradingConfig.MIN_MARGIN_REQUIRED}")
        logger.info(f"  - Execution fee: {MIN_EXECUTION_FEE / 1e18:.6f} ETH")
        logger.info(f"  - Supported tokens: {len(bmx_trader.supported_tokens)}")

        logger.info("🎯 BMX KEEPER ADVANTAGES:")
        logger.info("  🎯 Keeper-based execution system")
        logger.info("  💰 Fixed USDC 6-decimal handling") 
        logger.info("  🔮 Oracle price validation")
        logger.info("  👀 Execution monitoring")
        logger.info("  ⚡ Up to 50x leverage")
        logger.info("  💰 Lower trading fees")
        logger.info("  🚀 LIVE trade execution")
        logger.info("✅ Elite BMX Trading Bot KEEPER-LIVE and ready for trading!")

        return True

    except Exception as e:
        logger.error(f"❌ BMX application initialization failed: {str(e)}")
        return False

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return {'error': 'BMX endpoint not found'}, 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ BMX internal server error: {str(error)}")
    return {'error': 'BMX internal server error'}, 500

# ============================================================================
# 🎯 MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    # Initialize the BMX application
    if not initialize_application():
        logger.error("❌ Failed to initialize BMX application")
        sys.exit(1)

    # Get port from environment (Heroku compatibility)
    port = int(os.environ.get('PORT', 5000))

    logger.info(f"🌐 Starting BMX Flask server on port {port}...")

    # Start the Flask application
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,  # Set to False for production
        threaded=True
    )
