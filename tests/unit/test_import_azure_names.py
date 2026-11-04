"""A diagram that names no cloud still draws Azure's components by their names.

Mermaid, PlantUML and bare draw.io boxes carry no stencil saying which
library a shape is from. Azure's own resource visualizer writes such Mermaid,
naming each resource as "App Service" or "Key Vault: kv-shop"; this edition
draws those with Azure's icons, while a plain word ("Database", "Users")
keeps the shared component it always had.
"""

from __future__ import annotations

import pytest

from infragram.convert.draw import draw_sketch
from infragram.convert.match import match_component
from infragram.convert.mermaid import read_mermaid
from infragram.convert.model import Shape
from infragram.estate.draw import Box, Card

#: The example diagram of Azure's azure-resource-visualizer skill, as it ships.
VISUALIZER_EXAMPLE = """graph TB
    subgraph "Resource Group: rg-demo"
        subgraph "Network Layer"
            VNET[Virtual Network<br/>10.0.0.0/16]
            SUBNET1[Subnet: web<br/>10.0.1.0/24]
            SUBNET2[Subnet: data<br/>10.0.2.0/24]
            NSG[Network Security Group]
        end
        subgraph "Compute Layer"
            APP[App Service<br/>Plan: P1v2]
            FUNC[Function App<br/>Runtime: .NET 10]
        end
        subgraph "Data Layer"
            SQL[Azure SQL Database<br/>DTU: S1]
            STORAGE[Storage Account<br/>Type: Standard LRS]
        end
        subgraph "Security & Identity"
            KV[Key Vault]
            MI[Managed Identity]
        end
    end
    APP -->|"HTTPS requests"| FUNC
    FUNC -->|"SQL connection"| SQL
    FUNC -->|"Blob/Queue access"| STORAGE
    APP -->|"Uses identity"| MI
    MI -->|"Access secrets"| KV
    VNET --> SUBNET1
    VNET --> SUBNET2
    SUBNET1 --> APP
    SUBNET2 --> SQL
    NSG -->|"Rules applied to"| SUBNET1
"""


def _cards(items) -> list[Card]:
    found: list[Card] = []
    for item in items:
        if isinstance(item, Card):
            found.append(item)
        elif isinstance(item, Box):
            found += _cards(item.children)
    return found


def test_the_visualizers_example_draws_every_resource_with_azures_icon() -> None:
    drawing = draw_sketch(read_mermaid(VISUALIZER_EXAMPLE, name="rg-demo"))
    cards = {card.caption: f"{card.library}:{card.service_id}" for card in _cards(drawing.roots)}
    assert cards == {
        "Virtual Network": "azure:virtual-networks",
        "Subnet: web": "azure:subnet",
        "Subnet: data": "azure:subnet",
        "Network Security Group": "azure:network-security-groups",
        "App Service": "azure:app-services",
        "Function App": "azure:function-apps",
        "Azure SQL Database": "azure:sql-database",
        "Storage Account": "azure:storage-accounts",
        "Key Vault": "azure:key-vaults",
        "Managed Identity": "azure:managed-identities",
    }


@pytest.mark.parametrize(
    ("label", "component"),
    [
        ("Key Vault: kv-shop", "azure:key-vaults"),
        ("Private Endpoint: pe-sql", "azure:private-endpoints"),
        ("Application Insights: appi-shop", "azure:application-insights"),
        ("AKS cluster", "azure:kubernetes-services"),
        ("Log Analytics workspace", "azure:log-analytics-workspaces"),
        ("Application Gateway", "azure:application-gateways"),
    ],
)
def test_an_azure_name_in_a_bare_label_is_azures(label: str, component: str) -> None:
    match = match_component(Shape(key="x", label=label), [])
    assert f"{match.library}:{match.service_id}" == component


@pytest.mark.parametrize(
    ("label", "component"),
    [
        ("Database", "infragram:generic-database"),
        ("Users", "infragram:public-users"),
        ("Queue", "infragram:message-queue"),
        ("Load balancer", "infragram:generic-load-balancer"),
        ("Cache", "infragram:generic-cache"),
    ],
)
def test_a_plain_word_keeps_the_shared_component(label: str, component: str) -> None:
    match = match_component(Shape(key="x", label=label), [])
    assert f"{match.library}:{match.service_id}" == component


#: An AKS ingress review drawn in Mermaid: fills by class, shapes, line breaks.
REVIEW = """flowchart TB
    customer((Customer<br>HTTPS 443<br>payments only when billing is enabled)):::publicEdge
    fd[Front Door<br>WAF and cache]:::publicEdge
    control{{AKS control plane<br>managed API}}:::managed
    agw[Application Gateway<br>TLS termination]:::privateNet
    nogo[Current implementation: NO-GO<br>no recorded deployment evidence]:::blocker
    customer --> fd --> agw
    control -.- agw
    classDef publicEdge fill:#fde6d1,stroke:#cc7631
    classDef privateNet fill:#e7f2e8
    classDef managed fill:#efe9f8
    classDef blocker fill:#fce3e3
"""


def test_a_mermaid_review_keeps_its_shapes_fills_and_lines() -> None:
    sketch = read_mermaid(REVIEW, name="review")
    cards = {card.key: card for card in _cards(draw_sketch(sketch).roots)}
    assert (cards["customer"].shape, cards["customer"].tone) == ("ellipse", "edge")
    assert cards["customer"].detail == "HTTPS 443\npayments only when billing is enabled"
    assert (cards["control"].shape, cards["control"].tone) == ("hexagon", "managed")
    # Azure's own products keep Azure's icons; a verdict is a plain box
    assert cards["fd"].library == "azure" and cards["fd"].tone == "edge"
    assert cards["agw"].library == "azure" and cards["agw"].tone == "private"
    assert (cards["nogo"].library, cards["nogo"].service_id, cards["nogo"].tone) == (
        "infragram",
        "box",
        "blocker",
    )
    assert sketch.tones == {
        "edge": "public edge",
        "managed": "managed",
        "private": "private net",
        "blocker": "blocker",
    }
