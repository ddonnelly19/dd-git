#coding=utf-8
##############################################################################
##  TTY_HACMP_Applications.py : version 1.4
##
##  Description:
##    Uses TTY to discover IBM HACMP cluster details on servers
##
##  Version info:
##    1.0 : Re written by CORD to adhear to the UCMDB Cluster Model (Pat Odom), Jan 2010
##    1.1 : Revised to fix problems in the modeling of the cluster (Pat Odom) May 2010
##    1.2 : Corrected problems found in release cycle for CP7. (Pat Odom)
##    1.3 : Corrected problems after code review (Pat Odom)
##    1.4 : Fixed problem during QA cycle (Pat Odom)
##    1.5 : Fixed problem with discovery stopping if their was no secondary node (QCIM1H37510: 	HACMP Application Discovery hangs up)
##
##############################################################################

import re
import modeling
import logger
import netutils
import errorcodes
import errorobject
import errormessages

## from Java
from java.lang import Exception as JavaException

## from HP
from shellutils import ShellUtils
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))

#####################################
##  Pat Odom Temporary to fake out the commands
#####################################
def  simulatecmd(file):
# Open the file for read
    buffer = ""
    input = open(file,'r')
    lines = input.readlines()
    for line in lines:
        buffer = concatenate(buffer,line)
    input.close()
    return buffer

##############################################
##  Get Host OSH based on the IP ##
##############################################
def gethostOSH(hostIP, hostName):
    hostOSH = modeling.createHostOSH(hostIP, 'node', None, hostName)
    return hostOSH


##############################################
##  Get Cluster OSH based on the name ##
##############################################
def getclusterOSH(cluster):
    clusterOSH = ObjectStateHolder('hacmpcluster')
    clusterOSH.setAttribute('data_name', cluster)
    return clusterOSH

#################################
##  Create Cluster Service
##  These can be thought of as virtual instances of servers in the cluster that are running applications at
## any specific point in time. They are shown in the model to represent where the applications are currently
## allocated but since HACMP cluster applications are dynamic this can change. So the discovery is a point in time
## discovery.
#################################
def addclusterserverOSH( nodeEntry, cluster):
    clusterserverOSH = ObjectStateHolder('clusteredservice')
    clusterserverOSH.setAttribute('data_name', nodeEntry)
    clusterserverOSH.setAttribute('host_key', '%s:%s' % (cluster, nodeEntry))
    clusterserverOSH.setBoolAttribute('host_iscomplete', 1)
    return clusterserverOSH

########################################
# Create the Volume Group OSHs
########################################
def addvolumegroupOSH(HostOSH, myVec, volumegroup, resourcegroupOSH):
    volumegroupOSH = ObjectStateHolder('hacmpresource')
    volumegroupOSH.setAttribute('data_name', volumegroup)
    volumegroupOSH.setAttribute('resource_type', 'shared volume group')
    volumegroupOSH.setContainer(resourcegroupOSH)
    myVec.add(volumegroupOSH)
    hostvgOSH = ObjectStateHolder('volumegroup')
    hostvgOSH.setAttribute('data_name', volumegroup)
    hostvgOSH.setContainer(HostOSH)
    myVec.add(hostvgOSH)
    dependOSH = modeling.createLinkOSH('depend', volumegroupOSH, hostvgOSH)
    myVec.add(dependOSH)
    return myVec

