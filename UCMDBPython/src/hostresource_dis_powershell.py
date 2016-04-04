#coding=utf-8
import modeling
import shellutils

import logger
import wmiutils
import errormessages
import errorcodes
import errorobject
import TTY_HR_CPU_Lib
import TTY_HR_Disk_Lib
import TTY_HR_Memory_Lib
import TTY_HR_Software_Lib
import NTCMD_HR_REG_Service_Lib
import HR_Dis_Driver_Lib
import process
import process_discoverer
import applications
import Dis_TCP
import process_to_process
import hostresource
import host_win_wmi
import hostresource_win_wmi
import shared_resources_util

from java.lang import Exception as JException
from java.lang import Boolean
from java.util import Hashtable

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import AuthenticationException


def _discoverSharedResources(powershell, hostOsh):
    '''PowerShell, osh -> vector
    @raise Exception: failed getting shared resources by WMI
    '''
    wmiProvider = wmiutils.PowerShellWmiProvider(powershell)
    discoverer = hostresource_win_wmi.FileSystemResourceDiscoverer(wmiProvider)
    vector = ObjectStateHolderVector()
    for resource in discoverer.getSharedResources():
        shared_resources_util.createSharedResourceOsh(resource, hostOsh, vector)
    return vector


def _discoverWindowsDeviceDriver(powershell, hostOsh):
    '''PowerShell, osh -> vector
    @raise Exception: failed getting windows driver by WMI
    '''
    vector = ObjectStateHolderVector()
    HR_Dis_Driver_Lib.discoverDriverByWmi(powershell, vector, hostOsh)
    return vector


def _discoverUsers(hostOsh, powershell):
    ''' ObjectStateHolder, PowerShell -> ObjectStateHolderVector
    @raise HostResourceDiscoveryException if discovery failed
    @deprecated: use hostresources_win_wmi instead
    '''
    vector = ObjectStateHolderVector()
    wmiProvider = wmiutils.PowerShellWmiProvider(powershell)
    try:
        hostDo = host_win_wmi.Discoverer(wmiProvider).discoverHostInfo()
        domainName = hostDo.hostName
    except Exception, e:
        logger.debug(e.message)
        raise hostresource.HostResourceDiscoveryException, "Failed to get host domain name. %s" % e.message
    else:
        userResources = hostresource_win_wmi.UserDiscoverer(wmiProvider).discoverByDomain(domainName)
        userResources.build(hostOsh)
        vector = userResources.report()
    return vector


def _logWarn(errorCode, params, errorMessage):
    'int, list(str), str -> None'
    if not (modeling.CmdbClassModel().version() >= 9.0):
        errorMessage = errormessages.makeErrorMessage(params[1].upper(), params[0], errormessages.ERROR_DISCOVERY_BY_PROTOCOL)
    logger.debugException(errorMessage)
    errobj = errorobject.createError(errorCode, params, errorMessage)
    logger.reportWarningObject(errobj)


