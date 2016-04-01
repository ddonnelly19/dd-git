#coding=utf-8
from modeling import finalizeHostOsh
import WMI_Connection_Utils
import os
import sys
import re
import time
import string
import errormessages
import logger
import netutils
import modeling
#from xml.dom.minidom import parse
# Java imports
from java.io import File
from java.io import FileOutputStream
from java.lang import Exception, Boolean
from org.jdom.input import SAXBuilder

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

import ntpath

NMAP_PROGRAM_NAME = 'nmap.exe'

PORT_TYPE_NAMES_DICT = {'tcp' : modeling.SERVICEADDRESS_TYPE_TCP, 'udp' : modeling.SERVICEADDRESS_TYPE_UDP}

HOST_CLASS_DICT = {
                "Windows" : "nt",
                "HP-UX" : "unix",
                "SunOS" : "unix",
                "Solaris" : "unix",
                "OpenBSD" : "unix",
                "NetWare" : "netware",
                "NeXTStep" : "host",
                "UX/4800" : "host",
                "BSD-misc" : "unix",
                "Minix" : "host",
                "Windows Longhorn" : "nt",
                "DOS" : "nt",
                "VM/CMS" : "mainframe",
                "OS/2" : "host",
                "OS/390" : "mainframe",
                "Linux" : "unix",
                "Mac OS X" : "unix",
                "OS/400" : "as400",
                "FreeBSD" : "unix",
                "NetBSD" : "unix",
                "AIX" : "unix",
                "Digital UNIX" : "unix",
                "DragonFly BSD" : "unix" }

SOFTWARE_NAMES_DICT = {
                    "mysql" : "MySQL DB",
                    "tomcat" : "Apache WebServer",
                    "microsoft.*sql" : "MSSQL DB",
                    "ibm db2" : "IBM DB2",
                    "microsoft.*iis" : "Microsoft IIS WebServer",
                    "weblogic.*server" : "WebLogic AS",
                    "websphere.*server" : "WebSphere AS",
                    "vmware.*virtualcenter" : "VMware VirtualCenter",
                    "vmware esx" : "Virtualization Layer Software",
                    "microsoft exchange server" : "Microsoft Exchange Server" }

def syncNmapPortConfigFile(agentPath):
    '''
        Sync nmap port config with global probe's "port number to port name" mapping
    '''
    logger.debug('synchronizing nmap port config file')
    portConfigFilename = agentPath + CollectorsParameters.getDiscoveryConfigFolder() + CollectorsParameters.FILE_SEPARATOR + 'portNumberToPortName.xml'
    mamservice = File(portConfigFilename)
    nmapservice = File(agentPath + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'nmap-services')
    if nmapservice.lastModified() > mamservice.lastModified():
        return
    nmapFile = FileOutputStream(nmapservice)
    document = SAXBuilder(0).build(mamservice)
#	document = parse(portConfigFilename)
    ports = XmlWrapper(document.getRootElement().getChildren('portInfo'))
    for port in ports:
        if int(port.getAttributeValue("discover")):
            portNumber = port.getAttributeValue("portNumber")
            portName = port.getAttributeValue("portName")
            portProtocol = port.getAttributeValue("portProtocol")
            nmapFile.write("%s\t%s/%s\r\n" % (portName, portNumber, portProtocol))
    nmapFile.close()


class XmlWrapper:
    '''
    Due to bug in jython 2.1 we can't use xml.dom.minidom.
    Just a glue class for connecting Java and Jython XML Elements.
    '''
    def __init__(self, xmlElements):
        self.elements = []
        iterator = xmlElements.iterator()
        while iterator.hasNext():
            self.elements.append(iterator.next())
        self.len = len(self.elements)

    def __len__(self):
        return self.len

    def __getitem__(self, index):
        return self.elements[index]


def performNmapDiscover(client, ip, tmpFilename, timeout, agent_ext_dir, scanKnownPortsOnly, portstoscan, doServiceFingerprints, discoverUdpPorts, nmapLocation=None):
    #default port scaninng is -sS
    parametersList = ['-O', '-osscan-guess', '-sS']
    if doServiceFingerprints:
        parametersList.append('-sV')
    if discoverUdpPorts:
        parametersList.append('-sU')
    if portstoscan:
        parametersList.append('-p ' + portstoscan)
    if scanKnownPortsOnly:
        parametersList.append('-F')
    parametersList.append('--host-timeout ' + str(timeout) + 's')
    parametersList.append(ip)
    parametersList.append('-oX ' + tmpFilename)

    logger.debug('start executing nmap.exe')
    command = NMAP_PROGRAM_NAME
    if nmapLocation:
        nmapLocation = ntpath.normpath(nmapLocation)
        command = ntpath.join(nmapLocation, command)
        command = '"' + command +'"'
    command = ' '.join([command] + parametersList)
    output = client.executeCmd(command, timeout)

    if output.find('is not recognized') != -1:
        logger.error('NMAP is not installed on Probe machine. See job documentation for more details')
        raise ValueError, 'Nmap is not installed on Probe machine'

    logger.debug('end executing nmap.exe')

