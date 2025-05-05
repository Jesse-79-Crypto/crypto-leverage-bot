from web3 import Web3
import json
import time
import os

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
        leverage = int(os.getenv("LEVERAGE", 5))
        max_risk_pct = float(os.getenv("MAX_RISK_PCT", 15))

        # 💡 Get actual ETH balance from wallet and calculate position size
        wallet_balance = w3.eth.get_balance(account.address)
        eth_balance = float(w3.from_wei(wallet_balance, 'ether'))
        usd_balance = eth_balance * entry_price
        usd_amount = usd_balance * (max_risk_pct / 100)

        position_size = int(usd_amount * 1e6)  # BASE tokens have 6 decimals
        print(f"📊 Calculated position size: ${usd_amount:.2f} USD (~{position_size} tokens)")

        # Properly cast each field to match ABI expectations
        trade_struct = (
            Web3.to_checksum_address(account.address),  # address
            int(0),                                     # uint32
            int(leverage) & 0xFFFF,                     # uint16
            int(position_size) & 0xFFFFFF,              # uint24
            bool(is_long),                              # bool
            True,                                       # bool
            int(1) & 0xFF,                               # uint8 (slippage)
            int(3) & 0xFF,                               # uint8 (tpCount)
            int(0) & ((1 << 120) - 1),                  # uint120 (tpPrices placeholder)
            int(0) & ((1 << 64) - 1),                   # uint64 (slPrices placeholder)
            int(time.time()) + 120,                    # uint64 (deadline)
            int(0),                                     # uint64 (referralCode)
            int(0)                                      # uint192 (extraParams placeholder)
        )

        order_type = 0  # market order
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
