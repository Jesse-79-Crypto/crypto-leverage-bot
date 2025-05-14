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
        w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC_URL")))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to BASE network.")
        print("Connected to BASE")

        private_key = os.getenv("WALLET_PRIVATE_KEY")
        account = w3.eth.account.from_key(private_key)
        print(f"Wallet loaded: {account.address}")

        with open("abi/gains_base_abi.json", "r") as f:
            gains_abi = json.load(f)
        print("ABI loaded")

        contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
        contract = w3.eth.contract(address=contract_address, abi=gains_abi)
        print("Contract connected")

        # Load USDC ABI and contract
        try:
            with open("abi/usdc_abi.json", "r") as f:
                usdc_abi = json.load(f)
        except FileNotFoundError:
            usdc_abi = [
                {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "remaining", "type": "uint256"}], "type": "function"},
                {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
            ]

        usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
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
                gas_price = max(int(base_gas_price * 1.1), base_gas_price + 1_000_000_000)
                approval_amount = int(1_000 * 1e6)

                tx = usdc.functions.approve(contract_address, approval_amount).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'gasPrice': gas_price,
                })
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                print(f"Approval TX sent: {tx_hash.hex()}")

                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status != 1:
                    raise Exception("USDC approval transaction failed")
                print("USDC approval confirmed on-chain")
                time.sleep(3)

            except Exception as e:
                print("Approval error:", str(e))
                print(traceback.format_exc())
                return {"status": "error", "message": f"USDC approval failed: {str(e)}", "trace": traceback.format_exc()}

        # Trade logic
        is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
        entry_price = float(signal.get("Entry Price"))
        symbol = signal.get("Coin", "").strip().upper()
        pair_index = PAIR_INDEX_MAP.get(symbol, 0)

        if pair_index == 0:
            raise ValueError(f"Unsupported or missing symbol in signal: '{symbol}'")

        leverage = int(os.getenv("LEVERAGE", 5))

        notional_value = usd_amount * leverage
        min_required = MIN_NOTIONAL_PER_PAIR.get(symbol, 50)
        if notional_value < min_required:
            print(f"Skipping trade: Notional value ${notional_value:.2f} is below Gains minimum of ${min_required} for {symbol}")
            return {"status": "SKIPPED", "reason": f"Notional value ${notional_value:.2f} too low for {symbol}"}

        if usd_amount < 5:
            print(f"Skipping trade: position size ${usd_amount:.2f} is below $5 minimum.")
            return {"status": "SKIPPED", "reason": f"Trade size ${usd_amount:.2f} below $5 minimum"}

        position_size = int(usd_amount * 1e6)
        print(f"Position size: ${usd_amount:.2f} USD (~{position_size} tokens)")

        trade_struct = (
            Web3.to_checksum_address(account.address),
            int(pair_index),
            int(leverage) & 0xFFFF,
            int(position_size) & 0xFFFFFF,
            bool(is_long),
            True,
            1,
            3,
            0,
            0,
            int(time.time()) + 120,
            0,
            0
        )

        txn = contract.functions.openTrade(
            trade_struct,
            30,  # max slippage in tenths of a percent (3%)
            account.address
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'value': 0
        })

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

    except Exception as e:
        print("ERROR: An exception occurred during trade execution")
        print("Error details:", str(e))
        print("Traceback:\n", traceback.format_exc())
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}
