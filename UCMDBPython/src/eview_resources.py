# 
# Host Resource Discovery by Eview
#
# Created on Sep 20, 2010
#
# @author: kchhina
#
# CP8 -  Intial version 
# CP9 -  Added Dasd storage discovery for CP9 March 31,2011 podom
# CP9 -  Added FORMAT=SHORT and MAX=* to commands for defects to force the output of the commands podom
# CP10 - Changed script to support LONG format returned from Network commands on IPV6 enabled systems  QCCR1H38586 podom 
# CP10 - Fixed QCCR1H38525 - Duplicate Software CIs in Bulk  
# CP10 - Fixed QCCR1H6397 - Empty Volume Group causes failure on Volume Group Discovery
# CP10 - Add Job Discovery
# CP10 - CUP 1 to fix urget issue with Netlinks module being depricated.
# CP12 - Discovery CPU types of ZIIP and ZAAP processor and set CPU type attribute
# CP15 - Change Jobs Discovery to not discover time sharing users.  TSU type was incorrectly added as a Job. 
# Cp15 - Change interface discovery to add LPAR name to Linkname.  This will prevent duplicate interfaces if MAC not available. QCIM1H94721

import string, re, logger, modeling
import eview_lib
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from eview_lib import isNotNull, isnumeric, isNull
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from string import upper, lower
 
from modeling import _CMDB_CLASS_MODEL
import eview_netutils

''' Variables '''
global Framework
PARAM_HOST_ID = 'hostId'
PARAM_LPAR_NAME = 'LparName'
global knownPortsConfigFile

TCP_PORT_TYPE_ENUM = 1
UDP_PORT_TYPE_ENUM = 2

_CMD_D_SYMBOLS = 'D SYMBOLS'
_CMD_D_M_CPU = 'D M=CPU'
_CMD_D_TCPIP = 'D TCPIP'
_CMD_TCPIP_NETSTAT_HOME = 'D TCPIP,%s,NETSTAT,HOME,FORMAT=LONG'
_CMD_D_SSI = 'D SSI'
_CMD_D_NET_MAJNODES = 'D NET,MAJNODES,MAX=*'
_CMD_D_ASM = 'D ASM'
_CMD_D_PROD_STATE = 'D PROD,STATE'
_CMD_D_PROD_REGISTERED = 'D PROD,REGISTERED'
_CMD_D_XCF_GRP = 'D XCF,GRP'
_CMD_D_XCF_GRP_ALL = 'D XCF,GRP,%s,ALL'
_CMD_D_TCPIP_NETSTAT_CONN = 'D TCPIP,%s,NETSTAT,CONN,FORMAT=LONG,MAX=*'
_CMD_D_TCPIP_NETSTAT_ROUTE = 'D TCPIP,%s,NETSTAT,ROUTE,FORMAT=LONG'
_CMD_D_TCPIP_NETSTAT_DEV = 'D TCPIP,%s,NETSTAT,DEV,FORMAT=LONG'
_CMD_D_TCPIP_NETSTAT_ARP = 'D TCPIP,%s,NETSTAT,ARP,FORMAT=LONG,MAX=*'
_CMD_I_DASD = '*'

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

''' Methods '''

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

def getCpuStatus(cpuStatusSymbol):
    cpuStatus = ''
    if isNotNull(cpuStatusSymbol):
        #Spencer: CPU status could be a multi-character string
        cpuStatusSymbol = cpuStatusSymbol[0]
        
        if cpuStatusSymbol == '+':
            cpuStatus = 'ONLINE'
        elif cpuStatusSymbol == '-':
            cpuStatus = 'OFFLINE'
        elif cpuStatusSymbol == '.':
            cpuStatus = 'DOES NOT EXIST'
        elif cpuStatusSymbol == 'W':
            cpuStatus = 'WLM-MANAGED'
        elif cpuStatusSymbol == 'N':
            cpuStatus = 'NOT AVAILABLE'
    return cpuStatus

def processXcfGroups(xcfGroupsList):
    list = []
    for xcfGroupLists in xcfGroupsList:
        for xcfGroup in xcfGroupLists:
            # get the group name and the number of members ---------------------
            match = re.match('(.*)\((\d*)\)', xcfGroup)
            if match:
                groupName = match.group(1)
                memberCount = match.group(2)
                list.append([groupName, memberCount])
    return list


''' EView Command Execution Methods '''
def ev2_getSymlistOutput(ls):
    # process SYMLIST ----------------------------------------------------------
    symbolsMap = {} # {name:value}
    output = ls.evMvsCmd(_CMD_D_SYMBOLS)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        symbolsList = output.getValuesFromLineList('s', output.cmdResponseList, '&', '\.\s+=\s+"', '"')
        for symbols in symbolsList:
            if len(symbols) == 4:
                symbolName = symbols[1]
                symbolValue = symbols[2]
                if isNotNull(symbolName) and isNotNull(symbolValue):
                    symbolsMap[symbolName] = symbolValue
    return symbolsMap

