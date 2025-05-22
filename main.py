#!/usr/bin/env python3
"""
Entrypoint for Gunicorn / your container.
Imports the Flask app (with its /execute route) from runner.py
and adds a simple healthcheck at “/”.
"""

import os
from runner import app     # <-- runner.py must define `app = Flask(__name__)`

@app.route("/")
def home():
    return "✅ Agent 3 is live!"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
