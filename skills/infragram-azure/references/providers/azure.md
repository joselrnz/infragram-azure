# Azure library

Load only for Azure content. The theme is [`azure.json`](../../assets/themes/azure.json)
(`theme="azure"`); the component catalog is the full Azure Public Service
Icons set, 712 icons in `assets/icons/vendors/azure/`. Coverage: **full**.

## Frames

Starter stack: **Tenant → management group → subscription → resource group →
VNet → subnet**. Region and availability zone are optional *location* frames:
a resource group may hold resources from several regions, so region is never
the parent of a resource group.

| Frame id | Kind | Official tab icon |
|---|---|---|
| `custom-boundary-azure-tenant` | organization | Tenant properties |
| `custom-boundary-azure-management-group` | management-group | Management groups |
| `custom-boundary-azure-subscription` | subscription | Subscriptions |
| `custom-boundary-azure-resource-group` | resource-group | Resource groups |
| `custom-boundary-azure-region` / `custom-boundary-azure-zone` | region / zone | Region management / Availability sets |
| `custom-boundary-azure-vnet` | network | Virtual networks |
| `custom-boundary-azure-subnet` | subnet-private | Subnet |
| `custom-boundary-azure-aks` | cluster | Kubernetes services |

Every Azure frame carries official artwork on its tab (the `boundaries.icons`
block in `azure.json`), so the frames read as Azure without any decoration.

## Artwork

Use the bundled service icons in their reviewed colors and do not alter them;
Microsoft permits the artwork for architecture diagrams and documentation on
that condition. The Azure mark (`logos:microsoft-azure`) appears once as the
library filter.

## Modelling rules

- Subnets belong to a VNet; VNets belong to a resource group inside a
  subscription. Peering and VPN gateways are components, not frames.
- Managed identity, policy, and RBAC sit at the scope they apply to (tenant,
  management group, subscription, resource group) as badges or components.
- Microsoft Azure service artwork. Microsoft trademark and product-icon terms apply.
