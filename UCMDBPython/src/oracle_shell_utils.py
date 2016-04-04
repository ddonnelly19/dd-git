#coding=utf-8
import re
import logger

ORACLE_HOME_ENV_COMMANDS = {'Windows':'set ORACLE_HOME', 'Unix':'echo $ORACLE_HOME'}
WINDOWS_CONFIG_SUFFIX = '\\network\\admin\\'
UNIX_CONFIG_SUFFIX = '/network/admin/'
WINDOWS_HOSTS_CONFIG = '%SystemRoot%\system32\drivers\etc\hosts'
UNIX_HOSTS_CONFIG = '/etc/hosts'
ORACLE_BIN_DIR_UNIX='/bin/'
ORACLE_BIN_DIR_WINDOWS='\\bin\\'
ORACLE_LISTENER_STATUS='lsnrctl status'

class OraConfigParser:
    def __init__(self, configContent, filterNodes = {}):
        self.rootMatcher = '\s*([\w\-\.]+)\s*=.*'
        self.configContent = configContent
        self.filteredNodes = filterNodes
        self.resultTree = self.parseConfig()
        #filteredNodes format:
        # hash with NodeName and corresponding parsePattern
        # example {'Hosts' : '\(\s*HOST\s*=\s*([\w\-\.]+)\s*\)'}

    def parseConfig(self):
        tree = {}
        results = {}
        rootName = None

        if self.configContent:
            bracketsNum = 0
            for line in self.configContent.split('\n'):
                if not line.strip() or re.match('\s+#', line):
                    continue
                if bracketsNum == 0:
                    #extract root element
                    buff = re.match(self.rootMatcher, line)
                    if buff:
                        rootName = buff.group(1).strip().upper()
                        results = {}
                #extract filtered child
                for key in self.filteredNodes.keys():
                    buf = re.findall(self.filteredNodes[key], line)
                    if buf:
                        values = results.get(key.upper())
                        if not values:
                            results[key.upper()] = map(lambda x: x.upper(), buf)
                        else:
                            values.extend(map(lambda x: x.upper(), buf))
                            results[key.upper()] = values
                if rootName:
                    tree[rootName] = results

                openedBrackets = len(re.findall('.*\(.*', line))
                closedBrackets = len(re.findall('.*\).*', line))
                bracketsNum += openedBrackets - closedBrackets

            return tree

    def getResultsDict(self):
        return self.resultTree