def ev3_getCpulistOutput(ls):
    cpuLists = [] # [CPU ID, CPU STATUS, CPU SERIAL, CPU RAW STATUS]
    cpcSi = ''
    cpcName = ''
    cpcId = ''
    lpName = ''
    lpId = ''
    output = ls.evMvsCmd(_CMD_D_M_CPU)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        # first search for CPUs ------------------------------------------------
        headerColumns = ['ID', 'CPU', 'SERIAL']
        tableBeginPattern = 'PROCESSOR STATUS'
        tableEndPattern = 'CPC ND ='
        firstColumnPaddingChar = ''
        includeRegexPattern = ''
        ignorePatterns = []
        cpuTable = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(cpuTable)):
            # Spencer: Add the raw entry for the status to the cpuLists array
            cpuLists.append([cpuTable[i][0], getCpuStatus(cpuTable[i][1]), cpuTable[i][2], cpuTable[i][1]])
        
        # then search for CPC SI -----------------------------------------------
        cpcSiList = output.getValuesFromLineList('s', output.cmdResponseList, 'CPC SI =')
        if isNotNull(cpcSiList) and len(cpcSiList) > 0 and isNotNull(cpcSiList[0][1]):
            cpcSi = cpcSiList[0][1]
        
        # then search for CPC ID -----------------------------------------------
        cpcIdList = output.getValuesFromLineList('s', output.cmdResponseList, 'CPC ID =')
        if isNotNull(cpcIdList) and len(cpcIdList) > 0 and isNotNull(cpcIdList[0][1]):
            cpcId = cpcIdList[0][1]
        
        # then search for CPC Name ---------------------------------------------
        cpcNameList = output.getValuesFromLineList('s', output.cmdResponseList, 'CPC NAME =')
        if isNotNull(cpcNameList) and len(cpcNameList) > 0 and isNotNull(cpcNameList[0][1]):
            cpcName = cpcNameList[0][1]
        
        # finally search for LP NAME and LP ID ---------------------------------
        lpList = output.getValuesFromLineList('s', output.cmdResponseList, 'LP NAME =', 'LP ID =')
        if isNotNull(lpList) and len(lpList) > 0 and isNotNull(lpList[0][1]):
            lpName = lpList[0][1]
        if isNotNull(lpList) and len(lpList) > 0 and isNotNull(lpList[0][2]):
            lpId = lpList[0][2]
    return (cpuLists, cpcSi, cpcId, cpcName, lpId, lpName)

def ev4_getTcpStackNameOutput(ls):
    # get the running TCP stacks -----------------------------------------
    tcpStackList = []
    output = ls.evMvsCmd(_CMD_D_TCPIP)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        headerColumns = ['COUNT', 'TCPIP NAME', 'VERSION', 'STATUS']
        tableBeginPattern = 'EZAOP50I TCPIP STATUS REPORT'
        tableEndPattern = 'END TCPIP STATUS REPORT'
        firstColumnPaddingChar = ' '
        includeRegexPattern = ''
        ignorePatterns = ['------']
        stacks = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(stacks)):
            if len(stacks[i]) == 4 and isNotNull(stacks[i][1]):
                tcpStackList.append(stacks[i][1])
    return tcpStackList

def ev5_getHomelistOutput(ls, tcpStack):
    # process HOMELIST ---------------------------------------------------------
    homeLists = [] # [ADDRESS, LINK, FLG] 
    homelistentry = []
    complete = 0  
    output = ls.evMvsCmd(_CMD_TCPIP_NETSTAT_HOME % tcpStack)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for i in range(len(output.cmdResponseList)):                          
            retVal = output.getValuesFromLine('s', output.cmdResponseList[i], 'LINKNAME:')           
            if len(retVal) > 0 and isNotNull(retVal[1]):
                linkname = retVal[1]
                complete = 1
                continue
            retVal = output.getValuesFromLine('s', output.cmdResponseList[i], 'ADDRESS:')           
            if len(retVal) > 0 and isNotNull(retVal[1]):
                address = retVal[1]
                if eview_netutils._isValidIp (address): 
                    complete = 1
                else:
                    address = None
                continue
            retVal = output.getValuesFromLine('s', output.cmdResponseList[i], 'FLAGS:')            
            if len(retVal) > 0 and isNotNull(retVal[1]):
                flags = retVal[1] 
                complete = 1              
            else:
                flags = ' '                 
            if complete:      
                homelistentry = [address, linkname, flags]
                homeLists.append (homelistentry)
                complete = 0
    return homeLists

def ev6_getSsilistOutput(ls):
    # process SSILIST ----------------------------------------------------------
    ssiList = [] # [Name, Dynamic, Status, Commands]
    output = ls.evMvsCmd(_CMD_D_SSI)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        # first get the subsystem names from alternate lines -------------------
        ssiListOutput = output.getRegexedValuesFromList(output.cmdResponseList, '^SUBSYS=(.*)$')
        # then get the subsystem parameters from alternate lines ---------------
        ssiParamList = output.getValuesFromLineList('s', output.cmdResponseList, 'DYNAMIC=', 'STATUS=', 'COMMANDS=')
        if len(ssiListOutput) == len(ssiParamList): # TODO change this condition to something more air tight
            for i in range(len(ssiListOutput)):
                if isNotNull(ssiListOutput[i][0]):
                    ssiList.append([ssiListOutput[i][0], ssiParamList[i][1], ssiParamList[i][2], ssiParamList[i][3]])
    return ssiList

def ev7_getMajorNodesOutput(ls):
    # process MAJOR NODES ------------------------------------------------------
    majorNodesLists = []  # [Name, Type, Status]
    output = ls.evMvsCmd(_CMD_D_NET_MAJNODES)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        majNodeList = output.getValuesFromLineList('s', output.cmdResponseList, '\S+\s(\S+)', 'TYPE =', ',')
        for majNodes in majNodeList:
            if len(majNodes) == 5:
                majorNodesLists.append([majNodes[1], majNodes[3], majNodes[4]])
    return majorNodesLists
    
def ev8_getPagelistOutput(ls):
    # process PAGE LIST --------------------------------------------------------
    pageLists = []  # [Type, Used, Status, Device, DSN_Name]
    output = ls.evMvsCmd(_CMD_D_ASM)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        pageLists = output.getRegexedValuesFromList(output.cmdResponseList, '^(\S+)\s+(\d+)%\s+(\S+)\s+(\S+)\s+(\S+)$')
    return pageLists

def ev9_getListProdOutput(ls):
    # process LISTPROD ---------------------------------------------------------
    prodLists = []   # [ID, name, feature, version, owner, state]
    headerColumns = ['S', 'OWNER', 'NAME', 'FEATURE', 'VERSION', 'ID']
    tableBeginPattern = 'IFA111I'
    tableEndPattern = ''
    firstColumnPaddingChar = ''
    includeRegexPattern = ''
    ignorePatterns = []
    output = ls.evMvsCmd(_CMD_D_PROD_STATE)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        prods = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(prods)):
            if len(prods[i]) == 6:
                if prods[i][0] != 'D':
                    prodLists.append([prods[i][5], prods[i][2], prods[i][3], prods[i][4], prods[i][1], 'STATE'])

    output = ls.evMvsCmd(_CMD_D_PROD_REGISTERED)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        prods = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(prods)):
            if len(prods[i]) == 6:
                prodLists.append([prods[i][5], prods[i][2], prods[i][3], prods[i][4], prods[i][1], 'REGISTERED'])
    return prodLists

