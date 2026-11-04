"""A chat assistant that retrieves before it answers, zone-redundant on the answer path.

The answer path is one loop -- ask,
retrieve, ground, answer -- and everything on it is zone-redundant, so the
picture says what survives a datacenter going away. The indexing path runs
underneath on its own clock and never touches a user request.
"""

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Group, infragram as shared
from infragram.nodes.azure import (
    ai_machine_learning as ai,
    databases,
    devops,
    integration,
    networking,
    security,
    storage,
)
from infragram.nodes.frames import azure as az

with Diagram(
    "Grounded assistant on Azure OpenAI",
    "Retrieval-augmented chat, zone-redundant on the answer path.",
    slug="azure-rag-assistant",
    providers=("azure",),
    direction="down",
) as diagram:
    with Group("", "group").row().keep_order():
        person = shared.identity.PublicUsers("Employees", "Entra ID SSO")

        with Group("", "group").column().keep_order():
            with az.Subscription("AI platform subscription").column().keep_order():
                with az.Region("Sweden Central").column().keep_order():
                    with Group("Answer path · zone-redundant", "group").row().keep_order():
                        with az.Zone("Zone 1"):
                            gateway = integration.APIManagementServicesIntegration(
                                "API Management", "quota · token metering"
                            )
                        with az.Zone("Zone 2"):
                            orchestrator = networking.ApplicationGateways(
                                "Orchestrator", "Container Apps · 3 replicas"
                            )
                        with az.Zone("Zone 3"):
                            cache = databases.AzureManagedRedis("Redis", "semantic cache")

                    with az.VNet("vnet-ai").row().keep_order():
                        with az.Subnet("snet-ai").row().keep_order():
                            search = ai.CognitiveSearch("AI Search", "hybrid · semantic ranker")
                            model = ai.AzureOpenAI("Azure OpenAI", "gpt · text-embedding-3")
                            memory = databases.AzureCosmosDB("Cosmos DB", "chat history")

                with Group("Indexing path · runs on its own clock", "group").row().keep_order():
                    docs = storage.StorageAccounts("Documents", "SharePoint sync")
                    cracker = ai.FormRecognizers("Document Intelligence", "layout · tables")
                    indexer = ai.AIStudio("Indexer", "chunk · embed · upsert")

                with Group("Guardrails", "group").row().keep_order():
                    content = ai.CognitiveServicesDecisions("Content Safety", "in and out")
                    vault = security.KeyVaults("Key Vault", "keys · endpoints")
                    insights = devops.ApplicationInsights("App Insights", "traces · token spend")

    # the answer path: one loop, left to right and back
    person >> Edge("ask") >> gateway
    gateway >> Edge("route") >> orchestrator
    orchestrator >> Edge("cache hit?") >> cache
    orchestrator >> Edge("1 · retrieve") >> search
    search >> Edge("top-k chunks") >> orchestrator
    orchestrator >> Edge("2 · ground + generate") >> model
    model >> Edge("answer") >> orchestrator
    orchestrator >> Edge("turn") >> memory
    orchestrator >> Edge("answer") >> person

    # the indexing path: never on a user request
    docs >> Edge("new + changed") >> cracker
    cracker >> Edge("text + layout") >> indexer
    indexer >> Edge("embeddings") >> model
    indexer >> Edge("upsert index", dashed=True) >> search

    content >> Edge("screens", dashed=True) >> orchestrator
    vault >> Edge("secrets", dashed=True) >> orchestrator
    orchestrator >> Edge("telemetry", dashed=True) >> insights

if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