class DNSResolver:
    def __init__(self, shell, name, ipaddr = None):
        self.dnsName = name
        self.shell = shell
        self.ipAddr = ipaddr
        self.hostPrimaryIp = self.resolveIpByHostname()
        self.hostPrimaryDnsName = self.resolveDnsNameByHostname()
        if not self.ipAddr:
            self.ipAddr = self.resolveAddr()
        if not self.dnsName:
            self.dnsName = self.resolveDnsName()

    def resolveNSLookup(self, name = None):
        dnsName = name or self.dnsName
        if dnsName:
            buffer = self.shell.execCmd('nslookup '+dnsName)
            if buffer.find('can\'t find') == -1 and self.shell.getLastCmdReturnCode() == 0:
                matchPat = ".*Name:\s+"+dnsName+".*\n\s*Address:\s*((\d+\.\d+\.\d+\.\d+)|([\da-fA-F]+:[\da-fA-F:]+))"
                ipaddr = re.search(matchPat, buffer, re.S)
                if ipaddr:
                    return ipaddr.group(1).strip()

    def resolveNSLookupAliasBased(self, name = None):
        dnsName = name or self.dnsName
        if dnsName:
            buffer = self.shell.execCmd('nslookup '+dnsName)
            if buffer.find('can\'t find') == -1 and self.shell.getLastCmdReturnCode() == 0:
                aliasOrigin = re.search('canonical name\s*=\s*(.*?)\n', buffer)
                if aliasOrigin:
                    dnsName = aliasOrigin.group(1).strip()
                matchPat = ".*Name:\s+"+dnsName+".*\n\s*Address:\s*(.*)\n.*"
                ipaddrList = re.findall(matchPat, buffer, re.S)
                if ipaddrList:
                    return ipaddrList

    def resolveHostsFile(self):
        cmd = None
        if self.shell.isWinOs():
            cmd = WINDOWS_HOSTS_CONFIG
        else:
            cmd = UNIX_HOSTS_CONFIG

        if self.dnsName:
            buffer = self.shell.safecat(cmd)
            if buffer and self.shell.getLastCmdReturnCode() == 0:
                for line in buffer.split('\n'):
                    ipaddr = re.search(r"\s*(\d+\.\d+\.\d+.\d*).*\s"+self.dnsName+"[\s\.].*", line)
                    if ipaddr:
                        return ipaddr.group(1).strip()

    def __resolveIpByHostnameLinux(self):
        buffer = self.shell.execCmd('hostname -i')
        if buffer and self.shell.getLastCmdReturnCode() == 0:
            ipaddr = re.match(r"\s*(\d+\.\d+\.\d+.\d*).*", buffer)
            if ipaddr:
                ip = ipaddr.group(1).strip()
                if ip.find('127.0.0.') == -1:
                    return ip

    def __getHostname(self):
        hostName = self.shell.execCmd('hostname')
        if not hostName or not hostName.strip()or self.shell.getLastCmdReturnCode() != 0:
            return None
        return hostName.lower().strip()

    def __getDomainName(self):
        domainName = self.shell.execCmd('domainname')
        if not domainName or not domainName.strip() or self.shell.getLastCmdReturnCode() != 0:
            return None
        return domainName.lower().strip()

    def __resolveIpByHostnameNonLinux(self):
        hostName = self.__getHostname()
        domainName = self.__getDomainName()
        ipAddr = None
        if hostName and hostName.find(".") != -1:
            ipAddr = self.resolveNSLookup(hostName)
        elif domainName:
            # if not dot in hostname this is not a FQDN, so we'll try to build it
            ipAddr = self.resolveNSLookup(hostName + "." + domainName)
        return ipAddr

    def resolveIpByHostname(self):
        if self.shell.getOsType() == 'Linux':
            return self.__resolveIpByHostnameLinux()
        return self.__resolveIpByHostnameNonLinux()

    def resolveAddr(self):
        addr = self.resolveNSLookup()
        if not addr and self.hostPrimaryDnsName and self.hostPrimaryDnsName == self.dnsName:
            addr = self.hostPrimaryIp
        if not addr:
            addr = self.resolveHostsFile()
        return addr

    def resolveDnsNameByNslookup(self):
        if self.ipAddr:
            buffer = self.shell.execCmd('nslookup '+self.ipAddr)
            if buffer.find('can\'t find') == -1 and self.shell.getLastCmdReturnCode() == 0:
                matchPat = ".*Name:\s+(.*?)\n"
                dnsName = re.search(matchPat, buffer, re.S)
                if not dnsName:
                    matchPat = ".*arpa\s+name\s*=\s*(.*?)\.\s*\n"
                    dnsName = re.search(matchPat, buffer, re.S)
                if dnsName:
                    return dnsName.group(1).strip()

    def resolveDnsNameByHostname(self):
        if self.shell.getOsType() == 'Linux':
            hostDnsName = self.shell.execCmd('hostname -f').strip()
            if hostDnsName and self.shell.getLastCmdReturnCode() == 0:
                if hostDnsName.find('.') == -1:
                    hostDnsName = self.__getHostname()
                if hostDnsName and not (re.match('localhost\.', hostDnsName, re.I) or re.match('.*\.localdomain$', hostDnsName, re.I)):
                    return hostDnsName.strip()

    def resolveDnsName(self):
        dnsName = self.resolveDnsNameByNslookup()
        if not dnsName and self.hostPrimaryIp and self.ipAddr == self.hostPrimaryIp:
            dnsName = self.hostPrimaryDnsName
        return dnsName

    def getIPAddress(self):
        return self.ipAddr

    def getDnsName(self):
        return self.dnsName

class MACResolver:
    def __init__(self, shell, ipAddrList, isWinOS = None):
        self.shell = shell
        self.ipList = ipAddrList
        self.isWinOS =  isWinOS
        if self.isWinOS:
            self.isWinOS = self.shell.isWinOs()

        self.matchPattern = None
        self.arpTableCommand = None
        self.noArpEntry = None
        self. separator = None

        if self.isWinOS:
            self.matchPattern = '\s*%IPADDRESS%\s+([\w\-]+)\s+.*'
            self.arpTableCommand = 'arp -a '
            self.noArpEntry = 'No ARP Entries Found'
            self.separator = '-'
        else:
            self.matchPattern = '.*\(%IPADDRESS%\)\s+at\s+([\w:]+)\s+.*'
            self.arpTableCommand = 'arp -na'
            self.noArpEntry = 'no match found'
            self.separator = '-'
        self.macDict = self.resolveIPtoMAC()

    def resolveIPtoMAC(self):
        ipToMac = {}
        if self.arpTable:
            for ip in self.ipList:
                ipToMac[ip] = ''
                buffer = self.shell.execCmd(self.arpTableCommand)
                if buffer.find(self.noArpEntry) == -1 and self.shell.getLastCmdReturnCode() == 0:
                    matchPattern = self.matchPattern.replace('%IPADDRESS%',ip)
                    macMatch = re.search(matchPattern, self.arpTable, re.S)
                    mac = macMatch.group(1).strip()
                    if mac:
                        mac = mac.replace(self.separator, '')
                        ipToMac[ip] = mac

            return ipToMac

    def getResolvedMACs(self):
        return self.macDict

