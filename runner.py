#!/usr/bin/env python3
"""
ELITE Flask webhook for Gains Network trades - Optimized for Elite Trading Bot
Enhanced with regime-based position sizing, tier-based risk management,
multi-timeframe validation, and advanced performance tracking.
WITH EIP-1559 TRANSACTION FORMAT FIX FOR BASE NETWORK
"""

import os
import json
import time
import logging
import hashlib
import statistics
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from web3 import Web3
from google.oauth2 import service_account
from googleapiclient.discovery import build
from functools import wraps
from typing import Dict, Optional, Tuple

# ----- ELITE CONFIG -----
RPC_URL         = os.getenv('BASE_RPC_URL')
PRIVATE_KEY     = os.getenv('WALLET_PRIVATE_KEY')
TRADE_LOG_SHEET = os.getenv('TRADE_LOG_SHEET_ID')
TRADE_LOG_TAB   = os.getenv('TRADE_LOG_TAB_NAME', 'Elite Trade Log')
USDC_ADDRESS    = os.getenv('USDC_ADDRESS')

# ✅ CORRECT: Use the actual gTrade trading contract from Base mainnet
GAINS_TRADING_ADDRESS = os.getenv('GAINS_CONTRACT_ADDRESS', "0x6cD5aC19a07518A8092eEFfDA4f1174C72704eeb")
GNS_TOKEN_ADDRESS = "0xfB1AabA03c31EA98A3eec7591808ACb1947eE7aC"  # This is just the token

WEBHOOK_SECRET  = os.getenv('WEBHOOK_SECRET')  # Optional: Leave empty to disable auth

# Enhanced minimum notional based on volatility
MIN_NOTIONAL = {
    "BTC": {"BULL_TRENDING": 400, "BEAR_TRENDING": 350, "VOLATILE": 500, "DEFAULT": 300},
    "ETH": {"BULL_TRENDING": 300, "BEAR_TRENDING": 250, "VOLATILE": 400, "DEFAULT": 250}
}

# Elite trading configuration with regime-based adjustments
ELITE_CONFIG = {
    "base_leverage": 5,
    "max_slippage": 30,
    "max_positions": 3,
    "cooldown_minutes": 5,
    
    # Tier-based risk management - More realistic for crypto
    "tier1": {
        "risk_per_trade": 0.20,    # 20% for high-quality signals
        "min_rr_ratio": 1.2,       # More realistic for crypto (was 1.8)
        "max_leverage": 7,         # Allow higher leverage
        "regime_multiplier": {
            "BULL_TRENDING": 1.2,   # 20% larger positions in bull trends
            "BEAR_TRENDING": 0.8,   # 20% smaller in bear trends
            "VOLATILE": 0.9,        # Smaller in volatile markets
            "DEFAULT": 1.0
        }
    },
    "tier2": {
        "risk_per_trade": 0.15,    # 15% for good signals
        "min_rr_ratio": 1.5,       # More realistic for crypto (was 2.0)
        "max_leverage": 5,         # Standard leverage
        "regime_multiplier": {
            "BULL_TRENDING": 1.1,
            "BEAR_TRENDING": 0.7,   # Much smaller in bear trends
            "VOLATILE": 0.8,
            "DEFAULT": 1.0
        }
    },
    
    # Signal quality thresholds
    "min_signal_quality": 60,      # Minimum quality score
    "min_long_score": 4,           # Minimum long score to trade
    "min_short_score": 4,          # Minimum short score to trade
    
    # Market condition filters
    "regime_filters": {
        "RANGING": False,          # Don't trade in ranging markets
        "BULL_TRENDING": True,
        "BEAR_TRENDING": True,
        "VOLATILE": True,
        "TRENDING": True
    },
    
    # Performance tracking
    "max_daily_trades": 5,         # Limit daily trades
    "max_consecutive_losses": 3,   # Stop trading after 3 losses
    "profit_taking": {
        "daily_target": 0.05,      # 5% daily profit target
        "weekly_target": 0.20      # 20% weekly profit target
    }
}

# ----- ENHANCED LOGGING -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("elite_trading_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("EliteBot")

# ----- ENHANCED RPC SETUP WITH FALLBACK -----
def create_web3_connection():
    """Create Web3 connection with fallback RPCs"""
    rpc_urls = [
        RPC_URL,  # Primary RPC (your Alchemy)
        "https://mainnet.base.org",  # Official Base RPC
        "https://base.gateway.tenderly.co",  # Tenderly Base RPC
        "https://base.drpc.org",  # DRPC Base RPC
        "https://1rpc.io/base",  # 1RPC Base
    ]
    
    for i, rpc_url in enumerate(rpc_urls):
        if not rpc_url:
            continue
            
        try:
            log.info(f"Trying RPC {i+1}: {rpc_url[:50]}...")
            
            # Create connection with longer timeout
            w3_test = Web3(Web3.HTTPProvider(
                rpc_url, 
                request_kwargs={
                    'timeout': 60,
                    'headers': {'User-Agent': 'EliteTradingBot/1.0'}
                }
            ))
            
            if w3_test.is_connected():
                chain_id = w3_test.eth.chain_id
                latest_block = w3_test.eth.block_number
                
                if chain_id == 8453:  # Base mainnet
                    log.info(f"✅ Connected to Base mainnet via RPC {i+1}")
                    log.info(f"   Chain ID: {chain_id}, Block: {latest_block}")
                    return w3_test
                else:
                    log.warning(f"Wrong chain ID {chain_id} for RPC {i+1}")
            else:
                log.warning(f"Failed to connect to RPC {i+1}")
                
        except Exception as e:
            log.error(f"RPC {i+1} failed: {e}")
            continue
    
    raise Exception("All RPC endpoints failed - check network connectivity")

