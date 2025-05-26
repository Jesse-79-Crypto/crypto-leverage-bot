
#!/usr/bin/env python3
"""
Heroku entry point for Elite Trading Bot
Imports the main Flask app from runner.py
"""

from runner import app

if __name__ == '__main__':
    # This ensures the app runs correctly when called directly
    # but Heroku will use gunicorn main:app
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
