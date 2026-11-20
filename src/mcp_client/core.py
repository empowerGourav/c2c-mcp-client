import asyncio

from anthropic import Anthropic, PaymentRequiredError
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters
from mcp_types import TextContent

load_dotenv()

MODEL = "claude-haiku-5-5"
# The model thinks adaptively, so max_tokens leaves room for both thinking and the reply.
MAX_TOKENS = 10000
MAX_TOOL_TURNS = 10
INSUFFICIENT_CREDITS_MESSAGE = (
    "Anthropic API credits are insufficient. Check Plans & Billing, add credits, "
    "and try again."
)
anthropic = Anthropic()


class InsufficientCreditsError(Exception):
    """Raised when Anthropic rejects a request because the account has no credits."""


def server_params(server_script_path: str) -> StdioServerParameters:
    """Describe the subprocess that runs an MCP server."""
    if server_script_path.endswith(".py"):
        command = "python"
    elif server_script_path.endswith(".js"):
        command = "node"
    else:
        raise ValueError("Server script must be a .py or .js file")

    return StdioServerParameters(command=command, args=[server_script_path])


async def process_query(client: Client, query: str) -> str:
    """Process a query using Claude and available MCP tools."""
    messages = [{"role": "user", "content": query}]

    tool_list = await client.list_tools()
    available_tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tool_list.tools
    ]

    final_text = []
    try:
        response = await asyncio.to_thread(
            anthropic.messages.create,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
            tools=available_tools,
        )
    except PaymentRequiredError as error:
        raise InsufficientCreditsError(INSUFFICIENT_CREDITS_MESSAGE) from error

    for _ in range(MAX_TOOL_TURNS):
        tool_uses = []
        for content in response.content:
            if content.type == "text":
                final_text.append(content.text)
            elif content.type == "tool_use":
                tool_uses.append(content)

        if not tool_uses:
            return "\n".join(final_text)

        tool_results = []
        for tool_use in tool_uses:
            result = await client.call_tool(tool_use.name, tool_use.input)
            final_text.append(
                f"[Calling tool {tool_use.name} with args {tool_use.input}]"
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "\n".join(
                        block.text
                        for block in result.content
                        if isinstance(block, TextContent)
                    ),
                    "is_error": result.is_error,
                }
            )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        try:
            response = await asyncio.to_thread(
                anthropic.messages.create,
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=messages,
                tools=available_tools,
            )
        except PaymentRequiredError as error:
            raise InsufficientCreditsError(INSUFFICIENT_CREDITS_MESSAGE) from error

    final_text.extend(
        content.text for content in response.content if content.type == "text"
    )
    if any(content.type == "tool_use" for content in response.content):
        final_text.append(f"[Stopped after {MAX_TOOL_TURNS} tool-use turns]")
    return "\n".join(final_text)