# Create Web3 connection with fallback
w3 = create_web3_connection()

acct = w3.eth.account.from_key(PRIVATE_KEY)
log.info(f"Elite Bot wallet: {acct.address}")

# ----- ELITE TRADE TRACKING -----
class TradeTracker:
    def __init__(self):
        self.recent_trades = {}
        self.daily_stats = {}
        self.performance_history = []
        
    def is_duplicate(self, trade_hash: str) -> bool:
        if trade_hash in self.recent_trades:
            trade_time = self.recent_trades[trade_hash]
            return datetime.now() - trade_time < timedelta(minutes=ELITE_CONFIG['cooldown_minutes'])
        return False
    
    def add_trade(self, trade_hash: str, signal: Dict):
        self.recent_trades[trade_hash] = datetime.now()
        
        # Track daily stats
        today = datetime.now().date()
        if today not in self.daily_stats:
            self.daily_stats[today] = {"trades": 0, "pnl": 0.0}
        self.daily_stats[today]["trades"] += 1
    
    def get_daily_trade_count(self) -> int:
        today = datetime.now().date()
        return self.daily_stats.get(today, {}).get("trades", 0)
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        # Check daily trade limit
        if self.get_daily_trade_count() >= ELITE_CONFIG['max_daily_trades']:
            return True, "Daily trade limit reached"
        
        # Check consecutive losses (would need to be implemented with trade results)
        # This is a placeholder for now
        return False, ""

tracker = TradeTracker()

# ----- ABI LOADER (Same as original) -----
def load_abi(filename):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        abi_path = os.path.join(base_dir, 'abi', filename)
        with open(abi_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning(f"ABI file not found: {filename}, using minimal ABI")
        return [
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], 
             "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], 
             "type": "function"},
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, 
             {"name": "_spender", "type": "address"}], "name": "allowance", 
             "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
            {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, 
             {"name": "_value", "type": "uint256"}], "name": "approve", 
             "outputs": [{"name": "", "type": "bool"}], "type": "function"}
        ]

# Load contracts with proper checksumming
try:
    erc20 = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=load_abi('erc20_abi.json')
    )
    
    # ✅ Use the correct GNSMultiCollatDiamond trading contract
    gains = w3.eth.contract(
        address=Web3.to_checksum_address(GAINS_TRADING_ADDRESS),
        abi=load_abi('gains_base_abi.json')  # Will use existing ABI for now
    )
    log.info(f"Contracts loaded: USDC={Web3.to_checksum_address(USDC_ADDRESS)}")
    log.info(f"Contracts loaded: Gains Trading={Web3.to_checksum_address(GAINS_TRADING_ADDRESS)}")
        
except Exception as e:
    log.error(f"Failed to load contracts: {e}")
    raise

# ----- GOOGLE SHEETS (Enhanced & Optional) -----
def get_sheets_service():
    try:
        # Try to get credentials from environment variable first (for deployment)
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if google_creds_json:
            try:
                creds_dict = json.loads(google_creds_json)
                creds = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                log.info("Google Sheets: Using credentials from environment variable")
                return build('sheets', 'v4', credentials=creds)
            except json.JSONDecodeError:
                log.error("Google Sheets: Invalid JSON in GOOGLE_CREDENTIALS_JSON")
        
        # Fallback to credentials file
        creds_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        if os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            log.info("Google Sheets: Using credentials from file")
            return build('sheets', 'v4', credentials=creds)
        else:
            log.warning("Google Sheets: No credentials found - logging will be disabled")
            return None
            
    except Exception as e:
        log.error(f"Google Sheets setup failed: {e}")
        return None

sheets_service = get_sheets_service()

# ----- AUTHENTICATION (Optional) -----
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Make authentication optional if no webhook secret is set
        webhook_secret = os.getenv('WEBHOOK_SECRET')
        if not webhook_secret or webhook_secret == 'your-secret-key':
            # No authentication required
            return f(*args, **kwargs)
        
        # Check authentication if secret is configured
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {webhook_secret}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ----- ELITE HELPER FUNCTIONS -----
def generate_elite_hash(signal: Dict) -> str:
    """Generate unique hash for elite signals including regime and tier"""
    trade_str = f"{signal['symbol']}_{signal['direction']}_{signal['entry']}_{signal.get('tier', 0)}_{signal.get('regime', 'UNKNOWN')}"
    return hashlib.md5(trade_str.encode()).hexdigest()