########################################
# Create the Software and Node OSHs
########################################
def addsoftwaretoclusterOSH(ClusterOSH, myVec, primarynode_ip, primarynode_name, secondarynode_ip, secondarynode_name, serviceOSH):
    if primarynode_ip and primarynode_name:
        PrimaryhostOSH = gethostOSH(primarynode_ip, primarynode_name)
        priclusterSoftwareOSH = ObjectStateHolder('failoverclustersoftware')
        priclusterSoftwareOSH.setAttribute('data_name', 'HACMP Cluster Software')
        priclusterSoftwareOSH.setContainer(PrimaryhostOSH)
        myVec.add(PrimaryhostOSH)
        myVec.add(priclusterSoftwareOSH)
        memberOSH = modeling.createLinkOSH('member', ClusterOSH, priclusterSoftwareOSH)
        myVec.add(memberOSH)
        runOSH = modeling.createLinkOSH('run', priclusterSoftwareOSH, serviceOSH)
        myVec.add(runOSH)
        potrunOSH = modeling.createLinkOSH('potentially_run', priclusterSoftwareOSH, serviceOSH)
        myVec.add(potrunOSH)
    if secondarynode_ip and secondarynode_name:
        SecondaryhostOSH = gethostOSH(secondarynode_ip, secondarynode_name)
        secclusterSoftwareOSH = ObjectStateHolder('failoverclustersoftware')
        secclusterSoftwareOSH.setAttribute('data_name', 'HACMP Cluster Software')
        secclusterSoftwareOSH.setContainer(SecondaryhostOSH)
        myVec.add(SecondaryhostOSH)
        myVec.add(secclusterSoftwareOSH)
        memberOSH = modeling.createLinkOSH('member', ClusterOSH, secclusterSoftwareOSH)
        myVec.add(memberOSH)
        potrunOSH = modeling.createLinkOSH('potentially_run', secclusterSoftwareOSH, serviceOSH)
        myVec.add(potrunOSH)
    myVec.add(ClusterOSH)
    containedOSH = modeling.createLinkOSH('contained', ClusterOSH, serviceOSH)
    myVec.add(containedOSH)
    return myVec

########################################
# Create the Service IP OSHs
########################################
def addserviceIPOSH(myVec, service_ip, serviceOSH):
    serviceIPOSH = modeling.createIpOSH(service_ip)
    containedOSH = modeling.createLinkOSH('contained', serviceOSH, serviceIPOSH)
    myVec.add(containedOSH)
    return myVec

########################################
# Create the Resource Group OSH
########################################
def addresourcegroupOSH(myVec, resourceGroup, AttributeDictionary, serviceOSH):
    resourcegroupOSH = ObjectStateHolder('hacmpgroup')
    resourcegroupOSH.setAttribute('data_name', resourceGroup)
    if AttributeDictionary.has_key('hacmpgroup_fallbackpolicy'):
        resourcegroupOSH.setAttribute('hacmpgroup_fallbackpolicy', AttributeDictionary['hacmpgroup_fallbackpolicy'])
    if AttributeDictionary.has_key('hacmpgroup_falloverpolicy'):
        resourcegroupOSH.setAttribute('hacmpgroup_falloverpolicy', AttributeDictionary['hacmpgroup_falloverpolicy'])
    if AttributeDictionary.has_key('hacmpgroup_startpolicy'):
        resourcegroupOSH.setAttribute('hacmpgroup_startuppolicy', AttributeDictionary['hacmpgroup_startpolicy'])
    resourcegroupOSH.setContainer(serviceOSH)
    return resourcegroupOSH

########################################
# Create the Application Resource OSH
########################################
def addapplicationresourceOSH(myVec, application, AttributeDictionary, resourcegroupOSH):
    resourceOSH = ObjectStateHolder('hacmpappresource')
    resourceOSH.setAttribute('data_name', application)
    resourceOSH.setAttribute('resource_type', 'application')
    if AttributeDictionary.has_key('hacmpresource_start'):
        resourceOSH.setAttribute('hacmpresource_start', AttributeDictionary['hacmpresource_start'])
    if AttributeDictionary.has_key('hacmpresource_stop'):
        resourceOSH.setAttribute('hacmpresource_stop', AttributeDictionary['hacmpresource_stop'])
    resourceOSH.setContainer(resourcegroupOSH)
    myVec.add(resourceOSH)
    return myVec