def ev10_getXcfGroupOutput(ls):
    groups = []
    output = ls.evMvsCmd(_CMD_D_XCF_GRP)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        # get the groups from the first line -----------------------------------
        xcfGroupsList = output.getRegexedValuesFromList(output.cmdResponseList, ".*\s(\S+\(\d+\))\s+(\S+\(\d+\))\s+(\S+\(\d+\))$")
        groups.extend(processXcfGroups(xcfGroupsList))

        # get the set of three groups ------------------------------------------
        xcfGroupsList = output.getRegexedValuesFromList(output.cmdResponseList, "^(\S+\(\d+\))\s+(\S+\(\d+\))\s+(\S+\(\d+\))$")
        groups.extend(processXcfGroups(xcfGroupsList))

        # get the set of two groups --------------------------------------------
        xcfGroupsList = output.getRegexedValuesFromList(output.cmdResponseList, "^(\S+\(\d+\))\s+(\S+\(\d+\))$")
        groups.extend(processXcfGroups(xcfGroupsList))

        # get the set of single group ------------------------------------------
        xcfGroupsList = output.getRegexedValuesFromList(output.cmdResponseList, "^(\S+\(\d+\))$")
        groups.extend(processXcfGroups(xcfGroupsList))
    return groups

def ev11_getXcfMemberOutput(ls, groupName, xcfGroupsDict):
    output = ls.evMvsCmd(_CMD_D_XCF_GRP_ALL % groupName)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        headerColumns = ['MEMBER NAME:', 'SYSTEM:', 'JOB ID:', 'STATUS:']
        tableBeginPattern = 'INFORMATION FOR GROUP'
        tableEndPattern = 'FOR GROUP'
        firstColumnPaddingChar = ''
        includeRegexPattern = ''
        ignorePatterns = []
        prods = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        for i in range(1, len(prods)):
            if len(prods[i]) == 4:
                if xcfGroupsDict.has_key(groupName):
                    tempList = xcfGroupsDict[groupName]
                    tempList.append(prods[i])
                    xcfGroupsDict[groupName] = tempList
                else:
                    xcfGroupsDict[groupName] = [prods[i]]


def ev12_getTcpConnOutput(ls, tcpProcName):
    connections = []
    connectionentry = []
    output = ls.evMvsCmd(_CMD_D_TCPIP_NETSTAT_CONN % tcpProcName)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        #connectionentry = ['USER ID', 'CONN', 'LOCAL SOCKET', 'FOREIGN SOCKET', 'STATE']
        for line in output.cmdResponseList:
            if (re.search('EZD0101', line) or 
                re.search('USER ID', line)):               
                continue 
            m = re.search('LOCAL SOCKET:\s+(\S+)', line)
            if (m):
                localsocket = m.group(1)
                continue
            m = re.search('FOREIGN SOCKET:\s+(\S+)', line)
            if (m): 
                foreignsocket = m.group(1) 
                connectionentry = [userid, conn,localsocket,foreignsocket,state]
                connections.append (connectionentry)
                continue
            m = re.search('(\S+)\s+(\S+)\s+(\S+)', line)
            if (m):    
                userid = m.group(1) 
                conn = m.group(2) 
                state = m.group(3)
                    
   
    return connections

def ev13_getTcpRouteOutput(ls, tcpProcName):
    routes = []
    output = ls.evMvsCmd(_CMD_D_TCPIP_NETSTAT_ROUTE % tcpProcName)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        headerColumns = ['DESTINATION', 'GATEWAY', 'FLAGS', 'REFCNT', 'INTERFACE']
        tableBeginPattern = 'EZD0101I NETSTAT'
        tableEndPattern = 'RECORDS DISPLAYED'
        firstColumnPaddingChar = ''
        includeRegexPattern = ''
        ignorePatterns = ['IPV4']
        routes = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
    #logger.debug ('Routes == ',routes)
    return routes

def ev14_getTcpDevLinkOutput(ls, tcpProcName):
    linkDevLinkDict = {} # {LINKNAME:DevLink Instance}
    output = ls.evMvsCmd(_CMD_D_TCPIP_NETSTAT_DEV % tcpProcName)
    if isNotNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:
        for i in range(len(output.cmdResponseList)):
            # get device names -------------------------------------------------
            retVal = output.getValuesFromLine('s', output.cmdResponseList[i], 'DEVNAME:', 'DEVTYPE:')
            if len(retVal) == 3:
                # get link names -----------------------------------------------
                j = i + 2
                retVal1 = output.getValuesFromLine('s', output.cmdResponseList[j], 'LNKNAME:', 'LNKTYPE:', 'LNKSTATUS:')
                if len(retVal1) == 4:
                    if isNotNull(retVal1[1]):
                        linkDevLinkDict[retVal1[1]] = DevLink(retVal[1], retVal[2], retVal1[1], retVal1[2], retVal1[3], '')
    return linkDevLinkDict

def ev15_getArpCacheOutput(ls, tcpProcName):
    ipMacDict = {} # {IP:[MAC, LINKNAME]}
    output = ls.evMvsCmd(_CMD_D_TCPIP_NETSTAT_ARP % tcpProcName)
    if isNotNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:
        for i in range(len(output.cmdResponseList)):
            retVal = output.getValuesFromLine('s', output.cmdResponseList[i], 'CACHE FOR ADDRESS')
            if len(retVal) > 0 and isNotNull(retVal[1]):
                j = i + 1 #MAC is on the next line
                retVal1 = output.getValuesFromLine('s', output.cmdResponseList[j], 'INTERFACE:', 'ETHERNET:')
                if len(retVal1) > 0 and isNotNull(retVal1[1]) and isNotNull(retVal1[2]):
                    ipMacDict[retVal[1]] = [retVal1[1], retVal1[2]]
    return ipMacDict


''' OSHV Creation Methods '''

