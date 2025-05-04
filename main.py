from flask import Flask, request, jsonify
import os
import json
from agent3_runner import execute_trade_on_gains  # This must be in agent3_runner.py

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Agent 3 is live!"

@app.route("/execute", methods=["POST"])
def handle_trade_signal():
    try:
        signal = request.get_json(force=True)
        if not signal:
            return jsonify({"error": "No signal payload received"}), 400

        result = execute_trade_on_gains(signal)
        return jsonify(result)  # Return full result dictionary
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
