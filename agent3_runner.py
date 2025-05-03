from web3 import Web3
import json
import time
import os

def execute_trade_on_gains(signal):
    # Connect to BASE network via Alchemy
    w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC_URL")))
    if not w3.is_connected():
        raise ConnectionError("Failed to connect to BASE network.")

    # Load wallet
    private_key = os.getenv("WALLET_PRIVATE_KEY")
    account = w3.eth.account.from_key(private_key)

    # Load ABI
    with open("abi/gains_base_abi.json", "r") as abi_file:
        gains_abi = json.load(abi_file)

    # Load contract
    contract_address = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
    contract = w3.eth.contract(address=contract_address, abi=gains_abi)

    # Format trade details
    is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
    entry_price = float(signal.get("Entry Price"))
    leverage = int(os.getenv("LEVERAGE", 5))
    max_risk_pct = float(os.getenv("MAX_RISK_PCT", 15))
    usd_amount = 100 * (max_risk_pct / 100)
    position_size = int(usd_amount * 1e6)  # Adjust based on token decimals (e.g., 6 or 18)

    # Tuple (struct) argument
    trade_tuple = (
        account.address,     # user address
        0,                   # pairIndex — for now, default to 0 (must be updated with actual pairIndex)
        leverage,
        position_size,
        is_long,
        True,                # takeProfit flag (true/false)
        1,                   # slippage — basic default value
        3,                   # tpCount
        0,                   # tpPrices — to be handled in future
        0,                   # slPrices — to be handled in future
        int(time.time()) + 120,  # deadline (current time + 2 minutes)
        0,                   # referralCode
        0                    # extraParams
    )

    order_type = 0  # Assume 0 = market order (update as needed)
    referral_address = account.address  # No external referral yet

    # Build transaction
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    txn = contract.functions.openTrade(
        trade_tuple,
        order_type,
        referral_address
    ).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 900000,
        'gasPrice': gas_price
    })

    # Sign and send
    signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

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
        "log_link": f"https://basescan.org/tx/{tx_hash.hex()}",
    }
