#coding=utf-8
'''
iSeries Connection 

This procedure will attempt to connect to the local eview 400 client. Then it will issue 
commands to the client which are sent to the agent on the iSeries lpar. If sucessful, then a 
iseries CIT is created with an Eview Agent CI.

Created on  Aug 19, 2011

@author:  podom


'''
import  re, logger, modeling,  shellutils, errormessages
import eview400_lib
import file_mon_utils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Properties, Date
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients import ClientsConsts,ScriptsExecutionManager
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
import errorobject
import errorcodes
from eview400_lib import isNotNull, isNull
 

# Global Variables 
_STR_EMPTY = ''
UCMDB_VERSION = logger.Version().getVersion(ScriptsExecutionManager.getFramework())

# iSeries Commands

_CMD_EVIEW_VERSION = 'EVDSPPFM eview/version'
_CMD_SYSVAL_QMODEL  = 'DSPSYSVAL SYSVAL(QMODEL)'
_CMD_SYSVAL_QSRLNBR  = 'DSPSYSVAL SYSVAL(QSRLNBR)'
_CMD_ETHERNET  = 'ETHERNET'
_CMD_DSPNETA = 'DSPNETA'
# Classes
class EViewConfFileNameFilter:
    def accept(self, fileName):
        return re.search('^ev400_config_.*$', fileName.lower()) is not None

# Methods

def ev_getIPofLpar(ls):
    defaultIp = None
    macAddress = None
    maclist = []
    ipDict = {}
    # Get IP Information, Loopback address will not be reported
    output = ls.evApiCmd(_CMD_ETHERNET,'41')
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            splitline = line.split('|')
            if splitline[0] =='EOF':
                continue
            else:
                ipDict[splitline[6].strip()] = splitline
                maclist.append(splitline[6].strip())
        logger.debug (ipDict)   
        macAddress = min(maclist)
        logger.debug (macAddress)
        defaultIp = ipDict[macAddress][0].strip()
        logger.debug (defaultIp)  
    return defaultIp,macAddress

def ev1_getEviewVersion(ls):
    # process EView agent information ------------------------------------------
    eviewVersion = None
    try:
        output = ls.evClCmd(_CMD_EVIEW_VERSION )    
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            logger.debug('Successfully connected to EView Agent')
            eviewVersionLine = output.cmdResponseList[3]          
            regex = r"(\S+)\s+(.+)"
            eviewVersionList = output.getRegexedValues(eviewVersionLine, regex)          
            if len(eviewVersionList) == 2:
                eviewVersion = eviewVersionList[0]
                logger.debug('Found EView Agent Version = ', eviewVersion)
        else:
            logger.reportError('Unable to get output for command - %s\nError: %s' % (_CMD_EVIEW_VERSION, output.errorDump))
    except:
        errMsg = 'Failure in method ev1_getEviewVersion()'
        logger.errorException(errMsg)
        logger.reportError("Failed to get version.")

    return eviewVersion

def ev2_getiSeriesOutput(ls):
   
    model = ''
    serialnbr = ''
    osversion = ''
    sysname = ''
    r1 = re.compile('Current system name',re.IGNORECASE)           
    output = ls.evClCmd(_CMD_SYSVAL_QMODEL)
    if isNotNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:
        oslist = output.cmdResponseList[1].split()
        osversion = oslist[1]
        modelList = output.getValuesFromLineList('s', output.cmdResponseList, 'QMODEL')      
        model = modelList[0][1].split()[0]          
    else:
        logger.reportWarning('Unable to get output for command - %s' % _CMD_SYSVAL_QMODEL)   
    output = ls.evClCmd(_CMD_SYSVAL_QSRLNBR)
    if isNotNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:
        serialList = output.getValuesFromLineList('s', output.cmdResponseList, 'QSRLNBR')      
        serialnbr = serialList[0][1].split()[0] 
    else:
        logger.reportWarning('Unable to get output for command - %s' % _CMD_SYSVAL_QSRLNBR)
    output = ls.evClCmd(_CMD_DSPNETA)
    if isNotNull(output) and output.isSuccess() and len(output.cmdResponseList) > 0:
        for line in output.cmdResponseList:
            if r1.search(line):
                m = re.search('.*:\s+(\S+)', line)
                if (m):
                    sysname = m.group(1)
    else:
        logger.reportWarning('Unable to get output for command - %s' % _CMD_DSPNETA)   
    return ( model, serialnbr, osversion, sysname)


def osh_createiSeriesOsh(defaultIp,  model, osversion, serialnbr,sysname, macAddress):

    # Create Iseries OSH ----------------------------------
    str_discovered_os_name = 'discovered_os_name'
    str_discovered_os_version = 'discovered_os_version'
    str_discovered_os_vendor = 'discovered_os_vendor'
    str_discovered_model = 'discovered_model'
    str_vendor = 'vendor'
    str_os_vendor = 'os_vendor'
    str_name = 'name'
    host_key = 'host_key'
    str_serialnbr = 'serial_number'
    
    isComplete = 1    
    os400Osh = modeling.createHostOSH(defaultIp, 'as400_node', _STR_EMPTY, _STR_EMPTY, _STR_EMPTY)
    os400Osh.setAttribute(str_discovered_os_name, 'os/400')
    os400Osh.setBoolAttribute('host_iscomplete', isComplete)
    os400Osh.setAttribute(str_discovered_os_version, osversion)
    os400Osh.setAttribute(str_discovered_model, model)
    os400Osh.setAttribute(str_os_vendor, 'IBM')
    os400Osh.setAttribute(str_discovered_os_vendor, 'IBM')
    os400Osh.setAttribute(str_vendor, 'IBM')
    os400Osh.setAttribute(str_name, sysname )
    os400Osh.setAttribute(str_serialnbr, serialnbr )     
    os400Osh.setAttribute(host_key, macAddress )   
    
    return os400Osh