def osh_createSysplexOsh(lparOsh, symbolsMap):
    str_name = 'name'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
        
    _vector = ObjectStateHolderVector()
    sysplexOsh = None
    if symbolsMap.has_key('SYSPLEX'):
        sysplexOsh = ObjectStateHolder('mainframe_sysplex')
        sysplexOsh.setAttribute(str_name, symbolsMap['SYSPLEX'])
        _vector.add(sysplexOsh)
        str_membership = 'membership'
        if _CMDB_CLASS_MODEL.version() < 9:
            str_membership = 'member'
        membershipOsh = modeling.createLinkOSH(str_membership, sysplexOsh, lparOsh)
        _vector.add(lparOsh)
        _vector.add(membershipOsh)
    else:
        logger.warn("No sysplex found")
    
    return (_vector, sysplexOsh)

def osh_createMainframeCpcOsh(lparOsh, cpcSi, cpcId, cpcName, cpuLists):
    str_name = 'name'
    str_node_family = 'node_family'
    str_discovered_model = 'discovered_model'
    str_serial_number = 'serial_number'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
        str_node_family = 'host_servertype'
        str_discovered_model = 'host_model'
        str_serial_number = 'host_serialnumber'
        
    isComplete = 1
    createMainframe = 0
    _vector = ObjectStateHolderVector()
    cpcOsh = ObjectStateHolder('mainframe')                           # Mainframe CPC
    cpcOsh.setAttribute(str_name, cpcName)                            # CPC Name
    cpcOsh.setBoolAttribute('host_iscomplete', isComplete)
    cpcOsh.setAttribute('system_information', cpcSi)                  # CPC SI
    if isNotNull(cpcSi):
        cpcSiList = string.split(cpcSi, '.')
        if len(cpcSiList) == 5:
            cpcOsh.setAttribute(str_node_family, cpcSiList[0])          # CPC Type
            cpcOsh.setAttribute(str_discovered_model, cpcSiList[1])     # CPC Model
            if len(cpuLists) > 0:
                if isNotNull(cpuLists[0][2]):
                    cpuSerial = cpuLists[0][2]
                    cpcSerial = cpcSiList[4]
                    if isNotNull(cpcSerial):
                        createMainframe = 1
                    cpcOsh.setAttribute(str_serial_number, cpcSerial)   # CPC Serial
                    # set host_key as serial number ----------------------------
                    cpcOsh.setAttribute('host_key', cpcSerial)
    if createMainframe:
        str_membership = 'membership'
        if _CMDB_CLASS_MODEL.version() < 9:
            str_membership = 'member'
        membershipOsh = modeling.createLinkOSH(str_membership, cpcOsh, lparOsh)
        _vector.add(cpcOsh)
        _vector.add(lparOsh)
        _vector.add(membershipOsh)
    return _vector

def osh_createCpuOsh(lparOsh, cpuLists):
    _vector = ObjectStateHolderVector()
    for cpu in cpuLists:
        if isNotNull(cpu[0]) and isNotNull(cpu[1]) and cpu[1] == 'ONLINE':
            cpuOsh = ObjectStateHolder('cpu')
            if _CMDB_CLASS_MODEL.version() > 9:
                cpuOsh.setAttribute('cpu_id', cpu[0])
                cpuOsh.setAttribute('serial_number', cpu[2])
            else:
                cpuOsh.setAttribute('cpu_cid', cpu[0])
                
            #Spencer: Add cpu type
            cpu_type = ''
            if (len(cpu[3]) >= 2):
                if (cpu[3][1] == 'I'):
                    cpu_type = 'Ziip'
                elif (cpu[3][1] == 'A'):
                    cpu_type = 'Zaap'
                
            cpuOsh.setAttribute('cpu_type', cpu_type)
            
            cpuOsh.setContainer(lparOsh)
            _vector.add(cpuOsh)
    return _vector

def osh_createIpOsh(lparOsh, homeLists):
    _vector = ObjectStateHolderVector()
    ipOshDict = {}
    ipstoexclude = ['127.0.0.1']
    if len(homeLists) > 0:
        for home in homeLists:
            if isNotNull(home[0]) and upper(home[0]) != 'ADDRESS' and home[0] not in ipstoexclude and eview_netutils._isValidIp(home[0]):
                ipOsh = eview_netutils._buildIp(home[0])
                containedOsh = modeling.createLinkOSH('contained', lparOsh, ipOsh)
                _vector.add(lparOsh)
                _vector.add(ipOsh)
                _vector.add(containedOsh)
                # add IP OSH to dictionary for later use -----------------------
                ipOshDict[home[0]] = ipOsh
    return (_vector, ipOshDict)

def osh_createSubsystemsOsh(lparOsh, ssiList):
    str_name = 'name'
    str_discovered_product_name = 'discovered_product_name'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
        str_discovered_product_name = 'data_name' # duplicated on purpose

    _vector = ObjectStateHolderVector()
    if isNotNull(ssiList):
        for ssi in ssiList:
            if isNotNull(ssi[0]):
                ssOsh = ObjectStateHolder('mainframe_subsystem')
                ssOsh.setAttribute(str_name, ssi[0])
                ssOsh.setAttribute(str_discovered_product_name, ssi[0])
                
                # Is Dynamic ---------------------------------------------------
                if isNotNull(ssi[1]) and upper(ssi[1]) == 'YES':
                    ssOsh.setBoolAttribute('is_dynamic', 1)
                elif isNotNull(ssi[1]) and upper(ssi[1]) == 'NO':
                    ssOsh.setBoolAttribute('is_dynamic', 0)
                    
                # Is Active ----------------------------------------------------
                if isNotNull(ssi[2]) and upper(ssi[2]) == 'ACTIVE':
                    ssOsh.setBoolAttribute('is_active', 1)
                elif isNotNull(ssi[2]) and upper(ssi[2]) == 'INACTIVE':
                    ssOsh.setBoolAttribute('is_active', 0)
                
                # Accepts commands ---------------------------------------------
                if isNotNull(ssi[3]):
                    ssOsh.setAttribute('accepts_commands', ssi[3])
                
                ssOsh.setContainer(lparOsh)
                _vector.add(ssOsh)
    return _vector