########################################
# Create the Service Resources OSHs
########################################
def addserviceresourceOSH(shell, resourceDictionary, HostOSH, myVec, SvcDictionary, resourcegroupOSH):
    for svcif_name in SvcDictionary.keys():
        (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network, svcif_status, service_label) = SvcDictionary[svcif_name]
        if resourceDictionary.has_key(svcif_name):
            (name, type, network, nettype, attr, node, ipaddr, haddr, interfacename, globalname, netmask, hb_addr, site_name) = resourceDictionary[svcif_name]
            if (type == 'boot'):
                svcifOSH = ObjectStateHolder('hacmpresource')
                svcifOSH.setAttribute('data_name', svcif_name)
                svcifOSH.setAttribute('resource_type', 'interface')
                svcifOSH.setAttribute('resource_subtype', type)
                svcifOSH.setContainer(resourcegroupOSH)
                myVec.add(svcifOSH)
                mac_address = None
                mac_address = getMAC(shell, interfacename)
                if (mac_address != None):
                    hostifOSH = modeling.createInterfaceOSH(mac_address, name=interfacename)
                    hostifOSH.setContainer(HostOSH)
                    myVec.add(hostifOSH)
                    dependOSH = modeling.createLinkOSH('depend', svcifOSH, hostifOSH)
                    myVec.add(dependOSH)
            if (type == 'service') and (nettype == 'diskhb'):
                svcifOSH = ObjectStateHolder('hacmpresource')
                svcifOSH.setAttribute('data_name', svcif_name)
                svcifOSH.setAttribute('resource_type', 'network')
                svcifOSH.setAttribute('resource_subtype', type)
                svcifOSH.setContainer(resourcegroupOSH)
                myVec.add(svcifOSH)
                phydiskhb = ipaddr.split('/')
                lenphydisk =len(phydiskhb)
                phydiskOSH =   ObjectStateHolder('physicalvolume')
                phydiskOSH.setAttribute('data_name', phydiskhb[lenphydisk-1] )
                phydiskOSH.setContainer(HostOSH)
                myVec.add(phydiskOSH)
                dependOSH = modeling.createLinkOSH('depend', svcifOSH, phydiskOSH)
                myVec.add(dependOSH)
    svclblOSH = ObjectStateHolder('hacmpresource')
    svclblOSH.setAttribute('data_name', service_label)
    svclblOSH.setAttribute('resource_type', 'service label')
    svclblOSH.setContainer(resourcegroupOSH)
    myVec.add(svclblOSH)
    return myVec

#########################################################################
##  Perform Hostname lookup on clustered node via the /etc/hosts file
##  We use the /etc/hosts file becuase this is the recommended resolve
##  method for hostnames in an HACMP cluster
#########################################################################
def hostnamelookup(shell, namesToResolve,  Framework):
    filename = '/etc/hosts'
    cmdResult = None
    nodeDictionary = {}
    try:
        #rawCmdResult = simulatecmd('c:/etchosts.txt')
        rawCmdResult = shell.safecat(filename)
        cmdResult = rawCmdResult.strip()
    except:
        msg = "Failed reading /etc/host file."
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportWarningObject(errobj)
        logger.debug(msg)
        return nodeDictionary
    keywords = ['Permission\s*Denied', 'Cannot Open']
    for keyword in keywords:
        if re.search(keyword,cmdResult,re.I):
            msg = "Permission failure."
            errobj = errorobject.createError(errorcodes.PERMISSION_DENIED, None, msg)
            logger.reportErrorObject(errobj)
            logger.debug(msg)
            return nodeDictionary
    if (re.search('\r\n', cmdResult)):
        cmdResult = cmdResult.split('\r\n')
    elif (re.search('\n', cmdResult)):
        cmdResult = cmdResult.split('\n')

    ## Only parse the node names at first, for resolution before
    ## trying to map the actual interface content
    for line in cmdResult:
        try:
            line = line.strip()
            ## Parse out headers and blank lines
            if not line or re.match('#', line):
                continue
            Address = None
            ## Remove trailing comments
            if (re.search('#', line)):
                tmp = line.split('#', 1)
                line = tmp[0]
            tmp = line.split()

            # IP Address will be the first entry
            # Names will follow corresponding to the  IP.
            # We will validate the IP then search for the name to match
            # If we find it then we will add it into our node dictionary
            # Alphanumeric representation of the host:
            #    hostname, FQDN, alias....
            # Most objects will only have two names
            # The order (of FQDN, short name, aliases) is not
            #necessarily standard across platforms/versions
            if len(tmp) > 1:
                Address = tmp[0]
                tmp = tmp[1:]
            if not Address or not netutils.isValidIp(Address) or netutils.isLocalIp(Address):
                continue
            for entry in tmp:
                if entry in namesToResolve:
                    logger.debug ('Name to resolve  ',entry,' Address = ', Address)
                    if nodeDictionary.has_key(entry):
                        logger.debug(concatenate('   From /etc/host output:  Node ', entry, ' already has an address; ignoring ' , Address))
                    else:
                        nodeDictionary[entry] = Address
                        logger.debug(concatenate('   From /etc/host output:  Adding ', entry, ' to the list with address: ', Address))
        except:
            msg = "Failed to parse etc/host file."
            errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            logger.reportWarningObject(errobj)
            logger.debug(msg)

    return nodeDictionary

