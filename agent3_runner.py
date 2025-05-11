from web3 import Web3
import json
import time
import os
import traceback

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

def execute_trade_on_gains(signal):
    print("Incoming signal data:", json.dumps(signal, indent=2))
    print("Trade execution started")
    try:
        # Connect to Base network
        w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC_URL")))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to BASE network.")
        print("Connected to BASE")

        private_key = os.getenv("WALLET_PRIVATE_KEY")
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
        usd_amount = usdc_balance * float(os.getenv("MAX_RISK_PCT", 15)) / 100
        print(f"USDC balance: {usdc_balance:.2f}, Using: {usd_amount:.2f} for this trade")

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

        leverage = int(os.getenv("LEVERAGE", 5))
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

        # Let's debug the function signature directly to find exact field names
        for func_item in gains_abi:
            if func_item.get('name') == 'openTrade':
                print("Found openTrade function in ABI")
                print(json.dumps(func_item, indent=2))
                
                # Check if function has inputs
                if 'inputs' in func_item:
                    # Check if first input is a tuple/struct
                    first_input = func_item['inputs'][0]
                    if first_input.get('type') == 'tuple':
                        print("First parameter is a struct/tuple. Components:")
                        # Extract component names
                        for i, component in enumerate(first_input.get('components', [])):
                            print(f"Component {i}: name='{component.get('name')}', type='{component.get('type')}'")

        # Calculate slippage based on volatility of the asset
        slippage = 50 if symbol in ["BTC", "ETH"] else 100  # 0.5% for majors, 1% for others
        print(f"Using slippage: {slippage/10}%")

        try:
            # Build and send the transaction using low-level interface to avoid struct issues
            
            # Setup inputs manually based on the ABI analysis above
            # This will create a dictionary with the EXACT field names from the ABI
            trade_struct = {
                # IMPORTANT: These field names must exactly match what we found in the ABI
                'trader': Web3.to_checksum_address(account.address),
                'index': pair_index,  # Field name from error message
                'leverage': leverage, 
                'margin': position_size,
                'isLong': is_long,
                'referral': True,
                'mode': 1,
                'tp': 0,
                'sl': 0,
                'priceLimit': 0,
                'deadline': int(time.time()) + 300,
                'extra': 0
                # Add any other fields we found from ABI dumping
            }
            
            # Get nonce and gas price
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = int(w3.eth.gas_price * 1.3)  # 30% higher for Base
            
            # Try using our updated struct format
            print(f"Attempting trade with struct: {json.dumps(trade_struct, default=str)}")
            txn = contract.functions.openTrade(
                trade_struct,         # Updated struct with correct field names
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
            print(f"Trade sent! TX hash: {tx_hash.hex()}")
            
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
