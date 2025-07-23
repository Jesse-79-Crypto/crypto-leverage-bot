import os
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# 🧠 CONFIG ----------------------------------------------------------------
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# BMX CONTRACT ADDRESSES (Base network)
USDC_CONTRACT = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
BMX_ROUTER_CONTRACT = Web3.to_checksum_address("0x88B256d6b7ef47A775164bc8D9467538b2709c13")
PLUGIN_CONTRACT = Web3.to_checksum_address("0x7925aD2c2C6DBB5Bd8f8372Ab3693B17E1DAD6B3")

# Setup Web3
RPC_URL = os.getenv("BASE_RPC_URL")
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Approve Max Amount (uint256 max)
MAX_UINT256 = 2**256 - 1

# ✅ USDC ABI (minimal for approval)
erc20_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# ✅ BMX Router ABI (approvePlugin only)
router_abi = [
    {
        "inputs": [{"internalType": "address", "name": "_plugin", "type": "address"}],
        "name": "approvePlugin",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ------------------------------------------------------------------------
def send_tx(contract_function, sender_address, private_key):
    nonce = w3.eth.get_transaction_count(sender_address)
    tx = contract_function.build_transaction({
        'chainId': 8453,
        'gas': 150000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return tx_hash.hex()

# ------------------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting BMX one-time approval...")

    # Approve USDC for BMX Router
    usdc = w3.eth.contract(address=USDC_CONTRACT, abi=erc20_abi)
    usdc_approve_fn = usdc.functions.approve(BMX_ROUTER_CONTRACT, MAX_UINT256)
    tx_hash_1 = send_tx(usdc_approve_fn, WALLET_ADDRESS, PRIVATE_KEY)
    print(f"✅ USDC approval tx sent: https://basescan.org/tx/{tx_hash_1}")

    # Approve Plugin for BMX Router
    router = w3.eth.contract(address=BMX_ROUTER_CONTRACT, abi=router_abi)
    plugin_approve_fn = router.functions.approvePlugin(PLUGIN_CONTRACT)
    tx_hash_2 = send_tx(plugin_approve_fn, WALLET_ADDRESS, PRIVATE_KEY)
    print(f"✅ Plugin approval tx sent: https://basescan.org/tx/{tx_hash_2}")

    print("✅ All approvals sent! Wait for confirmation on BaseScan.")