#######################################################
##  Get the resource info for each host in the cluster
#######################################################
def getresourceinfo(shell,  cllsif_command):
    resourceDictionary = {}
    cmdResult = None
    rawCmdResult = None
    try:
        cmdForInterfaces = cllsif_command
        logger.debug(concatenate(' Executing command: ', cmdForInterfaces))
        rawCmdResult = shell.execCmd(cmdForInterfaces)
        cmdResult = rawCmdResult.strip()
    except:
        msg = "Command Failure - Unable to get cluster resource information "
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return resourceDictionary
    if not cmdResult:
        msg = "CLLSIF output was empty, unable to get cluster resources."
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return resourceDictionary
    keywords = ['not found']
    for keyword in keywords:
        if re.search(keyword,cmdResult,re.I):
            msg = "cllsif command not in path, check cldisp command parameter and sudo path"
            errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            logger.reportErrorObject(errobj)
            logger.debug(msg)
            return resourceDictionary
    if (re.search('\r\n', cmdResult)):
        cmdResult = cmdResult.split('\r\n')
    else:
        cmdResult = cmdResult.split('\n')

    ## Build a resource Dictionary from the cllsif data
    for line in cmdResult:
        line = line.strip()
        ## Parse out headers and blank lines
        if not line or re.match('#', line):
            continue
        name = type = network = nettype = attr = node = ipaddr = haddr = interfacename = globalname = netmask = hb_addr = site_name = None
        data = line.split(':')

        if (len(data) == 12):
            [name, type, network, nettype, attr, node, ipaddr, haddr, interfacename, globalname, netmask, hb_addr] = data
        elif (len(data) == 13):
            [name, type, network, nettype, attr, node, ipaddr, haddr, interfacename, globalname, netmask, hb_addr, site_name] = data

        resourceDictionary[name] = (name, type, network, nettype, attr, node, ipaddr, haddr, interfacename, globalname, netmask, hb_addr, site_name)
    return resourceDictionary

################################################
## Get MAC Address for Interface              ##
################################################
def getMAC(shell, int_name):
    cmdResult = None
    rawCmdResult = None
    mac = None
    entstat = None
    try:
        entstat_command = concatenate('entstat ', int_name)

        logger.debug(concatenate(' Executing command: ', entstat_command))
        entstat = shell.execCmd(entstat_command)

        if entstat != None:
            m = re.search('Device Type: (.+)', entstat)
            description = None
            if(m):
                description = m.group(1).strip()
            m = re.search('Hardware Address: ([0-9a-f:]{17})', entstat)
            rawMac = None
            if(m):
                rawMac = m.group(1)
                mac = netutils.parseMac(rawMac)
    except:
        msg = " Failed getting MAC address for interface '%s'" % int_name
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
        logger.reportWarningObject(errobj)
        logger.debug(msg)
        return None

    return mac