def osh_createIpOsh(iSeriesOsh, defaultIp):
    _vector = ObjectStateHolderVector()
    # Create IP OSH ------------------------------------
    ipOsh = modeling.createIpOSH(defaultIp)
    ipOsh.setAttribute('ip_probename', CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME))
    _vector.add(ipOsh)
    _vector.add(iSeriesOsh)   
    linkOsh = modeling.createLinkOSH('containment', iSeriesOsh, ipOsh)
    _vector.add(linkOsh)
    
    return _vector
    
def osh_createEviewOsh(localshell, iSeriesOsh, appPath, confFolder, file, nodeName, eviewVersion, defaultIp):
    # Create EView agent OSH ---------------------------------------------------
    
    logger.debug('Creating EView object')
    eviewOSH = ObjectStateHolder('eview')
    eviewOSH.setAttribute('name', nodeName)
    eviewOSH.setAttribute('discovered_product_name', nodeName)
    eviewOSH.setAttribute('version', eviewVersion)
    eviewOSH.setAttribute('application_path', appPath)
    eviewOSH.setAttribute('application_ip', defaultIp)
    eviewOSH.setAttribute('vendor', 'EView Technology Inc.')
    eviewOSH.setAttribute('eview_agent_type','iSeries')
    fileContents = localshell.safecat('%s%s' % (confFolder, file))
    address, port = eview400_lib.getEviewAgentAddress(localshell, fileContents)
    if eview400_lib.isNotNull(address):
        eviewOSH.setAttribute('application_ip', address)
    if eview400_lib.isNotNull(port) and eview400_lib.isnumeric(port):
        eviewOSH.setIntegerAttribute('application_port', int(port))
    eviewOSH.setContainer(iSeriesOsh)
    return eviewOSH

def processEviewConfFiles(Framework, localshell):
    _vector = ObjectStateHolderVector()
    fileMonitor = file_mon_utils.FileMonitor(Framework, localshell, ObjectStateHolderVector(), None, None)
    folder = Framework.getParameter('EViewInstallationFolder')
    if isNull(folder):
        logger.reportError('Job parameter - EViewInstallationFolder is empty. Set the path to the EView client installation root and rerun job.')
        return _vector
    
    appPath = fileMonitor.rebuildPath(folder) + "\\bin\\ev400hostcmd.exe"
    confFolder = fileMonitor.rebuildPath(folder) + "\\conf\\"
    confFiles = None
    try:
        confFiles = fileMonitor.listFilesWindows(confFolder, EViewConfFileNameFilter())
    except:
        logger.reportError('Unable to get EView configuration files from folder: %s' % confFolder)
        return _vector
    
    # Create iSeries & EView agent objects -----------------------------------------
    if isNull(confFiles):
        logger.reportError('Unable to get EView configuration files from folder: %s' % confFolder)
        return _vector
    elif len(confFiles) < 1:
        logger.reportError('Unable to get EView configuration files from folder: %s' % confFolder)
        return _vector
    else:
        for file in confFiles:
            
            nodeName = file[13:len(file)]   # The name of the configuration file is ev400_config_<NODE_NAME>
            logger.debug ('Node = ',nodeName)
            if eview400_lib.isNotNull(nodeName):
                
                #===================================================================
                # connect to each node with configuration and only
                # create EView CI for the ones that connect
                #===================================================================
                
                ls = eview400_lib.EvShell(Framework, nodeName, appPath)
                # Get EView agent version ------------------------------------------
                 
               
                eviewVersion = ev1_getEviewVersion(ls)
                if eview400_lib.isNotNull(eviewVersion):
                    logger.debug('Successfully executed command against EView agent on node: ', nodeName)
                     
                    # Get the iSeries  info -------------------------------------------------
                    (model, serialnbr, osversion, sysname) = ev2_getiSeriesOutput(ls)
                     
                     
                    # Get the default IP of the LPAR -------------------------------
                    defaultIp, macAddress = ev_getIPofLpar(ls)
                    
                    if isNull(defaultIp):
                        logger.reportWarning('Unable to get IP Address of LPAR: %s. Continuing with next LPAR.' % nodeName)
                        continue
                    else:
               
                        # Create iSeries OSH ---------------------------------
                        iSeriesOsh = osh_createiSeriesOsh(defaultIp,  model, osversion, serialnbr, sysname, macAddress)
                        _vector.add(iSeriesOsh)
                        
                        if isNotNull(iSeriesOsh):
                            # Create IP OSH and link it to zOS OSH -------------------------
                            _vector.addAll(osh_createIpOsh(iSeriesOsh, defaultIp))
                            
                            # Create EView Agent OSH and link it to the zOS OSH ------------
                            eviewOSH = osh_createEviewOsh(localshell, iSeriesOsh, appPath, confFolder, file, nodeName, eviewVersion, defaultIp)
                            _vector.add(eviewOSH)
                else:
                    warnMsg = 'Unable to connect to: %s' % nodeName
                    logger.warn(warnMsg)
                    warnObj = errorobject.createError(errorcodes.CONNECTION_FAILED, None, warnMsg)
                    logger.reportWarningObject(warnObj)
                    
    return _vector

######################
#        MAIN
######################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    logger.debug(" ###### Connecting to EView 400 client")
    codePage = Framework.getCodePage()
    properties = Properties()
    properties.put(BaseAgent.ENCODING, codePage)

    localshell = None
    try:
        client = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        localshell = shellutils.ShellUtils(client, properties, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
        logger.error(exInfo)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
        logger.error(exInfo)
    else:
        OSHVResult.addAll(processEviewConfFiles(Framework, localshell))
        localshell.closeClient()

    return OSHVResult