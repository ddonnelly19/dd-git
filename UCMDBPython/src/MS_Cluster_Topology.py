#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent

from java.util import Properties

import errorcodes
import errormessages
import errorobject
import fptools
import logger
import modeling
import dns_resolver
import netutils
import re
import shellutils
import sys
import ms_cluster
import ms_cluster_discoverer
import ip_addr


class NoInstanceFound(Exception):
    pass


def DiscoveryMain(Framework):
    vector = ObjectStateHolderVector()
    codePage = Framework.getCodePage()

    props = Properties()
    props.setProperty(BaseAgent.ENCODING, codePage)

    shell = None
    try:
        client = Framework.createClient(props)
        shell = shellutils.ShellFactory().createShell(client)
        dnsResolver = dns_resolver.NsLookupDnsResolver(shell)

        language = shell.osLanguage
        logger.debug("Using '%s' language bundle" % language.bundlePostfix)
        bundle = shellutils.getLanguageBundle('langMsCluster',
            language, Framework)
        clusterCmd = ms_cluster_discoverer.createClusterCmd(shell, bundle)
        if clusterCmd.isUsingCmd():
            bundle = clusterCmd.detectLangBandle(Framework)
        clusterCmd.setBundle(bundle)
        vector.addAll(_discoverTopology(clusterCmd, bundle,
            dnsResolver))
    except NoInstanceFound:
        errobj = errorobject.createError(
            errorcodes.MS_CLUSTER_INSTANCES_NOT_FOUND,
            None, 'MS cluster instances not found in discovery')
        logger.reportWarningObject(errobj)
    except:
        msg = str(sys.exc_info()[1])
        logger.debugException(msg)
        if (msg.lower().find('timeout') > -1):
            errobj = errorobject.createError(
                errorcodes.CONNECTION_TIMEOUT_NO_PROTOCOL,
                None,
                'Connection timed out - reactivate with larger timeout value')
            logger.reportErrorObject(errobj)
            logger.debugException('Connection timed out')
        else:
            errobj = errormessages.resolveError(msg, 'ntcmd')
            logger.reportErrorObject(errobj)
            logger.errorException(msg)
    try:
        shell and shell.closeClient()
    except:
        logger.debugException()
        logger.error("Unable to close shell")
    return vector