def osh_createMajorNodesOsh(lparOsh, majorNodesLists):
    str_name = 'name'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
    _vector = ObjectStateHolderVector()
    if len(majorNodesLists) > 0:
        for majNode in majorNodesLists:
            if isNotNull(majNode[0]):
                majOsh = ObjectStateHolder('mainframe_major_node')
                majOsh.setAttribute(str_name, majNode[0])
                if isNotNull(majNode[1]):
                    majOsh.setAttribute('type', majNode[1])
                majOsh.setContainer(lparOsh)
                _vector.add(majOsh)
    return _vector

def osh_createPageOsh(lparOsh, pageLists):
    str_name = 'name'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
    _vector = ObjectStateHolderVector()
    if len(pageLists) > 0:
        for page in pageLists:          # [Type, Used, Status, Device, DSN_Name]
            if isNotNull(page[4]):
                pageOsh = ObjectStateHolder('mainframe_page_dataset')
                pageOsh.setAttribute(str_name, page[4])        # DSN Name
                if isNotNull(page[0]):
                    pageOsh.setAttribute('type', page[0])    # Type
                if isNotNull(page[1]) and isnumeric(page[1]):
                    pageOsh.setIntegerAttribute('used', int(page[1]))    # Used
                if isNotNull(page[2]):
                    pageOsh.setAttribute('status', page[2])
                if isNotNull(page[3]):
                    pageOsh.setAttribute('device', page[3])
                pageOsh.setContainer(lparOsh)
                _vector.add(pageOsh)
    return _vector

def osh_createSoftwareOsh(lparOsh, prodLists):
    str_cit = 'installed_software'
    str_name = 'name'
    str_description = 'description'
    str_version = 'version'
    str_software_productid = 'software_productid'
    str_discovered_vendor = 'discovered_vendor'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_cit = 'software'
        str_name = 'data_name'
        str_description = 'data_description'
        str_version = 'software_version'
        str_software_productid = 'software_productid'
        str_discovered_vendor = 'software_vendor'
    
    _vector = ObjectStateHolderVector()
    if len(prodLists) > 0:
        for prod in prodLists:      # [ID, name, feature, version, owner, registered]
            swOsh = None
            if isNotNull(prod[1]) and isNotNull(prod[2]):
                swOsh = ObjectStateHolder(str_cit)
                softwareName = ''
                softwareDesc = ''
                if upper(prod[1]) == upper(prod[2]):
                    swOsh.setAttribute(str_name, prod[1]) # Name
                    swOsh.setAttribute(str_description, prod[1]) # Name
                else:
                    swOsh.setAttribute(str_name, '%s %s' % (prod[1], prod[2])) # Name Feature
                    swOsh.setAttribute(str_description, '%s %s' % (prod[1], prod[2])) # Name Feature
            elif isNotNull(prod[2]):
                swOsh = ObjectStateHolder(str_cit)
                swOsh.setAttribute(str_name, prod[2])   # Feature
            if isNotNull(swOsh):
                if isNotNull(prod[3]) and prod[3] != '**.**.**' and prod[3] != '* .* .*':
                    swOsh.setAttribute(str_version, prod[3])     # Version
                if isNotNull(prod[0]):
                    swOsh.setAttribute(str_software_productid, prod[0])  # Version
                if isNotNull(prod[4]):
                    swOsh.setAttribute(str_discovered_vendor, prod[4])  # Owner
                swOsh.setContainer(lparOsh)
                _vector.add(swOsh)
    return _vector

def getIpFromHomeList(homeLists, linkName = ''):
    if isNotNull(homeLists) and len(homeLists) > 0:
        firstAvailableIp = ''
        for home in homeLists:
            if isNotNull(home[0]) and upper(home[0]) != 'ADDRESS' and isNotNull(home[1]):
                firstAvailableIp = home[0]
                if isNotNull(linkName) and upper(home[1]) == upper(linkName):
                    return home[0]
                elif isNull(linkName) and isNotNull(home[2]) and upper(home[2]) == 'P':
                    return home[0]
        return firstAvailableIp    
    return ''

def getLinkFromHomeList(homeLists, ip):
    if isNotNull(homeLists) and len(homeLists) > 0 and isNotNull(ip):
        for home in homeLists:
            if isNotNull(home[0]) and upper(home[0]) != 'ADDRESS' and isNotNull(home[1]) and home[0] == ip:
                return home[1]
    return ''

def osh_createDeviceAndLinkOsh(lparOsh, ipOshDict, lparName, linkDevLinkDict, ipMacDict, homeLists):
    str_name = 'interface_name'
    str_mac_address = 'mac_address'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
        str_mac_address = 'interface_macaddr'
    
    _vector = ObjectStateHolderVector()
    
    for (linkName, j) in linkDevLinkDict.items():
        
        # create interfaces ----------------------------------------------------
        
        ifOsh = ObjectStateHolder('interface')
        ifOsh.setAttribute(str_name, linkName)
        ifOsh.setAttribute('data_note', j.linkType) ## ER: change attribute to link type
        # default the mac address attribute to linkName-Lparname and update later if MAC found            #CP15
        ifOsh.setAttribute(str_mac_address, '#%s-%s' % (linkName, lparName)) # if MAC not found for set #linkName-Lparname as key #CP15
        
        ifOsh.setContainer(lparOsh)
        
        # link interfaces to IPs -----------------------------------------------
        ipOsh = None
        parentIp = getIpFromHomeList(homeLists, linkName)
        if isNotNull(parentIp) and ipOshDict.has_key(parentIp):
            ipOsh = ipOshDict[parentIp]
            if isNotNull(ipMacDict) and ipMacDict.has_key(parentIp):
                arpInfo = ipMacDict[parentIp]
                if isNotNull(arpInfo) and len(arpInfo) == 2:
                    if isNotNull(arpInfo[0]) and upper(linkName) == upper(arpInfo[0]):
                        ifOsh.setAttribute(str_mac_address, arpInfo[1])
        _vector.add(ifOsh)
        
        if isNotNull(ipOsh):
            parentLinkOsh = modeling.createLinkOSH('containment', ifOsh, ipOsh)
            _vector.add(ipOsh)
            _vector.add(parentLinkOsh)
        
        # create devices (only for UCMDB 9.x) ----------------------------------
        if _CMDB_CLASS_MODEL.version() >= 9:
            devOsh = ObjectStateHolder('hardware_board')
            devOsh.setAttribute('serial_number', j.devName) # serial number not available, use device name
            devOsh.setAttribute('name', j.devName)
            ##devOsh.setAttribute('data_note', j.devType)
            devOsh.setContainer(lparOsh)
            _vector.add(devOsh)
        
    return _vector


