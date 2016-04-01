#coding=utf-8
import string
import re

import logger
import modeling
import shellutils
import netutils
import errormessages
from oracle_shell_utils import OraConfigParser
from oracle_shell_utils import EnvConfigurator, UnixOracleEnvConfig, WindowsOracleEnvConfig, SrvctlBasedDiscoverer
from oracle_shell_utils import ORACLE_LISTENER_STATUS
from oracle_shell_utils import DNSResolver

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################
TNSNAMES_CONFIGURATION_FILE = 'tnsnames.ora'

class TNSNamesConfig:
    def __init__(self, shell, envConf):
        self.shell = shell
        self.envConf = envConf
        # Depending on service names and SIDs tnsnames.ora is looked up for RAC
        # native definitions (multiple nodes for a single connection/service identifier.)
        self.tnsNamesConfigContent = self.fetchTNSNamesConfig()
        self.racParams = self.parseTNSNames()

    def fetchTNSNamesConfig(self):
        ''' Get configuration for databases addresses for establishing connections to them
        @usedFile: tnsnames.ora
        @types: -> str or None
        '''
        configDir = self.envConf.getConfigPath()
        if configDir:
            try:
                configFileContent = self.shell.safecat(configDir + TNSNAMES_CONFIGURATION_FILE)
            except:
                configFileContent = None
            if configFileContent and self.shell.getLastCmdReturnCode() == 0:
                return configFileContent

    def resolveNamesToIPs(self, hostNode, parsedData):
        if parsedData:
            for internalName in parsedData.keys():
                nodeData = parsedData[internalName]
                values = nodeData.get(hostNode)
                if values:
                    listenedIPs = {}
                    for ipaddr in values:
                        stripedIpAddr = ipaddr.strip()
                        if netutils.isValidIp(stripedIpAddr):
                            listenedIPs[stripedIpAddr] = ''
                        else:
                            resolver = DNSResolver(self.shell, stripedIpAddr)
                            resolvedIp = resolver.getIPAddress()
                            if resolvedIp:
                                listenedIPs[resolvedIp.strip()] = ''
                            else:
                                aliasBasedIps = resolver.resolveNSLookupAliasBased()
                                if aliasBasedIps:
                                    for ip in aliasBasedIps:
                                        listenedIPs[ip.strip()] = ''
                    nodeData[hostNode] = listenedIPs.keys()
                parsedData[internalName] = nodeData
        return parsedData

    def getPossibleRacServiceNames(self, parsedData, serviceMarker, instanceMarker):
        if parsedData:
            possibleRACServiceNames = {}
            for internalName in parsedData.keys():
                subValues = parsedData[internalName]
                serviceNames = subValues.get(serviceMarker)
                instanceNames = subValues.get(instanceMarker)
                if serviceNames and not instanceNames:
                    for serviceName in serviceNames:
                        possibleRACServiceNames[serviceName] = 1
            return possibleRACServiceNames

    def getRACParams(self, parsedData, possibleRACServiceNames, hostMarker, serviceMarker, instanceMarker):
        if parsedData and possibleRACServiceNames:
            discoverRacParams = {}
            for internalName in parsedData.keys():
                subValues = parsedData[internalName]
                serviceNames = subValues.get(serviceMarker)
                instanceNames = subValues.get(instanceMarker)
                nodes = subValues.get(hostMarker)
                if serviceNames and instanceNames and nodes:
                    for serviceName in serviceNames:
                        if possibleRACServiceNames.get(serviceName.upper()):
                            results = discoverRacParams.get(serviceName.upper())
                            if results is None:
                                results = {}
                            for ip in nodes:
                                for instance in instanceNames:
                                    results[ip] = instance.upper()
                            discoverRacParams[serviceName.upper()] = results
            return discoverRacParams
        else:
            logger.error('No candidates for RAC found.')


    def parseTNSNames(self):
        discoveredRacParams = {}
        if self.tnsNamesConfigContent:
            hostNode = 'HOST'
            serviceMarker = 'SERVICE_NAME'
            instanceMarker = 'INSTANCE_NAME'
            filter = {hostNode : 'HOST\s*=\s*([\w\-\.]+)[\s\)]*', serviceMarker : 'SERVICE_NAME\s*=\s*([\w\-\.]+)[\s\)]', instanceMarker : 'INSTANCE_NAME\s*=\s*([\w\-\.]+)[\s\)]'}
            parser = OraConfigParser(self.tnsNamesConfigContent, filter)
            parsedData = parser.getResultsDict()
            parsedData = self.resolveNamesToIPs(hostNode, parsedData)
            possibleRACServiceNames = self.getPossibleRacServiceNames(parsedData, serviceMarker, instanceMarker)
            discoveredRacParams = self.getRACParams(parsedData, possibleRACServiceNames, hostNode, serviceMarker, instanceMarker)
        else:
            raise Exception, "Couldn't find tnsnames.ora configuration file."
        return discoveredRacParams

    def getRacParams(self):
        return self.racParams

