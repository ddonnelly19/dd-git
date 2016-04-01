#######
# Created on Sep 20, 2010
#
# @author: kchhina
#
# Enhanced for CP9 to add program and transaction discovery 4/15/2011 P. Odom
# Changed the search for CICS regions to look at the active programs running on the lpar 5/3/11 P. Odom
# CP10 Added new discovery capability for CICS to DB2,  and CICS to MQ connections P. Odom
# CP10 Changed discovery of CICS Subsystem to discover if we find a DFSHIP program running.  P. Odom
# CP12 Changed to send program & transaction objects to server for each region and reuse intermediate vector. C. Sutton
# CP12 Changed program discovery to reinitialize dictionaries for each region. S. Sutton
########

import string, re, logger, modeling, netutils, shellutils, errormessages
import eview_lib
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.defines import AppilogTypes
from java.util import Date
from eview_lib import isNotNull, printSeparator, isnumeric, isNull
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager
from string import *


''' Variables '''

global Framework
UCMDB_VERSION = logger.Version().getVersion(ScriptsExecutionManager.getFramework())
PARAM_HOST_ID = 'hostId'
_CMD_F_CEMT_I_SYSTEM = 'F %s,CEMT I SYSTEM'
_CMD_F_CEMT_I_DB2CONN = 'F %s,CEMT I DB2CONN'
_CMD_F_CEMT_I_MQCONN = 'F %s,CEMT I MQCONN'
_CMD_F_CEMT_I_CONN = 'F %s,CEMT I CONN'
_CMD_F_ALL_JOBS ='*'

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))


#############################################################
##  Get the the CICS Subsystems                            ##
#############################################################
def getSubSystem(ls, lparOsh):
    # CICS Subsystems are built if we find a running program called DFHSIP. If so we will build a CICS Subsystem.
    str_name = 'name'
    str_discovered_product_name = 'discovered_product_name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'
        str_discovered_product_name = 'data_name' # duplicated on purpose
    subsystemOSH = None   
    output =  ls.evSysInfoCmd(_CMD_F_ALL_JOBS,'40')   
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:            
            if isNotNull(line):
                splitline = line.split('|') 
                if len(splitline) == 10:                   
                    if splitline[9] == 'DFHSIP':          
                        subsystemOSH = ObjectStateHolder('mainframe_subsystem')
                        subsystemOSH.setAttribute(str_name, 'CICS')
                        subsystemOSH.setAttribute(str_discovered_product_name, 'CICS')
                        subsystemOSH.setAttribute('type', 'CICS')
                        subsystemOSH.setContainer(lparOsh)
                        break
    
    return subsystemOSH
#############################################################
##  Get the CICS Regions                                   ##
#############################################################
def getCICSRegions(ls, subsystemOSH):

    regiondict =  {}
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'
    vector = ObjectStateHolderVector()
    # Get the active jobs running on the lpar
    # Look for the program name , if it is DFHSIP then we have found an active CICS job
    # The job name is the CICS region    
    output =  ls.evSysInfoCmd(_CMD_F_ALL_JOBS,'40')   
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:            
            if isNotNull(line):
                splitline = line.split('|') 
                if len(splitline) == 10:                   
                    if splitline[9] == 'DFHSIP': 
                        region = splitline[0].strip()
                        #logger.debug ('Found region ===> ',region)
                        cicsRegionOSH = ObjectStateHolder('cics_region')                      
                        cicsRegionOSH.setAttribute(str_name, region)                           
                        cicsRegionOSH.setContainer(subsystemOSH) 
                        addInfoOnRegions(ls, cicsRegionOSH)
                        if not(regiondict.has_key(region)): 
                            regiondict[region] = cicsRegionOSH
                        vector.add(cicsRegionOSH)           
    return vector, regiondict 