def _discoverTopology(clusterCmd, languageBundle, dnsResolver):
    r'@types: ClusterCmd, ResourceBundle, DNSResolver -> ObjectStateHolderVector'
    vector = ObjectStateHolderVector()

    # DISCOVER cluster basic topology (cluster + nodes)
    if clusterCmd.isUsingCmd():
        getCluster = clusterCmd.getCluster
    else:
        getCluster = clusterCmd.getClusterByPowerShell

    cluster = ms_cluster.createClusterWithDetails(getCluster(),
        fptools.safeFunc(clusterCmd.getClusterDetails)())
    logger.info("Found ", cluster)
    # DISCOVER nodes
    nodes = []
    detailsContentByName = {}
    getNodeAddress = fptools.safeFunc(clusterCmd.getHostAddressesbyNetinterface)
    ipsByNodeName = {}
    for node in clusterCmd.findNodes():
        logger.info("Discovered %s" % node)
        # in case if IP of node cannot be resolved there is no need to continue
        # discovery of this node
        ips = (dnsResolver.resolve_ips(node.name)
               or getNodeAddress(node.name))
        if not ips:
            logger.warn("Skip %s due to not resolved address" % node)
            continue
        ipsByNodeName[node.name.lower()] = ips

        details = None
        try:
            details = clusterCmd.getNodeDetails(node.name)
            buffer = clusterCmd.getLastCommandOutput()
            detailsContentByName[node.name.lower()] = buffer
        except Exception:
            logger.warnException("Failed to get details for %s" % node)

        # if needed re-create node with details in it
        nodes.append((details
                      and ms_cluster.Node(node.name, details=details)
                      or node))

    # REPORT cluster topology
    clusterBuilder = ms_cluster.Builder()
    clusterPdo = clusterBuilder.Pdo(cluster, len(nodes))
    clusterOsh = clusterBuilder.buildClusterPdo(clusterPdo)
    vector.add(clusterOsh)

    # REPORT nodes
    softwareOshByNodeName = {}
    for node in nodes:
        softwareOsh, nodeVector = _reportNode(
            node, cluster, ipsByNodeName.get(node.name.lower()), clusterOsh,
            dnsResolver.resolve_fqdn(node.name),
            detailsContentByName.get(node.name.lower()))
        vector.addAll(nodeVector)
        softwareOshByNodeName[node.name.lower()] = softwareOsh

    # DISCOVER resource groups
    if len(nodes) > 0:
        resourceBuilder = ms_cluster.ResourceBuilder()
        resourceReporter = ms_cluster.ResourceReporter(resourceBuilder)
        groups = clusterCmd.getResourceGroups()
        for group in groups:
            logger.info("Found %s" % group)
            groupDetails = fptools.safeFunc(clusterCmd.getResourceGroupDetails)(group.name)
            # update group with details
            groupDetailsContent = None
            if groupDetails:
                groupDetailsContent = clusterCmd.getLastCommandOutput()
                group = ms_cluster.ResourceGroup(group.name, group.nodeName,
                    groupDetails)
            else:
                logger.warn("Failed to get details")
            if clusterCmd.isUsingCmd():
                groupOwners = fptools.safeFunc(clusterCmd.getResourceGroupOwners)(group.name) or ()
            else:
                groupOwners = fptools.safeFunc(clusterCmd.getResourceGroupOwnersByPowerShell)(group.name) or ()
            if groupOwners:
                logger.info("Group owners are %s" % groupOwners)
                # get resources in the group and filter only IP resources
            resources = []
            # for this group resources get their details
            dependenciesByGroupName = {}
            privateDetBufferByResourceName = {}
            publicDetBufferByResourceName = {}
            logger.info("Discover group resources")
            try:
                if clusterCmd.isUsingCmd():
                    groupResources = clusterCmd.getResourcesByGroup(group.name)
                else:
                    groupResources = clusterCmd.getResourcesByGroupByPowerShell(group.name)
            except ms_cluster_discoverer.ClusterCmd.ExecuteException:
                logger.warn("Failed to find resources for %s" % group)
            else:
                for resource in groupResources:
                    logger.info("\tFound %s" % resource)
                    try:
                        resourceDetails = clusterCmd.getResourceDetails(resource.name)
                        publicDetBufferByResourceName[resource.name] = clusterCmd.getLastCommandOutput()
                        resource = ms_cluster.Resource(resource.name,
                            resource.groupName, resource.status, resourceDetails)
                    except Exception:
                        logger.warnException("Failed to get %s details" % resource)
                    try:
                        clusterCmd.getResourcePrivateDetails(resource.name)
                        privateDetBuffer = clusterCmd.getLastCommandOutput()
                        privateDetBufferByResourceName[resource.name.lower()] = privateDetBuffer
                        if resourceDetails.type == 'Network Name':
                            (networkName, fqdn )= ms_cluster_discoverer.getCrgNeworkNames(privateDetBuffer, dnsResolver)
                            if networkName or fqdn:
                                group = ms_cluster.ResourceGroup(group.name, group.nodeName,
                                    groupDetails, networkName, fqdn)
                    except Exception:
                        logger.warnException("Failed to get %s private details" % resource)
                    try:
                        dependencies = clusterCmd.getResourceDependencies(resource.name, group.name)
                        dependenciesByGroupName[resource.name.lower()] = dependencies
                        if dependencies:
                            logger.info("\t\tDependencies are %s" % dependencies)
                    except Exception:
                        logger.warnException("Failed to get %s dependencies")
                    resources.append(resource)

            # REPORT cluster resources
            # report clustered service
            builder = ms_cluster.ClusteredServiceBuilder()
            serviceOsh = builder.buildClusteredService(cluster, group)
            vector.add(serviceOsh)
            vector.add(modeling.createLinkOSH('contained', clusterOsh,
                serviceOsh))

            softwareOsh = softwareOshByNodeName.get(group.nodeName.lower())
            if not softwareOsh:
                logger.warn("Failed to find node of %s" % group)
            else:
                runOsh = modeling.createLinkOSH('run', softwareOsh, serviceOsh)
                vector.add(runOsh)

            for softwareOsh in softwareOshByNodeName.values():
                runOsh = modeling.createLinkOSH('potentially_run',
                    softwareOsh, serviceOsh)
                vector.add(runOsh)

            groupReporter = ms_cluster.ResourceGroupReporter(ms_cluster.ResourceGroupBuilder())
            groupOsh = groupReporter.reportGroup(group, serviceOsh)
            vector.add(groupOsh)

            # report group details
            if groupDetailsContent:
                vector.add(_reportGroupDetails(group, groupDetailsContent, groupOsh))

            # report linkage between group owners
            for ownerNodeName in groupOwners:
                # resolve node IPs by owner-node name
                ips = (
                    dnsResolver.resolve_ips(ownerNodeName)
                    or fptools.safeFunc(clusterCmd.getHostAddressesbyNetinterface)
                        (ownerNodeName))
                if not ips:
                    logger.warn("Failed to resolve address for %s" % node)
                    continue
                fqdn = dnsResolver.resolve_fqdn(ownerNodeName)
                vector.addAll(_reportHost(ips, fqdn)[1])
                vector.add(_buildOwnerPotentillyRun(softwareOsh, serviceOsh))

            # report resources
            for resource in resources:
                clusterResourcesPrivBuffer = privateDetBufferByResourceName.get(resource.name.lower())
                pdo = ms_cluster.ResourceBuilder.Pdo(resource, clusterResourcesPrivBuffer)
                resourceOsh = resourceReporter.reportResourcePdo(pdo, groupOsh)
                vector.add(resourceOsh)

                # and dependent resources
                for dependency in dependenciesByGroupName.get(resource.name.lower(), ()):
                    dependencyOsh = resourceReporter.reportResource(dependency, groupOsh)
                    vector.add(dependencyOsh)
                    dependOsh = modeling.createLinkOSH('depend', dependencyOsh, resourceOsh)
                    vector.add(dependOsh)

            # filter resource of type "IP Address" to gather group IPs
            ipResources = filter(ms_cluster.isIpAddressResource, resources)
            addressWord = languageBundle.getString('resource_ip_address_name')
            # look for the IP value inside private properties
            groupIps = []
            logger.info("Look for the IP resources in %s resources" % len(ipResources))
            for resource in ipResources:
                if clusterCmd.isUsingCmd():
                    groupIps.extend(_findIps(
                        privateDetBufferByResourceName.get(resource.name.lower()),
                        (addressWord, 'Address', 'Adresse')))
                else:
                    groupIps.extend(_findIpsByPowerShell(
                        privateDetBufferByResourceName.get(resource.name.lower()),
                        (addressWord, 'Address', 'Adresse')))

            for ip in groupIps:
                logger.info('Found IP(%s) for virtual cluster group %s' % (ip, group.name))
                ipOsh = modeling.createIpOSH(ip)
                containedOsh = modeling.createLinkOSH('contained', serviceOsh, ipOsh)
                vector.add(containedOsh)
                vector.add(ipOsh)
            #check if CRG name is a valid DNS name
            fqdn = group.fqdn
            if not fqdn:
                fqdn = dnsResolver.resolve_fqdn(group.name)
                if fqdn:
                    serviceOsh.setStringAttribute('primary_dns_name', fqdn)
            if not groupIps:
                logger.warn('Failed to resolve cluster IP for group %s' % group.name)
            elif not fqdn:
                primaryIp = groupIps[0]
                fqdn = dnsResolver.resolve_ips(str(primaryIp))
                if fqdn:
                    serviceOsh.setStringAttribute('primary_dns_name', fqdn[0])
    else:
        raise NoInstanceFound()
    return vector


