#coding=utf-8
import re
import sys
import logger
import mysql_version_by_shell
import shell_interpreter
from file_ver_lib import getLinuxFileVer
from plugins import Plugin
import modeling
import dbutils
import netutils
import dns_resolver
import socket

class MySQLVersionShellPlugin(Plugin):
    """
        Plugin set MySQL version by shell, depends on OS type.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__process = None
        self.__isWinOs = None
        self.__cmd = None

    def isApplicable(self, context):
        self.__client = context.client
        try:
            if self.__client.isWinOs():
                self.__isWinOs = 1
                self.__process = context.application.getProcess('mysqld-nt.exe')
                if not self.__process:
                    self.__process = context.application.getProcess('mysqld.exe')
            else:
                self.__process = context.application.getProcess('mysqld')
            if self.__process:
                return 1
        except:
            logger.errorException(sys.exc_info()[1])

    def process(self, context):
        applicationOsh = context.application.getOsh()
        mysql_version_by_shell.setVersion(applicationOsh, self.__process.executablePath, self.__client)


class OracleVersionShellPlugin(Plugin):
    """
        Plugin set Oracle version by shell, depends on OS type.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__process = None
        self.__isWinOs = None
        self.__cmd = None
        self.__listenerStatus = None

    def isApplicable(self, context):
        self.__client = context.client
        try:
            if self.__client.isWinOs():
                self.__isWinOs = 1
                self.__process = context.application.getProcess('oracle.exe')
            else:
                return 1

            if self.__process:
                return 1
        except:
            logger.errorException(sys.exc_info()[1])

    def __parseVersion(self, buff):
        match = re.search('Release\s+(\d+\.\d+)', buff)
        if match:
            return match.group(1)

    def setOracleHome(self, binDir):
        expCommand = 'export '
        if self.__isWinOs:
            expCommand = 'set '
        oraHome = re.match(r"(.*)bin[/\\]+", binDir)
        if oraHome:
            buf = self.__client.execCmd(expCommand + 'ORACLE_HOME='+oraHome.group(1).strip())

    def getWindowsVersion(self, applicationOsh):
        path = self.__process.executablePath
        if path:
            matchPath = re.search(r'(.+\\)[^\\]*?$', path)
            if matchPath:
                dir = matchPath.group(1).strip()
                self.setOracleHome(dir)
                self.__cmd = '"' + dir.replace('\/','\\') + 'sqlplus' +'"' +' -v'
                buff = self.__client.execCmd(self.__cmd, 60000)
            if buff and self.__client.getLastCmdReturnCode() == 0:
                version = self.__parseVersion(buff)
                if version:
                    applicationOsh.setAttribute("application_version_number", version)
                    logger.debug("Oracle version : " + version)
                else:
                    logger.error('Failed getting Oracle version')

    def getOraBinDir(self, dbSid):
        oratabContent = self.__client.safecat('/etc/oratab')
        if oratabContent and self.__client.getLastCmdReturnCode() == 0:
            for line in oratabContent.split('\n'):
                oracleHome = re.match(r"\s*" + dbSid + "\s*:(.*?):.*", line)
                if oracleHome:
                    return oracleHome.group(1).strip()+'/bin/'

    def getUnixVersion(self, applicationOsh):
        dbSID = applicationOsh.getAttributeValue('database_dbsid')
        if dbSID:
            oraBinDir = self.getOraBinDir(dbSID)
            if oraBinDir:
                self.setOracleHome(oraBinDir)
                self.__cmd = oraBinDir + 'sqlplus -v'
                buff = self.__client.execCmd(self.__cmd, 60000)
                if buff and self.__client.getLastCmdReturnCode() == 0:
                    version = self.__parseVersion(buff)
                    if version:
                        applicationOsh.setAttribute("application_version_number", version)
                        logger.debug("Oracle version : " + version)
                    else:
                        logger.error('Failed getting Oracle version')

    def process(self, context):
        applicationOsh = context.application.getOsh()
        try:
            if self.__isWinOs:
                self.getWindowsVersion(applicationOsh)
            else:
                self.getUnixVersion(applicationOsh)
        except:
            errMsg = 'Failed executing command: ' + self.__cmd + '. Exception received: %s' % (sys.exc_info()[1])
            logger.errorException(errMsg)

class OracleListenerShellPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.__shell = None
        self.__process = None
        self.__processInfo = None
        self.__isWinOs = None
        self.__listenerStatus = None
        self.__isRACWin = False
    def isApplicable(self, context):
        self.__shell = context.client
        try:
            if self.__shell.isWinOs():
                self.__isWinOs = 1
                self.__isRACWin = self.isRAC()
                self.__process = context.application.getProcess('tnslsnr.exe')
                self.__processInfo = context.application.getProcessInfo('tnslsnr.exe')
            else:
                self.__process = context.application.getProcess('tnslsnr')
                self.__processInfo = context.application.getProcessInfo('tnslsnr')

            if self.__process:
                return 1
        except:
            logger.errorException(sys.exc_info()[1])

    def getVersion(self, path):
        dir = re.match('(.*)tnslsnr.*$', path, re.IGNORECASE)
        if dir:
            self.setOracleHome(dir.group(1).strip())
            self.__listenerStatus = self.__shell.execCmd('\"'+dir.group(1).strip()+'lsnrctl\" status')
            if self.__listenerStatus and self.__shell.getLastCmdReturnCode() == 0:
                logger.debug('Status fetched')
                for line in self.__listenerStatus.split('\n'):
                    logger.debug('Processing line :'+ line)
                    version = re.search(r".*Version\s+(\d+\.\d+).*", line)
                    if version:
                        return version.group(1).strip()
            else:
                logger.debug('Error getting listener status.')
        else:
            logger.debug('Oracle home directory didn\'t match.')
    
    def getEndpointsFromListener(self):
        endpoints = []
        resolver = dns_resolver.create(self.__shell)
        if self.__listenerStatus:
            raw_endpoints = re.findall('HOST=([\w\.\-]+)\)\s*\(PORT=(\d+)\)', self.__listenerStatus)
            if raw_endpoints:
                for endpoint in raw_endpoints:
                    if netutils.isValidIp(endpoint[0]):
                        endpoints.append(endpoint)
                    else:
                        try:
                            ips = resolver.resolve_ips(endpoint[0])
                            for ip in ips:
                                if netutils.isValidIp(ip):
                                    endpoints.append((ip, endpoint[1]))
                        except:
                            logger.debugException('')
        return endpoints
    
    def getOracleSID(self, path):
        dir = re.match('(.*)tnslsnr.*$', path, re.IGNORECASE)
        sidlist = []
        if dir:
            self.setOracleHome(dir.group(1).strip())
            self.__listenerStatus = self.__shell.execCmd('\"' + dir.group(1).strip() + 'lsnrctl\" status')
            if self.__listenerStatus and self.__shell.getLastCmdReturnCode() == 0:
                logger.debug('Status fetched sid')
                for line in self.__listenerStatus.split('\n'):
                    sidline = re.search(r"Instance \"(\w*)\", status.*", line)
                    if sidline:
                        sidlist.append(sidline.group(1).strip())
            else:
                logger.debug('Error getting sid list.')
        else:
            logger.debug('Oracle home directory didn\'t match.')
        return set(sidlist)


    def getOracleHome(self, path):
        binDir = re.match('(.*)(?i)tnslsnr.*$', path, re.IGNORECASE)
        if binDir:
            oraHome = re.match(r"(.*)(?i)bin[/\\]+", binDir.group(1).strip())
            if oraHome:
                return oraHome.group(1).strip()


    def setOracleHome(self, binDir):
        oraHome = re.match(r"(.*)bin[/\\]+", binDir, re.IGNORECASE)
        if oraHome:
            environment = shell_interpreter.Factory().create(self.__shell).getEnvironment()
            try:
                environment.setVariable('ORACLE_HOME', oraHome.group(1).strip())
            except:
                logger.debugException('Failed to set ORACLE_HOME')
            else:
                logger.debug('ORACLE_HOME set to: %s' % oraHome.group(1).strip())

    def parseListenerAlias(self, listener_status):
        listener_alias = ''
        alias = re.search("Alias(\s+)(\w*)", listener_status)
        if alias:
            listener_alias = alias.group(2)
        else:
            logger.debug("Failed to parse Liatener Alias.")
        return listener_alias

    def getListenerIPs(self, listener_status):
        ip_list = []
        listener_ips = re.findall('HOST=([\w\.\-]+)\)\s*\(PORT=(\d+)\)', listener_status)
        if listener_ips:
            ip_list = listener_ips
        return ip_list

    def getListenerNameOnWinRAC(self):
        listener_list = []
        local_listeners = self.__shell.execCmd('srvctl status listener')
        local_listener_list = re.findall('Listener\s(.*)\sis\srunning\son', local_listeners, re.IGNORECASE)
        if local_listener_list:
            listener_list = local_listener_list
        scan_listeners = self.__shell.execCmd('srvctl status scan_listener')
        scan_listener_list = re.findall('SCAN\slistener\s(.*)\sis\srunning\son', scan_listeners, re.IGNORECASE)
        if scan_listener_list:
            for listener_name in scan_listener_list:
                listener_list.append(listener_name)
        return listener_list

    def getListenerNameOnWin(self, path):
        listener_name = ''
        dir = re.match('(.*)tnslsnr.*$', path, re.IGNORECASE)
        if dir:
            listener_Status = self.__shell.execCmd('\"' + dir.group(1).strip() + 'lsnrctl\" status')
            if listener_Status and self.__shell.getLastCmdReturnCode() == 0:
                listener_name = self.parseListenerAlias(listener_Status)
        return listener_name

    def isRAC(self):
        crs_status = self.__shell.execCmd('crsctl check crs')
        if crs_status and self.__shell.getLastCmdReturnCode() == 0:
            is_online = re.search('Cluster Ready Services is online', crs_status, re.IGNORECASE)
            if is_online:
                return True
            else:
                return False
        else:
            return False

    def mapListenerName(self, path, application_ip, port, listener_names):
        listener_name = ''
        dir = re.match('(.*)tnslsnr.*$', path, re.IGNORECASE)
        fqdn = socket.getfqdn(name=application_ip)
        shortname = fqdn.split('.')[0]
        if dir:
            for name in listener_names:
                listener_status = self.__shell.execCmd('\"'+dir.group(1).strip()+'lsnrctl\" status ' + name)
                listener_endpoints = self.getListenerIPs(listener_status)
                if (application_ip, port) in listener_endpoints or (fqdn, port) in listener_endpoints or (shortname, port) in listener_endpoints:
                    listener_name = name
                    break
        return listener_name

    def getPort(self, application_ip, endpoints_list):
        port = ''
        for endpoint in endpoints_list:
            if str(endpoint[0]) == application_ip:
                port = endpoint[1]
                break
        return port

    def process(self, context):
        applicationOsh = context.application.getOsh()
        path = self.__process.executablePath
        endpoints = self.__processInfo.getEndpoints()
        vector = context.resultsVector
        if path:
            version = self.getVersion(path)
            oracleHome = self.getOracleHome(path)
            if version:
                logger.debug('Listener version is :' + version)
                applicationOsh.setAttribute("application_version_number", version)
            if endpoints:
                sidlist = self.getOracleSID(path)
                endpoints_list = [(x.getAddress(), x.getPort()) for x in endpoints]
                if self.__isWinOs:
                    logger.info("Start to discover Listener Name on Windows")
                    if self.__isRACWin:
                        listener_names = self.getListenerNameOnWinRAC()
                        application_ip = applicationOsh.getAttributeValue("application_ip")
                        port = self.getPort(application_ip, endpoints_list)
                        listener_name = self.mapListenerName(path, application_ip, port, listener_names)
                    else:
                        listener_name = self.getListenerNameOnWin(path)

                    if listener_name:
                        applicationOsh.setAttribute("name", listener_name)
                    else:
                        logger.info("Failed to discover Oracle Listener name on Windows!")
                for sid in sidlist:
                    logger.debug('sid:', sid)
                    self.reportTopology(vector, sid, endpoints_list,
                                        context.application.getHostOsh())
            else:
                sidlist = self.getOracleSID(path)
                endpoints = self.getEndpointsFromListener()
                for sid in sidlist:
                    logger.debug('sid:', sid)
                    self.reportTopology(vector, sid, endpoints,
                                        context.application.getHostOsh())

    def reportTopology(self, vector, sid, endpoints, hostOsh):
        ip, port = endpoints[0]
        oracleOsh = modeling.createDatabaseOSH('oracle', sid, port, str(ip), hostOsh)
        vector.add(oracleOsh)
        for ip, port in endpoints:
            portOsh = modeling.createServiceAddressOsh(hostOsh, str(ip), port,
                                                       modeling.SERVICEADDRESS_TYPE_TCP)
            vector.add(portOsh)
            link = modeling.createLinkOSH('use', oracleOsh, portOsh)
            vector.add(link)