#############################################################
##  Add information for the Regions                        ##
#############################################################
__INT_ATTRIBUTES = ['aging', 'akp', 'logdefer', 'maxtasks', 'mrobatch', 'scandelay']
__LONG_ATTRIBUTES = ['dsalimit', 'edsalimit', 'runaway', 'time']
def addInfoOnRegions(ls, cicsRegionOSH):
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'        
    name = cicsRegionOSH.getAttributeValue(str_name)
    if isNotNull(name):        
        command = concatenate(_CMD_F_CEMT_I_SYSTEM % name)
        output = ls.evMvsCmd(command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            dataList = output.getValuesFromLineList('s', output.cmdResponseList, '\(', '\)')
            for values in dataList:
                if isNotNull(values) and isNotNull(values[0]) and isNotNull(values[1]):
                    values[0] = string.replace(values[0], '+', '')
                    values[0] = string.lower(string.strip(values[0]))
                    attributeName = 'cicsregion_%s' % values[0]
                    attributeValue = string.strip(values[1])
                    strValue = 1
                    for att in __INT_ATTRIBUTES:
                        if values[0].find(att) >= 0:
                            strValue = 0
                            modeling.__setAttributeIfExists(cicsRegionOSH, attributeName, attributeValue, AppilogTypes.INTEGER_DEF)
                            continue
                    for att in __LONG_ATTRIBUTES:
                        if values[0].find(att) >= 0:
                            strValue = 0
                            modeling.__setAttributeIfExists(cicsRegionOSH, attributeName, attributeValue, AppilogTypes.LONG_DEF)
                            continue
                    if strValue:
                        modeling.__setAttributeIfExists(cicsRegionOSH, attributeName, attributeValue)
    return       

#############################################################
##  Process CICS                                           ##
#############################################################    
def processCICS(ls, lparOsh):
    regiondict =  {}
    vector = ObjectStateHolderVector()
    subsystemOSH = getSubSystem (ls, lparOsh)
    if subsystemOSH is None:
        logger.warn ('No CICS subsystems were found')
        return vector, regiondict, subsystemOSH
    vector.add(subsystemOSH)
    cicsRegionVector, regiondict = getCICSRegions (ls, subsystemOSH)
    vector.addAll(cicsRegionVector)
    return vector, regiondict, subsystemOSH
    
#############################################################
##  Get the Programs and the Transactions and build OSHs   ##
#############################################################
def getCICSPrograms(ls,  regiondict , subsystemOSH, excluderestricted, Framework):

## Sample output:
#    
# LIST:DFH$IVPL
# LIST:DFHLIST
# LIST:XYZLIST
# LIST:ZORPHEN
# GROUP:CEE:DFH$IVPL:DFHLIST:XYZLIST
# GROUP:CICSLOGS:XYZLIST
# GROUP:DFHCBTS:DFH$IVPL:DFHLIST:XYZLIST
# GROUP:DFHDCTG:DFH$IVPL:DFHLIST:XYZLIST
# GROUP:DFHIPECI:DFH$IVPL:DFHLIST:XYZLIST
# GROUP:EVOGRP:XYZLIST
# GROUP:SOCKETS:XYZLIST
# GROUP:USERCONS:XYZLIST
# PGM:CALLOPC:   :ASSEMBLER:NO:NO:ENABLED:EVOGRP
# PGM:CALLOPCR:   :   :NO:NO:ENABLED:EVOGRP
# PGM:CEECBLDY:   :   :NO:NO:ENABLED:CEE
# PGM:CEECCICS:   :   :NO:NO:ENABLED:CEE
# PGM:CEECRHP:   :   :NO:NO:ENABLED:CEE
# PGM:CEECZST:   :   :NO:NO:ENABLED:CEE  
# TRN:CIEP:ECI OVER TCP/IP INTERFACE STARTED BY SO DOMAIN:DFHIEP:DFHCICST:ENABLED:NO::DFHTCL00:NO:NO:DFHIPECI
# TRN:EZAP:DISABLE SOCKETS INTERFACE:EZACIC22:DFHCICST:ENABLED:YES::DFHTCL00:NO:NO:SOCKETS
  
#######################################################
    
    # Query the mainframe for CICS Programs and Transactions
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'
    for region in regiondict.keys():
        cicslistdict = {}
        cicsgroupdict = {}
        cicspgmdict = {}
        vector = ObjectStateHolderVector() 
             
        regionwithoption  =  concatenate(region,'-',excluderestricted)
        # check if ev390cicstrans.pl script exists
        output = None
        scriptAbsolutePath = '%sev390cicstrans.pl' % ls.ar
        if ls.evFileExists(scriptAbsolutePath):
            output = ls.evGetCicsTran(regionwithoption)
        else:
            output = ls.evSysInfoCmd(regionwithoption, '12', 'EVOCICST' )
        if not isNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:         
            for line in  output.cmdResponseList:
                # Skip the CICS systems that are not up
                m = re.search('IEE341I', line)
                if (m):               
                    break               
                splitline = line.split(':')             
                # Look for all the CICS Lists and build OSHs for them
                if splitline[0] == 'LIST':
                    cicsListOSH = ObjectStateHolder('cics_list') 
                    cicsListOSH.setAttribute(str_name, splitline[1] )  
                    cicsListOSH.setContainer(regiondict[region])
                    vector.add (cicsListOSH)                  
                    if not(cicslistdict.has_key(splitline[1])): 
                        cicslistdict[splitline[1]] = cicsListOSH
                # Look for the CICS Groups and build OSHs for them
                elif splitline[0] == 'GROUP':
                    cicsGroupOSH = ObjectStateHolder('cics_group')                    
                    cicsGroupOSH.setAttribute(str_name, splitline[1] )
                    cicsGroupOSH.setContainer(regiondict[region])
                    vector.add (cicsGroupOSH)
                    i = 2 
                    while i < len(splitline):                   
                        cicsListOSH = ObjectStateHolder('cics_list') 
                        cicsListOSH.setAttribute(str_name, splitline[i] )  
                        cicsListOSH.setContainer(regiondict[region])
                        vector.add (cicsListOSH)                        
                        if not(cicslistdict.has_key(splitline[i])):  
                            cicslistdict[splitline[i]] = cicsListOSH
                        vector.add (modeling.createLinkOSH('containment', cicslistdict[splitline[i]], cicsGroupOSH))
                        i = i + 1
                # Look for the CICS Programs 
                elif splitline[0] == 'PGM':
                    cicsProgramOSH = ObjectStateHolder('cics_program')
                    cicsProgramOSH.setAttribute(str_name, splitline[1]) 
                    cicsProgramOSH.setAttribute('description', splitline[2])      
                    cicsProgramOSH.setAttribute('pgm_language', splitline[3]) 
                    cicsProgramOSH.setAttribute('pgm_reload', splitline[4])  
                    cicsProgramOSH.setAttribute('pgm_resident', splitline[5])  
                    cicsProgramOSH.setAttribute('pgm_status', splitline[6])             
                    cicsProgramOSH.setContainer(regiondict[region]) 
                    vector.add (cicsProgramOSH )
                    if not(cicspgmdict.has_key(splitline[1])):  
                            cicspgmdict[splitline[1]] = cicsProgramOSH 
                    i = 7 
                    while i < len(splitline):                   
                        cicsGroupOSH = ObjectStateHolder('cics_group') 
                        cicsGroupOSH.setAttribute(str_name, splitline[i] )  
                        cicsGroupOSH.setContainer(regiondict[region])
                        vector.add (cicsGroupOSH)                     
                        if not(cicsgroupdict.has_key(splitline[i])):  
                            cicsgroupdict[splitline[i]] = cicsGroupOSH
                        vector.add (modeling.createLinkOSH('containment', cicsgroupdict[splitline[i]],  cicsProgramOSH))
                        i = i + 1
                # Look for the CICS Transactions
                elif splitline[0] == 'TRN':
                    cicsTransactionOSH = ObjectStateHolder('cics_transaction')                  
                    cicsTransactionOSH.setAttribute(str_name, splitline[1]) 
                    cicsTransactionOSH.setAttribute('description', splitline[2])      
                    cicsTransactionOSH.setAttribute('trans_status', splitline[5]) 
                    cicsTransactionOSH.setAttribute('trans_protected', splitline[6])  
                    cicsTransactionOSH.setAttribute('trans_class', splitline[8])  
                    cicsTransactionOSH.setAttribute('resource_security', splitline[9]) 
                    cicsTransactionOSH.setAttribute('command_security', splitline[10])             
                    cicsTransactionOSH.setContainer(regiondict[region]) 
                    vector.add (cicsTransactionOSH)
                    i = 11 
                    while i < len(splitline):                   
                        cicsGroupOSH = ObjectStateHolder('cics_group') 
                        cicsGroupOSH.setAttribute(str_name, splitline[i] )  
                        cicsGroupOSH.setContainer(regiondict[region])
                        vector.add (cicsGroupOSH)                     
                        if not(cicsgroupdict.has_key(splitline[i])):  
                            cicsgroupdict[splitline[i]] = cicsGroupOSH
                        vector.add (modeling.createLinkOSH('containment', cicsgroupdict[splitline[i]],  cicsTransactionOSH))
                        i = i + 1
                    if cicspgmdict.has_key(splitline[3]):   
                        vector.add (modeling.createLinkOSH('usage',  cicsTransactionOSH, cicspgmdict[splitline[3]]))
        Framework.sendObjects(vector)
        Framework.flushObjects()
        vector.clear()
        vector = None

    return
    
################################################
# Discover the CICS Programs and Transactions   
################################################      
def processPrograms(ls, lparOsh, regiondict, subsystemOSH, Framework):

    vector = ObjectStateHolderVector()
    discoverPrograms = Framework.getParameter('discover_CICS_programs')
    if isNotNull(discoverPrograms ) and string.lower(discoverPrograms ) == 'true':
        discoverPrograms = 1
    else:
        discoverPrograms = 0
    if discoverPrograms:
        excluderestricted = Framework.getParameter('exclude_restricted_programs')
        if isNotNull(excluderestricted) and string.lower(excluderestricted ) == 'true':
            excluderestricted = 'Y'
        else:
            excluderestricted = 'N'
        getCICSPrograms(ls, regiondict, subsystemOSH, excluderestricted, Framework)

    return    
################################################
# Discover the CICS Connections to DB2 and MQ 
################################################      
def processConnections(ls, lparOsh, regiondict,  subsystemOSH, Framework): 
    vector = ObjectStateHolderVector()
    # Check each region for CICS to DB2 Connections
    for region in regiondict.keys():       
        command = concatenate(_CMD_F_CEMT_I_DB2CONN % region)
        output = ls.evMvsCmd(command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:         
            for line in  output.cmdResponseList:
                #logger.debug ('In DB2CONN ===> ',line)
                # Skip the CICS regions that are not up
                m = re.search('IEE341I', line)
                if (m):               
                    break
                # If the connection is not connected then we skip it
                m = re.search('Connectst\((.+)\)', line) 
                if (m):
                    connected = m.group(1).strip()
                    if connected == 'Notconnected':
                        break
                # If we find a DB2GroupID then we have a connection using a sysplex to DB2 Sharing Group
                m = re.search('Db2groupid\((.+)\)',line)
                if (m):
                    groupid = m.group(1).strip()
                    if isNotNull(groupid):
                        #logger.debug ('Found DB2 Group ID:',groupid)
                        regionOSH = regiondict[region]
                        str_name = 'name'
                        db2sharegroupOSH = ObjectStateHolder('db2_datasharing_group')
                        db2sharegroupOSH.setAttribute(str_name, groupid )  
                        vector.add (db2sharegroupOSH)
                        vector.add (regionOSH)
                        vector.add (modeling.createLinkOSH('usage', regionOSH,  db2sharegroupOSH))      
                # If we find a DB2id then we have a direct connection to a DB2 Subsystem
                m = re.search('Db2id\((.+)\)',line)
                if (m):
                    db2id = m.group(1).strip()
                    if isNotNull(db2id):
                        #logger.debug ('Found DB2 ID:',db2id)
                        regionOSH = regiondict[region]
                        str_name = 'name'
                        str_disc_name = 'discovered_product_name'
                        db2subsystemOSH = ObjectStateHolder('mainframe_subsystem')
                        db2subsystemOSH.setAttribute(str_name, db2id )
                        db2subsystemOSH.setAttribute(str_disc_name, db2id )
                        db2subsystemOSH.setContainer(lparOsh) 
                        vector.add (db2subsystemOSH)
                        vector.add (regionOSH)
                        vector.add (modeling.createLinkOSH('usage', regionOSH,  db2subsystemOSH))
    # Now Test each region for CICS to MQ Connections
    for region in regiondict.keys(): 
        # Check the version of CICS to see if it is greater than V4. Inquire MQCONN is only supported on V4 or higher
        cicsversion = 0
        command = concatenate(_CMD_F_CEMT_I_SYSTEM % region)
        output = ls.evMvsCmd(command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:         
            for line in  output.cmdResponseList:
                #logger.debug (line)
                m = re.search('Cicstslevel\((\d\d).+',line)
                if (m):
                    cicsversion = m.group(1).strip()                    
        # Skip the region if we are running CICS version < 4. 
        # MQCONN Command only works on CICS >= 4
        if int(cicsversion) < 4:
            break
        command = concatenate(_CMD_F_CEMT_I_MQCONN % region)
        output = ls.evMvsCmd(command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:         
            for line in  output.cmdResponseList:
                #logger.debug ('In MQCONN ===> ',line)
                # Skip the CICS regions that are not up
                m = re.search('IEE341I', line)
                if (m):               
                    break
                # If the connection is not connected then we skip it
                m = re.search('Connectst\((.+)\)', line) 
                if (m):
                    connected = m.group(1).strip()
                    if connected != 'Connected':
                        break
                # If we find a MQ connected to this region build the link
                m = re.search('Mqqmgr\((.+)\)',line)
                if (m):
                    mqmgr = m.group(1).strip()
                    if isNotNull(mqmgr):
                        #logger.debug ('Found MQMGR: ',mqmgr)
                        regionOSH = regiondict[region]
                        str_name = 'name'
                        # Build Websphere MQ OSH for this MQ 
                        Mqname =  'IBM WebSphere MQ '  
                        MqOSH = ObjectStateHolder('webspheremq')
                        MqOSH.setAttribute(str_name, Mqname)
                        MqOSH.setAttribute('vendor', 'ibm_corp')
                        MqOSH.setAttribute('application_category', 'Messaging')
                        modeling.setApplicationProductName(MqOSH,'IBM WebSphere MQ')
                        MqOSH.setContainer(lparOsh)
                        vector.add(MqOSH)
                        mqQMGROsh = ObjectStateHolder('mqqueuemanager')
                        mqQMGROsh.setAttribute(str_name, mqmgr)   
                        mqQMGROsh.setContainer(MqOSH)        
                        vector.add (mqQMGROsh)
                        vector.add (regionOSH)
                        vector.add (modeling.createLinkOSH('usage', regionOSH, mqQMGROsh  ))

    return vector  
######### 
# Main   
######### 
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # create LPAR node
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    lparOsh = None
    if eview_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)
    
    ls = eview_lib.EvShell(Framework)
    vector, regiondict, subsystemOSH = processCICS(ls, lparOsh)
    if isNull(subsystemOSH):
        logger.reportWarning('No CICS subsystems were found')
    else:
        Framework.sendObjects(vector)
        Framework.flushObjects()
        #OSHVResult.addAll(processPrograms(ls,lparOsh, regiondict, subsystemOSH, Framework)) 
        processPrograms(ls,lparOsh, regiondict, subsystemOSH, Framework)
        OSHVResult.addAll(processConnections(ls,lparOsh, regiondict, subsystemOSH, Framework))
    ls.closeClient()

    
    return OSHVResult
