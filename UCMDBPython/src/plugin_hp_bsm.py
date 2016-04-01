#coding=utf-8
import re
import logger
import file_system
from file_topology import FileAttrs, BASE_FILE_ATTRIBUTES
from plugins import Plugin
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
import netutils
import applications

GW_PROCESSES = ["hpbsm_db_loader", "hpbsm_wde", "schedulergw", "analytics_loader"]
DPS_PROCESSES = ["bpi_process_repository", "DomainManager", "hpbsm_pmanager", "hpbsm_marble_loader",\
                 "hpbsm_marble_worker_", "hpbsm_marble_matcher", "hpbsm_marble_supervisor",\
                 "hpbsm_offline_engine", "hpbsm_basel_engine", "hpbsm_pi_engine", "hpbsm_opr-backend", "hpbsm_bizImpact"]


class BsmBasePlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        return 1

    def process(self, context):
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses()

        isGw = 0
        isDps = 0
        for process in processes:
            processNameMatch = re.match("([\w\-]+)", process.getName())
            if not processNameMatch:
                continue
            processName = processNameMatch.group(1)
            logger.debug('Looking up process "%s"' % processName)
            if processName in GW_PROCESSES:
                isGw = 1
                logger.debug('Process %s matched - isGw')
            if processName in DPS_PROCESSES:
                isDps = 1
                logger.debug('Process %s matched - isDps')
                
        applicationName = applicationOsh.getAttributeValue('data_name')
        logger.debug('Preprocessing application "%s" isGw %s isDps %s' % (applicationName, isGw, isDps))
        if applicationName == "HP BSM GW Server" and not isGw:
            raise applications.IgnoreApplicationException('Not a GateWay server')
        elif applicationName == "HP BSM DPS Server" and not isDps:
            raise applications.IgnoreApplicationException('Not a DPS server')
#        if isGw and isDps:
#            applicationName = "HP BSM Typical install Server"
#        elif isGw and not isDps:
#            applicationName = "HP BSM GW Server"
#        elif not isGw and isDps:
#            applicationName = "HP BSM DPS Server"
#        else:
#            #old BAC
#            raise applications.IgnoreApplicationException('BAC installation found')
        
#        if applicationName:
#            applicationOsh.setStringAttribute("name", applicationName)
#            applicationOsh.setStringAttribute("discovered_product_name", applicationName)
    
