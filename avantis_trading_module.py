import os

from web3 import Web3

import random

import logging

from avantis_trader_sdk import TraderClient
from avantis_trader_sdk.types import TradeInput

import avantis_trader_sdk
print("🔍 Avantis SDK version:", avantis_trader_sdk.__version__)

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

TRADE_IN_PROGRESS = False
TRADE_LOCK = threading.Lock()# Flask and web framework imports

ACTIVE_TRADES = {}  # symbol -> bool  
ACTIVE_TRADES_LOCK = threading.Lock()

from flask import Flask, request, jsonify

# flask_cors import CORS

import requests

# USDC Contract on Base Network (CONFIRMED)
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# USDC ABI (minimal for balance checking)
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
    }
]


# ========== END CONSTANTS ==========

# Web3 and blockchain imports

from web3 import Web3

from web3.exceptions import Web3Exception, ContractLogicError

import eth_account

from eth_account import Account

 

# Data processing imports

import pandas as pd

import numpy as np

 

# Google Sheets API imports (commented for Heroku deployment)

# from google.oauth2.service_account import Credentials

# import gspread

 

# Environment and configuration

from dotenv import load_dotenv

# Load environment variables

load_dotenv()

# 🔍 LIVE PRICE FETCHING - NEW DEBUGGING FEATURE
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
        
AVANTIS_TRADING_CONTRACT = Web3.to_checksum_address('0x44914408af82bC9983bbb330e3578E1105e11d4e')
RPC_URL = os.getenv('RPC_URL')
CHAIN_ID = int(os.getenv('CHAIN_ID', 8453))
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# ✅ Load official Avantis Trading contract using SDK
from avantis_trader_sdk import TraderClient

# Manually define the official Avantis Trading contract (confirmed)
avantis_contract_address = "0x05B9E58232f15E44C5646aBd2Cd2736D6f81f8A6"  # <-- This is the real one from earlier

# Correct Avantis ABI with openTrade function
AVANTIS_TRADING_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "trader", "type": "address"},
                    {"name": "pairIndex", "type": "uint256"},
                    {"name": "index", "type": "uint256"},
                    {"name": "initialPosToken", "type": "uint256"},
                    {"name": "positionSizeUSDC", "type": "uint256"},
                    {"name": "openPrice", "type": "uint256"},
                    {"name": "buy", "type": "bool"},
                    {"name": "leverage", "type": "uint256"},
                    {"name": "tp", "type": "uint256"},
                    {"name": "sl", "type": "uint256"},
                    {"name": "timestamp", "type": "uint256"}
                ],
                "name": "t",
                "type": "tuple"
            },
            {"name": "_type", "type": "uint8"},
            {"name": "_slippageP", "type": "uint256"}
        ],
        "name": "openTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
# Configure logging with enhanced formatting

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',

    handlers=[

        logging.StreamHandler(sys.stdout),

        logging.FileHandler('trading_bot.log') if os.path.exists('.') else logging.StreamHandler(sys.stdout)

    ]

)

 

logger = logging.getLogger('avantis_trading_module')

 

# Flask application setup

app = Flask(__name__)

# CORS(app)

 
# ============================================================================

# 🔧 CONFIGURATION AND CONSTANTS 

# ============================================================================

 

