import argparse
import asyncio
from pathlib import Path

from mcp import Client
from mcp.client.stdio import stdio_client
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .core import process_query, server_params

console = Console()


async def chat_loop(client: Client) -> None:
    """Run an interactive chat loop with persistent history and completion."""
    tools = await client.list_tools()
    tool_names = [tool.name for tool in tools.tools]
    console.print(
        f"Connected to server with [bold]{len(tools.tools)}[/] tools."
    )
    commands = ["quit", "exit", "/help", "/tools", "/clear"]
    session = PromptSession(
        history=FileHistory(str(Path.home() / ".mcp-client-history")),
        completer=WordCompleter(commands + tool_names, ignore_case=True, WORD=True),
    )

    console.print(
        Panel(
            "Ask questions using the connected MCP server.\n"
            "Commands: [bold]/help[/], [bold]/tools[/], [bold]/clear[/], [bold]quit[/]",
            title="MCP Client",
            border_style="cyan",
        )
    )

    while True:
        try:
            query = (await session.prompt_async("Query> ")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not query:
            continue
        command = query.lower()
        if command in {"quit", "exit"}:
            break
        if command == "/help":
            console.print(
                "Enter a question, use [bold]/tools[/] to list server tools, "
                "[bold]/clear[/] to clear the screen, or [bold]quit[/] to exit."
            )
            continue
        if command == "/tools":
            table = Table(title="Available MCP tools")
            table.add_column("Tool", style="cyan")
            table.add_column("Description")
            for tool in tools.tools:
                table.add_row(tool.name, tool.description or "")
            console.print(table)
            continue
        if command == "/clear":
            console.clear()
            continue

        try:
            response = await process_query(client, query)
            console.print(Panel(Markdown(response), title="Claude", border_style="green"))
        except Exception as error:
            console.print(f"[bold red]Error:[/] {error}")


async def run(server_script_path: str) -> None:
    async with Client(stdio_client(server_params(server_script_path))) as client:
        await chat_loop(client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with an MCP server.")
    parser.add_argument("server_script", help="Path to the MCP server (.py or .js)")
    args = parser.parse_args()
    asyncio.run(run(args.server_script))


if __name__ == "__main__":
    main()
