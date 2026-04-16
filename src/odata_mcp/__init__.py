"""OData MCP Server — Connect any OData V2/V4 service to LLMs via MCP."""

__version__ = "0.1.0"

from odata_mcp.server import ODataMCPServer
from odata_mcp.metadata import MetadataParser
from odata_mcp.query_builder import ODataQueryBuilder
from odata_mcp.client import ODataClient

__all__ = [
    "ODataMCPServer",
    "MetadataParser",
    "ODataQueryBuilder",
    "ODataClient",
]
