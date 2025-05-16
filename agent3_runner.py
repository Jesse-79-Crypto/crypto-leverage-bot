from web3 import Web3
import json
import time
import os
import traceback
from datetime import datetime

# === Setup Constants === #
PAIR_INDEX_MAP = {
    "BTC": 0,
    "ETH": 1,
    "LINK": 2,
    "DOGE": 3,
    "ADA": 5,
    "AAVE": 7,
    "ALGO": 8,
    "BAT": 9,
    "COMP": 10,
    "DOT": 11,
    "EOS": 12
}

MIN_NOTIONAL_PER_PAIR = {
    "BTC": 100,
    "ETH": 75,
    "LINK": 50,
    "SOL": 50,
    "AVAX": 50,
    "ARB": 50
}

# Get the private key and derive account from it
PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
# Initialize Web3 connection early
w3 = Web3(Web3.HTTPProvider(os.environ.get("BASE_RPC_URL")))
# Derive wallet address from private key
account = w3.eth.account.from_key(PRIVATE_KEY)
WALLET_ADDRESS = account.address
print(f"Using wallet address: {WALLET_ADDRESS}")

# Get USDC address
usdc_address_env = os.getenv("USDC_ADDRESS")
if not usdc_address_env:
    print("WARNING: USDC_ADDRESS environment variable is not set!")
    USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC address
else:
    USDC_ADDRESS = Web3.to_checksum_address(usdc_address_env)

GAINS_CONTRACT_ADDRESS = Web3.to_checksum_address("0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac")
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }
]

# Use the same ABI for USDC contract
USDC_ABI = ERC20_ABI

# Create the contract object
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

# Add a default position size
position_size_in_usdc = 100 * 1e6  # Default position size if not defined

allowance = usdc_contract.functions.allowance(WALLET_ADDRESS, GAINS_CONTRACT_ADDRESS).call()
amount_to_trade = int(position_size_in_usdc)  # or use fixed amount if dynamic logic isn't ready

if allowance < amount_to_trade:
    print(f"🔐 Approving {amount_to_trade} USDC to Gains contract...")
    approve_tx = usdc_contract.functions.approve(
        GAINS_CONTRACT_ADDRESS,
        int(2**256 - 1)  # Max approval
    ).build_transaction({
        'from': WALLET_ADDRESS,  # Using the address derived from the private key
        'nonce': w3.eth.get_transaction_count(WALLET_ADDRESS),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'chainId': 8453
    })

    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_approve.rawTransaction)
    print("✅ USDC Approved. Tx:", tx_hash.hex())
    w3.eth.wait_for_transaction_receipt(tx_hash)

from google.oauth2 import service_account
from googleapiclient.discovery import build

def log_trade_to_sheet(data):
    try:
        sheet_id = os.getenv("TRADE_LOG_SHEET_ID")
        tab_name = os.getenv("TRADE_LOG_TAB_NAME")
        creds_json = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
        }

        creds = service_account.Credentials.from_service_account_info(
            creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        row = [
            datetime.utcnow().isoformat(),
            data.get("coin"),
            data.get("direction"),
            data.get("entry_price"),
            data.get("stop_loss"),
            data.get("tp1"),
            data.get("tp2"),
            data.get("tp3"),
            data.get("position_size_usd"),
            data.get("position_size_token"),
            data.get("tx_hash"),
            data.get("log_link")
        ]

        sheet.values().append(
            spreadsheetId=sheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()

        print("📊 Trade logged to sheet successfully.")
    except Exception as e:
        print("⚠️ Failed to log trade:", str(e))
