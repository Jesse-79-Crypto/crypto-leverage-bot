import json
import time
import os
from web3 import Web3

# Try the new import path first, fallback to the old one if needed
try:
    from web3.middleware.geth import geth_poa_middleware
except ImportError:
    try:
        # For web3.py v5.x
        from web3.middleware import geth_poa_middleware
    except ImportError:
        # Define a simple version if not available
        def geth_poa_middleware(make_request, web3):
            def middleware(method, params):
                return make_request(method, params)
            return middleware

# Import your variables (assuming this works)
from my_variables import PRIVATE_KEY, WALLET_ADDRESS

# Configuration
BASE_RPC_URL = "https://mainnet.base.org"
TRADING_CONTRACT_ADDRESS = "0xd8D177EFc926A18EE455da6F5f6A6CfCeE5F8f58"  # Verify this on Base
CHAIN_ID = 8453  # Base Mainnet

def execute_trade_on_gains(signal):
    """
    Execute a trade on Gains.io (Base network)
    
    Args:
        signal (dict): Trading signal with parameters
    """
    # Extract parameters from signal
    pair_index = signal.get('pair_index', 5)
    is_long = signal.get('is_long', True)
    position_size_dai = signal.get('position_size', 1)
    
    # Default to 5x leverage as per original requirements
    leverage = signal.get('leverage', 5)
    
    # Take profit settings - original code had 3%, 6%, and 10%
    # Note: Gains.io contract only allows one TP per trade, so we'll use the highest (10%)
    entry_price = signal.get('entry_price', 0)
    if entry_price > 0:
        # Calculate TP based on entry price
        take_profit_percent = 10  # Use 10% as the default TP level
        if is_long:
            take_profit = int(entry_price * (1 + take_profit_percent/100))
        else:
            take_profit = int(entry_price * (1 - take_profit_percent/100))
    else:
        # If no entry price provided, use default
        take_profit = signal.get('take_profit', 0)
    
    # Stop loss settings
    stop_loss = signal.get('stop_loss', 0)
    
    # Trailing stop value - typically a percentage of the position
    trailing_stop = signal.get('trailing_stop', 5)  # Default 5% trailing stop
    
    # Referrer address
    referrer = signal.get('referrer', WALLET_ADDRESS)
        
    try:
        # Connect to Base network
        web3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        
        # Add middleware for PoA chains (like Base)
        try:
            web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except:
            # If middleware injection fails, continue anyway
            print("Warning: Could not inject PoA middleware, but continuing...")
        
        # Check connection
        if not web3.is_connected():
            return {
                'status': 'error', 
                'message': 'Failed to connect to Base network',
                'suggested_fix': 'Check network connection or RPC endpoint'
            }
            
        print(f"Connected to Base network - Block: {web3.eth.block_number}")
        print(f"Trading with: {leverage}x leverage, TP at {take_profit}, SL at {stop_loss}, Trailing stop at {trailing_stop}%")
            
        # Load contract ABI
        try:
            with open('trading_abi.json', 'r') as f:
                contract_abi = json.load(f)
        except FileNotFoundError:
            # Inline minimal ABI if file not found
            contract_abi = [
                {
                    "inputs": [
                        {
                            "components": [
                                {"internalType": "address", "name": "trader", "type": "address"},
                                {"internalType": "uint32", "name": "pairIndex", "type": "uint32"},
                                {"internalType": "uint16", "name": "leverage", "type": "uint16"},
                                {"internalType": "uint24", "name": "openPrice", "type": "uint24"},
                                {"internalType": "bool", "name": "buy", "type": "bool"},
                                {"internalType": "bool", "name": "reduceOnly", "type": "bool"},
                                {"internalType": "uint8", "name": "param1", "type": "uint8"},
                                {"internalType": "uint8", "name": "param2", "type": "uint8"},
                                {"internalType": "uint120", "name": "positionSizeDai", "type": "uint120"},
                                {"internalType": "uint64", "name": "tp", "type": "uint64"},
                                {"internalType": "uint64", "name": "sl", "type": "uint64"},
                                {"internalType": "uint64", "name": "trailingStop", "type": "uint64"},
                                {"internalType": "uint192", "name": "deadline", "type": "uint192"}
                            ],
                            "internalType": "struct StorageInterfaceV5.Trade",
                            "name": "trade",
                            "type": "tuple"
                        },
                        {"internalType": "uint16", "name": "leverage", "type": "uint16"},
                        {"internalType": "address", "name": "referrer", "type": "address"}
                    ],
                    "name": "openTrade",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
        # Load contract
        trading_contract = web3.eth.contract(address=TRADING_CONTRACT_ADDRESS, abi=contract_abi)
        
        # Create the trade parameter struct as a tuple
        trade_struct = (
            WALLET_ADDRESS,       # address - trader address
            pair_index,           # uint32 - pair index
            leverage,             # uint16 - leverage multiplier
            30033138,             # uint24 - price/slippage parameter
            is_long,              # bool - position direction (True=long, False=short)
            False,                # bool - reduce only flag
            0,                    # uint8 - parameter 1
            0,                    # uint8 - parameter 2
            int(position_size_dai * 10**18),  # uint120 - position size in DAI (with 18 decimals)
            take_profit,          # uint64 - take profit price (10% level)
            stop_loss,            # uint64 - stop loss price
            trailing_stop,        # uint64 - trailing stop value
            int(time.time() + 3600),  # uint192 - deadline (1 hour from now)
        )

        # Get current gas price with buffer
        gas_price = web3.eth.gas_price
        gas_price = int(gas_price * 1.2)  # 20% buffer
        
        # Get nonce for the transaction
        nonce = web3.eth.get_transaction_count(WALLET_ADDRESS)
        
        # Build transaction
        txn = trading_contract.functions.openTrade(
            trade_struct,  # Structured tuple of trade parameters 
            leverage,      # Leverage amount
            referrer       # Referrer address
        ).build_transaction({
            'chainId': CHAIN_ID,
            'gas': 500000,  # Gas limit
            'gasPrice': gas_price,
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_txn = web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
        
        # Send transaction
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_hash_hex = web3.to_hex(tx_hash)
        print(f"Transaction sent: {tx_hash_hex}")
        
        # Wait for transaction receipt
        print("Waiting for transaction confirmation...")
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        if tx_receipt.status == 1:
            print(f"✅ Trade executed successfully!")
            return {
                'status': 'success', 
                'tx_hash': tx_hash_hex,
                'receipt': str(tx_receipt)  # Convert to string to make it JSON serializable
            }
        else:
            print(f"❌ Transaction failed on-chain")
            return {
                'status': 'error', 
                'message': 'Transaction reverted on-chain',
                'tx_hash': tx_hash_hex
            }
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error executing trade: {error_msg}")
        
        # Try to give a helpful suggestion
        suggestion = 'Check trade parameters and contract ABI'
        if 'gas' in error_msg.lower():
            suggestion = 'Try increasing gas limit or reducing gas price'
        elif 'nonce' in error_msg.lower():
            suggestion = 'Nonce issue - wait for pending transactions to confirm'
        elif 'abi' in error_msg.lower():
            suggestion = 'Trade parameters format mismatch - check contract ABI definition'
            
        return {
            'status': 'error', 
            'message': error_msg,
            'suggested_fix': suggestion
        }

# If this script is run directly (not imported)
if __name__ == "__main__":
    # Test with a sample signal
    test_signal = {
        "pair_index": 5,
        "is_long": True,
        "position_size": 1,
        "leverage": 5,  # 5x leverage
        "entry_price": 3000,  # Example entry price for BTC
        "stop_loss": 0,
        "trailing_stop": 5  # 5% trailing stop
    }
    print("Testing trade execution...")
    result = execute_trade_on_gains(test_signal)
    print(f"Result: {result}")