class TradingConfig:

    """Centralized configuration for the trading bot"""

   

    # 🌐 Network Configuration

    RPC_URL = os.getenv('BASE_RPC_URL')

    CHAIN_ID = int(os.getenv('CHAIN_ID', 8453))  # Base network

    PRIVATE_KEY = os.getenv('PRIVATE_KEY')

    # 🎯 Dynamic Position Sizing Configuration
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



    # 🔐 Security Configuration

    PRIVATE_KEY = os.getenv('PRIVATE_KEY')

    # 🎯 Avantis Protocol Configuration

    USDC_CONTRACT = Web3.to_checksum_address(os.getenv('USDC_ADDRESS', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'))  # Base USDC

   

    # 📊 Trading Parameters

    DEFAULT_LEVERAGE = 5

    DEFAULT_SLIPPAGE = 0.03  # 3% slippage (reduced for better execution)

    MIN_MARGIN_REQUIRED = 25  # Minimum margin in USDC

    GAS_LIMIT = 500000

    GAS_PRICE_GWEI = 1


   

    # 🎯 Position Sizing Configuration

    POSITION_SIZES = {

        1: 100,    # Tier 1: $100 USDC (margin: $100/5 = $20)

        2: 150,    # Tier 2: $150 USDC (margin: $150/5 = $30) 

        3: 250     # Tier 3: $250 USDC (margin: $250/5 = $50)

    }

    DEFAULT_POSITION_SIZE = 100  # Default $100 (margin: $20)

   

    # 🔍 Debugging Configuration

    ENABLE_DETAILED_LOGGING = True

    LOG_TRADE_PARAMETERS = True

    LOG_BALANCE_CHECKS = True

 

# ============================================================================

# 🌐 WEB3 AND BLOCKCHAIN UTILITIES

# ============================================================================

class Web3Manager:

    """Manages Web3 connections and blockchain interactions"""

   

    def __init__(self):

        self.w3 = None

        self.account = None

        self.trading_contract = None

        self.usdc_contract = None

        self._initialize_web3()

       

    def _initialize_web3(self):

        """Initialize Web3 connection and contracts"""

        try:

            # Initialize Web3

            self.w3 = Web3(Web3.HTTPProvider(TradingConfig.RPC_URL))

           

            if not self.w3.is_connected():

                logger.error("❌ Failed to connect to Base network")

                return False

               

            logger.info("✅ Connected to Base network")

           

            # Initialize account

            if TradingConfig.PRIVATE_KEY:

                self.account = Account.from_key(TradingConfig.PRIVATE_KEY)

                logger.info(f"✅ Account loaded: {self.account.address}")

            else:

                logger.warning("⚠️ No private key provided - read-only mode")

               

            # Initialize contracts (simplified ABIs for core functions)

            self._initialize_contracts()

           

            return True

           

        except Exception as e:

            logger.error(f"❌ Web3 initialization failed: {str(e)}")

            return False

           

    def _initialize_contracts(self):

        """Initialize smart contract interfaces"""

        try:

            # Simplified trading contract ABI for openTrade function

            trading_abi = [

                {

                    "inputs": [

                        {

                            "components": [

                                {"name": "trader", "type": "address"},

                                {"name": "pairIndex", "type": "uint256"},

                                {"name": "index", "type": "uint256"},

                                {"name": "initialPosToken", "type": "uint256"},

                                {"name": "positionSizeUsdc", "type": "uint256"},

                                {"name": "openPrice", "type": "uint256"},

                                {"name": "buy", "type": "bool"},

                                {"name": "leverage", "type": "uint256"},

                                {"name": "tp", "type": "uint256"},

                                {"name": "sl", "type": "uint256"},

                                {"name": "timestamp", "type": "uint256"}

                            ],

                            "name": "trade",

                            "type": "tuple"

                        },

                        {"name": "orderType", "type": "uint8"},

                        {"name": "slippageP", "type": "uint256"}

                    ],

                    "name": "openTrade",

                    "outputs": [],

                    "stateMutability": "nonpayable",

                    "type": "function"

                }

            ]

           

            # USDC contract ABI for balance checking

            usdc_abi = [

                {

                    "inputs": [{"name": "account", "type": "address"}],

                    "name": "balanceOf",

                    "outputs": [{"name": "", "type": "uint256"}],

                    "stateMutability": "view",

                    "type": "function"

                },

                {

                    "inputs": [],

                    "name": "decimals",

                    "outputs": [{"name": "", "type": "uint8"}],

                    "stateMutability": "view",

                    "type": "function"

                }

            ]

           

            # Create contract instances

            self.trading_contract = self.w3.eth.contract(

                address=AVANTIS_TRADING_CONTRACT,

                abi=trading_abi

            )

           

            self.usdc_contract = self.w3.eth.contract(

                address=TradingConfig.USDC_CONTRACT,

                abi=usdc_abi

            )

           

            logger.info("✅ Smart contracts initialized")

           

        except Exception as e:

            logger.error(f"❌ Contract initialization failed: {str(e)}")

           

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

           

    def is_connected(self) -> bool:

        """Check if Web3 is connected"""

        return self.w3 and self.w3.is_connected()

 

# Initialize global Web3 manager

web3_manager = Web3Manager()

 

# ============================================================================

# 📊 GOOGLE SHEETS INTEGRATION

# ============================================================================

 

class GoogleSheetsManager:

    """Manages Google Sheets integration for signal processing"""

   

    def __init__(self):

        self.sheets_client = None

        # Note: Google Sheets integration is simplified for Heroku deployment

        # In production, you would use service account credentials

       

    def process_sheets_signal(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:

        """Process incoming signal from Google Sheets webhook"""

        try:

            logger.info("📊 Processing Google Sheets signal...")

           

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

           

            logger.info(f"✅ Processed signal: {symbol} {direction} ${position_size} @ ${entry_price}")

           

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

# 🎯 AVANTIS TRADING ENGINE

# ============================================================================

 

class AvantisTrader:

    """Core trading engine for Avantis protocol integration"""

   

    def __init__(self):

        self.web3_manager = web3_manager

        self.pair_mappings = self._initialize_pair_mappings()

        try:
            # Get Web3 instance
            self.w3 = self.web3_manager.w3
            self.wallet_address = self.web3_manager.account.address
        
            logging.info(f"📝 Wallet Address: {self.wallet_address}")
            logging.info(f"📝 USDC Contract: {USDC_CONTRACT}")
            logging.info(f"📝 Avantis Contract: {AVANTIS_TRADING_CONTRACT}")
        
            # Create contract instances
            self.usdc_contract = self.w3.eth.contract(
            address=USDC_CONTRACT,
            abi=USDC_ABI
            )
        
            self.avantis_contract = self.w3.eth.contract(
            address=AVANTIS_TRADING_CONTRACT,
            abi=AVANTIS_TRADING_ABI
            )
        
            logging.info("✅ Contracts initialized successfully!")
        
        except Exception as e:
            logging.error(f"❌ Contract initialization failed: {e}")
            raise
            
    async def fetch_avantis_pairs(self):
                """Fetch correct pair indices from Avantis SDK"""
                try:
                    provider_url = "https://mainnet.base.org"
                    trader_client = TraderClient(provider_url)
            
                    logger.info("🔍 Fetching Avantis pair mappings...")
                    pairs_info = await trader_client.pairs_cache.get_pairs_info()
            
                    logger.info(f"✅ Got pairs info: {pairs_info}")
            
                    # Build dynamic mapping
                    pair_mapping = {}
                    for pair_data in pairs_info:
                        symbol = f"{pair_data.get('from', 'UNKNOWN')}/{pair_data.get('to', 'USDT')}"
                        pair_index = pair_data.get('pairIndex', 0)
                        pair_mapping[symbol] = pair_index
                
                    logger.info(f"🎯 Built pair mapping: {pair_mapping}")
                    return pair_mapping
            
                except Exception as e:
                    logger.error(f"❌ Failed to fetch pairs: {e}")
                    return None

    def get_pair_index(self, symbol):
        """Get correct pair index with validation"""
        pair_index = self.pair_mappings.get(symbol)
        if pair_index is None:
            logger.error(f"❌ Symbol {symbol} not found in mappings!")
            return None
    
        # Warn about potentially unsupported pairs
        if symbol in ['AVAX/USDT', 'LINK/USDT'] and pair_index > 2:
            logger.warning(f"⚠️ {symbol} might not be supported yet on Avantis!")
    
        return pair_index
    
    def _initialize_pair_mappings(self) -> Dict[str, int]:

                """Initialize trading pair mappings for Avantis"""

                return {

                'BTC/USD': 0,

                'BTCUSD': 0,

                'BTC': 0,

                'ETH/USD': 1,

                'ETHUSD': 1,

                'ETH': 1,

                'SOL/USD': 2,

                'SOLUSD': 2,

                'SOL': 2,

                'LINK/USD': 3,

                'LINKUSD': 3,

                'LINK': 3,

                'AVAX/USD': 4,

                'AVAXUSD': 4,

                'AVAX': 4,

                # USDT mappings for signal compatibility
                'BTC/USDT': 0,
            
                'ETH/USDT': 1,
            
                'SOL/USDT': 2,    # Map SOL signals to index 2
            
                'LINK/USDT': 3,   # Future LINK trading
            
                'AVAX/USDT': 4,
            
            }

       

    async def execute_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:

        """Execute trade on Avantis protocol with enhanced error handling"""

        try:

            logger.info(f"🎯 EXECUTING AVANTIS TRADE:")

            logger.info(f"🚀 ELITE TRADING BOT v214-MARGIN-FIX - Processing trade request")

            logger.info(f"🎯 MARGIN-FOCUSED VERSION - Fixing leverage calculation issue!")

            # ADD THIS NETWORK CHECK HERE:
            chain_id = self.w3.eth.chain_id  
            logger.info(f"🔗 NETWORK CHECK: Connected to Chain ID: {chain_id}")
            logger.info(f"🔗 EXPECTED: Base mainnet = 8453")
            if chain_id != 8453:
                logger.error(f"❌ WRONG NETWORK! You're on chain {chain_id}, not Base!")
                return {'status': 'error', 'error': f'Wrong network: {chain_id}'}
            else:
                logger.info(f"✅ CORRECT NETWORK: Base mainnet confirmed!")
                 # 🚨 ADD THIS NEW DEBUGGING:
                logger.info(f"🔍 RPC PROVIDER DEBUG:")
                logger.info(f"🔍 Provider type: {type(self.w3.provider)}")
                logger.info(f"🔍 Provider endpoint: {getattr(self.w3.provider, 'endpoint_uri', 'Unknown')}")
                logger.info(f"🔍 Latest block number: {self.w3.eth.block_number}")
                logger.info(f"🔍 Your ETH balance: {self.w3.eth.get_balance(self.wallet_address) / 1e18:.6f} ETH")
            # Enhanced debugging for entry price detection

            logger.info(f"🔍 DEBUGGING entry price detection:")

            logger.info(f"  Full trade_data keys: {list(trade_data.keys())}")

            logger.info(f"  entry_price field: {trade_data.get('entry_price', 'NOT FOUND')}")

            logger.info(f"  entry field: {trade_data.get('entry', 'NOT FOUND')}")

            logger.info(f"  price field: {trade_data.get('price', 'NOT FOUND')}")

           

            # Extract entry price with multiple field name attempts

            entry_price_dollars = None

            entry_price_source = None

           

            # Try different field names for entry price

            price_fields = ['entry_price', 'entry', 'price', 'open_price', 'entryPrice', 'openPrice']

           

            for field in price_fields:

                if field in trade_data and trade_data[field] and trade_data[field] != 0:

                    entry_price_dollars = float(trade_data[field])

                    entry_price_source = field

                    logger.info(f"💰 Found valid entry price in field '{field}': ${entry_price_dollars}")

                    break

           

            if entry_price_dollars is None or entry_price_dollars == 0:

                logger.error(f"❌ No valid entry price found in any field!")

                logger.error(f"   Available fields: {list(trade_data.keys())}")

                return {

                    'status': 'error',

                    'error': 'No valid entry price found',

                    'available_fields': list(trade_data.keys())

                }

           

            # Extract basic trade parameters

            symbol = trade_data.get('symbol', 'BTC/USD')

            direction = trade_data.get('direction', 'LONG').upper()

            leverage = int(trade_data.get('leverage', TradingConfig.DEFAULT_LEVERAGE))

            # Calculate position size in USDC (with 6 decimals) - FOCUS ON MARGIN

            # 🚀 DYNAMIC POSITION SIZING - ELITE STRATEGY!
            # Get current USDC balance for dynamic position sizing
            trader_address = self.web3_manager.account.address if self.web3_manager.account else None
        
            if trader_address:
                try:
                    logger.info(f"🔍 DEBUG: Checking balance for address: {trader_address}")
                    logger.info(f"🔍 DEBUG: USDC contract address: {self.usdc_contract.address}")                    
                    current_balance = self.web3_manager.get_usdc_balance(trader_address)
                    logger.info(f"✅ REAL Balance from blockchain: ${current_balance:.2f} USDC")

                    # Double-check with direct contract call
                    raw_balance = self.usdc_contract.functions.balanceOf(trader_address).call()
                    direct_balance = raw_balance / 1e6
                    logger.info(f"🔍 DIRECT balance check: ${direct_balance:.2f} USDC (raw: {raw_balance})")
                
                    # Use the higher of the two readings
                    current_balance = max(current_balance, direct_balance)
                    logger.info(f"🔍 FINAL balance used: ${current_balance:.2f} USDC")                
                except Exception as e:
                    logger.error(f"❌ Failed to read balance: {e}")
                    current_balance = 250  # Realistic fallback
                    logger.warning(f"⚠️ Using fallback balance: ${current_balance:.2f}")
            else:
                logger.error("❌ No trader address found!")
                current_balance = 250  # Realistic fallback instead of 1000
            
            # Calculate position size based on account balance and tier
            tier = int(trade_data.get('tier', 2))  # Default to tier 2 if not specified

            if tier in TradingConfig.TIER_POSITION_PERCENTAGES:
                # Calculate percentage-based position size
                percentage = TradingConfig.TIER_POSITION_PERCENTAGES[tier]
                calculated_position = current_balance * percentage
    
                # Ensure minimum position size is met
                min_position = TradingConfig.MIN_TIER_POSITIONS[tier]
                position_usdc_dollars = max(calculated_position, min_position)
    
                logger.info(f"💰 DYNAMIC POSITION SIZING - ELITE STRATEGY:")
                logger.info(f"  - Current Balance: ${current_balance:.2f} USDC")
                logger.info(f"  - Tier {tier}: {percentage*100:.0f}% of account")
                logger.info(f"  - Calculated: ${calculated_position:.2f}")
                logger.info(f"  - Minimum: ${min_position}")
                logger.info(f"  - Final Position: ${position_usdc_dollars:.2f} USDC")
    
                # Show scaling preview
                if current_balance >= 1000:
                    logger.info(f"🚀 SCALING SUCCESS: Account grew from $250 → ${current_balance:.0f}!")
                else:
                    future_1k = 1000 * percentage
                    logger.info(f"📈 FUTURE: At $1K balance, Tier {tier} = ${future_1k:.0f} position")
        
            else:
                # Fallback to signal's position_size if tier not recognized
                position_usdc_dollars = float(trade_data.get('position_size', 100))
                logger.warning(f"⚠️ Unknown tier {tier}, using signal position: ${position_usdc_dollars}")

            if position_usdc_dollars > current_balance * 0.9:  # Don't use more than 90% of balance
                logger.warning(f"⚠️ Position ${position_usdc_dollars:.2f} too large for balance ${current_balance:.2f}")
                position_usdc_dollars = current_balance * 0.8  # Use 80% of balance instead
                logger.info(f"⚠️ Reduced position to: ${position_usdc_dollars:.2f}")
                position_usdc = int(position_usdc_dollars * 1e6)

            # 💡 CONSERVATIVE SLIPPAGE ADJUSTMENT - Increased buffer to prevent failures
            slippage_adjustment = 1.10  # 10% buffer to ensure margin stays above $25
            # 🔍 BALANCE-AWARE ADJUSTMENT: Ensure we don't exceed available funds
            max_affordable = current_balance * 0.95  # Use 95% of balance for safety
            if position_usdc_dollars > max_affordable:
                logger.warning(f"💰 BALANCE LIMIT: Reducing position from ${position_usdc_dollars:.2f} to ${max_affordable:.2f}")
                position_usdc_dollars = max_affordable
                logger.info(f"✅ ADJUSTED: Position now fits within available balance")
                original_position = position_usdc_dollars
            position_usdc_dollars = position_usdc_dollars * slippage_adjustment

            # Store original position before any adjustments
            original_position = position_usdc_dollars            
            logger.info(f"💡 ENHANCED SLIPPAGE PROTECTION:")
            logger.info(f"   - Original position: ${original_position:.2f}")
            logger.info(f"   - With 15% buffer: ${position_usdc_dollars:.2f}")
            logger.info(f"   - Buffer amount: ${position_usdc_dollars - original_position:.2f}")
            logger.info(f"   - Final margin: ${position_usdc_dollars/leverage:.2f}")
            
            # Double-check margin will be sufficient
            final_margin_after_slippage = (position_usdc_dollars * (1 - TradingConfig.DEFAULT_SLIPPAGE)) / leverage
            if final_margin_after_slippage >= 25:
                logger.info(f"✅ MARGIN CHECK PASSED: ${final_margin_after_slippage:.2f} >= $25")
            else:
                logger.error(f"🚨 MARGIN CHECK FAILED: ${final_margin_after_slippage:.2f} < $25")
                position_usdc_dollars = position_usdc_dollars * slippage_adjustment  # $200 → $210
            logger.info(f"💡 SLIPPAGE ADJUSTED: Position increased to ${position_usdc_dollars:.2f} to account for {TradingConfig.DEFAULT_SLIPPAGE*100}% slippage")
            
            required_margin = position_usdc_dollars / leverage

            collateral_usdc_dollars = required_margin  # This is what Avantis contract needs
            collateral_usdc = int(collateral_usdc_dollars * 1_000_000)  # Convert to 6 decimals
            logger.info(f"💰 COLLATERAL (what contract gets): ${collateral_usdc_dollars:.2f} USDC")
            # Ensure minimum MARGIN for Avantis (likely $20+ required margin)

            min_margin_required = TradingConfig.MIN_MARGIN_REQUIRED  # $25

            if required_margin < min_margin_required:

                # Increase position size to meet margin requirement

                new_position_size = min_margin_required * leverage

                logger.warning(f"⚠️ Margin ${required_margin:.2f} below minimum ${min_margin_required}")

                logger.warning(f"⚠️ Increasing position from ${position_usdc_dollars} to ${new_position_size}")

                position_usdc_dollars = new_position_size

                required_margin = position_usdc_dollars / leverage

               

            collateral_usdc = int((position_usdc_dollars / leverage) * 1_000_000)  # $26 * 1M = 26,000,000

           

            logger.info(f"💰 MARGIN CALCULATION:")

            logger.info(f"  - Position Size: ${position_usdc_dollars:.2f} USDC")

            logger.info(f"  - Leverage: {leverage}x")

            logger.info(f"  - Required Margin: ${required_margin:.2f} USDC")

            logger.info(f"  - Collateral (6 decimals): {collateral_usdc}")

            logger.info(f"  - Minimum Margin Required: ${min_margin_required}")

            # 🔍 DEBUGGING: Get live price and compare
            webhook_price = entry_price_dollars
            logger.info(f"📊 PRICE COMPARISON DEBUG:")
            logger.info(f"   - Webhook price: ${webhook_price:.2f}")
            
            # Get live price from API
            live_price = get_live_price(symbol)
            
            if live_price:
                price_diff = abs(live_price - webhook_price) / webhook_price * 100
                logger.info(f"   - Live API price: ${live_price:.2f}")
                logger.info(f"   - Price difference: {price_diff:.2f}%")
                
                # Use live price if webhook price seems stale (>2% difference)
                if price_diff > 2.0:
                    logger.warning(f"⚠️ Webhook price stale! Using live price instead")
                    entry_price_dollars = live_price
                    entry_price_source = "Live API (CoinGecko)"
                else:
                    logger.info(f"✅ Webhook price fresh, using original")
            else:
                logger.warning(f"⚠️ Could not get live price, using webhook price")
            
            # 🧪 HARDCODED PRICE TEST MODE (uncomment to test specific price)
            # entry_price_dollars = 99224.91  # <-- Uncomment this line to test hardcoded price
            # logger.info(f"🧪 HARDCODED TEST MODE: Using price ${entry_price_dollars}")
            
            # Convert entry price to format Avantis expects (8 decimals)
            entry_price = int(Decimal(str(entry_price_dollars)) * (10**8))
            
            logger.info(f"💰 FINAL Entry price: ${entry_price_dollars:.2f} (raw: {entry_price})")
            logger.info(f"💰 Entry price source: {entry_price_source}")

            # 🔍 ADD THIS DEBUG CODE HERE (after line 1139):
            logger.info(f"🔍 ENTRY PRICE DEBUG:")
            logger.info(f"   - Original webhook price: {trade_data.get('entry_price')}")  
            logger.info(f"   - entry_price_dollars: ${entry_price_dollars:.2f}")
            logger.info(f"   - Final entry_price (8 decimals): {entry_price}")
            logger.info(f"   - Verification: ${entry_price/1e8:.2f}")            
            logger.info(f"🔍 DEBUG: Available pair_mappings = {self.pair_mappings}")

            pair_index = self.get_pair_index(symbol)

            logger.info(f"🔍 DEBUG: pair_index = {pair_index}, symbol = {symbol}")
            if pair_index is None or pair_index == -1:
                logger.error(f"❌ INVALID PAIR! Symbol {symbol} not found in mappings")
                return None
                
            logger.info(f"🎯 Trading pair: {symbol} -> Index {pair_index}")

           

            # Determine trade direction

            is_long = direction == 'LONG'

            logger.info(f"📈 Direction: {direction} (is_long: {is_long})")

           

            # Get trader address

            if not self.web3_manager.account:

                return {

                    'status': 'error',

                    'error': 'No trading account configured'

                }

               

            trader_address = self.web3_manager.account.address

           

            # Check USDC balance

            usdc_balance = self.web3_manager.get_usdc_balance(trader_address)

            logger.info(f"💰 USDC Balance: ${usdc_balance:.6f}")

           

            if usdc_balance < position_usdc_dollars:

                logger.warning(f"⚠️ Balance check: ${usdc_balance:.6f} vs ${position_usdc_dollars} needed")

                logger.warning(f"⚠️ You have $200 USDC but need ${position_usdc_dollars} - check if funds are available")

                # Continue anyway for now

            else:

                logger.info(f"✅ Sufficient balance: ${usdc_balance:.6f} >= ${position_usdc_dollars}")

           

            # Execute the trade
            position_usdc_full = int(position_usdc_dollars * 1_000_000)  # Convert $200 to 200,000,000
            
            result = await self._execute_avantis_trade(

                trader_address=trader_address,

                pair_index=pair_index,

                position_usdc=position_usdc_full,

                entry_price=entry_price,

                leverage=leverage,

                is_long=is_long,

                entry_price_dollars=entry_price_dollars,

                entry_price_source=entry_price_source,

                position_usdc_dollars=position_usdc_dollars,

                trade_data=trade_data
            )

           

            return result

           

        except Exception as e:

            logger.error(f"❌ Trade execution failed: {str(e)}")

            logger.error(f"Traceback: {traceback.format_exc()}")

            return {

                'status': 'error',

                'error': f'Trade execution failed: {str(e)}',

                'traceback': traceback.format_exc()

            }

    async def _execute_avantis_trade(

        self,

        trader_address: str,

        pair_index: int,

        position_usdc: int,

        entry_price: int,

        leverage: int,

        is_long: bool,

        entry_price_dollars: float,

        entry_price_source: str,

        position_usdc_dollars: float,

        trade_data: Dict[str, Any]        

    ) -> Dict[str, Any]:

        """Execute the actual trade on Avantis protocol"""

       

        try:

            current_nonce = self.w3.eth.get_transaction_count(trader_address, 'pending')
         
            logger.info(f"🎯 Preparing trade parameters...")

            # 🔍 ENHANCED DEBUGGING: Log all transaction parameters in detail
            logger.info(f"🔍 RAW TRANSACTION PAYLOAD DEBUG:")
            logger.info(f"   - trader_address: {trader_address}")
            logger.info(f"   - pair_index: {pair_index} (0=BTC, 1=ETH, 2=SOL)")
            logger.info(f"   - position_usdc: {position_usdc} (${position_usdc/1e6:.2f} USDC)")
            logger.info(f"   - entry_price: {entry_price} (${entry_price/1e8:.2f})")
            logger.info(f"   - leverage: {leverage}x")
            logger.info(f"   - is_long: {is_long} ({'LONG' if is_long else 'SHORT'})")
            logger.info(f"   - margin_required: ${(position_usdc/1e6)/leverage:.2f}")
            
            # Calculate what Avantis contract will see
            effective_position_after_slippage = position_usdc_dollars * (1 - TradingConfig.DEFAULT_SLIPPAGE)
            effective_margin_after_slippage = effective_position_after_slippage / leverage
            
            logger.info(f"🔍 AVANTIS CONTRACT ANALYSIS:")
            logger.info(f"   - Position before slippage: ${position_usdc_dollars:.2f}")
            logger.info(f"   - Position after {TradingConfig.DEFAULT_SLIPPAGE*100}% slippage: ${effective_position_after_slippage:.2f}")
            logger.info(f"   - Margin after slippage: ${effective_margin_after_slippage:.2f}")
            logger.info(f"   - Minimum margin needed: $25.00")
            logger.info(f"   - Margin buffer: ${effective_margin_after_slippage - 25:.2f}")
            
            if effective_margin_after_slippage < 25:
                logger.error(f"🚨 PROBLEM DETECTED: Margin {effective_margin_after_slippage:.2f} < $25 minimum!")
                logger.error(f"🚨 This will likely cause transaction revert!")
                logger.error(f"💡 Solution: Increase position to ${25 * leverage * 1.1:.0f} or reduce leverage")            

            # FIXED: Use decimal slippage for SDK (addresses slippage/fee issue)

            order_type = 0  # MARKET

            slippage_pct = TradingConfig.DEFAULT_SLIPPAGE
            slippage = int(slippage_pct * 10**10)

            # Force all trade_params to be integers (addresses decimal precision issue)

            trade_input = TradeInput(
                
                trader_address=trader_address,
                
                pair_index=pair_index,
                
                margin = int(position_usdc_dollars / leverage * 1e6),
                
                open_collateral=Decimal(trade_data.get("open_collateral", 0)),
                
                collateral_in_trade=Decimal(trade_data.get("collateral_in_trade", 0)),
                
                leverage=leverage,
                
                buy=is_long,
                
                slippage=slippage,
                
                order_type=order_type,
                
                timestamp=int(time.time())
                
            )

            logger.info(f"  - slippage_pct: {slippage_pct} (type: {type(slippage_pct).__name__}) - Reduced to 3%")

            logger.info(f"  - entry_price value: {entry_price} (${entry_price/100_000_000:.2f})")

            logger.info(f"  - position_usdc value: {position_usdc} (${position_usdc/1_000_000:.2f})")

            logger.info(f"  - required_margin: ${(position_usdc/1_000_000)/leverage:.2f} USDC")

           

            # CRITICAL: Verify entry price and margin are valid

            if entry_price == 0:

                logger.error(f"🚨 STOPPING: Entry price is ZERO! Cannot execute trade.")

                return {

                    'status': 'error',

                    'error': 'Entry price is zero - trade aborted',

                    'entry_price_source': entry_price_source,

                    'original_value': entry_price_dollars

                }

               

            # Calculate effective position after slippage/fees

            effective_position = position_usdc_dollars * (1 - slippage_pct)

            effective_margin = effective_position / leverage

           

            logger.info(f"💰 SLIPPAGE IMPACT ANALYSIS:")

            logger.info(f"  - Original position: ${position_usdc_dollars:.2f}")

            logger.info(f"  - After {slippage_pct*100}% slippage: ${effective_position:.2f}")

            logger.info(f"  - Effective margin: ${effective_margin:.2f}")

           

            if effective_margin < 20:

                logger.warning(f"⚠️ Effective margin ${effective_margin:.2f} might be below Avantis minimum!")

                logger.warning(f"⚠️ Consider increasing position size or reducing leverage")


                logger.info(f"🎯 Attempting Avantis trade execution...")

                logger.info(f"  - Entry price: ${entry_price/1_000_000_000_000_000_000:.2f}")

                logger.info(f"  - Position size: ${position_usdc/1_000_000:.2f} USDC")

                logger.info(f"  - Leverage: {leverage}x")

                logger.info(f"  - Direction: {'LONG' if is_long else 'SHORT'}")

                logger.info(f"  - Market order type: {order_type} ({type(order_type).__name__})")

                logger.info(f"  - Slippage: {slippage_pct} ({type(slippage_pct).__name__})")

           
            balance_before = self.usdc_contract.functions.balanceOf(trader_address).call() / 1e6
            logger.info(f"🔍 USDC Balance BEFORE trade: ${balance_before:.6f}") 
            # 🔑 APPROVE USDC FIRST (THE MISSING PIECE!)
            logger.info("🔑 Step 1: Approving USDC spending...")
            approve_amount = position_usdc  # Amount to approve
            approve_txn = self.usdc_contract.functions.approve(AVANTIS_TRADING_CONTRACT, approve_amount).build_transaction({
                'from': trader_address,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(trader_address),
            })
            signed_approve = self.w3.eth.account.sign_transaction(approve_txn, TradingConfig.PRIVATE_KEY)
            approve_hash = self.w3.eth.send_raw_transaction(signed_approve.rawTransaction)
            try:
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                logger.info("✅ USDC approval confirmed after waiting!")
            except Exception as e:
                if "TimeExhausted" in str(e):
                    logger.info("⏰ Checking if approval completed anyway...")
                    try:
                        approve_receipt = self.w3.eth.get_transaction_receipt(approve_hash)
                        if approve_receipt and approve_receipt.status == 1:
                            logger.info("🎉 SUCCESS! USDC approval completed despite timeout!")
                        else:
                            logger.info("❌ USDC approval still pending - network very slow today")
                            raise e
                    except:
                        logger.info("❌ USDC approval failed - will retry on next signal")
                        raise e
                else:
                    raise e            
            logger.info(f"✅ USDC approved! Hash: {approve_hash.hex()}")

            logger.info(f"🔄 Step 2: Building transaction with direct contract call")

            # Build trade struct in correct order for openTrade ABI
            trade_input = (
                trader_address,           # trader (address)
                pair_index,               # pairIndex (uint256) - 1 for your pair
                0,                        # index (uint256)
                0,                        # initialPosToken (uint256)
                position_usdc,            # positionSizeUSDC (uint256)
                0,                        # openPrice (uint256) - 0 for market price
                is_long,                  # buy (bool)
                leverage,                 # leverage (uint256)
                0,                        # tp (uint256) - take profit
                0,                        # sl (uint256) - stop loss
                int(time.time())         # timestamp (uint256)
            )

            # Build transaction
            nonce = self.w3.eth.get_transaction_count(trader_address)
            gas_price = self.w3.eth.gas_price

            transaction_data = self.avantis_contract.functions.openTrade(
                trade_input,              # TradeInput struct
                0,                        # order type (uint8) - 0 for market
                int(slippage_pct * 1e10)  # Example: 0.01 * 1e10 = 1000000000 (1% slippage)
            ).build_transaction({
                'from': trader_address,
                'gas': TradingConfig.GAS_LIMIT,
                'gasPrice': gas_price,
                'nonce': nonce,
                'value': 0
            })
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(
                transaction_data, TradingConfig.PRIVATE_KEY
            )

            # 🚀 Send transaction and wait for confirmation            
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash_str = tx_hash.hex()

            logger.info(f"📨 Sent trade tx: {tx_hash_str}")
            logger.info(f"⏳ Waiting for confirmation...")

            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                logger.info("✅ Trade confirmed after waiting!")
            except Exception as e:
                if "TimeExhausted" in str(e):
                    logger.info("⏰ Checking if trade completed anyway...")
                    try:
                        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                        if receipt and receipt.status == 1:
                            logger.info("🎉 SUCCESS! Trade completed despite timeout!")
                        else:
                            logger.info("❌ Trade still pending - network very slow today")
                            raise e
                    except:
                        logger.info("❌ Trade failed - will retry on next signal")
                        raise e
                else:
                    raise e
            if receipt.status == 1:
                logger.info(f"✅ Trade executed successfully! Gas used: {receipt.gasUsed}")
                logger.info(f"🔗 BaseScan: https://basescan.org/tx/{tx_hash_str}")
                # CHECK USDC BALANCE AFTER
                balance_after = self.usdc_contract.functions.balanceOf(trader_address).call() / 1e6
                logger.info(f"🔍 USDC Balance AFTER trade: ${balance_after:.6f}")
                logger.info(f"🔍 USDC MOVED: ${balance_before - balance_after:.6f}")                
                return {
                    "status": "success",
                    "tx_hash": tx_hash_str,
                    "gas_used": receipt.gasUsed,
                    "block_number": receipt.blockNumber
                }
            else:
                logger.info(f"📋 Receipt: {receipt}")
                raise Exception(f"Transaction reverted: {tx_hash_str}")        

        except Exception as e:
            error_msg = str(e)
            logger.error(f"🚨 TRANSACTION FAILED - REAL ERROR: {error_msg}")
            logger.error(f"🚨 ERROR TYPE: {type(e).__name__}")
            logger.error(f"🚨 FULL ERROR DETAILS: {repr(e)}")
            logger.error("❌ TRADE FAILED - NOT GENERATING FAKE SUCCESS MESSAGES")

            try:
                logger.error(f"🔍 ANALYZING REVERT: Transaction hash 0x{receipt.transactionHash.hex()}")
                logger.error(f"🔍 BASESCAN LINK: https://basescan.org/tx/{receipt.transactionHash.hex()}")

                logger.error(f"🔍 GAS USED: {receipt.gasUsed} / Block: {receipt.blockNumber}")
                logger.error(f"🔍 CONTRACT ADDRESS: {receipt.to}")
                
                logger.error(f"🔍 SENT PARAMETERS:")
                logger.error(f"   - Trader: {trader_address}")
                logger.error(f"   - Pair Index: {pair_index}")
                logger.error(f"   - Position: {position_usdc} ({position_usdc/1e6:.2f} USDC)")
                logger.error(f"   - Entry Price: {entry_price} ({entry_price/1e8:.2f})")
                logger.error(f"   - Leverage: {leverage}")
                logger.error(f"   - Is Long: {is_long}")
                
            except Exception as debug_error:
                logger.error(f"🔍 DEBUG ERROR: {debug_error}")            
            return {
                "status": "error",
                "message": f"Transaction failed: {error_msg}",
                "error_type": type(e).__name__
            }
  

        except Exception as e:

            logger.error(f"❌ Avantis trade execution failed: {str(e)}")

           

            # Enhanced error analysis for BELOW_MIN_POS

            if "BELOW_MIN_POS" in str(e):

                actual_margin = position_usdc/1_000_000/leverage

                logger.error(f"💡 BELOW_MIN_POS Analysis:")

                logger.error(f"   - Position Size: ${position_usdc/1_000_000:.2f} USDC")

                logger.error(f"   - Leverage: {leverage}x")

                logger.error(f"   - Required Margin: ${actual_margin:.2f} USDC")

                logger.error(f"   - After 3% slippage: ${actual_margin * 0.97:.2f} USDC")

                logger.error(f"💡 Try: Increase position size or reduce leverage!")

                logger.error(f"💡 Suggestion: Use $150+ position with 5x leverage = $30+ margin")

               

            return {

                'status': 'error',

                'error': str(e),

                'analysis': f'Margin: ${(position_usdc/1_000_000)/leverage:.2f} USDC',

                'suggestion': 'Increase position size or reduce leverage for higher margin'

            }

 

# Initialize Avantis trader

avantis_trader = AvantisTrader()

 

# ============================================================================

# 🔄 SIGNAL PROCESSING ENGINE

# ============================================================================

 

class SignalProcessor:

    """Advanced signal processing and validation engine"""

   

    def __init__(self):

        self.sheets_manager = sheets_manager

        self.trader = avantis_trader

       

    async def process_signal(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:

        """Process incoming trading signal from any source"""

        try:

            logger.info("🔄 Processing incoming signal...")

           

            # Determine signal source and process accordingly

            source = trade_data.get('source', 'unknown').lower()

           

            if 'sheets' in source or 'google' in source:
                processed_signal = self.sheets_manager.process_sheets_signal(trade_data)
            else:
                processed_signal = self._process_generic_signal(trade_data)

            # ✅ Protect against None or invalid signal
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

            if not processed_signal:
                    logger.error("🚨 processed_signal is None — aborting trade")
                    return None
                   
            # Execute the trade

            trade_result = await self.trader.execute_trade(processed_signal)

           

            return {

                'status': 'success' if trade_result.get('status') == 'success' else 'failed',

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

        if not trade_data:
            logging.error("❌ No signal data received.")
            return None  # ✅ Return None so upper logic can handle it cleanly


        """Process generic signal format"""

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

        """Validate processed signal before execution"""

       

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

        if signal['position_size'] < 50:  # Minimum $50 (matches tier 3 minimum)

            return {

                'valid': False,

                'reason': 'Position size too small (minimum $50)'

            }

           

        # Validate leverage

        leverage = signal.get('leverage', 1)

        if leverage < 1 or leverage > 100:

            return {

                'valid': False,

                'reason': 'Leverage must be between 1 and 100'

            }

           

        return {'valid': True}

 

# Initialize signal processor

signal_processor = SignalProcessor()

 

# ============================================================================

# 🌐 WEBHOOK ENDPOINTS AND API ROUTES

# ============================================================================

 

@app.route('/', methods=['GET'])

def health_check():

    """Health check endpoint"""

    return {

        'status': 'healthy',

        'service': 'Elite Crypto Trading Bot',

        'version': 'v214-MARGIN-FIX',

        'timestamp': datetime.now(timezone.utc).isoformat(),

        'web3_connected': web3_manager.is_connected(),

        'features': {

            'google_sheets': True,

            'avantis_trading': True,

            'margin_calculation': True,

            'enhanced_debugging': True

        }

    }

 

@app.route('/webhook', methods=['POST'])

def webhook():

    """Enhanced webhook endpoint for trading signals with Avantis integration"""

   

    try:

        trade_data = request.get_json()
        if not trade_data:

            logger.error("❌ Empty request body")

            return {'error': 'Empty request body'}, 400

        source = trade_data.get('source', 'unknown').lower()
        
        
        # Version tracking - MARGIN FIX VERSION

        logger.info(f"🚀 ELITE TRADING BOT v214-MARGIN-FIX - Processing webhook request")

        time.sleep(2)  # 🚫 Prevent duplicate trades from rapid webhooks
     
        logger.info(f"🎯 MARGIN-FOCUSED VERSION - Fixing leverage calculation issue!")

        # ADD THESE 6 LINES HERE ⬇️
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

        
       # NEW CODE - Add symbol checking
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
            logger.info(f"✅ {symbol} marked as ACTIVE")

           

        logger.info(f"📨 Received signal data: {json.dumps(trade_data, indent=2)}")

       

        # Process the signal asynchronously

        async def process_webhook():

            return await signal_processor.process_signal(trade_data)

           

        # Run the async processing

        result = asyncio.run(process_webhook())

       

        # Log the result

        if result.get('status') == 'success':

            logger.info(f"✅ Webhook processing successful!")

            logger.info(f"   Trade result: {result.get('trade_result', {})}")

        else:

            logger.warning(f"⚠️ Webhook processing failed: {result.get('error', 'Unknown error')}")

           
        
        return result

       

    except Exception as e:

        logger.error(f"❌ Webhook error: {str(e)}")

        logger.error(f"Traceback: {traceback.format_exc()}")

        return {

            'status': 'error',

            'error': f'Webhook processing failed: {str(e)}'

        }, 500

    finally:  
        # Release symbol lock
            if 'symbol' in locals():
                with ACTIVE_TRADES_LOCK:
                    ACTIVE_TRADES[symbol] = False
                    logger.info(f"🔓 {symbol} marked as INACTIVE")

        
            TRADE_IN_PROGRESS = False  # Always reset, even on error
    
@app.route('/balance', methods=['GET'])

def get_balance():

    """Get current USDC balance"""

    try:

        if not web3_manager.account:

            return {'error': 'No account configured'}, 400

           

        balance = web3_manager.get_usdc_balance(web3_manager.account.address)

       

        return {

            'address': web3_manager.account.address,

            'usdc_balance': balance,

            'timestamp': datetime.now(timezone.utc).isoformat()

        }

       

    except Exception as e:

        logger.error(f"❌ Balance check failed: {str(e)}")

        return {'error': f'Balance check failed: {str(e)}'}, 500

 

@app.route('/test-trade', methods=['POST'])

def test_trade():

    """Test trade endpoint for debugging"""

    try:

        test_signal = {

            'symbol': 'BTC/USD',

            'direction': 'LONG',

            'entry_price': 50000.0,

            'position_size': 130,

            'leverage': 5,

            'tier': 1,

            'source': 'Test'

        }

       

        logger.info(f"🧪 Testing trade with signal: {test_signal}")

       

        async def process_test():

            return await signal_processor.process_signal(test_signal)

           

        result = asyncio.run(process_test())

       

        return result

       

    except Exception as e:

        logger.error(f"❌ Test trade failed: {str(e)}")

        return {

            'status': 'error',

            'error': f'Test trade failed: {str(e)}'

        }, 500

 

@app.route('/config', methods=['GET'])

def get_config():

    """Get current bot configuration"""

    return {

        'position_sizes': TradingConfig.POSITION_SIZES,

        'default_leverage': TradingConfig.DEFAULT_LEVERAGE,

        'default_slippage': TradingConfig.DEFAULT_SLIPPAGE,

        'min_margin_required': TradingConfig.MIN_MARGIN_REQUIRED,

        'gas_limit': TradingConfig.GAS_LIMIT,

        'supported_pairs': list(avantis_trader.pair_mappings.keys()),

        'version': 'v214-MARGIN-FIX'

    }

 

# ============================================================================

# 📄 GOOGLE SHEETS INTEGRATION SCRIPT

# ============================================================================

 

def generate_google_sheets_script():

    """Generate Google Apps Script code for Sheets integration"""

   

    script_code = '''

/**

* 🚀 ELITE CRYPTO TRADING BOT - Google Sheets Integration Script v214

*

 * This script sends trading signals from Google Sheets to your Heroku trading bot

* with enhanced margin calculation and error handling.

*

 * Setup Instructions:

* 1. Replace WEBHOOK_URL with your actual Heroku app URL

* 2. Set up your trading signals in the Google Sheet

* 3. Run sendTradingSignal() function to send signals

*/

 

// 🔗 Configuration - UPDATE THIS URL!

const WEBHOOK_URL = "https://crypto-trading-bot-jesse-f6537b3a1992.herokuapp.com/webhook";

 

/**

* 📊 Main function to send trading signals to the bot

* Call this function to send the current signal from your sheet

*/

function sendTradingSignal() {

  try {

    console.log('🚀 Elite Trading Bot v214-MARGIN-FIX - Sending signal...');

   

    // 📋 Read signal data from the active sheet

    const sheet = SpreadsheetApp.getActiveSheet();

    const signal = readSignalFromSheet(sheet);

   

    if (!signal) {

      console.error('❌ No valid signal found in sheet');

      return;

    }

   

    console.log('📊 Signal data:', JSON.stringify(signal, null, 2));

   

    // 🌐 Send signal to trading bot

    const response = sendWebhookRequest(signal);

   

    // 📝 Log the response

    logResponse(sheet, signal, response);

   

    console.log('✅ Signal sent successfully!');

   

  } catch (error) {

    console.error('❌ Error sending signal:', error);

    Browser.msgBox('Error', 'Failed to send signal: ' + error.toString(), Browser.Buttons.OK);

  }

}

 

/**

* 📋 Read trading signal from the Google Sheet

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

   

    // Calculate position size based on tier (with margin focus)

    signalData.position_size = calculatePositionSize(signalData.tier);

   

    // Add metadata

    signalData.timestamp = new Date().toISOString();

    signalData.source = 'Google Sheets v214';

    signalData.sheet_name = sheet.getName();

   

    // Validate required fields

    if (!signalData.symbol || !signalData.direction || signalData.entry_price <= 0) {

      console.error('❌ Invalid signal data:', signalData);

      return null;

    }

   

    console.log('✅ Signal extracted:', signalData);

    return signalData;

   

  } catch (error) {

    console.error('❌ Error reading signal from sheet:', error);

    return null;

  }

}

 

/**

* 💰 Calculate position size based on tier with margin requirements

* Updated for Avantis margin minimums

*/

function calculatePositionSize(tier) {

  // Position sizing based on signal tier - ADJUSTED FOR MARGIN REQUIREMENTS 

  const positionSizes = {

    1: 130,    // Tier 1: $200 USDC (margin: $200/5 = $40)

    2: 150,    // Tier 2: $200 USDC (margin: $200/5 = $40) 

    3: 250     // Tier 3: $250 USDC (margin: $250/5 = $50)

  };

  return positionSizes[tier] || 200; // Default $200 (margin: $40)

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

* 🌐 Send webhook request to the trading bot

*/

function sendWebhookRequest(signalData) {

  try {

    const options = {

      method: 'POST',

      headers: {

        'Content-Type': 'application/json',

        'User-Agent': 'Google-Apps-Script-Elite-Bot-v214'

      },

      payload: JSON.stringify(signalData)

    };

   

    console.log('🌐 Sending webhook to:', WEBHOOK_URL);

    console.log('📤 Payload:', JSON.stringify(signalData, null, 2));

   

    const response = UrlFetchApp.fetch(WEBHOOK_URL, options);

    const responseText = response.getContentText();

   

    console.log('📥 Response status:', response.getResponseCode());

    console.log('📥 Response body:', responseText);

   

    if (response.getResponseCode() !== 200) {

      throw new Error(`HTTP ${response.getResponseCode()}: ${responseText}`);

    }

   

    return JSON.parse(responseText);

   

  } catch (error) {

    console.error('❌ Webhook request failed:', error);

    throw error;

  }

}

 

/**

* 📝 Log the response from the trading bot

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

      JSON.stringify(response).substr(0, 100) + '...'

    ];

   

    // Write log entry

    sheet.getRange(logStartRow, 1, 1, logEntry.length).setValues([logEntry]);

   

    console.log('📝 Response logged to sheet');

   

  } catch (error) {

    console.error('❌ Error logging response:', error);

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

   

    const headers = ['Timestamp', 'Symbol', 'Direction', 'Entry Price', 'Position Size', 'Status', 'Response'];

    sheet.getRange(logHeaderRow, 1, 1, headers.length).setValues([headers]);

   

    return logHeaderRow + 1;

   

  } catch (error) {

    console.error('❌ Error managing log section:', error);

    return sheet.getLastRow() + 1;

  }

}

 

/**

* 🧪 Test function to verify the integration

*/

function testIntegration() {

  try {

    console.log('🧪 Testing integration with sample signal...');

   

    const testSignal = {

      symbol: 'BTC/USD',

      direction: 'LONG',

      entry_price: 50000,

      tier: 1,

      position_size: 130,

      leverage: 5,

      timestamp: new Date().toISOString(),

      source: 'Google Sheets Test v214'

    };

   

    const response = sendWebhookRequest(testSignal);

   

    console.log('✅ Test completed!');

    console.log('📊 Response:', JSON.stringify(response, null, 2));

   

    Browser.msgBox('Test Result', 'Integration test completed. Check logs for details.', Browser.Buttons.OK);

   

  } catch (error) {

    console.error('❌ Test failed:', error);

    Browser.msgBox('Test Failed', 'Integration test failed: ' + error.toString(), Browser.Buttons.OK);

  }

}

 

/**

* 📋 Create a sample trading sheet layout

*/

function createSampleSheet() {

  try {

    const sheet = SpreadsheetApp.getActiveSheet();

   

    // Clear existing content

    sheet.clear();

   

    // Create headers and sample data

    const data = [

      ['Parameter', 'Value', 'Description'],

      ['Symbol', 'BTC/USD', 'Trading pair (BTC/USD, ETH/USD, etc.)'],

      ['Direction', 'LONG', 'LONG or SHORT'],

      ['Entry Price', 50000, 'Entry price in USD'],

      ['Tier', 1, 'Signal tier (1, 2, or 3)'],

      ['Leverage', 5, 'Leverage multiplier (1-100)'],

      ['Stop Loss', 48000, 'Stop loss price (optional)'],

      ['Take Profit', 55000, 'Take profit price (optional)'],

      ['Quality', 85, 'Signal quality score (0-100)'],

      ['', '', ''],

      ['Position Size', '=IF(B5=1,100,IF(B5=2,150,250))', 'Auto-calculated based on tier'],

      ['Margin Required', '=B11/B6', 'Required margin (Position Size / Leverage)'],

      ['', '', ''],

      ['Instructions:', '', ''],

      ['1. Update values above', '', ''],

      ['2. Run sendTradingSignal()', '', ''],

      ['3. Check logs below', '', ''],

      ['', '', ''],

      ['--- Execution Log ---', '', '']

    ];

   

    // Write data to sheet

    sheet.getRange(1, 1, data.length, 3).setValues(data);

   

    // Format the sheet

    sheet.getRange('A1:C1').setFontWeight('bold');

    sheet.getRange('A14:A17').setFontWeight('bold');

    sheet.getRange('A19:C19').setFontWeight('bold');

   

    // Auto-resize columns

    sheet.autoResizeColumns(1, 3);

   

    console.log('✅ Sample sheet created successfully!');

    Browser.msgBox('Success', 'Sample trading sheet created! Update the values and run sendTradingSignal()', Browser.Buttons.OK);

   

  } catch (error) {

    console.error('❌ Error creating sample sheet:', error);

    Browser.msgBox('Error', 'Failed to create sample sheet: ' + error.toString(), Browser.Buttons.OK);

  }

}

 

// 🔧 Auto-execution functions (optional)

 

/**

* ⏰ Auto-send signal when sheet is edited (optional)

* Uncomment to enable automatic signal sending on sheet edits

*/

/*

function onEdit(e) {

  try {

    // Only trigger on specific cells (B2:B9)

    const range = e.range;

    if (range.getRow() >= 2 && range.getRow() <= 9 && range.getColumn() === 2) {

      console.log('📝 Sheet edited, auto-sending signal...');

      Utilities.sleep(1000); // Wait 1 second for other edits

      sendTradingSignal();

    }

  } catch (error) {

    console.error('❌ Auto-send error:', error);

  }

}

*/

 

/**

* ⏱️ Scheduled signal sending (optional)

* Use with Google Apps Script triggers for automatic execution

*/

/*

function scheduledSignalSend() {

  try {

    // Add your conditions here (e.g., market hours, signal freshness)

    const now = new Date();

    const hour = now.getHours();

   

    // Only send during market hours (example: 9 AM to 5 PM UTC)

    if (hour >= 9 && hour <= 17) {

      sendTradingSignal();

    }

  } catch (error) {

    console.error('❌ Scheduled send error:', error);

  }

}

*/

 

console.log('🚀 Elite Trading Bot Google Sheets Integration v214 loaded successfully!');

console.log('💡 Available functions: sendTradingSignal(), testIntegration(), createSampleSheet()');

console.log('🎯 Margin-focused version with enhanced position sizing!');

'''

   

    return script_code

 

# ============================================================================

# 🚀 APPLICATION STARTUP AND MAIN EXECUTION

# ============================================================================

 

def initialize_application():

    """Initialize the trading bot application"""

    try:

        logger.info("🚀 ELITE CRYPTO TRADING BOT v214-MARGIN-FIX STARTING UP...")


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

        logger.info("✅ Signal processor initialized")

        logger.info("✅ Avantis trader initialized")

        logger.info("✅ Google Sheets manager initialized")

       

        # Log configuration

        logger.info(f"🔧 Configuration:")

        logger.info(f"  - Position sizes: {TradingConfig.POSITION_SIZES}")

        logger.info(f"  - Default leverage: {TradingConfig.DEFAULT_LEVERAGE}x")

        logger.info(f"  - Default slippage: {TradingConfig.DEFAULT_SLIPPAGE*100}%")

        logger.info(f"  - Minimum margin: ${TradingConfig.MIN_MARGIN_REQUIRED}")

        logger.info(f"  - Supported pairs: {len(avantis_trader.pair_mappings)}")

       

        logger.info("🎯 MARGIN-FOCUSED VERSION - Ready to execute trades with enhanced margin calculation!")

        logger.info("✅ Elite Trading Bot initialization complete!")

       

        return True

       

    except Exception as e:

        logger.error(f"❌ Application initialization failed: {str(e)}")

        return False

 

# Error handlers

@app.errorhandler(404)

def not_found(error):

    return {'error': 'Endpoint not found'}, 404

 

@app.errorhandler(500)

def internal_error(error):

    logger.error(f"❌ Internal server error: {str(error)}")

    return {'error': 'Internal server error'}, 500

 

# ============================================================================

# 🎯 MAIN EXECUTION

# ============================================================================

 

if __name__ == '__main__':

    # Initialize the application

    if not initialize_application():

        logger.error("❌ Failed to initialize application")

        sys.exit(1)

   

    # Get port from environment (Heroku compatibility)

    port = int(os.environ.get('PORT', 5000))

   

    logger.info(f"🌐 Starting Flask server on port {port}...")

   

    # Start the Flask application

    app.run(

        host='0.0.0.0',

        port=port,

        debug=False,  # Set to False for production

        threaded=True

    )
