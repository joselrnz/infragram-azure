"""A medallion lakehouse: raw in on the left, a dashboard out on the right.

Three zones the data passes through and is renamed by -- bronze as it landed,
silver once it is conformed, gold once it answers a question -- and the
governance that watches all three without being in the path.
"""

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Group, infragram as shared
from infragram.nodes.azure import (
    analytics,
    databases,
    integration,
    iot,
    security,
    storage,
)
from infragram.nodes.frames import azure as az

with Diagram(
    "Medallion lakehouse on Azure",
    "Streams and batches in, one governed lake, dashboards out.",
    slug="azure-lakehouse",
    providers=("azure",),
    direction="down",
) as diagram:
    with Group("", "group").row().keep_order():
        with Group("Sources", "group").column().keep_order():
            devices = iot.IoTHub("IoT Hub", "250k devices")
            events = analytics.EventHubs("Event Hubs", "clickstream · 40k/s")
            line_of_business = databases.AzureCosmosDB("Cosmos DB", "change feed")

        with Group("", "group").column().keep_order():
            with az.Subscription("Data platform subscription").column().keep_order():
                with Group("Ingest", "group").row().keep_order():
                    stream = analytics.StreamAnalyticsJobs("Stream Analytics", "windowing · 1 min")
                    bus = integration.AzureServiceBus("Service Bus", "replay · dead letter")

                with az.VNet("vnet-data · 10.40.0.0/16").row().keep_order():
                    with az.Subnet("snet-lake · private endpoints").keep_order():
                        bronze = storage.DataLakeStorageGen1("Bronze", "as it landed · parquet")
                        silver = storage.DataLakeStorageGen1("Silver", "conformed · deduped")
                        gold = storage.DataLakeStorageGen1("Gold", "modelled · served")

                with Group("Transform", "group").row().keep_order():
                    spark = analytics.AzureDatabricks("Databricks", "autoloader · Delta")
                    warehouse = analytics.AzureSynapseAnalytics("Synapse", "serverless SQL")

                with Group("Govern", "group").row().keep_order():
                    catalog = integration.AzureDataCatalog(
                        "Data catalog", "lineage · classification"
                    )
                    vault = security.KeyVaults("Key Vault", "keys · service principals")

        with Group("Consumers", "group").column().keep_order():
            report = analytics.PowerBIEmbedded("Power BI", "direct lake")
            analyst = shared.identity.PublicUser("Analyst", "reads gold only")

    devices >> Edge("telemetry") >> stream
    events >> Edge("events") >> stream
    line_of_business >> Edge("change feed") >> bus
    stream >> Edge("land raw") >> bronze
    bus >> Edge("land raw") >> bronze
    bronze >> Edge("clean · conform") >> spark
    spark >> Edge("write Delta") >> silver
    silver >> Edge("model") >> warehouse
    warehouse >> Edge("publish") >> gold
    gold >> Edge("direct lake") >> report
    report >> Edge("reads") >> analyst
    catalog >> Edge("scans", dashed=True) >> bronze
    catalog >> Edge("scans", dashed=True) >> silver
    catalog >> Edge("scans", dashed=True) >> gold
    vault >> Edge("secrets", dashed=True) >> spark

if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
