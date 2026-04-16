"""OData query URL builder with $filter, $select, $expand, etc."""

from __future__ import annotations

from urllib.parse import quote


class ODataQueryBuilder:
    """Builds OData query URLs from structured parameters."""

    def build_query_url(
        self,
        base: str,
        filter_expr: str | None = None,
        select: str | None = None,
        expand: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        orderby: str | None = None,
        count: bool = False,
        search: str | None = None,
        format_json: bool = True,
    ) -> str:
        """Build a full OData query URL with system query options."""
        params: list[str] = []

        if filter_expr:
            params.append(f"$filter={self._sanitize_filter(filter_expr)}")
        if select:
            params.append(f"$select={select}")
        if expand:
            params.append(f"$expand={expand}")
        if top is not None:
            params.append(f"$top={top}")
        if skip is not None:
            params.append(f"$skip={skip}")
        if orderby:
            params.append(f"$orderby={orderby}")
        if count:
            params.append("$count=true")
        if search:
            params.append(f"$search={quote(search)}")
        if format_json:
            params.append("$format=json")

        if params:
            return f"{base}?{'&'.join(params)}"
        return base

    def _sanitize_filter(self, filter_expr: str) -> str:
        """Basic sanitization of filter expressions.

        Prevents obvious injection patterns while allowing
        legitimate OData filter syntax.
        """
        # Block dangerous patterns
        blocked = ["<script", "javascript:", "eval(", "exec("]
        lower = filter_expr.lower()
        for pattern in blocked:
            if pattern in lower:
                raise ValueError(f"Blocked filter pattern: {pattern}")

        return filter_expr

    def build_batch_url(self, base: str) -> str:
        """Build a $batch URL."""
        return f"{base}/$batch"

    def build_count_url(self, base: str) -> str:
        """Build a $count URL."""
        return f"{base}/$count"
