# coding=utf-8
import ip_addr
import logger
import modeling
import netutils
import shellutils

from java.util import HashMap
from java.util.regex import Pattern
from java.lang import String

from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.accuratedependencies.processing import DependenciesDiscoveryConsts

PROVIDER_IP = 'PROVIDER_IP'
PROVIDER_PORT = 'PROVIDER_PORT'

PORT_GROUP_FROM_PATTERN = 1
PORT_PATTERN = Pattern.compile('\s*(\d+)\s*')

def StepMain(Framework):
    consumers = Framework.getProperty(DependenciesDiscoveryConsts.NEXT_HOP_PROVIDERS_RESULT_PROPERTY)
    OSHVResult = ObjectStateHolderVector()
    if (consumers is not None) and (consumers.size() > 0):
        ipPortconcepts = HashMap()

        localShell = None
        try:
            dnsServers = Framework.getParameter('dnsServers') or None

            if dnsServers:
                dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None

            localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))

            #going through extracted consumers
            for i in range(0, consumers.size()):
                consumer = consumers.get(i)
                depedencies = consumer.getDependencies()
                #going through dependencies of consumer
                for depedency in depedencies:
                    variables = depedency.getExportVariables()
                    #going through extracted variables of dependency
                    for variable in variables:
                        variableName = variable.getName()
                        values = variable.getValues()
                        conceptDefinition = variableName.split('.')
                        if (len(conceptDefinition) == 2) and len(conceptDefinition[0]) and ((conceptDefinition[1].upper() == PROVIDER_IP) or (conceptDefinition[1].upper() == PROVIDER_PORT)):
                            processIpPortConcept(ipPortconcepts, conceptDefinition[0].upper(), conceptDefinition[1].upper(), values)
                        elif variableName.upper() == PROVIDER_IP:
                            processIps(Framework, OSHVResult, values, localShell, dnsServers)

            resolveIpFromDnsPortipPortconcepts(Framework, OSHVResult, ipPortconcepts, localShell, dnsServers)
            Framework.sendObjects(OSHVResult)
            Framework.flushObjects()
        except:
            Framework.reportError(logger.prepareJythonStackTrace(''))
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)

        if localShell is not None:
            try:
                localShell.close()
                localShell = None
            except:
                pass
    Framework.getState().setProperty(DependenciesDiscoveryConsts.NEXT_HOP_PROVIDERS_RESULT_PROPERTY, not OSHVResult.isEmpty())
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

def processIps(Framework, OSHVResult, ipOrDnsOrAliases, localShell, dnsServers = None):
    logger.debug('Resolving ips for ', ipOrDnsOrAliases)
    for ipOrDnsOrAlias in ipOrDnsOrAliases:
        logger.debug('Resolving to IP [', ipOrDnsOrAlias, ']')
        resolvedIp = resolveIpFromDns(Framework, ipOrDnsOrAlias, localShell, dnsServers)
        if resolvedIp is not None:
            logger.debug('Resolved to IP [', ipOrDnsOrAlias, ']->[', resolvedIp, ']')
            try:
                ipOSH = modeling.createIpOSH(resolvedIp)
                OSHVResult.add(ipOSH)
            except:
                Framework.reportWarning(logger.prepareJythonStackTrace(''))
                logger.debug('Failed to process ip:[', resolvedIp, ']')
        else:
            logger.debug('Failed to resolve to IP [', ipOrDnsOrAlias, ']')

def processIpPortConcept(ipPortconcepts, conceptName, conceptField, values):
    if (values is not None) and (len(values) > 0):
        logger.debug('Adding for [', conceptName, '].[', conceptField, '] values', values)
        conceptInstances = ipPortconcepts.get(conceptName)
        if conceptInstances is None:
            conceptInstances = HashMap()
            ipPortconcepts.put(conceptName, conceptInstances)
        conceptInstances.put(conceptField, values)
    else:
        logger.debug('No values for [', conceptName, '].[', conceptField, ']')

