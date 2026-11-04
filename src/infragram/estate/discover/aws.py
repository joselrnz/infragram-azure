"""A live AWS estate, read-only through the ``aws`` CLI.

Every call is a ``describe``, ``list`` or ``get``, in each region named (and
once for the global services: S3, CloudFront, Route 53). What each returns is
written as the Terraform resource it would be, with the values the drawing
reads: ids, the VPC and subnets each sits in, the security groups it wears,
its rules and its load balancer's targets. A default VPC and its default
subnets are drawn only when something sits in them.
"""

from __future__ import annotations

import os
from typing import Any

from ..link import link_by_value
from ..model import Estate, Found
from . import CallError, DiscoveryError, Runner, cli_runner, tags

__all__ = ["discover_aws"]


class _Reader:
    def __init__(self, run: Runner, profile: str | None) -> None:
        self.run = run
        self.profile = profile
        self.found: list[Found] = []
        self.notes: list[str] = []
        self.seen: set[str] = set()
        self.ids: set[tuple[str, str]] = set()

    def call(self, service: str, operation: str, region: str | None, *extra: str) -> Any:
        args = [service, operation, *extra, "--output", "json"]
        if region:
            args += ["--region", region]
        if self.profile:
            args += ["--profile", self.profile]
        try:
            return self.run(args) or {}
        except CallError as error:
            self.notes.append(
                f"not read: aws {service} {operation}{f' in {region}' if region else ''}: "
                f"{error.message}"
            )
            return {}

    def add(
        self, kind: str, name: str, values: dict[str, Any], source: str, region: str | None
    ) -> None:
        # one resource reached twice is read once; two that share a name (an
        # ECS service in two clusters, a function in two regions) are both
        # kept, the later one suffixed, as the Azure and GCP readers do
        identity = f"{region}/{values.get('arn') or values.get('id') or name}"
        if (kind, identity) in self.ids:
            return
        self.ids.add((kind, identity))
        address = f"{kind}.{name}"
        n = 2
        while address in self.seen:
            address = f"{kind}.{name}_{n}"
            n += 1
        self.seen.add(address)
        self.found.append(Found(address, kind, name, values, source=source, region=region))

    # ------------------------------------------------------------ networks
    def networks(self, region: str) -> None:
        src = f"aws ec2 ({region})"
        for vpc in self.call("ec2", "describe-vpcs", region).get("Vpcs", []):
            self.add(
                "aws_vpc",
                vpc["VpcId"],
                {
                    "id": vpc["VpcId"],
                    "cidr_block": vpc.get("CidrBlock"),
                    "tags": tags(vpc.get("Tags")),
                    "is_default": vpc.get("IsDefault"),
                },
                src,
                region,
            )
        for subnet in self.call("ec2", "describe-subnets", region).get("Subnets", []):
            self.add(
                "aws_subnet",
                subnet["SubnetId"],
                {
                    "id": subnet["SubnetId"],
                    "vpc_id": subnet.get("VpcId"),
                    "cidr_block": subnet.get("CidrBlock"),
                    "availability_zone": subnet.get("AvailabilityZone"),
                    "map_public_ip_on_launch": subnet.get("MapPublicIpOnLaunch"),
                    "tags": tags(subnet.get("Tags")),
                    "is_default": subnet.get("DefaultForAz"),
                },
                src,
                region,
            )
        for gateway in self.call("ec2", "describe-internet-gateways", region).get(
            "InternetGateways", []
        ):
            attached = [a.get("VpcId") for a in gateway.get("Attachments", []) if a.get("VpcId")]
            self.add(
                "aws_internet_gateway",
                gateway["InternetGatewayId"],
                {
                    "id": gateway["InternetGatewayId"],
                    "vpc_id": attached[0] if attached else None,
                    "tags": tags(gateway.get("Tags")),
                },
                src,
                region,
            )
        for gateway in self.call("ec2", "describe-nat-gateways", region).get("NatGateways", []):
            if gateway.get("State") in ("deleted", "deleting", "failed"):
                continue
            self.add(
                "aws_nat_gateway",
                gateway["NatGatewayId"],
                {
                    "id": gateway["NatGatewayId"],
                    "subnet_id": gateway.get("SubnetId"),
                    "vpc_id": gateway.get("VpcId"),
                    "tags": tags(gateway.get("Tags")),
                },
                src,
                region,
            )
        for table in self.call("ec2", "describe-route-tables", region).get("RouteTables", []):
            routes = [
                {
                    "gateway_id": r.get("GatewayId"),
                    "nat_gateway_id": r.get("NatGatewayId"),
                    "cidr_block": r.get("DestinationCidrBlock"),
                }
                for r in table.get("Routes", [])
            ]
            self.add(
                "aws_route_table",
                table["RouteTableId"],
                {"id": table["RouteTableId"], "vpc_id": table.get("VpcId"), "route": routes},
                src,
                region,
            )
            for association in table.get("Associations", []):
                if association.get("SubnetId"):
                    self.add(
                        "aws_route_table_association",
                        association["RouteTableAssociationId"],
                        {
                            "subnet_id": association["SubnetId"],
                            "route_table_id": table["RouteTableId"],
                        },
                        src,
                        region,
                    )
        for group in self.call("ec2", "describe-security-groups", region).get("SecurityGroups", []):
            ingress = []
            for permission in group.get("IpPermissions", []):
                ingress.append(
                    {
                        "protocol": permission.get("IpProtocol"),
                        "from_port": permission.get("FromPort"),
                        "to_port": permission.get("ToPort"),
                        "cidr_blocks": [r.get("CidrIp") for r in permission.get("IpRanges", [])],
                        "security_groups": [
                            p.get("GroupId") for p in permission.get("UserIdGroupPairs", [])
                        ],
                    }
                )
            self.add(
                "aws_security_group",
                group["GroupId"],
                {
                    "id": group["GroupId"],
                    "name": group.get("GroupName"),
                    "vpc_id": group.get("VpcId"),
                    "ingress": ingress,
                },
                src,
                region,
            )
        for endpoint in self.call("ec2", "describe-vpc-endpoints", region).get("VpcEndpoints", []):
            self.add(
                "aws_vpc_endpoint",
                endpoint["VpcEndpointId"],
                {
                    "id": endpoint["VpcEndpointId"],
                    "vpc_id": endpoint.get("VpcId"),
                    "service_name": endpoint.get("ServiceName"),
                    "vpc_endpoint_type": endpoint.get("VpcEndpointType"),
                    "subnet_ids": endpoint.get("SubnetIds", []),
                    "security_group_ids": [g.get("GroupId") for g in endpoint.get("Groups", [])],
                    "tags": tags(endpoint.get("Tags")),
                },
                src,
                region,
            )
        for gateway in self.call("ec2", "describe-transit-gateways", region).get(
            "TransitGateways", []
        ):
            self.add(
                "aws_ec2_transit_gateway",
                gateway["TransitGatewayId"],
                {
                    "id": gateway["TransitGatewayId"],
                    "arn": gateway.get("TransitGatewayArn"),
                    "tags": tags(gateway.get("Tags")),
                },
                src,
                region,
            )
        for attachment in self.call("ec2", "describe-transit-gateway-vpc-attachments", region).get(
            "TransitGatewayVpcAttachments", []
        ):
            self.add(
                "aws_ec2_transit_gateway_vpc_attachment",
                attachment["TransitGatewayAttachmentId"],
                {
                    "transit_gateway_id": attachment.get("TransitGatewayId"),
                    "vpc_id": attachment.get("VpcId"),
                    "subnet_ids": attachment.get("SubnetIds", []),
                },
                src,
                region,
            )
        for peering in self.call("ec2", "describe-vpc-peering-connections", region).get(
            "VpcPeeringConnections", []
        ):
            self.add(
                "aws_vpc_peering_connection",
                peering["VpcPeeringConnectionId"],
                {
                    "vpc_id": (peering.get("RequesterVpcInfo") or {}).get("VpcId"),
                    "peer_vpc_id": (peering.get("AccepterVpcInfo") or {}).get("VpcId"),
                },
                src,
                region,
            )
        for connection in self.call("ec2", "describe-vpn-connections", region).get(
            "VpnConnections", []
        ):
            self.add(
                "aws_vpn_connection",
                connection["VpnConnectionId"],
                {
                    "id": connection["VpnConnectionId"],
                    "vpn_gateway_id": connection.get("VpnGatewayId"),
                    "transit_gateway_id": connection.get("TransitGatewayId"),
                    "customer_gateway_id": connection.get("CustomerGatewayId"),
                    "tags": tags(connection.get("Tags")),
                },
                src,
                region,
            )

    # ------------------------------------------------------------ compute
    def compute(self, region: str) -> None:
        src = f"aws ec2 ({region})"
        for reservation in self.call("ec2", "describe-instances", region).get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if (instance.get("State") or {}).get("Name") in ("terminated", "shutting-down"):
                    continue
                self.add(
                    "aws_instance",
                    instance["InstanceId"],
                    {
                        "id": instance["InstanceId"],
                        "subnet_id": instance.get("SubnetId"),
                        "vpc_id": instance.get("VpcId"),
                        "instance_type": instance.get("InstanceType"),
                        "vpc_security_group_ids": [
                            g.get("GroupId") for g in instance.get("SecurityGroups", [])
                        ],
                        "private_ip": instance.get("PrivateIpAddress"),
                        "tags": tags(instance.get("Tags")),
                    },
                    src,
                    region,
                )
        for function in self.call("lambda", "list-functions", region).get("Functions", []):
            config = function.get("VpcConfig") or {}
            self.add(
                "aws_lambda_function",
                function["FunctionName"],
                {
                    "arn": function.get("FunctionArn"),
                    "function_name": function["FunctionName"],
                    "runtime": function.get("Runtime"),
                    "vpc_config": [
                        {
                            "subnet_ids": config.get("SubnetIds", []),
                            "security_group_ids": config.get("SecurityGroupIds", []),
                        }
                    ],
                },
                f"aws lambda ({region})",
                region,
            )
        for name in self.call("eks", "list-clusters", region).get("clusters", []):
            cluster = (
                self.call("eks", "describe-cluster", region, "--name", name).get("cluster") or {}
            )
            config = cluster.get("resourcesVpcConfig") or {}
            self.add(
                "aws_eks_cluster",
                name,
                {
                    "name": name,
                    "arn": cluster.get("arn"),
                    "version": cluster.get("version"),
                    "vpc_config": [
                        {
                            "subnet_ids": config.get("subnetIds", []),
                            "security_group_ids": config.get("securityGroupIds", []),
                        }
                    ],
                },
                f"aws eks ({region})",
                region,
            )
        for arn in self.call("ecs", "list-clusters", region).get("clusterArns", []):
            name = arn.rsplit("/", 1)[-1]
            self.add(
                "aws_ecs_cluster",
                name,
                {"arn": arn, "id": arn, "name": name},
                f"aws ecs ({region})",
                region,
            )
            services = self.call("ecs", "list-services", region, "--cluster", arn).get(
                "serviceArns", []
            )
            for start in range(0, len(services), 10):
                described = self.call(
                    "ecs",
                    "describe-services",
                    region,
                    "--cluster",
                    arn,
                    "--services",
                    *services[start : start + 10],
                )
                for service in described.get("services", []):
                    network = (service.get("networkConfiguration") or {}).get(
                        "awsvpcConfiguration"
                    ) or {}
                    self.add(
                        "aws_ecs_service",
                        service["serviceName"],
                        {
                            "arn": service.get("serviceArn"),
                            "name": service["serviceName"],
                            "cluster": arn,
                            "launch_type": service.get("launchType"),
                            "network_configuration": [
                                {
                                    "subnets": network.get("subnets", []),
                                    "security_groups": network.get("securityGroups", []),
                                }
                            ],
                            "load_balancer": [
                                {"target_group_arn": lb.get("targetGroupArn")}
                                for lb in service.get("loadBalancers", [])
                            ],
                        },
                        f"aws ecs ({region})",
                        region,
                    )

    # ------------------------------------------------------------ load balancers
    def balancers(self, region: str) -> None:
        src = f"aws elbv2 ({region})"
        for balancer in self.call("elbv2", "describe-load-balancers", region).get(
            "LoadBalancers", []
        ):
            arn = balancer["LoadBalancerArn"]
            self.add(
                "aws_lb",
                balancer["LoadBalancerName"],
                {
                    "id": arn,
                    "arn": arn,
                    "name": balancer["LoadBalancerName"],
                    "dns_name": balancer.get("DNSName"),
                    "internal": balancer.get("Scheme") == "internal",
                    "load_balancer_type": balancer.get("Type"),
                    "vpc_id": balancer.get("VpcId"),
                    "subnets": [
                        zone.get("SubnetId") for zone in balancer.get("AvailabilityZones", [])
                    ],
                    "security_groups": balancer.get("SecurityGroups", []),
                },
                src,
                region,
            )
            for listener in self.call(
                "elbv2", "describe-listeners", region, "--load-balancer-arn", arn
            ).get("Listeners", []):
                groups = []
                for action in listener.get("DefaultActions", []):
                    if action.get("TargetGroupArn"):
                        groups.append(action["TargetGroupArn"])
                    for group in (action.get("ForwardConfig") or {}).get("TargetGroups") or []:
                        groups.append(group.get("TargetGroupArn"))
                self.add(
                    "aws_lb_listener",
                    listener["ListenerArn"].rsplit("/", 1)[-1],
                    {
                        "arn": listener["ListenerArn"],
                        "load_balancer_arn": arn,
                        "port": listener.get("Port"),
                        "protocol": listener.get("Protocol"),
                        "default_action": [{"target_group_arn": g} for g in groups if g],
                    },
                    src,
                    region,
                )
        for group in self.call("elbv2", "describe-target-groups", region).get("TargetGroups", []):
            arn = group["TargetGroupArn"]
            self.add(
                "aws_lb_target_group",
                group["TargetGroupName"],
                {
                    "id": arn,
                    "arn": arn,
                    "port": group.get("Port"),
                    "protocol": group.get("Protocol"),
                    "vpc_id": group.get("VpcId"),
                },
                src,
                region,
            )
            health = self.call("elbv2", "describe-target-health", region, "--target-group-arn", arn)
            for description in health.get("TargetHealthDescriptions", []):
                target = (description.get("Target") or {}).get("Id")
                if target:
                    self.add(
                        "aws_lb_target_group_attachment",
                        f"{group['TargetGroupName']}-{target}",
                        {"target_group_arn": arn, "target_id": target},
                        src,
                        region,
                    )

    # ------------------------------------------------------------ data
    def data(self, region: str) -> None:
        subnet_groups: dict[str, list[str]] = {}
        for db in self.call("rds", "describe-db-instances", region).get("DBInstances", []):
            group = db.get("DBSubnetGroup") or {}
            if group.get("DBSubnetGroupName"):
                subnet_groups[group["DBSubnetGroupName"]] = [
                    s.get("SubnetIdentifier") for s in group.get("Subnets", [])
                ]
            self.add(
                "aws_db_instance",
                db["DBInstanceIdentifier"],
                {
                    "id": db.get("DbiResourceId"),
                    "arn": db.get("DBInstanceArn"),
                    "identifier": db["DBInstanceIdentifier"],
                    "instance_class": db.get("DBInstanceClass"),
                    "engine": db.get("Engine"),
                    "engine_version": db.get("EngineVersion"),
                    "db_subnet_group_name": group.get("DBSubnetGroupName"),
                    "cluster_identifier": db.get("DBClusterIdentifier"),
                    "vpc_security_group_ids": [
                        g.get("VpcSecurityGroupId") for g in db.get("VpcSecurityGroups", [])
                    ],
                },
                f"aws rds ({region})",
                region,
            )
        for cluster in self.call("rds", "describe-db-clusters", region).get("DBClusters", []):
            self.add(
                "aws_rds_cluster",
                cluster["DBClusterIdentifier"],
                {
                    "arn": cluster.get("DBClusterArn"),
                    "cluster_identifier": cluster["DBClusterIdentifier"],
                    "engine": cluster.get("Engine"),
                    "engine_version": cluster.get("EngineVersion"),
                    "db_subnet_group_name": cluster.get("DBSubnetGroup"),
                    "vpc_security_group_ids": [
                        g.get("VpcSecurityGroupId") for g in cluster.get("VpcSecurityGroups", [])
                    ],
                },
                f"aws rds ({region})",
                region,
            )
        for name, subnets in subnet_groups.items():
            self.add(
                "aws_db_subnet_group",
                name,
                {"id": name, "name": name, "subnet_ids": subnets},
                f"aws rds ({region})",
                region,
            )
        for group in self.call("elasticache", "describe-cache-subnet-groups", region).get(
            "CacheSubnetGroups", []
        ):
            self.add(
                "aws_elasticache_subnet_group",
                group["CacheSubnetGroupName"],
                {
                    "id": group["CacheSubnetGroupName"],
                    "name": group["CacheSubnetGroupName"],
                    "subnet_ids": [s.get("SubnetIdentifier") for s in group.get("Subnets", [])],
                },
                f"aws elasticache ({region})",
                region,
            )
        for cache in self.call("elasticache", "describe-cache-clusters", region).get(
            "CacheClusters", []
        ):
            self.add(
                "aws_elasticache_cluster",
                cache["CacheClusterId"],
                {
                    "arn": cache.get("ARN"),
                    "cluster_id": cache["CacheClusterId"],
                    "name": cache["CacheClusterId"],
                    "node_type": cache.get("CacheNodeType"),
                    "engine": cache.get("Engine"),
                    "subnet_group_name": cache.get("CacheSubnetGroupName"),
                    "security_group_ids": [
                        g.get("SecurityGroupId") for g in cache.get("SecurityGroups", [])
                    ],
                },
                f"aws elasticache ({region})",
                region,
            )
        for system in self.call("efs", "describe-file-systems", region).get("FileSystems", []):
            self.add(
                "aws_efs_file_system",
                system["FileSystemId"],
                {
                    "id": system["FileSystemId"],
                    "arn": system.get("FileSystemArn"),
                    "name": system.get("Name"),
                    "tags": tags(system.get("Tags")),
                },
                f"aws efs ({region})",
                region,
            )
        for table in self.call("dynamodb", "list-tables", region).get("TableNames", []):
            self.add(
                "aws_dynamodb_table", table, {"name": table}, f"aws dynamodb ({region})", region
            )
        for url in self.call("sqs", "list-queues", region).get("QueueUrls", []):
            name = url.rsplit("/", 1)[-1]
            self.add(
                "aws_sqs_queue", name, {"id": url, "name": name}, f"aws sqs ({region})", region
            )
        for topic in self.call("sns", "list-topics", region).get("Topics", []):
            arn = topic.get("TopicArn", "")
            self.add(
                "aws_sns_topic",
                arn.rsplit(":", 1)[-1],
                {"arn": arn, "name": arn.rsplit(":", 1)[-1]},
                f"aws sns ({region})",
                region,
            )
        for api in self.call("apigatewayv2", "get-apis", region).get("Items", []):
            self.add(
                "aws_apigatewayv2_api",
                api["ApiId"],
                {
                    "id": api["ApiId"],
                    "name": api.get("Name"),
                    "protocol_type": api.get("ProtocolType"),
                },
                f"aws apigatewayv2 ({region})",
                region,
            )

    def global_services(self, region: str) -> None:
        for bucket in self.call("s3api", "list-buckets", None).get("Buckets", []):
            name = bucket["Name"]
            self.add(
                "aws_s3_bucket",
                name,
                {"bucket": name, "arn": f"arn:aws:s3:::{name}", "id": name},
                "aws s3api list-buckets",
                None,
            )
        listing = self.call("cloudfront", "list-distributions", None).get("DistributionList") or {}
        for distribution in listing.get("Items", []) or []:
            origins = (distribution.get("Origins") or {}).get("Items") or []
            self.add(
                "aws_cloudfront_distribution",
                distribution["Id"],
                {
                    "id": distribution["Id"],
                    "arn": distribution.get("ARN"),
                    "domain_name": distribution.get("DomainName"),
                    "origin": [{"domain_name": o.get("DomainName")} for o in origins],
                },
                "aws cloudfront list-distributions",
                None,
            )
        for zone in self.call("route53", "list-hosted-zones", None).get("HostedZones", []):
            zone_id = zone["Id"].rsplit("/", 1)[-1]
            self.add(
                "aws_route53_zone",
                zone_id,
                {"id": zone_id, "name": zone.get("Name", "").rstrip(".")},
                "aws route53 list-hosted-zones",
                None,
            )


def discover_aws(
    *, regions: list[str] | None = None, profile: str | None = None, runner: Runner | None = None
) -> Estate:
    """What the signed-in account holds in ``regions``, as an estate."""
    chosen = list(dict.fromkeys(regions or []))
    if not chosen:
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise DiscoveryError("name a region with --region (or set AWS_REGION)")
        chosen = [region]
    reader = _Reader(runner or cli_runner("aws"), profile)
    try:
        identity = (
            reader.run(
                [
                    "sts",
                    "get-caller-identity",
                    "--output",
                    "json",
                    *(["--profile", profile] if profile else []),
                ]
            )
            or {}
        )
    except CallError as error:
        raise DiscoveryError(f"the aws CLI cannot sign in: {error.message}") from error
    account = identity.get("Account", "?")
    for region in chosen:
        reader.networks(region)
        reader.compute(region)
        reader.balancers(region)
        reader.data(region)
    reader.global_services(chosen[0])
    estate = Estate(
        f"AWS account {account}",
        f"AWS account {account} in {', '.join(chosen)}, read-only",
        reader.found,
        reader.notes,
    )
    link_by_value(estate)
    return estate