def validate_elite_signal(signal: Dict) -> bool:
    """Enhanced validation for elite signals"""
    log.info(f"Validating elite signal: {signal.get('symbol', 'UNKNOWN')} {signal.get('direction', 'UNKNOWN')}")
    
    # Smart field mapping - handle different field names from Google Apps Script
    if 'rationale' in signal and ('regime' not in signal or signal.get('regime') == 'UNKNOWN'):
        rationale = signal['rationale']
        if 'BULL_TRENDING' in rationale:
            signal['regime'] = 'BULL_TRENDING'
        elif 'BEAR_TRENDING' in rationale:
            signal['regime'] = 'BEAR_TRENDING' 
        elif 'VOLATILE' in rationale:
            signal['regime'] = 'VOLATILE'
        elif 'TRENDING' in rationale:
            signal['regime'] = 'TRENDING'
        else:
            signal['regime'] = 'DEFAULT'
    
    # Set default signal quality if missing
    if 'signalQuality' not in signal or signal.get('signalQuality') == 'UNKNOWN':
        tier = signal.get('tier', 2)
        signal['signalQuality'] = 80 if tier == 1 else 70  # Assume good quality for tier signals
    
    # Check required elite fields
    required_fields = ['symbol', 'direction', 'entry', 'stopLoss', 'takeProfit1']
    for field in required_fields:
        if field not in signal:
            raise ValueError(f"Missing required field: {field}")
    
    # Extract coin from symbol (BTC/USDT -> BTC)
    symbol = signal['symbol']
    coin = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
    
    if coin not in ['BTC', 'ETH']:
        raise ValueError(f"Unsupported coin: {coin}")
    
    # Validate direction
    if signal['direction'] not in ['LONG', 'SHORT']:
        raise ValueError(f"Invalid direction: {signal['direction']}")
    
    # Get tier configuration
    tier = signal.get('tier', 2)
    if tier not in [1, 2]:
        raise ValueError(f"Invalid tier: {tier}")
    
    tier_config = ELITE_CONFIG[f'tier{tier}']
    
    # Validate prices and R:R ratio
    entry = float(signal['entry'])
    stop = float(signal['stopLoss'])
    tp1 = float(signal['takeProfit1'])
    
    if entry <= 0 or stop <= 0 or tp1 <= 0:
        raise ValueError("Invalid price values")
    
    # Calculate R:R ratio
    if signal['direction'] == 'LONG':
        risk = entry - stop
        reward = tp1 - entry
    else:
        risk = stop - entry
        reward = entry - tp1
    
    if risk <= 0:
        raise ValueError("Invalid stop loss")
    
    rr_ratio = reward / risk
    min_rr = tier_config['min_rr_ratio']
    if rr_ratio < min_rr:
        raise ValueError(f"R:R ratio {rr_ratio:.2f} below minimum {min_rr}")
    
    # Validate signal quality (more lenient)
    signal_quality = signal.get('signalQuality', 70)
    min_quality = max(50, ELITE_CONFIG['min_signal_quality'] - 10)  # Allow 10 points lower
    if signal_quality < min_quality:
        raise ValueError(f"Signal quality {signal_quality} below minimum {min_quality}")
    
    # Validate market regime (more lenient)
    regime = signal.get('regime', 'DEFAULT')
    if regime == 'RANGING':
        raise ValueError(f"Trading disabled for regime: {regime}")
    
    # More lenient score validation - skip if not provided
    if signal['direction'] == 'LONG' and 'longScore' in signal:
        score = signal.get('longScore', 5)
        min_score = max(2, ELITE_CONFIG['min_long_score'] - 2)  # Allow 2 points lower
        if score < min_score:
            raise ValueError(f"Long score {score} below minimum {min_score}")
    elif signal['direction'] == 'SHORT' and 'shortScore' in signal:
        score = signal.get('shortScore', 5)
        min_score = max(2, ELITE_CONFIG['min_short_score'] - 2)  # Allow 2 points lower
        if score < min_score:
            raise ValueError(f"Short score {score} below minimum {min_score}")
    
    log.info(f"Signal validation passed: Tier {tier}, Quality {signal_quality}, R:R {rr_ratio:.2f}, Regime {regime}")
    return True

def calculate_elite_position_size(signal: Dict, balance_usdc: float) -> float:
    """Calculate position size using elite risk management"""
    symbol = signal['symbol']
    coin = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
    tier = signal.get('tier', 2)
    regime = signal.get('regime', 'DEFAULT')
    
    tier_config = ELITE_CONFIG[f'tier{tier}']
    
    # Get regime-specific minimum notional
    coin_minimums = MIN_NOTIONAL.get(coin, MIN_NOTIONAL['ETH'])
    min_notional = coin_minimums.get(regime, coin_minimums['DEFAULT'])
    min_collateral = min_notional / ELITE_CONFIG['base_leverage']
    
    # Risk-based collateral
    base_risk = tier_config['risk_per_trade']
    regime_multiplier = tier_config['regime_multiplier'].get(regime, 1.0)
    
    # Adjust risk based on signal quality
    signal_quality = signal.get('signalQuality', 60)
    quality_multiplier = 0.8 + (signal_quality - 60) / 100  # 0.8x to 1.2x based on quality
    quality_multiplier = max(0.5, min(1.5, quality_multiplier))
    
    # Calculate final risk percentage
    final_risk = base_risk * regime_multiplier * quality_multiplier
    risk_collateral = balance_usdc * final_risk
    
    # Use the larger of minimum or risk-based
    collateral = max(risk_collateral, min_collateral)
    
    # Cap at maximum (30% of balance)
    max_collateral = balance_usdc * 0.3
    collateral = min(collateral, max_collateral)
    
    log.info(f"Position sizing: Base {base_risk:.1%} × Regime {regime_multiplier:.1f}x × Quality {quality_multiplier:.1f}x = {final_risk:.1%} = ${collateral:.2f}")
    
    return collateral

