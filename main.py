from flask import Flask, request, jsonify
import os
import json
import traceback  # ✅ Added for full error tracing
from agent3_runner import execute_trade_on_gains  # This must be in agent3_runner.py

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
            return jsonify({"error": "No signal payload received"}), 400

        result = execute_trade_on_gains(signal)
        print("✅ Trade executed successfully:", result)

        return jsonify(result)  # Return full trade result
    except Exception as e:
        print("❌ Exception occurred during trade execution:")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
