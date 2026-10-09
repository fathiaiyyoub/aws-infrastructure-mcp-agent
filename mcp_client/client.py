import asyncio
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from security import APPROVAL_ENV, make_approval_grant


def build_server_params(approval_grant=None):
    # MCP does not inherit AWS settings by default. Never forward OpenAI keys
    # or an ambient execution grant. Profiles remain outside the repository.
    env = {key: value for key, value in os.environ.items() if key.startswith("AWS_")}
    for key in ("DEPLOYMENT_ENV", "MONTHLY_BUDGET_USD", "PRODUCTION_ALLOWED"):
        if key in os.environ:
            env[key] = os.environ[key]
    if approval_grant is not None:
        env[APPROVAL_ENV] = approval_grant
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )


async def get_tools():
    async with Client(stdio_client(build_server_params())) as client:
        return await client.list_tools()


async def call_tool(tool_name, arguments=None):
    async with Client(stdio_client(build_server_params())) as client:
        return await client.call_tool(tool_name, arguments or {})


async def call_approved_terraform_tool(tool_name, plan_sha256):
    """Trusted agent path after terminal approval; never an MCP tool."""
    operations = {"apply_terraform_tool": "apply", "destroy_terraform_tool": "destroy"}
    if tool_name not in operations:
        raise ValueError("Not an infrastructure execution tool.")
    grant = make_approval_grant(operations[tool_name], plan_sha256)
    async with Client(stdio_client(build_server_params(grant))) as client:
        return await client.call_tool(tool_name, {"plan_sha256": plan_sha256})


async def get_resources():
    async with Client(stdio_client(build_server_params())) as client:
        return await client.list_resources()


async def read_resource(resource_uri):
    async with Client(stdio_client(build_server_params())) as client:
        return await client.read_resource(resource_uri)


async def get_prompts():
    async with Client(stdio_client(build_server_params())) as client:
        return await client.list_prompts()


async def get_prompt(prompt_name, arguments=None):
    async with Client(stdio_client(build_server_params())) as client:
        return await client.get_prompt(prompt_name, arguments or {})


async def main():
    result = await get_prompt(
        "aws-security-review",
        {"terraform_configuration": "No Terraform configuration available yet."},
    )
    for message in result.messages:
        print(message.content.text)


if __name__ == "__main__":
    asyncio.run(main())