def processNmapResult(fileName, OSHVResult, discoverOsName, doServiceFingerprints, createApp, Framework):
    try:
        document = SAXBuilder(0).build(fileName)
    except:
        raise ValueError, "Can't parse XML document with nmap results. Skipped."
    hosts = XmlWrapper(document.getRootElement().getChildren('host'))
    for host in hosts:
        hostOsh = None
        ip = None
        macs = []
        addresses = XmlWrapper(host.getChildren('address'))
        for address in addresses:
            type = address.getAttributeValue('addrtype')
            addr = address.getAttributeValue('addr')
            if type == 'ipv4':
                ip = addr
            elif type == 'mac':
                macs.append(addr)
        hostnames = host.getChild('hostnames')
        if (hostnames is not None) and netutils.isValidIp(ip):
            hostnames = map(lambda elem: elem.getAttributeValue('name'), XmlWrapper(hostnames.getChildren('hostname')))
            hostname = hostnames and hostnames[0] or None #using only first dnsname
            os = host.getChild('os')
            if os and discoverOsName:
                osClass = os.getChild('osclass')
                if not osClass:
                    osMatch = os.getChild('osmatch')
                    osClass = osMatch.getChild('osclass')
                if osClass:
                    osType = osClass.getAttributeValue("type")
                    osFamily = osClass.getAttributeValue("osfamily")
                    osVendor = osClass.getAttributeValue("vendor")

                    hostClass = getHostClass(osType, osFamily)
                    if not hostClass:
                        Framework.reportWarning("Unknown OS detected. Vendor '%s', family '%s'" % (osVendor, osFamily))
                        hostClass = "host"

                    hostOsh = modeling.createHostOSH(ip, hostClass)
                    hostOsh.setAttribute("host_vendor", osVendor)
                    osMatch = os.getChild('osmatch')
                    if osMatch:
                        separateCaption(hostOsh, osMatch.getAttributeValue("name"))
                        hostOsh.setAttribute("host_osaccuracy", osMatch.getAttributeValue("accuracy")  + '%')
            if not hostOsh:
                hostOsh = modeling.createHostOSH(ip)

            ipOsh = modeling.createIpOSH(ip, dnsname=hostname)
            OSHVResult.add(ipOsh)
            OSHVResult.add(finalizeHostOsh(hostOsh))
            OSHVResult.add(modeling.createLinkOSH('contained', hostOsh, ipOsh))

            for mac in macs:
                if netutils.isValidMac(mac):
                    interfaceOsh = modeling.createInterfaceOSH(mac, hostOsh)
                    OSHVResult.add(interfaceOsh)
                    OSHVResult.add(modeling.createLinkOSH('containment', interfaceOsh, ipOsh))

            applicationList = []
            if not host.getChild('ports'):
                return
            ports = XmlWrapper(host.getChild('ports').getChildren('port'))
            for port in ports:
                portNumber = port.getAttributeValue('portid')
                protocol = port.getAttributeValue('protocol')
                serviceName = None
                if doServiceFingerprints:
                    if port.getChild("state").getAttributeValue("state").find('open') == -1:
                        continue
                    serviceNode = port.getChild("service")
                    if serviceNode:
                        serviceName = serviceNode.getAttributeValue("name")
                        serviceProduct = serviceNode.getAttributeValue("product")
                        serviceVersion = serviceNode.getAttributeValue("version")
                        if createApp and serviceProduct and serviceProduct not in applicationList:
                            addApplicationCI(ip,hostOsh,serviceProduct,serviceVersion, OSHVResult)
                            applicationList.append(serviceProduct)
                addServiceAddressOsh(hostOsh, OSHVResult, ip, portNumber, protocol, serviceName)