class BsmTopologyByShell(BsmBasePlugin):
    VERSION_FILE_LOCATIONS = ['../dat/version.txt', '../../dat/version.txt', '../../dat/Version.txt']
    def __init__(self):
        BsmBasePlugin.__init__(self)
    
    def process(self, context):
        client = context.client
        BsmBasePlugin.process(self, context)
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses()
        vector = None
        for process in processes:
            if process.getName() in ["MercuryAS.exe", "MercuryAS"]:
                fullPath = process.executablePath
                pathToExecutableMatch = re.match("(.*)MercuryAS", fullPath)
                if pathToExecutableMatch:
                    configFileContent = ""
                    try:
                        configFilePath = pathToExecutableMatch.group(1) + "../../odb/conf/cmdb.conf"
                        configFileContent = self.getConfigFile(client, configFilePath)
                    except:
                        logger.debugException('')
                        logger.debug('Failed getting configuration file.')
                    else:
                        parsedData = self.parseConfigFile(configFileContent)
                        if parsedData["host"]:
                            if netutils.isValidIp(parsedData["host"]):
                                parsedData["serverIp"] = parsedData["serverIp"]
                            else:
                                parsedData["serverIp"] = netutils.resolveIP(client, parsedData["host"])
    
                            if parsedData["dbtype"] == "Oracle":
                                vector = self.createOracleTopology(parsedData, applicationOsh)
                            else:
                                vector = self.createMsSqlTopology(parsedData, applicationOsh)
                    versionFileContent = ''
                    for fileLocation in BsmTopologyByShell.VERSION_FILE_LOCATIONS:
                        try:
                            configFilePath = pathToExecutableMatch.group(1) + fileLocation
                            versionFileContent = self.getConfigFile(client, configFilePath)
                        except:
                            logger.debug('Failed getting version file content')
                            continue
                        
                        (longVersion, shortVersion) = self.parseVersion(versionFileContent)
                        
                        if shortVersion and int(shortVersion) < 9:
                            #Not a BSM but a BAC -> ignoring application
                            raise applications.IgnoreApplicationException('Not a BSM installation')
                        
                        if longVersion:
                            applicationOsh.setStringAttribute('application_version', longVersion)
                        if shortVersion:
                            applicationOsh.setStringAttribute('application_version_number' , shortVersion)
        vector and context.resultsVector.addAll(vector)
        
    def parseVersion(self, content):
        longVersion = None
        shortVersion = None 
        if content:
            m = re.search('\s*Version\s*:*\s*([\d\.\-]+)', content)
            longVersion = m and m.group(1)
            m = longVersion and re.search('(\d+)', longVersion)
            shortVersion = m and m.group(1)
        return (longVersion, shortVersion)
                
    def getConfigFile(self, client, filePath):
        if filePath:
            fs = file_system.createFileSystem(client)
            fileAttributes = []
            fileAttributes.extend(BASE_FILE_ATTRIBUTES)
            fileAttributes.append(FileAttrs.CONTENT)
            file = fs.getFile(filePath, fileAttributes)
            return file.content
            
    
    def parseConfigFile(self, output):
        results = {"host": None, "dbtype" : None, "port" : None, "sid" : None, "dbname" : None}
        if output:
            m = re.search("dal.datamodel.host.name=([\w\-\.]+)", output)
            results["host"] = m and m.group(1)
            m = re.search("dal.datamodel.db.type=(\w+)", output)
            results["dbtype"] = m and m.group(1)
            m = re.search("dal.datamodel.port=(\d+)", output)
            results["port"] = m and m.group(1)
            m = re.search("dal.datamodel.sid=([\w\-\.]+)", output)
            results["sid"] = m and m.group(1)
            m = re.search("dal.datamodel.db.name=([\w\.\-]+)", output)
            results["dbname"] = m and m.group(1)
        return results
    
            
    def createOracleTopology(self, parsedData, applicationOsh):
        vector = ObjectStateHolderVector()
        if not parsedData["serverIp"] and parsedData["sid"]:
            return vector
        hostOsh = modeling.createHostOSH(parsedData["serverIp"])
        dbOsh = modeling.createDatabaseOSH('oracle', parsedData["sid"], parsedData["port"], parsedData["serverIp"], hostOsh)
        serviceEndPointOsh = modeling.createServiceAddressOsh(hostOsh, parsedData["serverIp"], parsedData["port"], 1)
        clientServerLinkOsh = modeling.createLinkOSH('client_server', applicationOsh, serviceEndPointOsh)
        clientServerLinkOsh.setStringAttribute('clientserver_protocol', 'tcp')
        usageLinkOsh = modeling.createLinkOSH('usage', dbOsh, serviceEndPointOsh)
        vector.add(hostOsh)
        vector.add(dbOsh)
        vector.add(serviceEndPointOsh)
        vector.add(clientServerLinkOsh)
        vector.add(usageLinkOsh)
        return vector
    
    def createMsSqlTopology(self, parsedData, applicationOsh):
        vector = ObjectStateHolderVector()
        if not parsedData["sid"]:
            parsedData["sid"] = parsedData["host"]
        if not parsedData["serverIp"] and parsedData["sid"]:
            return vector
        hostOsh = modeling.createHostOSH(parsedData["serverIp"])
        dbOsh = modeling.createDatabaseOSH('sqlserver', parsedData["sid"], parsedData["port"], parsedData["serverIp"], hostOsh)
        serviceEndPointOsh = modeling.createServiceAddressOsh(hostOsh, parsedData["serverIp"], parsedData["port"], 1)
        clientServerLinkOsh = modeling.createLinkOSH('client_server', applicationOsh, serviceEndPointOsh)
        clientServerLinkOsh.setStringAttribute('clientserver_protocol', 'tcp')
        usageLinkOsh = modeling.createLinkOSH('usage', dbOsh, serviceEndPointOsh)
        vector.add(hostOsh)
        vector.add(dbOsh)
        vector.add(serviceEndPointOsh)
        vector.add(clientServerLinkOsh)
        vector.add(usageLinkOsh)
        return vector
    