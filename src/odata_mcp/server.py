"""MCP server that auto-generates tools from OData $metadata."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from odata_mcp.metadata import MetadataParser, EntitySet, Property
from odata_mcp.query_builder import ODataQueryBuilder
from odata_mcp.client import ODataClient

logger = logging.getLogger(__name__)


class ODataMCPServer:
    """Auto-generates MCP tools from OData $metadata and serves them."""

    def __init__(
        self,
        endpoint: str,
        auth: dict[str, str] | None = None,
        read_only: bool = False,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        cache_ttl: int = 3600,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.read_only = read_only
        self.include = include
        self.exclude = exclude or []
        self.cache_ttl = cache_ttl

        self.client = ODataClient(self.endpoint, auth=auth)
        self.parser = MetadataParser()
        self.query_builder = ODataQueryBuilder()
        self.entity_sets: dict[str, EntitySet] = {}
        self.tools: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        """Fetch $metadata, parse it, and generate tool definitions."""
        logger.info("Fetching $metadata from %s", self.endpoint)
        metadata_xml = await self.client.fetch_metadata()

        self.entity_sets = self.parser.parse(metadata_xml)
        logger.info(
            "Parsed %d entity sets from metadata", len(self.entity_sets)
        )

        self._apply_filters()
        self._generate_tools()

        logger.info("Generated %d MCP tools", len(self.tools))

    def _apply_filters(self) -> None:
        """Apply include/exclude filters to entity sets."""
        if self.include:
            self.entity_sets = {
                k: v for k, v in self.entity_sets.items() if k in self.include
            }
        for name in self.exclude:
            self.entity_sets.pop(name, None)

    def _generate_tools(self) -> None:
        """Generate MCP tool definitions from parsed entity sets."""
        self.tools = []

        for name, entity_set in self.entity_sets.items():
            # Query tool (list/search)
            self.tools.append(self._make_query_tool(name, entity_set))

            # Get-by-key tool
            if entity_set.key_properties:
                self.tools.append(self._make_get_tool(name, entity_set))

            # Write tools (if not read-only)
            if not self.read_only:
                self.tools.append(self._make_create_tool(name, entity_set))
                self.tools.append(self._make_update_tool(name, entity_set))
                self.tools.append(self._make_delete_tool(name, entity_set))

    def _make_query_tool(
        self, name: str, entity_set: EntitySet
    ) -> dict[str, Any]:
        """Generate a query/list tool for an entity set."""
        filterable = [
            p.name for p in entity_set.properties if p.filterable
        ]

        return {
            "name": f"query_{name}",
            "description": (
                f"Query {name} entities. "
                f"Filterable fields: {', '.join(filterable[:15])}"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": (
                            "OData $filter expression. Examples: "
                            "'Name eq \\'Milk\\'', 'Price gt 100', "
                            "'startswith(Name, \\'A\\')'"
                        ),
                    },
                    "select": {
                        "type": "string",
                        "description": "Comma-separated field names to return",
                    },
                    "expand": {
                        "type": "string",
                        "description": "Navigation properties to expand",
                    },
                    "top": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20, max: 100)",
                        "default": 20,
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Number of results to skip (for pagination)",
                    },
                    "orderby": {
                        "type": "string",
                        "description": "Sort expression. Example: 'Name asc, Price desc'",
                    },
                    "count": {
                        "type": "boolean",
                        "description": "Include total count in response (V4 only)",
                    },
                },
            },
        }

    def _make_get_tool(
        self, name: str, entity_set: EntitySet
    ) -> dict[str, Any]:
        """Generate a get-by-key tool for an entity set."""
        key_props = entity_set.key_properties
        properties: dict[str, Any] = {}
        required: list[str] = []

        for kp in key_props:
            properties[kp.name] = {
                "type": _edm_to_json_type(kp.edm_type),
                "description": f"Key field: {kp.name}",
            }
            required.append(kp.name)

        properties["expand"] = {
            "type": "string",
            "description": "Navigation properties to expand",
        }
        properties["select"] = {
            "type": "string",
            "description": "Comma-separated field names to return",
        }

        return {
            "name": f"get_{name}_by_key",
            "description": f"Get a single {name} entity by its key ({', '.join(required)})",
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def _make_create_tool(
        self, name: str, entity_set: EntitySet
    ) -> dict[str, Any]:
        """Generate a create tool for an entity set."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for prop in entity_set.properties:
            if prop.read_only:
                continue
            properties[prop.name] = {
                "type": _edm_to_json_type(prop.edm_type),
                "description": prop.label or prop.name,
            }
            if not prop.nullable:
                required.append(prop.name)

        return {
            "name": f"create_{name}",
            "description": f"Create a new {name} entity",
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def _make_update_tool(
        self, name: str, entity_set: EntitySet
    ) -> dict[str, Any]:
        """Generate an update (PATCH) tool for an entity set."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for kp in entity_set.key_properties:
            properties[kp.name] = {
                "type": _edm_to_json_type(kp.edm_type),
                "description": f"Key: {kp.name}",
            }
            required.append(kp.name)

        properties["fields"] = {
            "type": "object",
            "description": "Fields to update as key-value pairs",
        }
        required.append("fields")

        return {
            "name": f"update_{name}",
            "description": f"Update an existing {name} entity by key",
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def _make_delete_tool(
        self, name: str, entity_set: EntitySet
    ) -> dict[str, Any]:
        """Generate a delete tool for an entity set."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for kp in entity_set.key_properties:
            properties[kp.name] = {
                "type": _edm_to_json_type(kp.edm_type),
                "description": f"Key: {kp.name}",
            }
            required.append(kp.name)

        return {
            "name": f"delete_{name}",
            "description": f"Delete a {name} entity by key",
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    async def handle_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool call against the OData service."""
        parts = tool_name.split("_", 1)
        if len(parts) < 2:
            return {"error": f"Unknown tool: {tool_name}"}

        action = parts[0]
        entity_name = parts[1]

        # Handle get_X_by_key pattern
        if entity_name.endswith("_by_key"):
            entity_name = entity_name[:-7]
            action = "get"

        entity_set = self.entity_sets.get(entity_name)
        if not entity_set:
            return {"error": f"Unknown entity set: {entity_name}"}

        try:
            if action == "query":
                return await self._execute_query(entity_name, arguments)
            elif action == "get":
                return await self._execute_get(
                    entity_name, entity_set, arguments
                )
            elif action == "create":
                return await self._execute_create(entity_name, arguments)
            elif action == "update":
                return await self._execute_update(
                    entity_name, entity_set, arguments
                )
            elif action == "delete":
                return await self._execute_delete(
                    entity_name, entity_set, arguments
                )
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            logger.exception("Tool call failed: %s", tool_name)
            return {"error": str(e)}

    async def _execute_query(
        self, entity_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a query against an entity set."""
        url = self.query_builder.build_query_url(
            base=f"{self.endpoint}/{entity_name}",
            filter_expr=args.get("filter"),
            select=args.get("select"),
            expand=args.get("expand"),
            top=min(args.get("top", 20), 100),
            skip=args.get("skip"),
            orderby=args.get("orderby"),
            count=args.get("count", False),
        )
        return await self.client.get(url)

    async def _execute_get(
        self,
        entity_name: str,
        entity_set: EntitySet,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch a single entity by key."""
        key_parts = []
        for kp in entity_set.key_properties:
            val = args[kp.name]
            if kp.edm_type in ("Edm.String", "Edm.Guid"):
                key_parts.append(f"{kp.name}='{val}'")
            else:
                key_parts.append(f"{kp.name}={val}")

        key_str = ",".join(key_parts)
        url = f"{self.endpoint}/{entity_name}({key_str})"

        params: dict[str, str] = {}
        if args.get("expand"):
            params["$expand"] = args["expand"]
        if args.get("select"):
            params["$select"] = args["select"]

        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"

        return await self.client.get(url)

    async def _execute_create(
        self, entity_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new entity."""
        url = f"{self.endpoint}/{entity_name}"
        return await self.client.post(url, json=args)

    async def _execute_update(
        self,
        entity_name: str,
        entity_set: EntitySet,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an entity by key."""
        key_parts = []
        for kp in entity_set.key_properties:
            val = args[kp.name]
            if kp.edm_type in ("Edm.String", "Edm.Guid"):
                key_parts.append(f"{kp.name}='{val}'")
            else:
                key_parts.append(f"{kp.name}={val}")

        key_str = ",".join(key_parts)
        url = f"{self.endpoint}/{entity_name}({key_str})"
        fields = args.get("fields", {})
        return await self.client.patch(url, json=fields)

    async def _execute_delete(
        self,
        entity_name: str,
        entity_set: EntitySet,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Delete an entity by key."""
        key_parts = []
        for kp in entity_set.key_properties:
            val = args[kp.name]
            if kp.edm_type in ("Edm.String", "Edm.Guid"):
                key_parts.append(f"{kp.name}='{val}'")
            else:
                key_parts.append(f"{kp.name}={val}")

        key_str = ",".join(key_parts)
        url = f"{self.endpoint}/{entity_name}({key_str})"
        return await self.client.delete(url)

    def get_tools_list(self) -> list[dict[str, Any]]:
        """Return all generated tool definitions."""
        return self.tools


def _edm_to_json_type(edm_type: str) -> str:
    """Convert OData EDM type to JSON Schema type."""
    mapping = {
        "Edm.String": "string",
        "Edm.Int16": "integer",
        "Edm.Int32": "integer",
        "Edm.Int64": "integer",
        "Edm.Decimal": "number",
        "Edm.Double": "number",
        "Edm.Single": "number",
        "Edm.Boolean": "boolean",
        "Edm.DateTime": "string",
        "Edm.DateTimeOffset": "string",
        "Edm.Date": "string",
        "Edm.Time": "string",
        "Edm.TimeOfDay": "string",
        "Edm.Guid": "string",
        "Edm.Binary": "string",
        "Edm.Byte": "integer",
    }
    return mapping.get(edm_type, "string")
