"""Tests for the MCP server tool generation."""

import pytest
from odata_mcp.server import ODataMCPServer, _edm_to_json_type
from odata_mcp.metadata import EntitySet, Property, NavigationProperty


class TestEdmTypeMapping:
    """Test EDM → JSON type conversions."""

    def test_string(self):
        assert _edm_to_json_type("Edm.String") == "string"

    def test_int32(self):
        assert _edm_to_json_type("Edm.Int32") == "integer"

    def test_decimal(self):
        assert _edm_to_json_type("Edm.Decimal") == "number"

    def test_boolean(self):
        assert _edm_to_json_type("Edm.Boolean") == "boolean"

    def test_datetime(self):
        assert _edm_to_json_type("Edm.DateTimeOffset") == "string"

    def test_guid(self):
        assert _edm_to_json_type("Edm.Guid") == "string"

    def test_unknown_defaults_to_string(self):
        assert _edm_to_json_type("Edm.Unknown") == "string"


class TestToolGeneration:
    """Test that tools are generated correctly from entity sets."""

    def _make_server_with_entities(
        self, entity_sets: dict, read_only: bool = False
    ) -> ODataMCPServer:
        server = ODataMCPServer(
            endpoint="https://example.com/odata",
            read_only=read_only,
        )
        server.entity_sets = entity_sets
        server._generate_tools()
        return server

    def _sample_entity_set(self) -> EntitySet:
        return EntitySet(
            name="Products",
            entity_type="Demo.Product",
            properties=[
                Property(name="ProductID", edm_type="Edm.Int32", nullable=False),
                Property(name="Name", edm_type="Edm.String"),
                Property(name="Price", edm_type="Edm.Decimal"),
            ],
            key_properties=[
                Property(name="ProductID", edm_type="Edm.Int32", nullable=False),
            ],
        )

    def test_read_only_generates_2_tools(self):
        es = self._sample_entity_set()
        server = self._make_server_with_entities(
            {"Products": es}, read_only=True
        )
        names = [t["name"] for t in server.tools]
        assert "query_Products" in names
        assert "get_Products_by_key" in names
        assert "create_Products" not in names
        assert len(server.tools) == 2

    def test_read_write_generates_5_tools(self):
        es = self._sample_entity_set()
        server = self._make_server_with_entities(
            {"Products": es}, read_only=False
        )
        names = [t["name"] for t in server.tools]
        assert "query_Products" in names
        assert "get_Products_by_key" in names
        assert "create_Products" in names
        assert "update_Products" in names
        assert "delete_Products" in names

    def test_query_tool_has_filter_param(self):
        es = self._sample_entity_set()
        server = self._make_server_with_entities({"Products": es})
        query_tool = next(t for t in server.tools if t["name"] == "query_Products")
        props = query_tool["inputSchema"]["properties"]
        assert "filter" in props
        assert "top" in props
        assert "orderby" in props

    def test_get_tool_requires_key(self):
        es = self._sample_entity_set()
        server = self._make_server_with_entities({"Products": es})
        get_tool = next(t for t in server.tools if t["name"] == "get_Products_by_key")
        assert "ProductID" in get_tool["inputSchema"]["required"]

    def test_include_filter(self):
        server = ODataMCPServer(
            endpoint="https://example.com/odata",
            include=["Products"],
        )
        server.entity_sets = {
            "Products": self._sample_entity_set(),
            "Categories": EntitySet(name="Categories", entity_type="Demo.Category"),
        }
        server._apply_filters()
        assert "Products" in server.entity_sets
        assert "Categories" not in server.entity_sets

    def test_exclude_filter(self):
        server = ODataMCPServer(
            endpoint="https://example.com/odata",
            exclude=["AuditLogs"],
        )
        server.entity_sets = {
            "Products": self._sample_entity_set(),
            "AuditLogs": EntitySet(name="AuditLogs", entity_type="Demo.AuditLog"),
        }
        server._apply_filters()
        assert "Products" in server.entity_sets
        assert "AuditLogs" not in server.entity_sets
