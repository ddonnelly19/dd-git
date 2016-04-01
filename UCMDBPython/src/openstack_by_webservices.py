# coding=utf-8
import sys
import logger
import modeling
import openstack_discoverer
import openstack

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants

from org.jclouds import ContextBuilder
from org.jclouds.openstack.keystone.v2_0 import KeystoneApi
from org.jclouds.openstack.nova.v2_0 import NovaApi
from org.jclouds.openstack.neutron.v2 import NeutronApi
from org.jclouds.openstack.glance.v1_0 import GlanceApi
from org.jclouds.openstack.cinder.v1 import CinderApi

from com.google.common.io import Closeables

def buildApi(provider, endpoint, identity, credential, classname):
    return ContextBuilder.newBuilder(provider).endpoint(endpoint).credentials(identity, credential).buildApi(classname)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    endpoint = Framework.getDestinationAttribute('endpoint')
    ip = Framework.getDestinationAttribute('ip')
    protocols = Framework.getAvailableProtocols(ip, "http")

    if len(protocols) == 0:
        msg = 'Protocol not defined or IP out of protocol network range'
        logger.reportWarning(msg)
        logger.error(msg)
        return OSHVResult

    novaApi = None
    cinderApi = None
    glanceApi = None
    neutronApi = None

    zoneOshDict = {}
    serverOshDict = {}
    networkOshDict = {}

    for protocol in protocols:
        try:
            identity = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME)
            credential = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD)

            keystoneApi = buildApi('openstack-keystone', endpoint, identity, credential, KeystoneApi)
            logger.debug('keystoneApi:', keystoneApi)

            tenant_discover = openstack_discoverer.TenantDiscoverer(keystoneApi)
            tenants = tenant_discover.discover()
            if tenants:
                openstack_software = openstack.OpenStack(ip, credentials_id=protocol)
                openstack_osh, openstack_vector = openstack_software.report()
                OSHVResult.addAll(openstack_vector)
            else:
                continue

            for tenant in tenants:
                tenant_osh = tenant.report()
                OSHVResult.add(tenant_osh)
                OSHVResult.add(modeling.createLinkOSH("composition", openstack_osh, tenant_osh))

                identity = tenant.name + ":" + identity

                novaApi = buildApi('openstack-nova', endpoint, identity, credential, NovaApi)
                cinderApi = buildApi('openstack-cinder', endpoint, identity, credential, CinderApi)
                glanceApi = buildApi('openstack-glance', endpoint, identity, credential, GlanceApi)
                neutronApi = buildApi('openstack-neutron', endpoint, identity, credential, NeutronApi)

                regions = novaApi.getConfiguredRegions()
                for tmp_region in regions:
                    logger.debug("region:", tmp_region)
                    region = openstack.Region(tmp_region)
                    region_osh = region.report(tenant_osh)
                    OSHVResult.add(region_osh)

                    OSHVResult.addAll(getZones(novaApi, region.name, region_osh, zoneOshDict))
                    logger.debug("zoneOshDict:", zoneOshDict)

                    OSHVResult.addAll(getImages(glanceApi, region.name, region_osh))
                    OSHVResult.addAll(getHypervisors(novaApi, region.name, region_osh))
                    OSHVResult.addAll(getVms(novaApi, region.name, region_osh, serverOshDict))

                    OSHVResult.addAll(getVolumes(cinderApi, region.name, region_osh, zoneOshDict, serverOshDict))
                    logger.debug("serverOshDict:", serverOshDict)

                    OSHVResult.addAll(getNetworks(neutronApi, region.name, region_osh, networkOshDict, openstack_osh))
                    logger.debug("networkOshDict:", networkOshDict)

                    OSHVResult.addAll(getPorts(neutronApi, region.name, serverOshDict, networkOshDict))

                    OSHVResult.addAll(getSubnets(neutronApi, region.name, networkOshDict, openstack_osh))

                    OSHVResult.addAll(getFlavors(novaApi, region.name, region_osh))
        except:
            strException = str(sys.exc_info()[1])
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug(strException)
            logger.debug(excInfo)
            pass
        finally:
            if novaApi:
                Closeables.close(novaApi, True)
            if cinderApi:
                Closeables.close(cinderApi, True)
            if glanceApi:
                Closeables.close(glanceApi, True)
            if neutronApi:
                Closeables.close(neutronApi, True)

    reportError = OSHVResult.size() == 0
    if reportError:
        msg = 'Failed to connect using all protocols'
        logger.reportError(msg)
        logger.error(msg)
    return OSHVResult

