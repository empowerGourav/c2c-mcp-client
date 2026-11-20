import os

from .web import create_app

server_url = os.environ.get("MCP_SERVER_URL")
if not server_url:
    raise RuntimeError("Set the MCP_SERVER_URL environment variable.")

app = create_app(server_url=server_url)
