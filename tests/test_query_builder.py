"""Tests for OData query builder."""

import pytest
from odata_mcp.query_builder import ODataQueryBuilder


class TestQueryBuilder:
    """Tests for OData query URL construction."""

    def setup_method(self):
        self.builder = ODataQueryBuilder()
        self.base = "https://example.com/odata/Products"

    def test_no_params(self):
        url = self.builder.build_query_url(self.base, format_json=False)
        assert url == self.base

    def test_filter(self):
        url = self.builder.build_query_url(
            self.base, filter_expr="Price gt 100", format_json=False
        )
        assert "$filter=Price gt 100" in url

    def test_select(self):
        url = self.builder.build_query_url(
            self.base, select="Name,Price", format_json=False
        )
        assert "$select=Name,Price" in url

    def test_expand(self):
        url = self.builder.build_query_url(
            self.base, expand="Category", format_json=False
        )
        assert "$expand=Category" in url

    def test_top_and_skip(self):
        url = self.builder.build_query_url(
            self.base, top=10, skip=20, format_json=False
        )
        assert "$top=10" in url
        assert "$skip=20" in url

    def test_orderby(self):
        url = self.builder.build_query_url(
            self.base, orderby="Name asc", format_json=False
        )
        assert "$orderby=Name asc" in url

    def test_count(self):
        url = self.builder.build_query_url(
            self.base, count=True, format_json=False
        )
        assert "$count=true" in url

    def test_combined_params(self):
        url = self.builder.build_query_url(
            self.base,
            filter_expr="Price gt 50",
            select="Name,Price",
            top=5,
            orderby="Price desc",
            format_json=False,
        )
        assert "$filter=Price gt 50" in url
        assert "$select=Name,Price" in url
        assert "$top=5" in url
        assert "$orderby=Price desc" in url

    def test_format_json_default(self):
        url = self.builder.build_query_url(self.base)
        assert "$format=json" in url

    def test_sanitize_blocks_script(self):
        with pytest.raises(ValueError, match="Blocked"):
            self.builder.build_query_url(
                self.base, filter_expr="<script>alert(1)</script>"
            )

    def test_sanitize_blocks_eval(self):
        with pytest.raises(ValueError, match="Blocked"):
            self.builder.build_query_url(
                self.base, filter_expr="eval(something)"
            )

    def test_batch_url(self):
        url = self.builder.build_batch_url(self.base)
        assert url == f"{self.base}/$batch"

    def test_count_url(self):
        url = self.builder.build_count_url(self.base)
        assert url == f"{self.base}/$count"
