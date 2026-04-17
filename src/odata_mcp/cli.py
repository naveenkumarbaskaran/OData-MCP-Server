"""CLI entry point for OData MCP Server."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from odata_mcp.server import ODataMCPServer


def main() -> None:
    """Run the OData MCP Server."""
    parser = argparse.ArgumentParser(
        description="OData MCP Server — Connect any OData service to LLMs"
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="OData service root URL (e.g., https://services.odata.org/V4/Northwind/Northwind.svc)",
    )
    parser.add_argument(
        "--auth",
        choices=["none", "basic", "bearer", "oauth2"],
        default="none",
        help="Authentication method",
    )
    parser.add_argument("--user", help="Username for basic auth")
    parser.add_argument("--password", help="Password for basic auth")
    parser.add_argument("--token", help="Bearer token")
    parser.add_argument("--client-id", help="OAuth2 client ID")
    parser.add_argument("--client-secret", help="OAuth2 client secret")
    parser.add_argument("--token-url", help="OAuth2 token endpoint URL")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only generate query/read tools",
    )
    parser.add_argument(
        "--include",
        help="Comma-separated entity set names to include",
    )
    parser.add_argument(
        "--exclude",
        help="Comma-separated entity set names to exclude",
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=3600,
        help="Metadata cache TTL in seconds (default: 3600)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Build auth config
    auth = None
    if args.auth == "basic":
        auth = {"type": "basic", "user": args.user, "password": args.password}
    elif args.auth == "bearer":
        auth = {"type": "bearer", "token": args.token}
    elif args.auth == "oauth2":
        auth = {
            "type": "oauth2",
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "token_url": args.token_url,
        }

    include = args.include.split(",") if args.include else None
    exclude = args.exclude.split(",") if args.exclude else []

    server = ODataMCPServer(
        endpoint=args.endpoint,
        auth=auth,
        read_only=args.read_only,
        include=include,
        exclude=exclude,
        cache_ttl=args.cache_ttl,
    )

    asyncio.run(_run_stdio(server))


async def _run_stdio(server: ODataMCPServer) -> None:
    """Run MCP server over stdio (JSON-RPC)."""
    await server.initialize()

    logger = logging.getLogger("odata_mcp.stdio")
    logger.info("OData MCP Server ready. Listening on stdin...")

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: protocol, sys.stdin.buffer
    )

    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            request = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue

        method = request.get("method")
        req_id = request.get("id")

        if method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": server.get_tools_list()},
            }
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await server.handle_tool_call(tool_name, arguments)
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