###################################################################################
# Create the OSHs for the Applications and Services and attach them to the Topology
###################################################################################
def createserviceapplicationOSH (shell, appDictionary, resourceDictionary, HostOSH, ClusterOSH,  Framework):

    myVec = ObjectStateHolderVector()
    namesToResolve = []
    nodeDictionary = {}

    # Loop over all the applications in the dictionary and build the appropriate OSHs
    for application in appDictionary.keys():
        Cluster, resourceGroup, primarynode, secondarynode , service_name, service_ip, volumeGrouplist, AttributeDictionary, SvcDictionary = appDictionary[application]

        # Get all the necessary OSHs that are parents to build the services and application OSHs
        if not primarynode or not secondarynode:
            continue
        primarynode_ip = None
        secondarynode_ip = None
        namesToResolve.append(primarynode)
        namesToResolve.append(secondarynode)
        nodeDictionary = hostnamelookup(shell, namesToResolve, Framework)
        if nodeDictionary.has_key(primarynode):
            primarynode_ip = nodeDictionary[primarynode]
        else:
            msg = concatenate(" Cannot resolve primary node for cluster from the /etc/hosts file, discovery aborted.", primarynode)
            errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
            logger.reportErrorObject(errobj)
            logger.debug(msg)
            return None
        if  nodeDictionary.has_key(secondarynode):
            secondarynode_ip = nodeDictionary[secondarynode]
        else:
            msg = concatenate(" Cannot resolve secondary node for cluster from the /etc/hosts file", secondarynode)
            #errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
            #logger.reportErrorObject(errobj)
            logger.debug(msg)
            #return None

        if not primarynode_ip :
            msg = concatenate(" Error getting ip address for node in cluster, discovery aborted", secondarynode)
            errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
            logger.reportErrorObject(errobj)
            logger.debug(msg)
            return None

        # Recreate the Host and the Software OSHs so that we can connect
        # the appropriate services to them
        serviceOSH = addclusterserverOSH(service_name, Cluster)
        myVec.add(serviceOSH)
        myVec = addsoftwaretoclusterOSH(ClusterOSH, myVec, primarynode_ip, primarynode, secondarynode_ip, secondarynode, serviceOSH)

        # Create the IP OSH for the services and link them to the service
        myVec = addserviceIPOSH(myVec, service_ip, serviceOSH)

        # Create the resource group for the Application and link it to the service
        resourcegroupOSH = addresourcegroupOSH(myVec, resourceGroup, AttributeDictionary, serviceOSH)
        myVec.add(resourcegroupOSH)

        # Create the application resource for the Application and link to the Group
        myVec = addapplicationresourceOSH(myVec, application, AttributeDictionary, resourcegroupOSH)

        # ReCreate the Host Volume groups so we can link them to the HACMP Resource group VG
        for volumegroup in volumeGrouplist:
            myVec = addvolumegroupOSH(HostOSH, myVec,  volumegroup, resourcegroupOSH)

        # Create the service interfaces and attach them to the resource group. Also create depend links to physical host resources.
        myVec = addserviceresourceOSH(shell, resourceDictionary, HostOSH, myVec, SvcDictionary, resourcegroupOSH)
    return myVec

######################################################
##  Discover the HACMP Applications and Services    ##
######################################################
def getapplicationInfo(shell,  cldisp_command,  Framework):
    cmdResult = None
    rawCmdResult = None
    appDictionary = {}
    svcDictionary = {}
    attributeDictionary = {}
    application_name = None
    resourceGroup = None
    service_name = None
    service_label = None
    service_ip = None
    primarynode = None
    secondarynode = None
    Cluster = None
    parsesection = 0
    parseresourcegroup = 0
    parseservice = 0
    parsevgsection = 0
    parsetopology = 0
    VolumeGrouplist = []
    svcif_name = ''
    svcif_status = ''
    svcif_ip = ''
    svcif_device = ''
    svcif_interface = ''
    svcif_node = ''
    svcif_network = ''

    try:
        cmdForApplications = cldisp_command
        logger.debug(concatenate(' Executing command: ', cmdForApplications))
        rawCmdResult = shell.execCmd(cmdForApplications)
        cmdResult = rawCmdResult.strip()
    except:
        msg = "Command Failure - Unable to get cluster topology information "
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return appDictionary
    if re.search('cannot execute', cmdResult):
        msg = "cldisp commamd failed. Verify permissions and sudo access"
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return appDictionary
    if not cmdResult:
        msg = "cldisp command output was empty, unable to get cluster topology."
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return appDictionary
    if re.search('not found', cmdResult):
        msg = "cldisp commamd is not found."
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return appDictionary
    if re.search('Cluster\s+services:\s+inactive', cmdResult, re.I):
        msg = "Cluster services are inactive"
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return appDictionary

    elif (re.search('\r\n', cmdResult)):
        cmdResult = cmdResult.split('\r\n')
    else:
        cmdResult = cmdResult.split('\n')

    # Parse the cluster config file line by line
    for line in cmdResult:
        line = line.strip()
        ## Ignore headers and blank lines
        if not line  or re.match('#', line):
            continue

        ## APPLICATIONS section
        if (re.match(r'APPLICATIONS\s*$', line)):
            parsesection = 1
