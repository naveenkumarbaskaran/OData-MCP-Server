"""Tests for OData metadata parser."""

import pytest
from odata_mcp.metadata import MetadataParser, EntitySet, Property


SAMPLE_V4_METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="NorthwindModel" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Product">
        <Key>
          <PropertyRef Name="ProductID"/>
        </Key>
        <Property Name="ProductID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="ProductName" Type="Edm.String" Nullable="false" MaxLength="40"/>
        <Property Name="UnitPrice" Type="Edm.Decimal" Nullable="true"/>
        <Property Name="UnitsInStock" Type="Edm.Int16" Nullable="true"/>
        <Property Name="Discontinued" Type="Edm.Boolean" Nullable="false"/>
        <NavigationProperty Name="Category" Type="NorthwindModel.Category"/>
        <NavigationProperty Name="Order_Details" Type="Collection(NorthwindModel.Order_Detail)"/>
      </EntityType>
      <EntityType Name="Category">
        <Key>
          <PropertyRef Name="CategoryID"/>
        </Key>
        <Property Name="CategoryID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="CategoryName" Type="Edm.String" Nullable="false" MaxLength="15"/>
        <Property Name="Description" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="NorthwindEntities">
        <EntitySet Name="Products" EntityType="NorthwindModel.Product"/>
        <EntitySet Name="Categories" EntityType="NorthwindModel.Category"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


SAMPLE_V2_METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="ODataDemo" xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
            xmlns:sap="http://www.sap.com/Protocols/SAPData">
      <EntityType Name="Employee">
        <Key>
          <PropertyRef Name="EmployeeID"/>
        </Key>
        <Property Name="EmployeeID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="FirstName" Type="Edm.String" sap:label="First Name" sap:filterable="true"/>
        <Property Name="LastName" Type="Edm.String" sap:label="Last Name" sap:filterable="true"/>
        <Property Name="HireDate" Type="Edm.DateTime" sap:filterable="false"/>
      </EntityType>
      <EntityContainer Name="DemoService" m:IsDefaultEntityContainer="true">
        <EntitySet Name="Employees" EntityType="ODataDemo.Employee"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


class TestMetadataParserV4:
    """Tests for V4 metadata parsing."""

    def setup_method(self):
        self.parser = MetadataParser()

    def test_parse_entity_sets(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        assert "Products" in result
        assert "Categories" in result
        assert len(result) == 2

    def test_product_properties(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        prop_names = [p.name for p in products.properties]
        assert "ProductID" in prop_names
        assert "ProductName" in prop_names
        assert "UnitPrice" in prop_names
        assert "Discontinued" in prop_names

    def test_product_key(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        assert len(products.key_properties) == 1
        assert products.key_properties[0].name == "ProductID"
        assert products.key_properties[0].edm_type == "Edm.Int32"

    def test_navigation_properties(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        nav_names = [np.name for np in products.navigation_properties]
        assert "Category" in nav_names
        assert "Order_Details" in nav_names

    def test_collection_navigation(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        order_details = next(
            np for np in products.navigation_properties
            if np.name == "Order_Details"
        )
        assert order_details.is_collection is True

    def test_nullable_flag(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        prop_map = {p.name: p for p in products.properties}
        assert prop_map["ProductID"].nullable is False
        assert prop_map["UnitPrice"].nullable is True

    def test_edm_types_preserved(self):
        result = self.parser.parse(SAMPLE_V4_METADATA)
        products = result["Products"]
        prop_map = {p.name: p for p in products.properties}
        assert prop_map["ProductID"].edm_type == "Edm.Int32"
        assert prop_map["UnitPrice"].edm_type == "Edm.Decimal"
        assert prop_map["Discontinued"].edm_type == "Edm.Boolean"


class TestMetadataParserV2:
    """Tests for V2 metadata parsing."""

    def setup_method(self):
        self.parser = MetadataParser()

    def test_parse_v2_entity_sets(self):
        result = self.parser.parse(SAMPLE_V2_METADATA)
        assert "Employees" in result

    def test_v2_properties(self):
        result = self.parser.parse(SAMPLE_V2_METADATA)
        employees = result["Employees"]
        prop_names = [p.name for p in employees.properties]
        assert "EmployeeID" in prop_names
        assert "FirstName" in prop_names
        assert "LastName" in prop_names

    def test_v2_sap_annotations(self):
        result = self.parser.parse(SAMPLE_V2_METADATA)
        employees = result["Employees"]
        prop_map = {p.name: p for p in employees.properties}
        assert prop_map["FirstName"].label == "First Name"
        assert prop_map["FirstName"].filterable is True
        assert prop_map["HireDate"].filterable is False

    def test_v2_keys(self):
        result = self.parser.parse(SAMPLE_V2_METADATA)
        employees = result["Employees"]
        assert len(employees.key_properties) == 1
        assert employees.key_properties[0].name == "EmployeeID"