def _getIpPortFromSocket(socket, primaryIp):
    ip = ''
    port = ''
    if isNotNull(socket):
        socket = string.split(socket, "..")
        if len(socket) == 2:
            if isNotNull(socket[0]):
                ip = socket[0]
            if isNotNull(socket[1]):
                port = socket[1]
    if ip == '0.0.0.0': # use homelist primary IP
        ip = primaryIp
    if not eview_netutils._isValidIp (ip):          
        ip = None     
    return (ip, port)


def osh_createTcpConnectionsOsh(lparOsh, ipOshDict, connsList, knownPortsConfigFile, homeLists):
    str_containment = 'containment'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_containment = 'contained'
    _vector = ObjectStateHolderVector()
    
    ignoreLocalConnections = 0 ## ER: parameterize
    primaryIp = getIpFromHomeList(homeLists)

    for conn in connsList:
        if upper(conn[0]) != 'USER ID':
            id = conn[0]
            localSocket = conn[2]
            foreignSocket = conn[3]
            state = conn[4]
            srcAddr = ''
             
            # split up the socket text into IP and port ------------------------
            (dstAddr, dstPort) = _getIpPortFromSocket(localSocket, primaryIp)
            if upper(state) == 'ESTBLSH':
                (srcAddr, srcPort) = _getIpPortFromSocket(foreignSocket, primaryIp)
           
            if ignoreLocalConnections and (srcAddr == dstAddr):
                continue

            if isNotNull(dstAddr) and eview_netutils._isValidIp(dstAddr):
                # create destination (server) IP and Host --------------------------
                dstIpOsh = eview_netutils._buildIp(dstAddr)
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

                if isNotNull(srcAddr) and eview_netutils._isValidIp(srcAddr):
                    # create source (client) IP and Host ---------------------------
                    srcIpOsh = eview_netutils._buildIp(srcAddr)
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
    if _CMDB_CLASS_MODEL.version() < 9:
        str_dependency = 'dependency'
    nodeDependencyLinkOsh = modeling.createLinkOSH(str_dependency, clientHostOsh, serverHostOSH)
    nodeDependencyLinkOsh.setAttribute('dependency_name', serverPort)
    nodeDependencyLinkOsh.setAttribute('dependency_source', portName)
    return nodeDependencyLinkOsh

def _createClientServerLinkOsh(serverPort, serverPortOsh, portName, portType, clientIpOsh):
    str_client_server = 'client_server'
    str_name = 'name'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_client_server = 'clientserver'
        str_name = 'data_name'
    csLinkOsh = modeling.createLinkOSH(str_client_server, clientIpOsh, serverPortOsh)
    csLinkOsh.setStringAttribute('clientserver_protocol', portType)
    csLinkOsh.setStringAttribute(str_name, portName)
    csLinkOsh.setLongAttribute('clientserver_destport', int(serverPort))
    return csLinkOsh

def osh_createXcfOsh(lparOsh, xcfGroupsDict, sysplexOsh, lparName):
    str_name = 'name'
    str_membership = 'membership'
    str_containment = 'containment'
    if _CMDB_CLASS_MODEL.version() < 9:
        str_name = 'data_name'
        str_membership = 'member'
        str_containment = 'contained'
    _vector = ObjectStateHolderVector()
    
    if isNotNull(sysplexOsh):
        if isNotNull(xcfGroupsDict):
            for (groupName, membersList) in xcfGroupsDict.items():
                # Create XCF Groups
                xcfGroupOsh = ObjectStateHolder('mainframe_xcf_group')
                xcfGroupOsh.setAttribute(str_name, groupName)
                xcfGroupOsh.setContainer(sysplexOsh)
                _vector.add(xcfGroupOsh)
                
                # Make the LPAR member of XCF
                if isNotNull(xcfGroupOsh):
                    memberLinkOsh = modeling.createLinkOSH(str_membership, xcfGroupOsh, lparOsh)
                    _vector.add(memberLinkOsh)
                
                # Create XCF member for every group
                if isNotNull(xcfGroupOsh) and isNotNull(membersList) and len(membersList) > 0:
                    for member in membersList:
                        if isNotNull(member[0]):
                            memberOsh = ObjectStateHolder('mainframe_xcf_member')
                            memberOsh.setAttribute(str_name, member[0])
                            memberOsh.setAttribute('job_id', member[2])
                            memberOsh.setAttribute('xcf_member_status', member[3])
                            memberOsh.setContainer(xcfGroupOsh)
                            _vector.add(memberOsh)
                            
                            # If LPAR sysid matches member system name, create contained link
                            if isNotNull(lparName) and isNotNull(memberOsh) and string.upper(lparName) == string.upper(member[1]):
                                containedLinkOsh = modeling.createLinkOSH(str_containment, lparOsh, memberOsh)
                                _vector.add(containedLinkOsh)
                    
    else:
        logger.debug('Not creating any XCF Groups since no sysplex discovered')
    return _vector




