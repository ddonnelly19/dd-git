#coding=utf-8
################################################
# Created on Dec 8, 2010
#
# Author: Pat Odom
# Rewrote by Vladimir Kravets @ March 31, 2011
#
# AS400 discovery using IBM JavaToolBox library
################################################
import sys
import re
import logger
import netutils
import modeling
import errorcodes
import errorobject
import errormessages
from modeling import NetworkInterface

# Java imports

### Common Java Classes ###
from java.util import HashMap
from java.lang import Integer, IllegalArgumentException, NoClassDefFoundError

### UCMDB Common Java Classes ###
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

### UCMDB Agent/Client Java Classes ###
from com.hp.ucmdb.discovery.library.clients.agents.as400.query import ProgramCallDocumentQueryConfig, \
    ProgramCallQueryConfig, ServiceProgramCallQueryConfig

### AS400 Access Java Classes ###
try:
    from com.ibm.as400.access import AS400Text, AS400Bin4, ProgramParameter
except ImportError:
    ### Ignore import error - this mean that 3rd library is not exists in the classpath
    ### Such case will be processed during client creation and an appropriate message will be reported to uCMDB
    pass

protocolName = 'as400protocol'

class AS400Dicoverer:
    def __init__(self, client):
        self.__client = client
        self.__ipInfo = []
        self.__interfacesInfo = []
        self.__sysInfo = None
        
    def discover(self):
        logger.debug("Getting system information...")
        self.__sysInfo = self.__discoverSysInfo()
        logger.debug("Getting network information...")
        self.__ipInfo = self.__discoverIPInfo()
        logger.debug("Getting network interfaces information...")
        self.__interfacesInfo = self.__discoverInterfacesInfo()
    
    def __executeQuery(self):
        if self.__client.executeQuery():
            return 1
        else:
            self.__debugAS400Messages()
            return 0
    
    def __discoverInterfacesInfo(self):
        ips = {}
        masks = {}
        interfacesDict = {}
        interfacesList = []

        # Separate out the entries from the network information class entries
        for entry in self.__ipInfo:
            interfaceDescr = entry.interfaceDescr
            interfacesDict[interfaceDescr] = entry.interfaceName
            ip = entry.ip
            mask = entry.mask
            if netutils.isValidIp(ip) and not netutils.isLocalIp(ip):
                inIPs = ips.get(interfaceDescr, [])
                if not inIPs:
                    ips[interfaceDescr] = inIPs
                inIPs.append(ip)
                
                inMasks = masks.get(interfaceDescr, [])
                if not inMasks:
                    masks[interfaceDescr] = inMasks 
                inMasks.append(mask)

        maclist = self.__getMACsData()
        if maclist == None:
            logger.warn('Invalid MAC info, skipping.')
        else:
            for interfaceDesc in maclist.keys():
                mac = maclist.get(interfaceDesc)
                if netutils.isValidMac(mac):
                    logger.debug("Interface: %s, MAC: %s" % (interfaceDesc, mac))
                    mac = netutils.parseMac(mac)
                    interface = NetworkInterface(interfaceDesc, mac, ips.get(interfaceDesc), masks.get(interfaceDesc), -1, 0)
                    interface.name = interfacesDict.get(interfaceDescr) or None;
                    interfacesList.append(interface)
        return interfacesList

    def __getMACsData(self):
        '''
        Return list of macs which exists on connected host
        @types AS400Client, list(NetworkInfo), str -> list(string) 
        '''
        
        nummacs = 0;
        sizeofentry = 0;
        listoffset = 0;
        txt10 = AS400Text(10)
        txt20 = AS400Text(20)
        txt50 = AS400Text(50)
        txt8 = AS400Text(8)
        txt1 = AS400Text(1)
        bin4 = AS400Bin4()
        userspacename = "UCMDBIPINFQTEMP".ljust(20);
        extendattr = " "*10;
        initialvalue = " ";
        publicauthority = "*ALL";
        txtdescription = "Get Phy Int Data";
        replacecode = "*YES";
        format = "IFCD0100";
        
        parmList = []
        parmList.append(ProgramParameter(txt20.toBytes(userspacename), 20))
        parmList.append(ProgramParameter(bin4.toBytes(0)))
        queryConfig = ProgramCallQueryConfig("/QSYS.LIB/QUSDLTUS.PGM", parmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()
    
        parmList = []
        parmList.append(ProgramParameter(txt20.toBytes(userspacename), 20))
        parmList.append(ProgramParameter(txt10.toBytes(extendattr), 10))
        parmList.append(ProgramParameter(bin4.toBytes(5000)))
        parmList.append(ProgramParameter(txt1.toBytes(initialvalue), 1))
        parmList.append(ProgramParameter(txt10.toBytes(publicauthority), 10))
        parmList.append(ProgramParameter(txt50.toBytes(txtdescription), 50))
        parmList.append(ProgramParameter(txt10.toBytes(replacecode), 10))
        parmList.append(ProgramParameter(bin4.toBytes(0)))
        queryConfig = ProgramCallQueryConfig("/QSYS.LIB/QUSCRTUS.PGM", parmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()
    
        netparmList = [];
        param0 = ProgramParameter(txt20.toBytes(userspacename), 20)
        param0.setParameterType(2)
        param1 = ProgramParameter(txt8.toBytes(format), 8)
        param1.setParameterType(2)
        param2 = ProgramParameter(bin4.toBytes(0))
        param2.setParameterType(2)
    
        netparmList.append(param0)
        netparmList.append(param1)
        netparmList.append(param2)
    
        queryConfig = ServiceProgramCallQueryConfig("/QSYS.LIB/QTOCNETSTS.SRVPGM", "QtocLstPhyIfcDta", 0, netparmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()
    
        props = HashMap()
        queryConfig = ProgramCallDocumentQueryConfig("QUSRTVUS.pcml", "QUSRTVUS")
        self.__client.initQuery(queryConfig)
        macs = {}
        if self.__executeQuery():
            props = self.__client.getProperties(["QUSRTVUS.receiver.numentries", "QUSRTVUS.receiver.sizeofentry", "QUSRTVUS.receiver.listoffset"])
            nummacs = int(props.getProperty("QUSRTVUS.receiver.numentries"))
            sizeofentry = int(props.getProperty("QUSRTVUS.receiver.sizeofentry"))
            listoffset = int(props.getProperty("QUSRTVUS.receiver.listoffset"))
            for m in xrange(0, nummacs):
                props = HashMap()
                queryConfig = ProgramCallDocumentQueryConfig("QUSRTVUS4.pcml", "QUSRTVUS")
                self.__client.initQuery(queryConfig)
                values = HashMap()
                values.put("QUSRTVUS.start", Integer(int(listoffset) + 1))
                values.put("QUSRTVUS.length", Integer(int(sizeofentry)))
                self.__client.initPresetValues(values)
                if self.__executeQuery():
                    props = self.__client.getProperties(["QUSRTVUS.receiver.linetype", "QUSRTVUS.receiver.phyintstatus", "QUSRTVUS.receiver.physicaladdress", "QUSRTVUS.receiver.linedesc"])
                    linedesc = props.getProperty("QUSRTVUS.receiver.linedesc")
                    inttype = int(props.getProperty("QUSRTVUS.receiver.linetype"))
                    intstatus = int(props.getProperty("QUSRTVUS.receiver.phyintstatus"))
                    mac = props.getProperty("QUSRTVUS.receiver.physicaladdress")
                    if (inttype == 1) and (intstatus == 1):
                        logger.debug("Found MAC: %s" % mac)
                        macs[linedesc] = mac;
                    listoffset += sizeofentry;
        return macs;

    def __discoverIPInfo(self):
        '''
        Gets Network information for connected host
        @types AS400Client -> list(NetworkInfo)
        '''
        networkList = []
        intips = 0;
        sizeofentry = 0;
        listoffset = 0;
        txt10 = AS400Text(10);
        txt20 = AS400Text(20);
        txt50 = AS400Text(50);
        txt8 = AS400Text(8);
        txt1 = AS400Text(1);
        bin4 = AS400Bin4();
        userspacename = "UCMDBIPINFQTEMP".ljust(20)
        extendattr = " "*10
        initialvalue = " "
        publicauthority = "*ALL"
        txtdescription = "List Network Interfaces"
        replacecode = "*YES"
        format = "NIFC0100"
        
        parmList = []
        parmList.append(ProgramParameter(txt20.toBytes(userspacename), 20))
        parmList.append(ProgramParameter(bin4.toBytes(0)))
        queryConfig = ProgramCallQueryConfig("/QSYS.LIB/QUSDLTUS.PGM", parmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()
    
        parmList = []
        parmList.append(ProgramParameter(txt20.toBytes(userspacename), 20))
        parmList.append(ProgramParameter(txt10.toBytes(extendattr), 10))
        parmList.append(ProgramParameter(bin4.toBytes(5000)))
        parmList.append(ProgramParameter(txt1.toBytes(initialvalue), 1))
        parmList.append(ProgramParameter(txt10.toBytes(publicauthority), 10))
        parmList.append(ProgramParameter(txt50.toBytes(txtdescription), 50))
        parmList.append(ProgramParameter(txt10.toBytes(replacecode), 10))
        parmList.append(ProgramParameter(bin4.toBytes(0)))
        queryConfig = ProgramCallQueryConfig("/QSYS.LIB/QUSCRTUS.PGM", parmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()
        
        param0 = ProgramParameter(txt20.toBytes(userspacename), 20)
        param0.setParameterType(2);
        param1 = ProgramParameter(txt8.toBytes(format), 8);
        param1.setParameterType(2);
        param2 = ProgramParameter(bin4.toBytes(0));
        netparmList = [param0, param1, param2]
        queryConfig = ServiceProgramCallQueryConfig("/QSYS.LIB/QTOCNETSTS.SRVPGM", "QtocLstNetIfc", 0, netparmList)
        self.__client.initQuery(queryConfig)
        self.__executeQuery()

        queryConfig = ProgramCallDocumentQueryConfig("QUSRTVUS.pcml", "QUSRTVUS")
        self.__client.initQuery(queryConfig)
        if self.__executeQuery():
            ipsInfo = self.__client.getProperties(["QUSRTVUS.receiver.numentries", "QUSRTVUS.receiver.sizeofentry", "QUSRTVUS.receiver.listoffset"])
            intips = int(ipsInfo.getProperty("QUSRTVUS.receiver.numentries"))
            sizeofentry = int(ipsInfo.getProperty("QUSRTVUS.receiver.sizeofentry"))
            listoffset = int(ipsInfo.getProperty("QUSRTVUS.receiver.listoffset"))
            for m in xrange(intips):
                queryConfig = ProgramCallDocumentQueryConfig("QUSRTVUS2.pcml", "QUSRTVUS")
                self.__client.initQuery(queryConfig)
                values = HashMap()
                values.put("QUSRTVUS.start", Integer(int(listoffset) + 1))
                values.put("QUSRTVUS.length", Integer(int(sizeofentry)))
                self.__client.initPresetValues(values)
                if self.__executeQuery():
                    props = self.__client.getProperties(["QUSRTVUS.receiver.internetaddr", "QUSRTVUS.receiver.networkaddr", "QUSRTVUS.receiver.linedesc", "QUSRTVUS.receiver.interfacesubnetmask", "QUSRTVUS.receiver.interfacename"])
                    ip = props.getProperty("QUSRTVUS.receiver.internetaddr")
                    networkAddr = props.getProperty("QUSRTVUS.receiver.networkaddr")
                    interfaceDescr = props.getProperty("QUSRTVUS.receiver.linedesc")
                    interfaceName = props.getProperty("QUSRTVUS.receiver.interfacename")
                    networkMask = props.getProperty("QUSRTVUS.receiver.interfacesubnetmask")
                    if not isIpInList(networkList, ip):
                        try:
                            networkInfo = NetworkInfo(ip, networkAddr, interfaceName, interfaceDescr, networkMask)
                        except IllegalArgumentException, e:
                            logger.debugException(str(e))
                        else:
                            networkList.append(networkInfo);  
                    listoffset += sizeofentry;
        return networkList;
    
    def __getOSVersion(self):
        queryConfig = ProgramCallDocumentQueryConfig("QSZRTVPR.pcml", "QSZRTVPR")
        self.__client.initQuery(queryConfig)
        receiverLength = self.__client.getOutputSize("QSZRTVPR.receiver");
        presetValues = HashMap()
        presetValues.put("QSZRTVPR.receiverLength", receiverLength)
        self.__client.initPresetValues(presetValues)
        osversion = ""
        try:
            if(self.__executeQuery()):
                sysprops = self.__client.getProperties(["QSZRTVPR.receiver.releaselevel"])
                osversion = sysprops.getProperty("QSZRTVPR.receiver.releaselevel");
                logger.debug("Host OS Version: %s" % osversion);
            else:
                logger.warn("Cannot get host OS version from system.")
        except:
            logger.warn("Cannot get host OS version from system.")
            logger.debugException("")
        return osversion

    def __discoverSysInfo(self): 
        '''
        Gets system information of connected host:
        - hostName
        - model
        - serial number
        - os version
        
        @types AS400Client -> list(str)
        '''
        
        hostName = self.__client.getSystemValue("SYSNAME")
        hostModel = self.__client.getSystemValue("QMODEL")
        hostSerialNum = self.__client.getSystemValue("QSRLNBR")
        logger.debug("Host model is %s" % hostModel)
        logger.debug("Host name is %s" % hostName)
        logger.debug("Host Serial # is %s" % hostSerialNum)
        logger.debug("Getting OS Version...")
        osVersion = self.__getOSVersion()
        sysinfo = SysInfo(hostName, hostModel, hostSerialNum, osVersion)
        return sysinfo;

    ###############################################
    ##  Get the AS400 host information        ##
    ###############################################
    def buildTopology(self):
        '''
        Construct as400 node topology
        @types AS400Client -> ObjectStateHolderVector
        '''
        myvec = ObjectStateHolderVector()
        ip_address = self.__client.getIpAddress()
        # create as400 agent OSH

        interfaceList = self.__interfacesInfo
        as400HostOsh = None
        if interfaceList and len(interfaceList) > 0:
            # Create as400 CIT       
            try: 
                # Get the host_key - lowest mac address of the valid interface list
                as400HostOsh = modeling.createCompleteHostOSHByInterfaceList('as400_node', interfaceList, 'OS400', self.__sysInfo.hostName)
                as400HostOsh.setAttribute('host_model', self.__sysInfo.hostModel)
                as400HostOsh.setAttribute('host_serialnumber', self.__sysInfo.hostSerialNum)
                as400HostOsh.setAttribute('host_osversion', self.__sysInfo.hostOSVersion)
                as400HostOsh.setAttribute('host_vendor', 'IBM')
                myvec.add(as400HostOsh)
                
                as400Osh = self.__createAS400AgentOSH(ip_address)
                as400Osh.setAttribute('credentials_id', self.__client.getCredentialId())
                as400Osh.setContainer(as400HostOsh)
                myvec.add(as400Osh)

            except:
                logger.warn('Could not find a valid MAC addresses for key on ip : ', self.__client.getIpAddress())
       
        # add all interfaces to the host
        if as400HostOsh is not None:
            for interface in interfaceList:
                interfaceOsh = modeling.createInterfaceOSH(interface.macAddress, as400HostOsh, interface.description, interface.interfaceIndex, interface.type, interface.adminStatus, interface.adminStatus, interface.speed, interface.name, interface.alias, interface.className)
                ips = interface.ips
                masks = interface.masks
                if interfaceOsh:
                    myvec.add(interfaceOsh)
                    if ips and masks:
                        for i in xrange(len(ips)):
                            ipAddress = ips[i]
                            ipMask = masks[i]

                            ipProp = modeling.getIpAddressPropertyValue(ipAddress, ipMask, interface.dhcpEnabled, interface.description)
                            ipOSH = modeling.createIpOSH(ipAddress, ipMask, ipProp)
                            myvec.add(ipOSH)
                            
                            myvec.add(modeling.createLinkOSH('containment', as400HostOsh, ipOSH))
                            netOSH = modeling.createNetworkOSH(ipAddress, ipMask)   
                            myvec.add(netOSH)
                            
                            myvec.add(modeling.createLinkOSH('member', netOSH, as400HostOsh))
                            myvec.add(modeling.createLinkOSH('member', netOSH, ipOSH))
                            myvec.add(modeling.createLinkOSH('containment', interfaceOsh, ipOSH))
        else:
            logger.warn('Parent host wasn\'t created. No interfaces will be reported.')
        return myvec

    def __createAS400AgentOSH(self, ip_address):
        '''
        @types str->ObjectStateHolder 
        '''
        as400Osh = ObjectStateHolder('as400')
        as400Osh.setAttribute('application_ip', ip_address)
        as400Osh.setAttribute('data_name', 'as400')
        return as400Osh
    
    def __debugAS400Messages(self):
        messages = self.__client.getMessages()
        if messages is not None and messages.size() > 0:
            logger.debug("AS400 Messages:")
            for msg in messages:
                logger.warn("\t%s" % msg)
        else:
            logger.debug("AS400 Messages: <Empty>")

class SysInfo:
    def __init__(self, hostName, hostModel, hostSerialNum, hostOSVersion):
        if hostName is None:
            raise IllegalArgumentException("Host name cannot be null")
        self.hostName = hostName
        self.hostModel = hostModel
        self.hostSerialNum = hostSerialNum
        self.hostOSVersion = hostOSVersion

    def __repr__(self):
        return "SysInfo[HostName: %s, HostModel: %s, SerialNumber: %s, OSVersion: %s]" % (self.hostName, self.hostModel, self.hostSerialNum, self.hostOSVersion)

class NetworkInfo:
    '''
        Data Object Class to save network information 
    '''
    def __init__(self, ip, netArray=None, interfaceName = None, interfaceDescr=None, mask=None):
        '''
        @types str, str, str, str
        @raise IllegalArgumentException: if ip is None  
        '''
        if ip is None:
            raise IllegalArgumentException("IP cannot be null")
        self.ip = ip
        self.netArray = netArray
        self.interfaceDescr = interfaceDescr
        self.interfaceName = interfaceName
        self.mask = mask
        
    def __repr__(self):
        return "NetworkInfo[ip: %s, network: %s, mask: %s, interfaceDescr: %s, interfaceName: %s]" % (self.ip, self.netArray, self.mask, self.interfaceDescr, self.interfaceName)

def isIpInList(networkList, ip):
    '''
    Check if ip is include to the network
    @types list(NetworkInfo), str -> bool
    '''
    for networkInfo in networkList:
        if networkInfo.ip == ip: 
            return 1
    return 0


def processException(errorsList, warnList, msg = None): 
    excInfo = logger.prepareJythonStackTrace('')
    logger.error('AS400 Discovery Exception: <%s>' % excInfo)
    if msg:
        excInfo = msg
    else:
        excInfo = str(sys.exc_info()[1])
    errormessages.resolveAndAddToObjectsCollections(excInfo, protocolName, warnList, errorsList)

def reportErrors(warningsList, errorsList):
    for errobj in warningsList:
        logger.reportWarningObject(errobj)
    for errobj in errorsList:
        logger.reportErrorObject(errobj)
    return


############################
#    MAIN
############################
def DiscoveryMain(Framework): 
    warningsList = []
    errorsList = []
    oshvector = ObjectStateHolderVector()
    errobj = errorobject.INTERNAL_ERROR
    client = None

    ip_address = Framework.getDestinationAttribute('ip_address')
    ip_domain = Framework.getDestinationAttribute('ip_domain')
    credentials = netutils.getAvailableProtocols(Framework, protocolName, ip_address, ip_domain)  
  
    if len(credentials) == 0:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        warningsList.append(errobj)
        logger.debug(msg)
    else: 
        try:
            logger.info('Starting AS400 Connection.')
            for credential in credentials:
                client = Framework.createClient(credential)
                dicoverer = AS400Dicoverer(client)
                dicoverer.discover()
                oshvector.addAll(dicoverer.buildTopology())
        except NoClassDefFoundError, error:
            # Trying to catch if as400 java package is not found
            msg = error.getMessage()
            if re.search("as400", msg, re.I):
                processException(errorsList,warningsList,"Third party library is not found. Please read the documentation about prerequisites for this job.")
            else:
                processException(errorsList,warningsList, msg)
        except:
            processException(errorsList,warningsList)
        
    if client:
        client.close()
    logger.info('Finished AS400 Connection.')
    reportErrors(warningsList, errorsList)
    return oshvector

