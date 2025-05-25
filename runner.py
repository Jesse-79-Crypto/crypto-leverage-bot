
#!/usr/bin/env python3

"""

Minimal Elite Trading Bot - Test Basic Startup

"""

 

import os

from flask import Flask, jsonify

 

# Basic Flask app to test if gunicorn can import

app = Flask(__name__)

 

@app.route('/health', methods=['GET'])

def health():

    return jsonify({

        "status": "healthy",

        "version": "minimal_test",

        "message": "Basic startup working"

    })

 

@app.route('/', methods=['GET'])

def root():

    return jsonify({

       "message": "Elite Trading Bot - Minimal Test Version",

        "status": "running"

    })

 

if __name__ == '__main__':

    port = int(os.getenv('PORT', 8080))

    app.run(host='0.0.0.0', port=port, debug=False)

 