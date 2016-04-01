#coding=utf-8
# 
# iSeries Resource Discovery by Eview
#
# Created on Aug 20 , 2011
#
# @author: podom
#
# CP10 -  Initial version 
# CP10 Cup 1   Fixed CR 70111 Traceback becuase missing module Netlinks_Services

 
import string, re, logger, modeling
import eview400_lib 
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Date
from eview400_lib import isNotNull, isNull
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from string import upper, lower
from modeling import _CMDB_CLASS_MODEL

# Variables  
global Framework
PARAM_HOST_ID = 'hostId'
PARAM_LPAR_NAME = 'LparName'
global knownPortsConfigFile

TCP_PORT_TYPE_ENUM = 1
UDP_PORT_TYPE_ENUM = 2

_CMD_DSPHDWRC_PROCESSOR = 'DSPHDWRSC Type(*PRC)'
_CMD_SYSVAL_QMODEL  = 'DSPSYSVAL SYSVAL(QMODEL)'
_CMD_SYSVAL_QSRLNBR  = 'DSPSYSVAL SYSVAL(QSRLNBR)'
_CMD_ETHERNET = 'ETHERNET'
_CMD_SUBSYSTEM = ''
_CMD_ASP = ''
_CMD_DISK = ''
_CMD_TCP = ''
_CMD_DSPSFWRSC ='DSPSFWRSC'

# Classes  
class DevLink:
    devName = ''
    devType = ''
    linkName = ''
    linkType = ''
    linkStatus = ''
    linkMac = ''
    def __init__(self, devName, devType, linkName, linkType, linkStatus, linkMac):
        self.devName = devName
        self.devType = devType
        self.linkName = linkName
        self.linkType = linkType
        self.linkStatus = linkStatus
        self.linkMac = linkMac

# Methods  

def appendToList(originalList, newList):
    tempList = []
    if isNull(originalList):
        originalList = tempList
    for val in newList:
        if isNotNull(val):
            originalList.append(val)
    return originalList

def appendToDictionary(originalDict, newDict):
    dict = {}
    if isNull(originalDict):
        originalDict = dict
    for (x, y) in newDict.items():
        if isNotNull(y) and not originalDict.has_key(x):
            originalDict[x] = y
    return originalDict



# EView Command Execution Methods 

def ev1_getCpulistOutput(ls):
    cpuTable = None
    cecTable = None 
    memTable = None
    output = ls.evClCmd(_CMD_DSPHDWRC_PROCESSOR)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        cpuTable = output.getRegexedValuesFromList(output.cmdResponseList, 'MP(\d+)\s+(\w+-\w+)\s+(\w+-\w+)') 
        cecTable = output.getRegexedValuesFromList(output.cmdResponseList, '(CEC\d+)\s+(\w+-\w+)\s+(\w+-\w+)')
        memTable = output.getRegexedValuesFromList(output.cmdResponseList, 'MS\d+.*\s(\d+)MB MAIN STORAGE CARD')
        
    return cpuTable, cecTable, memTable


def ev2_getTCPStack(ls):  
    # Get IP Information-----------------------------------------------
    ipDict = {}
    maclist = []
    output = ls.evApiCmd(_CMD_ETHERNET,'41')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                ipDict[splitline[6].strip()] = splitline
                maclist.append (splitline[6].strip())
    maclist.sort()
    primaryIP = ipDict[maclist[0]][0].strip()
    return ipDict, primaryIP

def ev3_getSubsystemOutput(ls):
    # process Subsystem List ----------------------------------------------------------
    
    ssiList = [] # [Name,  Library, Max Jobs, Active Jobs, Description]
    output = ls.evApiCmd(_CMD_SUBSYSTEM,'04')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                ssiList.append (splitline)
    return ssiList
  
def ev4_getAspandDisk(ls):
    # process ASPs ----------------------------------------------------------
    # [ASP Number, Number Disks, ASP Capacity in MB, ASP Avail in MB, ASP Protected in MB, 
    # ASP Avail Protected in MB, ASP Capacity unprotected in MB, ASP Avail unprotected in MB,
    # ASP System Storage, Overflow Storage in  MB, Space allocated to error log, 
    # space allocated to machine log, space allocated to machine trace, 
    
    ASPList = [] 
    DiskList = []                
    output = ls.evApiCmd(_CMD_ASP,'31')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                ASPList.append (splitline)
    output = ls.evApiCmd(_CMD_DISK,'34')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                DiskList.append (splitline)            
    return ASPList , DiskList
  