def DiscoveryMain(Framework):
    vector = ObjectStateHolderVector()
    protocol = Framework.getDestinationAttribute('Protocol')
    client = None
    shell = None
    try:
        try:
            # connect to destination
            client = Framework.createClient()
            # wrap client with Shell
            shell = shellutils.ShellFactory().createShell(client)
        except AuthenticationException, ae:
            errormessages.resolveAndReport(ae.getMessage(), protocol, Framework)
        except:
            exInfo = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(exInfo, protocol, Framework)
        else:

            language = Framework.getDestinationAttribute('language')
            hostCmdbId = Framework.getDestinationAttribute('hostId')

            # configure internationalization support
            if language and language != 'NA':
                langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY', language)
            else:
                langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY')

            # discovery
            discoverCPUs = Boolean.parseBoolean(Framework.getParameter('discoverCPUs'))
            discoverDisks = Boolean.parseBoolean(Framework.getParameter('discoverDisks'))
            discoveriSCSIInfo = Boolean.parseBoolean(Framework.getParameter('discoveriSCSIInfo'))
            discoverDrivers = Boolean.parseBoolean(Framework.getParameter('discoverDrivers'))
            discoverMemory = Boolean.parseBoolean(Framework.getParameter('discoverMemory'))
            discoverSoftware = Boolean.parseBoolean(Framework.getParameter('discoverInstalledSoftware'))
            discoverUsers = Boolean.parseBoolean(Framework.getParameter('discoverUsers'))
            discoverServices = Boolean.parseBoolean(Framework.getParameter('discoverServices'))
            discoverShares = Boolean.parseBoolean(Framework.getParameter('discoverShares'))
            discoverP2P = Boolean.parseBoolean(Framework.getParameter('discoverP2P'))

            try:

                hostOsh = modeling.createOshByCmdbIdString('host', hostCmdbId)

                if discoverShares:
                    try:
                        vector.addAll(_discoverSharedResources(shell, hostOsh))
                    except:
                        errorMessage = 'Failed to discover shared resources'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['share', protocol], errorMessage)

                if discoverCPUs:
                    try:
                        vector.addAll(TTY_HR_CPU_Lib.disWinOS(hostCmdbId, shell, Framework, langBund))
                    except:
                        errorMessage = 'Failed to discover CPUs'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['cpus', protocol], errorMessage)

                if discoverDisks:
                    try:
                        vector.addAll(TTY_HR_Disk_Lib.disWinOS(hostOsh, shell))
                    except:
                        errorMessage = 'Failed to discover disks'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['disks', protocol], errorMessage)

                if discoverDrivers and shell.isWinOs():
                    try:
                        vector.addAll(_discoverWindowsDeviceDriver(shell, hostOsh))
                    except:
                        errorMessage = 'Failed to discover windows device driver by powershell'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['windows device driver', protocol], errorMessage)

                if discoveriSCSIInfo:
                    try:
                        vector.addAll(TTY_HR_Disk_Lib.disWinOSiSCSIInfo(hostOsh, shell))
                    except:
                        errorMessage = 'Failed to discover iSCSI info'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['iSCSI', protocol], errorMessage)

                if discoverMemory:
                    try:
                        vector.addAll(TTY_HR_Memory_Lib.disWinOS(hostCmdbId, shell, Framework, langBund))
                    except:
                        errorMessage = 'Failed to discover memory'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['memory', protocol], errorMessage)

                processes = []
                try:
                    processesDiscoverer = process_discoverer.DiscovererByShellOnWindows(shell)
                    processes = processesDiscoverer.discoverAllProcesses()
                    if not processes:
                        raise ValueError()
                except:
                    errorMessage = 'Failed to discover processes'
                    _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['processes', protocol], errorMessage)

                if processes:
                    # save processes to DB
                    process_discoverer.saveProcessesToProbeDb(processes, hostCmdbId, Framework)

                    # report processes
                    discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
                    if discoverProcesses:
                        processReporter = process.Reporter()
                        for processObject in processes:
                            processVector = processReporter.reportProcess(hostOsh, processObject)
                            vector.addAll(processVector)

                if discoverUsers:
                    try:
                        vector.addAll(_discoverUsers(hostOsh, shell))
                    except:
                        errorMessage = 'Failed to discover users'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['users', protocol], errorMessage)

                cmdLineToInstalledSoftware = {}
                softNameToInstSoftOSH = {}
                if discoverSoftware:
                    try:
                        softwareOSHs = TTY_HR_Software_Lib.disWinOS(hostCmdbId, shell, Framework, langBund, softNameToInstSoftOSH)
                        if softwareOSHs:
                            vector.addAll(softwareOSHs)
                    except:
                        errorMessage = 'Failed to discover installed software'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE, ['installed software', protocol], errorMessage)

                servicesByCmd = Hashtable()
                if discoverServices:
                    try:
                        srvcOSHs = NTCMD_HR_REG_Service_Lib.doService(shell, hostOsh, servicesByCmd, langBund, Framework)
                        vector.addAll(srvcOSHs)
                    except:
                        errorMessage = 'Failed to discover services'
                        _logWarn(errorcodes.FAILED_DISCOVERING_RESOURCE, ['services', protocol], errorMessage)

                connectivityEndPoints = []
                try:
                    tcpDiscoverer = Dis_TCP.getDiscovererByShell(client, Framework, shell)
                    if tcpDiscoverer is not None:
                        tcpDiscoverer.discoverTCP()
                        connectivityEndPoints = tcpDiscoverer.getProcessEndPoints()
                except:
                    errorMessage = 'Failed to run TCP discovery'
                    _logWarn(errorcodes.FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE, ['tcp', protocol], errorMessage)

                appSign = applications.createApplicationSignature(Framework, client, shell)

                if processes:
                    appSign.setProcessesManager(applications.ProcessesManager(processes, connectivityEndPoints))

                servicesInfo = applications.ServicesInfo(servicesByCmd)
                appSign.setServicesInfo(servicesInfo)

                softwareInfo = applications.InstalledSoftwareInfo(cmdLineToInstalledSoftware, softNameToInstSoftOSH)
                appSign.setInstalledSoftwareInfo(softwareInfo)

                appSign.getApplicationsTopology(hostCmdbId)

                if discoverP2P:
                    try:
                        p2p = process_to_process.ProcessToProcess(Framework)
                        p2p.getProcessesToProcess()
                    except:
                        errorMessage = 'Failed to run p2p discovery'
                        _logWarn(errorcodes.FAILED_RUNNING_DISCOVERY, ['p2p', protocol], errorMessage)

            except JException, ex:
                exInfo = ex.getMessage()
                errormessages.resolveAndReport(exInfo, protocol, Framework)
            except:
                exInfo = logger.prepareJythonStackTrace('')
                errormessages.resolveAndReport(exInfo, protocol, Framework)
    finally:
        shell and shell.closeClient()
    return vector
