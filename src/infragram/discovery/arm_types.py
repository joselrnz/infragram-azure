"""Which node class draws an Azure resource, by its ARM type.

Resource Graph reports every resource's type in lower case
(``microsoft.network/applicationgateways``), so the table is keyed that way.
A value names a class under ``infragram.nodes.azure`` as ``module.Class``;
the class brings the icon, so nothing here names artwork directly.

Some types are one type in ARM and several services to a reader: a
``microsoft.web/sites`` is a web app, a function app or a Logic App by its
``kind``, and a Cognitive Services account is Azure OpenAI or Speech the
same way. :data:`BY_KIND` settles those before the plain table is read.

:data:`PLUMBING` lists the types that exist to support something else --
network interfaces, OS disks, alert rules, VM extensions. Drawn, they bury
the estate under its own wiring, so the importer leaves them out unless
asked for everything. A network interface still places its VM in a subnet;
it is only never drawn.
"""

from __future__ import annotations

from importlib import import_module

from ..nodes._base import Element

__all__ = ["BY_KIND", "FALLBACK", "PLUMBING", "TYPES", "class_path", "node_class", "short_type"]

#: What an unknown type draws as.
FALLBACK = "general.AllResources"

TYPES: dict[str, str] = {
    # --- compute ---------------------------------------------------------
    "microsoft.compute/virtualmachines": "compute.VirtualMachine",
    "microsoft.compute/virtualmachinescalesets": "compute.VMScaleSets",
    "microsoft.compute/availabilitysets": "compute.AvailabilitySets",
    "microsoft.compute/disks": "compute.Disks",
    "microsoft.compute/snapshots": "compute.DisksSnapshots",
    "microsoft.compute/images": "compute.Images",
    "microsoft.compute/galleries": "compute.AzureComputeGalleries",
    "microsoft.compute/galleries/images": "compute.ImageDefinitions",
    "microsoft.compute/galleries/images/versions": "compute.ImageVersions",
    "microsoft.compute/diskencryptionsets": "compute.DiskEncryptionSets",
    "microsoft.compute/hostgroups": "compute.HostGroups",
    "microsoft.compute/hostgroups/hosts": "compute.Hosts",
    "microsoft.compute/restorepointcollections": "compute.RestorePointsCollections",
    "microsoft.compute/sshpublickeys": "other.SSHKeys",
    "microsoft.compute/proximityplacementgroups": "networking.ProximityPlacementGroups",
    "microsoft.compute/capacityreservationgroups": "other.CapacityReservationGroups",
    "microsoft.compute/virtualmachines/extensions": "general.Extensions",
    "microsoft.compute/virtualmachinescalesets/extensions": "general.Extensions",
    "microsoft.batch/batchaccounts": "compute.BatchAccounts",
    "microsoft.desktopvirtualization/hostpools": "compute.HostPools",
    "microsoft.desktopvirtualization/applicationgroups": "compute.ApplicationGroup",
    "microsoft.desktopvirtualization/workspaces": "compute.Workspaces",
    "microsoft.servicefabric/clusters": "compute.ServiceFabricClusters",
    "microsoft.servicefabric/managedclusters": "compute.ManagedServiceFabric",
    "microsoft.appplatform/spring": "compute.AzureSpringApps",
    "microsoft.avs/privateclouds": "other.AzureVmwareSolution",
    "microsoft.hybridcompute/machines": "management_governance.ArcMachines",
    # --- containers ------------------------------------------------------
    "microsoft.containerservice/managedclusters": "compute.KubernetesServices",
    "microsoft.containerservice/fleets": "other.KubernetesFleetManager",
    "microsoft.containerinstance/containergroups": "compute.ContainerInstances",
    "microsoft.containerregistry/registries": "containers.ContainerRegistries",
    "microsoft.redhatopenshift/openshiftclusters": "containers.AzureRedHatOpenShift",
    "microsoft.kubernetes/connectedclusters": "management_governance.AzureArc",
    "microsoft.app/managedenvironments": "other.ContainerAppsEnvironments",
    "microsoft.app/containerapps": "other.WorkerContainerApp",
    "microsoft.app/jobs": "other.WorkerContainerApp",
    # --- web and app services --------------------------------------------
    "microsoft.web/sites": "app_services.AppServices",
    "microsoft.web/sites/slots": "general.WebSlots",
    "microsoft.web/serverfarms": "app_services.AppServicePlans",
    "microsoft.web/hostingenvironments": "app_services.AppServiceEnvironments",
    "microsoft.web/staticsites": "web.StaticApps",
    "microsoft.web/certificates": "app_services.AppServiceCertificates",
    "microsoft.web/connections": "devops.APIConnections",
    "microsoft.certificateregistration/certificateorders": "app_services.AppServiceCertificates",
    "microsoft.domainregistration/domains": "app_services.AppServiceDomains",
    "microsoft.signalrservice/signalr": "web.Signalr",
    "microsoft.signalrservice/webpubsub": "integration.Pubsub",
    "microsoft.notificationhubs/namespaces": "iot.NotificationHubNamespaces",
    "microsoft.notificationhubs/namespaces/notificationhubs": "app_services.NotificationHubs",
    "microsoft.apimanagement/service": "devops.APIManagementServices",
    "microsoft.apicenter/services": "web.APICenter",
    "microsoft.search/searchservices": "ai_machine_learning.CognitiveSearch",
    "microsoft.communication/communicationservices": "other.AzureCommunicationServices",
    # --- networking ------------------------------------------------------
    "microsoft.network/virtualnetworks": "networking.VirtualNetworks",
    "microsoft.network/networkinterfaces": "networking.NetworkInterfaces",
    "microsoft.network/networksecuritygroups": "networking.NetworkSecurityGroups",
    "microsoft.network/applicationsecuritygroups": "security.ApplicationSecurityGroups",
    "microsoft.network/publicipaddresses": "networking.PublicIPAddresses",
    "microsoft.network/publicipprefixes": "networking.PublicIPPrefixes",
    "microsoft.network/customipprefixes": "other.CustomIPPrefix",
    "microsoft.network/loadbalancers": "networking.LoadBalancers",
    "microsoft.network/applicationgateways": "networking.ApplicationGateways",
    "microsoft.network/applicationgatewaywebapplicationfirewallpolicies": "networking.WebApplicationFirewallPoliciesWAF",
    "microsoft.network/frontdoorwebapplicationfirewallpolicies": "networking.WebApplicationFirewallPoliciesWAF",
    "microsoft.network/azurefirewalls": "networking.Firewalls",
    "microsoft.network/firewallpolicies": "networking.AzureFirewallPolicy",
    "microsoft.network/bastionhosts": "networking.Bastions",
    "microsoft.network/virtualnetworkgateways": "networking.VirtualNetworkGateways",
    "microsoft.network/localnetworkgateways": "networking.LocalNetworkGateways",
    "microsoft.network/connections": "networking.Connections",
    "microsoft.network/expressroutecircuits": "networking.ExpressrouteCircuits",
    "microsoft.network/expressrouteports": "other.ExpressrouteDirect",
    "microsoft.network/expressroutegateways": "networking.VirtualNetworkGateways",
    "microsoft.network/vpngateways": "networking.VirtualNetworkGateways",
    "microsoft.network/p2svpngateways": "networking.VirtualNetworkGateways",
    "microsoft.network/vpnsites": "networking.LocalNetworkGateways",
    "microsoft.network/virtualwans": "networking.VirtualWans",
    "microsoft.network/virtualhubs": "networking.VirtualWANHub",
    "microsoft.network/virtualrouters": "networking.VirtualRouter",
    "microsoft.network/routetables": "networking.RouteTables",
    "microsoft.network/routefilters": "networking.RouteFilters",
    "microsoft.network/natgateways": "networking.NAT",
    "microsoft.network/privateendpoints": "other.PrivateEndpoints",
    "microsoft.network/privatelinkservices": "networking.PrivateLinkService",
    "microsoft.network/privatednszones": "networking.DNSZones",
    "microsoft.network/privatednszones/virtualnetworklinks": "networking.DNSZones",
    "microsoft.network/dnszones": "networking.DNSZones",
    "microsoft.network/dnsresolvers": "networking.DNSPrivateResolver",
    "microsoft.network/trafficmanagerprofiles": "networking.TrafficManagerProfiles",
    "microsoft.network/frontdoors": "networking.FrontDoorAndCDNProfiles",
    "microsoft.network/ddosprotectionplans": "networking.DdosProtectionPlans",
    "microsoft.network/ipgroups": "networking.IPGroups",
    "microsoft.network/networkmanagers": "other.NetworkManagers",
    "microsoft.network/networksecurityperimeters": "other.NetworkSecurityPerimeters",
    "microsoft.network/serviceendpointpolicies": "networking.ServiceEndpointPolicies",
    "microsoft.network/networkwatchers": "monitor.NetworkWatcher",
    "microsoft.network/networkwatchers/flowlogs": "monitor.NetworkWatcher",
    "microsoft.cdn/profiles": "networking.FrontDoorAndCDNProfiles",
    "microsoft.cdn/profiles/endpoints": "networking.CDNProfilesNetworking",
    "microsoft.cdn/profiles/afdendpoints": "networking.CDNProfilesNetworking",
    # --- storage ---------------------------------------------------------
    "microsoft.storage/storageaccounts": "storage.StorageAccounts",
    "microsoft.classicstorage/storageaccounts": "storage.StorageAccountsClassic",
    "microsoft.netapp/netappaccounts": "storage.AzureNetappFiles",
    "microsoft.netapp/netappaccounts/capacitypools": "storage.AzureNetappFiles",
    "microsoft.netapp/netappaccounts/capacitypools/volumes": "storage.AzureNetappFiles",
    "microsoft.storagesync/storagesyncservices": "storage.StorageSyncServices",
    "microsoft.storagecache/caches": "storage.AzureHcpCache",
    "microsoft.elasticsan/elasticsans": "other.ElasticSAN",
    "microsoft.datashare/accounts": "storage.DataShares",
    "microsoft.databox/jobs": "storage.DataBoxStorage",
    "microsoft.recoveryservices/vaults": "management_governance.RecoveryServicesVaults",
    "microsoft.dataprotection/backupvaults": "other.BackupVault",
    # --- databases -------------------------------------------------------
    "microsoft.sql/servers": "databases.SQLServer",
    "microsoft.sql/servers/databases": "databases.SQLDatabase",
    "microsoft.sql/servers/elasticpools": "databases.SQLElasticPools",
    "microsoft.sql/managedinstances": "databases.SQLManagedInstance",
    "microsoft.sql/managedinstances/databases": "databases.ManagedDatabase",
    "microsoft.sql/virtualclusters": "databases.VirtualClusters",
    "microsoft.sqlvirtualmachine/sqlvirtualmachines": "databases.AzureSQLVM",
    "microsoft.documentdb/databaseaccounts": "databases.AzureCosmosDB",
    "microsoft.documentdb/mongoclusters": "databases.AzureCosmosDB",
    "microsoft.documentdb/cassandraclusters": "other.ManagedInstanceApacheCassandra",
    "microsoft.dbforpostgresql/servers": "databases.AzureDatabasePostgreSQLServer",
    "microsoft.dbforpostgresql/flexibleservers": "databases.AzureDatabasePostgreSQLServer",
    "microsoft.dbforpostgresql/servergroupsv2": "databases.AzureDatabasePostgreSQLServerGroup",
    "microsoft.dbformysql/servers": "databases.AzureDatabaseMySQLServer",
    "microsoft.dbformysql/flexibleservers": "databases.AzureDatabaseMySQLServer",
    "microsoft.dbformariadb/servers": "databases.AzureDatabaseMariadbServer",
    "microsoft.cache/redis": "databases.CacheRedis",
    "microsoft.cache/redisenterprise": "databases.AzureManagedRedis",
    "microsoft.datamigration/services": "databases.AzureDatabaseMigrationServices",
    # --- analytics -------------------------------------------------------
    "microsoft.databricks/workspaces": "analytics.AzureDatabricks",
    "microsoft.databricks/accessconnectors": "analytics.AzureDatabricks",
    "microsoft.synapse/workspaces": "analytics.AzureSynapseAnalytics",
    "microsoft.datafactory/factories": "analytics.DataFactories",
    "microsoft.eventhub/namespaces": "analytics.EventHubs",
    "microsoft.eventhub/clusters": "analytics.EventHubClusters",
    "microsoft.streamanalytics/streamingjobs": "analytics.StreamAnalyticsJobs",
    "microsoft.hdinsight/clusters": "analytics.HdInsightClusters",
    "microsoft.analysisservices/servers": "analytics.AnalysisServices",
    "microsoft.powerbidedicated/capacities": "analytics.PowerBIEmbedded",
    "microsoft.kusto/clusters": "analytics.AzureDataExplorerClusters",
    "microsoft.operationalinsights/workspaces": "analytics.LogAnalyticsWorkspaces",
    # --- integration -----------------------------------------------------
    "microsoft.servicebus/namespaces": "integration.AzureServiceBus",
    "microsoft.eventgrid/topics": "integration.EventGridTopics",
    "microsoft.eventgrid/domains": "integration.EventGridDomains",
    "microsoft.eventgrid/systemtopics": "integration.SystemTopic",
    "microsoft.eventgrid/namespaces": "integration.EventGridTopics",
    "microsoft.eventgrid/partnernamespaces": "integration.PartnerNamespace",
    "microsoft.logic/workflows": "integration.LogicApps",
    "microsoft.logic/integrationaccounts": "integration.IntegrationAccounts",
    "microsoft.appconfiguration/configurationstores": "integration.AppConfiguration",
    "microsoft.relay/namespaces": "integration.Relays",
    "microsoft.datacatalog/catalogs": "integration.AzureDataCatalog",
    "microsoft.healthcareapis/services": "integration.AzureAPIForFhir",
    "microsoft.healthcareapis/workspaces/fhirservices": "other.FhirService",
    # --- AI and machine learning -----------------------------------------
    "microsoft.cognitiveservices/accounts": "ai_machine_learning.CognitiveServices",
    "microsoft.cognitiveservices/accounts/projects": "ai_machine_learning.FoundryProject",
    "microsoft.machinelearningservices/workspaces": "ai_machine_learning.AzureMachineLearning",
    "microsoft.machinelearningservices/registries": "ai_machine_learning.AzureMachineLearning",
    "microsoft.botservice/botservices": "ai_machine_learning.BotServices",
    # --- security and identity -------------------------------------------
    "microsoft.keyvault/vaults": "security.KeyVaults",
    "microsoft.keyvault/managedhsms": "other.DedicatedHSM",
    "microsoft.hardwaresecuritymodules/dedicatedhsms": "other.DedicatedHSM",
    "microsoft.managedidentity/userassignedidentities": "identity.ManagedIdentities",
    "microsoft.aad/domainservices": "identity.EntraDomainServices",
    "microsoft.azureactivedirectory/b2cdirectories": "identity.AzureAdB2c",
    "microsoft.attestation/attestationproviders": "other.Azureattestation",
    "microsoft.confidentialledger/ledgers": "other.ConfidentialLedgers",
    # --- monitoring and management ---------------------------------------
    "microsoft.insights/components": "monitor.ApplicationInsightsMonitor",
    "microsoft.insights/workbooks": "monitor.AzureWorkbooksMonitor",
    "microsoft.insights/actiongroups": "management_governance.Alerts",
    "microsoft.insights/metricalerts": "management_governance.Alerts",
    "microsoft.insights/scheduledqueryrules": "management_governance.Alerts",
    "microsoft.insights/activitylogalerts": "management_governance.Alerts",
    "microsoft.insights/autoscalesettings": "monitor.AutoScale",
    "microsoft.insights/datacollectionrules": "other.DataCollectionRules",
    "microsoft.insights/datacollectionendpoints": "other.DataCollectionRules",
    "microsoft.alertsmanagement/smartdetectoralertrules": "management_governance.Alerts",
    "microsoft.alertsmanagement/prometheusrulegroups": "management_governance.Alerts",
    "microsoft.alertsmanagement/actionrules": "management_governance.Alerts",
    "microsoft.monitor/accounts": "other.Promethus",
    "microsoft.dashboard/grafana": "other.AzureManagedGrafana",
    "microsoft.portal/dashboards": "other.AzureMonitorDashboard",
    "microsoft.automation/automationaccounts": "management_governance.AutomationAccounts",
    "microsoft.automation/automationaccounts/runbooks": "management_governance.AutomationAccounts",
    "microsoft.operationsmanagement/solutions": "management_governance.Solutions",
    "microsoft.maintenance/maintenanceconfigurations": "compute.MaintenanceConfiguration",
    "microsoft.resources/templatespecs": "other.TemplateSpecs",
    "microsoft.resources/templatespecs/versions": "other.TemplateSpecs",
    "microsoft.resources/deploymentscripts": "general.Powershell",
    "microsoft.chaos/experiments": "other.AzureChaosStudio",
    "microsoft.loadtestservice/loadtests": "devops.LoadTesting",
    "microsoft.devcenter/devcenters": "other.MicrosoftDevBox",
    "microsoft.devcenter/projects": "other.MicrosoftDevBox",
    "microsoft.devtestlab/labs": "devops.DevtestLabs",
    "microsoft.labservices/labplans": "devops.LabServices",
    "microsoft.labservices/labs": "devops.LabServices",
    "microsoft.devopsinfrastructure/pools": "devops.ManagedDevOpsPools",
    "microsoft.visualstudio/account": "devops.AzureDevOps",
    # --- IoT -------------------------------------------------------------
    "microsoft.devices/iothubs": "iot.IoTHub",
    "microsoft.devices/provisioningservices": "iot.DeviceProvisioningServices",
    "microsoft.digitaltwins/digitaltwinsinstances": "iot.DigitalTwins",
    "microsoft.iotcentral/iotapps": "iot.IoTCentralApplications",
    "microsoft.maps/accounts": "iot.AzureMapsAccounts",
    "microsoft.timeseriesinsights/environments": "iot.TimeSeriesInsightsEnvironments",
}