# Process LPAR Network Resources  
def processNetworkResources(ls, lparOsh, ipOshDict, lparName, sysplexOsh, knownPortsConfigFile, Framework):
    _vector = ObjectStateHolderVector()

    #===========================================================================
    # Run commands and create OSHs
    # XCF (Groups, Members), TCPIP NETSTAT (CONN, HOME, ROUTE)
    #===========================================================================
    
    # XCF Groups and Members Commands ------------------------------------------
    xcfGroupsDict = {}   # {groupName:[[memberName, memberSystem, jobId, status]]
    xcfGroups = ev10_getXcfGroupOutput(ls)
    for group in xcfGroups:
        if isNotNull(group[0]):
            ev11_getXcfMemberOutput(ls, group[0], xcfGroupsDict) 
    _vector.addAll(osh_createXcfOsh(lparOsh, xcfGroupsDict, sysplexOsh, lparName))
    
    # TCPIP Stacks Command -----------------------------------------------------
    createTcpUdp = Framework.getParameter('discover_TCP_UDP')
    if isNotNull(createTcpUdp) and string.lower(createTcpUdp) == 'true':
        createTcpUdp = 1
    else:
        createTcpUdp = 0
    tcpStacksList = ev4_getTcpStackNameOutput(ls)
    connsList = []
    routeList = []
    linkDevLinkDict = {}
    ipMacDict = {}
    homeLists = []
    for tcpStack in tcpStacksList:
        linkDevLinkDict = appendToDictionary(linkDevLinkDict, ev14_getTcpDevLinkOutput(ls, tcpStack)) # for TCP devices and interfaces (links)
        ipMacDict       = appendToDictionary(ipMacDict, ev15_getArpCacheOutput(ls, tcpStack))         # for TCP interfaces (links)
        homeLists       = appendToList(homeLists, ev5_getHomelistOutput(ls, tcpStack))                # for IP addresses and links
        if createTcpUdp:
            connsList       = appendToList(connsList, ev12_getTcpConnOutput(ls, tcpStack))                # for TCP connections
            routeList       = appendToList(routeList, ev13_getTcpRouteOutput(ls, tcpStack))               # for TCP connections
    
    _vector.addAll(osh_createDeviceAndLinkOsh(lparOsh, ipOshDict, lparName, linkDevLinkDict, ipMacDict, homeLists))
    if createTcpUdp:
        _vector.addAll(osh_createTcpConnectionsOsh(lparOsh, ipOshDict, connsList, knownPortsConfigFile, homeLists))
    
    return _vector


####################################
##  Create Jobs Objects          ##
####################################

def createJobsOSH(joblist,lparOSH):
    myVec = ObjectStateHolderVector()
    for job in joblist:             
            jobOSH = ObjectStateHolder('mainframe_job')
            jobOSH.setAttribute('name', job[0])
            jobOSH.setAttribute('step_name',job[1]) 
            jobOSH.setAttribute('proc_step',job[2])
            jobOSH.setAttribute('job_id',job[3]) 
            jobOSH.setAttribute('process_user',job[4])               
            jobOSH.setIntegerAttribute('current_storage', int(job[8])) 
            jobOSH.setAttribute('program_name',job[9])
            jobid = job[3]
            if re.findall("STC.*", jobid): 
                jobOSH.setAttribute('type', 'Started Task')
            elif re.findall("JOB.*", jobid):                #CP15
                jobOSH.setAttribute('type', 'Job')          #CP15
            else:
                continue                                    #CP15
            jobOSH.setContainer(lparOSH)
            myVec.add(jobOSH)      
    return myVec

####################################
##  Create DASD Volume object     ##
####################################

def createDASDVolOSH(vollist,lparOSH):
    
    dasdOSH = ObjectStateHolder('dasd3390')
    dasdOSH.setAttribute('name', vollist[0])
    dasdOSH.setIntegerAttribute('num_tracks', int(vollist[1])) 
    dasdOSH.setIntegerAttribute('tracks_per_cyl', int(vollist[2])) 
    dasdOSH.setIntegerAttribute('volume_free_extents', int(vollist[3]))
    dasdOSH.setIntegerAttribute('volume_free_tracks', int(vollist[4])) 
    dasdOSH.setIntegerAttribute('largest_extent', int(vollist[5])) 
    dasdOSH.setIntegerAttribute('percent_used', int(vollist[6]))  
    dasdOSH.setContainer(lparOSH)    
    return dasdOSH

####################################
##  Create DASD Storage Group     ##
####################################

def createDASDSG(grouplist,lparOSH):
    
    dasdOSH = ObjectStateHolder('volumegroup')
    dasdOSH.setAttribute('name', grouplist[0])     
    dasdOSH.setContainer(lparOSH)    
    return dasdOSH
    
#############################################################
##  Get the Indivual DASD Volumes and the Groups           ##
#############################################################  

def getvolumes(ls,lparOSH):
    
    vector = ObjectStateHolderVector()
    vollinelist = []
    volDICT = {} 
   
    #
    # First get the indivual DASD volumes for the Lpar
    #
    output = ls.evSysInfoCmd(_CMD_I_DASD,'01')  
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        lines = output.cmdResponseList
        for line in lines:
            vollinelist = line.split('|')
            volDICT[vollinelist[0]] = vollinelist 
            vector.add(createDASDVolOSH(vollinelist,lparOSH))        
    return vector, volDICT

#############################################################
##  Get the Storage Volumes in the Storage Groups          ##
#############################################################  

def getStorageVolumes(ls, lparOSH, vgOSH, sgname, volDICT):
    
    vector = ObjectStateHolderVector()
    volumelist = []
   
    #
    # First get the volumes for the storage group
    #
    output = ls.evSysInfoCmd(sgname,'12','evsgv')  
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        lines = output.cmdResponseList
        for line in lines:
            volumelist = line.split()
            if (volumelist[0] in volDICT.keys()):
                volOSH =  createDASDVolOSH(volDICT[volumelist[0]],lparOSH)
                vector.add(modeling.createLinkOSH('containment', vgOSH , volOSH))     
    return vector 
    
#############################################################
##  Get the Storage Groups                                ##
#############################################################  


def getStorageGroups(ls, lparOSH):
    
    vector = ObjectStateHolderVector()
    grouplist = []
    (volvector, volDICT) = getvolumes(ls,lparOSH)
    vector.addAll(volvector)
    #
    #  Get the Storage Groups
    #
    output = ls.evSysInfoCmd('','12','evsgl')  
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        lines = output.cmdResponseList
        for line in lines:
            grouplist = line.split() 
            #Skip the VIO group as it is not a real group
            if grouplist[0] == 'VIO':
                continue
            #Verify we have a valid group, must be at least 10 entries to be valid
            if len(grouplist) >= 10:          
                vgOSH = createDASDSG(grouplist,lparOSH)
                vector.add (vgOSH)
                vector.addAll(getStorageVolumes(ls, lparOSH, vgOSH, grouplist[0], volDICT))          
    return vector 
