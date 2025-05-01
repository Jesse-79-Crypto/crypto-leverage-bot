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
    result = service.values().get(spreadsheetId=SHEET_ID, range=f"{SIGNAL_TAB_NAME}!A1:Z").execute()
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

def simulate_trade_execution(signal):
    trade_direction = signal.get("Trade Direction")
    entry_price = float(signal.get("Entry Price"))
    stop_loss = float(signal.get("Stop-Loss"))
    tp1 = float(signal.get("TP1"))
    tp2 = float(signal.get("TP2"))
    tp3 = float(signal.get("TP3"))

    # Simulated result
    return {
        "status": "TRADE EXECUTED",
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "leverage": LEVERAGE,
        "wallet_balance": 100,  # Placeholder
        "position_size_usd": 100 * (MAX_RISK / 100),
        "position_size_token": round((100 * (MAX_RISK / 100)) / entry_price, 4),
        "log_link": f"https://docs.google.com/spreadsheets/d/{TRADE_LOG_SHEET_ID}",
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
            result = simulate_trade_execution(signal)
            log_trade(service, result)
            mark_signal_processed(service, row_index)
            send_email("Trade Executed", json.dumps(result, indent=2))
        else:
            print("No actionable trade found.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
