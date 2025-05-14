from web3 import Web3
import json
import time
import os
import traceback
import threading
import requests
from decimal import Decimal, getcontext

# Set decimal precision
getcontext().prec = 28

# Set default values for environment variables if not present
def get_env_or_default(var_name, default_value):
    """
    Get environment variable or return default value if not present
    """
    value = os.getenv(var_name)
    if value is None:
        print(f"Environment variable {var_name} not found, using default: {default_value}")
        return default_value
    return value

# Default values for trading parameters
DEFAULT_LEVERAGE = 5
DEFAULT_MAX_RISK_PCT = 15

# Map trading symbols to Gains Network pair indices
PAIR_INDEX_MAP = {
    "BTC": 1,
    "ETH": 2,
    "LINK": 3,
    "SOL": 4,
    "AVAX": 5,
    "ARB": 6
}

# Approximate minimum notional values required by Gains Network per pair
MIN_NOTIONAL_PER_PAIR = {
    "BTC": 100,
    "ETH": 75,
    "LINK": 50,
    "SOL": 50,
    "AVAX": 50,
    "ARB": 50
}

# Default take profit levels (percentage)
DEFAULT_TP_LEVELS = {
    "TP1": 3.0,  # 3% for first take profit
    "TP2": 6.0,  # 6% for second take profit
    "TP3": 10.0  # 10% for third take profit
}

# Percentage of position to close at each TP level
TP_CLOSE_PERCENTAGES = {
    "TP1": 30,  # Close 30% of position at first take profit
    "TP2": 30,  # Close another 30% at second take profit
    "TP3": 40   # Close remaining 40% at third take profit
}

# Price API endpoints for different assets
PRICE_APIS = {
    "BTC": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    "ETH": "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
    "LINK": "https://api.binance.com/api/v3/ticker/price?symbol=LINKUSDT",
    "SOL": "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
    "AVAX": "https://api.binance.com/api/v3/ticker/price?symbol=AVAXUSDT",
    "ARB": "https://api.binance.com/api/v3/ticker/price?symbol=ARBUSDT"
}

# Active trades being monitored
active_trades = {}

class TrailingStopManager:
    def __init__(self, symbol, entry_price, is_long, initial_stop_pct=1.5, trail_pct=0.5):
        """
        Initialize a trailing stop manager
        
        Args:
            symbol: Trading symbol (BTC, ETH, etc.)
            entry_price: Position entry price
            is_long: True for long position, False for short
            initial_stop_pct: Initial stop loss percentage from entry
            trail_pct: How closely the stop follows the price (in percentage)
        """
        self.symbol = symbol
        self.entry_price = Decimal(str(entry_price))
        self.is_long = is_long
        self.initial_stop_pct = Decimal(str(initial_stop_pct))
        self.trail_pct = Decimal(str(trail_pct))
        
        # Calculate initial stop loss level
        if is_long:
            self.stop_price = self.entry_price * (1 - self.initial_stop_pct / 100)
            self.highest_price = self.entry_price
        else:
            self.stop_price = self.entry_price * (1 + self.initial_stop_pct / 100)
            self.lowest_price = self.entry_price
            
        self.activated = False
        self.last_update = time.time()
    
    def update(self, current_price):
        """
        Update the trailing stop based on current price
        
        Args:
            current_price: Latest price of the asset
            
        Returns:
            tuple: (triggered, stop_price) - whether stop loss triggered and current stop price
        """
        current_price = Decimal(str(current_price))
        
        # For long positions, trail upwards
        if self.is_long:
            # If price goes above previous high, adjust stop loss upward
            if current_price > self.highest_price:
                self.highest_price = current_price
                # Set new stop price to trail behind by trail_pct
                new_stop = self.highest_price * (1 - self.trail_pct / 100)
                # Only move stop price up, never down
                if new_stop > self.stop_price:
                    self.stop_price = new_stop
                    self.activated = True
                    
            # Check if stop loss is triggered
            if current_price <= self.stop_price:
                return True, float(self.stop_price)
        
        # For short positions, trail downwards
        else:
            # If price goes below previous low, adjust stop loss downward
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                # Set new stop price to trail behind by trail_pct
                new_stop = self.lowest_price * (1 + self.trail_pct / 100)
                # Only move stop price down, never up
                if new_stop < self.stop_price:
                    self.stop_price = new_stop
                    self.activated = True
                    
            # Check if stop loss is triggered
            if current_price >= self.stop_price:
                return True, float(self.stop_price)
        
        # Not triggered, return current stop level
        self.last_update = time.time()
        return False, float(self.stop_price)

