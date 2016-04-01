import re
import logger
import netutils
import ibm_hmc_lib

class IbmHmcDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)
        
    def discover(self):
        hmcHost = self.getNetworkingInformation()
        #discovers HMC Type and serialNumber
        typeInformation = self.discoverSerialNumberAndType()
        # discovers full and short versions of the HMC
        versionInformation = self.discoverVersionInformation()
        #Setting BIOS information
        bios = self.getBiosVersion()
        
        hmcSoftware = ibm_hmc_lib.IbmHmc(bios, typeInformation, versionInformation)
        hmcHost.hmcSoftware = hmcSoftware
        
        return hmcHost

    def parseShortVersion(self, output):
        """
        This function parses and sets the Version information of the HMC
        @param output: output of 'lshmc -v' command
        @type output: String
        """
        version = re.search('Version\s*:\s*(\w+?)\s', output)
        if version:
            return version.group(1).strip()
    
    def parseFullVersion(self, output):
        """
        This function parses and sets the Version information of the HMC
        @param output: output of 'lshmc -V' command
        @type output: String
        """
        fullVersion = re.search('base_version\s*=\s*([\w\.]+?)[\s"]', output) or re.search('Release\s*:s*([\w\.]+?)', output)
        if fullVersion:
            return fullVersion.group(1).strip()
    
    def discoverBaseOSVersion(self):
        """
        """
        output = self._shell.execCmd('uname -r')
        if output and output.strip() and self._shell.getLastCmdReturnCode() == 0 and re.search('\d', output):
            return output.strip()
        else:
            logger.warn("Failed getting host OS version")
            
    def discoverVersionInformation(self):
        """
        This function discovers Version information of the HMC
        @param hmcDo: instance of VersionInformation class
        @type hmcDo: VersionInformation instance 
        """
        
        output = self.executeCommand('lshmc -V')
        shortVersion = self.parseShortVersion(output)
        fullVersion = self.parseFullVersion(output)
        baseOSVersion = self.discoverBaseOSVersion()
        
        return ibm_hmc_lib.VersionInformation(shortVersion, fullVersion, baseOSVersion)
    
    def parseSerialNumber(self, output):
        """
        This function parses  Serial Number 
        @param output: output of 'lshmc -V' command
        @type output: String
        """
        if output:
            serialNumber = re.search('\*SE\s+([\w \-]+?)[\r\n]', output)
            if not serialNumber:
                raise ValueError, "HMC not found"
            return serialNumber.group(1).strip()
    
    def parseType(self, output):
        if output:
            hmcType = re.search('\*TM (\w+?)\s', output)
            if hmcType:
                return hmcType.group(1).strip()
    
    def discoverSerialNumberAndType(self):
        output = self.executeCommand('lshmc -v')
        serialNumber = self.parseSerialNumber(output)
        hmcType = self.parseType(output)
        return ibm_hmc_lib.HmcTypeInformation(hmcType, serialNumber)
    
    def parseBiosVersion(self, output):
        """
        This function parses HMC Bios information
        @param output: output of 'lshmc -b' command
        @type output: String
        @return : BIOS version
        @rtype : String 
        """
        bios = re.search('bios=([^\n]+)', output)
        if bios:
            return bios.group(1).strip()
            
    def getBiosVersion(self):
        """
            This function parses and sets HMC Bios information
            @param output: output of 'lshmc -b' command
            @type output: String
            @param hmcDo: instance of IbmHmcDo class
            @type hmcDo: IbmHmcDo instance 
        """
        output = self.executeCommand('lshmc -b')
        return self.parseBiosVersion(output)
    
    def parseNetworkingInformation(self, buffer):
        """
        This function performs parsing of the 'lshmc -n' command output
        @param buffer: string buffer of the command output 
        @return: host and ip information
        @rtype: instance of HostDo object
        """
        host = ibm_hmc_lib.Host()
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            host.hostname = propertiesDict.get('hostname')
            host.domainName = propertiesDict.get('domain')
            for (key, value) in propertiesDict.items():
                if key.startswith('ipv4addr_eth'):
                    if value and netutils.isValidIp(value) and not netutils.isLocalIp(value):
                        ip = ibm_hmc_lib.Ip(value, propertiesDict.get(key.replace('addr', 'netmask')))
                        host.ipList.append(ip)
            
            if not host.ipList: #another version of HMC outputs, for the minor HMC version change
                ipStr = propertiesDict.get('ipaddr')
                netMaskStr = propertiesDict.get('networkmask')
                if ipStr and netMaskStr:
                    ipList = ipStr.split(',')
                    netMaskList = netMaskStr.split(',')
                    for i in range(len(ipList)):
                        ipAddr = ipList[i].strip()
                        netMask = netMaskList[i].strip()
                        if ipAddr and netutils.isValidIp(ipAddr) and not netutils.isLocalIp(ipAddr):
                            ip = ibm_hmc_lib.Ip(ipAddr, netMask)
                            host.ipList.append(ip)
                            
            if not host.ipList:
                raise ValueError("Failed parsing HMC host IP addresses from  %s " % buffer)
        return host

        
    def getNetworkingInformation(self):
        """
        This function performs discovery of IBM HMC Host Networking information
        @param shell: either SSH or Telnet Client wrapped with the ShellUtils
        @type shell: ShellUtils instance
        @return: host and ip information
        @rtype: instance of HostDo object
        """
        try:
            output = self.executeCommand('lshmc -n')
        except ValueError:
            logger.reportWarning('IBM HMC not detected.')
            raise
        
        return self.parseNetworkingInformation(output)
    
