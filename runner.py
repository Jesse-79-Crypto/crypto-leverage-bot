from flask import Flask, jsonify

import os

 

app = Flask(__name__)

 

@app.route('/')

def hello():

    return jsonify({"message": "Hello World", "status": "working"})

 

@app.route('/health')

def health():

    return jsonify({"status": "healthy"})

 

@app.route('/env-test')

def env_test():

    """Test environment variables without importing web3"""

    rpc_url = os.getenv('BASE_RPC_URL', 'Not set')

    chain_id = os.getenv('CHAIN_ID', 'Not set')

    usdc_address = os.getenv('USDC_ADDRESS', 'Not set')

    gains_address = os.getenv('GAINS_CONTRACT_ADDRESS', 'Not set')

   

    # Hide sensitive parts of RPC URL and private key

    rpc_display = rpc_url[:50] + "..." if len(rpc_url) > 50 else rpc_url

    has_private_key = "Set" if os.getenv('WALLET_PRIVATE_KEY') else "Not set"

   

    return jsonify({

        "status": "environment_check",

        "rpc_url": rpc_display,

        "chain_id": chain_id,

        "usdc_address": usdc_address,

        "gains_contract_address": gains_address,

        "private_key": has_private_key

    })

 

if __name__ == '__main__':

    import os

    port = int(os.getenv('PORT', 8080))

    app.run(host='0.0.0.0', port=port)