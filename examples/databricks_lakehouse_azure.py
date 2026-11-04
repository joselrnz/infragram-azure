"""A Databricks lakehouse on Azure, written as it would be described.

Clickstream events arrive through Event Hubs and files land in an ADLS Gen2
container. Structured Streaming and Auto Loader bring both into bronze Delta
tables, a Lakeflow pipeline refines them to silver and gold on serverless
compute, and Lakeflow Jobs keeps the schedule. A SQL warehouse serves Power
BI and the workspace's own AI/BI dashboards. Unity Catalog governs every
table, reaches the lake through an access connector (a managed identity, no
storage key), records lineage, and shares the gold tables with a partner
through Delta Sharing. The workspace's secrets live in Key Vault.

Databricks frames come from ``infragram.nodes.frames.databricks``, its
products from ``infragram.nodes.databricks``; the storage, streaming,
identity and reporting stay Azure's.

Through the skill's launcher, from the plugin folder::

    python skills/infragram-azure/scripts/infragram.py compose examples/databricks_lakehouse_azure.py \\
        --formats template,html,svg,png --output-dir dist
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Group, infragram as shared
from infragram.nodes.azure import analytics as az_analytics, identity, security, storage
from infragram.nodes.databricks import analytics, engineering, governance, sharing
from infragram.nodes.frames import azure, databricks

with Diagram(
    "Databricks lakehouse on Azure",
    "Event Hubs and an ADLS Gen2 landing zone feed Structured Streaming and Auto Loader; a Lakeflow "
    "pipeline refines bronze to gold on serverless compute; a SQL warehouse serves Power BI and "
    "AI/BI dashboards; Unity Catalog governs the lake through an access connector and shares the "
    "gold tables through Delta Sharing.",
    slug="databricks-lakehouse-azure",
) as diagram:
    with azure.Subscription("Production subscription"), azure.Region("East US 2").row():
        with azure.ResourceGroup("rg-lakehouse-prod").column().keep_order():
            events = az_analytics.EventHubs("Event Hubs", "clickstream - 20k/s")
            landing = storage.StorageAccounts("Landing zone", "ADLS Gen2 - raw drops")
            lake = storage.StorageAccounts("Lakehouse storage", "ADLS Gen2 - Delta tables")
            connector = identity.ManagedIdentities("Access connector", "managed identity - no key")
            security.KeyVaults("Key Vault", "the workspace's secret scope")

        with databricks.Account("Databricks account").column().keep_order():
            with databricks.Workspace("Workspace - prod").row():
                with databricks.Compute("Serverless compute").column().keep_order():
                    stream = engineering.StructuredStreaming(
                        "Structured Streaming", "events to bronze"
                    )
                    loader = engineering.AutoLoader("Auto Loader", "files to bronze")
                    pipeline = engineering.SparkDeclarativePipelines(
                        "Lakeflow pipeline", "bronze - silver - gold"
                    )
                    jobs = engineering.LakeflowJobs("Lakeflow Jobs", "hourly schedule")
                warehouse = analytics.SQLWarehouse("SQL warehouse", "serverless - Photon")
                dashboards = analytics.AIBIDashboards("AI/BI dashboards", "sales and ops")
            with databricks.UnityCatalog("Unity Catalog").row():
                catalog = governance.UnityCatalog("Catalog: prod", "bronze - silver - gold schemas")
                lineage = governance.DataLineage("Lineage", "table and column")
                share = sharing.DeltaSharing("Delta Sharing", "gold tables")

    with Group("Consumers").column().keep_order():
        powerbi = az_analytics.PowerBIEmbedded("Power BI", "DirectQuery reports")
        analysts = shared.identity.PublicUsers("Analysts", "Power BI and SQL")
        partner = shared.identity.PublicUser("Partner", "Delta Sharing recipient")

    events >> Edge("events") >> stream
    landing >> Edge("new files") >> loader
    stream >> Edge("bronze") >> pipeline
    loader >> Edge("bronze") >> pipeline
    jobs >> Edge("runs", dotted=True) >> pipeline
    pipeline >> Edge("Delta tables") >> lake
    warehouse >> Edge("queries") >> lake
    powerbi >> Edge("DirectQuery") >> warehouse
    dashboards >> Edge("SQL") >> warehouse
    analysts >> Edge("reports") >> powerbi
    catalog >> Edge("governs", dotted=True) >> connector
    connector >> Edge("reads and writes", dotted=True) >> lake
    catalog >> Edge("records", dotted=True) >> lineage
    share >> Edge("shares") >> partner


if __name__ == "__main__":
    print(diagram.export(Path("dist"), formats=("template", "html", "svg", "png")).html)