class LookupElem:
    def __init__(self, primaryIP, hostName, ipAddr, macAddr = None):
        self.primaryIP = primaryIP
        self.hostName = hostName
        self.ipAddr = ipAddr
        self.macAddr = macAddr

    def getPrimaryIP(self):
        return self.primaryIP

    def getMacAddr(self):
        return self.macAddr

    def getHostName(self):
        return self.hostName

    def getIpAddr(self):
        return self.ipAddr

class LookupManager:
    def __init__(self, listenedIPs):
        self.listenedIPs = listenedIPs
        self.lookupIPDict = self.parseListenedIps()

    def parseListenedIps(self):
        lookupIPDict = {}
        if self.listenedIPs:
            for param in self.listenedIPs:
                if  param == "NA":
                    break
                paramList = param.split('@')
                if paramList:
                    hostName = None
                    hostPrimIP = None
                    part1 = paramList[0];
                    part2 = paramList[1];
                    values = re.match( r"(.*?):(.*)", part1)
                    if values:
                        hostName = values.group(1).strip()
                        hostPrimIP = values.group(2).strip()
                    for ipaddr in part2.split(';'):
                        lookupIPDict[ipaddr] = LookupElem(hostPrimIP, hostName, ipaddr)
                            #if not lookupIPDict.has_key(ipaddr):
                            #    lookupIPDict[ipaddr] = []
                            #lookupIPDict[ipaddr.strip()].append(LookupElem(hostPrimIP, hostName, ipaddr, mac))

        return lookupIPDict

    def lookupByIp(self, ipaddr):
        elem = self.lookupIPDict.get(ipaddr.strip())
        if elem:
            return elem.getHostName()

    def getElement(self, ipaddr):
        elem = self.lookupIPDict.get(ipaddr.strip())
        return elem

    def getPrimaryIp(self, ipaddr):
        elem = self.lookupIPDict.get(ipaddr.strip())
        if elem:
            return elem.getPrimaryIP()

#    def lookUpUsingMAC(self, ipaddr):
#
class ServiceChecker:
    def __init__(self, shell, envConf, serviceName = None, listenerName = None):
        '''
        @types: Shell, oracle_shell_utils.EnvConfigurator, str, str
        '''
        self.shell = shell
        self.serviceName = serviceName
        self.envConf = envConf
        self.listenerStatus = self.getListenerStatus(listenerName) or self.getListenerStatus()
        self.knownDbInstances = self.parseDbInstances()

    def getListenerStatus(self, listenerName = None):
        ''' Get output lines of command to extract status of specified listener
        @command: lsnrctl status <listener name>
        @types: str -> list(str)'''
        binDir = self.envConf.getOracleBinDir()
        if binDir:
            cmd = "%s%s %s" % (binDir, ORACLE_LISTENER_STATUS, listenerName or '')
            listenerStatus = self.shell.execCmd(cmd.strip())
            if listenerStatus and self.shell.getLastCmdReturnCode() == 0:
                return listenerStatus.split('\n')
        return []

    def isServiceRunning(self, servName = None):
        serviceName = self.serviceName
        if servName is not None:
            serviceName = servName

        if self.listenerStatus and serviceName:
            listenedServices = {}
            for line in self.listenerStatus:
                matcher = re.search( '.*Service\s*\"(.*?)\".*', line)
                if matcher:
                    listenedServices[matcher.group(1).upper().strip()] = 1
            return listenedServices.has_key(serviceName.strip())
        else:
            logger.error('Failed to check listener status')

    def getServiceInstancesNumber(self, servName = None):
        serviceName = self.serviceName
        if servName is not None:
            serviceName = servName

        if self.listenerStatus and serviceName:
            for line in self.listenerStatus:
                formatedServiceName = serviceName.replace('.','\\.')
                matchPattern = '.*Service\s+\"' + formatedServiceName + '\"\s+has\s+(\d+)\s+.*'
                matcher = re.search(matchPattern, line, re.IGNORECASE)
                if matcher:
                    return matcher.group(1)
        else:
            logger.error('Failed to get instances count.')
        return 0

    def parseDbInstances(self):
        knownServices = {}
        matched = 0
        serviceName = None
        if self.listenerStatus:
            for line in self.listenerStatus:
                if not matched:
                    matcher = re.match('.*?Services Summary(.*)', line, re.S)
                    if matcher:
                        matched = 1
                else:
                    srvName = re.match(r"Service\s+\"(.*?)\".*", line)
                    if srvName:
                        serviceName = srvName.group(1)
                        knownServices[serviceName] = []
                    instanceName = re.match(r"\s+Instance\s+\"(.*?)\".*", line)
                    if instanceName and serviceName:
                        knownServices[serviceName].append(instanceName.group(1))
        return knownServices

    def getDbInstanceNumber(self, dbSid, servName = None):
        serviceName = self.serviceName
        if servName:
            serviceName = servName

        if self.knownDbInstances and serviceName and dbSid:
            dbInstances = self.knownDbInstances.get(serviceName)
            if dbInstances:
                i = 1
                for instanceName in dbInstances:
                    if instanceName and instanceName.lower() == dbSid.lower():
                        return str(i)
                    i += 1

    def getVersion(self):
        if self.listenerStatus:
            for line in self.listenerStatus:
                ver = re.match('.*Version\s+([\d\.]+).*', line)
                if ver:
                    return ver.group(1).strip()
    def getShortVersion(self):
        fullVersion = self.getVersion()
        if fullVersion:
            version = re.match('(\d+\.\d+)', fullVersion)
            if version:
                return version.group(1).strip()