def getHostClass(osType,osFamily):
    if osType == "general purpose":
        hclass = HOST_CLASS_DICT.get(osFamily)
    elif osType == "router":
        hclass = "router"
    elif osType == "printer":
        hclass = "netprinter"
    else:
        hclass = "host"
    return hclass


def addApplicationCI(ip, hostOsh, serviceProduct,serviceVersion, OSHVResult):
    if serviceProduct:
        softwareName = None
        serviceProduct = serviceProduct.lower()
        patterns = SOFTWARE_NAMES_DICT.keys()
        patterns.sort()
        patterns.reverse()
        for pattern in patterns:
            if re.search(pattern, serviceProduct):
                softwareName = SOFTWARE_NAMES_DICT[pattern]
                break
        else:
            return

        applicationOSH = modeling.createApplicationOSH('application', softwareName, hostOsh)

        applicationOSH.setAttribute('application_ip', ip)

        if serviceVersion:
            applicationOSH.setAttribute('application_version', serviceVersion)

        OSHVResult.add(applicationOSH)


def addServiceAddressOsh(hostOsh, OSHVResult, ip, portNumber, protocol, portName=None):
    portType = PORT_TYPE_NAMES_DICT.get(protocol)
    if portType:
        if not portName:
            portConfig = ConfigFilesManagerImpl.getInstance().getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
            portName = portConfig.getPortNameByNumberAndType(int(portNumber), str(portType))
        serviceAddressOsh = modeling.createServiceAddressOsh(hostOsh, ip, portNumber, portType, portName)
        OSHVResult.add(serviceAddressOsh)

def separateCaption(hostOSH, caption):
    if caption.find('Windows')>-1:
        spList = re.findall('SP(\\d)', caption)
        if len(spList) == 1:
            sp = spList[0]
            hostOSH.setAttribute('nt_servicepack', sp)
        else:
            logger.debug('Service pack cannot be identified, discovered value: \'%s\'; skipping SP attribute' % caption)
        caption = WMI_Connection_Utils.separateCaption(caption)[1]
    modeling.setHostOsName(hostOSH, caption)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    logger.debug('Start nmap_osfingerprint.py')
    ip = Framework.getDestinationAttribute('ip_address')
    timeout = Framework.getParameter('nmap_host_timeout')
    if not str(timeout).isdigit():
        msg = "Timeout parameter value must be a digit"
        logger.debug(msg)
        errormessages.resolveAndReport(msg, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
        return OSHVResult

    timeout = int(timeout) * 1000
    scanKnownPortsOnly = Boolean.parseBoolean(Framework.getParameter('scan_known_ports_only'))
    portstoscan	= Framework.getParameter('scan_these_ports_only')
    doServiceFingerprints =Boolean.parseBoolean(Framework.getParameter('Perform_Port_Fingerprints'))
    createApp = Boolean.parseBoolean(Framework.getParameter('Create_Application_CI'))
    discoverOsName =Boolean.parseBoolean(Framework.getParameter('discover_os_name'))
    nmapLocation = Framework.getParameter('nmap_location')
    #discover_UDP_Ports	= int(Framework.getParameter('Discover_UDP_Ports'))
    discoverUdpPorts = 0

    agent_root_dir=CollectorsParameters.BASE_PROBE_MGR_DIR
    agent_ext_dir = agent_root_dir + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR
    tmp_file_name = agent_ext_dir + string.replace(ip,'.','_') + time.strftime("%H%M%S",time.gmtime(time.time())) + 'nmap.xml'

    syncNmapPortConfigFile(agent_root_dir)

    logger.debug('temp file for storing nmap results: ', tmp_file_name)
    try:
        client = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        try:
            performNmapDiscover(client, ip, tmp_file_name,timeout,agent_ext_dir,scanKnownPortsOnly,portstoscan,doServiceFingerprints, discoverUdpPorts, nmapLocation)
            if os.path.exists(tmp_file_name):
                logger.debug('start processing the nmap results')
                processNmapResult(tmp_file_name, OSHVResult, discoverOsName, doServiceFingerprints, createApp, Framework)
            else:
                raise ValueError, 'Error nmap result file is missing: %s' % tmp_file_name
        finally:
            client.close()
            File(tmp_file_name).delete()
    except Exception, e:
        msg = str(e.getMessage())
        logger.debug(msg)
        errormessages.resolveAndReport(msg, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
    except ValueError:
        msg = str(sys.exc_info()[1])
        errormessages.resolveAndReport(msg, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        logger.debug(msg)
        errormessages.resolveAndReport(msg, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)

    return OSHVResult
