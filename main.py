from flask import Flask, request, jsonify
import os
import json
import traceback
from agent3_runner import execute_trade_on_gains

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Agent 3 is live!"

@app.route("/execute", methods=["POST"])
def handle_trade_signal():
    try:
        signal = request.get_json(force=True)
        print("📩 Signal received:", signal)

        if not signal:
            return jsonify({"status": "error", "message": "No signal payload received"}), 400

        # Execute trade and capture result
        result = execute_trade_on_gains(signal)

        # Ensure result is serializable and structured
        if isinstance(result, dict):
            print("✅ Trade executed successfully:", result)
            return jsonify(result), 200
        else:
            return jsonify({"status": "error", "message": "Unexpected response format from trade executor."}), 500

    except Exception as e:
        print("❌ Exception occurred during trade execution:")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }), 500

if __name__ == "__main__":
    # Run locally (ignored by Railway)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
