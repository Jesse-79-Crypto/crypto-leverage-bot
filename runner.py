#!/usr/bin/env python3
"""
Enhanced Flask webhook for Gains Network trades.
Adds signal validation, duplicate prevention, position tracking,
and comprehensive error handling.
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from web3 import Web3
from google.oauth2 import service_account
from googleapiclient.discovery import build
from functools import wraps

# ----- CONFIG -----
RPC_URL         = os.getenv('BASE_RPC_URL')
PRIVATE_KEY     = os.getenv('WALLET_PRIVATE_KEY')
TRADE_LOG_SHEET = os.getenv('TRADE_LOG_SHEET_ID')
TRADE_LOG_TAB   = os.getenv('TRADE_LOG_TAB_NAME', 'Trade Log')
USDC_ADDRESS    = os.getenv('USDC_ADDRESS')
GAINS_ADDRESS   = "0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac"
WEBHOOK_SECRET  = os.getenv('WEBHOOK_SECRET', 'your-secret-key')

MIN_NOTIONAL = {
    "BTC": 300,
    "ETH": 250,
    "DEFAULT": 150
}

TRADING_CONFIG = {
    "leverage": 5,
    "max_slippage": 30,  # basis points
    "risk_per_trade": 0.15,  # 15% of balance
    "max_positions": 3,  # Max concurrent positions
    "min_rr_ratio": 1.5,  # Minimum risk/reward ratio
    "cooldown_minutes": 5,  # Prevent duplicate trades
}

# ----- LOGGING -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ----- WEB3 SETUP -----
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    log.error("Failed to connect to RPC")
    raise Exception("Web3 connection failed")

acct = w3.eth.account.from_key(PRIVATE_KEY)
log.info(f"Bot wallet: {acct.address}")

# ----- TRADE TRACKING -----
recent_trades = {}  # Track recent trades to prevent duplicates

# ----- ABI LOADER -----
def load_abi(filename):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        abi_path = os.path.join(base_dir, 'abi', filename)
        with open(abi_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning(f"ABI file not found: {filename}, using minimal ABI")
        # Minimal ERC20 ABI
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

# Load contracts
try:
    erc20 = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=load_abi('erc20_abi.json')
    )
    gains = w3.eth.contract(
        address=Web3.to_checksum_address(GAINS_ADDRESS),
        abi=load_abi('gains_base_abi.json')
    )
except Exception as e:
    log.error(f"Failed to load contracts: {e}")
    raise

# ----- GOOGLE SHEETS -----
def get_sheets_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json'),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        log.error(f"Failed to setup Google Sheets: {e}")
        return None

sheets_service = get_sheets_service()

# ----- AUTHENTICATION -----
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {WEBHOOK_SECRET}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ----- HELPER FUNCTIONS -----
def generate_trade_hash(signal):
    """Generate unique hash for trade to prevent duplicates"""
    trade_str = f"{signal['coin']}_{signal['direction']}_{signal['entry']}"
    return hashlib.md5(trade_str.encode()).hexdigest()

def is_duplicate_trade(trade_hash):
    """Check if trade was recently executed"""
    if trade_hash in recent_trades:
        trade_time = recent_trades[trade_hash]
        if datetime.now() - trade_time < timedelta(minutes=TRADING_CONFIG['cooldown_minutes']):
            return True
    return False

def validate_signal(signal):
    """Validate incoming signal data"""
    required_fields = ['coin', 'direction', 'entry', 'stopLoss', 'tp1']
    
    # Check required fields
    for field in required_fields:
        if field not in signal:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate coin
    if signal['coin'] not in ['BTC', 'ETH']:
        raise ValueError(f"Unsupported coin: {signal['coin']}")
    
    # Validate direction
    if signal['direction'] not in ['LONG', 'SHORT']:
        raise ValueError(f"Invalid direction: {signal['direction']}")
    
    # Validate prices
    entry = float(signal['entry'])
    stop = float(signal['stopLoss'])
    tp1 = float(signal['tp1'])
    
    if entry <= 0 or stop <= 0 or tp1 <= 0:
        raise ValueError("Invalid price values")
    
    # Validate R:R ratio
    if signal['direction'] == 'LONG':
        risk = entry - stop
        reward = tp1 - entry
    else:
        risk = stop - entry
        reward = entry - tp1
    
    if risk <= 0:
        raise ValueError("Invalid stop loss")
    
    rr_ratio = reward / risk
    if rr_ratio < TRADING_CONFIG['min_rr_ratio']:
        raise ValueError(f"R:R ratio {rr_ratio:.2f} below minimum {TRADING_CONFIG['min_rr_ratio']}")
    
    return True

def calculate_position_size(coin, balance_usdc):
    """Calculate position size based on risk management rules"""
    min_notional = MIN_NOTIONAL.get(coin, MIN_NOTIONAL['DEFAULT'])
    min_collateral = min_notional / TRADING_CONFIG['leverage']
    
    # Risk-based collateral (percentage of balance)
    risk_collateral = balance_usdc * TRADING_CONFIG['risk_per_trade']
    
    # Use the larger of min collateral or risk-based collateral
    collateral = max(risk_collateral, min_collateral)
    
    # Cap at maximum reasonable size
    max_collateral = balance_usdc * 0.3  # Never risk more than 30% on one trade
    collateral = min(collateral, max_collateral)
    
    return collateral

def send_transaction(tx_function, gas_limit=300000):
    """Send transaction with retry logic"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            nonce = w3.eth.get_transaction_count(acct.address, 'pending')
            gas_price = w3.eth.gas_price
            
            # Add 10% to gas price for faster execution
            gas_price = int(gas_price * 1.1)
            
            tx = tx_function.build_transaction({
                'from': acct.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price
            })
            
            signed_tx = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt['status'] == 1:
                return tx_hash, receipt
            else:
                raise Exception(f"Transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            log.error(f"Transaction attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(5)  # Wait before retry

def log_trade_to_sheet(trade_data):
    """Log trade data to Google Sheets"""
    if not sheets_service:
        log.warning("Sheets service not available, skipping logging")
        return
    
    try:
        values = [[
            datetime.now().isoformat(),
            trade_data.get('coin'),
            trade_data.get('direction'),
            trade_data.get('entry'),
            trade_data.get('stopLoss'),
            trade_data.get('tp1'),
            trade_data.get('tp2'),
            trade_data.get('tp3'),
            trade_data.get('collateral'),
            trade_data.get('leverage'),
            trade_data.get('rsi30m'),
            trade_data.get('macd30m'),
            trade_data.get('regime'),
            trade_data.get('rrRatio'),
            trade_data.get('tx_hash'),
            trade_data.get('status'),
            trade_data.get('error', '')
        ]]
        
        body = {'values': values}
        
        sheets_service.spreadsheets().values().append(
            spreadsheetId=TRADE_LOG_SHEET,
            range=f"{TRADE_LOG_TAB}!A:Q",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
    except Exception as e:
        log.error(f"Failed to log to sheets: {e}")

# ----- FLASK APP -----
app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        return jsonify({
            "status": "healthy",
            "wallet": acct.address,
            "balance_usdc": balance,
            "connected": w3.is_connected()
        })
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/execute', methods=['POST'])
@require_auth
def execute_trade():
    """Execute trade based on signal"""
    signal = request.json
    trade_data = signal.copy()
    
    try:
        log.info(f"Received signal: {signal.get('coin')} {signal.get('direction')}")
        
        # 1. Validate signal
        validate_signal(signal)
        
        # 2. Check for duplicate trades
        trade_hash = generate_trade_hash(signal)
        if is_duplicate_trade(trade_hash):
            log.warning(f"Duplicate trade detected: {trade_hash}")
            return jsonify({"status": "rejected", "reason": "duplicate trade"}), 200
        
        # 3. Check balance
        balance_wei = erc20.functions.balanceOf(acct.address).call()
        balance_usdc = balance_wei / 1e6
        
        if balance_usdc < 50:  # Minimum balance check
            raise Exception(f"Insufficient balance: {balance_usdc:.2f} USDC")
        
        # 4. Calculate position size
        coin = signal['coin']
        collateral = calculate_position_size(coin, balance_usdc)
        collateral_units = int(collateral * 1e6)
        
        log.info(f"Position size: {collateral:.2f} USDC (Balance: {balance_usdc:.2f})")
        
        # 5. Check and set allowance
        current_allowance = erc20.functions.allowance(acct.address, GAINS_ADDRESS).call()
        if current_allowance < collateral_units:
            log.info("Setting USDC allowance...")
            approve_tx = erc20.functions.approve(GAINS_ADDRESS, 2**256 - 1)
            tx_hash, _ = send_transaction(approve_tx, gas_limit=100000)
            log.info(f"Approval tx: {tx_hash.hex()}")
            time.sleep(5)  # Wait for approval
        
        # 6. Prepare trade parameters
        pair_index = {'BTC': 0, 'ETH': 1}[coin]
        is_long = signal['direction'] == 'LONG'
        
        # Convert prices to proper format (1e8)
        tp_price = int(float(signal['tp1']) * 1e8)
        sl_price = int(float(signal['stopLoss']) * 1e8)
        
        # Trade struct for Gains Network
        trade_tuple = (
            acct.address,        # trader
            0,                   # pairIndex
            pair_index,          # index
            TRADING_CONFIG['leverage'],  # leverage
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
        
        # 7. Execute trade
        log.info(f"Opening {signal['direction']} position on {coin}...")
        trade_tx = gains.functions.openTrade(
            trade_tuple,
            TRADING_CONFIG['max_slippage'],
            acct.address
        )
        
        tx_hash, receipt = send_transaction(trade_tx, gas_limit=400000)
        
        # 8. Record successful trade
        recent_trades[trade_hash] = datetime.now()
        
        # 9. Log to sheet
        trade_data.update({
            'collateral': collateral,
            'leverage': TRADING_CONFIG['leverage'],
            'tx_hash': tx_hash.hex(),
            'status': 'SUCCESS',
            'gas_used': receipt['gasUsed']
        })
        log_trade_to_sheet(trade_data)
        
        log.info(f"Trade executed successfully: {tx_hash.hex()}")
        
        return jsonify({
            "status": "success",
            "tx_hash": tx_hash.hex(),
            "collateral": collateral,
            "pair": f"{coin}/USDT"
        })
        
    except Exception as e:
        log.error(f"Trade execution failed: {str(e)}", exc_info=True)
        
        # Log failed trade
        trade_data.update({
            'status': 'FAILED',
            'error': str(e)
        })
        log_trade_to_sheet(trade_data)
        
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/positions', methods=['GET'])
@require_auth
def get_positions():
    """Get current open positions"""
    try:
        # This would need the actual Gains Network position tracking implementation
        # Placeholder for now
        return jsonify({
            "status": "success",
            "positions": [],
            "message": "Position tracking not yet implemented"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Startup checks
    try:
        balance = erc20.functions.balanceOf(acct.address).call() / 1e6
        log.info(f"Bot started - Wallet: {acct.address}, Balance: {balance:.2f} USDC")
    except Exception as e:
        log.error(f"Startup check failed: {e}")
    
    # Run Flask app
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
