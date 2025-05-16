#!/usr/bin/env python3
"""
Gains Network Trading Bot
Enhanced version with improved error handling, reliability, and risk management
"""

import json
import time
import os
import traceback
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from web3 import Web3
from web3.exceptions import TransactionNotFound
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ======== CONFIGURATION ======== #
class Config:
    # Chain and contract configuration
    CHAIN_ID = 8453  # Base chain
    DEFAULT_RPC_URL = "https://mainnet.base.org"  # Fallback RPC
    USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
    GAINS_CONTRACT_ADDRESS = "0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac"  # Base Gains
    
    # Trading configuration
    DEFAULT_LEVERAGE = 5  # Conservative leverage
    MAX_SLIPPAGE = 30  # Maximum slippage in basis points (0.3%)
    MAX_RISK_PERCENTAGE = 15  # Max percentage of balance to risk per trade
    GAS_PRICE_MULTIPLIER = 1.1  # Multiplier for gas price
    GAS_LIMIT_TRADE = 350000  # Higher gas limit for trades
    
    # Transaction configuration
    MAX_TX_RETRIES = 3
    RETRY_WAIT_TIME = 5  # seconds
    TX_TIMEOUT = 180  # seconds
    
    # Asset-specific configuration
    PAIR_INDEX_MAP = {
        "BTC": 0,
        "ETH": 1,
        "LINK": 2,
        "DOGE": 3,
        "ADA": 5,
        "AAVE": 7,
        "ALGO": 8,
        "BAT": 9,
        "COMP": 10,
        "DOT": 11,
        "EOS": 12
    }
    
    # Minimum position sizes for different assets (collateral × leverage)
    MIN_POSITION_SIZE = {
        "BTC": 300,  # Increased from your 100
        "ETH": 250,  # Increased from your 75
        "LINK": 150,
        "DOGE": 150,
        "ADA": 150,
        "AAVE": 150,
        "ALGO": 150,
        "BAT": 150,
        "COMP": 150,
        "DOT": 150,
        "EOS": 150,
        "DEFAULT": 150  # Default for any pair not explicitly listed
    }
    
    # Collateral token index in Gains Network (USDC = 0 on Base)
    COLLATERAL_INDEX = 0  # USDC on Base

