from waitress import serve
from app import app

serve(
    app,
    host='0.0.0.0',
    port=5000,
    threads=8,
    backlog=2048,
    channel_timeout=120,
    connection_limit=2000,
)