def createWeakListener(hostOsh):
    osh = modeling.createApplicationOSH('application', 'TNS Listener', hostOsh, 'Database', 'Oracle')
    return osh

def createRacOSH(racName, instancesNumber, serviceName, version):
    racOSH = ObjectStateHolder('rac')
    racOSH.setAttribute('data_name', racName)
    racOSH.setAttribute('rac_servicename', serviceName)
    if instancesNumber:
        try:
            racOSH.setIntegerAttribute('instancescount' , int(instancesNumber))
        except:
            logger.warn('Number of instances appeared to be a non integer value: %s' % instancesNumber)

    modeling.setAppSystemVendor(racOSH)
    if version:
        racOSH.setAttribute('version', version)
    return racOSH

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    shell = None
    protocol = Framework.getDestinationAttribute('Protocol')
    listenerName = Framework.getDestinationAttribute('listenerName')
    listenerPath = Framework.getDestinationAttribute('listener_process_path')
    defOraHomes = Framework.getParameter('OracleHomes')
    listenerIp = Framework.getDestinationAttribute('listener_ip')
    listenedIPs = Framework.getTriggerCIDataAsList('listened_ips')

    try:
        try:
            client = Framework.createClient()
            shell = shellutils.ShellUtils(client)

            if listenerPath:
                envConf = UnixOracleEnvConfig(shell)
                if shell.isWinOs():
                    envConf = WindowsOracleEnvConfig(shell)
                envConf.setOracleHomeEnvVar(listenerPath)
            else:
                envConf = EnvConfigurator(shell, defOraHomes)
            
            if not listenedIPs:
                Framework.reportError('No listened_ips attribute values found.')
                return OSHVResult
            lookuper = LookupManager(listenedIPs)
            
            serviceToNodesMap = {}
            srvDiscoverer = SrvctlBasedDiscoverer(shell, envConf)
            databases = srvDiscoverer.getDatabases()
            for database in databases:
                instanceAndNodes = srvDiscoverer.getInstancesWithNodes(database)
                if instanceAndNodes:
                    serviceToNodesMap[database] = instanceAndNodes
                    for elem in instanceAndNodes:
                        resolver = DNSResolver(shell, elem.get('Node'))
                        ipAddr = resolver.resolveNSLookup()
                        if not ipAddr:
                            ipAddr = resolver.resolveNSLookupAliasBased()
                            ipAddr = ipAddr and ipAddr[0]
                            try:
                                if not ipAddr:
                                    ipAddr = resolver.resolveHostsFile()
                            except:
                                pass
                        elem['ip'] = ipAddr
                    
                    
            for (serviceName, params) in serviceToNodesMap.items():
                try:
                    listeners = []
                    oracles = []
                    for elem in params:
                        ipAddr = elem.get('ip')
                        if not ipAddr:
                            raise ValueError('One of the Node Ip is not discovered. Can not create full topology.')
                        hostOSH = modeling.createHostOSH(ipAddr)
                        OSHVResult.add(hostOSH)
                        listenerOSH = createWeakListener(hostOSH)
                        if listenerIp == ipAddr:
                            listenerOSH.setStringAttribute('name', listenerName)
                        listeners.append(listenerOSH)
                        oracleOsh = modeling.createDatabaseOSH('oracle', elem['Instance'], None, ipAddr, hostOSH)
                        listeners.append(oracleOsh)
                        oracles.append(oracleOsh)
                    racName = ''
                    nodes = [ x['Node'] for x in params if x['Node'] ]
                    nodes.sort()
                    racName = ':'.join(nodes)
                    racOsh = createRacOSH(racName, len(params), serviceName, None)
                    OSHVResult.add(racOsh)
                    for listener in listeners:
                        OSHVResult.add(listener)
                        OSHVResult.add(modeling.createLinkOSH('member', racOsh, listener))
                    for oracle in oracles:
                        OSHVResult.add(oracle)
                        OSHVResult.add(modeling.createLinkOSH('member', racOsh, oracle))
                except:
                    Framework.reportWarning('Failed to lookup host name of the node. Probably not all nodes were discovered by \"Oracle Listener by Shell\" Job. No RAC CI will be created.')
                    logger.warn('Failed to lookup host name for node with ip. No RAC CI will be created.')
            if not serviceToNodesMap:
                logger.warn('Failed to get information via srvctl. Will use old approach.')
            else:
                return OSHVResult
            #old flow
            tnsConfig = {}
            try:
                tnsConfig = TNSNamesConfig(shell, envConf)
            except:
                logger.debug('Failed to get tnsnames.ora. Trying different home.')
                envConf = EnvConfigurator(shell, defOraHomes)
                oraHome = envConf.findMatchingDefaultOracleHome()
                envConf = UnixOracleEnvConfig(shell)
                envConf.setOracleHomeEnvVar(oraHome)
                tnsConfig = TNSNamesConfig(shell, envConf)

            racParams = tnsConfig.getRacParams()
            servChec = ServiceChecker(shell, envConf, listenerName = listenerName)
            for racServiceName in racParams.keys():
                parametersDict = racParams[racServiceName]
                racNodeNameList = []
                racInstCount = len(parametersDict.keys())

                if not servChec.isServiceRunning(racServiceName.upper()) or racInstCount == 0 or racInstCount != int(servChec.getServiceInstancesNumber(racServiceName)):
                    Framework.reportWarning('Oracle RAC is not running or not all Instances were detected')
                    continue

                racVersion = servChec.getVersion()
                shortVersion = servChec.getShortVersion()
                listeners = []
                oracles = []
                for ip in parametersDict.keys():
                    hostName = lookuper.lookupByIp(ip) or ' '
                    hostPrimIp = lookuper.getPrimaryIp(ip)
                    actIp = ip

                    if not hostName:
                        Framework.reportError('Failed to lookup host name of the node. Probably not all nodes were discovered by \"Oracle Listener by Shell\" Job. No RAC CI will be created.')
                        logger.error('Failed to lookup host name for node with ip %s . No RAC CI will be created.' % ip)
                        return ObjectStateHolderVector()
                    racNodeNameList.append(hostName)
                    dbSid = parametersDict[actIp]
                    if hostPrimIp:
                        actIp = hostPrimIp
                    hostOSH = modeling.createHostOSH(actIp)
                    OSHVResult.add(hostOSH)
                    listenerOSH = createWeakListener(hostOSH)
                    listeners.append(listenerOSH)
                    oracleOSH = modeling.createDatabaseOSH('oracle', dbSid, None, actIp, hostOSH, None, None, None, shortVersion, racVersion, shortVersion)
                    instanceNumber = servChec.getDbInstanceNumber(dbSid, racServiceName)
                    if instanceNumber:
                        oracleOSH.setAttribute('oracle_instancenumber', instanceNumber)
                    oracles.append(oracleOSH)
                racNodeNameList.sort()
                racName = ''
                for nodeName in racNodeNameList:
                    if racName == '':
                        racName = nodeName
                    else:
                        racName += ':' + nodeName
                racOSH = createRacOSH(racName, racInstCount, racServiceName, racVersion)
                OSHVResult.add(racOSH)
                for listener in listeners:
                    OSHVResult.add(listener)
                    OSHVResult.add(modeling.createLinkOSH('member', racOSH, listener))
                for oracle in oracles:
                    OSHVResult.add(oracle)
                    OSHVResult.add(modeling.createLinkOSH('member', racOSH, oracle))
        finally:
            try:
                shell and shell.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    except:
        msg = logger.prepareFullStackTrace('')
        errormessages.resolveAndReport(msg, protocol, Framework)
    return OSHVResult
