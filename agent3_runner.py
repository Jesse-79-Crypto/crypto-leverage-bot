import json
import time
import logging
import os
from web3 import Web3
from web3.middleware import geth_poa_middleware
from decimal import Decimal
import datetime
import sys

# Import from your existing variables file
from my_variables import PRIVATE_KEY, WALLET_ADDRESS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GainsTrader")

# Configuration
class Config:
    # Network settings
    BASE_RPC_URL = "https://mainnet.base.org"
    CHAIN_ID = 8453  # Base Mainnet
    
    # Contract addresses
    TRADING_CONTRACT_ADDRESS = "0xd8D177EFc926A18EE455da6F5f6A6CfCeE5F8f58"  # Verify this on Base!
    DAI_CONTRACT_ADDRESS = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"  # Verify this on Base!
    
    # Gas settings
    GAS_LIMIT = 500000
    GAS_PRICE_BUFFER = 1.2  # 20% buffer
    
    # Trading parameters
    DEFAULT_SLIPPAGE = 0.5  # 0.5%
    DEFAULT_LEVERAGE = 50
    
    # Timeouts
    TRANSACTION_TIMEOUT = 300  # seconds
    RETRY_DELAY = 5  # seconds
    MAX_RETRIES = 3

class TradingPair:
    # Common trading pairs (index values may differ on Base)
    BTC_USD = 0
    ETH_USD = 1
    BNB_USD = 2
    SOL_USD = 3
    XRP_USD = 4
    ADA_USD = 5
    # Add more pairs as needed

class TradeType:
    MARKET = 2
    LIMIT = 3
    # Add more types as needed

class TradeDirection:
    LONG = True
    SHORT = False

