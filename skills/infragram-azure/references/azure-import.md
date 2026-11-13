# Drawing a live Azure subscription

`infragram export:azure` reads what is deployed and draws it. It holds no
credential of its own: every call goes through the Azure CLI, so whatever
`az login` established (a user, a service principal, a managed identity) is
what reads the estate, with that identity's permissions. The read is one
paged Azure Resource Graph query over `az rest`, so no CLI extension and no
Python package beyond this one is needed.

```text
az login                                        # once; --tenant <id> for another tenant
infragram export:azure --list-subscriptions     # what az can see; * marks the current one
infragram export:azure                          # current subscription, network view, icons
infragram export:azure -s "Production" -s "Connectivity" --view both --formats template,html,svg,png
infragram export:azure --all-subscriptions -g "rg-hub-*" -g "rg-prod-*"
infragram export:azure -m "mg-platform"         # every enabled subscription under a management group
```

## Two views of one read

| `--view` | Frames | Where a resource lands |
|---|---|---|
| `network` (default) | tenant → subscription → resource group → VNet → subnet | in the subnet it has an address in, else in its resource group |
| `groups` | tenant → subscription → resource group | in its resource group, as ARM files it |
| `both` | one export of each, `<slug>-network` and `<slug>-groups` | |

Placement in the network view is read from ids, never guessed from names:

- a VM or scale set through its network interface;
- an AKS cluster through its node pools' `vnetSubnetID`;
- a private endpoint, firewall, Bastion, gateway, Application Gateway or
  internal load balancer through the subnet its IP configuration names;
- App Service and Functions through their VNet integration subnet.

A subnet named only in a *firewall rule* (a storage account's
`networkAcls`, a SQL server's virtual network rule) does not move the
resource into it. What applies to a subnet is a badge on the subnet's
top-right corner, the way Azure's reference architectures seat an NSG on its
subnet: the NSG's icon on the corner point itself, a route table on the top
border beside it, each icon hiding the line behind it, with just its name
beside it under the line. A NAT gateway is the subnet's way out, so it sits
where Azure's NAT gateway diagrams put it: the middle of the top edge, over
a teal bar along that edge that marks the subnet it serves. One NSG or NAT
gateway on two subnets is drawn on each. An NSG can instead be attached to a VM's network interface: then it is
a card in that VM's subnet, captioned "on NIC · <vm>", with a dashed `NIC`
wire to the VM it guards (in the groups view too). A VNet-injected Databricks
workspace sits in its container subnet. A resource group whose resources all
moved into subnets is not drawn; a really empty one is.

## Wires

- **Peering**, both ways, drawn once per pair. In the network view each
  peered VNet holds a *Peerings* card and the wire runs between those,
  because a wire to a frame lands on the first card the frame holds.
- **Private link**, from the private endpoint to the resource it reaches,
  labelled with the sub-resource (`blob`, `sqlServer`, `vault`).
- **Parent to child**, dashed: a SQL server to its databases.
- **References**, dashed, only with `--references`: a resource naming another
  in its properties (a web app its plan, a cluster its Log Analytics
  workspace). Off by default because on a real estate they cross the whole
  picture.

## Networks in other subscriptions

A peering often crosses subscriptions (hub in *Connectivity*, spokes in the
landing zones). Read every subscription involved (`-s A -s B`, or
`--all-subscriptions`) and both sides draw in full, each under its own
subscription frame. When the far side is not in the read, because its
subscription was not named, the identity cannot read it, or `-g` filtered it
out, it is still drawn: a VNet card in a subscription frame labelled
`· not read` or `· filtered out`, so the peering keeps both ends and the
picture says what it did not see.

## What is left out, and how to bring it back

| Left out by default | Flag |
|---|---|
| Plumbing: NICs, OS disks, public IPs, VM extensions, alert rules, action groups, network watchers, DNS zone links | `--all` |
| Resource groups another service manages (AKS `MC_*`, Databricks) | `--all` |
| The `master` database of a SQL server | never drawn |
| Any type you name | `--exclude-type "microsoft.insights/*"` |

An unknown resource type still draws, with the generic *All resources* icon,
and the command lists every such type so the mapping in
`infragram.discovery.arm_types` can grow. Kubernetes objects inside an
AKS cluster are not read: that needs cluster credentials, not ARM.

## Unused resources

The same read marks what the estate keeps without using. Each one says
**Unused** in amber text in its card's corner, has an *Unused* row with the reason in
its details, and a count by rule in the command's summary. Unused plumbing (an
unattached disk, a detached NIC, an unassociated IP) is drawn even without
`--all`, since it belongs to nothing else. A rule fires only on what ARM states
outright, never on a property a row leaves out.