class TakeProfitManager:
    def __init__(self, symbol, entry_price, is_long, position_size, tp_levels=None):
        """
        Initialize a take profit manager
        
        Args:
            symbol: Trading symbol (BTC, ETH, etc.)
            entry_price: Position entry price
            is_long: True for long position, False for short
            position_size: Size of position in USD
            tp_levels: Dictionary of take profit levels in percentage
        """
        self.symbol = symbol
        self.entry_price = Decimal(str(entry_price))
        self.is_long = is_long
        self.position_size = Decimal(str(position_size))
        self.remaining_size = self.position_size
        
        # Use default TP levels if none provided
        if tp_levels is None:
            self.tp_levels = DEFAULT_TP_LEVELS
        else:
            self.tp_levels = tp_levels
            
        # Calculate TP price levels
        self.tp_prices = {}
        for level, pct in self.tp_levels.items():
            if is_long:
                self.tp_prices[level] = self.entry_price * (1 + Decimal(str(pct)) / 100)
            else:
                self.tp_prices[level] = self.entry_price * (1 - Decimal(str(pct)) / 100)
                
        # Track which levels have been hit
        self.tp_hit = {"TP1": False, "TP2": False, "TP3": False}
    
    def check(self, current_price):
        """
        Check if any take profit levels are hit
        
        Args:
            current_price: Latest price of the asset
            
        Returns:
            tuple: (level_hit, close_size, close_price) - TP level hit, size to close, price
        """
        current_price = Decimal(str(current_price))
        
        for level in ["TP1", "TP2", "TP3"]:
            # Skip if this level was already hit
            if self.tp_hit[level]:
                continue
                
            # Check if price hits take profit level
            if (self.is_long and current_price >= self.tp_prices[level]) or \
               (not self.is_long and current_price <= self.tp_prices[level]):
                
                # Mark this level as hit
                self.tp_hit[level] = True
                
                # Calculate size to close
                close_pct = TP_CLOSE_PERCENTAGES[level]
                close_size = self.position_size * Decimal(str(close_pct)) / 100
                
                # Ensure we don't try to close more than remaining
                close_size = min(close_size, self.remaining_size)
                self.remaining_size -= close_size
                
                return level, float(close_size), float(self.tp_prices[level])
        
        # No levels hit
        return None, 0, 0

def get_current_price(symbol):
    """
    Get current price for a crypto asset
    
    Args:
        symbol: Trading symbol (BTC, ETH, etc.)
        
    Returns:
        float: Current price of the asset
    """
    try:
        if symbol in PRICE_APIS:
            response = requests.get(PRICE_APIS[symbol], timeout=10)
            data = response.json()
            return float(data.get('price', 0))
        else:
            print(f"No price API defined for {symbol}")
            return 0
    except Exception as e:
        print(f"Error fetching price for {symbol}: {str(e)}")
        return 0