class EnvConfigurator:
    def __init__(self, shell, oracleHomes, isWinOS = None):
        self.isWinOS = isWinOS
        if self.isWinOS is None:
            self.isWinOS = shell.isWinOs()
        self.shell = shell
        self.defaultOracleHomes = oracleHomes
        self.activeOracleHome = None
        self.configPath = None
        if self.isWinOS:
            self.configPath = self.getWinConfigPath()
        else:
            self.configPath = self.getUnixConfigPath()

    def setDefaultOracleHome(self, defaultPath):
        if self.isWinOS:
            cmd = 'set ORACLE_HOME=%s' % defaultPath
        else:
            cmd = 'ORACLE_HOME=%s;export ORACLE_HOME' % defaultPath
        self.shell.execCmd(cmd)

    def findMatchingDefaultOracleHome(self):
        oracleHomeList = self.getConfiguredOracleHomes()
        if self.defaultOracleHomes:
            oracleHomeList.extend(self.defaultOracleHomes.split(','))
        if oracleHomeList:
            for oraHome in oracleHomeList:
                oraHome = oraHome.replace('\\','/')
                if self.shell.fsObjectExists(oraHome):
                    return oraHome.strip()


    def getConfiguredOracleHomes(self):
        oracleHomeList = []
        oratabContent = self.shell.execCmd('cat /etc/oratab | grep -v \":N\" | grep \'/\' | awk -F \":\" \'{print$2}\' | sort -u')
        if oratabContent and self.shell.getLastCmdReturnCode() == 0:
            for line in oratabContent.split('\n'):
                if line and line.strip():
                    oracleHomeList.append(line.strip())
        return oracleHomeList

    def getUnixConfigPath(self):
        buffer = self.shell.execCmd(ORACLE_HOME_ENV_COMMANDS['Unix'])
        if buffer and self.shell.getLastCmdReturnCode() == 0:
            oraHome = re.match(r"\s*(/.*)", buffer)
            if oraHome and oraHome.group(1).strip():
                self.activeOracleHome = oraHome.group(1).strip()
                logger.debug('Active Oracle Home is ' + self.activeOracleHome)
                return self.activeOracleHome + UNIX_CONFIG_SUFFIX
        else:
            oraHome = self.findMatchingDefaultOracleHome()
            if oraHome:
                self.setDefaultOracleHome(oraHome)
                self.activeOracleHome = oraHome
                logger.debug('Active Oracle Home is ' + self.activeOracleHome)
                return self.activeOracleHome + UNIX_CONFIG_SUFFIX
            raise Exception, "ORACLE_HOME not found."

    def getWinConfigPath(self):
        buffer = self.shell.execCmd(ORACLE_HOME_ENV_COMMANDS['Windows'])
        if buffer and self.shell.getLastCmdReturnCode() == 0:
            oraHome = re.match(r"\s*ORACLE_HOME=(.*)", buffer)
            if oraHome and oraHome.group(1).strip():
                self.activeOracleHome = oraHome.group(1).strip()
                return self.activeOracleHome + WINDOWS_CONFIG_SUFFIX
        else:
            oraHome = self.findMatchingDefaultOracleHome()
            if oraHome:
                self.setDefaultOracleHome(oraHome)
                self.activeOracleHome = oraHome
                return self.activeOracleHome + WINDOWS_CONFIG_SUFFIX
            raise Exception, "ORACLE_HOME not found."

    def getOracleHome(self):
        return self.activeOracleHome

    def getConfigPath(self):
        return self.configPath

    def getOracleBinDir(self):
        if self.isWinOS:
            return self.activeOracleHome + ORACLE_BIN_DIR_WINDOWS
        else:
            return self.activeOracleHome + ORACLE_BIN_DIR_UNIX


