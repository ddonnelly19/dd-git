#coding=utf-8
# Jython Imports
import re

import sys
import logger
import modeling
import shellutils

import errormessages
import errorcodes
import errorobject
import file_ver_lib

from java.util import Properties

# MAM Imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent


def getSystemsWithPriorities(systemList):
    """ SystemList parameter handler 
    Details : http://seer.entsupport.symantec.com/docs/249366.htm
    Output: map from node name to its priority (implicit or assigned)
    """
    systems = {}
    if systemList:
        lastPriority = -1
        elements = systemList.split(',')
        for element in elements:
            element = element and element.strip() or None
            if element:
                system = element
                priority = lastPriority + 1 
                matcher = re.match(r"(.+?)\s*=\s*(\d+)$", element) 
                if matcher:
                    system = matcher.group(1)
                    priority = int(matcher.group(2))
                systems[system] = priority
                lastPriority = priority
    return systems 

def mainFunction(resBuffer, cfPath, shUtils, OSHVResult, protocol, Framework, lastUpdateTime):

    # Parsing the main.cf file by a reg exp that returns (Element type, name and properties)
    
    reg = '(\w+)\s([^\s]+)\s\(([^\)]+)\)'

    compiled = re.compile(reg)
    matches = compiled.findall(resBuffer)

    clusterName        = None
    groupName        = None
    veritasclusterOSH    = None
    vcsGroupOSH        = None
    clusterDeviceOSH        = None

    resourceNameToOSH    = {}
    nodeNameToOSH        = {}
    nodeNameToFSSWOSH    = {}

    for match in matches:

        element_type = match[0].strip()
        element_name = match[1].strip()
        element_prop = match[2].strip()

        # Handle the cluster element
        if element_type == 'cluster':
            clusterName = element_name

            veritasclusterOSH = ObjectStateHolder('veritascluster')
            veritasclusterOSH.setAttribute('data_name', clusterName)
            modeling.setAppSystemVendor(veritasclusterOSH)
            OSHVResult.add(veritasclusterOSH)

            # Create configuration file object containing the zipped main.cf
            configFileOsh = modeling.createConfigurationDocumentOSH("main.cf.properties", "NA", resBuffer, veritasclusterOSH, modeling.MIME_TEXT_PLAIN, lastUpdateTime, 'main.cf')
            OSHVResult.add(configFileOsh)

        # Handle the system element (Cluster nodes)
        elif element_type == 'system':
            nodeName = element_name

            hostOSH = shUtils.resolveHost(nodeName.strip())
            if hostOSH == None:
                continue

            hostOSH.setAttribute('host_hostname', nodeName)
            OSHVResult.add(hostOSH)
            
            clusterSoftware = modeling.createClusterSoftwareOSH(hostOSH, 'Veritas Cluster SW')
    
            memberOSH = modeling.createLinkOSH('member', veritasclusterOSH, clusterSoftware)
            OSHVResult.add(clusterSoftware)
            OSHVResult.add(memberOSH)
            element_prop = element_prop.strip()
            if (element_prop != '') and (len(element_prop) > 3):

                # create config file object containing the zipped cf file and link it to host
                configFileName = "%s.properties" % nodeName
                configFileOsh = modeling.createConfigurationDocumentOSH(configFileName, "NA", element_prop, clusterSoftware, modeling.MIME_TEXT_PLAIN, lastUpdateTime, nodeName)
                OSHVResult.add(configFileOsh)

            # add hostosh to nodenames map so it will be easy to access later based on nodename
            nodeNameToOSH[nodeName] = hostOSH
            nodeNameToFSSWOSH[nodeName] = clusterSoftware

        # Handle the group element
        elif element_type == 'group':
            groupName = element_name

            clusterDeviceOSH = ObjectStateHolder('clusteredservice')
            clusterDeviceOSH.setAttribute('data_name', groupName)
            clusterName = veritasclusterOSH.getAttribute('data_name').getValue()
            clusterDeviceOSH.setAttribute('host_key', '%s:%s' % (clusterName, groupName))
            clusterDeviceOSH.setBoolAttribute('host_iscomplete', 1)

            containsOSH = modeling.createLinkOSH('contained', veritasclusterOSH, clusterDeviceOSH)
            OSHVResult.add(clusterDeviceOSH)
            OSHVResult.add(containsOSH)