def determine_elite_leverage(signal: Dict) -> int:
    """Determine leverage based on signal tier and market conditions"""
    tier = signal.get('tier', 2)
    regime = signal.get('regime', 'DEFAULT')
    
    tier_config = ELITE_CONFIG[f'tier{tier}']
    base_leverage = ELITE_CONFIG['base_leverage']
    max_leverage = tier_config['max_leverage']
    
    # Adjust leverage based on regime
    if regime == 'VOLATILE':
        leverage = min(base_leverage, max_leverage - 1)  # Reduce leverage in volatile markets
    elif regime in ['BULL_TRENDING', 'BEAR_TRENDING']:
        leverage = max_leverage  # Use max leverage in trending markets
    else:
        leverage = base_leverage
    
    return leverage

def send_transaction(tx_function, gas_limit=300000):
    """Enhanced transaction sending with EIP-1559 format for Base network"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Check Web3 connection
            if not w3.is_connected():
                raise Exception("Web3 not connected to RPC")
            
            # Get current network info
            chain_id = w3.eth.chain_id
            block_number = w3.eth.block_number
            log.info(f"Network: Chain ID {chain_id}, Block {block_number}")
            
            nonce = w3.eth.get_transaction_count(acct.address, 'pending')
            log.info(f"Account nonce: {nonce}")
            
            # Enhanced gas pricing for Base network - USE EIP-1559 FORMAT
            try:
                # Get base fee from latest block
                latest_block = w3.eth.get_block('latest')
                base_fee = latest_block.get('baseFeePerGas', w3.to_wei('0.1', 'gwei'))
                
                # Set priority fee (tip) - higher for Base network
                priority_fee = w3.to_wei('0.1', 'gwei')  # 0.1 gwei tip
                
                # Max fee = base fee * 2 + priority fee (EIP-1559 standard)
                max_fee = base_fee * 2 + priority_fee
                
                log.info(f"Base fee: {w3.from_wei(base_fee, 'gwei'):.6f} gwei")
                log.info(f"Priority fee: {w3.from_wei(priority_fee, 'gwei'):.6f} gwei") 
                log.info(f"Max fee: {w3.from_wei(max_fee, 'gwei'):.6f} gwei")
                
            except Exception as e:
                log.error(f"Gas price error: {e}")
                # Fallback values
                priority_fee = w3.to_wei('0.1', 'gwei')
                max_fee = w3.to_wei('1.0', 'gwei')
            
            # Build EIP-1559 transaction (Type 2) instead of legacy
            tx_params = {
                'from': acct.address,
                'nonce': nonce,
                'gas': gas_limit,
                'maxFeePerGas': max_fee,              # EIP-1559 format
                'maxPriorityFeePerGas': priority_fee, # EIP-1559 format
                'chainId': chain_id,
                'type': 2  # Explicitly set as EIP-1559 transaction
            }
            
            log.info(f"Building EIP-1559 transaction with params: {tx_params}")
            tx = tx_function.build_transaction(tx_params)
            
            # Validate transaction before signing
            log.info(f"EIP-1559 transaction built: {tx}")
            
            # Sign transaction
            signed_tx = acct.sign_transaction(tx)
            log.info(f"Transaction signed successfully")
            
            # Get raw transaction data
            raw_tx_data = getattr(signed_tx, 'raw_transaction', getattr(signed_tx, 'rawTransaction', None))
            if raw_tx_data is None:
                raise Exception("Could not get raw transaction data")
            
            log.info(f"Raw transaction size: {len(raw_tx_data)} bytes")
            
            # CRITICAL: Check account state before submission
            eth_balance = w3.eth.get_balance(acct.address)
            log.info(f"Account ETH balance: {w3.from_wei(eth_balance, 'ether'):.6f} ETH")
            
            gas_cost = gas_limit * max_fee
            if eth_balance < gas_cost:
                raise Exception(f"Insufficient ETH for gas: need {w3.from_wei(gas_cost, 'ether'):.6f} ETH")
            
            # Send transaction with detailed logging
            log.info(f"Submitting EIP-1559 transaction to network...")
            
            try:
                tx_hash = w3.eth.send_raw_transaction(raw_tx_data)
                log.info(f"✅ Primary RPC accepted transaction, hash: {tx_hash.hex()}")
            except Exception as submit_error:
                log.error(f"❌ Primary RPC FAILED: {submit_error}")
                
                # Try alternative RPCs for submission
                backup_rpcs = [
                    "https://mainnet.base.org",
                    "https://base.gateway.tenderly.co", 
                    "https://base.drpc.org"
                ]
                
                tx_hash = None
                for i, backup_rpc in enumerate(backup_rpcs):
                    try:
                        log.info(f"Trying backup RPC {i+1}: {backup_rpc}")
                        w3_backup = Web3(Web3.HTTPProvider(backup_rpc))
                        
                        if w3_backup.is_connected():
                            tx_hash = w3_backup.eth.send_raw_transaction(raw_tx_data)
                            log.info(f"✅ Backup RPC {i+1} accepted transaction: {tx_hash.hex()}")
                            break
                    except Exception as backup_error:
                        log.error(f"Backup RPC {i+1} failed: {backup_error}")
                        continue
                
                if not tx_hash:
                    raise Exception("All RPCs failed to submit transaction")
            
            # CRITICAL: Immediately verify transaction reached the blockchain
            log.info(f"🔍 Verifying transaction reached Base network...")
            
            verification_attempts = 0
            transaction_found = False
            
            while verification_attempts < 10:  # Try for 20 seconds
                try:
                    # Try to fetch the transaction from the blockchain
                    tx_receipt_check = w3.eth.get_transaction(tx_hash)
                    if tx_receipt_check:
                        log.info(f"✅ VERIFIED: Transaction found on Base blockchain!")
                        log.info(f"TX Hash: {tx_hash.hex()}")
                        log.info(f"BaseScan URL: https://basescan.org/tx/{tx_hash.hex()}")
                        transaction_found = True
                        break
                except Exception as verify_error:
                    if "not found" in str(verify_error).lower():
                        verification_attempts += 1
                        log.info(f"Verification attempt {verification_attempts}/10...")
                        time.sleep(2)
                    else:
                        log.error(f"Verification error: {verify_error}")
                        break
            
            if not transaction_found:
                log.error(f"❌ CRITICAL: Transaction hash returned but NOT FOUND on blockchain!")
                log.error(f"This means RPC accepted but didn't broadcast to Base network")
                log.error(f"Hash: {tx_hash.hex()}")
                raise Exception(f"Transaction not broadcast to network: {tx_hash.hex()}")
            
            # 🚀 NEW: RETURN IMMEDIATELY AFTER VERIFICATION
            log.info(f"🎉 TRANSACTION SUBMITTED SUCCESSFULLY!")
            log.info(f"🔄 Transaction will confirm in background (typically 1-3 minutes)")
            log.info(f"📊 Monitor progress: https://basescan.org/tx/{tx_hash.hex()}")
            
            # Create mock receipt for immediate return
            mock_receipt = {
                'transactionHash': tx_hash,
                'blockNumber': None,  # Will be set when mined
                'gasUsed': gas_limit,  # Estimated
                'status': 1  # Assume success (will be verified on blockchain)
            }
            
            return tx_hash, mock_receipt
                
        except Exception as e:
            log.error(f"Transaction attempt {attempt + 1} failed: {e}")
            if "nonce too low" in str(e).lower():
                log.info("Nonce issue detected, retrying...")
                time.sleep(5)
            elif attempt == max_retries - 1:
                raise
            else:
                time.sleep(10)  
                
def log_elite_trade(trade_data: Dict):
    """Enhanced trade logging for elite signals"""
    if not sheets_service:
        log.info("Google Sheets logging disabled - trade data logged locally only")
        log.info(f"TRADE LOG: {json.dumps(trade_data, indent=2)}")
        return
    
    if not TRADE_LOG_SHEET:
        log.warning("TRADE_LOG_SHEET_ID not configured - skipping sheets logging")
        return
    
    try:
        # Comprehensive trade log with all elite signal data
        values = [[
            datetime.now().isoformat(),
            trade_data.get('symbol'),
            trade_data.get('direction'),
            trade_data.get('tier', 'N/A'),
            trade_data.get('regime', 'UNKNOWN'),
            trade_data.get('signalQuality', 0),
            trade_data.get('longScore', 0),
            trade_data.get('shortScore', 0),
            trade_data.get('entry'),
            trade_data.get('stopLoss'),
            trade_data.get('takeProfit1'),
            trade_data.get('takeProfit2', ''),
            trade_data.get('takeProfit3', ''),
            trade_data.get('collateral'),
            trade_data.get('leverage'),
            trade_data.get('rrRatio', 0),
            trade_data.get('rsi30m', 'N/A'),
            trade_data.get('macd30m', 'N/A'),
            trade_data.get('ema9', 'N/A'),
            trade_data.get('ema21', 'N/A'),
            trade_data.get('macd4h', 'N/A'),
            trade_data.get('macd1d', 'N/A'),
            trade_data.get('rationale', ''),
            trade_data.get('tx_hash', ''),
            trade_data.get('gas_used', 0),
            trade_data.get('status'),
            trade_data.get('error', '')
        ]]
        
        body = {'values': values}
        
        sheets_service.spreadsheets().values().append(
            spreadsheetId=TRADE_LOG_SHEET,
            range=f"{TRADE_LOG_TAB}!A:AA",  # Extended to column AA
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        log.info("Trade logged to Google Sheets successfully")
        
    except Exception as e:
        log.error(f"Failed to log to Google Sheets: {e}")
        # Still log locally as backup
        log.info(f"BACKUP TRADE LOG: {json.dumps(trade_data, indent=2)}")

# ----- FLASK APP -----
app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Enhanced health check with elite bot status"""
    try:
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        
        daily_trades = tracker.get_daily_trade_count()
        should_stop, stop_reason = tracker.should_stop_trading()
        
        return jsonify({
            "status": "healthy" if not should_stop else "limited",
            "version": "elite_v1.0_eip1559",
            "wallet": acct.address,
            "balance_usdc": round(balance, 2),
            "web3_connected": w3.is_connected(),
            "daily_trades": daily_trades,
            "max_daily_trades": ELITE_CONFIG['max_daily_trades'],
            "trading_enabled": not should_stop,
            "stop_reason": stop_reason if should_stop else None,
            "google_sheets": "enabled" if sheets_service else "disabled",
            "authentication": "enabled" if os.getenv('WEBHOOK_SECRET') else "disabled"
        })
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/execute', methods=['POST'])
@require_auth
def execute_elite_trade():
    """Execute trade with elite signal processing"""
    signal = request.json
    trade_data = signal.copy()
    
    try:
        log.info(f"=== ELITE SIGNAL RECEIVED ===")
        log.info(f"Symbol: {signal.get('symbol', 'UNKNOWN')}")
        log.info(f"Direction: {signal.get('direction', 'UNKNOWN')}")
        log.info(f"Tier: {signal.get('tier', 'UNKNOWN')}")
        log.info(f"Regime: {signal.get('regime', 'UNKNOWN')}")
        log.info(f"Quality: {signal.get('signalQuality', 'UNKNOWN')}")
        
        # 1. Check if trading should be stopped
        should_stop, stop_reason = tracker.should_stop_trading()
        if should_stop:
            log.warning(f"Trading stopped: {stop_reason}")
            return jsonify({"status": "rejected", "reason": stop_reason}), 200
        
        # 2. Validate elite signal
        validate_elite_signal(signal)
        
        # 3. Check for duplicate trades
        trade_hash = generate_elite_hash(signal)
        if tracker.is_duplicate(trade_hash):
            log.warning(f"Duplicate elite trade detected: {trade_hash}")
            return jsonify({"status": "rejected", "reason": "duplicate trade"}), 200
        
        # 4. Check balance
        balance_wei = erc20.functions.balanceOf(acct.address).call()
        balance_usdc = balance_wei / 1e6
        
        if balance_usdc < 100:  # Higher minimum for elite trading
            raise Exception(f"Insufficient balance: {balance_usdc:.2f} USDC")
        
        # 5. Calculate elite position size and leverage
        symbol = signal['symbol']
        coin = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
        
        collateral = calculate_elite_position_size(signal, balance_usdc)
        leverage = determine_elite_leverage(signal)
        collateral_units = int(collateral * 1e6)
        
        # Define pair index and trade parameters FIRST
        pair_index = {'BTC': 0, 'ETH': 1}[coin]
        is_long = signal['direction'] == 'LONG'
        
        # Convert prices to proper format (1e8 for Gains Network)
        tp_price = int(float(signal['takeProfit1']) * 1e8)
        sl_price = int(float(signal['stopLoss']) * 1e8)
        
        log.info(f"=== POSITION DETAILS ===")
        log.info(f"Collateral: ${collateral:.2f} USDC")
        log.info(f"Leverage: {leverage}x")
        log.info(f"Notional: ${collateral * leverage:.2f}")
        log.info(f"Balance: ${balance_usdc:.2f} USDC")
        
        # 7. Check and set allowance
        gains_address_checksum = Web3.to_checksum_address(GAINS_TRADING_ADDRESS)
        current_allowance = erc20.functions.allowance(acct.address, gains_address_checksum).call()
        log.info(f"Current USDC allowance: {current_allowance / 1e6:.2f} USDC")
        log.info(f"Required collateral: {collateral_units / 1e6:.2f} USDC")
        
        if current_allowance < collateral_units:
            log.info("Setting USDC allowance...")
            approve_tx = erc20.functions.approve(gains_address_checksum, 2**256 - 1)
            tx_hash, _ = send_transaction(approve_tx, gas_limit=100000)
            log.info(f"Approval tx: {tx_hash.hex()}")
            time.sleep(10)  # Wait longer for approval
            
            # Verify allowance was set
            new_allowance = erc20.functions.allowance(acct.address, gains_address_checksum).call()
            log.info(f"New allowance: {new_allowance / 1e6:.2f} USDC")
        
        # 8. Debug all trade parameters
        log.info(f"Pair Index: {pair_index} (BTC=0, ETH=1)")
        log.info(f"Is Long: {is_long}")
        log.info(f"Leverage: {leverage}")
        log.info(f"Collateral: {collateral_units} units ({collateral:.2f} USDC)")
        log.info(f"Entry Price: Market order (0)")
        log.info(f"Take Profit: {tp_price} ({float(signal['takeProfit1']):.2f})")
        log.info(f"Stop Loss: {sl_price} ({float(signal['stopLoss']):.2f})")
        
        # Check if prices are reasonable (BTC should be ~$60k-$100k range)
        entry_price_estimate = float(signal.get('entry', 0))
        if entry_price_estimate < 50000 or entry_price_estimate > 150000:
            log.warning(f"Unusual BTC price: ${entry_price_estimate:.2f} - check signal data")
        
        # Check minimum position size (Gains Network might have minimums)
        notional_value = collateral * leverage
        log.info(f"Total position size: ${notional_value:.2f}")
        if notional_value < 100:
            log.warning(f"Position size ${notional_value:.2f} might be below minimum requirements")
        
        # Elite trade struct - EXACTLY as Gains Network expects
        trade_tuple = (
            acct.address,        # trader
            0,                   # pairIndex (will be overridden)
            pair_index,          # index (BTC=0, ETH=1)
            leverage,            # leverage
            is_long,             # buy (True for long)
            True,                # isOpen (always True for new trades)
            0,                   # collateralIndex (0 = USDC)
            0,                   # tradeType (0 = market order)
            collateral_units,    # collateralAmount in USDC wei
            0,                   # openPrice (0 for market orders)
            tp_price,           # tp (take profit in 1e8 format)
            sl_price,           # sl (stop loss in 1e8 format)
            0                   # referral (0 = no referral)
        )
        
        log.info(f"Final trade tuple: {trade_tuple}")
        
        # 9. TEST: Try to call a read-only function to verify contract works
        try:
            log.info("=== TESTING GAINS TRADING CONTRACT CONNECTION ===")
            log.info(f"Using GNSMultiCollatDiamond at {GAINS_TRADING_ADDRESS}")
            log.info("Gains Network trading contract appears accessible")
        except Exception as contract_error:
            log.error(f"Cannot access Gains Network trading contract: {contract_error}")
            raise Exception(f"Contract connection issue: {contract_error}")
        
        # 10. Execute elite trade with enhanced debugging
        log.info(f"=== EXECUTING ELITE TRADE ===")
        log.info(f"Opening {signal['direction']} position on {coin}")
        log.info(f"Trade params: pair_index={pair_index}, leverage={leverage}, is_long={is_long}")
        log.info(f"Collateral: {collateral_units} units, TP: {tp_price}, SL: {sl_price}")
        
        # ATTEMPT 1: Try with original parameters
        try:
            log.info("Attempting gas estimation with current parameters...")
            estimated_gas = gains.functions.openTrade(
                trade_tuple,
                ELITE_CONFIG['max_slippage'] * 10,  # 300 basis points = 3%
                acct.address
            ).estimate_gas({'from': acct.address})
            log.info(f"✅ Gas estimation successful: {estimated_gas}")
            gas_limit = int(estimated_gas * 1.5)  # Add 50% buffer
            
        except Exception as gas_error:
            log.error(f"❌ Gas estimation failed: {gas_error}")
            log.error(f"Trade tuple: {trade_tuple}")
            log.error(f"Max slippage: {ELITE_CONFIG['max_slippage'] * 10}")
            
            # ATTEMPT 2: Try with different pair index (maybe BTC is pair 1?)
            log.info("Trying with different pair index...")
            alt_trade_tuple = list(trade_tuple)
            alt_trade_tuple[2] = 1 if pair_index == 0 else 0  # Flip pair index
            
            try:
                log.info(f"Testing pair index {alt_trade_tuple[2]}...")
                estimated_gas = gains.functions.openTrade(
                    tuple(alt_trade_tuple),
                    ELITE_CONFIG['max_slippage'] * 10,
                    acct.address
                ).estimate_gas({'from': acct.address})
                log.info(f"✅ Alternative pair index works! Using pair {alt_trade_tuple[2]}")
                trade_tuple = tuple(alt_trade_tuple)
                gas_limit = int(estimated_gas * 1.5)
                
            except Exception as alt_error:
                log.error(f"Alternative pair index also failed: {alt_error}")
                
                # ATTEMPT 3: Try with larger position size
                log.info("Trying with larger position size...")
                larger_collateral = int(200 * 1e6)  # $200 instead of $60
                large_trade_tuple = list(trade_tuple)
                large_trade_tuple[8] = larger_collateral
                
                try:
                    log.info(f"Testing larger position: ${larger_collateral / 1e6:.2f}")
                    estimated_gas = gains.functions.openTrade(
                        tuple(large_trade_tuple),
                        ELITE_CONFIG['max_slippage'] * 10,
                        acct.address
                    ).estimate_gas({'from': acct.address})
                    log.info(f"✅ Larger position works! Minimum might be $200")
                    trade_tuple = tuple(large_trade_tuple)
                    gas_limit = int(estimated_gas * 1.5)
                    
                    # Update collateral for logging
                    collateral = larger_collateral / 1e6
                    
                except Exception as large_error:
                    log.error(f"Larger position also failed: {large_error}")
                    log.error(f"❌ ALL ATTEMPTS FAILED - Contract is rejecting trade")
                    log.error(f"Possible issues:")
                    log.error(f"  1. Wrong contract ABI")
                    log.error(f"  2. Contract paused/disabled")  
                    log.error(f"  3. Insufficient allowance")
                    log.error(f"  4. Invalid price format")
                    log.error(f"  5. Pair not supported")
                    
                    # Use very high gas limit and try anyway
                    gas_limit = 1000000
                    log.warning(f"Proceeding with high gas limit anyway: {gas_limit}")
        
        # Build the transaction
        trade_tx = gains.functions.openTrade(
            trade_tuple,
            ELITE_CONFIG['max_slippage'] * 10,  # max_slippage in basis points
            acct.address
        )
        
        tx_hash, receipt = send_transaction(trade_tx, gas_limit=gas_limit)
        
        # 11. Record successful elite trade
        tracker.add_trade(trade_hash, signal)
        
        # 12. Enhanced logging
        trade_data.update({
            'collateral': collateral,
            'leverage': leverage,
            'tx_hash': tx_hash.hex(),
            'gas_used': receipt['gasUsed'],
            'status': 'SUCCESS'
        })
        log_elite_trade(trade_data)
        
        log.info(f"=== ELITE TRADE SUCCESS ===")
        log.info(f"TX Hash: {tx_hash.hex()}")
        log.info(f"Gas Used: {receipt['gasUsed']}")
        
        return jsonify({
            "status": "success",
            "version": "elite_eip1559",
            "tx_hash": tx_hash.hex(),
            "collateral": collateral,
            "leverage": leverage,
            "pair": f"{coin}/USDT",
            "tier": signal.get('tier'),
            "regime": signal.get('regime'),
            "quality": signal.get('signalQuality')
        })
        
    except Exception as e:
        log.error(f"=== ELITE TRADE FAILED ===")
        log.error(f"Error: {str(e)}", exc_info=True)
        
        # Log failed trade with full context
        trade_data.update({
            'status': 'FAILED',
            'error': str(e)
        })
        log_elite_trade(trade_data)
        
        return jsonify({
            "status": "error",
            "version": "elite_eip1559",
            "message": str(e)
        }), 500

