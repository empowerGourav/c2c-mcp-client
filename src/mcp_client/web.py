import argparse
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

from .core import InsufficientCreditsError, process_query, server_params

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MCP Client</title>
  <style>
    :root { color-scheme: dark; font: 16px/1.5 system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #101318; color: #e8edf5; }
    main { width: min(900px, 100%); min-height: 100vh; margin: auto; padding: 28px 20px; display: flex; flex-direction: column; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #29313d; padding-bottom: 18px; }
    h1 { margin: 0; font-size: 1.25rem; }
    #status { color: #9aa8bb; font-size: .9rem; }
    #tools { display: flex; flex-wrap: wrap; gap: 8px; padding: 14px 0; }
    .tool { border: 1px solid #394557; border-radius: 999px; padding: 3px 10px; color: #b7c8e2; font-size: .8rem; }
    #messages { flex: 1; display: flex; flex-direction: column; gap: 14px; padding: 12px 0 24px; }
    .message { max-width: 90%; border: 1px solid #29313d; border-radius: 12px; padding: 12px 16px; }
    .message.user { align-self: flex-end; background: #1b2b42; }
    .message.assistant { align-self: flex-start; background: #171c24; }
    .label { color: #9aa8bb; font-size: .75rem; margin-bottom: 5px; }
    .content { white-space: pre-wrap; overflow-wrap: anywhere; }
    form { display: flex; gap: 10px; border-top: 1px solid #29313d; padding-top: 16px; }
    textarea { flex: 1; min-height: 54px; max-height: 180px; resize: vertical; border: 1px solid #394557; border-radius: 10px; padding: 12px; background: #171c24; color: inherit; font: inherit; }
    button { border: 0; border-radius: 10px; padding: 0 20px; background: #6ea8fe; color: #101318; font: inherit; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .55; cursor: wait; }
    .hint { margin: 8px 0 0; color: #8290a3; font-size: .8rem; text-align: right; }
    @media (max-width: 560px) { main { padding: 18px 12px; } .message { max-width: 100%; } }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>MCP Client</h1>
      <span id="status">Connecting to MCP server...</span>
    </header>
    <section id="tools" aria-label="Available tools"></section>
    <section id="messages" aria-live="polite">
      <article class="message assistant"><div class="label">Assistant</div><div class="content">Ask a question to get started.</div></article>
    </section>
    <form id="chat-form">
      <textarea id="query" aria-label="Your message" placeholder="Message the MCP assistant..." required></textarea>
      <button id="send" type="submit">Send</button>
    </form>
    <p class="hint">Press Ctrl+Enter to send</p>
  </main>
  <script>
    const status = document.querySelector("#status");
    const messages = document.querySelector("#messages");
    const form = document.querySelector("#chat-form");
    const queryInput = document.querySelector("#query");
    const sendButton = document.querySelector("#send");

    function addMessage(role, text) {
      const article = document.createElement("article");
      article.className = `message ${role}`;
      const label = document.createElement("div");
      label.className = "label";
      label.textContent = role === "user" ? "You" : "Assistant";
      const content = document.createElement("div");
      content.className = "content";
      content.textContent = text;
      article.append(label, content);
      messages.append(article);
      article.scrollIntoView({ behavior: "smooth", block: "end" });
      return content;
    }

    async function loadTools() {
      try {
        const response = await fetch("/api/tools");
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        const tools = await response.json();
        const container = document.querySelector("#tools");
        for (const tool of tools) {
          const chip = document.createElement("span");
          chip.className = "tool";
          chip.textContent = tool.name;
          chip.title = tool.description || tool.name;
          container.append(chip);
        }
        status.textContent = `Connected · ${tools.length} tool${tools.length === 1 ? "" : "s"}`;
      } catch (error) {
        status.textContent = `Connection error · ${error.message}`;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const query = queryInput.value.trim();
      if (!query || sendButton.disabled) return;
      addMessage("user", query);
      queryInput.value = "";
      const reply = addMessage("assistant", "Thinking...");
      sendButton.disabled = true;
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query })
        });
        const body = await response.text();
        let result = {};
        if (body) {
          try {
            result = JSON.parse(body);
          } catch {
            result = {};
          }
        }
        if (!response.ok) {
          const plainTextError =
            response.headers.get("content-type")?.startsWith("text/plain") &&
            body !== "Internal Server Error"
              ? body
              : "";
          const detail = typeof result.detail === "string" ? result.detail : plainTextError;
          throw new Error(detail || `Request failed (${response.status}). Please try again.`);
        }
        if (typeof result.response !== "string") {
          throw new Error("The server returned an invalid response.");
        }
        reply.textContent = result.response;
      } catch (error) {
        reply.textContent = `Error: ${error.message}`;
      } finally {
        sendButton.disabled = false;
        queryInput.focus();
      }
    });

    queryInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
    loadTools();
  </script>
</body>
</html>"""


class ChatRequest(BaseModel):
    query: str


def create_app(
    server_script_path: str | None = None,
    *,
    server_url: str | None = None,
) -> FastAPI:
    if server_script_path is not None and server_url is not None:
        raise ValueError("Specify either a server script or a server URL, not both.")
    if server_script_path is None and server_url is None:
        raise ValueError("A server script or server URL is required.")

    connection: str | StdioServerParameters
    if server_url is not None:
        connection = server_url
    else:
        connection = server_params(server_script_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        transport = stdio_client(connection) if isinstance(connection, StdioServerParameters) else connection
        async with Client(transport) as client:
            app.state.mcp_client = client
            app.state.chat_lock = asyncio.Lock()
            yield

    app = FastAPI(title="MCP Client", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE

    @app.get("/api/tools")
    async def list_tools(request: Request) -> list[dict[str, str]]:
        client: Client = request.app.state.mcp_client
        result = await client.list_tools()
        return [
            {"name": tool.name, "description": tool.description or ""}
            for tool in result.tools
        ]

    @app.post("/api/chat")
    async def chat(body: ChatRequest, request: Request) -> dict[str, str]:
        query = body.query.strip()
        if not query:
            raise HTTPException(status_code=422, detail="Query cannot be empty.")

        client: Client = request.app.state.mcp_client
        async with request.app.state.chat_lock:
            try:
                response = await process_query(client, query)
            except InsufficientCreditsError as error:
                raise HTTPException(status_code=402, detail=str(error)) from error
        return {"response": response}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MCP client web interface.")
    parser.add_argument("server_script", help="Path to the MCP server (.py or .js)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(
        create_app(server_script_path=args.server_script),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