class GainsTrader:
    def __init__(self):
        self.config = Config()
        self.connect_to_network()
        self.load_contracts()
    
    def connect_to_network(self):
        """Connect to the Base network"""
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.config.BASE_RPC_URL))
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            if not self.web3.is_connected():
                raise Exception("Failed to connect to Base network")
                
            logger.info(f"Connected to Base network - Block: {self.web3.eth.block_number}")
        except Exception as e:
            logger.error(f"Network connection error: {str(e)}")
            raise
    
    def load_contracts(self):
        """Load contract ABIs and create contract objects"""
        try:
            # Load Trading contract ABI
            with open('trading_abi.json', 'r') as f:
                trading_abi = json.load(f)
            
            # Load DAI token ABI (ERC20 standard)
            with open('erc20_abi.json', 'r') as f:
                dai_abi = json.load(f)
            
            # Create contract objects
            self.trading_contract = self.web3.eth.contract(
                address=self.config.TRADING_CONTRACT_ADDRESS, 
                abi=trading_abi
            )
            
            self.dai_contract = self.web3.eth.contract(
                address=self.config.DAI_CONTRACT_ADDRESS,
                abi=dai_abi
            )
            
            logger.info("Contract ABIs loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load contracts: {str(e)}")
            raise
    
    def get_current_gas_price(self):
        """Get current gas price with buffer"""
        gas_price = self.web3.eth.gas_price
        return int(gas_price * self.config.GAS_PRICE_BUFFER)
    
    def get_dai_balance(self):
        """Get DAI balance for the wallet"""
        try:
            balance_wei = self.dai_contract.functions.balanceOf(WALLET_ADDRESS).call()
            balance_dai = self.web3.from_wei(balance_wei, 'ether')
            logger.info(f"Current DAI balance: {balance_dai}")
            return balance_dai
        except Exception as e:
            logger.error(f"Failed to get DAI balance: {str(e)}")
            return 0
    
    def approve_dai_spending(self, amount_dai):
        """Approve the trading contract to spend DAI"""
        try:
            # Convert DAI to wei
            amount_wei = self.web3.to_wei(amount_dai, 'ether')
            
            # Get current allowance
            current_allowance = self.dai_contract.functions.allowance(
                WALLET_ADDRESS, 
                self.config.TRADING_CONTRACT_ADDRESS
            ).call()
            
            if current_allowance >= amount_wei:
                logger.info(f"Spending of {amount_dai} DAI already approved")
                return True
            
            # Prepare approval transaction
            nonce = self.web3.eth.get_transaction_count(WALLET_ADDRESS)
            txn = self.dai_contract.functions.approve(
                self.config.TRADING_CONTRACT_ADDRESS,
                amount_wei
            ).build_transaction({
                'chainId': self.config.CHAIN_ID,
                'gas': 100000,  # Lower gas for approval
                'gasPrice': self.get_current_gas_price(),
                'nonce': nonce,
            })
            
            # Sign and send transaction
            signed_txn = self.web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            logger.info(f"DAI approval sent: {self.web3.to_hex(tx_hash)}")
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, self.config.TRANSACTION_TIMEOUT)
            
            if receipt.status == 1:
                logger.info(f"DAI approval confirmed!")
                return True
            else:
                logger.error("DAI approval failed!")
                return False
                
        except Exception as e:
            logger.error(f"DAI approval error: {str(e)}")
            return False
    
    def get_open_trades(self, pair_index=None):
        """Get current open trades for the wallet"""
        try:
            # This function requires knowing the specific contract calls
            # Modify based on the actual contract function to get open trades
            if pair_index is not None:
                count = self.trading_contract.functions.openTradesCount(WALLET_ADDRESS, pair_index).call()
                logger.info(f"Open trades for pair {pair_index}: {count}")
            else:
                # Loop through common pairs to get total count
                total = 0
                for i in range(10):  # Assuming 10 pairs max
                    try:
                        count = self.trading_contract.functions.openTradesCount(WALLET_ADDRESS, i).call()
                        total += count
                    except:
                        pass
                logger.info(f"Total open trades: {total}")
                return total
        except Exception as e:
            logger.error(f"Failed to get open trades: {str(e)}")
            return 0
    
    def open_trade(self, pair_index, is_long, position_size_dai, leverage=None, 
                   take_profit=0, stop_loss=0, slippage=None):
        """
        Open a new trade on Gains.io
        
        Args:
            pair_index (int): Index of the trading pair
            is_long (bool): True for long, False for short
            position_size_dai (float): Size of position in DAI
            leverage (int, optional): Leverage multiplier. Defaults to Config.DEFAULT_LEVERAGE.
            take_profit (int, optional): Take profit price. Defaults to 0 (none).
            stop_loss (int, optional): Stop loss price. Defaults to 0 (none).
            slippage (float, optional): Max slippage percentage. Defaults to Config.DEFAULT_SLIPPAGE.
        
        Returns:
            dict: Transaction result
        """
        if leverage is None:
            leverage = self.config.DEFAULT_LEVERAGE
            
        if slippage is None:
            slippage = self.config.DEFAULT_SLIPPAGE
            
        # First approve DAI spending if needed
        if not self.approve_dai_spending(position_size_dai):
            return {'status': 'error', 'message': 'Failed to approve DAI spending'}
            
        for attempt in range(self.config.MAX_RETRIES):
            try:
                # Define trade parameters properly as a tuple
                # This follows the struct format required by the contract:
                # (address,uint32,uint16,uint24,bool,bool,uint8,uint8,uint120,uint64,uint64,uint64,uint192)
                trade_params = (
                    WALLET_ADDRESS,       # address - trader address
                    TradeType.MARKET,     # uint32 - trade type (2 for market order)
                    pair_index,           # uint16 - pair index (e.g., ETH/USD)
                    int(slippage * 100),  # uint24 - slippage threshold in basis points
                    is_long,              # bool - position direction (True=long, False=short)
                    False,                # bool - reduce only flag
                    0,                    # uint8 - parameter 1
                    0,                    # uint8 - parameter 2
                    int(position_size_dai * 10**18),  # uint120 - position size in DAI (with 18 decimals)
                    take_profit,          # uint64 - take profit price
                    stop_loss,            # uint64 - stop loss price
                    0,                    # uint64 - trailing stop value
                    int(time.time() + 3600),  # uint192 - deadline (1 hour from now)
                )

                # Get current gas price and nonce
                gas_price = self.get_current_gas_price()
                nonce = self.web3.eth.get_transaction_count(WALLET_ADDRESS)
                
                # Build transaction
                txn = self.trading_contract.functions.openTrade(
                    trade_params,  # Structured tuple of trade parameters
                    leverage,      # Leverage amount
                    WALLET_ADDRESS # Referrer address (self-referral)
                ).build_transaction({
                    'chainId': self.config.CHAIN_ID,
                    'gas': self.config.GAS_LIMIT,
                    'gasPrice': gas_price,
                    'nonce': nonce,
                })
                
                # Sign transaction
                signed_txn = self.web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
                
                # Send transaction
                tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
                tx_hash_hex = self.web3.to_hex(tx_hash)
                logger.info(f"Trade transaction sent: {tx_hash_hex}")
                
                # Wait for transaction receipt
                logger.info("Waiting for transaction confirmation...")
                tx_receipt = self.web3.eth.wait_for_transaction_receipt(
                    tx_hash, 
                    timeout=self.config.TRANSACTION_TIMEOUT
                )
                
                if tx_receipt.status == 1:
                    logger.info(f"✅ Trade executed successfully!")
                    return {
                        'status': 'success', 
                        'tx_hash': tx_hash_hex,
                        'receipt': tx_receipt
                    }
                else:
                    logger.error(f"❌ Transaction failed on-chain")
                    return {
                        'status': 'error', 
                        'message': 'Transaction reverted on-chain',
                        'tx_hash': tx_hash_hex
                    }
                    
            except Exception as e:
                logger.error(f"❌ Attempt {attempt+1} failed: {str(e)}")
                if attempt < self.config.MAX_RETRIES - 1:
                    logger.info(f"Retrying in {self.config.RETRY_DELAY} seconds...")
                    time.sleep(self.config.RETRY_DELAY)
                else:
                    return {
                        'status': 'error', 
                        'message': f"Failed after {self.config.MAX_RETRIES} attempts: {str(e)}"
                    }
    
    def close_trade(self, pair_index, trade_index):
        """Close an existing trade"""
        try:
            # Build transaction to close the trade
            # You'll need to check the actual method in the contract for closing trades
            nonce = self.web3.eth.get_transaction_count(WALLET_ADDRESS)
            
            # This is a placeholder - check actual contract for correct function name
            txn = self.trading_contract.functions.closeTrade(
                pair_index,
                trade_index
            ).build_transaction({
                'chainId': self.config.CHAIN_ID,
                'gas': self.config.GAS_LIMIT,
                'gasPrice': self.get_current_gas_price(),
                'nonce': nonce,
            })
            
            # Sign transaction
            signed_txn = self.web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
            
            # Send transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash_hex = self.web3.to_hex(tx_hash)
            logger.info(f"Close trade transaction sent: {tx_hash_hex}")
            
            # Wait for confirmation
            receipt = self.web3.eth.wait_for_transaction_receipt(
                tx_hash, 
                timeout=self.config.TRANSACTION_TIMEOUT
            )
            
            if receipt.status == 1:
                logger.info(f"✅ Trade closed successfully!")
                return {'status': 'success', 'tx_hash': tx_hash_hex}
            else:
                logger.error(f"❌ Close transaction failed on-chain")
                return {'status': 'error', 'message': 'Transaction reverted on-chain'}
                
        except Exception as e:
            logger.error(f"Failed to close trade: {str(e)}")
            return {'status': 'error', 'message': str(e)}

