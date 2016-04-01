#coding=utf-8
import sys

import logger

import file_mon_utils

import errormessages
import errorcodes
import errorobject


from appilog.common.system.types.vectors import ObjectStateHolderVector
from shellutils import ShellUtils
from service_guard_discoverers import (ServiceGuardClusterDiscoverer,
                                    AdditionalPackageResourcesDiscoverer,
                                    OracleDiscoverer, OracleIasDiscoverer)
from service_guard import (Reporter,
                            PackageToRunningSoftwareTopologyBuilder)
import service_guard
import netutils


def getParameter(Framework, parameterName, parameterDefaultValue):
    param = Framework.getDestinationAttribute(parameterName)
    if (param == None) or (param == 'NA'):
        param = parameterDefaultValue
    return param


def discoverConfigFiles(Framework, sgclusterOSH, shellUtils, cmclconfig_path, cmclconfig_files_pattern, OSHVResult):
    #get list of all config files
    file_name = None
    exstention = None
    if cmclconfig_files_pattern.rfind('.') > 0:
        file_name = cmclconfig_files_pattern
    else:
        exstention = cmclconfig_files_pattern

    try:
        fileMonitor = file_mon_utils.FileMonitor(Framework, shellUtils, OSHVResult, exstention, None)
        fileMonitor.getFiles(sgclusterOSH, cmclconfig_path, file_name)
    except:
        errorMessage = 'Failed to find configuration files for Service Guard Cluster'
        logger.debugException('errorMessage')
        errobj = errorobject.createError(errorcodes.FAILED_FINDING_CONFIGURATION_FILE, ['Service Guard Cluster'], errorMessage)
        logger.reportWarningObject(errobj)


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    cmclconfig_path = getParameter(Framework, 'cmclconfig_path', '/etc/cmcluster/')
    cmclconfig_files_pattern = getParameter(Framework, 'cmclconfig_file', 'ascii')

    client = None
    try:
        try:
            client = Framework.createClient()
            shell = ShellUtils(client)

            clusterDiscoverer = ServiceGuardClusterDiscoverer(shell)
            cluster = clusterDiscoverer.discover()

            if cluster.packages:
                # in case any running packages were discovered,
                # try to discover package mount points, ips and networks
                # which do not appear in cmview command output
                addPkgInfoDiscoverer = AdditionalPackageResourcesDiscoverer(shell)
                packageNameToPackageMap = addPkgInfoDiscoverer.discover(cmclconfig_path, cluster)
                #merging data into the stored packages DO
                for package in cluster.packages:
                    addPackage = packageNameToPackageMap.get(package.name)
                    if addPackage:
                        package.mountPoints = addPackage.mountPoints
                        package.additionalIpList = addPackage.additionalIpList
                        package.ipNetworkList = addPackage.ipNetworkList

            endpointReporter = netutils.EndpointReporter(
                                        netutils.ServiceEndpointBuilder())
            quorumServerReporter = service_guard.QuorumServerReporter(
                                        service_guard.QuorumServerBuilder(),
                                        endpointReporter)
            vector = Reporter(quorumServerReporter).report(cluster)
            OSHVResult.addAll(vector)

            softwareInformationList = []
            for discoverer in (OracleDiscoverer(shell),
                               OracleIasDiscoverer(shell)):
                try:
                    softwareInformationList.extend(discoverer.discover())
                except:
                    logger.debugException('')

            if softwareInformationList:
                relationsBuilder = PackageToRunningSoftwareTopologyBuilder(cluster)
                OSHVResult.addAll(relationsBuilder.build(softwareInformationList))

            if cluster.osh != None:
                discoverConfigFiles(Framework, cluster.osh, shell,
                        cmclconfig_path, cmclconfig_files_pattern, OSHVResult)
            else:
                errobj = errorobject.createError(
                    errorcodes.SERVICE_GUARD_CLUSTER_NOT_FOUND,
                    None, 'Service Guard Cluster not found in discovery')
                logger.reportWarningObject(errobj)
        except:
            msg = sys.exc_info()[1]
            strmsg = '%s' % msg
            if (strmsg.lower().find('timeout') > -1):
                errobj = errorobject.createError(
                    errorcodes.CONNECTION_TIMEOUT_NO_PROTOCOL, None,
                    'Connection timed out')
                logger.reportErrorObject(errobj)
                logger.debugException('Connection timed out')
            else:
                errobj = errormessages.resolveError(strmsg, 'shell')
                logger.reportErrorObject(errobj)
                logger.errorException(strmsg)

    finally:
        if client != None:
            client.close()
    return OSHVResult