#: ``type -> {kind fragment: class}``; the first fragment found in the
#: resource's lower-cased ``kind`` wins, so list the narrower one first.
BY_KIND: dict[str, dict[str, str]] = {
    "microsoft.web/sites": {
        "workflowapp": "integration.LogicApps",
        "functionapp": "compute.FunctionApps",
    },
    "microsoft.cognitiveservices/accounts": {
        "openai": "ai_machine_learning.AzureOpenAI",
        "aiservices": "ai_machine_learning.AIFoundry",
        "formrecognizer": "ai_machine_learning.FormRecognizers",
        "computervision": "ai_machine_learning.ComputerVision",
        "speechservices": "ai_machine_learning.SpeechServices",
        "textanalytics": "ai_machine_learning.Language",
        "contentsafety": "ai_machine_learning.ContentSafety",
        "texttranslation": "ai_machine_learning.TranslatorText",
        "face": "ai_machine_learning.FaceAPIS",
        "customvision": "ai_machine_learning.CustomVision",
        "contentmoderator": "ai_machine_learning.ContentModerators",
        "anomalydetector": "ai_machine_learning.AnomalyDetector",
        "personalizer": "ai_machine_learning.Personalizers",
        "qnamaker": "ai_machine_learning.QnaMakers",
        "luis": "ai_machine_learning.LanguageUnderstanding",
        "immersivereader": "ai_machine_learning.ImmersiveReaders",
    },
    "microsoft.machinelearningservices/workspaces": {
        "hub": "ai_machine_learning.AIFoundry",
        "project": "ai_machine_learning.FoundryProject",
    },
}