# ======== LOGGING SETUP ======== #
def setup_logging():
    """Set up structured logging to file and console"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f"trading_bot_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("trading_bot")

logger = setup_logging()

# ======== WEB3 CONNECTION ======== #
class Web3Connection:
    def __init__(self):
        self.w3 = None
        self.connect()
    
    def connect(self):
        """Establish connection to the blockchain with fallback options"""
        rpc_urls = [
            os.environ.get("BASE_RPC_URL"),
            Config.DEFAULT_RPC_URL,
            "https://base-mainnet.g.alchemy.com/v2/demo",  # Public Alchemy endpoint
            "https://base-mainnet.public.blastapi.io"  # Public Blast API endpoint
        ]
        
        for url in rpc_urls:
            if not url:
                continue
            
            try:
                logger.info(f"Attempting to connect to RPC: {url}")
                provider = Web3(Web3.HTTPProvider(url))
                if provider.is_connected():
                    self.w3 = provider
                    logger.info("Successfully connected to RPC")
                    return
            except Exception as e:
                logger.error(f"Failed to connect to {url}: {str(e)}")
        
        raise ConnectionError("Failed to connect to any RPC endpoint")
    
    def ensure_connected(self):
        """Ensure we are connected to the blockchain"""
        if not self.w3 or not self.w3.is_connected():
            logger.warning("Lost connection to RPC. Reconnecting...")
            self.connect()
        return self.w3

# ======== CONTRACT INTERACTIONS ======== #
class ContractManager:
    def __init__(self, web3_conn: Web3Connection, private_key: str):
        self.web3_conn = web3_conn
        self.private_key = private_key
        self.account = web3_conn.w3.eth.account.from_key(private_key)
        self.wallet_address = self.account.address
        
        # Load contract ABIs
        self.usdc_contract = None
        self.gains_contract = None
        self.load_contracts()
    
    def load_contracts(self):
        """Load contract ABIs and create contract objects"""
        # Load USDC contract
        erc20_abi = self.load_abi("abi/erc20_abi.json") or self.get_default_erc20_abi()
        self.usdc_contract = self.web3_conn.w3.eth.contract(
            address=Web3.to_checksum_address(Config.USDC_ADDRESS),
            abi=erc20_abi
        )
        
        # Load Gains Network contract
        try:
            gains_abi = self.load_abi("abi/gains_base_abi.json")
            self.gains_contract = self.web3_conn.w3.eth.contract(
                address=Web3.to_checksum_address(Config.GAINS_CONTRACT_ADDRESS),
                abi=gains_abi
            )
        except Exception as e:
            logger.error(f"Failed to load Gains contract: {str(e)}")
            raise
    
    def load_abi(self, file_path: str) -> List:
        """Load ABI from file"""
        try:
            with open(file_path, "r") as abi_file:
                return json.load(abi_file)
        except Exception as e:
            logger.error(f"Failed to load ABI from {file_path}: {str(e)}")
            return None
    
    def get_default_erc20_abi(self) -> List:
        """Return default ERC20 ABI in case file loading fails"""
        return [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "remaining", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            }
        ]
    
    def get_usdc_balance(self) -> float:
        """Get USDC balance in human-readable format"""
        balance_wei = self.usdc_contract.functions.balanceOf(self.wallet_address).call()
        return balance_wei / 1e6  # USDC has 6 decimals
    
    def check_and_approve_usdc(self, amount_usdc: float) -> bool:
        """Check USDC allowance and approve if needed"""
        w3 = self.web3_conn.ensure_connected()
        
        # Convert to USDC units (6 decimals)
        amount_units = int(amount_usdc * 1e6)
        
        # Ensure contract address is checksummed
        gains_address = Web3.to_checksum_address(Config.GAINS_CONTRACT_ADDRESS)
        
        try:
            # Check current allowance
            current_allowance = self.usdc_contract.functions.allowance(
                self.wallet_address, 
                gains_address
            ).call()
            
            if current_allowance >= amount_units:
                logger.info(f"USDC already approved: {current_allowance / 1e6} USDC")
                return True
            
            # Need to approve
            logger.info(f"Approving USDC: {amount_usdc} USDC")
            
            # Using max uint256 for unlimited approval
            approve_tx = self.usdc_contract.functions.approve(
                gains_address,
                2**256 - 1  # Max approval
            ).build_transaction({
                'from': self.wallet_address,
                'nonce': w3.eth.get_transaction_count(self.wallet_address),
                'gas': 100000,
                'gasPrice': self.get_optimal_gas_price(),
                'chainId': Config.CHAIN_ID
            })
            
            tx_hash = self.send_transaction(approve_tx)
            receipt, success = self.wait_for_transaction(tx_hash)
            
            if success:
                logger.info("USDC approval successful")
                return True
            else:
                logger.error("USDC approval failed")
                return False
            
        except Exception as e:
            logger.error(f"Error in USDC approval: {str(e)}")
            return False
    
    def send_transaction(self, transaction):
        """Send transaction with retry logic"""
        w3 = self.web3_conn.ensure_connected()
        
        for attempt in range(Config.MAX_TX_RETRIES):
            try:
                signed_txn = w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                logger.info(f"Transaction sent: {tx_hash.hex()}")
                return tx_hash
            except Exception as e:
                if attempt == Config.MAX_TX_RETRIES - 1:
                    logger.error(f"Transaction failed after {Config.MAX_TX_RETRIES} attempts: {str(e)}")
                    raise
                    
                logger.warning(f"Transaction attempt {attempt+1} failed: {str(e)}. Retrying in {Config.RETRY_WAIT_TIME}s...")
                time.sleep(Config.RETRY_WAIT_TIME)
    
    def wait_for_transaction(self, tx_hash, timeout=Config.TX_TIMEOUT):
        """Wait for transaction confirmation with timeout"""
        w3 = self.web3_conn.ensure_connected()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    if receipt.status == 1:
                        logger.info(f"Transaction {tx_hash.hex()} confirmed successfully")
                        return receipt, True
                    else:
                        logger.error(f"Transaction {tx_hash.hex()} failed on-chain")
                        return receipt, False
            except TransactionNotFound:
                pass  # Transaction still pending
            except Exception as e:
                logger.error(f"Error checking transaction status: {str(e)}")
            
            # Still waiting
            if (time.time() - start_time) % 15 < 1:  # Log every ~15 seconds
                logger.info(f"Waiting for transaction {tx_hash.hex()} to be mined...")
            
            time.sleep(3)
        
        logger.error(f"Transaction {tx_hash.hex()} timed out after {timeout} seconds")
        return None, False
    
    def get_optimal_gas_price(self):
        """Calculate optimal gas price based on network conditions"""
        w3 = self.web3_conn.ensure_connected()
        base_gas_price = w3.eth.gas_price
        return int(base_gas_price * Config.GAS_PRICE_MULTIPLIER)

# ======== TRADING LOGIC ======== #
class TradingStrategy:
    def __init__(self, contract_manager: ContractManager):
        self.contract_manager = contract_manager
    
    def calculate_position_size(self, symbol: str, entry_price: float) -> Tuple[float, int]:
        """
        Calculate optimal position size with fixed leverage
        Returns: (collateral_amount, leverage)
        """
        # Get available balance
        available_balance = self.contract_manager.get_usdc_balance()
        logger.info(f"Available USDC balance: {available_balance}")
        
        # Fix leverage at 5x as per user preference
        leverage = Config.DEFAULT_LEVERAGE  # This should be set to 5
        
        # Get minimum position size for the asset
        min_position_size = Config.MIN_POSITION_SIZE.get(symbol, Config.MIN_POSITION_SIZE["DEFAULT"])
        
        # Calculate minimum collateral needed at 5x leverage
        min_collateral_needed = min_position_size / leverage
        logger.info(f"Minimum collateral needed for {symbol} at {leverage}x leverage: {min_collateral_needed:.2f} USDC")
        
        # First check if we can meet minimum requirements
        if available_balance < min_collateral_needed:
            logger.error(f"Insufficient balance ({available_balance:.2f} USDC) to meet minimum position size ({min_position_size:.2f} USDC) at {leverage}x leverage")
            logger.error(f"Need at least {min_collateral_needed:.2f} USDC collateral")
            return 0, leverage  # Will trigger error in calling function
        
        # Calculate amount based on risk percentage
        max_risk_amount = available_balance * (Config.MAX_RISK_PERCENTAGE / 100)
        
        # If max risk amount is less than minimum needed, use minimum needed instead
        if max_risk_amount < min_collateral_needed:
            logger.info(f"Risk limit ({max_risk_amount:.2f} USDC) is below minimum requirement, using minimum required collateral: {min_collateral_needed:.2f} USDC")
            collateral_amount = min_collateral_needed
        else:
            collateral_amount = max_risk_amount
            logger.info(f"Using risk-based collateral: {collateral_amount:.2f} USDC")
        
        # Round collateral to 2 decimals (USDC precision)
        collateral_amount = round(collateral_amount, 2)
        
        # Final position size check (should always pass with this logic)
        position_size = collateral_amount * leverage
        logger.info(f"Final position size: {collateral_amount:.2f} USDC with {leverage}x leverage = {position_size:.2f} notional")
        
        return collateral_amount, leverage

# ======== TRADE EXECUTION ======== #
class TradeExecutor:
    def __init__(self, contract_manager: ContractManager, strategy: TradingStrategy):
        self.contract_manager = contract_manager
        self.strategy = strategy
    
    def execute_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a trade based on the given signal
        Signal format: {
            "Coin": "ETH",
            "Trade Direction": "LONG" or "SHORT",
            "Entry Price": 2585.03,
            "Stop-Loss": 2550.65,
            "TP1": 2662.58,
            "TP2": 2740.14,
            "TP3": 2843.54
        }
        """
        logger.info(f"Processing trade signal: {json.dumps(signal, indent=2)}")
        
        try:
            # Extract signal parameters
            symbol = signal.get("Coin", "").strip().upper()
            is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
            entry_price = float(signal.get("Entry Price", 0))
            stop_loss = float(signal.get("Stop-Loss", 0))
            tp1 = float(signal.get("TP1", 0))
            tp2 = float(signal.get("TP2", 0)) if "TP2" in signal else 0
            tp3 = float(signal.get("TP3", 0)) if "TP3" in signal else 0
            
            # Validate signal
            if not self._validate_signal(symbol, entry_price, stop_loss, tp1):
                return {"status": "error", "message": "Invalid signal parameters"}
            
            # Get pair index
            pair_index = Config.PAIR_INDEX_MAP.get(symbol)
            if pair_index is None:
                logger.error(f"Unsupported trading pair: {symbol}")
                return {"status": "error", "message": f"Unsupported trading pair: {symbol}"}
            
            # Calculate position size and leverage
            collateral_amount, leverage = self.strategy.calculate_position_size(symbol, entry_price)
            
            if collateral_amount <= 0:
                return {
                    "status": "error", 
                    "message": f"Calculated position size too small for {symbol}"
                }
            
            # Ensure USDC is approved
            if not self.contract_manager.check_and_approve_usdc(collateral_amount):
                return {"status": "error", "message": "Failed to approve USDC"}
            
            # Execute the trade
            return self._send_trade_to_chain(
                symbol=symbol,
                pair_index=pair_index,
                is_long=is_long,
                leverage=leverage,
                collateral_amount=collateral_amount,
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1,
                signal=signal  # Pass the full signal for TP2/TP3 access
            )
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    
    def _validate_signal(self, symbol, entry_price, stop_loss, tp1) -> bool:
        """Validate trade signal parameters"""
        if not symbol or symbol not in Config.PAIR_INDEX_MAP:
            logger.error(f"Invalid symbol: {symbol}")
            return False
        
        if entry_price <= 0 or stop_loss <= 0 or tp1 <= 0:
            logger.error(f"Invalid price parameters: entry={entry_price}, sl={stop_loss}, tp={tp1}")
            return False
        
        return True
    
    def _send_trade_to_chain(self, symbol, pair_index, is_long, leverage, 
                           collateral_amount, entry_price, stop_loss, tp1, signal=None) -> Dict[str, Any]:
        """Send the trade to the blockchain"""
        w3 = self.contract_manager.web3_conn.ensure_connected()
        
        try:
            # Convert USDC amount to units (6 decimals)
            collateral_units = int(collateral_amount * 1e6)
            
            # Convert price values to oracle format (8 decimals)
            tp_price_oracle = int(tp1 * 1e8)
            sl_price_oracle = int(stop_loss * 1e8)
            
            # Create trade struct
            trade_struct = (
                self.contract_manager.wallet_address,  # user
                0,                          # index (always 0 for new trades)
                pair_index,                 # pairIndex
                leverage,                   # leverage 
                is_long,                    # isLong
                True,                       # isOpen (always True for opening trades)
                Config.COLLATERAL_INDEX,    # collateralIndex (0 = USDC on Base)
                0,                          # tradeType (0 = Market order)
                collateral_units,           # collateralAmount (in USDC units)
                0,                          # openPrice (0 for market orders)
                tp_price_oracle,            # tp (take profit price)
                sl_price_oracle,            # sl (stop loss price)
                0                           # _placeholder
            )
            
            logger.info(f"Preparing trade: {symbol} {'LONG' if is_long else 'SHORT'} {leverage}x")
            logger.info(f"Position size: {collateral_amount} USDC (notional: {collateral_amount * leverage} USD)")
            
            # Build transaction
            tx = self.contract_manager.gains_contract.functions.openTrade(
                trade_struct,
                Config.MAX_SLIPPAGE,        # Max slippage in basis points 
                self.contract_manager.wallet_address  # Referrer
            ).build_transaction({
                'from': self.contract_manager.wallet_address,
                'nonce': w3.eth.get_transaction_count(self.contract_manager.wallet_address, 'pending'),
                'gas': Config.GAS_LIMIT_TRADE,
                'gasPrice': self.contract_manager.get_optimal_gas_price(),
                'chainId': Config.CHAIN_ID,
                'value': 0
            })
            
            # Send transaction
            tx_hash = self.contract_manager.send_transaction(tx)
            
            # Log trade immediately after sending
            logger.info(f"Trade submitted: {tx_hash.hex()}")
            
            # Return trade details immediately without waiting for confirmation
            position_size_token = round(collateral_amount * leverage / entry_price, 4)
            
            # Get TP2/TP3 values from signal if available, otherwise use defaults
            tp2 = signal.get("TP2", tp1 * 1.05) if signal else tp1 * 1.05
            tp3 = signal.get("TP3", tp1 * 1.10) if signal else tp1 * 1.10
            
            # Create BaseScan URL for transaction
            base_scan_url = f"https://basescan.org/tx/{tx_hash.hex()}"
            logger.info(f"Transaction can be viewed at: {base_scan_url}")
            
            return {
                "status": "TRADE SENT",
                "tx_hash": tx_hash.hex(),
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "position_size_usd": collateral_amount,
                "position_size_token": position_size_token,
                "leverage": leverage,
                "log_link": base_scan_url
            }
            
        except Exception as e:
            logger.error(f"Error sending trade to chain: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

# ======== LOGGING AND TRACKING ======== #
class TradeLogger:
    def __init__(self):
        self.sheet_id = os.getenv("TRADE_LOG_SHEET_ID")
        self.tab_name = os.getenv("TRADE_LOG_TAB_NAME", "Trades")
    
    def log_trade_to_sheet(self, data: Dict[str, Any]) -> bool:
        """Log trade to Google Sheet"""
        if not self.sheet_id:
            logger.warning("Google Sheet ID not provided. Skipping trade logging.")
            return False
        
        try:
            # Create Google Sheets credentials
            creds_json = {
                "type": "service_account",
                "project_id": os.getenv("GOOGLE_PROJECT_ID"),
                "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
                "private_key": os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n"),
                "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "auth_uri": os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri": os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL", 
                                                         "https://www.googleapis.com/oauth2/v1/certs"),
                "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
            }
            
            creds = service_account.Credentials.from_service_account_info(
                creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            
            service = build("sheets", "v4", credentials=creds)
            sheet = service.spreadsheets()
            
            # Format row for sheet
            row = [
                datetime.utcnow().isoformat(),  # Timestamp
                data.get("symbol", ""),
                data.get("direction", ""),
                data.get("entry_price", ""),
                data.get("stop_loss", ""),
                data.get("tp1", ""),
                data.get("tp2", ""),
                data.get("tp3", ""),
                data.get("position_size_usd", ""),
                data.get("leverage", ""),
                data.get("position_size_token", ""),
                data.get("tx_hash", ""),
                data.get("log_link", ""),
                data.get("status", "")
            ]
            
            # Append to sheet
            sheet.values().append(
                spreadsheetId=self.sheet_id,
                range=f"{self.tab_name}!A1",
                valueInputOption="RAW",
                body={"values": [row]}
            ).execute()
            
            logger.info("Trade successfully logged to Google Sheet")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log trade to Google Sheet: {str(e)}")
            logger.error(traceback.format_exc())
            return False

# ======== MAIN APPLICATION ======== #
class GainsNetworkBot:
    def __init__(self):
        # Get private key from environment
        self.private_key = os.getenv("WALLET_PRIVATE_KEY")
        if not self.private_key:
            raise ValueError("WALLET_PRIVATE_KEY environment variable not set")
        
        # Initialize components
        self.web3_conn = Web3Connection()
        self.contract_manager = ContractManager(self.web3_conn, self.private_key)
        self.strategy = TradingStrategy(self.contract_manager)
        self.executor = TradeExecutor(self.contract_manager, self.strategy)
        self.logger = TradeLogger()
    
    def process_trade_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Process a trade signal"""
        logger.info(f"Received trade signal for {signal.get('Coin', 'Unknown')} {signal.get('Trade Direction', 'Unknown')}")
        
        # Execute trade
        result = self.executor.execute_trade(signal)
        
        # Log trade
        if result.get("status") == "TRADE SENT":
            log_data = {
                "symbol": signal.get("Coin", ""),
                "direction": signal.get("Trade Direction", ""),
                "entry_price": result.get("entry_price", ""),
                "stop_loss": result.get("stop_loss", ""),
                "tp1": result.get("tp1", ""),
                "tp2": result.get("tp2", ""),
                "tp3": result.get("tp3", ""),
                "position_size_usd": result.get("position_size_usd", ""),
                "leverage": result.get("leverage", ""),
                "position_size_token": result.get("position_size_token", ""),
                "tx_hash": result.get("tx_hash", ""),
                "log_link": result.get("log_link", ""),
                "status": result.get("status", "")
            }
            self.logger.log_trade_to_sheet(log_data)
        
        return result

# ======== SCRIPT EXECUTION AND COMPATIBILITY ======== #
def main():
    """Main entry point for the trading bot"""
    try:
        # Initialize the bot
        bot = GainsNetworkBot()
        
        # Example signal - replace with your actual signal source
        signal = {
            "Coin": "ETH",
            "Trade Direction": "LONG",
            "Entry Price": 2585.037757501186,
            "Stop-Loss": 2550.6567553264204,
            "TP1": 2662.588890226222,
            "TP2": 2740.1400229512574,
            "TP3": 2843.5415332513053
        }
        
        # Process the signal
        result = bot.process_trade_signal(signal)
        
        # Output the result
        logger.info(f"Trade execution result:")
        logger.info(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Bot execution failed: {str(e)}")
        logger.error(traceback.format_exc())
        return 1
    
    return 0

# For backwards compatibility with your existing code
def execute_trade_on_gains(signal):
    """Compatibility wrapper for existing code"""
    print("Incoming signal data:", json.dumps(signal, indent=2))
    print("Trade execution started")

    try:
        # Initialize the bot
        bot = GainsNetworkBot()
        
        # Process the signal
        result = bot.process_trade_signal(signal)
        
        # Output the result
        print(f"✅ Trade execution result:")
        print(json.dumps(result, indent=2))
        
        return result
        
    except Exception as e:
        print("ERROR: An exception occurred during trade execution")
        print("Error details:", str(e))
        print("Traceback:\n", traceback.format_exc())
        return {
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
