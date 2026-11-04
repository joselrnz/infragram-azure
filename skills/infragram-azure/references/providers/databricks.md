# Databricks library (platform)

Load only for Databricks content. The theme is
[`databricks.json`](../../assets/themes/databricks.json)
(`theme="databricks"`); the component catalog is the Databricks
architecture icon set, 78 icons in `assets/icons/vendors/databricks/`,
built from Databricks' official SVGs. Coverage: **reviewed**. Databricks is a
*platform* library: it runs in a cloud account, so in this edition draw its
workspace inside the Azure subscription and region it is deployed to, never
in place of them. `examples/databricks_lakehouse_azure.py` shows one.

## Frames

Starter stack: **Account → workspace → compute**. Unity Catalog governs an
account's workspaces: draw its frame beside them, holding what one metastore
governs (catalogs, tables, volumes).

| Frame id | Kind |
|---|---|
| `custom-boundary-databricks-account` | account (Databricks mark on the tab) |
| `custom-boundary-databricks-workspace` | project (Workspace artwork) |
| `custom-boundary-databricks-compute` | cluster (Compute artwork) |
| `custom-boundary-databricks-unity-catalog` | group (Unity Catalog artwork) |

## Artwork

| Category | Folder | Icons | Examples |
|---|---|---|---|
| Platform & Compute | `platform` | 10 | `databricks:databricks`, `databricks:data-intelligence-platform`, `databricks:lakehouse`, `databricks:apache-spark` ... |
| Data Engineering | `engineering` | 9 | `databricks:lakeflow`, `databricks:lakeflow-connect`, `databricks:zerobus-ingest`, `databricks:spark-declarative-pipelines` ... |
| Storage & Databases | `storage` | 6 | `databricks:delta-lake`, `databricks:apache-iceberg`, `databricks:lakehouse-storage`, `databricks:liquid-clustering` ... |
| Analytics & BI | `analytics` | 7 | `databricks:data-warehousing`, `databricks:databricks-sql`, `databricks:sql-warehouse`, `databricks:lakehouse-rt` ... |
| AI & Agents | `ai` | 16 | `databricks:genie`, `databricks:genie-one`, `databricks:genie-agents`, `databricks:genie-code` ... |
| Governance & Security | `governance` | 8 | `databricks:unity-catalog`, `databricks:unity-catalog-semantics`, `databricks:data-lineage`, `databricks:abac` ... |
| Sharing & Collaboration | `sharing` | 5 | `databricks:delta-sharing`, `databricks:opensharing`, `databricks:marketplace`, `databricks:clean-rooms` ... |
| Developer Tools & Apps | `devtools` | 10 | `databricks:databricks-apps`, `databricks:notebooks`, `databricks:workspace`, `databricks:git-folders` ... |

The set's seven full-colour logos sit in their own category (`logos`) and in
the sidebar beside their products: `databricks:logo-apache-spark`,
`logo-apache-iceberg`, `logo-delta-lake`, `logo-delta-sharing`, `logo-mlflow`,
`logo-terraform`, `logo-unity-catalog`. They are wordmarks: for a small card,
the square product icon reads better.

Former names still find their icon: Delta Live Tables and DLT find Spark
Declarative Pipelines, Databricks Workflows finds Lakeflow Jobs, Vector
Search finds AI Search, Lakehouse Monitoring finds Data Quality Monitoring.

## Modelling rules

- The control plane is Databricks'; the compute plane runs in the cloud
  account: draw clusters and SQL warehouses inside the workspace, and the
  workspace inside the cloud's network or account frame it is deployed to.
- Storage is Azure's: Delta Lake tables live in ADLS Gen2 (a Storage Accounts
  card); wire the workspace to it, not to a Databricks storage icon. Unity
  Catalog reaches it through an access connector, a managed identity.
- Unity Catalog governs; draw its lineage and access as dotted wires.
- Artwork: the Databricks Architecture Icons set (MIT), from Databricks'
  official SVGs. Databricks, its logo and product names are trademarks of
  Databricks, Inc.; the license grants no trademark rights.