#: Types that support something else and are left out unless ``--all``.
PLUMBING: frozenset[str] = frozenset(
    {
        "microsoft.network/networkinterfaces",
        "microsoft.network/publicipaddresses",
        "microsoft.network/networkwatchers",
        "microsoft.network/networkwatchers/flowlogs",
        "microsoft.network/privatednszones/virtualnetworklinks",
        "microsoft.compute/disks",
        "microsoft.compute/snapshots",
        "microsoft.compute/restorepointcollections",
        "microsoft.compute/sshpublickeys",
        "microsoft.compute/virtualmachines/extensions",
        "microsoft.compute/virtualmachinescalesets/extensions",
        "microsoft.insights/actiongroups",
        "microsoft.insights/metricalerts",
        "microsoft.insights/scheduledqueryrules",
        "microsoft.insights/activitylogalerts",
        "microsoft.insights/autoscalesettings",
        "microsoft.insights/datacollectionrules",
        "microsoft.insights/datacollectionendpoints",
        "microsoft.alertsmanagement/smartdetectoralertrules",
        "microsoft.alertsmanagement/prometheusrulegroups",
        "microsoft.alertsmanagement/actionrules",
        "microsoft.portal/dashboards",
        "microsoft.automation/automationaccounts/runbooks",
        "microsoft.operationsmanagement/solutions",
        "microsoft.maintenance/maintenanceconfigurations",
        "microsoft.resources/deploymentscripts",
        "microsoft.resources/templatespecs/versions",
    }
)


def class_path(arm_type: str, kind: str = "") -> str:
    """The ``module.Class`` a resource draws as."""
    arm_type = arm_type.lower()
    lowered = (kind or "").lower()
    for fragment, path in BY_KIND.get(arm_type, {}).items():
        if fragment in lowered:
            return path
    return TYPES.get(arm_type, FALLBACK)


def node_class(arm_type: str, kind: str = "") -> type[Element]:
    """The node class a resource draws as."""
    module_name, _, class_name = class_path(arm_type, kind).rpartition(".")
    found: type[Element] = getattr(
        import_module(f"infragram.nodes.azure.{module_name}"), class_name
    )
    return found


def short_type(arm_type: str) -> str:
    """``microsoft.network/applicationgateways`` -> ``applicationgateways``."""
    return arm_type.rsplit("/", 1)[-1]
