from web3 import Web3
import json
import time
import os

# ✅ Map trading symbols to Gains Network pair indices
PAIR_INDEX_MAP = {
    "BTC": 1,
    "ETH": 2,
    "LINK": 3,
    "SOL": 4,
    "AVAX": 5,
    "ARB": 6
}

def execute_trade_on_gains(signal):
    print("🚦 Trade execution started")
    try:
        # Connect to BASE network via Alchemy
        w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC_URL")))
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to BASE network.")
        print("🔌 Connected to BASE")

        # Load wallet
        private_key = os.getenv("WALLET_PRIVATE_KEY")
        account = w3.eth.account.from_key(private_key)
        print(f"👛 Wallet loaded: {account.address}")

        # Load ABI
        with open("abi/gains_base_abi.json", "r") as abi_file:
            gains_abi = json.load(abi_file)
        print("📦 ABI loaded")

        # Load contract
        contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
        contract = w3.eth.contract(address=contract_address, abi=gains_abi)
        print("📄 Contract connected")

        # Format trade details
        is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
        entry_price = float(signal.get("Entry Price"))
        symbol = signal.get("Coin", "").strip().upper()
        pair_index = PAIR_INDEX_MAP.get(symbol, 0)

        if pair_index == 0:
            raise ValueError(f"❌ Unsupported or missing symbol in signal: '{symbol}'")

        leverage = int(os.getenv("LEVERAGE", 5))
        max_risk_pct = float(os.getenv("MAX_RISK_PCT", 15))

        # 💡 Get actual ETH balance and conservative USD estimate
        wallet_balance = w3.eth.get_balance(account.address)
        eth_balance = float(w3.from_wei(wallet_balance, 'ether'))
        eth_usd_price = float(os.getenv("ETH_USD_PRICE", 3000))  # fallback
        usd_balance = eth_balance * eth_usd_price
        usd_amount = usd_balance * (max_risk_pct / 100)

        position_size = int(usd_amount * 1e6)  # BASE tokens have 6 decimals
        print(f"📊 Calculated position size: ${usd_amount:.2f} USD (~{position_size} tokens)")

        # Tuple (struct) argument - types match contract expectations
        trade_struct = (
            Web3.to_checksum_address(account.address),  # address
            int(pair_index),                            # uint32
            int(leverage) & 0xFFFF,                     # uint16
            int(position_size) & 0xFFFFFF,              # uint24
            bool(is_long),                              # bool
            True,                                       # bool (takeProfit)
            int(1) & 0xFF,                              # uint8 (slippage)
            int(3) & 0xFF,                              # uint8 (tpCount)
            int(0) & ((1 << 120) - 1),                  # uint120 (tpPrices)
            int(0) & ((1 << 64) - 1),                   # uint64 (slPrices)
            int(time.time()) + 120,                     # uint64 (deadline)
            int(0),                                     # uint64 (referralCode)
            int(0)                                      # uint192 (extraParams)
        )

        order_type = 0
        referral_address = account.address

        # Build transaction
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price

        txn = contract.functions.openTrade(
            trade_struct,
            order_type,
            referral_address
        ).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 300000,
            'gasPrice': gas_price,
            'value': 0
        })

        # Sign and send
        signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

        print(f"🚀 Trade sent! TX hash: {tx_hash.hex()}")

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
        print(f"❌ ERROR: {e}")
        raise