# Main function to execute trades
def execute_strategy():
    """Main function to execute trading strategy"""
    try:
        # Initialize the trader
        trader = GainsTrader()
        
        # Check DAI balance
        dai_balance = trader.get_dai_balance()
        if dai_balance < 10:  # Minimum 10 DAI required
            logger.error(f"Insufficient DAI balance: {dai_balance}")
            return
            
        # Check existing open trades
        open_trades = trader.get_open_trades()
        logger.info(f"Current open trades: {open_trades}")
        
        # Example: Open a long trade on ETH/USD with 10 DAI at 50x leverage
        # Customize this based on your strategy
        result = trader.open_trade(
            pair_index=TradingPair.ETH_USD,
            is_long=TradeDirection.LONG,
            position_size_dai=10,
            leverage=50,
            take_profit=0,  # No take profit
            stop_loss=0     # No stop loss
        )
        
        logger.info(f"Trade result: {result}")
        
        # You could implement more complex strategies here:
        # - Technical indicators
        # - Market data analysis
        # - Portfolio management
        # - Stop-loss management
        # - etc.
        
    except Exception as e:
        logger.error(f"Strategy execution failed: {str(e)}")

# Run the bot
if __name__ == "__main__":
    logger.info("Starting Gains.io trading bot...")
    execute_strategy()
