import os
import time
import json
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# === Load Environment Variables === #
SHEET_ID = os.getenv("SIGNAL_SHEET_ID")
SIGNAL_TAB_NAME = os.getenv("SIGNAL_TAB_NAME")
TRADE_LOG_SHEET_ID = os.getenv("TRADE_LOG_SHEET_ID")
TRADE_LOG_TAB_NAME = os.getenv("TRADE_LOG_TAB_NAME")
HOT_WALLET_ADDRESS = os.getenv("HOT_WALLET_ADDRESS")
HOT_WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
GOOGLE_CREDS_JSON = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
}
EMAIL_ALERT_ADDRESS = os.getenv("EMAIL_ALERT_ADDRESS")
LEVERAGE = float(os.getenv("LEVERAGE", 5))
MAX_RISK = float(os.getenv("MAX_RISK_PCT", 15))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SEC", 180))
CHAIN_ID = os.getenv("CHAIN_ID")
GAS_TOKEN = os.getenv("GAS_TOKEN")
GAINS_CONTRACT = os.getenv("GAINS_CONTRACT_ADDRESS")

# === Google Sheets Setup === #
def get_google_service():
    creds = service_account.Credentials.from_service_account_info(GOOGLE_CREDS_JSON)
    return build("sheets", "v4", credentials=creds).spreadsheets()

def read_latest_signal(service):
    result = service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SIGNAL_TAB_NAME}!A1:Z"
    ).execute()

    rows = result.get("values", [])
    if len(rows) <= 1:
        return None, None

    headers = rows[0]
    last_row = rows[-1]
    signal = dict(zip(headers, last_row))

    if signal.get("Processed", "").strip() == "✅ Processed":
        return None, None

    required = ["Trade Direction", "Entry Price", "Stop-Loss", "TP1", "TP2", "TP3"]
    if not all(signal.get(f) for f in required):
        return None, None

    return signal, len(rows)

def mark_signal_processed(service, row_number):
    cell = f"{chr(65 + 41)}{row_number}"  # Column AP (index 41)
    service.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SIGNAL_TAB_NAME}!{cell}",
        valueInputOption="RAW",
        body={"values": [["✅ Processed"]]},
    ).execute()

def send_email(subject, body):
    print(f"[EMAIL TO {EMAIL_ALERT_ADDRESS}] {subject}\n{body}")

from web3 import Web3
import json

def execute_trade_on_gains(signal):
    # Connect to BASE via Alchemy
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

    # Extract signal data
    market = "ETH/USD"  # Placeholder; adjust to match Gains contract
    is_long = signal.get("Trade Direction", "").strip().upper() == "LONG"
    leverage = int(os.getenv("LEVERAGE", 5))
    entry_price = float(signal.get("Entry Price"))
    stop_loss = float(signal.get("Stop-Loss"))
    tp1 = float(signal.get("TP1"))
    tp2 = float(signal.get("TP2"))
    tp3 = float(signal.get("TP3"))
    amount_usd = 100 * (float(os.getenv("MAX_RISK_PCT", 15)) / 100)

    # Estimate gas + nonce
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    # Build transaction (placeholder function, update to match actual Gains method)
    txn = contract.functions.openTrade(
        market,
        is_long,
        int(amount_usd * 1e18),
        leverage
    ).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 500000,
        'gasPrice': gas_price,
    })

    # Sign + send
    signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    print(f"🚀 Trade sent! TX hash: {tx_hash.hex()}")

    return {
        "status": "TRADE SENT",
        "tx_hash": tx_hash.hex(),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "leverage": leverage,
        "wallet_balance": 100,  # Placeholder
        "position_size_usd": amount_usd,
        "position_size_token": round(amount_usd / entry_price, 4),
        "log_link": f"https://basescan.org/tx/{tx_hash.hex()}",
    }

def log_trade(service, result):
    values = [[
        time.strftime("%Y-%m-%d %H:%M:%S"),
        result["entry_price"],
        result["stop_loss"],
        result["tp1"],
        result["tp2"],
        result["tp3"],
        result["position_size_usd"],
        result["position_size_token"],
        result["status"]
    ]]
    service.values().append(
        spreadsheetId=TRADE_LOG_SHEET_ID,
        range=TRADE_LOG_TAB_NAME,
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

def main_loop():
    service = get_google_service()
    while True:
        print("Checking for signal...")
        signal, row_index = read_latest_signal(service)
        if signal:
            print("Valid signal found, processing...")
            result = execute_trade_on_gains(signal)
            log_trade(service, result)
            mark_signal_processed(service, row_index)
            send_email("Trade Executed", json.dumps(result, indent=2))
        else:
            print("No actionable trade found.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