def _buildOwnerPotentillyRun(softwareOsh, serviceOsh):
    osh = modeling.createLinkOSH('potentially_run', softwareOsh, serviceOsh)
    osh.setAttribute('data_name', 'Preferred Owner')
    osh.setBoolAttribute('is_owner', 1)
    return osh


def _reportNode(node, cluster, ips, clusterOsh, fqdn=None, nodeDetailsContent=None):
    r'@types: Node, Cluster, list[ip_addr.IPAddress], ObjectStateHolder, str, str -> tuple[ObjectStateHolder, ObjectStateHolderVector]'
    assert node and cluster and ips and clusterOsh
    vector = ObjectStateHolderVector()
    hostOsh, nodeVector = _reportHost(ips, fqdn)
    vector.addAll(nodeVector)
    # report cluster software running on the node
    softwareOsh = modeling.createClusterSoftwareOSH(hostOsh,
        'Microsoft Cluster SW', cluster.version)
    vector.add(softwareOsh)
    vector.add(modeling.createLinkOSH('membership', clusterOsh, softwareOsh))
    if nodeDetailsContent:
        vector.add(_reportNodeDetails(node, nodeDetailsContent, softwareOsh))
    return softwareOsh, vector


def _reportNodeDetails(node, content, containerOsh):
    r'@types: ms_cluster.Node, str -> ObjectStateHolder'
    return modeling.createConfigurationDocumentOSH(
        'MSCS_%s_properties.properties' % node.name, None,
        content, containerOsh, modeling.MIME_TEXT_PLAIN, None,
        'Cluster properties output', None, 'UTF-8')


