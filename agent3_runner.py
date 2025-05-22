#!/usr/bin/env python3
"""
Gains Network Trading Bot — Runner
Executes trades from webhook payload, enforcing per-coin minimum collateral,
approving USDC, opening trades with 5× leverage, and logging everything.
"""

import os
import json
import time
import logging
from flask import Flask, request, jsonify
from web3 import Web3
from web3.exceptions import TransactionNotFound
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ===== CONFIGURATION =====
RPC_URL         = os.getenv('BASE_RPC_URL')
PRIVATE_KEY     = os.getenv('WALLET_PRIVATE_KEY')
TRADE_LOG_SHEET = os.getenv('TRADE_LOG_SHEET_ID')
TRADE_LOG_TAB   = os.getenv('TRADE_LOG_TAB_NAME', 'Trade Log')
USDC_ADDRESS    = os.getenv('USDC_ADDRESS')  # e.g. "0x8335..."
GAINS_ADDRESS   = "0xfb1aaba03c31ea98a3eec7591808acb1947ee7ac"  # Base Gains

# Min notional per coin (collateral × leverage)
MIN_NOTIONAL = {
    "BTC": 300,
    "ETH": 250,
    "DEFAULT": 150
}

LEVERAGE = 5
MAX_SLIPPAGE = 30  # bps (0.3%)

# ===== LOGGING =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

# ===== WEB3 SETUP =====
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)

# Load ABIs
def load_abi(path):
    with open(path) as f:
        return json.load(f)

erc20 = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=load_abi('abi/erc20_abi.json')
)
gains = w3.eth.contract(
    address=Web3.to_checksum_address(GAINS_ADDRESS),
    abi=load_abi('abi/gains_base_abi.json')
)

# ===== HELPERS =====
def send_tx(tx):
    signed = account.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed.rawTransaction)

def log_to_sheet(row_vals):
    creds = service_account.Credentials.from_service_account_file(
        'path/to/service_account.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    svc = build('sheets', 'v4', credentials=creds).spreadsheets()
    svc.values().append(
        spreadsheetId=TRADE_LOG_SHEET,
        range=f"{TRADE_LOG_TAB}!A1",
        valueInputOption='RAW',
        body={'values': [row_vals]}
    ).execute()

# ===== FLASK APP =====
app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute():
    sig = request.json
    try:
        # Parse core fields
        coin      = sig['coin']             # e.g. "BTC"
        direction = sig['direction']        # "LONG" or "SHORT"
        entry     = float(sig['entry'])
        stop      = float(sig['stop'])
        tp1       = float(sig['tp1'])

        # Determine minimum collateral for this coin
        min_notional = MIN_NOTIONAL.get(coin, MIN_NOTIONAL['DEFAULT'])
        min_collat    = min_notional / LEVERAGE

        # Calculate risk-based collateral (15% of balance)
        balance = erc20.functions.balanceOf(account.address).call() / 1e6
        risk_collat = balance * 0.15

        # Final collateral = max(risk_collat, min_collat)
        collateral_amount = max(risk_collat, min_collat)
        collateral_units  = int(collateral_amount * 1e6)

        log.info(f"{coin} collateral set to {collateral_amount:.2f} USDC (min {min_collat:.2f})")

        # Approve USDC if needed
        current_allowance = erc20.functions.allowance(account.address, GAINS_ADDRESS).call()
        if current_allowance < collateral_units:
            log.info("Approving USDC...")
            tx = erc20.functions.approve(
                GAINS_ADDRESS,
                2**256 - 1
            ).buildTransaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
                'gas': 100_000,
                'gasPrice': w3.eth.gas_price
            })
            send_tx(tx)
            time.sleep(3)

        # Build trade struct
        pair_index = {'BTC':0, 'ETH':1}[coin]
        trade_struct = (
            account.address,
            0,                  # index
            pair_index,
            LEVERAGE,
            (direction == 'LONG'),
            True,               # isOpen
            0,                  # collateralIndex (USDC)
            0,                  # tradeType (market)
            collateral_units,
            0,                  # openPrice (market order)
            int(tp1 * 1e8),     # TP1
            int(stop * 1e8),    # SL
            0
        )

        tx = gains.functions.openTrade(
            trade_struct,
            MAX_SLIPPAGE,
            account.address
        ).buildTransaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
            'gas': 350_000,
            'gasPrice': w3.eth.gas_price
        })

        # Send trade
        tx_hash = send_tx(tx)
        log.info(f"Trade sent: {tx_hash.hex()}")

        # Log to Google Sheet (include metrics if desired)
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
            collateral_amount,
            tx_hash.hex()
        ]
        log_to_sheet(row)

        return jsonify(status='ok', tx=tx_hash.hex())

    except Exception as e:
        log.error("Execution error", exc_info=True)
        return jsonify(status='error', message=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