#            for clusterSoftware in clusterSoftwares:
#                runOSH = modeling.createLinkOSH('run', clusterSoftware, clusterDeviceOSH)
#                OSHVResult.add(runOSH)

            # create group object and link it to the cluster
            vcsGroupOSH = ObjectStateHolder('vcsgroup')
            vcsGroupOSH.setAttribute('data_name', groupName)
            vcsGroupOSH.setContainer(clusterDeviceOSH)
            OSHVResult.add(vcsGroupOSH)

            element_prop = element_prop.strip()
            if (element_prop != '') and (len(element_prop) > 3):

                # create config file object containing the current group related section in cf file, zipped and link it to cluster
                configFileName = "%s.properties" % groupName
                configFileOsh = modeling.createConfigurationDocumentOSH(configFileName, "NA", element_prop, vcsGroupOSH, modeling.MIME_TEXT_PLAIN, lastUpdateTime, groupName)
                OSHVResult.add(configFileOsh)

            m = re.search('SystemList\s*\=\s*\{(.*)\}', element_prop, re.M)
            if m:
                systemList = m.group(1)
                systemsWithPriorities = getSystemsWithPriorities(systemList)
                for nodeName, priority in systemsWithPriorities.items():
                    if nodeNameToFSSWOSH.has_key(nodeName):
                        clusterSoftware = nodeNameToFSSWOSH[nodeName]
                        ownerOSH = modeling.createLinkOSH('potentially_run', clusterSoftware, clusterDeviceOSH)
                        if priority == 0:
                            ownerOSH.setAttribute('data_name', 'Preferred Owner')
                            ownerOSH.setBoolAttribute('is_owner', 1)
                        else:
                            ownerOSH.setAttribute('data_name', 'Alternate Owner')
                            ownerOSH.setBoolAttribute('is_owner', 0)

                        OSHVResult.add(ownerOSH)

        # Handle the resource element
        elif element_type != None:
            if vcsGroupOSH == None:
                continue

            resourceName = element_name

            vcsresourceOSH = ObjectStateHolder('vcsresource')
            vcsresourceOSH.setAttribute('data_name', resourceName)
            vcsresourceOSH.setAttribute('type', element_type)
            vcsresourceOSH.setContainer(vcsGroupOSH)
            OSHVResult.add(vcsresourceOSH)

            element_prop = element_prop.strip()
            if (element_prop != '') and (len(element_prop) > 3):
                (zippedBytes, checksumValue, dataLength) = modeling.processBytesAttribute(element_prop)
                vcsresourceOSH.setBytesAttribute('resource_properties', zippedBytes)

            resourceNameToOSH[resourceName] = vcsresourceOSH
            
            # Create the real resource element behine the vcs resource and link the two objects with a depend link
            handleResource(element_name, element_type, element_prop, vcsresourceOSH, nodeNameToOSH, OSHVResult, clusterDeviceOSH)

    # Handle the resources dependencies
    reg = '([\w-]+)\srequires\s([\w-]+)'
    compiled = re.compile(reg)
    matches = compiled.findall(resBuffer)

    for match in matches:

        depended = match[0].strip()
        master  = match[1].strip()

        # link each resource with the resource it depends on
        dependOSH = modeling.createLinkOSH('depend', resourceNameToOSH[depended], resourceNameToOSH[master])
        OSHVResult.add(dependOSH)


    # Handle the CF included files
    reg = 'include\s\"(.*)\"'
    compiled = re.compile(reg)
    matches = compiled.findall(resBuffer)

    for match in matches:

        cfFileName = match.strip()
        try:
            includeFilePath = cfPath + cfFileName
            currCFBuffer = shUtils.safecat(includeFilePath)
        except:
            errorMessage = 'Failed to handle include file %s' % includeFilePath
            logger.debugException(errorMessage)
            errobj = errorobject.createError(errorcodes.FAILED_HANDLING_INCLUDE_FILE, [includeFilePath], errorMessage)
            logger.reportWarningObject(errobj)
        
        if not shUtils.getLastCmdReturnCode():
            currCFBuffer = currCFBuffer.strip()
            if (currCFBuffer != None) and (currCFBuffer != ''):
                # create configuration file object with the included cf file zipped
                configFileName = "%s.properties" % cfFileName
                configFileOsh = modeling.createConfigurationDocumentOSH(configFileName, "NA", currCFBuffer, veritasclusterOSH, modeling.MIME_TEXT_PLAIN, lastUpdateTime, cfFileName)
                OSHVResult.add(configFileOsh)