| Rule | Marked when | Still billed |
|---|---|---|
| `unattached-disk` | `diskState` is `Unattached` | yes |
| `unassociated-ip` | no IP configuration and no NAT gateway | Standard SKU |
| `detached-nic` | no VM, private endpoint or link service, and nothing names it | no |
| `unassociated-nsg` | on no subnet and no NIC | no |
| `unassociated-route-table` | on no subnet | no |
| `idle-nat-gateway` | on no subnet | yes |
| `empty-load-balancer` | no backend in any pool | Standard SKU |
| `empty-application-gateway` | no backend in any pool | yes |
| `empty-plan` | an App Service plan with `numberOfSites` 0 | yes |
| `stopped-app` | a web or function app whose `state` is `Stopped` | its plan |
| `empty-availability-set` | holds no VM | no |
| `stopped-vm` | power state `stopped`, not deallocated | yes: compute too |
| `deallocated-vm` | power state `deallocated` | its disks only |
| `idle-gateway` | a VPN or ExpressRoute gateway no connection joins (point-to-site excepted) | yes |
| `unlinked-dns-zone` | a private DNS zone with no virtual-network link | no |
| `disconnected-endpoint` | every private-link connection disconnected or rejected | yes |
| `empty-resource-group` | holds no resource (service-managed groups excepted) | no |

A deallocated VM is priced at no compute; what it would cost started is kept
as `running_monthly` beside its finding.

## Recent changes and security findings

The same read takes two more of Resource Graph's tables, so a snapshot says
what changed lately and what a security review would raise:

- **Changes** (`resourcechanges`): the last fourteen days, newest first, at
  most 5000. Each says when (UTC), whether the resource was created,
  updated or deleted, the properties that moved from what to what, and,
  where Azure Resource Manager recorded it, who made the change and through
  what client (portal, CLI, a template). Azure's own bookkeeping (an etag, a
  provisioning state) is not called a change.
- **Findings**: each Defender for Cloud recommendation a resource fails,
  with its severity (High, Medium, Low) and how to fix it, and each Azure
  Policy rule it does not comply with, named as the rule is and with the
  assignment that applies it. A rule failed through several assignments is
  one finding. A tenant without Defender, or without policy assignments,
  simply has none of that kind.

Each goes on the card a reader would look at: a NIC's or disk's on the VM
that lists it, a subnet's on its subnet (on its network in the groups view),
an NSG drawn as a subnet badge on that subnet, a deleted resource's on its
resource group. Plumbing left out of the picture keeps its own. A card lists
its newest ten changes and its worst twenty findings, and says how many in
all. The command's summary counts both. The exported pictures leave them out:
they are the page's to show (see *In the page*).

Both are read by default; `--no-changes` and `--no-findings` skip them. The
Reader role reads all three tables. If Azure refuses one (an identity
without access to Defender, say), the snapshot notes why under `unread`, the
summary says `findings not read: ...`, and the rest is drawn as usual. A
snapshot saved before these reads draws as it always did.

A subscription the identity may not read at all is not drawn as an empty
one: Resource Graph leaves such a subscription out of a read of several
without a word, so one that comes back with no resource group is asked
again on its own. If Azure refuses, its frame is captioned `· not read`, the
snapshot lists it under `unreadable`, and the summary says why. Grant the
identity the Reader role there, or sign in as someone who has it.

## What a VM carries

A VM's details list its NICs (with the private address), its OS and data
disks (SKU and size) and its public IPs (address), read from the NIC's
`virtualMachine`, the disk's `managedBy` and the IP's `ipConfiguration`; each
part's details name what it is attached to. They are plumbing, so the map
leaves them out; with `--all` each sits beside its VM, in its subnet, wired to
it and labelled with its role. A public IP on a load balancer, gateway or
firewall is listed on that resource the same way.

## In the page

