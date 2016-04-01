#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Boolean, Exception
from java.util import Hashtable
import Dis_TCP
import NTCMD_HR_REG_Service_Lib
import TTY_HR_CPU_Lib
import TTY_HR_Disk_Lib
import TTY_HR_Memory_Lib
import TTY_HR_Share_Lib
import TTY_HR_Software_Lib
import TTY_HR_User_Lib
import applications
import errorcodes
import errormessages
import errorobject
import logger
import modeling
import netutils
import process
import process_discoverer
import process_to_process
import shellutils
import flow
from flow import discover_or_warn
from fc_hba_discoverer import discover_fc_hba_oshs_by_shell
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager


def getHRRoutine(platformName, TTY_HR):
    if platformName == 'Win':
        return TTY_HR.disWinOS
    elif platformName == 'Linux':
        return TTY_HR.disLinux
    elif platformName == 'FreeBSD':
        return TTY_HR.disFreeBSD
    elif platformName == 'SunOS':
        return TTY_HR.disSunOS
    elif platformName == 'HP-UX':
        return TTY_HR.disHPUX
    elif platformName == 'AIX':
        return TTY_HR.disAIX
    elif platformName == 'VMkernel':
        return TTY_HR.disVMKernel

def logWarn(framework, errorCode, params, errorMessage):
    if not (modeling.CmdbClassModel().version() >= 9.0):
        errorMessage = errormessages.makeErrorMessage(params[1].upper(), params[0], errormessages.ERROR_DISCOVERY_BY_PROTOCOL)
    logger.debugException(errorMessage)
    errobj = errorobject.createError(errorCode, params, errorMessage)
    logger.reportWarningObject(errobj)