def close_position(trade_info, close_pct, reason=""):
    """
    Close a position or part of a position
    
    Args:
        trade_info: Dictionary containing trade information
        close_pct: Percentage of position to close (0-100)
        reason: Reason for closing position
    
    Returns:
        Dictionary with close transaction result
    """
    try:
        print(f"Closing {close_pct}% of {trade_info['symbol']} position. Reason: {reason}")
        
        # Connect to Base network
        w3 = Web3(Web3.HTTPProvider(get_env_or_default("BASE_RPC_URL", "")))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to BASE network.")
        
        private_key = get_env_or_default("WALLET_PRIVATE_KEY", "")
        account = w3.eth.account.from_key(private_key)
        
        # Load contract ABI
        try:
            with open("abi/gains_base_abi.json", "r") as abi_file:
                gains_abi = json.load(abi_file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise Exception(f"Failed to load ABI: {str(e)}")
        
        contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
        contract = w3.eth.contract(address=contract_address, abi=gains_abi)
        
        # Get position ID from trade_info
        position_id = trade_info.get('position_id')
        if not position_id:
            raise ValueError("No position ID available for closing")
        
        # Calculate amount to close based on percentage
        close_size = int(trade_info.get('position_size_usd', 0) * close_pct / 100 * 1e6)
        
        # Prepare close position parameters
        try:
            # Try direct method call with parameters as expected
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            
            # Build close transaction
            txn = contract.functions.closePosition(
                position_id,          # Position ID
                close_size,           # Size to close
                30,                   # Slippage (0.1%)
                account.address       # Callback
            ).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'gasPrice': int(w3.eth.gas_price * 1.3),  # 30% higher for Base
                'value': 0
            })
            
            # Set gas limit
            txn['gas'] = 500000
            
            # Sign and send
            signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            
            print(f"Position close TX sent: {tx_hash.hex()}")
            
            return {
                "status": "CLOSE_SENT",
                "tx_hash": tx_hash.hex(),
                "close_pct": close_pct,
                "reason": reason,
                "log_link": f"https://basescan.org/tx/{tx_hash.hex()}"
            }
            
        except Exception as close_error:
            print(f"Error closing position: {str(close_error)}")
            return {
                "status": "error",
                "message": f"Failed to close position: {str(close_error)}",
                "trace": traceback.format_exc()
            }
            
    except Exception as e:
        print(f"Error in close_position: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }

def position_monitor(trade_info):
    """
    Monitor an open position and manage trailing stops and take profits
    
    Args:
        trade_info: Dictionary containing trade information
    """
    symbol = trade_info.get('symbol')
    entry_price = float(trade_info.get('entry_price', 0))
    is_long = trade_info.get('is_long', True)
    
    if not symbol or not entry_price:
        print(f"Invalid trade info for monitoring: {trade_info}")
        return
    
    print(f"Starting position monitor for {symbol} {'long' if is_long else 'short'} @ {entry_price}")
    
    # Initialize trailing stop with professional settings
    # Use tighter stops for higher volatility assets
    if symbol in ["BTC", "ETH"]:
        initial_stop_pct = 1.5  # Lower volatility major cryptos
    else:
        initial_stop_pct = 2.0  # Higher volatility altcoins
    
    # Create managers
    trailing_stop = TrailingStopManager(
        symbol, 
        entry_price, 
        is_long,
        initial_stop_pct=initial_stop_pct,
        trail_pct=0.5  # Tight trail of 0.5%
    )
    
    # Get TP levels from trade info or use defaults
    tp_levels = {}
    for level in ["TP1", "TP2", "TP3"]:
        if trade_info.get(level.lower()):
            tp_level_pct = (float(trade_info[level.lower()]) - entry_price) / entry_price * 100
            if not is_long:
                tp_level_pct = -tp_level_pct
            tp_levels[level] = abs(tp_level_pct)
    
    # Use defaults if not all levels are provided
    if len(tp_levels) < 3:
        tp_levels = DEFAULT_TP_LEVELS
    
    take_profit = TakeProfitManager(
        symbol,
        entry_price,
        is_long,
        float(trade_info.get('position_size_usd', 0)),
        tp_levels
    )
    
    # Monitor loop
    running = True
    check_interval = 5  # Check every 5 seconds
    
    while running and symbol in active_trades:
        try:
            # Get current price
            current_price = get_current_price(symbol)
            if not current_price:
                time.sleep(check_interval)
                continue
            
            # Update trailing stop
            stop_triggered, stop_price = trailing_stop.update(current_price)
            
            # Check if trailing stop is triggered
            if stop_triggered:
                print(f"⚠️ TRAILING STOP TRIGGERED for {symbol} at {stop_price}")
                # Close entire position
                result = close_position(trade_info, 100, reason="Trailing Stop Loss")
                if result.get('status') == "CLOSE_SENT":
                    print(f"✅ Position closed due to trailing stop: {result}")
                    # Remove from active trades
                    if symbol in active_trades:
                        del active_trades[symbol]
                    running = False
                else:
                    print(f"❌ Failed to close position: {result}")
            
            # Check take profit levels
            level_hit, close_size, tp_price = take_profit.check(current_price)
            
            # If a TP level is hit
            if level_hit:
                print(f"🎯 TAKE PROFIT {level_hit} REACHED for {symbol} at {tp_price}")
                
                # Calculate percentage to close
                close_pct = TP_CLOSE_PERCENTAGES[level_hit]
                
                # Close partial position
                result = close_position(trade_info, close_pct, reason=f"Take Profit {level_hit}")
                if result.get('status') == "CLOSE_SENT":
                    print(f"✅ Partial position ({close_pct}%) closed at {level_hit}: {result}")
                    
                    # Update position size in trade_info
                    remaining_pct = 100
                    for lvl, pct in TP_CLOSE_PERCENTAGES.items():
                        if take_profit.tp_hit[lvl]:
                            remaining_pct -= pct
                    
                    # If all TPs hit, remove from active trades
                    if remaining_pct <= 0 and symbol in active_trades:
                        del active_trades[symbol]
                        running = False
                else:
                    print(f"❌ Failed to close position at {level_hit}: {result}")
            
            # Log status periodically
            if int(time.time()) % 60 < 5:  # Log roughly every minute
                print(f"Monitoring {symbol}: Price=${current_price}, Stop=${stop_price}, " +
                      f"Entry=${entry_price}, Remaining={take_profit.remaining_size}")
                print(f"TP Status: TP1={'✅' if take_profit.tp_hit['TP1'] else '❌'}, " +
                      f"TP2={'✅' if take_profit.tp_hit['TP2'] else '❌'}, " +
                      f"TP3={'✅' if take_profit.tp_hit['TP3'] else '❌'}")
                      
        except Exception as monitor_error:
            print(f"Error in position monitor: {str(monitor_error)}")
            traceback.print_exc()
        
        time.sleep(check_interval)
    
    print(f"Position monitor for {symbol} terminated")

def execute_trade_on_gains(signal):
    print("Incoming signal data:", json.dumps(signal, indent=2))
    print("Trade execution started")
    try:
        # Connect to Base network
        w3 = Web3(Web3.HTTPProvider(get_env_or_default("BASE_RPC_URL", "")))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to BASE network.")
        print("Connected to BASE")

        private_key = get_env_or_default("WALLET_PRIVATE_KEY", "")
        account = w3.eth.account.from_key(private_key)
        print(f"Wallet loaded: {account.address}")

        # Load ABI with proper error handling
        try:
            with open("abi/gains_base_abi.json", "r") as abi_file:
                gains_abi = json.load(abi_file)
            print("ABI loaded")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise Exception(f"Failed to load ABI: {str(e)}")

        contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
        contract = w3.eth.contract(address=contract_address, abi=gains_abi)
        print("Contract connected")

        usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        usdc_abi = [
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "remaining", "type": "uint256"}], "type": "function"},
            {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
        ]
        usdc = w3.eth.contract(address=usdc_address, abi=usdc_abi)

        usdc_balance = usdc.functions.balanceOf(account.address).call() / 1e6
        usd_amount = usdc_balance * float(get_env_or_default("MAX_RISK_PCT", DEFAULT_MAX_RISK_PCT)) / 100
        print(f"USDC balance: {usdc_balance:.2f}, Using: {usd_amount:.2f} for this trade (MAX_RISK_PCT: {get_env_or_default('MAX_RISK_PCT', DEFAULT_MAX_RISK_PCT)}%)")

        allowance = usdc.functions.allowance(account.address, contract_address).call() / 1e6
        print(f"Current allowance for Gains contract: {allowance:.2f} USDC")

        if allowance < usd_amount:
            print("USDC allowance too low, re-approving now...")
            try:
                nonce = w3.eth.get_transaction_count(account.address, 'pending')
                base_gas_price = w3.eth.gas_price
                
                # More aggressive gas price for Base network
                gas_price = int(base_gas_price * 1.2)
                
                # Higher approval amount to avoid frequent re-approvals
                approval_amount = int(10_000 * 1e6)  # 10,000 USDC

                tx = usdc.functions.approve(contract_address, approval_amount).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gasPrice': gas_price,
                })
                
                # Estimate gas instead of hardcoding
                try:
                    gas_estimate = w3.eth.estimate_gas(tx)
                    tx['gas'] = int(gas_estimate * 1.2)  # Add 20% buffer
                except Exception as gas_err:
                    print(f"Gas estimation failed: {str(gas_err)}")
                    tx['gas'] = 150000  # Fallback gas limit
                
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                print(f"Approval TX sent: {tx_hash.hex()}")

                # Wait with timeout for approval transaction
                for _ in range(30):  # 30 * 3s = 90s timeout
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx_hash)
                        if receipt is not None:
                            if receipt.status != 1:
                                raise Exception(f"USDC approval transaction failed with status: {receipt.status}")
                            print("USDC approval confirmed on-chain")
                            break
                    except Exception as e:
                        if "not found" not in str(e).lower():
                            raise
                    time.sleep(3)
                else:
                    raise TimeoutError("Approval transaction not confirmed after 90 seconds")
                
                # Additional wait time after confirmed approval
                time.sleep(5)

            except Exception as e:
                print("Approval error:", str(e))
                print(traceback.format_exc())
                return {"status": "error", "message": f"USDC approval failed: {str(e)}", "trace": traceback.format_exc()}

        # Parse signal data with validation
        try:
            is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
            entry_price = float(signal.get("Entry Price", 0))
            if entry_price <= 0:
                raise ValueError(f"Invalid entry price: {signal.get('Entry Price')}")
                
            symbol = signal.get("Coin", "").strip().upper()
            pair_index = PAIR_INDEX_MAP.get(symbol, 0)
            
            if pair_index == 0:
                raise ValueError(f"Unsupported or missing symbol in signal: '{symbol}'")
        except (ValueError, TypeError) as e:
            print(f"Signal parsing error: {str(e)}")
            return {"status": "error", "message": f"Failed to parse signal data: {str(e)}"}

        leverage = int(get_env_or_default("LEVERAGE", DEFAULT_LEVERAGE))
        print(f"Using leverage: {leverage}x")
        
        notional_value = usd_amount * leverage
        min_required = MIN_NOTIONAL_PER_PAIR.get(symbol, 50)

        if notional_value < min_required:
            print(f"Skipping trade: Notional value ${notional_value:.2f} is below Gains minimum of ${min_required} for {symbol}")
            return {
                "status": "SKIPPED",
                "reason": f"Notional value ${notional_value:.2f} too low for {symbol}"
            }

        if usd_amount < 5:
            print(f"Skipping trade: position size ${usd_amount:.2f} is below $5 minimum.")
            return {"status": "SKIPPED", "reason": f"Trade size ${usd_amount:.2f} below $5 minimum"}

        position_size = int(usd_amount * 1e6)
        print(f"Position size: ${usd_amount:.2f} USD ({position_size} tokens)")

        # Calculate slippage based on volatility of the asset
        slippage = 50 if symbol in ["BTC", "ETH"] else 100  # 0.5% for majors, 1% for others
        print(f"Using slippage: {slippage/10}%")

        try:
            # FINAL FIELD NAMES BASED ON ERROR MESSAGES
            # Update with all field names we've discovered
            trade_struct = {
                'user': Web3.to_checksum_address(account.address),
                'index': pair_index,            # First attempt
                'pairIndex': pair_index,        # Second attempt
                'leverage': leverage, 
                'margin': position_size,
                'long': is_long,                # Changed from 'isLong' to 'long' based on latest error
                'isLong': is_long,              # Keep this as fallback
                'referral': True,
                'mode': 1,
                'tp': 0,
                'sl': 0,
                'priceLimit': 0,
                'deadline': int(time.time()) + 300,
                'extra': 0
            }
            
            # Get nonce and gas price
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = int(w3.eth.gas_price * 1.3)  # 30% higher for Base
            
            try:
                # First try with the combined struct
                print(f"Attempting trade with combined struct: {json.dumps(trade_struct, default=str)}")
                txn = contract.functions.openTrade(
                    trade_struct,         # Dict with both field names
                    slippage,             # Slippage tolerance
                    account.address       # Callback address
                ).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gasPrice': gas_price,
                    'value': 0
                })
                
                # Add a generous gas limit
                txn['gas'] = 500000
                
                # Sign and send
                signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                
            except Exception as struct_error:
                print(f"Dict approach failed: {str(struct_error)}")
                
                # Fallback to tuple approach with 13 elements
                # Updated to include all 13 expected elements
                trade_tuple = (
                    Web3.to_checksum_address(account.address),
                    pair_index,
                    leverage,
                    position_size,
                    is_long,
                    True,   # referral
                    1,      # mode
                    0,      # tp
                    0,      # sl
                    0,      # priceLimit
                    int(time.time()) + 300,  # deadline
                    0,      # extra (1)
                    0       # extra (2) - Add this missing 13th element
                )
                
                print(f"Attempting trade with tuple approach")
                txn = contract.functions.openTrade(
                    trade_tuple,
                    slippage,
                    account.address
                ).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gasPrice': gas_price,
                    'value': 0
                })
                
                # Add a generous gas limit
                txn['gas'] = 500000
                
                # Sign and send
                signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            
            print(f"Trade sent! TX hash: {tx_hash.hex()}")
            
            # Create trade info for monitoring
            trade_info = {
                "tx_hash": tx_hash.hex(),
                "symbol": symbol,
                "entry_price": entry_price,
                "is_long": is_long,
                "position_size_usd": usd_amount,
                "leverage": leverage,
                "stop_loss": signal.get("Stop-Loss"),
                "tp1": signal.get("TP1"),
                "tp2": signal.get("TP2"),
                "tp3": signal.get("TP3"),
                "position_id": None  # Will be populated later when we get position details
            }
            
            # Store in active_trades
            active_trades[symbol] = trade_info
            
            # Start position monitor in a separate thread
            monitor_thread = threading.Thread(target=position_monitor, args=(trade_info,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
            return {
                "status": "TRADE SENT",
                "tx_hash": tx_hash.hex(),
                "entry_price": entry_price,
                "stop_loss": signal.get("Stop-Loss"),
                "tp1": signal.get("TP1"),
                "tp2": signal.get("TP2"),
                "tp3": signal.get("TP3"),
                "position_size_usd": usd_amount,
                "position_size_token": round(usd_amount / entry_price, 4),
                "log_link": f"https://basescan.org/tx/{tx_hash.hex()}"
            }
            
        except Exception as tx_error:
            # More specific error handling for transaction failures
            error_msg = str(tx_error)
            print(f"Detailed error: {error_msg}")
            
            # If we get a specific field name error, try to add that field
            if "KeyError:" in error_msg:
                try:
                    missing_field = error_msg.split("KeyError: '")[1].split("'")[0]
                    print(f"Missing field detected: '{missing_field}'")
                    
                    # Log this for future fixes
                    print(f"Please add '{missing_field}' to the trade_struct dictionary!")
                except:
                    pass
            
            # Check for common error patterns
            if "gas required exceeds allowance" in error_msg:
                suggested_fix = "Increase gas limit or optimize contract call"
            elif "insufficient funds" in error_msg:
                suggested_fix = "Check BASE native token balance for gas fees"
            elif "nonce too low" in error_msg:
                suggested_fix = "Nonce issue - try resetting transaction count"
            elif "execution reverted" in error_msg:
                suggested_fix = "Contract execution failed - check parameters and trade conditions"
            elif "ABI Not Found" in error_msg or "MismatchedABI" in error_msg:
                suggested_fix = "Trade parameters format mismatch - check contract ABI definition"
            else:
                suggested_fix = "Review transaction parameters and contract requirements"
                
            return {
                "status": "error",
                "message": f"Transaction failed: {error_msg}",
                "suggested_fix": suggested_fix,
                "trace": traceback.format_exc()
            }
            
    except Exception as e:
        print("ERROR: An exception occurred during trade execution")
        print("Error details:", str(e))
        print("Traceback:\n", traceback.format_exc())
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}


def start_bot():
    """
    Main function to start the trading bot
    """
    print("="*80)
    print("🚀 Professional Crypto Trading Bot with Risk Management Started 🚀")
    print("="*80)
    print(f"• Max Risk: {get_env_or_default('MAX_RISK_PCT', DEFAULT_MAX_RISK_PCT)}%")
    print(f"• Leverage: {get_env_or_default('LEVERAGE', DEFAULT_LEVERAGE)}x")
    print(f"• Take Profit Levels: TP1={DEFAULT_TP_LEVELS['TP1']}%, TP2={DEFAULT_TP_LEVELS['TP2']}%, TP3={DEFAULT_TP_LEVELS['TP3']}%")
    print(f"• Take Profit Distribution: TP1={TP_CLOSE_PERCENTAGES['TP1']}%, TP2={TP_CLOSE_PERCENTAGES['TP2']}%, TP3={TP_CLOSE_PERCENTAGES['TP3']}%")
    print(f"• Default Initial Stop Loss: 1.5-2.0% (asset dependent)")
    print(f"• Trailing Stop: 0.5% trail distance")
    print("="*80)
    
    # You would add your signal receiver logic here
    # This could be a REST API endpoint, websocket connection, etc.
    
    # For example:
    # start_signal_receiver()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
            active_positions = len(active_trades)
            if active_positions > 0:
                print(f"Currently monitoring {active_positions} active positions: {list(active_trades.keys())}")
    except KeyboardInterrupt:
        print("Bot shutdown requested. Closing all positions...")
        # Close all active positions on shutdown
        for symbol, trade_info in active_trades.items():
            try:
                close_position(trade_info, 100, reason="Bot Shutdown")
            except Exception as e:
                print(f"Error closing position for {symbol}: {str(e)}")
        print("Bot shutdown complete")


if __name__ == "__main__":
    # Start the bot if this file is run directly
    start_bot()