def handleResource(element_name, element_type, element_prop, vcsresourceOSH, nodeNameToOSH, OSHVResult, clusterDeviceOSH):
    #this routine handles resources of type IP or Oracle and creates the proper objects and links for those resources
    
    if element_type == 'Oracle':
        # Create the oracle database instance on all relevant nodes
        
        sid = None
        oracleIP = None
        oraclePort = None

        try:
            sidRes = re.search('Sid\s*?(?:[@\w]*?)*?\s*?=\s*?(\w+)',element_prop)
            if(sidRes):
                sid = sidRes.group(1).strip()
            oipRes = re.search('IPAddr\s*?=\s*?[\'"]?([.\d]+)[\'"]?',element_prop)
            oportRes = re.search('Portnum\s*?=\s*?[\'"]?([\d]+)[\'"]?',element_prop)
            if oipRes:
                oracleIP = oipRes.group(1).strip()
            if oportRes:
                oraclePort = oportRes.group(1).strip()
        except:
            return
        
        oracleApplicationOsh = modeling.createDatabaseOSH(element_type.lower(), sid, oraclePort, oracleIP, clusterDeviceOSH) 
        OSHVResult.add(oracleApplicationOsh)
        if oracleIP and oraclePort:
            oracleSAOSH = modeling.createServiceAddressOsh(clusterDeviceOSH,oracleIP,oraclePort,modeling.SERVICEADDRESS_TYPE_TCP,'oracle')
            useLinkOSH = modeling.createLinkOSH('use',oracleApplicationOsh,oracleSAOSH)
            OSHVResult.add(oracleSAOSH)
            OSHVResult.add(useLinkOSH)

    if element_type in ['SQLServer2000','SQLServer2005','SQLServer2008']:
        # Create the oracle database instance on all relevant nodes
        
        instanceName = None
        instanceIP = None
        instancePort = None
        instanceUser = None
        instanceDomain = None
        CRG = None

        try:
            inRes = re.search('Instance\s*?=\s*?([.\-_\w]+)',element_prop)
            if(inRes):
                instanceName = inRes.group(1).strip()
            domainRes = re.search('Domain\s*?=\s*?([.\-_\w]+)',element_prop)
            if domainRes:
                instanceDomain = domainRes.group(1).strip()
            userRes = re.search('Username\s*?=\s*?([.\-_\w]+)',element_prop)
            if userRes:
                instanceUser = userRes.group(1).strip()            
            CRG = clusterDeviceOSH.getAttribute('data_name').getValue()
            sipRes = re.search('IPAddr\s*?=\s*?[\'"]?([.\d]+)[\'"]?',element_prop)
            sportRes = re.search('Portnum\s*?=\s*?[\'"]?([\d]+)[\'"]?',element_prop)
            if sipRes:
                instanceIP = sipRes.group(1).strip()
            if sportRes:
                instancePort = sportRes.group(1).strip()
        except:
            return
        
        if CRG and instanceName:
            instanceName = CRG + '\\' + instanceName
        
        if instanceDomain:
            instanceUser = instanceDomain + '\\' + instanceUser
        
        sqlApplicationOsh = modeling.createDatabaseOSH('sqlserver', instanceName, instancePort, instanceIP, clusterDeviceOSH, None, instanceUser) 
        OSHVResult.add(sqlApplicationOsh)
        if instanceIP and instancePort:
            sqlSAOSH = modeling.createServiceAddressOsh(clusterDeviceOSH,instanceIP,instancePort,modeling.SERVICEADDRESS_TYPE_TCP,'sql')
            useLink = modeling.createLinkOSH('use',sqlApplicationOsh,sqlSAOSH)
            OSHVResult.add(sqlSAOSH)
            OSHVResult.add(useLink)

    if element_type == 'MySQL':
        # Create the oracle database instance on all relevant nodes
        
        sid = None
        mysqlPort = None
        mysqlIP = None

        try:
            ipRes = re.search('IPAddr\s*?=\s*?[\'"]?([.\d]+)[\'"]?',element_prop)
            portRes = re.search('Portnum\s*?=\s*?[\'"]?([\d]+)[\'"]?',element_prop)
            if ipRes:
                mysqlIP = ipRes.group(1).strip()
            if portRes:
                mysqlPort = portRes.group(1).strip()
            if mysqlPort:
                sid = 'MySQL on port ' + mysqlPort
        except:
            return
        if mysqlIP and mysqlPort:
            serviceAddrOSH = modeling.createServiceAddressOsh(clusterDeviceOSH, mysqlIP, mysqlPort, modeling.SERVICEADDRESS_TYPE_TCP, 'mysql')            
            applicationOsh = modeling.createDatabaseOSH(element_type.lower(), sid, mysqlPort, mysqlIP, clusterDeviceOSH)
            useLinkOSH = modeling.createLinkOSH('use',applicationOsh,serviceAddrOSH)
            OSHVResult.add(serviceAddrOSH)
            OSHVResult.add(useLinkOSH)
            OSHVResult.add(applicationOsh)

    if element_type in ['IP', 'IPMultiNIC','IPMultiNICB']:

        # Create the IP instance and connect it to the resource
        addr = None
        mask = None

        try:
            addrRes = re.search('Address\s*?=\s*?[\'"](.*)[\'"]',element_prop)
            if(addrRes):
                addr = addrRes.group(1).strip()
            else:
                logger.warn('NO ADDR')
            maskRes = re.search('NetMask\s*?=\s*?[\'"](.*)[\'"]',element_prop)
            if(maskRes):
                mask = maskRes.group(1).strip()
            else:
                logger.warn('NO MASK')
        except:
            logger.error('ERROR handling resource')
            addr = None
            mask = None

        if (addr != None) and (mask != None):

            ipOSH = modeling.createIpOSH(addr)
            ipOSH.setAttribute('ip_netmask', mask)
            OSHVResult.add(ipOSH)

            # Add depend link between the database and the resource element
            containedOSH = modeling.createLinkOSH('contained', clusterDeviceOSH, ipOSH)
            OSHVResult.add(containedOSH)