def _reportHost(ips, fqnd):
    r'@types: [ip_addr.IPAddress] -> tuple[ObjectStateHolder, ObjectStateHolderVector]'
    assert ips
    vector = ObjectStateHolderVector()
    nodeOsh = _buildWindowsHost(ips[0], fqnd)
    for ip_obj in ips:
        ipOSH = modeling.createIpOSH(ip_obj)
        vector.add(ipOSH)
        vector.add(modeling.createLinkOSH('containment', nodeOsh, ipOSH))
    vector.add(nodeOsh)
    return nodeOsh, vector


def _buildWindowsHost(ip, fqdn):
    r'@types: ip_addr.IPAddress, str -> ObjectStateHolder'
    osh = (modeling.createHostOSH(str(ip), 'nt')
           or ObjectStateHolder('nt'))
    # populate node with DNS information
    if fqdn:
        if fqdn.count('.') > 0:
            osh.setStringAttribute('primary_dns_name', fqdn)
            osh.setStringAttribute('name', fqdn.split('.')[0])
        else:
            osh.setStringAttribute('name', fqdn)
    osh.setStringAttribute('os_family', 'windows')
    return osh


def _reportGroupDetails(group, content, containerOsh):
    r'@types: ResourceGroup, str, ObjectStateHolder -> ObjectStateHolder'
    return modeling.createConfigurationDocumentOSH(
        "MSCS_group_properties.properties", None,
        content, containerOsh, modeling.MIME_TEXT_PLAIN, None,
        'Cluster group prop output', None, 'UTF-8')


def _findIps(resourceProperties, ipMarkers):
    '@types: str, seq[str] -> list[ip_addr._BaseIP]'
    if resourceProperties:
        createIp = fptools.safeFunc(ip_addr.IPAddress)
        ipPattern = '\s+%s\s+(\S*)$'
        return parseFindIpsOutput(resourceProperties, ipMarkers, ipPattern)

def _findIpsByPowerShell(resourceProperties, ipMarkers):
    '@types: str, seq[str] -> list[ip_addr._BaseIP]'
    if resourceProperties:
        ipPattern = '\s+%s\s+(\S*)\s+(\S*)$'
        return parseFindIpsOutput(resourceProperties, ipMarkers, ipPattern)


def parseFindIpsOutput(resourceProperties, ipMarkers, ipPattern):
    createIp = fptools.safeFunc(ip_addr.IPAddress)
    for ipMarker in ipMarkers:
        for line in resourceProperties.splitlines():
            ipMatcher = re.search(ipPattern % ipMarker, line)
            if ipMatcher:
                ip = createIp(ipMatcher.group(1).strip())
                if ip:
                    return [ip]
    return []