#############################################################
# Discover the Dasd Storage connected to the Mainframe   
#############################################################       
def processDasd(ls,lparOSH,Framework):

    _vector = ObjectStateHolderVector()
    discoverDasd = Framework.getParameter('discover_DASD')
    if isNotNull(discoverDasd) and string.lower(discoverDasd) == 'true':
        discoverDasd = 1
    else:
        discoverDasd = 0
    if discoverDasd:
        _vector = getStorageGroups(ls, lparOSH)
    return _vector


#############################################################
##  Get the each Address Space (Jobs and  Started Tasks)   ##
#############################################################  

def getjobs(ls,jobregex,lparOSH):
    
    vector = ObjectStateHolderVector()
    joblist = [] 
    joblinelist = []  
    if jobregex == None:
        jobregex = '*'
    #
    # First get the jobs and started tasks
    #
    output = ls.evSysInfoCmd(jobregex,'40') 
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        lines = output.cmdResponseList
        for line in lines:
            joblinelist = line.split('|')
            joblist.append(joblinelist) 
        vector.addAll(createJobsOSH(joblist,lparOSH)) 
    else:
        logger.reportWarning('Jobs where not found on target system. Please, verify the regex expression parameter and rerun discovery.')
                          
    return vector

#############################################################
##  Process the Host Resources                             ##
############################################################# 
def processHostResources(ls, lparOsh, Framework):
    _vector = ObjectStateHolderVector()
    
    #===========================================================================
    # Run commands and create OSHs
    # SYMLIST, CPULIST, HOMELIST, SSILIST, MAJNODES, PAGELIST, LISTPROD
    #===========================================================================
    
    # Symbols ------------------------------------------------------------------
    symbolsMap = ev2_getSymlistOutput(ls)   # {symbolName:symbolValue}
    
    # Create Sysplex OSH -------------------------------------------------------
    (sysplexTopology, sysplexOsh) = osh_createSysplexOsh(lparOsh, symbolsMap)
    _vector.addAll(sysplexTopology)
    
    # CPU List Command ---------------------------------------------------------
    (cpuLists, cpcSi, cpcId, cpcName, lpId, lpName) = ev3_getCpulistOutput(ls)
    
    ''' Create Mainframe CPC OSH '''
    _vector.addAll(osh_createMainframeCpcOsh(lparOsh, cpcSi, cpcId, cpcName, cpuLists))
    
    ''' Create CPU OSH '''
    createCpu = Framework.getParameter('discover_CPUs')
    if isNotNull(createCpu) and string.lower(createCpu) == 'true':
        _vector.addAll(osh_createCpuOsh(lparOsh, cpuLists))
    
    ''' TCPIP Stacks Command '''
    tcpStacksList = ev4_getTcpStackNameOutput(ls)
    
    # For every TCP stack run the TCPIP NETSTAT HOME ---------------------------
    homeLists = []
    for tcpStack in tcpStacksList:
        homeLists = homeLists + ev5_getHomelistOutput(ls, tcpStack)  # [ADDRESS, LINK, FLG]
    
    # Create IP OSH ------------------------------------------------------------
    (ipOshv, ipOshDict) = osh_createIpOsh(lparOsh, homeLists)
    _vector.addAll(ipOshv)
    
    createSubsystem = Framework.getParameter('discover_Subsystems')
    if isNotNull(createSubsystem) and string.lower(createSubsystem) == 'true':
        ''' SSI Command '''
        ssiList = ev6_getSsilistOutput(ls)   # {Subsystem Name:[Dynamic, Status, Commands]}
        
        ''' Create Subsystem OSH '''
        _vector.addAll(osh_createSubsystemsOsh(lparOsh, ssiList))

    createNodes = Framework.getParameter('discover_MajorNodes')
    if isNotNull(createNodes) and string.lower(createNodes) == 'true':
        ''' Major Nodes Command '''
        majorNodesLists = ev7_getMajorNodesOutput(ls) # [Name, Type, Status]
        
        ''' Create Mainframe Major Nodes OSH '''
        _vector.addAll(osh_createMajorNodesOsh(lparOsh, majorNodesLists))
    
    createPageDatasets = Framework.getParameter('discover_PageDatasets')
    if isNotNull(createPageDatasets) and string.lower(createPageDatasets) == 'true':
        ''' Page Lists Command '''
        pageLists = ev8_getPagelistOutput(ls)  # [Type, Used, Status, Device, DSN_Name]
        
        ''' Create Mainframe Page Dataset OSH '''
        _vector.addAll(osh_createPageOsh(lparOsh, pageLists))
    
    createSoftware = Framework.getParameter('discover_Software')
    if isNotNull(createSoftware) and string.lower(createSoftware) == 'true':
        ''' Prod Lists Command '''
        prodLists = ev9_getListProdOutput(ls)   # [ID, name, feature, version, owner, state]
        
        ''' Create Mainframe Software OSH '''
        _vector.addAll(osh_createSoftwareOsh(lparOsh, prodLists))
        
    createJobs = Framework.getParameter('discover_Jobs')
    if isNotNull(createJobs) and string.lower(createJobs) == 'true': 
        jobregex = Framework.getParameter('job_Regex')
        if isNotNull(jobregex):
            _vector.addAll(getjobs(ls,jobregex,lparOsh))
        else: 
            logger.reportWarning('Regex Parameter invalid. Please, verify the Regex expression parameter and rerun discovery.')
                              
         
    return _vector, ipOshDict, sysplexOsh

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
    if eview_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)
    
    ls = eview_lib.EvShell(Framework)
    (hostResourcesOshv, ipOshDict, sysplexOsh) = processHostResources(ls, lparOsh, Framework)
    OSHVResult.addAll(hostResourcesOshv)
    (networkResourcesOshv) = processNetworkResources(ls, lparOsh, ipOshDict, lparName, sysplexOsh, knownPortsConfigFile, Framework)
    OSHVResult.addAll(networkResourcesOshv)
    OSHVResult.addAll(processDasd(ls,lparOsh,Framework))
    ls.closeClient()

    
    return OSHVResult