def ev5_getInstalledSoftware(ls):
    # process LISTPROD ---------------------------------------------------------
    prodLists = []   # [Product ID, Feature, , Type, Library, Release, Description]
    headerColumns = ['ID','OPTION','FEATURE','TYPE','LIBRARY','RELEASE','DESCRIPTION']
    tableBeginPattern = 'RESOURCE'
    tableEndPattern = '* * * * *   E N D   O F   C O M P U T E R   P R I N T O U T   * * * * *'
    firstColumnPaddingChar = ''
    includeRegexPattern = ''
    ignorePatterns = ['SOFTWARE RESOURCES LIST','PAGE']
    output = ls.evClCmd(_CMD_DSPSFWRSC)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        prods = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(prods)):
            if (prods[i][0]  in ['RESOURCE','ID','5722SS1 V']):
                continue 
            prodLists.append([prods[i][0], prods[i][1], prods[i][2], prods[i][3],prods[i][4],prods[i][5],prods[i][6] ])   
    return prodLists 



def ev6_getTcpConnOutput(ls):
    connections = []
    
    output = ls.evApiCmd(_CMD_TCP,'42')
    if output.isSuccess() and len(output.cmdResponseList) > 0:     
        #connectionentry = [remote addr,remote port,local addr, local port, type, user, idlse time, bytes in, bytes out, conn status, jobs ]
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                connections.append (splitline)
                logger.debug (splitline)
   
    return  connections



''' OSHV Creation Methods '''



def osh_createIBMframeOsh(lparOsh ,cecTable):
    str_name = 'name'    
    str_discovered_model = 'discovered_model'
    str_serial_number = 'serial_number'     
    isComplete = 1 
    _vector = ObjectStateHolderVector()
    cecOsh = ObjectStateHolder('ibm_pseries_frame')                          # iSeries CEC
    cecOsh.setAttribute(str_name, 'CEC'+cecTable[0][2])                            
    cecOsh.setBoolAttribute('host_iscomplete', isComplete)
    cecOsh.setAttribute( str_discovered_model, cecTable[0][1])                  # CPC SI    
    cecOsh.setAttribute('host_key', cecTable[0][2])
    cecOsh.setAttribute( str_serial_number , cecTable[0][2])   
    str_membership = 'membership'        
    membershipOsh = modeling.createLinkOSH(str_membership, cecOsh, lparOsh)
    _vector.add(cecOsh)
    _vector.add(lparOsh)
    _vector.add(membershipOsh)
    return _vector

def osh_createCpuOsh(lparOsh, cpuLists):
    _vector = ObjectStateHolderVector()    
    for cpu in cpuLists:        
        if isNotNull(cpu[0]):
            cpuOsh = ObjectStateHolder('cpu')                      
            cpuOsh.setAttribute('cpu_id', cpu[0])
            cpuOsh.setAttribute('cpu_vendor', 'IBM')
            cpuOsh.setAttribute('serial_number', cpu[2])
            cpuOsh.setAttribute('cpu_type', cpu[1])
            cpuOsh.setContainer(lparOsh)
            _vector.add(cpuOsh)
    return _vector

def osh_updateMemOsh(lparOsh, memTable):
    _vector = ObjectStateHolderVector()
    memTotal = 0
    for entry in memTable:
        mem = entry[0]
        memTotal = memTotal + int(mem)
    lparOsh.setAttribute('memory_size',int(memTotal))
    _vector.add(lparOsh)
    return _vector

def osh_createIpOsh(lparOsh, tcpStacks):
    
    ipstoexclude = ['127.0.0.1']
    # tcpStacks  [ip, network, mask, interface name, status, type, mac address]str_name = 'name'    
    str_name = 'name'
    str_mac_address = 'mac_address'
    _vector = ObjectStateHolderVector()
    for mac, tcpentry in tcpStacks.items():
        ipAddress = tcpentry[0].strip()
        if ipAddress not in ipstoexclude:       
            ipOsh = modeling.createIpOSH(ipAddress)
            probeName = CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME) 
            if isNotNull(probeName):
                ipOsh.setAttribute('ip_probename', probeName)   
                containedOsh = modeling.createLinkOSH('contained', lparOsh, ipOsh)         
            _vector.add(lparOsh)
            _vector.add(ipOsh)
            _vector.add(containedOsh)
         
            # create interface ----------------------------------------------------
        
            ifOsh = ObjectStateHolder('interface')
            interfacename = tcpentry[3].strip()
            ifOsh.setAttribute(str_name,  interfacename)       
            # default the mac address attribute to linkName and update later if MAC found 
            ifOsh.setAttribute(str_mac_address, mac) # if MAC not found for set #linkName as key       
            ifOsh.setContainer(lparOsh)
            _vector.add(ifOsh)
            if tcpStacks.has_key(mac):
                parentLinkOsh = modeling.createLinkOSH('containment', ifOsh, ipOsh)
                _vector.add(parentLinkOsh)
    return _vector

