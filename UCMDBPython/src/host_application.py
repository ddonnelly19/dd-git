import logger
import modeling
import netutils
import process_discoverer
import TTY_HR_Main
import errorcodes
import errormessages
import errorobject
import asm_Disc_TCP
import process
import asm_applications
import Framework_delegator
import applications
import scp

from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Hashtable


def doApplication(Framework, ip, OSHVResult, client, shell, hostOsh):
    clientType = client.getClientType()
    language = Framework.getDestinationAttribute('language')
    portToDiscover = Framework.getDestinationAttribute("PORT")
    scp_id = Framework.getDestinationAttribute("SCP_ID")
    portInNetstat = False
    processMapOnPort = {}
    signatureFound = False

    filterRunningSoftwareByPort = Framework.getParameter('filterRunningSoftwareByPort')
    logger.debug("Start to do host application")
    logger.debug("ip:", ip)
    #hostOsh = modeling.createHostOSH(ip)

    platformTrait = None
    processes = []
    packageToExecutablePath = {}
    CLUSTERLIST = ["Microsoft Cluster SW"]

    if shell.isWinOs():
        uname = 'Win'
        #client = shell
        if (language != None) and (language != 'NA'):
            langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY', language)
        else:
            langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY')

        try:
            wmicPath = Framework.getParameter('wmicPath')
            if wmicPath:
                shell.execCmd('set PATH=%PATH%;' + wmicPath)
        except:
            logger.debug('Failed to add default wmic location to the PATH variable.')
    else:
        if shell.getClientType() == 'ssh':
            uname = netutils.getOSName(client, 'uname -a')
        else:
            uname = netutils.getOSName(client, 'uname')

        langBund = Framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY', 'eng')

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
            TTY_HR_Main.logWarn(Framework, errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE,
                                ['processes', clientType], errorMessage)

    if processes:

        # save processes to DB
        #process_discoverer.saveProcessesToProbeDb(processes, hostId, Framework)

        # discover packages info
        try:
            packagesDiscoverer = process_discoverer.getPackagesDiscovererByShell(shell, platformTrait)
            packageToExecutablePath = packagesDiscoverer.getPackagesByProcesses(processes)
        except:
            logger.warn("Failed to get package names by processes path")

            # report processes
            #if discoverProcesses:

    connectivityEndPoints = []
    connections = []
    runningApplications = []
    errorsList = []

    #No tcp and p2p discovery for vmkernel
    if not uname == 'VMkernel':
        try:
            tcpDiscoverer = asm_Disc_TCP.getDiscovererByShell(client, Framework, shell)
            if tcpDiscoverer is not None:
                tcpDiscoverer.pdu = asm_Disc_TCP.TcpStateHolder(None)
                tcpDiscoverer.discoverTCP()
                connections = tcpDiscoverer.pdu.tcp_connections
                connectivityEndPoints = tcpDiscoverer.getProcessEndPoints()
        except:
            errorMessage = 'Failed to run tcp discovery by shell'
            TTY_HR_Main.logWarn(Framework, errorcodes.FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE, ['tcp', clientType],
                                errorMessage)

        #if workInTopDown:
        linkOshv = ObjectStateHolderVector()
        processReporter = process.Reporter()
        processBuilder = process.ProcessBuilder()
        for connectivityEndPoint in connectivityEndPoints:
            processid = connectivityEndPoint.getKey()
            endpoints = connectivityEndPoint.getEndpoints()
            #logger.debug('#processid=', processid)
            #logger.debug('#endpoints=', endpoints)
            for processObject in processes:
                #logger.debug('#processObject.getPid()=', processObject.getPid())
                #logger.debug('#processObject.getName()=', processObject.getName())
                if 4 < processid == processObject.getPid() and processObject.getName() != 'svchost.exe':
                    processOSH, _ = processReporter.report(hostOsh, processObject, processBuilder)
                    for endpoint in endpoints:
                        if str(portToDiscover) == str(endpoint.getPort()):
                            portInNetstat = True
                            processMapOnPort[processid] = processObject
                        builder = netutils.ServiceEndpointBuilder()
                        reporter = netutils.EndpointReporter(builder)
                        ipServerOSH = reporter.reportEndpoint(endpoint, hostOsh)
                        linkOsh = modeling.createLinkOSH('usage', processOSH, ipServerOSH)
                        linkOshv.add(linkOsh)
                    break

        if not portInNetstat:
            errorMessage = errormessages.makeErrorMessage(clientType, message=portToDiscover,
                                                          pattern=errormessages.ERROR_FINDING_PROCESS_BY_PORT)
            logger.debugException("port cannot be found:", portToDiscover)
            errobj = errorobject.createError(errorcodes.FAILED_FINDING_PROCESS_BY_PORT, [portToDiscover], errorMessage)
            errorsList.append(errobj)

        OSHVResult.addAll(linkOshv)

        framework_delegator = Framework_delegator.FrameworkDelegator()

        appSign = asm_applications.createASMApplicationSignature(Framework, framework_delegator, client, shell)
        if processes:
            appSign.setProcessesManager(applications.ProcessesManager(processes, connectivityEndPoints))
        servicesByCmd = Hashtable()
        servicesInfo = applications.ServicesInfo(servicesByCmd)
        appSign.setServicesInfo(servicesInfo)
        cmdLineToInstalledSoftware = {}
        softNameToInstSoftOSH = {}
        softwareInfo = applications.InstalledSoftwareInfo(cmdLineToInstalledSoftware, softNameToInstSoftOSH)
        appSign.setInstalledSoftwareInfo(softwareInfo)

        runningApplications = appSign.getApplicationsTopologyUsingHostOsh(hostOsh)
        logger.debug('runningApplications=%s' % runningApplications)
        logger.debug('adding netstat port results')
        for application in runningApplications:
            pids = [str(x.getPid()) for x in application.getProcesses() if x]
            logger.debug('pids for application:%s %s' % (application.getName(), pids))
            if pids in processMapOnPort.keys():
                signatureFound = True
            for connectivityEndPoint in connectivityEndPoints:
                processid = connectivityEndPoint.getKey()
                endpoints = connectivityEndPoint.getEndpoints()
                if str(processid) in pids:
                    for endpoint in endpoints:
                        logger.debug('adding port:', endpoint.getPort())
                        framework_delegator.addNetstatPortResult(application.getName(), endpoint.getPort())

        if (not signatureFound) and processMapOnPort.values():
            errorMessage = errormessages.makeErrorMessage(
                clientType, message="%s listening on port %s" % (processMapOnPort.values(), portToDiscover),
                pattern=errormessages.ERROR_FINDING_APPSIG_BY_PROCESS)
            logger.debugException("no listening port found for process %s and port %s" % (processMapOnPort.values(), portToDiscover))
            errobj = errorobject.createError(errorcodes.FAILED_FINDING_APPSIG_BY_PROCESS,
                                             [repr(processMapOnPort.values()), portToDiscover], errorMessage)
            errorsList.append(errobj)

        filteredRunningApplications = []
        if filterRunningSoftwareByPort and filterRunningSoftwareByPort == 'true':
            logger.debug('try to filter running applications using port:', portToDiscover)
            logger.debug('application list using port filter',
                         framework_delegator.getApplicationNamesByPort(portToDiscover))

            for runningApplication in runningApplications:
                if runningApplication.getName() in framework_delegator.getApplicationNamesByPort(portToDiscover):
                    logger.debug("adding application: ", runningApplication.getName())
                    filteredRunningApplications.append(runningApplication)
                elif runningApplication.getName() in CLUSTERLIST:
                    logger.debug("include cluster related ci: ", runningApplication.getName())
                    filteredRunningApplications.append(runningApplication)
                    OSHVResult.addAll(
                        framework_delegator.getResultVectorByApplicationName(runningApplication.getName()))
                else:
                    logger.debug("remove application: ", runningApplication.getName())

            logger.debug('filteredRunningApplications=%s' % filteredRunningApplications)

            if not filteredRunningApplications:
                logger.debug("running software for port was not found:", portToDiscover)

            for resultVector in framework_delegator.getResultVectorsByPort(portToDiscover):
                OSHVResult.addAll(resultVector)

            #create ownership between runningsoftware and scp
            logger.debug("create ownership between runningsoftware and scp")
            for runningApplication in filteredRunningApplications:
                logger.debug("APP:", runningApplication.getName())
                OSHVResult.addAll(scp.createOwnerShip(scp_id, runningApplication.getOsh()))

        else:
            logger.debug('filterRunningSoftwareByPort is %s, will report all running software discovered')
            for runningApplication in runningApplications:
                filteredRunningApplications.append(runningApplication)
                OSHVResult.addAll(framework_delegator.getResultVectorByApplicationName(runningApplication.getName()))
                OSHVResult.addAll(scp.createOwnerShip(scp_id, runningApplication.getOsh()))

        logger.debug("crgMap = ", appSign.crgMap)
        vector = ObjectStateHolderVector()
        vector.addAll(OSHVResult)
        if appSign.crgMap:
            for osh in vector:
                oshClass = osh.getObjectClass()
                #weak node
                if oshClass == 'node' and osh.getAttributeValue('host_iscomplete') == 0 and osh.getAttributeValue(
                        'host_key'):
                    ip = osh.getAttributeValue('host_key').split(' ')[0]
                    if ip in appSign.crgMap.keys():
                        logger.debug("replace weak node:", osh.getAttribute("host_key"))
                        OSHVResult.remove(osh)
                        OSHVResult.add(appSign.crgMap[ip])
                #root container
                elif osh.getAttribute('root_container'):
                    obj = osh.getAttribute("root_container").getObjectValue()
                    if obj.getObjectClass() == 'node' and obj.getAttributeValue(
                            'host_iscomplete') == 0 and obj.getAttributeValue('host_key'):
                        logger.debug("replace root_container:", osh)
                        ip = obj.getAttributeValue('host_key').split(' ')[0]
                        if ip in appSign.crgMap.keys():
                            logger.debug("replace root_container:", obj.getAttribute("host_key"))
                            osh.setContainer(appSign.crgMap[ip])


    return filteredRunningApplications, processes, connectivityEndPoints, connections, errorsList