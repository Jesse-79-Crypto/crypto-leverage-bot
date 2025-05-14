import json
import time
import os
import traceback
from web3 import Web3

# Trade pair mapping and minimums
PAIR_INDEX_MAP = {
    "BTC": 1,
    "ETH": 2,
    "LINK": 3,
    "SOL": 4,
    "AVAX": 5,
    "ARB": 6
}

MIN_NOTIONAL_PER_PAIR = {
    "BTC": 100,
    "ETH": 75,
    "LINK": 50,
    "SOL": 50,
    "AVAX": 50,
    "ARB": 50
}

# In-memory record of open trades (replace with database later)
OPEN_TRADES = set()


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

        with open("abi/gains_base_abi.json", "r") as abi_file:
            gains_abi = json.load(abi_file)
        contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
        contract = w3.eth.contract(address=contract_address, abi=gains_abi)

        usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        with open("abi/usdc_abi.json", "r") as f:
            usdc_abi = json.load(f)
        usdc = w3.eth.contract(address=usdc_address, abi=usdc_abi)

        usdc_balance = usdc.functions.balanceOf(account.address).call() / 1e6
        usd_amount = usdc_balance * float(os.getenv("MAX_RISK_PCT", 15)) / 100

        is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
        entry_price = float(signal.get("Entry Price"))
        symbol = signal.get("Coin", "").strip().upper()
        pair_index = PAIR_INDEX_MAP.get(symbol, 0)

        if pair_index == 0:
            raise ValueError(f"Unsupported or missing symbol in signal: '{symbol}'")

        leverage = int(os.getenv("LEVERAGE", 5))

        # Trade cap enforcement
        if len(OPEN_TRADES) >= 2:
            print("Trade skipped: Max active trades limit reached.")
            return {"status": "SKIPPED", "reason": "Too many active trades"}

        if symbol in OPEN_TRADES:
            print(f"Trade skipped: Already have an open trade for {symbol}.")
            return {"status": "SKIPPED", "reason": f"Already open position on {symbol}"}

        notional_value = usd_amount * leverage
        min_required = MIN_NOTIONAL_PER_PAIR.get(symbol, 50)
        if notional_value < min_required:
            print(f"Skipping trade: Notional value ${notional_value:.2f} < ${min_required}")
            return {"status": "SKIPPED", "reason": f"Notional too low for {symbol}"}

        if usd_amount < 5:
            print(f"Skipping trade: position size ${usd_amount:.2f} is below $5 minimum.")
            return {"status": "SKIPPED", "reason": "Trade size below $5 minimum"}

        # Approve if needed
        allowance = usdc.functions.allowance(account.address, contract_address).call() / 1e6
        if allowance < usd_amount:
            try:
                print("Approving USDC for contract...")
                nonce = w3.eth.get_transaction_count(account.address, 'pending')
                gas_price = int(w3.eth.gas_price * 1.1)
                tx = usdc.functions.approve(contract_address, int(1000 * 1e6)).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'gasPrice': gas_price
                })
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                time.sleep(3)
            except Exception as e:
                return {"status": "error", "message": f"Approval failed: {str(e)}"}

        # Construct trade
        position_size = int(usd_amount * 1e6)
        trade_struct = (
            Web3.to_checksum_address(account.address),
            int(pair_index),
            leverage & 0xFFFF,
            position_size & 0xFFFFFF,
            is_long,
            True,
            1, 3, 0, 0,
            int(time.time()) + 120,
            0, 0
        )

        txn = contract.functions.openTrade(trade_struct, 30, account.address).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'value': 0
        })

        signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"Trade sent: {tx_hash.hex()}")

        # Mark trade as open (TEMP memory-based)
        OPEN_TRADES.add(symbol)

        return {
            "status": "TRADE SENT",
            "tx_hash": tx_hash.hex(),
            "position_size_usd": usd_amount,
            "symbol": symbol,
            "log_link": f"https://basescan.org/tx/{tx_hash.hex()}"
        }

    except Exception as e:
        print("Trade failed:", str(e))
        print(traceback.format_exc())
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}