def osh_createNetworkOsh(lparOsh, tcpStacks):
    # tcpStacks  [ip, network, mask, interface name, status, type, mac address]
    _vector = ObjectStateHolderVector()
    for mac, tcpentry in tcpStacks.items():
        networkAddress = tcpentry[1].strip()
        ipAddress = tcpentry[0].strip()
        mask = tcpentry[2].strip()
        ipOsh = modeling.createIpOSH(ipAddress)
        netOsh = modeling.createNetworkOSH(networkAddress, mask)        
        memberOsh = modeling.createLinkOSH('membership', netOsh, lparOsh)         
        _vector.add(lparOsh)
        _vector.add(netOsh)
        _vector.add(memberOsh)
        memberOsh = modeling.createLinkOSH('membership',  netOsh, ipOsh)
        _vector.add(memberOsh)          
    return _vector
def osh_createSubsystemsOsh(lparOsh, ssiList):
    
    # ssi   [Name,  Library, Max Jobs, Active Jobs, Description]
    str_name = 'name'
    str_discovered_product_name = 'discovered_product_name'
    str_description = 'description'
    str_actjobs = 'active_jobs'
    _vector = ObjectStateHolderVector()
    if isNotNull(ssiList):
        for ssi in ssiList:
            if isNotNull(ssi[0]):
                ssOsh = ObjectStateHolder('iseriessubsystem')
                ssOsh.setAttribute(str_name,ssi[0].strip())
                ssOsh.setAttribute(str_discovered_product_name ,ssi[0].strip())
                ssOsh.setAttribute(str_description,ssi[4].strip())
                ssOsh.setAttribute(str_actjobs,int(ssi[3]))
                ssOsh.setContainer(lparOsh)
                _vector.add(ssOsh)
    return _vector

def osh_createASPOsh(lparOsh, ASPList, DiskList):
    
    spDict = {}     
    str_name = 'name'
    str_storagepool_poolid = 'storagepool_poolid'
    str_storagepool_mbavailable = 'storagepool_mbavailable'
    str_storagepool_mbtotal = 'storagepool_mbtotal'
    str_storagepool_capacitynum = 'storagepool_capacitynum'  
    str_serial_number = 'serial_number'
    str_logicalvolume_fstype = 'logicalvolume_fstype'
    str_logicalvolume_id = 'logicalvolume_id'
    str_logicalvolume_free = 'logicalvolume_free'
    str_logicalvolume_size = 'logicalvolume_size'
    _vector = ObjectStateHolderVector()
    if isNotNull(ASPList):
        for asp in ASPList:
            if isNotNull(asp[0]):
                aspname = ('ASP' + asp[0])
                spOsh = ObjectStateHolder('storagepool')
                spOsh.setAttribute(str_name, aspname )                
                spOsh.setIntegerAttribute(str_storagepool_poolid, int(asp[0]))
                spOsh.setDoubleAttribute(str_storagepool_mbavailable, asp[3])
                spOsh.setDoubleAttribute(str_storagepool_mbtotal, asp[2])
                spOsh.setIntegerAttribute(str_storagepool_capacitynum, asp[1])
                spOsh.setContainer(lparOsh)
                spDict[asp[0]] = spOsh
                _vector.add(spOsh)
    if isNotNull(DiskList):
        for disk in DiskList:
            if isNotNull(disk[0]):
                aspid =  disk[0]
                diskOsh = ObjectStateHolder('logical_volume')
                diskOsh.setAttribute(str_name, disk[4])
                diskOsh.setAttribute(str_serial_number, disk[3])
                diskOsh.setAttribute(str_logicalvolume_fstype, disk[1])                                
                diskOsh.setIntegerAttribute(str_logicalvolume_id, int(disk[5]))
                diskOsh.setDoubleAttribute(str_logicalvolume_free, disk[7])
                diskOsh.setDoubleAttribute(str_logicalvolume_size, disk[6])                
                diskOsh.setContainer(lparOsh)
                _vector.add(diskOsh)
                if spDict.has_key(aspid):                   
                    memberOsh = modeling.createLinkOSH('membership', spDict[aspid], diskOsh) 
                    _vector.add(memberOsh)                        
    return _vector


