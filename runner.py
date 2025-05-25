from flask import Flask, jsonify

 

app = Flask(__name__)

 

@app.route('/')

def hello():

    return jsonify({"message": "Hello World", "status": "working"})

 

@app.route('/health')

def health():

    return jsonify({"status": "healthy"})

 

if __name__ == '__main__':

    import os

    port = int(os.getenv('PORT', 8080))

    app.run(host='0.0.0.0', port=port)