def build_config(framework):
    config = (flow.DiscoveryConfigBuilder(framework)
          .bool_params(discoverCPUs=True)
          .bool_params(discoverDisks=True)
          .bool_params(discoverMemory=True)
          .bool_params(discoverInstalledSoftware=False)
          .bool_params(discoverUsers=True)
          .bool_params(discoverServices=False)
          .bool_params(discoverShares=True)
          .bool_params(discoverProcesses=False)
          .bool_params(discoverFcHBAs=False)
          ).build()
    return config


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    language = Framework.getDestinationAttribute('language')
    protocol = Framework.getDestinationAttribute('Protocol')
    langBund = None

    hostId = Framework.getDestinationAttribute('hostId')
    client = None
    uname = None
    shell = None
    try:
        originClient = Framework.createClient()
        client = originClient
        shell = shellutils.ShellUtils(client)
        if shell.isWinOs():
            uname = 'Win'
            client = shell
            if (language != None) and (language != 'NA'):
                langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY',language)
            else:
                langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY')

            try:
                wmicPath = Framework.getParameter('wmicPath')
                if wmicPath:
                    client.execCmd('set PATH=%PATH%;'+wmicPath)
            except:
                logger.debug('Failed to add default wmic location to the PATH variable.')
        else:
            if shell.getClientType() == 'ssh':
                uname = netutils.getOSName(client, 'uname -a')
            else:
                uname = netutils.getOSName(client, 'uname')

            langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY', 'eng')
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    else:
        # connection established

        config = build_config(Framework)
        discoverCPUs = Boolean.parseBoolean(Framework.getParameter('discoverCPUs'))
        discoverDisks = Boolean.parseBoolean(Framework.getParameter('discoverDisks'))
        discoverMemory = Boolean.parseBoolean(Framework.getParameter('discoverMemory'))
        discoverSoftware = Boolean.parseBoolean(Framework.getParameter('discoverInstalledSoftware'))
        discoverUsers = Boolean.parseBoolean(Framework.getParameter('discoverUsers'))
        discoverServices = Boolean.parseBoolean(Framework.getParameter('discoverServices'))
        discoverShares = Boolean.parseBoolean(Framework.getParameter('discoverShares'))
        discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
        discoverP2P = Boolean.parseBoolean(Framework.getParameter('discoverP2P'))
        workInTopDown = Boolean.parseBoolean(Framework.getParameter('workInTopDown'))
        #unit test do not have this attribute in destination data, add this for unit test
        if workInTopDown is None:
            workInTopDown = True
        #no services discovery in non-windows machines
        if not shell.isWinOs():
            discoverServices = 0

        if not uname:
            errormessages.resolveAndReport('Unrecognized OS', protocol, Framework)
        else:
            try:
                hostOsh = modeling.createOshByCmdbIdString('host', hostId)

                if discoverShares and shell.isWinOs():
                    try:
                        TTY_HR_Share_Lib.discoverSharedResourcesByWmic(client, hostOsh, OSHVResult)
                    except:
                        errorMessage = 'Failed to discover shared resources by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['share', protocol], errorMessage)


                if discoverCPUs and not uname == 'MacOs':
                    try:
                        host_is_virtualt_str = Framework.getDestinationAttribute('is_virtual')
                        host_is_virtual = False
                        if host_is_virtualt_str and host_is_virtualt_str != 'NA' and host_is_virtualt_str.lower() in ['1', 'true']:
                            host_is_virtual = True
                        hrRoutine = getHRRoutine(uname, TTY_HR_CPU_Lib)
                        OSHVResult.addAll(hrRoutine(hostId, shell, Framework, langBund, host_is_virtual))
                    except:
                        errorMessage = 'Failed to discover cpus by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['cpus', protocol], errorMessage)


                if discoverDisks and not uname == 'MacOs':
                    try:
                        hrRoutine = getHRRoutine(uname, TTY_HR_Disk_Lib)
                        OSHVResult.addAll(hrRoutine(hostOsh, shell))
                    except:
                        errorMessage = 'Failed to discover disks by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['disks', protocol], errorMessage)


                if discoverMemory and not uname == 'MacOs':
                    try:
                        hrRoutine = getHRRoutine(uname, TTY_HR_Memory_Lib)
                        OSHVResult.addAll(hrRoutine(hostId, shell, Framework, langBund))
                    except:
                        errorMessage = 'Failed to discover memory by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['memory', protocol], errorMessage)

                platformTrait = None
                processes = []
                packageToExecutablePath = {}

                # get platform details
                try:
                    platformTrait = process_discoverer.getPlatformTrait(shell)
                    if platformTrait is None:
                        raise ValueError()
                except:
                    logger.warnException("Failed to determine platform")

                # discover processes
                if platformTrait and not uname == 'VMkernel':
                    try:
                        discoverer = process_discoverer.getDiscovererByShell(shell, platformTrait)
                        processes = discoverer.discoverAllProcesses()
                        if not processes:
                            raise ValueError()
                    except:
                        errorMessage = 'Failed to discover processes by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['processes', protocol], errorMessage)

                if processes:

                    # save processes to DB
                    process_discoverer.saveProcessesToProbeDb(processes, hostId, Framework)

                    # discover packages info
                    try:
                        packagesDiscoverer = process_discoverer.getPackagesDiscovererByShell(shell, platformTrait)
                        packageToExecutablePath = packagesDiscoverer.getPackagesByProcesses(processes)
                    except:
                        logger.warn("Failed to get package names by processes path")

                    # report processes
                    if discoverProcesses:
                        processReporter = process.Reporter()
                        for processObject in processes:
                            processesVector = processReporter.reportProcess(hostOsh, processObject)
                            OSHVResult.addAll(processesVector)

                if discoverUsers:
                    try:
                        if shell.isWinOs():
                            OSHVResult.addAll(TTY_HR_User_Lib.disWinOs(hostOsh, shell))
                        else:
                            OSHVResult.addAll(TTY_HR_User_Lib.disGenericUNIX(hostId, shell))
                    except:
                        errorMessage = 'Failed to discover users by shell'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['users', protocol], errorMessage)


                cmdLineToInstalledSoftware = {}
                softNameToInstSoftOSH = {}
                if discoverSoftware:
                    try:
                        softwareOSHs = None
                        if uname == 'Linux':
                            softwareOSHs = TTY_HR_Software_Lib.disLinux(hostId, shell, Framework, langBund, packageToExecutablePath, cmdLineToInstalledSoftware)
                        elif uname == 'SunOS':
                            softwareOSHs = TTY_HR_Software_Lib.disSunOS(hostId, shell, Framework, langBund, packageToExecutablePath, cmdLineToInstalledSoftware)
                        elif uname == 'Win':
                            softwareOSHs = TTY_HR_Software_Lib.disWinOS(hostId, shell, Framework, langBund, softNameToInstSoftOSH)
                        else:
                            hrRoutine = getHRRoutine(uname, TTY_HR_Software_Lib)
                            softwareOSHs = hrRoutine(hostId, shell, Framework, langBund)
                        if softwareOSHs != None:
                            OSHVResult.addAll(softwareOSHs)
                    except:
                        errorMessage = 'Failed to discover installed software'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE, ['installed software', protocol], errorMessage)

                servicesByCmd = Hashtable()
                if shell.isWinOs() and discoverServices:
                    try:
                        srvcOSHs = NTCMD_HR_REG_Service_Lib.doService(shell, hostOsh, servicesByCmd, langBund, Framework)
                        OSHVResult.addAll(srvcOSHs)
                    except:
                        errorMessage = 'Failed to discover services'
                        logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE, ['services', protocol], errorMessage)

                if config.discoverFcHBAs:
                    oshs, warning = discover_or_warn('fibre channel HBAs',
                                                      discover_fc_hba_oshs_by_shell, shell,
                                                      hostOsh, protocol,
                                                      protocol_name=protocol)
                    if warning:
                        logger.reportWarningObject(warning)
                    else:
                        OSHVResult.addAll(oshs)

                connectivityEndPoints = []

                #No tcp and p2p discovery for vmkernel
                if not uname == 'VMkernel':
                    try:
                        tcpDiscoverer = Dis_TCP.getDiscovererByShell(originClient, Framework, shell)
                        if tcpDiscoverer is not None:
                            tcpDiscoverer.discoverTCP()
                            connectivityEndPoints = tcpDiscoverer.getProcessEndPoints()
                    except:
                        errorMessage = 'Failed to run tcp discovery by shell'
                        logWarn(Framework, errorcodes.FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE, ['tcp', protocol], errorMessage)

                    if workInTopDown:
                        linkOshv = ObjectStateHolderVector()
                        processReporter = process.Reporter()
                        for connectivityEndPoint in connectivityEndPoints:
                            processid = connectivityEndPoint.getKey()
                            endpoints = connectivityEndPoint.getEndpoints()
                            for processObject in processes:
                                if 4 < processid == processObject.getPid() and processObject.getName() != 'svchost.exe':
                                    processOSH = processReporter.reportProcessOsh(hostOsh, processObject)
                                    for endpoint in endpoints:
                                        builder = netutils.ServiceEndpointBuilder()
                                        reporter = netutils.EndpointReporter(builder)
                                        ipServerOSH = reporter.reportEndpoint(endpoint, hostOsh)
                                        linkOsh = modeling.createLinkOSH('usage', processOSH, ipServerOSH)
                                        linkOshv.add(linkOsh)
                                    break
                        OSHVResult.addAll(linkOshv)

                    appSign = applications.createApplicationSignature(Framework, originClient, shell)
                    if processes:
                        appSign.setProcessesManager(applications.ProcessesManager(processes, connectivityEndPoints))

                    servicesInfo = applications.ServicesInfo(servicesByCmd)
                    appSign.setServicesInfo(servicesInfo)

                    softwareInfo = applications.InstalledSoftwareInfo(cmdLineToInstalledSoftware, softNameToInstSoftOSH)
                    appSign.setInstalledSoftwareInfo(softwareInfo)

                    appSign.getApplicationsTopology(hostId)
                    if discoverP2P:
                        try:
                            p2p = process_to_process.ProcessToProcess(Framework)
                            p2p.getProcessesToProcess()
                        except:
                            errorMessage = 'Failed to run p2p discovery'
                            logWarn(Framework, errorcodes.FAILED_RUNNING_DISCOVERY, ['p2p', protocol], errorMessage)

                    if appSign.crgMap:
                        vector = ObjectStateHolderVector()
                        resultVectors = ScriptsExecutionManager.getFramework().getObjectsForAddOrUpdate()
                        vector.addAll(resultVectors)
                        for osh in vector:
                            oshClass = osh.getObjectClass()
                            #weak node
                            if oshClass == 'node' and osh.getAttributeValue('host_iscomplete') == 0 and osh.getAttributeValue('host_key'):
                                ip = osh.getAttributeValue('host_key').split(' ')[0]
                                if ip in appSign.crgMap.keys():
                                    logger.debug("replace weak node:", osh.getAttribute("host_key"))
                                    resultVectors.remove(osh)
                                    resultVectors.add(appSign.crgMap[ip])
                            #root container
                            elif osh.getAttribute('root_container'):
                                obj = osh.getAttribute("root_container").getObjectValue()
                                if obj.getObjectClass() == 'node' and obj.getAttributeValue('host_iscomplete') == 0 and obj.getAttributeValue('host_key'):
                                    logger.debug("replace root_container:", osh)
                                    ip = obj.getAttributeValue('host_key').split(' ')[0]
                                    if ip in appSign.crgMap.keys():
                                        logger.debug("replace root_container:", obj.getAttribute("host_key"))
                                        osh.setContainer(appSign.crgMap[ip])

            except Exception, ex:
                exInfo = ex.getMessage()
                errormessages.resolveAndReport(exInfo, protocol, Framework)
            except:
                exInfo = logger.prepareJythonStackTrace('')
                errormessages.resolveAndReport(exInfo, protocol, Framework)

    try:
        if shell != None:
            shell.closeClient()
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    return OSHVResult