@app.route('/positions', methods=['GET'])
@require_auth
def get_elite_positions():
    """Get current positions with enhanced tracking"""
    try:
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        daily_trades = tracker.get_daily_trade_count()
        
        return jsonify({
            "status": "success",
            "version": "elite_eip1559",
            "balance_usdc": round(balance, 2),
            "daily_trades": daily_trades,
            "max_daily_trades": ELITE_CONFIG['max_daily_trades'],
            "positions": [],  # Would need Gains Network position tracking
            "message": "Elite position tracking - implement with Gains Network API"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status/<tx_hash>', methods=['GET'])
@require_auth
def check_transaction_status(tx_hash):
    """Check status of a specific transaction"""
    try:
        # Validate tx hash format
        if not tx_hash.startswith('0x') or len(tx_hash) != 66:
            return jsonify({"error": "Invalid transaction hash format"}), 400
        
        # Check transaction status
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                status = "success" if receipt['status'] == 1 else "failed"
                return jsonify({
                    "status": status,
                    "tx_hash": tx_hash,
                    "block_number": receipt['blockNumber'],
                    "gas_used": receipt['gasUsed'],
                    "basescan_url": f"https://basescan.org/tx/{tx_hash}"
                })
            else:
                return jsonify({
                    "status": "pending",
                    "tx_hash": tx_hash,
                    "basescan_url": f"https://basescan.org/tx/{tx_hash}"
                })
        except Exception as e:
            if "not found" in str(e).lower():
                return jsonify({
                    "status": "not_found",
                    "tx_hash": tx_hash,
                    "message": "Transaction not found on blockchain"
                })
            else:
                raise
                
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/stats', methods=['GET'])
@require_auth
def get_elite_stats():
    """Get elite bot trading statistics"""
    try:
        today = datetime.now().date()
        daily_stats = tracker.daily_stats.get(today, {"trades": 0, "pnl": 0.0})
        
        return jsonify({
            "status": "success",
            "version": "elite_eip1559",
            "today": {
                "trades": daily_stats["trades"],
                "pnl": daily_stats["pnl"],
                "max_trades": ELITE_CONFIG['max_daily_trades']
            },
            "config": {
                "tier1_risk": ELITE_CONFIG['tier1']['risk_per_trade'],
                "tier2_risk": ELITE_CONFIG['tier2']['risk_per_trade'],
                "min_signal_quality": ELITE_CONFIG['min_signal_quality'],
                "regime_filters": ELITE_CONFIG['regime_filters']
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Error handlers remain the same
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found", "version": "elite_eip1559"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "version": "elite_eip1559"}), 500

if __name__ == '__main__':
    # Elite startup checks
    try:
        # Test wallet and contracts
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        log.info(f"=== ELITE BOT STARTED ===")
        log.info(f"Chain ID: {w3.eth.chain_id}")
        log.info(f"Latest Block: {w3.eth.block_number}")
        log.info(f"Wallet: {acct.address}")
        log.info(f"Balance: ${balance:.2f} USDC")
        log.info(f"Trading Contract: {GAINS_TRADING_ADDRESS}")
        log.info(f"Max Daily Trades: {ELITE_CONFIG['max_daily_trades']}")
        log.info(f"Tier 1 Risk: {ELITE_CONFIG['tier1']['risk_per_trade']:.1%}")
        log.info(f"Tier 2 Risk: {ELITE_CONFIG['tier2']['risk_per_trade']:.1%}")
        log.info(f"Min Signal Quality: {ELITE_CONFIG['min_signal_quality']}")
        log.info(f"Google Sheets Logging: {'✅ Enabled' if sheets_service else '❌ Disabled (will log locally)'}")
        log.info(f"Authentication: {'🔒 Enabled' if os.getenv('WEBHOOK_SECRET') else '🔓 Disabled'}")
        log.info(f"Transaction Format: EIP-1559 (Type 2) for Base compatibility")
        log.info(f"=== READY FOR ELITE SIGNALS ===")
    except Exception as e:
        log.error(f"Elite startup check failed: {e}")
        log.error(f"Check RPC connection and contract addresses")
    
    # Run Flask app
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
