#!/usr/bin/env python3
"""
Flask runner for Gains Network trades.
Enforces per-coin min collateral, approves USDC, opens trades at 5×,
and logs metrics to your Trade Log sheet.
"""

import os
import json
import time
import logging
from flask import Flask, request, jsonify
from web3 import Web3
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ----- CONFIG -----
RPC_URL         = os.getenv('BASE_RPC_URL')
PRIVATE_KEY     = os.getenv('WALLET_PRIVATE_KEY')
TRADE_LOG_SHEET = os.getenv('TRADE_LOG_SHEET_ID')
TRADE_LOG_TAB   = os.getenv('TRADE_LOG_TAB_NAME', 'Trade Log')
USDC_ADDRESS    = os.getenv('USDC_ADDRESS')
GAINS_ADDRESS   = "0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac"

MIN_NOTIONAL = {
    "BTC": 300,
    "ETH": 250,
    "DEFAULT": 150
}
LEVERAGE     = 5
MAX_SLIPPAGE = 30  # basis points (0.3%)

# ----- LOGGING -----
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

# ----- WEB3 SETUP -----
w3 = Web3(Web3.HTTPProvider(RPC_URL))
acct = w3.eth.account.from_key(PRIVATE_KEY)

# ----- ABI LOADER WITH FALLBACK -----
def load_abi(path):
    # Build full absolute path relative to this script
    base = os.path.dirname(__file__)
    full_path = os.path.join(base, path)
    try:
        with open(full_path) as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback minimal ERC-20 ABI for balanceOf, allowance, approve
        return [
            {
                "constant": True,
                "inputs": [{"name":"_owner","type":"address"}],
                "name": "balanceOf",
                "outputs":[{"name":"balance","type":"uint256"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],
                "name": "allowance",
                "outputs":[{"name":"remaining","type":"uint256"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],
                "name": "approve",
                "outputs":[{"name":"","type":"bool"}],
                "type": "function"
            }
        ]

# Load ABIs
erc20 = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=load_abi('abi/erc20_abi.json')
)
gains = w3.eth.contract(
    address=Web3.to_checksum_address(GAINS_ADDRESS),
    abi=load_abi('abi/gains_base_abi.json')
)

# ----- TRANSACTION HELPERS -----
def send_tx(tx):
    signed = acct.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed.rawTransaction)

def log_to_sheet(vals):
    creds = service_account.Credentials.from_service_account_file(
        'path/to/service_account.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    svc = build('sheets', 'v4', credentials=creds).spreadsheets()
    svc.values().append(
        spreadsheetId=TRADE_LOG_SHEET,
        range=f"{TRADE_LOG_TAB}!A1",
        valueInputOption='RAW',
        body={'values': [vals]}
    ).execute()

# ----- FLASK APP -----
app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute():
    sig = request.json
    try:
        # Parse core fields
        coin      = sig['coin']
        direction = sig['direction']
        entry     = float(sig['entry'])
        stop      = float(sig['stop'])
        tp1       = float(sig['tp1'])

        # 1) Determine minimum collateral
        min_notional = MIN_NOTIONAL.get(coin, MIN_NOTIONAL['DEFAULT'])
        min_collat    = min_notional / LEVERAGE

        # 2) Compute risk-based collateral (15% of balance)
        balance     = erc20.functions.balanceOf(acct.address).call() / 1e6
        risk_collat = balance * 0.15
        collateral  = max(risk_collat, min_collat)
        units       = int(collateral * 1e6)
        log.info(f"{coin} → collateral set to {collateral:.2f} USDC (min {min_collat:.2f})")

        # 3) Approve USDC if allowance too low
        if erc20.functions.allowance(acct.address, GAINS_ADDRESS).call() < units:
            tx = erc20.functions.approve(GAINS_ADDRESS, 2**256 - 1).buildTransaction({
                'from': acct.address,
                'nonce': w3.eth.get_transaction_count(acct.address, 'pending'),
                'gas': 100_000,
                'gasPrice': w3.eth.gas_price
            })
            send_tx(tx)
            time.sleep(3)

        # 4) Build and send the trade
        pair_idx = {'BTC':0, 'ETH':1}[coin]
        trade_struct = (
            acct.address, 0, pair_idx, LEVERAGE,
            direction == 'LONG', True, 0, 0,
            units, 0,
            int(tp1 * 1e8), int(stop * 1e8), 0
        )
        tx = gains.functions.openTrade(trade_struct, MAX_SLIPPAGE, acct.address).buildTransaction({
            'from': acct.address,
            'nonce': w3.eth.get_transaction_count(acct.address, 'pending'),
            'gas': 350_000,
            'gasPrice': w3.eth.gas_price
        })
        txh = send_tx(tx)
        log.info(f"Trade sent: {txh.hex()}")

        # 5) Log all metrics to Google Sheet
        row = [
            coin,
            direction,
            entry,
            stop,
            tp1,
            sig.get('rsi30'),
            sig.get('macd30'),
            sig.get('ema9'),
            sig.get('ema21'),
            sig.get('bbU'),
            sig.get('bbL'),
            sig.get('macd4h'),
            sig.get('macd1d'),
            sig.get('longScore'),
            sig.get('shortScore'),
            sig.get('regime'),
            collateral,
            txh.hex()
        ]
        log_to_sheet(row)
        return jsonify(status='ok', tx=txh.hex())

    except Exception as e:
        log.error("Execution error", exc_info=True)
        return jsonify(status='error', message=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
