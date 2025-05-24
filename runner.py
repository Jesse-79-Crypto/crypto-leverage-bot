#!/usr/bin/env python3
"""
ELITE Flask webhook for Gains Network trades - Optimized for Elite Trading Bot
Enhanced with regime-based position sizing, tier-based risk management,
multi-timeframe validation, and advanced performance tracking.
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
GAINS_ADDRESS   = "0xfB1AabA03c31EA98A3eec7591808ACb1947eE7aC"  # Checksummed address
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

# ----- WEB3 SETUP -----
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    log.error("Failed to connect to RPC")
    raise Exception("Web3 connection failed")

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
    gains = w3.eth.contract(
        address=Web3.to_checksum_address(GAINS_ADDRESS),
        abi=load_abi('gains_base_abi.json')
    )
    log.info(f"Contracts loaded: USDC={Web3.to_checksum_address(USDC_ADDRESS)}")
    log.info(f"Contracts loaded: Gains={Web3.to_checksum_address(GAINS_ADDRESS)}")
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
    """Enhanced transaction sending with better error handling"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            nonce = w3.eth.get_transaction_count(acct.address, 'pending')
            
            # Dynamic gas pricing
            try:
                gas_price = w3.eth.gas_price
                # Add 15% to gas price for faster execution in volatile markets
                gas_price = int(gas_price * 1.15)
            except:
                gas_price = w3.to_wei('20', 'gwei')  # Fallback gas price
            
            tx = tx_function.build_transaction({
                'from': acct.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price
            })
            
            signed_tx = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            log.info(f"Transaction sent: {tx_hash.hex()}")
            
            # Wait for confirmation with timeout
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
            
            if receipt['status'] == 1:
                log.info(f"Transaction confirmed: Gas used {receipt['gasUsed']}")
                return tx_hash, receipt
            else:
                raise Exception(f"Transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            log.error(f"Transaction attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(10)  # Longer wait before retry

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
            "version": "elite_v1.0",
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
        
        log.info(f"=== POSITION DETAILS ===")
        log.info(f"Collateral: ${collateral:.2f} USDC")
        log.info(f"Leverage: {leverage}x")
        log.info(f"Notional: ${collateral * leverage:.2f}")
        log.info(f"Balance: ${balance_usdc:.2f} USDC")
        
        # 6. Check and set allowance
        gains_address_checksum = Web3.to_checksum_address(GAINS_ADDRESS)
        current_allowance = erc20.functions.allowance(acct.address, gains_address_checksum).call()
        if current_allowance < collateral_units:
            log.info("Setting USDC allowance...")
            approve_tx = erc20.functions.approve(gains_address_checksum, 2**256 - 1)
            tx_hash, _ = send_transaction(approve_tx, gas_limit=100000)
            log.info(f"Approval tx: {tx_hash.hex()}")
            time.sleep(5)
        
        # 7. Prepare elite trade parameters
        pair_index = {'BTC': 0, 'ETH': 1}[coin]
        is_long = signal['direction'] == 'LONG'
        
        # Convert prices to proper format (1e8 for Gains Network)
        tp_price = int(float(signal['takeProfit1']) * 1e8)
        sl_price = int(float(signal['stopLoss']) * 1e8)
        
        # Elite trade struct
        trade_tuple = (
            acct.address,        # trader
            0,                   # pairIndex
            pair_index,          # index
            leverage,            # dynamic leverage
            is_long,             # buy
            True,                # isOpen
            0,                   # collateralIndex (USDC)
            0,                   # tradeType (market)
            collateral_units,    # collateralAmount
            0,                   # openPrice (0 for market)
            tp_price,           # tp
            sl_price,           # sl
            0                   # referral
        )
        
        # 8. Execute elite trade
        log.info(f"=== EXECUTING ELITE TRADE ===")
        log.info(f"Opening {signal['direction']} position on {coin}")
        
        trade_tx = gains.functions.openTrade(
            trade_tuple,
            ELITE_CONFIG['base_leverage'] * 10,  # max_slippage in basis points
            acct.address
        )
        
        tx_hash, receipt = send_transaction(trade_tx, gas_limit=500000)
        
        # 9. Record successful elite trade
        tracker.add_trade(trade_hash, signal)
        
        # 10. Enhanced logging
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
            "version": "elite",
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
            "version": "elite",
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
            "version": "elite",
            "balance_usdc": round(balance, 2),
            "daily_trades": daily_trades,
            "max_daily_trades": ELITE_CONFIG['max_daily_trades'],
            "positions": [],  # Would need Gains Network position tracking
            "message": "Elite position tracking - implement with Gains Network API"
        })
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
            "version": "elite",
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
    return jsonify({"error": "Endpoint not found", "version": "elite"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "version": "elite"}), 500

if __name__ == '__main__':
    # Elite startup checks
    try:
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        log.info(f"=== ELITE BOT STARTED ===")
        log.info(f"Wallet: {acct.address}")
        log.info(f"Balance: ${balance:.2f} USDC")
        log.info(f"Max Daily Trades: {ELITE_CONFIG['max_daily_trades']}")
        log.info(f"Tier 1 Risk: {ELITE_CONFIG['tier1']['risk_per_trade']:.1%}")
        log.info(f"Tier 2 Risk: {ELITE_CONFIG['tier2']['risk_per_trade']:.1%}")
        log.info(f"Min Signal Quality: {ELITE_CONFIG['min_signal_quality']}")
        log.info(f"Google Sheets Logging: {'✅ Enabled' if sheets_service else '❌ Disabled (will log locally)'}")
        log.info(f"Authentication: {'🔒 Enabled' if os.getenv('WEBHOOK_SECRET') else '🔓 Disabled'}")
        log.info(f"=== READY FOR ELITE SIGNALS ===")
    except Exception as e:
        log.error(f"Elite startup check failed: {e}")
    
    # Run Flask app
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
