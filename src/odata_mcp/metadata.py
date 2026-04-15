"""OData $metadata XML parser — supports EDMX V2 and V4."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

# Common EDMX namespaces
EDMX_NS = {
    "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
    "edmx_v2": "http://schemas.microsoft.com/ado/2007/06/edmx",
    "edm": "http://docs.oasis-open.org/odata/ns/edm",
    "edm_v2": "http://schemas.microsoft.com/ado/2008/09/edm",
    "edm_v3": "http://schemas.microsoft.com/ado/2009/11/edm",
    "sap": "http://www.sap.com/Protocols/SAPData",
}


@dataclass
class Property:
    """A property (field) in an OData entity type."""

    name: str
    edm_type: str
    nullable: bool = True
    filterable: bool = True
    sortable: bool = True
    read_only: bool = False
    label: str | None = None
    max_length: int | None = None


@dataclass
class NavigationProperty:
    """A navigation (relationship) property."""

    name: str
    target_entity: str
    is_collection: bool = False


@dataclass
class EntitySet:
    """An OData entity set parsed from $metadata."""

    name: str
    entity_type: str
    properties: list[Property] = field(default_factory=list)
    key_properties: list[Property] = field(default_factory=list)
    navigation_properties: list[NavigationProperty] = field(
        default_factory=list
    )


class MetadataParser:
    """Parses OData EDMX $metadata XML into structured EntitySet objects."""

    def parse(self, xml_text: str) -> dict[str, EntitySet]:
        """Parse $metadata XML and return entity sets keyed by name."""
        root = ET.fromstring(xml_text)
        version = self._detect_version(root)

        if version == "v4":
            return self._parse_v4(root)
        else:
            return self._parse_v2(root)

    def _detect_version(self, root: ET.Element) -> str:
        """Detect whether this is V2/V3 or V4 metadata."""
        tag = root.tag.lower()
        if "oasis-open.org" in tag:
            return "v4"
        return "v2"

    def _parse_v4(self, root: ET.Element) -> dict[str, EntitySet]:
        """Parse OData V4 EDMX metadata."""
        ns = {"edmx": EDMX_NS["edmx"], "edm": EDMX_NS["edm"]}
        result: dict[str, EntitySet] = {}

        # Parse entity types
        entity_types: dict[str, dict[str, Any]] = {}
        for schema in root.findall(".//edm:Schema", ns):
            namespace = schema.get("Namespace", "")

            for et in schema.findall("edm:EntityType", ns):
                type_name = et.get("Name", "")
                fqn = f"{namespace}.{type_name}"

                props = self._parse_properties_v4(et, ns)
                keys = self._parse_keys_v4(et, ns, props)
                nav_props = self._parse_nav_props_v4(et, ns)

                entity_types[fqn] = {
                    "properties": props,
                    "keys": keys,
                    "nav_props": nav_props,
                }
                # Also index by short name
                entity_types[type_name] = entity_types[fqn]

        # Parse entity container → entity sets
        for container in root.findall(".//edm:EntityContainer", ns):
            for es in container.findall("edm:EntitySet", ns):
                es_name = es.get("Name", "")
                es_type = es.get("EntityType", "")

                type_info = entity_types.get(es_type, {})
                if not type_info:
                    short = es_type.rsplit(".", 1)[-1]
                    type_info = entity_types.get(short, {})

                entity_set = EntitySet(
                    name=es_name,
                    entity_type=es_type,
                    properties=type_info.get("properties", []),
                    key_properties=type_info.get("keys", []),
                    navigation_properties=type_info.get("nav_props", []),
                )
                result[es_name] = entity_set

        return result

    def _parse_properties_v4(
        self, entity_type: ET.Element, ns: dict[str, str]
    ) -> list[Property]:
        """Parse properties from a V4 EntityType element."""
        props: list[Property] = []
        for p in entity_type.findall("edm:Property", ns):
            prop = Property(
                name=p.get("Name", ""),
                edm_type=p.get("Type", "Edm.String"),
                nullable=p.get("Nullable", "true").lower() == "true",
                max_length=_safe_int(p.get("MaxLength")),
            )
            props.append(prop)
        return props

    def _parse_keys_v4(
        self,
        entity_type: ET.Element,
        ns: dict[str, str],
        props: list[Property],
    ) -> list[Property]:
        """Parse key properties from V4 EntityType."""
        keys: list[Property] = []
        key_elem = entity_type.find("edm:Key", ns)
        if key_elem is not None:
            prop_map = {p.name: p for p in props}
            for ref in key_elem.findall("edm:PropertyRef", ns):
                key_name = ref.get("Name", "")
                if key_name in prop_map:
                    keys.append(prop_map[key_name])
        return keys

    def _parse_nav_props_v4(
        self, entity_type: ET.Element, ns: dict[str, str]
    ) -> list[NavigationProperty]:
        """Parse navigation properties from V4 EntityType."""
        nav_props: list[NavigationProperty] = []
        for np in entity_type.findall("edm:NavigationProperty", ns):
            nav_type = np.get("Type", "")
            is_collection = nav_type.startswith("Collection(")
            if is_collection:
                target = nav_type[len("Collection(") : -1]
            else:
                target = nav_type

            nav_props.append(
                NavigationProperty(
                    name=np.get("Name", ""),
                    target_entity=target,
                    is_collection=is_collection,
                )
            )
        return nav_props

    def _parse_v2(self, root: ET.Element) -> dict[str, EntitySet]:
        """Parse OData V2/V3 EDMX metadata."""
        # Try multiple V2/V3 namespace variants
        for edm_uri in [EDMX_NS["edm_v3"], EDMX_NS["edm_v2"]]:
            ns = {"edm": edm_uri}
            schemas = root.findall(".//{%s}Schema" % edm_uri)
            if schemas:
                return self._parse_v2_with_ns(root, edm_uri)

        # Fallback: try without namespace
        return self._parse_v2_no_ns(root)

    def _parse_v2_with_ns(
        self, root: ET.Element, edm_uri: str
    ) -> dict[str, EntitySet]:
        """Parse V2 metadata with a known EDM namespace."""
        result: dict[str, EntitySet] = {}
        entity_types: dict[str, dict[str, Any]] = {}

        for schema in root.iter("{%s}Schema" % edm_uri):
            namespace = schema.get("Namespace", "")

            for et in schema.iter("{%s}EntityType" % edm_uri):
                type_name = et.get("Name", "")
                fqn = f"{namespace}.{type_name}"

                props = self._parse_properties_v2(et, edm_uri)
                keys = self._parse_keys_v2(et, edm_uri, props)

                entity_types[fqn] = {"properties": props, "keys": keys}
                entity_types[type_name] = entity_types[fqn]

        for container in root.iter("{%s}EntityContainer" % edm_uri):
            for es in container.iter("{%s}EntitySet" % edm_uri):
                es_name = es.get("Name", "")
                es_type = es.get("EntityType", "")

                type_info = entity_types.get(es_type, {})
                if not type_info:
                    short = es_type.rsplit(".", 1)[-1]
                    type_info = entity_types.get(short, {})

                sap_label = es.get(
                    "{%s}label" % EDMX_NS["sap"], es_name
                )

                entity_set = EntitySet(
                    name=es_name,
                    entity_type=es_type,
                    properties=type_info.get("properties", []),
                    key_properties=type_info.get("keys", []),
                )
                result[es_name] = entity_set

        return result

    def _parse_properties_v2(
        self, entity_type: ET.Element, edm_uri: str
    ) -> list[Property]:
        """Parse properties from a V2/V3 EntityType element."""
        props: list[Property] = []
        sap_ns = EDMX_NS["sap"]

        for p in entity_type.iter("{%s}Property" % edm_uri):
            filterable = p.get(f"{{{sap_ns}}}filterable", "true")
            sortable = p.get(f"{{{sap_ns}}}sortable", "true")
            label = p.get(f"{{{sap_ns}}}label")

            prop = Property(
                name=p.get("Name", ""),
                edm_type=p.get("Type", "Edm.String"),
                nullable=p.get("Nullable", "true").lower() == "true",
                filterable=filterable.lower() == "true",
                sortable=sortable.lower() == "true",
                label=label,
                max_length=_safe_int(p.get("MaxLength")),
            )
            props.append(prop)
        return props

    def _parse_keys_v2(
        self,
        entity_type: ET.Element,
        edm_uri: str,
        props: list[Property],
    ) -> list[Property]:
        """Parse key properties from V2/V3 EntityType."""
        keys: list[Property] = []
        prop_map = {p.name: p for p in props}

        for key_elem in entity_type.iter("{%s}Key" % edm_uri):
            for ref in key_elem.iter("{%s}PropertyRef" % edm_uri):
                key_name = ref.get("Name", "")
                if key_name in prop_map:
                    keys.append(prop_map[key_name])
        return keys

    def _parse_v2_no_ns(self, root: ET.Element) -> dict[str, EntitySet]:
        """Fallback parser that ignores namespaces."""
        return {}


def _safe_int(val: str | None) -> int | None:
    """Convert string to int, or return None."""
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
