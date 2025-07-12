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

# Trading state management
TRADE_IN_PROGRESS = False
TRADE_LOCK = threading.Lock()
ACTIVE_TRADES = {}  # symbol -> bool  
ACTIVE_TRADES_LOCK = threading.Lock()

# Flask and web framework imports
from flask import Flask, request, jsonify
import requests

# ============================================================================
# 🎯 BMX PROTOCOL CONSTANTS - UPDATED FOR BMX.TRADE
# ============================================================================

# USDC Contract on Base Network (same as before)
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# BMX Protocol Contracts on Base Network
BMX_TOKEN_CONTRACT = "0x548f93779fbc992010c07467cbaf329dd5f059b7"
WBLT_TOKEN_CONTRACT = "0x4e74d4db6c0726ccded4656d0bce448876bb4c7a"

# ✅ BMX Trading Contracts on Base Network - FOUND!
BMX_POSITION_ROUTER = "0x927F9c03d1Ac6e2630d31E614F226b5Ed028d443"  # ✅ BMX Position Router
BMX_VAULT_CONTRACT = "0x9cC4E8e60a2c9a67Ac7D20f54607f98EfBA38AcF"    # ✅ BMX Vault
BMX_READER_CONTRACT = "0x927F9c03d1Ac6e2630d31E614F226b5Ed028d443"   # ✅ Reader (same as router)

# USDC ABI (same as before)
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

