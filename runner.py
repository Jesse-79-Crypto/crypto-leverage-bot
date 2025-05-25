from flask import Flask, jsonify

import os

from web3 import Web3

 

app = Flask(__name__)

 

# Initialize Web3 connection

def get_web3_connection():

    try:

        rpc_url = os.getenv('BASE_RPC_URL')

        if not rpc_url:

            return None, "BASE_RPC_URL not configured"

       

        w3 = Web3(Web3.HTTPProvider(rpc_url))

       

        # Test connection

        if w3.is_connected():

            latest_block = w3.eth.block_number

            return w3, f"Connected to Base network, latest block: {latest_block}"

        else:

            return None, "Failed to connect to Base network"

    except Exception as e:

        return None, f"Web3 connection error: {str(e)}"

 

@app.route('/')

def hello():

    return jsonify({"message": "Hello World", "status": "working"})

 

@app.route('/health')

def health():

    return jsonify({"status": "healthy"})

 

@app.route('/web3-test')

def web3_test():

    w3, message = get_web3_connection()

   

    if w3:

        # Get some additional network info

        try:

            latest_block = w3.eth.get_block('latest')

            base_fee = latest_block.get('baseFeePerGas', 0)

            chain_id = w3.eth.chain_id

           

            return jsonify({

                "status": "success",

                "message": message,

                "chain_id": chain_id,

                "latest_block": latest_block['number'],

                "base_fee_gwei": Web3.from_wei(base_fee, 'gwei') if base_fee else 0,

                "network": "Base Mainnet" if chain_id == 8453 else f"Chain {chain_id}"

            })

        except Exception as e:

            return jsonify({

                "status": "partial_success",

                "message": message,

                "error": f"Additional info failed: {str(e)}"

            })

    else:

        return jsonify({

            "status": "error",

            "message": message

        })

 

if __name__ == '__main__':

    import os

    port = int(os.getenv('PORT', 8080))

    app.run(host='0.0.0.0', port=port)

 

 