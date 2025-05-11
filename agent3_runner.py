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

def verify_gains_trade_struct(trade_struct):
    """
    Verifies the trade struct parameters, checking common issues
    """
    issues = []
    status = "PASS"
    
    # Verify address
    if not Web3.is_address(trade_struct[0]):
        issues.append("Invalid trader address")
        status = "FAIL"
    
    # Verify pair index (should be 1-15 for most Gains deployments)
    if not isinstance(trade_struct[1], int) or trade_struct[1] < 1 or trade_struct[1] > 15:
        issues.append(f"Suspicious pair index: {trade_struct[1]}")
        status = "WARNING"
    
    # Verify leverage (Gains usually allows 2-150x)
    if not isinstance(trade_struct[2], int) or trade_struct[2] < 2 or trade_struct[2] > 150:
        issues.append(f"Leverage value suspicious: {trade_struct[2]}")
        status = "WARNING"
    
    # Verify position size (Gains usually expects this in USDC with 6 decimals)
    # Minimum size is usually around 5 USDC (5,000,000)
    if not isinstance(trade_struct[3], int) or trade_struct[3] < 5_000_000:
        issues.append(f"Position size suspicious: {trade_struct[3]}")
        status = "WARNING"
    
    # Verify direction is boolean
    if not isinstance(trade_struct[4], bool):
        issues.append(f"Direction not boolean: {trade_struct[4]}")
        status = "FAIL"
    
    # Verify deadline
    current_time = int(time.time())
    if not isinstance(trade_struct[10], int) or trade_struct[10] < current_time:
        issues.append(f"Deadline already passed: {trade_struct[10]}")
        status = "FAIL"
    
    return {
        "status": status,
        "issues": issues,
        "struct": trade_struct
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

        # Check if the required function exists in the ABI
        if not any(func.get('name') == 'openTrade' for func in gains_abi if 'name' in func):
            raise Exception("openTrade function not found in ABI - check your ABI file")

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

        # IMPORTANT: The struct must match the contract's expected format exactly
        trade_struct = (
            Web3.to_checksum_address(account.address),  # trader
            pair_index,                                 # pairIndex (must be a valid index from PAIR_INDEX_MAP)
            leverage,                                   # leverage (must be within contract's allowed range)
            position_size,                              # positionSizeStable (in USDC token units, 6 decimals)
            is_long,                                    # direction (true for long, false for short)
            True,                                       # referral enabled
            1,                                          # openMode (1 for market)
            3,                                          # closeMode 
            0,                                          # TP price (0 for none)
            0,                                          # SL price (0 for none)
            int(time.time()) + 300,                     # deadline (5 mins from now)
            0,                                          # Reserved1
            0                                           # Reserved2
        )
        
        # CRITICAL: Log and verify the trade parameters for debugging
        print(f"Pair Index: {pair_index}, Type: {type(pair_index)}")
        print(f"Leverage: {leverage}, Type: {type(leverage)}")
        print(f"Position Size: {position_size}, Type: {type(position_size)}")
        print(f"Is Long: {is_long}, Type: {type(is_long)}")
        print(f"Deadline: {int(time.time()) + 300}, Type: {type(int(time.time()) + 300)}")
        
        # Verify trade struct before sending
        verification = verify_gains_trade_struct(trade_struct)
        print(f"Trade struct verification: {verification['status']}")
        if verification['issues']:
            print("Issues found:")
            for issue in verification['issues']:
                print(f"- {issue}")
            if verification['status'] == "FAIL":
                return {"status": "error", "message": f"Failed trade struct validation: {verification['issues']}"}
        
        # Calculate slippage based on volatility of the asset
        slippage = 50 if symbol in ["BTC", "ETH"] else 100  # 0.5% for majors, 1% for others
        print(f"Using slippage: {slippage/10}%")

        try:
            # Verify contract method signature before proceeding
            print("Verifying contract interface...")
            
            # Build the transaction
            txn = contract.functions.openTrade(
                trade_struct,
                slippage,              # slippage (tenths of a percent)
                account.address        # callback target
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
                'value': 0
            })
            
            # Log the full transaction data for debugging
            tx_data = txn.get('data', '0x')
            print(f"Transaction data length: {len(tx_data)}")
            print(f"Transaction data prefix: {tx_data[:66]}...")
            
            # Add gas price with buffer for Base network
            base_gas_price = w3.eth.gas_price
            txn['gasPrice'] = int(base_gas_price * 1.3)  # 30% higher gas price
            
            # Dynamically estimate gas instead of using hardcoded value
            try:
                gas_estimate = w3.eth.estimate_gas(txn)
                txn['gas'] = int(gas_estimate * 1.3)  # Add 30% buffer
                print(f"Estimated gas: {gas_estimate}, using: {txn['gas']}")
            except Exception as gas_err:
                print(f"Gas estimation failed: {str(gas_err)}")
                # Use higher gas limit as fallback
                txn['gas'] = 500000
                print(f"Using fallback gas limit: {txn['gas']}")
            
            # Final transaction details for logging
            print(f"Transaction details: nonce={txn['nonce']}, gas={txn['gas']}, gasPrice={txn['gasPrice']}")
            
            # Sign and send transaction
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
            
            # Check for common error patterns
            if "gas required exceeds allowance" in error_msg:
                suggested_fix = "Increase gas limit or optimize contract call"
            elif "insufficient funds" in error_msg:
                suggested_fix = "Check BASE native token balance for gas fees"
            elif "nonce too low" in error_msg:
                suggested_fix = "Nonce issue - try resetting transaction count"
            elif "execution reverted" in error_msg:
                suggested_fix = "Contract execution failed - check parameters and trade conditions"
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