def osh_createSoftwareOsh(lparOsh, prodLists): 
    str_name = 'name'
    str_description = 'description'
    str_version = 'version'
    str_software_type = 'software_type'    
    str_software_productid = 'software_productid'
    str_discovered_vendor = 'software_vendor'   
    _vector = ObjectStateHolderVector()
    if len(prodLists) > 0:
        for prod in prodLists:    
            swOsh = None
            swOsh = ObjectStateHolder('installed_software')
            swOsh.setAttribute(str_name , prod[0]+'-'+prod[1]+'-'+prod[2]) # Name
            swOsh.setAttribute(str_description ,prod[6])
            swOsh.setAttribute(str_version,prod[5])
            swOsh.setAttribute(str_software_type,prod[3])
            swOsh.setAttribute(str_software_productid,prod[0])
            swOsh.setContainer(lparOsh)
            _vector.add (swOsh)
    return _vector



def osh_createTcpConnectionsOsh(lparOsh,  primaryIP, knownPortsConfigFile, connections):
    str_containment = 'containment'
    _vector = ObjectStateHolderVector()
    
    ignoreLocalConnections = 0 ## ER: parameterize

    probeName = CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME)
    
    for conn in connections:
        dstPort = ''
        dstAddr = ''
        srcAddr = ''
        srcPort = ''
        
        id = conn[5]
        #(dstAddr, dstPort) = _getIpPortFromSocket(localSocket, primaryIP)
        dstAddr = conn[2].strip()
        if dstAddr == '0.0.0.0' or dstAddr == '127.0.0.1':
            dstAddr = primaryIP.strip()
        dstPort = conn[3].strip()
        state = conn[9].strip()        
            
        
        
        
        #(srcAddr, srcPort) = _getIpPortFromSocket(foreignSocket, primaryIP)
        if upper(state) == 'ESTABLISH':
            srcAddr = conn[0].strip()
            srcPort = conn[1].strip()
        if srcAddr == '127.0.0.1':
            srcAddr = primaryIP.strip()
                
            
        if ignoreLocalConnections and (srcAddr == dstAddr):
            continue
            
        if isNotNull(dstAddr):
            destination = '%s:%s' % (dstAddr, dstPort)
            logger.debug('[', state, '] Current connection: ', srcAddr, ' -> ', destination)
                
            # create destination (server) IP and Host --------------------------
            dstIpOsh = modeling.createIpOSH(dstAddr)
            if isNotNull(probeName):
                dstIpOsh.setAttribute('ip_probename', probeName)
            dstHostOsh = None
            if isNotNull(lparOsh):
                dstHostOsh = lparOsh
            else:
                dstHostOsh = modeling.createHostOSH(dstAddr)
            dstContainedLinkOsh = modeling.createLinkOSH(str_containment, dstHostOsh, dstIpOsh)
            _vector.add(dstIpOsh)
            _vector.add(dstHostOsh)
            _vector.add(dstContainedLinkOsh)
                
            # create destination service address object ------------------------
            portTypeEnum =  TCP_PORT_TYPE_ENUM
            portName = knownPortsConfigFile.getTcpPortName(int(dstPort))
            if upper(state) == 'UDP':
                portTypeEnum =  UDP_PORT_TYPE_ENUM            
                portName = knownPortsConfigFile.getUdpPortName(int(dstPort))
            if isNull(portName):
                portName = dstPort
            serverPortOsh = modeling.createServiceAddressOsh(dstHostOsh, dstAddr, int(dstPort), portTypeEnum, portName)
            _vector.add(serverPortOsh)
    
            if isNotNull(srcAddr):
                # create source (client) IP and Host ---------------------------
                srcIpOsh = modeling.createIpOSH(srcAddr)
                if isNotNull(probeName):
                    srcIpOsh.setAttribute('ip_probename', probeName)
                srcHostOsh = modeling.createHostOSH(srcAddr)
                srcContainedLinkOsh = modeling.createLinkOSH(str_containment, srcHostOsh, srcIpOsh)
                _vector.add(srcIpOsh)
                _vector.add(srcHostOsh)
                _vector.add(srcContainedLinkOsh)
                    
                # create client-server links -----------------------------------
                _vector.add(_createClientServerLinkOsh(dstPort, serverPortOsh, portName, lower(state), srcIpOsh))
                    
                # create client server dependency links ------------------------
                _vector.add(_createClientServerDependencyLinkOsh(dstHostOsh, dstPort, srcHostOsh, portName))
    return _vector


