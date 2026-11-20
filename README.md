# MCP Client

An interactive Claude client for MCP servers.

## Terminal interface

Run the client with a Python or JavaScript MCP server:

```powershell
uv run mcp-client path\to\server.py
```

The terminal UI renders Markdown and tool lists, saves prompt history in
`~\.mcp-client-history`, and offers completion for client commands and server
tool names. Use `/help`, `/tools`, `/clear`, or `quit` in the prompt.

The root `client.py` remains available as a direct launcher:

```powershell
uv run python client.py path\to\server.py
```

## Browser interface

Start the local web UI with:

```powershell
uv run mcp-client-web path\to\server.py
```

Open `http://127.0.0.1:8000` in a browser. Use `--host` and `--port` to choose
a different bind address or port.

## Vercel

The Vercel entrypoint connects to a remote Streamable HTTP MCP server. Configure
these environment variables in the Vercel project settings:

- `ANTHROPIC_API_KEY`
- `MCP_SERVER_URL`

Do not commit either value. `.vercelignore` excludes local `.env` files from
deployment bundles. Rotate any credential that has been shared in chat before
using it in a deployment.