The exported page carries a **Resources** tab in its bottom drawer: every
resource as a row with its type, resource group, location, what it carries
or is attached to, its monthly price, its unused rule and reason, and its
tags. It searches, filters (type, group, Unused, Untagged, Priced), sorts,
downloads as CSV, and a row click finds the card. A VM's popup lists its
NICs, disks and public IPs and shows them on the canvas or folds them away.

When the read took them, the table adds a **Findings** column (`1 high,
2 medium`, sorted worst first) and a **Changed** column (the newest change
and its day), and two filters: **With findings** and **Changed in 7 days**,
counted from the day of the read, not from today. A frame with a change or a
finding (a subnet, a resource group that lost a resource) has a row too. The
details beside the table list every finding with its fix and the newest
changes with what moved and who moved it. A **Changes** tab lists every
change by day, each row picking its card. On the map, right-click empty
canvas for **Show what changed in 7 days** and **Show what has findings**.

## Looks and outputs

Icons with captions are the default (`--display icon`); `card` draws titled
cards, and `both` writes cards plus an `-icons` variant of the SVG and PNG.
A resource group or subnet with more than three loose services lays them
out as a grid (three to six columns) rather than a tower, with its networks
on rows of their own. A caption says the SKU or size; the region is added
only when the estate spans more than one.
Every drawn resource carries its type, resource group, location, id and tags
in a table the editor opens on click. The other export options (`--formats`,
`--output-dir`, `--theme`, `--scale`, `--background`, `--verify`, `--force`)
mean what they mean for [export.md](export.md).

## Snapshots

`--snapshot-out estate.json` keeps what was read; `--from-snapshot
estate.json` redraws it with no Azure access, in CI or on another machine.
A snapshot is plain JSON (`infragram.azure-snapshot/1`): the subscriptions,
the resource groups and every resource row with its properties, then the
`changes` and `findings` rows when they were read. It contains
resource ids, names, tags and configuration, so treat it like the
subscription's inventory, not like a public file.

## Reading it again

`--refresh` redraws an earlier diagram from a new read and keeps the work
done on it:

```text
infragram export:azure --refresh azure-production-network.infragram.json \
  --since estate.json --snapshot-out estate-2.json
```

- **What the reader did stays.** A card moved, a frame resized or a style set
  in the editor is written back into the document, and the refresh gives it to
  the element drawn for the same resource now, matched by its Resource ID.
  A new resource never takes the place of another that had its name.
  The earlier diagram can be the `.infragram.json`, or a page or picture saved
  from the editor, since those carry the document. What is new is laid out as
  on a first read, so look over where it landed.
- **What changed is marked.** With `--since`, the snapshot the earlier diagram
  was drawn from, the two reads are compared resource by resource. Each added
  or changed element carries `refresh` (a change names its fields, such as
  `sku` or `properties.networkAcls`), and the root lists what was removed. In
  the page, **Show what changed since the last read** (right-click empty
  canvas) lights them, a network or subnet on its frame. Fields Azure
  rewrites by itself, such as `provisioningState`, are not counted as
  changes. Without `--since`, added
  and removed still show, from the Resource IDs on the earlier cards, but
  nothing can be called changed. The earlier diagram is then compared with
  the one drawn from the new read, so a resource drawn as part of a frame or
  not drawn at all is never reported, and the same read twice reports
  nothing.
- **The same subscriptions are read.** With no subscription named, those in
  the `--since` snapshot are read again. `--from-snapshot` replays a newer
  snapshot instead of calling Azure.
- **One diagram per refresh.** Give the earlier diagram's `--view` (network or
  groups), not `both`. The new files keep its name. A file edited since it
  was written is refused unless `--force` is given, or use another
  `--output-dir`.

The command prints the account (`1 added, 1 changed, 1 removed since …`,
then a line for each) and exits 4 when anything changed, 0 when nothing did.
A scheduled job can run it against Azure (without `--from-snapshot`) and act
on that status. It only reads; nothing in Azure is created, changed or
deleted.

## From Python

```python
from pathlib import Path

from infragram.discovery import AzureSession, ImportOptions, blueprint

session = AzureSession()
snapshot = session.snapshot(session.resolve(["Production"]))
plan, summary = blueprint(snapshot, ImportOptions(view="network"))
plan.export(Path("dist"), formats=("template", "html", "svg"))
```