def resolveIpFromDnsPortipPortconcepts(Framework, OSHVResult, ipPortconcepts, localShell, dnsServers = None):
    logger.debug('Resolving concepts')
    for ipPortConceptEntry in ipPortconcepts.entrySet():
        conceptName = ipPortConceptEntry.getKey()
        conceptFields = ipPortConceptEntry.getValue()
        logger.debug('processing [', conceptName, ']')
        PROVIDER_IPs = None
        PROVIDER_PORTs = None
        for conceptFieldEntry in conceptFields.entrySet():
            fieldName = conceptFieldEntry.getKey().upper()
            if fieldName == PROVIDER_IP:
                PROVIDER_IPs = conceptFieldEntry.getValue()
            elif fieldName == PROVIDER_PORT:
                PROVIDER_PORTs = conceptFieldEntry.getValue()

        if PROVIDER_IPs is not None:
            logger.debug('for concept [', conceptName, '].[', PROVIDER_IP, '] found [', str(len(PROVIDER_IPs)), '] values')
            if PROVIDER_PORTs is None:
                processIps(Framework, OSHVResult, PROVIDER_IPs, localShell)
            elif len(PROVIDER_IPs) != len(PROVIDER_PORTs):
                errorMessage = 'There is a mismatch between the number of IP addresses and the number of ports that were found. The concept [' + conceptName + '].[' + PROVIDER_IP + '] found [' + str(len(PROVIDER_IPs)) + '] values while for [' + conceptName + '].[' + PROVIDER_PORT + '] found [' + str(len(PROVIDER_PORTs)) + '] values'
                Framework.reportWarning(errorMessage)
                logger.warn(errorMessage)
                processIps(Framework, OSHVResult, PROVIDER_IPs, localShell)
            else:
                for index in range(len(PROVIDER_IPs)):
                    resolvedIp = resolveIpFromDns(Framework, PROVIDER_IPs[index], localShell, dnsServers)
                    if resolvedIp is not None:
                        processIpPort(Framework, OSHVResult, resolvedIp, PROVIDER_PORTs[index], localShell, dnsServers)
        else:
            logger.error('No ' + PROVIDER_IP + ' field returned for concept [', conceptName, ']')

def processIpPort(Framework, OSHVResult, ipOrDnsOrAlias, port, localShell, dnsServers = None):
    logger.debug('Resolving ip port for [', ipOrDnsOrAlias, '] and [', port, ']')
    resolvedIp = resolveIpFromDns(Framework, ipOrDnsOrAlias, localShell, dnsServers)
    if resolvedIp is not None:
        try:
            ipOSH = modeling.createIpOSH(resolvedIp)
            OSHVResult.add(ipOSH)
            matcher = PORT_PATTERN.matcher(String(port))
            if matcher.find():
                purePort = matcher.group(PORT_GROUP_FROM_PATTERN)
                hostOSH = modeling.createHostOSH(resolvedIp)
                portOsh = modeling.createServiceAddressOsh(hostOSH, resolvedIp, purePort, modeling.SERVICEADDRESS_TYPE_TCP)
                portOsh.setAttribute("name", String(port))
                OSHVResult.add(portOsh)
            else:
                errorMessage = 'An invalid (non-numeric) port value was found in the configuration file [' + port + '] and will be skipped'
                Framework.reportWarning(errorMessage)
                logger.warn(errorMessage)
        except:
            Framework.reportWarning(logger.prepareJythonStackTrace(''))
            logger.debug('Failed to process ip:[', resolvedIp, '] with port [', port, ']')

def resolveIpFromDns(Framework, ipOrDnsOrAlias, localShell, dnsServers = None):
    normalizedIp = str(ipOrDnsOrAlias).strip()

    if not normalizedIp or normalizedIp == "localhost" or (ip_addr.isValidIpAddress(normalizedIp) and (ip_addr.IPAddress(normalizedIp).is_loopback or ip_addr.IPAddress(normalizedIp).is_multicast)):
        logger.debug('Skipped ip [', normalizedIp, '] for next hop, because it is empty or loopback or not a valid ip address')
        return None

    if dnsServers is not None:
        logger.debug('Trying to resolve ip using provided dnsServers names')
        dnsResolver = netutils.DNSResolver(localShell)
        for dnsServer in dnsServers:
            logger.debug('Trying to resolve ip using DNS Server [', dnsServer, ']')
            try:
                resolvedIp = dnsResolver.resolveHostIp(normalizedIp, dnsServer)
                if resolvedIp is not None:
                    logger.debug('Resolved ip [', resolvedIp, '] from [', normalizedIp, '] using DNS Server [', dnsServer, ']')
                    return resolvedIp
            except:
                Framework.reportWarning(logger.prepareJythonStackTrace(''))
                logger.debug('Failed to resolve [', normalizedIp, ']')

    try:
        logger.debug('Trying to resolve ip using local DNS server')
        resolvedIp = netutils.resolveIP(localShell, normalizedIp)
        if resolvedIp is not None:
            logger.debug('Resolved ip [', resolvedIp, '] from [', normalizedIp, '] using configured local DNS Server or hosts file')
            return resolvedIp
        else:
            errorMessage = 'Failed to resolve ip from [' + normalizedIp + '] using configured local DNS Server or hosts file'
            Framework.reportWarning(errorMessage)
            logger.warn(errorMessage)
    except:
        Framework.reportWarning(logger.prepareJythonStackTrace(''))
        logger.warn(errorMessage)
    return resolvedIp