def _createClientServerDependencyLinkOsh(serverHostOSH, serverPort, clientHostOsh, portName):
    str_dependency = 'node_dependency'

    nodeDependencyLinkOsh = modeling.createLinkOSH(str_dependency, clientHostOsh, serverHostOSH)
    nodeDependencyLinkOsh.setAttribute('dependency_name', serverPort)
    nodeDependencyLinkOsh.setAttribute('dependency_source', portName)
    return nodeDependencyLinkOsh

def _createClientServerLinkOsh(serverPort, serverPortOsh, portName, portType, clientIpOsh):
    str_client_server = 'client_server'
    str_name = 'name'

    csLinkOsh = modeling.createLinkOSH(str_client_server, clientIpOsh, serverPortOsh)
    csLinkOsh.setStringAttribute('clientserver_protocol', portType)
    csLinkOsh.setStringAttribute(str_name, portName)
    csLinkOsh.setLongAttribute('clientserver_destport', int(serverPort))
    return csLinkOsh

def processiSeriesResources(ls, lparOsh, knownPortsConfigFile, Framework):
    
    # Process LPAR iSeries Resources 
    _vector = ObjectStateHolderVector()
    
    #===========================================================================
    # Run commands and create OSHs
    #===========================================================================
    (cpuLists ,cecTable, memTable) = ev1_getCpulistOutput(ls)
    # If we don't get output then the Iseries command failed and we need to get out
    if isNull (cpuLists):
        return _vector
    ''' Create IBM Frame OSH '''
    
    _vector.addAll(osh_createIBMframeOsh(lparOsh ,cecTable))
     
    # CPU List Command ---------------------------------------------------------
     
    ''' Create CPU OSH '''
    createCpu = Framework.getParameter('discover_CPUs')
    if isNotNull(createCpu) and string.lower(createCpu) == 'true':     
        _vector.addAll(osh_createCpuOsh(lparOsh, cpuLists))
        
    ''' Update the memory in the lpar OSH'''   
         
    _vector.addAll(osh_updateMemOsh(lparOsh, memTable))
    
    ''' TCPIP Stacks Command '''
    tcpStacks, primaryIP = ev2_getTCPStack(ls)    
 
    # Create IP OSHs ------------------------------------------------------------
    
    _vector.addAll(osh_createIpOsh(lparOsh, tcpStacks))
    
    # Create Network OSHs ------------------------------------------------------------
    
    _vector.addAll(osh_createNetworkOsh(lparOsh, tcpStacks))
    
    # Discover Subsystems -------------------------------------------------------
    
    createSubsystem = Framework.getParameter('discover_Subsystems')
    if isNotNull(createSubsystem) and string.lower(createSubsystem) == 'true':      
        ssiList = ev3_getSubsystemOutput(ls)            
        _vector.addAll(osh_createSubsystemsOsh(lparOsh, ssiList))
    

    # Discover Auxillary Storage Pools and Disks------------------------------------------------------
    
    createASP = Framework.getParameter('discover_ASP')
    if isNotNull(createASP) and string.lower(createASP) == 'true':      
        aspList, diskList = ev4_getAspandDisk(ls)       
        _vector.addAll(osh_createASPOsh(lparOsh, aspList, diskList))
     
      
 
    createSoftware = Framework.getParameter('discover_Software')
    if isNotNull(createSoftware) and string.lower(createSoftware) == 'true':
    
        prodLists = ev5_getInstalledSoftware(ls)   
        
        ''' Create Iseries Software CIs '''
        _vector.addAll(osh_createSoftwareOsh(lparOsh, prodLists))
        
    createTCP = Framework.getParameter('discover_TCP_UDP')
    if isNotNull(createTCP) and string.lower(createTCP) == 'true':
        connections = ev6_getTcpConnOutput(ls)
                  
        ''' Create Iseries Connection CIs '''
        _vector.addAll(osh_createTcpConnectionsOsh(lparOsh, primaryIP, knownPortsConfigFile, connections))

    
    return _vector

#######
# MAIN
#######

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()   
    knownPortsConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
    # create LPAR node
    lparName = Framework.getDestinationAttribute(PARAM_LPAR_NAME)
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    lparOsh = None
    if eview400_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)
    
    ls = eview400_lib.EvShell(Framework)
    (hostResourcesOshv) = processiSeriesResources(ls, lparOsh, knownPortsConfigFile, Framework)
    OSHVResult.addAll(hostResourcesOshv)
    
    ls.closeClient()
  
    return OSHVResult