class OracleEnvConfig:
    CONFIG_SUFFIX = '/network/admin/'
    BIN_DIR_SUFFIX='/bin/'

    def __init__(self, shell):
        self.shell = shell
        self.oracleHome = None

    def setOracleHomeEnvVar(self, rawOracleHome):
        raise ValueError, "Not implemented"

    def normalizeOracleHome(self, rawOracleHome):
        oracleHome = rawOracleHome.replace('\\','/')
        match = re.match('(.*?)(/opmn)?/bin/*.*', oracleHome, re.IGNORECASE)
        if match:
            oracleHome = match.group(1)
        return oracleHome

    def getOracleHome(self):
        return self.oracleHome

    def getConfigPath(self):
        return self.oracleHome + OracleEnvConfig.CONFIG_SUFFIX

    def getOracleBinDir(self):
        return self.oracleHome + OracleEnvConfig.BIN_DIR_SUFFIX

class UnixOracleEnvConfig(OracleEnvConfig):
    def __init__(self, shell):
        OracleEnvConfig.__init__(self, shell)

    def setOracleHomeEnvVar(self, rawOracleHome):
        if not rawOracleHome:
            raise ValueError, "No ORACLE_HOME passed to the UnixOracleEnvConfig class"
        self.oracleHome = self.normalizeOracleHome(rawOracleHome)

        self.shell.execCmd('ORACLE_HOME=%s;export ORACLE_HOME' % self.oracleHome)

class WindowsOracleEnvConfig(OracleEnvConfig):
    def __init__(self, shell):
        OracleEnvConfig.__init__(self, shell)

    def setOracleHomeEnvVar(self, rawOracleHome):
        if not rawOracleHome:
            raise ValueError, "No ORACLE_HOME passed to the WindowsOracleEnvConfig class"
        self.oracleHome = self.normalizeOracleHome(rawOracleHome)

        self.shell.execCmd('set ORACLE_HOME=%s' % self.oracleHome)

class SrvctlBasedDiscoverer:
    def __init__(self, shell, envConf):
        self.__shell = shell
        self.__envConf = envConf

    def __parseDatabases(self, output):
        if output and output.strip():
            return [x.strip() for x in re.split('[\r\n]+', output) if x.strip()]

    def getDatabases(self):
        binDir = self.__envConf.getOracleBinDir()
        result = []
        if binDir:
            output = self.__shell.execCmd('%ssrvctl config database' % binDir)
            if self.__shell.getLastCmdReturnCode() == 0 and output:
                result = self.__parseDatabases(output)
        return result

    def __parseService(self, output):
        results = []
        if output:
            resultList = re.findall('Instance\s+([\w\-\.]+)\s+is\s+running\s+on\s+node\s+([\w\-\.]+)', output)
            if resultList:
                for resultLine in resultList:
                    results.append({'Node' : resultLine[1] and resultLine[1].strip(), 'Instance' : resultLine[0], 'ip' : None})
        return results

    def fixOraBinPath(self, output):
        binPath = None

        try:
            if isinstance(output, unicode):
                output = output.encode('ascii', 'ignore')

            strPattern = 'run the program from '
            idx = output.find(strPattern)

            if idx >= 0:
                binPath = output[idx + len(strPattern) : ]
                binPath = re.sub('\.[\r\n]+', '', binPath)

                if self.__shell.isWinOs():
                    binPath += ORACLE_BIN_DIR_WINDOWS;
                else:
                    binPath += ORACLE_BIN_DIR_UNIX;
        except:
            logger.warn('failed to correct the Oracle bin path %s', output)

        return binPath

    def getInstancesWithNodes(self, serviceName):
        if not serviceName:
            raise ValueError('Service Name is not set')
        binDir = self.__envConf.getOracleBinDir()
        if binDir:
            output = self.__shell.execCmd('%ssrvctl status database -d %s' % (binDir, serviceName))
            if self.__shell.getLastCmdReturnCode() != 0 and output and ('PRCD-1229' in output):
                binDir = self.fixOraBinPath(output)
                logger.debug('New dir of srvctl is %s' % binDir)
                output = self.__shell.execCmd('%ssrvctl status database -d %s' % (binDir, serviceName))

            if self.__shell.getLastCmdReturnCode() == 0 and output:
                return self.__parseService(output)

def getEnvConfigurator(shell):
    if shell.isWinOs():
        return WindowsOracleEnvConfig(shell)
    else:
        return UnixOracleEnvConfig(shell)