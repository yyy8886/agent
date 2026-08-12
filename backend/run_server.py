"""Run the web server. Ctrl+C to stop."""
import uvicorn
from my_agent_next.app.web_server import app

uvicorn.run(app, host='127.0.0.1', port=19842, log_level='error')