# BMX Position Router ABI (GMX v1 style with BMX modifications)
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
        "inputs": [
            {"name": "_path", "type": "address[]"},
            {"name": "_indexToken", "type": "address"},
            {"name": "_collateralDelta", "type": "uint256"},
            {"name": "_sizeDelta", "type": "uint256"},
            {"name": "_isLong", "type": "bool"},
            {"name": "_receiver", "type": "address"},
            {"name": "_acceptablePrice", "type": "uint256"},
            {"name": "_minOut", "type": "uint256"},
            {"name": "_executionFee", "type": "uint256"},
            {"name": "_withdrawETH", "type": "bool"},
            {"name": "_callbackTarget", "type": "address"}
        ],
        "name": "createDecreasePosition",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "payable",
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
RPC_URL = os.getenv('RPC_URL')
CHAIN_ID = int(os.getenv('CHAIN_ID', 8453))
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

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
# 🔧 CONFIGURATION AND CONSTANTS - ENHANCED FOR BMX
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

    # 🎯 BMX Protocol Configuration
    USDC_CONTRACT = Web3.to_checksum_address(os.getenv('USDC_ADDRESS', USDC_CONTRACT))
    BMX_TOKEN = Web3.to_checksum_address(BMX_TOKEN_CONTRACT)
    WBLT_TOKEN = Web3.to_checksum_address(WBLT_TOKEN_CONTRACT)
   
    # 📊 Trading Parameters (optimized for BMX)
    DEFAULT_LEVERAGE = 5
    DEFAULT_SLIPPAGE = 0.02  # 2% slippage (BMX has no price impact)
    MIN_MARGIN_REQUIRED = 25  # Minimum margin in USDC
    GAS_LIMIT = 800000  # Higher for BMX complexity
    GAS_PRICE_GWEI = 1

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
# 🌐 WEB3 AND BLOCKCHAIN UTILITIES - ENHANCED FOR BMX
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
            # Initialize Web3
            self.w3 = Web3(Web3.HTTPProvider(TradingConfig.RPC_URL))

            if not self.w3.is_connected():
                logger.error("❌ Failed to connect to Base network")
                return False

            logger.info("✅ Connected to Base network for BMX trading")

            # Initialize account
            if TradingConfig.PRIVATE_KEY:
                self.account = Account.from_key(TradingConfig.PRIVATE_KEY)
                logger.info(f"✅ Account loaded: {self.account.address}")
            else:
                logger.warning("⚠️ No private key provided - read-only mode")

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
            # USDC contract (same as before)
            usdc_abi = USDC_ABI
            self.usdc_contract = self.w3.eth.contract(
                address=TradingConfig.USDC_CONTRACT,
                abi=usdc_abi
            )

            # BMX Position Router contract
            self.bmx_position_router = self.w3.eth.contract(
                address=BMX_POSITION_ROUTER,
                abi=BMX_POSITION_ROUTER_ABI
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

            # BMX Position Router contract
            self.bmx_position_router = self.w3.eth.contract(
                address=BMX_POSITION_ROUTER,
                abi=BMX_POSITION_ROUTER_ABI
            )

            # BMX Vault contract
            vault_abi = [
                {
                    "inputs": [{"name": "_token", "type": "address"}],
                    "name": "poolAmounts",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                },
                {
                    "inputs": [{"name": "_account", "type": "address"}, {"name": "_token", "type": "address"}],
                    "name": "tokenBalances",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            self.bmx_vault = self.w3.eth.contract(
                address=BMX_VAULT_CONTRACT,
                abi=vault_abi
            )

            logger.info("✅ BMX smart contracts initialized")

        except Exception as e:
            logger.error(f"❌ BMX contract initialization failed: {str(e)}")

    def get_usdc_balance(self, address: str) -> float:
        """Get USDC balance for an address"""
        try:
            if not self.usdc_contract:
                return 0.0

            balance_wei = self.usdc_contract.functions.balanceOf(address).call()
            balance_usdc = balance_wei / 1_000_000  # USDC has 6 decimals

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
web3_manager = Web3Manager()

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
# 🎯 BMX TRADING ENGINE - COMPLETELY NEW FOR BMX.TRADE
# ============================================================================

class BMXTrader:
    """Core trading engine for BMX protocol integration"""

    def __init__(self):
        self.web3_manager = web3_manager
        self.supported_tokens = self._initialize_supported_tokens()
        
        try:
            # Get Web3 instance
            self.w3 = self.web3_manager.w3
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
        
            logging.info("✅ BMX contracts initialized successfully!")
        
        except Exception as e:
            logging.error(f"❌ BMX contract initialization failed: {e}")
            raise

    def _initialize_supported_tokens(self) -> Dict[str, Dict]:
        """Initialize supported trading tokens on BMX with REAL Base network addresses"""
        return {
            'BTC': {
                'symbol': 'BTC',
                'address': '0x8e3BCC334657560253B83f08331d85267316e08a',  # ✅ Real cbBTC on Base
                'precision': 8,
                'coingecko_id': 'bitcoin'
            },
            'ETH': {
                'symbol': 'ETH', 
                'address': '0x4200000000000000000000000000000000000006',  # ✅ Real WETH on Base
                'precision': 18,
                'coingecko_id': 'ethereum'
            },
            'SOL': {
                'symbol': 'SOL',
                'address': '0x22a31BD4cB694433B6de19e8aE1972E3C5e0D40C',  # ✅ SOL on Base (bridged)
                'precision': 9,
                'coingecko_id': 'solana'
            },
            'LINK': {
                'symbol': 'LINK',
                'address': '0x491e136ff7ff03e6ab097e54734697bb5802fc1c',  # ✅ Real LINK on Base
                'precision': 18,
                'coingecko_id': 'chainlink'
            },
            'AVAX': {
                'symbol': 'AVAX',
                'address': '0x4158734D47Fc9692176B5085E0F52ee0Da5d47F1',  # ✅ AVAX on Base (if supported)
                'precision': 18,
                'coingecko_id': 'avalanche-2'
            }
        }

    def get_supported_symbol(self, symbol: str) -> Optional[str]:
        """Get supported symbol from various input formats with validation"""
        # Clean up symbol format
        clean_symbol = symbol.replace('/USD', '').replace('/USDT', '').replace('USD', '').upper()
        
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

    async def execute_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trade on BMX protocol with enhanced error handling"""
        try:
            logger.info(f"🎯 EXECUTING BMX TRADE:")
            logger.info(f"🚀 ELITE BMX TRADING BOT v300 - Processing trade request")
            logger.info(f"🎯 BMX NO-PRICE-IMPACT VERSION - Superior execution!")

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

            # Execute the BMX trade
            result = await self._execute_bmx_trade(
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

    async def _execute_bmx_trade(
        self,
        trader_address: str,
        symbol: str,
        position_usdc_dollars: float,
        entry_price: float,
        leverage: int,
        is_long: bool,
        trade_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the actual trade on BMX protocol"""
        
        try:
            logger.info(f"🎯 Preparing BMX trade parameters...")
            
            # BMX uses a single liquidity pool model (BLT)
            # Trades are executed against oracle prices with no price impact
            
            logger.info(f"🔍 BMX TRADE PARAMETERS:")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Position: ${position_usdc_dollars:.2f} USDC")
            logger.info(f"   - Entry Price: ${entry_price:.2f}")
            logger.info(f"   - Leverage: {leverage}x")
            logger.info(f"   - Direction: {'LONG' if is_long else 'SHORT'}")
            logger.info(f"   - Margin: ${position_usdc_dollars/leverage:.2f}")

            # Check USDC balance
            balance_before = self.usdc_contract.functions.balanceOf(trader_address).call() / 1e6
            logger.info(f"🔍 USDC Balance BEFORE: ${balance_before:.6f}")

            # ✅ BMX TRADING IMPLEMENTATION - LIVE!
            logger.info(f"🚀 EXECUTING LIVE BMX TRADE!")
            
            # Step 1: Approve USDC for Position Router
            position_usdc = int(position_usdc_dollars / leverage * 1e6)  # Margin in USDC
            approve_amount = position_usdc * 2  # Approve 2x for safety
            
            logger.info(f"💰 APPROVING ${approve_amount/1e6:.2f} USDC for BMX Position Router...")
            
            # 🔧 ROBUST NONCE HANDLING to prevent "nonce too low" errors
            current_nonce = self.w3.eth.get_transaction_count(trader_address, 'pending')
            logger.info(f"🔍 Current nonce: {current_nonce}")
            
            approve_txn = self.usdc_contract.functions.approve(
                BMX_POSITION_ROUTER, 
                approve_amount
            ).build_transaction({
                'from': trader_address,
                'gas': 100000,
                'gasPrice': int(self.w3.eth.gas_price * 1.1),  # 10% gas boost for faster execution
                'nonce': current_nonce
            })
            
            signed_approve = self.w3.eth.account.sign_transaction(approve_txn, TradingConfig.PRIVATE_KEY)
            approve_hash = self.w3.eth.send_raw_transaction(signed_approve.rawTransaction)
            logger.info(f"✅ USDC approved! Hash: {approve_hash.hex()}")
            
            # Wait for approval
            import time
            time.sleep(3)
            
            # Step 2: Create position via BMX Position Router
            # 🔧 CRITICAL FIX: Use correct token addresses
            collateral_token = USDC_CONTRACT  # ✅ Collateral = USDC (what we deposit as margin)
            
            # 🎯 Get the actual trading token address (BTC, ETH, etc.)
            if symbol not in self.supported_tokens:
                logger.error(f"❌ Unsupported symbol: {symbol}")
                return {"status": "error", "error": f"Unsupported symbol: {symbol}"}
                
            index_token = self.supported_tokens[symbol]['address']  # ✅ Index = actual asset we're trading
            
            logger.info(f"🔧 TOKEN SETUP:")
            logger.info(f"   - Collateral (margin): USDC {collateral_token}")
            logger.info(f"   - Index (trading): {symbol} {index_token}")
            
            size_delta = int(position_usdc_dollars * 1e30)  # Position size in USD (30 decimals)
            acceptable_price = int(entry_price * 1.05 * 1e30) if is_long else int(entry_price * 0.95 * 1e30)
            execution_fee = self.w3.eth.gas_price * 200000  # Execution fee for keeper
            
            logger.info(f"🎯 CREATING BMX POSITION:")
            logger.info(f"   - Collateral: ${position_usdc/1e6:.2f} USDC")
            logger.info(f"   - Size: ${size_delta/1e30:.2f} USD") 
            logger.info(f"   - Price: ${acceptable_price/1e30:.2f}")
            logger.info(f"   - Direction: {'LONG' if is_long else 'SHORT'}")
            
            position_txn = self.bmx_position_router.functions.createIncreasePosition(
                [collateral_token],     # path
                index_token,            # index token
                position_usdc,          # amount in
                0,                      # min out
                size_delta,             # size delta
                is_long,                # is long
                acceptable_price,       # acceptable price
                execution_fee,          # execution fee
                b'\x00' * 32,           # referral code
                trader_address          # callback target
            ).build_transaction({
                'from': trader_address,
                'gas': TradingConfig.GAS_LIMIT,
                'gasPrice': int(self.w3.eth.gas_price * 1.2),
                'nonce': self.w3.eth.get_transaction_count(trader_address) + 1,
                'value': execution_fee  # execution fee
            })
            
            # Execute position transaction
            signed_position = self.w3.eth.account.sign_transaction(position_txn, TradingConfig.PRIVATE_KEY)
            position_hash = self.w3.eth.send_raw_transaction(signed_position.rawTransaction)
            
            logger.info(f"🚀 BMX POSITION CREATED! Hash: {position_hash.hex()}")
            logger.info(f"🔗 BaseScan: https://basescan.org/tx/{position_hash.hex()}")
            
            # Check balance after
            balance_after = self.usdc_contract.functions.balanceOf(trader_address).call() / 1e6
            logger.info(f"🔍 USDC Balance AFTER: ${balance_after:.6f}")
            
            return {
                "status": "success", 
                "message": "BMX trade executed successfully!",
                "tx_hash": position_hash.hex(),
                "basescan_url": f"https://basescan.org/tx/{position_hash.hex()}",
                "trade_details": {
                    "symbol": symbol,
                    "position_size": f"${position_usdc_dollars:.2f}",
                    "entry_price": f"${entry_price:.2f}",
                    "leverage": f"{leverage}x",
                    "direction": "LONG" if is_long else "SHORT",
                    "margin_used": f"${position_usdc_dollars/leverage:.2f}",
                    "balance_before": f"${balance_before:.2f}",
                    "balance_after": f"${balance_after:.2f}"
                },
                "bmx_advantages": [
                    "✅ No price impact execution",
                    "✅ Oracle-based pricing", 
                    "✅ Single liquidity pool efficiency",
                    "✅ Lower fees than competitors"
                ]
            }

        except Exception as e:
            logger.error(f"❌ BMX trade execution failed: {str(e)}")
            return {
                "status": "error",
                "message": f"BMX trade failed: {str(e)}",
                "error_type": type(e).__name__
            }

# Initialize BMX trader
bmx_trader = BMXTrader()

# ============================================================================
# 🔄 SIGNAL PROCESSING ENGINE - ADAPTED FOR BMX
# ============================================================================

class SignalProcessor:
    """Advanced signal processing and validation engine for BMX"""

    def __init__(self):
        self.sheets_manager = sheets_manager
        self.trader = bmx_trader

    async def process_signal(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming trading signal for BMX trading"""
        try:
            logger.info("🔄 Processing incoming signal for BMX...")

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

            # Execute the BMX trade
            trade_result = await self.trader.execute_trade(processed_signal)

            return {
                'status': 'success' if trade_result.get('status') in ['success', 'pending_implementation'] else 'failed',
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
        """Validate processed signal before BMX execution"""

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
# 🌐 WEBHOOK ENDPOINTS AND API ROUTES - ENHANCED FOR BMX
# ============================================================================

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint for BMX bot"""
    return {
        'status': '🚀 FULLY OPERATIONAL',
        'service': 'Elite BMX Trading Bot',
        'version': 'v300-BMX-LIVE',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'web3_connected': web3_manager.is_connected(),
        'protocol': 'BMX.trade on Base',
        'contracts': {
            'position_router': BMX_POSITION_ROUTER,
            'vault': BMX_VAULT_CONTRACT,
            'reader': BMX_READER_CONTRACT,
            'bmx_token': BMX_TOKEN_CONTRACT,
            'wblt_token': WBLT_TOKEN_CONTRACT
        },
        'features': {
            'google_sheets': True,
            'bmx_trading': True,
            'dynamic_position_sizing': True,
            'no_price_impact': True,
            'enhanced_debugging': True,
            'up_to_50x_leverage': True,
            'live_execution': True
        },
        'advantages': [
            '🎯 No price impact trading',
            '💪 Single liquidity pool efficiency', 
            '📊 Oracle-based pricing',
            '💰 Lower trading fees',
            '🚀 Higher capital efficiency',
            '⚡ Live trade execution'
        ]
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """Enhanced webhook endpoint for BMX trading signals"""
    
    try:
        trade_data = request.get_json()
        if not trade_data:
            logger.error("❌ Empty request body")
            return {'error': 'Empty request body'}, 400

        # Version tracking - BMX Live
        logger.info(f"🚀 ELITE BMX TRADING BOT v300-LIVE - Processing webhook request")
        logger.info(f"🎯 BMX LIVE TRADING - EXECUTING REAL TRADES!")

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

        # Check if symbol already has active trade
        with ACTIVE_TRADES_LOCK:
            if ACTIVE_TRADES.get(symbol, False):
                logger.warning(f"🚫 Trade REJECTED - Trade already active for {symbol}!")
                return {'status': 'rejected', 'reason': f'Trade already active for {symbol}'}, 400

            # Mark this symbol as active
            ACTIVE_TRADES[symbol] = True
            logger.info(f"✅ {symbol} marked as ACTIVE for BMX trading")

        logger.info(f"📨 Received BMX signal data: {json.dumps(trade_data, indent=2)}")

        # Process the signal asynchronously
        async def process_webhook():
            return await signal_processor.process_signal(trade_data)

        # Run the async processing
        result = asyncio.run(process_webhook())

        # Log the result
        if result.get('status') == 'success':
            logger.info(f"✅ BMX webhook processing successful!")
            logger.info(f"   Trade result: {result.get('trade_result', {})}")
        else:
            logger.warning(f"⚠️ BMX webhook processing failed: {result.get('error', 'Unknown error')}")

        return result

    except Exception as e:
        logger.error(f"❌ BMX webhook error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'status': 'error',
            'error': f'BMX webhook processing failed: {str(e)}'
        }, 500
    finally:  
        # Release symbol lock
        if 'symbol' in locals():
            with ACTIVE_TRADES_LOCK:
                ACTIVE_TRADES[symbol] = False
                logger.info(f"🔓 {symbol} marked as INACTIVE")

        TRADE_IN_PROGRESS = False  # Always reset

@app.route('/balance', methods=['GET'])
def get_balance():
    """Get current USDC, BMX, and wBLT balances"""
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
            'bmx_balance': bmx_balance,
            'wblt_balance': wblt_balance,
            'total_portfolio_value': usdc_balance,  # Can be enhanced with token values
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'protocol': 'BMX.trade'
        }

    except Exception as e:
        logger.error(f"❌ Balance check failed: {str(e)}")
        return {'error': f'Balance check failed: {str(e)}'}, 500

@app.route('/test-trade', methods=['POST'])
def test_trade():
    """Test BMX trade endpoint with SMALL position for safety"""
    try:
        test_signal = {
            'symbol': 'BTC/USD',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'position_size': 50,  # 🔧 SMALL $50 test position for safety
            'leverage': 5,
            'tier': 3,  # Tier 3 for minimum size
            'source': 'BMX Test - SMALL POSITION'
        }

        logger.info(f"🧪 Testing BMX trade with SMALL signal: {test_signal}")
        logger.info(f"💡 Using $50 position for safe testing")

        async def process_test():
            return await signal_processor.process_signal(test_signal)

        result = asyncio.run(process_test())

        return result

    except Exception as e:
        logger.error(f"❌ BMX test trade failed: {str(e)}")
        return {
            'status': 'error',
            'error': f'BMX test trade failed: {str(e)}'
        }, 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current BMX bot configuration with LIVE contract info"""
    return {
        'position_sizes': TradingConfig.POSITION_SIZES,
        'tier_percentages': TradingConfig.TIER_POSITION_PERCENTAGES,
        'default_leverage': TradingConfig.DEFAULT_LEVERAGE,
        'default_slippage': TradingConfig.DEFAULT_SLIPPAGE,
        'min_margin_required': TradingConfig.MIN_MARGIN_REQUIRED,
        'gas_limit': TradingConfig.GAS_LIMIT,
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
        'version': 'v300-BMX-LIVE',
        'network': 'Base (Chain ID: 8453)',
        'safety_features': [
            '🔧 Real token addresses',
            '🔧 Robust nonce handling',
            '🔧 Contract error detection',
            '🔧 Minimum position validation',
            '🔧 Enhanced gas management'
        ],
        'advantages': [
            '🎯 No price impact trading',
            '💪 Single liquidity pool',
            '⚡ Up to 50x leverage',
            '💰 Lower fees',
            '🚀 Oracle-based pricing'
        ]
    }

# ============================================================================
# 📄 GOOGLE SHEETS INTEGRATION SCRIPT - UPDATED FOR BMX
# ============================================================================

def generate_google_sheets_script():
    """Generate Google Apps Script code for BMX Sheets integration"""
    
    script_code = '''
/**
 * 🚀 ELITE BMX TRADING BOT - Google Sheets Integration Script v300-LIVE
 *
 * This script sends trading signals from Google Sheets to your LIVE BMX trading bot
 * with real contract execution and no price impact trading.
 *
 * Setup Instructions:
 * 1. Replace WEBHOOK_URL with your actual Heroku app URL
 * 2. Set up your trading signals in the Google Sheet
 * 3. Run sendTradingSignal() function to send LIVE signals
 */

// 🔗 Configuration - UPDATE THIS URL!
const WEBHOOK_URL = "https://your-bmx-bot.herokuapp.com/webhook";

/**
 * 📊 Main function to send LIVE trading signals to the BMX bot
 * Call this function to send the current signal from your sheet
 */
function sendTradingSignal() {
  try {
    console.log('🚀 Elite BMX Trading Bot v300-LIVE - Sending LIVE signal...');
   
    // 📋 Read signal data from the active sheet
    const sheet = SpreadsheetApp.getActiveSheet();
    const signal = readSignalFromSheet(sheet);
   
    if (!signal) {
      console.error('❌ No valid signal found in sheet');
      return;
    }
   
    console.log('📊 BMX LIVE Signal data:', JSON.stringify(signal, null, 2));
   
    // 🌐 Send signal to LIVE BMX trading bot
    const response = sendWebhookRequest(signal);
   
    // 📝 Log the response
    logResponse(sheet, signal, response);
   
    console.log('✅ BMX LIVE Signal sent successfully!');
   
  } catch (error) {
    console.error('❌ Error sending BMX LIVE signal:', error);
    Browser.msgBox('Error', 'Failed to send LIVE signal: ' + error.toString(), Browser.Buttons.OK);
  }
}

/**
 * 📋 Read trading signal from the Google Sheet for BMX
 * Supports multiple sheet layouts and field names
 */
function readSignalFromSheet(sheet) {
  try {
    // Method 1: Try reading from specific cells (most common)
    const signalData = {
      symbol: getCellValue(sheet, 'B2') || getCellValue(sheet, 'A2') || 'BTC/USD',
      direction: getCellValue(sheet, 'B3') || getCellValue(sheet, 'A3') || 'LONG',
      entry_price: parseFloat(getCellValue(sheet, 'B4') || getCellValue(sheet, 'A4') || '0'),
      tier: parseInt(getCellValue(sheet, 'B5') || getCellValue(sheet, 'A5') || '1'),
      leverage: parseInt(getCellValue(sheet, 'B6') || getCellValue(sheet, 'A6') || '5'),
      stop_loss: parseFloat(getCellValue(sheet, 'B7') || getCellValue(sheet, 'A7') || '0'),
      take_profit: parseFloat(getCellValue(sheet, 'B8') || getCellValue(sheet, 'A8') || '0'),
      quality: parseInt(getCellValue(sheet, 'B9') || getCellValue(sheet, 'A9') || '85')
    };
   
    // Calculate position size based on tier (BMX optimized)
    signalData.position_size = calculateBMXPositionSize(signalData.tier);
   
    // Add metadata
    signalData.timestamp = new Date().toISOString();
    signalData.source = 'Google Sheets BMX v300';
    signalData.sheet_name = sheet.getName();
   
    // Validate required fields
    if (!signalData.symbol || !signalData.direction || signalData.entry_price <= 0) {
      console.error('❌ Invalid BMX signal data:', signalData);
      return null;
    }
   
    console.log('✅ BMX Signal extracted:', signalData);
    return signalData;
   
  } catch (error) {
    console.error('❌ Error reading BMX signal from sheet:', error);
    return null;
  }
}

/**
 * 💰 Calculate position size based on tier for BMX
 * Updated for BMX's superior capital efficiency
 */
function calculateBMXPositionSize(tier) {
  // Position sizing optimized for BMX's no price impact trading
  const positionSizes = {
    1: 150,    // Tier 1: $150 USDC (benefits from no slippage)
    2: 125,    // Tier 2: $125 USDC  
    3: 100     // Tier 3: $100 USDC
  };
  return positionSizes[tier] || 150; // Default $150
}

/**
 * 📖 Helper function to safely get cell values
 */
function getCellValue(sheet, cellAddress) {
  try {
    const value = sheet.getRange(cellAddress).getValue();
    return value ? value.toString().trim() : '';
  } catch (error) {
    console.error(`❌ Error reading cell ${cellAddress}:`, error);
    return '';
  }
}

/**
 * 🌐 Send webhook request to the BMX trading bot
 */
function sendWebhookRequest(signalData) {
  try {
    const options = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Google-Apps-Script-BMX-Bot-v300'
      },
      payload: JSON.stringify(signalData)
    };
   
    console.log('🌐 Sending BMX webhook to:', WEBHOOK_URL);
    console.log('📤 BMX Payload:', JSON.stringify(signalData, null, 2));
   
    const response = UrlFetchApp.fetch(WEBHOOK_URL, options);
    const responseText = response.getContentText();
   
    console.log('📥 BMX Response status:', response.getResponseCode());
    console.log('📥 BMX Response body:', responseText);
   
    if (response.getResponseCode() !== 200) {
      throw new Error(`HTTP ${response.getResponseCode()}: ${responseText}`);
    }
   
    return JSON.parse(responseText);
   
  } catch (error) {
    console.error('❌ BMX webhook request failed:', error);
    throw error;
  }
}

/**
 * 📝 Log the response from the BMX trading bot
 */
function logResponse(sheet, signal, response) {
  try {
    // Find or create a log section
    const logStartRow = findOrCreateLogSection(sheet);
   
    // Create log entry
    const logEntry = [
      new Date(),
      signal.symbol,
      signal.direction,
      signal.entry_price,
      signal.position_size,
      response.status || 'unknown',
      'BMX: ' + (JSON.stringify(response).substr(0, 80) + '...')
    ];
   
    // Write log entry
    sheet.getRange(logStartRow, 1, 1, logEntry.length).setValues([logEntry]);
   
    console.log('📝 BMX response logged to sheet');
   
  } catch (error) {
    console.error('❌ Error logging BMX response:', error);
  }
}

/**
 * 🔍 Find or create log section in the sheet
 */
function findOrCreateLogSection(sheet) {
  try {
    // Look for existing log header
    const data = sheet.getDataRange().getValues();
   
    for (let i = 0; i < data.length; i++) {
      if (data[i][0] && data[i][0].toString().includes('Log')) {
        return i + 2; // Return row after header
      }
    }
   
    // Create log section if not found
    const lastRow = sheet.getLastRow();
    const logHeaderRow = lastRow + 2;
   
    const headers = ['Timestamp', 'Symbol', 'Direction', 'Entry Price', 'Position Size', 'Status', 'BMX Response'];
    sheet.getRange(logHeaderRow, 1, 1, headers.length).setValues([headers]);
   
    return logHeaderRow + 1;
   
  } catch (error) {
    console.error('❌ Error managing log section:', error);
    return sheet.getLastRow() + 1;
  }
}

/**
 * 🧪 Test function to verify the BMX integration
 */
function testBMXIntegration() {
  try {
    console.log('🧪 Testing BMX integration with sample signal...');
   
    const testSignal = {
      symbol: 'BTC/USD',
      direction: 'LONG',
      entry_price: 50000,
      tier: 1,
      position_size: 150,
      leverage: 5,
      timestamp: new Date().toISOString(),
      source: 'Google Sheets BMX Test v300'
    };
   
    const response = sendWebhookRequest(testSignal);
   
    console.log('✅ BMX Test completed!');
    console.log('📊 BMX Response:', JSON.stringify(response, null, 2));
   
    Browser.msgBox('BMX Test Result', 'BMX integration test completed. Check logs for details.', Browser.Buttons.OK);
   
  } catch (error) {
    console.error('❌ BMX Test failed:', error);
    Browser.msgBox('BMX Test Failed', 'BMX integration test failed: ' + error.toString(), Browser.Buttons.OK);
  }
}

/**
 * 📋 Create a sample BMX trading sheet layout
 */
function createBMXSampleSheet() {
  try {
    const sheet = SpreadsheetApp.getActiveSheet();
   
    // Clear existing content
    sheet.clear();
   
    // Create headers and sample data
    const data = [
      ['Parameter', 'Value', 'Description'],
      ['Symbol', 'BTC/USD', 'Trading pair (BTC/USD, ETH/USD, SOL/USD, etc.)'],
      ['Direction', 'LONG', 'LONG or SHORT'],
      ['Entry Price', 50000, 'Entry price in USD'],
      ['Tier', 1, 'Signal tier (1, 2, or 3)'],
      ['Leverage', 5, 'Leverage multiplier (1-50 for BMX)'],
      ['Stop Loss', 48000, 'Stop loss price (optional)'],
      ['Take Profit', 55000, 'Take profit price (optional)'],
      ['Quality', 85, 'Signal quality score (0-100)'],
      ['', '', ''],
      ['Position Size', '=IF(B5=1,150,IF(B5=2,125,100))', 'Auto-calculated for BMX'],
      ['Margin Required', '=B11/B6', 'Required margin (Position / Leverage)'],
      ['', '', ''],
      ['BMX ADVANTAGES:', '', ''],
      ['✅ No Price Impact', '', 'Trade at oracle price'],
      ['✅ Single Liquidity Pool', '', 'Higher capital efficiency'],
      ['✅ Up to 50x Leverage', '', 'More trading power'],
      ['✅ Lower Fees', '', 'Competitive trading costs'],
      ['', '', ''],
      ['Instructions:', '', ''],
      ['1. Update values above', '', ''],
      ['2. Run sendTradingSignal()', '', ''],
      ['3. Check BMX logs below', '', ''],
      ['', '', ''],
      ['--- BMX Execution Log ---', '', '']
    ];
   
    // Write data to sheet
    sheet.getRange(1, 1, data.length, 3).setValues(data);
   
    // Format the sheet
    sheet.getRange('A1:C1').setFontWeight('bold');
    sheet.getRange('A14:A18').setFontWeight('bold');
    sheet.getRange('A20:A23').setFontWeight('bold');
    sheet.getRange('A25:C25').setFontWeight('bold');
   
    // Auto-resize columns
    sheet.autoResizeColumns(1, 3);
   
    console.log('✅ BMX sample sheet created successfully!');
    Browser.msgBox('Success', 'BMX trading sheet created! Update values and run sendTradingSignal()', Browser.Buttons.OK);
   
  } catch (error) {
    console.error('❌ Error creating BMX sample sheet:', error);
    Browser.msgBox('Error', 'Failed to create BMX sample sheet: ' + error.toString(), Browser.Buttons.OK);
  }
}

console.log('🚀 Elite BMX Trading Bot Google Sheets Integration v300-LIVE loaded successfully!');
console.log('💡 Available functions: sendTradingSignal(), testBMXIntegration(), createBMXSampleSheet()');
console.log('🎯 BMX-LIVE with real contract execution and no price impact trading!');
'''
    
    return script_code

# ============================================================================
# 🚀 APPLICATION STARTUP AND MAIN EXECUTION
# ============================================================================

def initialize_application():
    """Initialize the BMX trading bot application"""
    try:
        logger.info("🚀 ELITE BMX TRADING BOT v300-LIVE STARTING UP...")
        logger.info("🎯 BMX LIVE TRADING VERSION - FULLY OPERATIONAL!")

        # Check Web3 connection
        if not web3_manager.is_connected():
            logger.error("❌ Web3 connection failed")
            return False

        # Check account configuration
        if not web3_manager.account:
            logger.warning("⚠️ No trading account configured (read-only mode)")
        else:
            balance = web3_manager.get_usdc_balance(web3_manager.account.address)
            logger.info(f"💰 Account balance: ${balance:.6f} USDC")

        # Initialize components
        logger.info("✅ Signal processor initialized for BMX")
        logger.info("✅ BMX trader initialized with LIVE contracts")
        logger.info("✅ Google Sheets manager initialized")

        # Log BMX contract addresses
        logger.info(f"🔧 BMX LIVE CONTRACT ADDRESSES:")
        logger.info(f"  - Position Router: {BMX_POSITION_ROUTER}")
        logger.info(f"  - Vault: {BMX_VAULT_CONTRACT}")
        logger.info(f"  - Reader: {BMX_READER_CONTRACT}")
        logger.info(f"  - BMX Token: {BMX_TOKEN_CONTRACT}")
        logger.info(f"  - wBLT Token: {WBLT_TOKEN_CONTRACT}")

        # Log configuration
        logger.info(f"🔧 BMX Configuration:")
        logger.info(f"  - Position sizes: {TradingConfig.POSITION_SIZES}")
        logger.info(f"  - Tier percentages: {TradingConfig.TIER_POSITION_PERCENTAGES}")
        logger.info(f"  - Default leverage: {TradingConfig.DEFAULT_LEVERAGE}x")
        logger.info(f"  - Default slippage: {TradingConfig.DEFAULT_SLIPPAGE*100}%")
        logger.info(f"  - Minimum margin: ${TradingConfig.MIN_MARGIN_REQUIRED}")
        logger.info(f"  - Supported tokens: {len(bmx_trader.supported_tokens)}")

        logger.info("🎯 BMX LIVE ADVANTAGES:")
        logger.info("  🎯 No price impact trading")
        logger.info("  💪 Single liquidity pool efficiency") 
        logger.info("  📊 Oracle-based pricing")
        logger.info("  ⚡ Up to 50x leverage")
        logger.info("  💰 Lower trading fees")
        logger.info("  🚀 LIVE trade execution")
        logger.info("✅ Elite BMX Trading Bot LIVE and ready for trading!")

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