#           logger.debug('Set parsesection to true')
            continue

        m = re.match(r'Application:\s*(\S+)', line)
        if (m):
            if application_name != None:
                appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode, service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary)
            application_name = m.group(1)
            parsesection = 1
            parsevgsection = 0
            continue

        if parsesection:
            m = re.match(r'Cluster\s+(\w+)\s+provides the following applications:(.*)', line)
            if (m):
                Cluster = m.group(1).strip()
                Applications = m.group(2).split()
                for application_name in Applications:
                    appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode, service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary)
                continue
            m = re.search('is started by\s+(.*)', line)
            if (m):
                start_script = m.group(1)
                attributeDictionary['hacmpresource_start'] = start_script
                continue
            m = re.search('is stopped by\s+(.*)', line)
            if (m):
                stop_script = m.group(1)
                attributeDictionary['hacmpresource_stop'] = stop_script
                parsesection = 0
                continue

        ## Resource Group policy section
        m = re.match(r'This application is part of resource group\s*\'(\S+)\'', line,re.I)
        if (m):
            resourceGroup = m.group(1)
            appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode , service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary)
            parseresourcegroup = 1
            continue

        if parseresourcegroup:
            m = re.match(r'Startup:\s*(.+)', line,re.I)
            if (m):
                startup_policy = m.group(1).strip()
                attributeDictionary['hacmpgroup_startpolicy'] = startup_policy
                continue

            m = re.match(r'Fallover:\s*(.+)', line,re.I)
            if (m):
                fallover_policy = m.group(1).strip()
                attributeDictionary['hacmpgroup_falloverpolicy'] = fallover_policy
                continue

            m = re.match(r'Fallback:\s*(.+)', line,re.I)
            if (m):
                fallback_policy = m.group(1).strip()
                attributeDictionary['hacmpgroup_fallbackpolicy'] = fallback_policy
                continue

            m = re.match(r'State of.+:\s*(.+)', line,re.I)
            if (m):
                application_state = m.group(1).strip()
                parseresourcegroup = 0
                attributeDictionary['hacmpresource_state'] = application_state
                continue


        ## Node currently providing assy008: a_wwasy008 {up}
        ## Save the node that is currently running the application in the app dictionary
        ## We must also check for an application that has no nodes or resources, in this case we remove the application from the dictionary.
        m = re.match(r'No nodes configured to provide.+', line,re.I)
        if (m):
            if  appDictionary.has_key(application_name):
                del appDictionary[application_name]
            continue

        m = re.match(r'The node that will provide\s+(\S+)\s+if\s+(\S+).*is:\s+(\S+)', line,re.I)
        if (m):
            logger.debug(concatenate('Current node for Application ', m.group(1), ' is ',  m.group(2), ' failover node is ', m.group(3)))
            application_name = m.group(1)
            primarynode = m.group(2)
            secondarynode = m.group(3)
            appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode , service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary)
            continue

        ## Service labels section
        m = re.match(r'Service Labels\s*$', line,re.I)
        if (m):
            parseservice = 1
#           logger.debug ('Set parseservice to true')
            continue

        ## Extract the service node and service IP
        if parseservice:
            m = re.match(r'(.*)\((.*)\).*$', line)
            if (m):
                service_name = m.group(1).strip()
                service_ip = m.group(2)
                service_label = line.replace ('{online}','')
                logger.debug('Application service ',service_name,'   ',service_ip)
                Cluster, resourceGroup, primarynode, secondarynode, dummy1, dummy2,VolumeGrouplist, attributeDictionary, svcDictionary = appDictionary[application_name]
                appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode, service_name, service_ip,VolumeGrouplist, attributeDictionary, svcDictionary)
                continue

            ## Extract the Service info information
            m = re.match('(\S+)\s*\{(.*)\}', line)
            if  (m):
                svcif_name = ''
                svcif_status = ''
                svcif_ip = ''
                svcif_device = ''
                svcif_interface = ''
                svcif_node = ''
                svcif_network = ''
                svcif_name = m.group(1).strip()
                svcif_status = m.group(2)

                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'with IP address:\s*(\S+)', line,re.I)
            if  (m):
                svcif_ip = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'device:\s*(\S+)', line,re.I)
            if  (m):
                svcif_device = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on interface:\s*(\S+)', line,re.I)
            if  (m):
                svcif_interface = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on node:\s*(\S+)', line,re.I)
            if  (m):
                svcif_node = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on network:\s*(\S+)', line,re.I)
            if  (m):
                svcif_network = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

        ## Shared Volume Group section
        if  re.match(r'Shared Volume Groups:\s*$', line,re.I):
            parseservice = 0
            parsevgsection = 1
            VolumeGrouplist = []
