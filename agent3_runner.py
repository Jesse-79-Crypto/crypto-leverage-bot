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
        # Connect to BASE network
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

        # ✅ Approve USDC if necessary
        usdc_address = Web3.to_checksum_address("0xd9AAEC86B65d86f6A7B5B1b0c42FFA531710b6CA")  # ✅ USDC on Base
        usdc_abi = [
            {
                "name": "approve",
                "type": "function",
                "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable"
            },
            {
                "name": "allowance",
                "type": "function",
                "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
                "outputs": [{"name": "remaining", "type": "uint256"}],
                "stateMutability": "view"
            },
            {
                "name": "balanceOf",
                "type": "function",
                "inputs": [{"name": "_owner", "type": "address"}],
                "outputs": [{"name": "balance", "type": "uint256"}],
                "stateMutability": "view"
            }
        ]
        usdc = w3.eth.contract(address=usdc_address, abi=usdc_abi)
        current_allowance = usdc.functions.allowance(account.address, contract_address).call()
        desired_allowance = int(500 * 1e6)

        if current_allowance < desired_allowance:
            print("🧾 Approving USDC for Gains contract...")
            nonce = w3.eth.get_transaction_count(account.address)
            gas_price = w3.eth.gas_price
            tx = usdc.functions.approve(contract_address, desired_allowance).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': gas_price,
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"✅ Approval TX sent: {tx_hash.hex()}")
            time.sleep(10)

        # ✅ Get USDC balance instead of ETH
        usdc_balance = usdc.functions.balanceOf(account.address).call() / 1e6
        usd_amount = usdc_balance * float(os.getenv("MAX_RISK_PCT", 15)) / 100

        # Extract trade details
        is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
        entry_price = float(signal.get("Entry Price"))
        symbol = signal.get("Coin", "").strip().upper()
        pair_index = PAIR_INDEX_MAP.get(symbol, 0)

        if pair_index == 0:
            raise ValueError(f"❌ Unsupported or missing symbol in signal: '{symbol}'")

        leverage = int(os.getenv("LEVERAGE", 5))

        # 🛑 Skip if trade size is too small
        if usd_amount < 5:
            print(f"⚠️ Skipping trade: position size ${usd_amount:.2f} is below $5 minimum.")
            return {
                "status": "SKIPPED",
                "reason": f"Trade size ${usd_amount:.2f} below $5 minimum"
            }

        position_size = int(usd_amount * 1e6)
        print(f"📊 Position size: ${usd_amount:.2f} USD (~{position_size} tokens)")

        # Build trade struct
        trade_struct = (
            Web3.to_checksum_address(account.address),  # address
            int(pair_index),                            # uint32
            int(leverage) & 0xFFFF,                     # uint16
            int(position_size) & 0xFFFFFF,              # uint24
            bool(is_long),                              # bool
            True,                                       # takeProfit
            1,                                          # slippage (uint8)
            3,                                          # tpCount (uint8)
            0,                                          # tpPrices (uint120)
            0,                                          # slPrices (uint64)
            int(time.time()) + 120,                     # deadline (uint64)
            0,                                          # referralCode (uint64)
            0                                           # extraParams (uint192)
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