# unix-specific function which attempts to discover veritas config path
def getMainCFPath(shUtils):
    resString = None

    # Look for the veritas cluster start configuration file
    cmd = 'ls /etc/rc3.d/S*vcs'
    veritasStartCFname = shUtils.execCmd(cmd)#@@CMD_PERMISION shell protocol execution
    # get the return status of the executed command
    status = shUtils.getLastCmdReturnCode()
    # Get the veritas cluster start configuration file data
    if (status == 0 and veritasStartCFname != None and veritasStartCFname != ''):
        veritasStartCFnameLine = veritasStartCFname.splitlines()
        startCFData = shUtils.safecat(veritasStartCFnameLine[0].strip())

        # Grab the main.cf path (Assembled from three diffrent arguments in the returned buffer)
        vcsPath = re.search('VCS_CONF:-"(.*)"',startCFData)
        confDirectory = re.search('\$\{VCS_CONF\}/(.*)/\$\{conf_dir\}',startCFData)
        conf_dir = re.search('conf_dir=(.*)',startCFData)

        if vcsPath and confDirectory and conf_dir:
            # Assembled main.cf path
            resString = vcsPath.group(1).strip() + '/' + confDirectory.group(1).strip() + '/' + conf_dir.group(1).strip() + '/'
            logger.debug("main.cf path [" + resString + "]")
    else:
        logger.debug('ls /etc/rc3.d/S*vcs failed with status=%d' % status)

    return resString