#           logger.debug('Setting parsevgsection = true')
            continue

        ## Shared Volume Groups:
        if parsevgsection:
            m = re.match(r'(\S+)$', line)
            if (m):
                if re.match(r'TOPOLOGY', line):
                    parsevgsection  = 0
                    parsetopology = 1
#                   logger.debug('Setting parsevgsection = false')
                    Cluster, resourceGroup, primarynode, secondarynode , service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary  = appDictionary[application_name]
                    appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode, service_name, service_ip, VolumeGrouplist, attributeDictionary, svcDictionary)
                    continue
                else:
                    volumeGroup = m.group(1).strip()
                    VolumeGrouplist.append(volumeGroup)
#                   logger.debug(concatenate('Volume Group: ', volumeGroup))
                    continue
        if re.match(r'TOPOLOGY', line):
            parsevgsection  = 0
            parsetopology = 1
#           logger.debug('Setting parsevgsection = false')
#           logger.debug('Setting parsetopology = true')
            continue
        if parsetopology:
            m = re.match('(\S+)\s*\{(.*)\}', line)
            if  (m):
                svcif_name = ''
                svcif_status = ''
                svcif_ip = ''
                svcif_device = ''
                svcif_interface = ''
                svcif_node = ''
                svcif_network = ''
                svcif_name = m.group(1).strip()
                svcif_status = m.group(2)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'with IP address:\s*(\S+)', line,re.I)
            if  (m):
                svcif_ip = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'device:\s*(\S+)', line,re.I)
            if  (m):
                svcif_device = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on interface:\s*(\S+)', line,re.I)
            if  (m):
                svcif_interface = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on node:\s*(\S+)', line,re.I)
            if  (m):
                svcif_node = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                continue

            m = re.match(r'on network:\s*(\S+)', line,re.I)
            if  (m):
                svcif_network = m.group(1)
                if svcif_name != '':
                    svcDictionary[svcif_name] = (svcif_name, svcif_ip, svcif_device, svcif_interface, svcif_node, svcif_network,svcif_status, service_label)
                    appDictionary[application_name] = (Cluster, resourceGroup, primarynode, secondarynode, service_name, service_ip,VolumeGrouplist, attributeDictionary, svcDictionary)
                continue

    return appDictionary

##############################
##  Discovery  MAIN  block  ##
##############################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    logger.info('Starting HACMP Applications')
    hostIP = Framework.getDestinationAttribute('ip_address')
    logger.debug ('Host IP: ',hostIP)
    cluster =  Framework.getDestinationAttribute('cluster')
    hostOS = Framework.getDestinationAttribute('host_os')
    hostOS = hostOS or 'NA'
    protocolName = Framework.getDestinationAttribute('Protocol')
    hostId = Framework.getDestinationAttribute('hostId')
    ##  Get Parameter Section
    cldisp_command = Framework.getParameter('cldisp_command') or 'cldisp'
    cllsif_command = Framework.getParameter('cllsif_command') or 'cllsif'

    try:
        client = Framework.createClient()
        shell = ShellUtils(client)
        #   If we get  good client connection , run the client commands to get the Application information for the cluster
        HostOSH = modeling.createOshByCmdbIdString('host', hostId)
        ClusterOSH = getclusterOSH(cluster)
        appDictionary = getapplicationInfo(shell,  cldisp_command,  Framework)
        resourceDictionary = getresourceinfo(shell, cllsif_command)
        OSHVResult.addAll(createserviceapplicationOSH (shell, appDictionary, resourceDictionary, HostOSH, ClusterOSH,   Framework))
        client.close()
    except JavaException, ex:
        strException = ex.getMessage()
        logger.debugException('')
        errormessages.resolveAndReport(strException, protocolName, Framework)

    logger.info('Finished HACMP Applications')
    return OSHVResult