class IbmHmcV3Discoverer(IbmHmcDiscoverer):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def parseNetworkingInformation(self, buffer):
        """
        This function performs parsing of the 'lshmc -n' command output for HMC 3.7 version
        @param buffer: string buffer of the command output 
        @return: host and ip information
        @rtype: instance of HostDo object
        """
        host = ibm_hmc_lib.Host()
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer, '\n', ':')
            host.hostname = propertiesDict.get('Host Name')
            host.domainName = propertiesDict.get('Domain Name')
            for (key, value) in propertiesDict.items():
                if re.match('TCP/IP Interface \d+ Address', key):
                    if value and netutils.isValidIp(value) and not netutils.isLocalIp(value):
                        ip = ibm_hmc_lib.Ip(value, propertiesDict.get(key.replace('Address', 'Network Mask')))
                        host.ipList.append(ip)
        return host
    
    def parseBiosVersion(self, output):
        """
        This function parses HMC Bios information
        @param output: output of 'lshmc -b' command
        @type output: String
        @return : BIOS version
        @rtype : String 
        """
        bios = output and output.strip()
        if bios:
            return bios

class IbmIvmDiscoverer(IbmHmcDiscoverer):
    def __init__(self, shell):
        IbmHmcDiscoverer.__init__(self, shell)

    def parseSerialNumberAndVersion(self, output):
        """str -> list(str,str,str)"""
        version = None
        serial = None
        if output:
            pairs = output.split(',')
            version = pairs[0].strip()
            serial = pairs[1].strip()
        return (version, version, serial)

    def discoverSerialNumberAndVersion(self):
        """
        This function discovers Version information of the IVM
        @param hmcDo: instance of VersionInformation class
        @type hmcDo: VersionInformation instance 
        """
        
        output = self.executeCommand('lsivm')
        (shortVersion, fullVersion, serialNumber) = self.parseSerialNumberAndVersion(output)
        
        return (ibm_hmc_lib.VersionInformation(shortVersion, fullVersion), serialNumber)

    def parseNetworkingInformation(self, output):
        host = ibm_hmc_lib.Host()
        if output:
            potential_ips = re.findall('e[nt]+\s+([\da-fA-F:]+)\s+([\da-fA-F:]+)', output)
            for (ipAddr, mask) in potential_ips:
                if ipAddr and netutils.isValidIp(ipAddr) and not netutils.isLocalIp(ipAddr):
                    ip = ibm_hmc_lib.Ip(ipAddr, mask)
                    host.ipList.append(ip)
        return host

    def getNetworkingInformation(self):
        output = self.executeCommand('lstcpip -interfaces')
        return self.parseNetworkingInformation(output)

    def getHostName(self):
        output = self.executeCommand('hostname')
        if output:
            return output.strip()

    def discover(self):
        ivmHost = self.getNetworkingInformation()
        ivmHost.hostname = self.getHostName()
        #discovers HMC Type and serialNumber
        (versionInformation, serialNumber) = self.discoverSerialNumberAndVersion()
        typeInformation = ibm_hmc_lib.HmcTypeInformation(None, serialNumber)
        hmcSoftware = ibm_hmc_lib.IbmIvm(None, typeInformation, versionInformation)
        ivmHost.hmcSoftware = hmcSoftware
        
        return ivmHost