def getZones(novaApi, regionName, region_osh, zoneOshDict):
    vector = ObjectStateHolderVector()
    zone_discover = openstack_discoverer.ZoneDiscoverer(novaApi, regionName)
    zones = zone_discover.discover()
    for zone in zones:
        zone_osh, zone_vector = zone.report(region_osh)
        zoneOshDict[zone.name] = zone_osh
        vector.addAll(zone_vector)
    return vector

def getVolumes(cinderApi, regionName, region_osh, zoneOshDict, serverOshDict):
    vector = ObjectStateHolderVector()
    volume_discoverer = openstack_discoverer.VolumeDiscoverer(cinderApi, regionName)
    volumes = volume_discoverer.discover()
    for volume in volumes:
        vector.addAll(volume.report(region_osh, zoneOshDict, serverOshDict))
    return vector

def getImages(glanceApi, regionName, region_osh):
    vector = ObjectStateHolderVector()
    image_discover = openstack_discoverer.ImageDiscoverer(glanceApi, regionName)
    images = image_discover.discover()
    for image in images:
        image_osh, image_vector = image.report(region_osh)
        vector.addAll(image_vector)
    return vector

def getHypervisors(novaApi, regionName, region_osh):
    vector = ObjectStateHolderVector()
    hypervisor_discover = openstack_discoverer.HypervisorDiscoverer(novaApi, regionName)
    hypervisors = hypervisor_discover.discover()
    for hypervisor in hypervisors:
        hypervisor_osh, hypervisor_vector = hypervisor.report(region_osh)
        vector.addAll(hypervisor_vector)
    return vector

def getVms(novaApi, regionName, region_osh, serverOshDict):
    vector = ObjectStateHolderVector()
    vm_discoverer = openstack_discoverer.VmDiscoverer(novaApi, regionName)
    vms = vm_discoverer.discover()
    for vm in vms:
        vm_osh, vm_vector = vm.report(region_osh)
        serverOshDict[vm.id] = vm_osh
        vector.addAll(vm_vector)
    return vector

def getNetworks(neutronApi, regionName, region_osh, networkOshDict, openstack_osh):
    vector = ObjectStateHolderVector()
    network_discover = openstack_discoverer.NetworkDiscoverer(neutronApi, regionName)
    networks = network_discover.discover()
    for network in networks:
        network_osh, network_vector = network.report(region_osh, openstack_osh)
        networkOshDict[network.id] = network_osh
        vector.addAll(network_vector)
    return vector

def getPorts(neutronApi, regionName, serverOshDict, networkOshDict):
    vector = ObjectStateHolderVector()
    port_discover = openstack_discoverer.InterfaceDiscoverer(neutronApi, regionName)
    interfaces = port_discover.discover()
    for interface in interfaces:
        vector.addAll(interface.report(serverOshDict, networkOshDict))
    return vector

def getSubnets(neutronApi, regionName, networkOshDict, openstack_osh):
    vector = ObjectStateHolderVector()
    subnet_discover = openstack_discoverer.SubnetDiscoverer(neutronApi, regionName)
    subnets = subnet_discover.discover()
    for subnet in subnets:
        vector.addAll(subnet.report(networkOshDict, openstack_osh))
    return vector

def getFlavors(novaApi, regionName, region_osh):
    vector = ObjectStateHolderVector()
    flavor_discover = openstack_discoverer.FlavorDiscoverer(novaApi, regionName)
    flavors = flavor_discover.discover()
    for flavor in flavors:
        flavor_osh, flavor_vector = flavor.report(region_osh)
        vector.addAll(flavor_vector)
    return vector


