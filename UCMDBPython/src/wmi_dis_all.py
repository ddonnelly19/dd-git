#coding=utf-8
import logger
import errorcodes
import errorobject
import modeling

import wmi_dis_user_lib
import wmi_dis_service_lib
import wmi_dis_share_lib
import wmi_dis_software_lib
import wmi_dis_memory_lib
import wmi_dis_cpu_lib

import process
import process_discoverer
import applications

from java.lang import Boolean
from java.util import Hashtable
from java.util import Properties

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
import NTCMD_HR_Dis_Disk_Lib

from fptools import safeFunc as Sfn

from functools import partial
from flow import discover_or_warn


def createWmiClient(Framework, namespace=None):
    try:
        if namespace:
            props = Properties()
            props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, namespace)
            return Framework.createClient(props)
        else:
            return Framework.createClient()
    except:
        errobj = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL, ["WMI"], 'Failed to connect')
        logger.reportErrorObject(errobj)
        logger.debugException('Failed to to connect')


def __create_client_fn(framework, namespace):
    props = Properties()
    props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, namespace)
    return Sfn(framework.createClient)(props)


def discover_fc_hbas(framework, host_osh, protocol, vector):
    discoverFcHBAs = Boolean.parseBoolean(framework.getParameter('discoverFcHBAs'))
    if discoverFcHBAs:
        import wmi
        from fc_hba_discoverer import discover_fc_hba_oshs_by_shell

        client = None
        try:
            client = wmi.ClientWrapper(partial(__create_client_fn, framework))
            shell = wmi.ShellWrapper(client)
            oshs = discover_fc_hba_oshs_by_shell(shell, host_osh, protocol)
            vector.addAll(oshs)
        finally:
            client and Sfn(client.close)()


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    client = None
    try:
        client = createWmiClient(Framework)

        if client:
            protocol = Framework.getDestinationAttribute('Protocol')
            hostId = Framework.getDestinationAttribute('hostId')
            hostOsh = modeling.createOshByCmdbIdString('nt', hostId)

            _, warning = discover_or_warn('fibre channel HBAs',
                                discover_fc_hbas, Framework, hostOsh,
                                protocol, OSHVResult, protocol_name=protocol)
            if warning:
                logger.reportWarningObject(warning)

            discoverUsers = Boolean.parseBoolean(Framework.getParameter('discoverUsers'))
            if discoverUsers:
                try:
                    wmi_dis_user_lib.executeWmiQuery(client, Framework, OSHVResult, hostOsh)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['users', 'wmi'], 'Failed to discover users by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover users by wmi')

            discoverShares = Boolean.parseBoolean(Framework.getParameter('discoverShares'))
            if discoverShares:
                try:
                    wmi_dis_share_lib.executeWmiQuery(client, OSHVResult, hostOsh)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['shares', 'wmi'], 'Failed to discover shares by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover shares by wmi')

            discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
            processes = []

            try:
                processDiscoverer = process_discoverer.getDiscovererByWmi(client)
                processes = processDiscoverer.discoverAllProcesses()
                if not processes:
                    raise ValueError()
            except:
                errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['processes', 'wmi'], 'Failed to discover processes by wmi')
                logger.reportErrorObject(errobj)
                logger.errorException('Failed to discover processes by wmi')

            if processes:
                # save processes to DB
                process_discoverer.saveProcessesToProbeDb(processes, hostId, Framework)

                # report processes
                if discoverProcesses:
                    processReporter = process.Reporter()
                    for processObject in processes:
                        processesVector = processReporter.reportProcess(hostOsh, processObject)
                        OSHVResult.addAll(processesVector)

            discoverMemory = Boolean.parseBoolean(Framework.getParameter('discoverMemory'))
            if discoverMemory:
                try:
                    wmi_dis_memory_lib.executeWmiQuery(client, OSHVResult, hostOsh)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['memory', 'wmi'], 'Failed to discover memory by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover memory by wmi')

            discoverDisks = Boolean.parseBoolean(Framework.getParameter('discoverDisks'))
            if discoverDisks:
                try:
                    containerOsh = hostOsh or modeling.createHostOSH(client.getIpAddress())
                    NTCMD_HR_Dis_Disk_Lib.discoverDiskByWmic(client, OSHVResult, containerOsh)

                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['disks', 'wmi'], 'Failed to discover disks by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover disks by wmi')

            discoverCPUs = Boolean.parseBoolean(Framework.getParameter('discoverCPUs'))
            if discoverCPUs:
                try:
                    wmi_dis_cpu_lib.executeWmiQuery(client, OSHVResult, hostOsh)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['cpus', 'wmi'], 'Failed to discover cpus by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover cpus by wmi')

            discoverServices = Boolean.parseBoolean(Framework.getParameter('discoverServices'))
            servicesByCmd = Hashtable()
            if discoverServices:
                try:
                    servOSHV = wmi_dis_service_lib.executeWmiQuery(client, OSHVResult, servicesByCmd, hostOsh)
                    OSHVResult.addAll(servOSHV)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['services', 'wmi'], 'Failed to discover services by wmi')
                    logger.reportErrorObject(errobj)
                    logger.errorException('Failed to discover services by wmi')

            #NOTE: software discovery had to be the last in discovery chain
            discoverSoftware = Boolean.parseBoolean(Framework.getParameter('discoverInstalledSoftware'))
            softNameToInstSoftOSH = {}
            if discoverSoftware:
                (softNameToInstSoftOSH, client) = __discoverInstalledSoftware(Framework, OSHVResult, client)

            if not client:
                logger.warn("Application Signature will not be run since the client is not initialized")

            if client:

                appSign = applications.createApplicationSignature(Framework, client)
                if processes:
                    appSign.setProcessesManager(applications.ProcessesManager(processes, []))
                servicesInfo = applications.ServicesInfo(servicesByCmd)
                appSign.setServicesInfo(servicesInfo)

                softwareInfo = applications.InstalledSoftwareInfo(None, softNameToInstSoftOSH)
                appSign.setInstalledSoftwareInfo(softwareInfo)

                appSign.getApplicationsTopology(hostId)

    finally:
        if client != None:
            client.close()
    return OSHVResult


def __discoverInstalledSoftware(Framework, OSHVResult, client):
    discoverSoftwareOld = Boolean.parseBoolean(Framework.getParameter('discoverInstalledSoftwareByOldMechanism'))

    softNameToInstSoftOSH = {}
    try:
        if discoverSoftwareOld:
            #we close client here since in the software discovery we had to open another client
            #since we changing namespace and reference registry instead of wmi
            logger.debug('The software is discovered using old mechanism. This mechanism is very non-efficient and thus discovery might take time.')
            client.close()
            client = None

            wmi_dis_software_lib.mainFunction(Framework, OSHVResult, softNameToInstSoftOSH)

            #reopen general WMI client since it will be used in Plug-ins
            logger.debug("Reopening WMI client")
            client = createWmiClient(Framework)
        else:
            wmi_dis_software_lib.mainFunctionWithWbem(Framework, client, OSHVResult, softNameToInstSoftOSH)
    except:
        errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['software', 'wmi'], 'Failed to discover software by wmi')
        logger.reportErrorObject(errobj)
        logger.errorException('Failed to discover software by wmi')
    return (softNameToInstSoftOSH, client)