###################
###################
#### MAIN BODY ####
###################
###################

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    protocol = Framework.getDestinationAttribute('Protocol')
    
    DEFAULT_MAIN_FC_PATH = ''
    #this default value would be used as last resort in case the file main.cf will not be found
    if protocol == 'ntcmd':
        DEFAULT_MAIN_FC_PATH = 'c:\\program Files\\VERITAS\\cluster server\\conf\config\\'
    else:
        DEFAULT_MAIN_FC_PATH = '/etc/VRTSvcs/conf/config/'

    # take the following parameter from the section 'destinationData name' ${PARAMETERS.<paramname>) defined in the pattern's xml file
    main_cf_path = Framework.getParameter('main_cf_path')

    properties = Properties()

    # Set codepage
    codePage = Framework.getCodePage()
    properties.put( BaseAgent.ENCODING, codePage)

    try:
        # Connect to the SSH/TELNET/NTCMD agent
        client = Framework.createClient(properties)
        clientShUtils = shellutils.ShellUtils(client)
    except:
        msg = sys.exc_info()[1]
        strmsg = '%s' % msg
        if (strmsg.lower().find('timeout') > -1):
            errobj = errorobject.createError(errorcodes.CONNECTION_TIMEOUT_NO_PROTOCOL, None, 'Connection timed out - reactivate with larger timeout value')
            logger.reportErrorObject(errobj)
            logger.debugException('Connection timed out')
        else:
            errobj = errormessages.resolveError(strmsg, 'shell')
            logger.reportErrorObject(errobj)
            logger.errorException(strmsg)
    else:
        # Get main.cf path
        if ((main_cf_path == None) or (main_cf_path == 'NA')) and (protocol != 'ntcmd'):
            main_cf_path = getMainCFPath(clientShUtils)
            if (main_cf_path == None) or (main_cf_path == 'NA'):
                main_cf_path = DEFAULT_MAIN_FC_PATH
        if ((main_cf_path == None) or (main_cf_path == 'NA')) and (protocol == 'ntcmd'):
            main_cf_path = DEFAULT_MAIN_FC_PATH
        
        # Assemble the main.cf command
        cfFullPath = main_cf_path + 'main.cf'
        try:
            resBuffer = clientShUtils.safecat(cfFullPath)
        except:
            errorMessage = 'Failed to get configuration file:' + cfFullPath
            logger.debugException(errorMessage)
            errobj = errorobject.createError(errorcodes.FAILED_FINDING_CONFIGURATION_FILE, [cfFullPath], errorMessage)
            logger.reportErrorObject(errobj)
        else:        
            if resBuffer.find('Permission denied') > -1:
                errobj = errorobject.createError(errorcodes.PERMISSION_DENIED_NO_PROTOCOL_WITH_DETAILS, ['User has no permissions to read main.cf file'], 'User has no permissions to read main.cf file')
                logger.reportErrorObject(errobj)
            else:
                lastUpdateTime = file_ver_lib.getFileLastModificationTime(clientShUtils, cfFullPath)
                mainFunction(resBuffer, main_cf_path, clientShUtils, OSHVResult, protocol, Framework, lastUpdateTime)

        try:
            clientShUtils and clientShUtils.closeClient()
        except:
            logger.debugException('')
            logger.error('Unable to close shell')
    return OSHVResult