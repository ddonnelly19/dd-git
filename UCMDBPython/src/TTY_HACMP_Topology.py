#coding=utf-8
##############################################################################
##  TTY_HACMP_Toplogy.py : 1.4
##
##  Description:
##    Uses TTY to discover the existence of IBM HACMP cluster  
##
##  Version info:
##    1.0 : Rewritten for UCMDB 8.x created by CORD (Pat Odom), Sept 2009 
##    1.1 : Updated to correct issues in version 1.0
##    1.2 : Added storage and interfaces. Also changed code to use shellutils (Pat Odom) May 2010
##    1.3 : Fixed code mistakes after code review (Pat Odom)
##    1.4 : Fixed problems identified in QA cycle (Pat Odom)
##############################################################################


import re
import modeling 
import logger
import errorcodes
import errorobject
import errormessages
import netutils


## from Java
from java.lang import Exception as JavaException
## from HP

from shellutils import ShellUtils
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from storage_topology import VolumeGroup, LogicalVolume, PhysicalVolume,\
    createVolumeGroupOsh, createLogicalVolumeOsh, createPhysicalVolumeOsh



##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))


##############################
##  Construct the host OSH  ##
##############################
def createHostOSH(hostIP):
    hostOSH = modeling.createHostOSH(hostIP)
    return hostOSH

#####################################
##  Pat Odom simulate the commands
#####################################  
def simulatecmd(file):
## Open the file for read
    buffer = ""    
    input = open(file,'r')
    lines = input.readlines()
    for line in lines:
        buffer = concatenate(buffer,line)
    input.close()      
    return buffer

#################################################################################
##  Use the package info command to determine the platform and  HACMP version    
#################################################################################
def getClusterVersion(shell, hostOS, AIX_ClusterPackageName):

    try:
     
        packageInfoCmd = None
        packageInfoStr = None
        version = None
        if (hostOS == 'NA'):
            rawCmdResult = shell.execCmd('uname')
            if (re.search('aix', rawCmdResult.lower())):
                hostOS = 'aix'
            else:
                raise ValueError, "OS type not found; unable to build command for query package version"
        else:
            hostOS = hostOS.lower().strip()

        ## Build the correct command based on platform
        
        if hostOS == 'aix':
            packageInfoCmd = concatenate('lslpp -l ', AIX_ClusterPackageName)
        else:
            return None

        ## Run the package query for HACMP version 
        logger.debug(concatenate(' Executing command: ', packageInfoCmd))
        packageInfoStr = shell.execCmd(packageInfoCmd)
        #  Sample Output
        #  cluster.license            5.4.0.0  COMMITTED  HACMP Electronic License
        result = packageInfoStr.strip()
   
        ## Parse the result     
        keywords = ['No package provides', 'No such file or directory', 'not installed', 'Error:']
        for keyword in keywords:
            if re.search(keyword,result,re.I):
                return None 
  
        version = None
        lines = result.split('\n')
        for line in lines:
            m = re.search('^\s*\S+\s+(\d+[^ ]+)\s', line)
            if (m):
                version = m.group(1)
                logger.debug(concatenate(' Cluster package version: ', version))
                break
                
                    
    except:
        msg = "Could not execute Package Info Command "
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportWarningObject(errobj)
        logger.debug(msg)
        return None

    return version
 
#################################################################
##  Discover the physical and logical volumes / Volume Groups ##
#################################################################   
def createstorage(shell, HostOsh):

    myVec = ObjectStateHolderVector()
    volumegroupDictionary = {} 
    pvolumelist = []
    lvolumelist = [] 
       
    #  Get all the Physical Volumes , this will also give us the volume groups
    try:
        cmdForVG = 'lspv'
        logger.debug(concatenate(' Executing command: ', cmdForVG))
        rawCmdResult = shell.execCmd(cmdForVG)
        cmdResult = rawCmdResult.strip()
        if shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed getting storage topology"
    except:
        msg = "Failed getting storage topology" 
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportWarningObject(errobj)
        logger.debug(msg)
        return None

    ## Sample output...
    #    dwscmdb : lspv
    #    hdisk1          00ca4bbe84bdab4f                    rootvg          active
    #    hdisk0          00ca4bbe84bdac14                    rootvg          active
    #    hdisk2          00ca4bbeeeb6b3c2                    QSWIQ9A0_vg     concurrent
    #    hdisk3          00ca4bbeeeb3c581                    None            
    #    hdisk4          00ca4bbeeeb6b499                    QSWIQ9A0_vg     concurrent
    #    hdisk5          00ca4bbeeeb3c403                    None            
    #    hdisk6          00ca4bbeeeb6b60d                    QSWIQ9B0_vg     concurrent
    keywords = [ 'Error']
    for keyword in keywords:
        if re.search(keyword,cmdResult,re.I):
            msg = concatenate("Error in getting storage topology, ",cmdResult)
            errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            logger.reportWarningObject(errobj)
            logger.debug(msg)
            return None
              
    if (cmdResult == ''):
        logger.info('Storage topology command result empty ')
        return myVec
    cmdResult = re.split('[\r\n]+', cmdResult)
    for line in cmdResult:
        line = line.strip()
        ## Parse out headers and blank lines
        
        if not line or re.match('#', line):
            continue 
                   
        m = re.search('^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line)
        if (m):
            
            physicalvolume = PhysicalVolume()
            physicalvolume.pvName = m.group(1)
            physicalvolume.pvId = m.group(2)
            volume_group = m.group(3)
            physicalvolume.pvState = m.group(4)
            physicalvolume.volumeGroupName = volume_group

            if volume_group != 'None':
                pvolumelist.append (physicalvolume)
                volumegroupDictionary[volume_group] = None
                logger.debug ('Physical Volumes count', len(pvolumelist),  '  ',len(lvolumelist))
                
                 
        
     
        #  Now get all the logical volumes
   
    for volume_group in volumegroupDictionary.keys():
        lvolumelist = [] 
        parselogical = 0
        try:
            cmdForVG = concatenate('lsvg -l ', volume_group)
            logger.debug(concatenate(' Executing command: ', cmdForVG))
            rawCmdResult = shell.execCmd(cmdForVG)
            cmdResult = rawCmdResult.strip()
            if shell.getLastCmdReturnCode() != 0:
                raise ValueError, "Failed getting storage topology"
        except:
            msg = "Failure to get logical volume information" 
            errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            logger.reportWarningObject(errobj)
            logger.debug(msg)
            return None

        ## Sample output...
        #bash-4.0$ lsvg -l db2dbm9c_vg
        #   db2dbm9c_vg:
        #   LV NAME             TYPE       LPs     PPs     PVs  LV STATE      MOUNT POINT
        #   db2dbm9c_log_lv     jfs2log    2       4       2    closed/syncd  N/A
        #   db2dbm9c_IH_lv      jfs2       48      96      2    closed/syncd  /export/l11s03p03/db2dbm9c_IH
        #   db2dbm9c_tiv_lv     jfs2       4       8       2    closed/syncd  /export/l11s03p03/db2dbm9c_tiv
        keywords = ['Error']
        for keyword in keywords:
            if re.search(keyword,cmdResult,re.I):
                msg = concatenate("Error in getting logical volume topology, ",cmdResult)
                errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
                logger.reportWarningObject(errobj)
                logger.debug(msg)
                return None
        if not cmdResult:
            logger.info('No Logical Volumes in Volume group, skipping ', volume_group)
            continue
        cmdResult = re.split('[\r\n]+', cmdResult)
        for line in cmdResult:
            
            line = line.strip()
            if not line:
                continue
            logger.debug ('lsvg -l Line = ',line)
            ## Parse out headers and blank lines
            if re.search('^LV NAME', line):
                parselogical = 1
                continue
                
            if not parselogical:
                continue
            m = re.search('(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line)
            if (m):
                logicalvolume = LogicalVolume()
                logicalvolume.lvName = m.group(1)
                logicalvolume.lvAccType = m.group(2)
                logicalvolume.lvState = m.group(6)
                logicalvolume.mountPoint = m.group(7)
                logicalvolume.volumeGroupName = volume_group
            if volume_group != 'None':
                lvolumelist.append (logicalvolume) 
                volumegroupDictionary[volume_group] = None
                logger.debug ('Logical Volumes count', len(pvolumelist),  '  ',len(lvolumelist))
           



    #Create the Volume Groups
    
       

    for vg in volumegroupDictionary.keys():
        volumeGroup = VolumeGroup()
        volumeGroup.vgName = vg
        volumeGroupOsh = createVolumeGroupOsh(volumeGroup, HostOsh)
        volumegroupDictionary[vg]= volumeGroupOsh
        myVec.add(volumeGroupOsh)
        
        #Create the Logical  Volumes 

    for logicalVolume in lvolumelist:
        volumeGroupOsh = volumegroupDictionary.get(logicalVolume.volumeGroupName)
        if volumeGroupOsh:
            logicalVolumeOsh = createLogicalVolumeOsh(logicalVolume, HostOsh)
            myVec.add(logicalVolumeOsh)
            myVec.add(modeling.createLinkOSH("contained", volumeGroupOsh, logicalVolumeOsh))
                
                      
        #Create the Physical Volumes  

    for physicalVolume in pvolumelist:
        volumeGroupOsh = volumegroupDictionary.get(physicalVolume.volumeGroupName)
        if volumeGroupOsh:
            physicalVolumeOsh = createPhysicalVolumeOsh(physicalVolume, HostOsh)
            myVec.add(physicalVolumeOsh)
            myVec.add(modeling.createLinkOSH("contained", volumeGroupOsh, physicalVolumeOsh))
            
      
    return myVec
 
#################################################################################
##  Create the interfaces and add the CIs to the vector ##
#################################################################################   
     

def createinterfaces(shell,HostOSH,Framework):
    mac = None
    myVec = ObjectStateHolderVector()
    lines = ()
    
    # Get a listing of the device names for the network interfaces
    # prtconf = client.execCmd('lscfg | grep ent')
     
     
    prtconf = shell.execAlternateCmds('/usr/sbin/lsdev -Cc adapter | egrep ^ent',
                                    'lsdev -Cc adapter | egrep ^ent',
                                    'lsdev -Cc adapter | grep -e ^ent',
                                    '/usr/sbin/lsdev -Cc adapter | grep -e ^ent')
    #prtconf ='ent0      Available 03-08 2-Port 10/100/1000 Base-TX PCI-X Adapter (14108902)'

    if prtconf == None:
        prtconf = ''

    lines = prtconf.split('\n')
    interfaces = {}
    for line in lines:
        m = re.search('^(\S+)',line)
        if(m):
            interfaces[m.group(1)] = 'pending'

        if(len(interfaces) < 1):
            logger.debug('did not find any interfaces in prtconf (timeout?)' )
            #fail step
            return 

        # Get further info on each of the network interfaces
        for devname in interfaces.keys():
            entstat = shell.execCmd('entstat ' + devname)#@@CMD_PERMISION shell protocol execution
#            entstat = simulatecmd('c:/entstat.txt')
            if entstat == None:
                entstat = ''
            m = re.search('Device Type: (.+)', entstat)
            intdescription = None
            if(m):
                intdescription = m.group(1).strip()
            m = re.search('Hardware Address: ([0-9a-f:]{17})', entstat)
            rawMac = None
            if(m):
                rawMac = m.group(1)
                mac = netutils.parseMac(rawMac) 
                hostifOSH = modeling.createInterfaceOSH(mac, description=intdescription)
                hostifOSH.setContainer(HostOSH)
                myVec.add(hostifOSH) 
    return myVec
         
########################################################################################
# Execute the cldisp command to get the Cluster Name , build a HACMP Software CI
# We build the Cluster OSH and the Cluster Software OSH here
########################################################################################     


def CreateCluster(shell, version, hostOSH, hostIP, cldisp_command, Framework):

    myVec = ObjectStateHolderVector()
    clusterDictionary = {}
    clusterDictionary['version'] = version
    clusterOSH = None
    cmdResult = None
    rawCmdResult = ""
    try:
        cmdForClusterInfo = cldisp_command
        logger.debug(concatenate(' Executing command: ', cmdForClusterInfo))
        rawCmdResult = shell.execCmd(cmdForClusterInfo)
        cmdResult = rawCmdResult.strip()
    except:
        msg = "Failure to get cluster information" 
        errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
        logger.reportErrorObject(errobj)
        logger.debug(msg)
        return None
    keywords = ['Error','not found']
    for keyword in keywords:
        if re.search(keyword,cmdResult,re.I):
            msg = concatenate("Failure issueing cluster command, ",cmdResult)
            errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            logger.reportErrorObject(errobj)
            logger.debug(msg)
            return None
    if (cmdResult == None or (not cmdResult.find('[Cc]luster'))):
        logger.warnException('')
        Framework.reportWarning("Command to get cluster information failed")
        return myVec
    elif (re.search('\r\n', cmdResult)):
        cmdResult = cmdResult.split('\r\n')
    elif (re.search('\n', cmdResult)):
        cmdResult = cmdResult.split('\n')

    ## Parse the cluster info at the start of the output
    
    for line in cmdResult:
    
            line = line.strip()
            
            ## Parse out headers and blank lines
            
            if not line:
                continue

            m = re.match('Cluster\s*:\s*(\S+)', line, re.I)
            if (m):
                cluster = m.group(1)
                clusterDictionary['data_name'] = m.group(1)
                clusterDictionary['vendor'] = 'ibm_corp'     
                continue

#            m = re.match('Cluster\s*Services\s*:\s*(\S+)', line,re.I)
#            if (m):
#                clusterDictionary['hacmpcluster_services'] = m.group(1)[:16]
#                continue
#
#
#            m = re.match('State\s*of\s*Cluster\s*:\s*(\S+)', line,re.I)
#            if (m):
#                clusterDictionary['hacmpcluster_state'] = m.group(1)[:16]
#                continue
#
#            m = re.match('SubState\s*:\s*(\S+)', line,re.I)
#            if (m):
#                clusterDictionary['hacmpcluster_substate'] = m.group(1)[:16]
#                continue
                
            m = re.search('#######', line)
            if (m):
                # Create the Cluster OSH
                if clusterDictionary.has_key('data_name'):
                    logger.debug(concatenate(' HACMP cluster name: ', clusterDictionary['data_name']))
                    clusterOSH = ObjectStateHolder('hacmpcluster') 
                    for key in clusterDictionary.keys():
                        clusterOSH.setAttribute(key, clusterDictionary[key])
                    myVec.add(clusterOSH)
                    break
   

    # Build the HACMP Topology for the Cluster
   
  
    Topologysection = 0
    nodeDictionary = {}
    nodelist = []
    nodecounter = 0
    nodecount = 0
    node = None
    
    for line in cmdResult:
     
            line = line.strip()
            
            ## Parse out headers and blank lines
            
            if not line: 
                continue
            # Parse looking for the Topology section  
                         
            if (re.search('TOPOLOGY', line)):
                Topologysection = 1
                continue 
                
            if Topologysection:
                m = re.match('Network interfaces:', line,re.I)  
                if (m):
                    if len(nodelist) >= 0:
                        node = nodelist[nodecounter]
                        nodecounter = nodecounter + 1
                        continue
                m = re.search('(\S+)\s+consists of the following nodes:\s+(.*)', line)                      
                if (m):
                    nodelist = m.group(2).split()
                    nodecount = len(nodelist)
                    continue
                    
                m = re.search('with IP address:\s+(\S+)', line)
                if (m):
                    nodeDictionary[m.group(1)] = node
                    continue
                     
       

    # Create Topology software
    
    for nodeIPAddress in nodeDictionary.keys():
        hostOSH = createHostOSH(nodeIPAddress)
        nodeEntry = nodeDictionary[nodeIPAddress]
        hostOSH.setAttribute('data_name', nodeEntry)
        myVec.add(hostOSH) 
        
        # Create a cluster software CI
        
        clusterSoftwareOSH = ObjectStateHolder('failoverclustersoftware')
        clusterSoftwareOSH.setAttribute('data_name', 'HACMP Cluster Software' )
        clusterSoftwareOSH.setAttribute('vendor', 'ibm_corp')
        clusterSoftwareOSH.setAttribute('application_category', 'Cluster')
        clusterSoftwareOSH.setAttribute('application_version', clusterDictionary['version'])
        clusterSoftwareOSH.setAttribute('application_ip', hostIP)
        clusterSoftwareOSH.setContainer(hostOSH)
        myVec.add(clusterSoftwareOSH)       
        myVec.add(modeling.createLinkOSH('member', clusterOSH, clusterSoftwareOSH))

    return myVec


##############################
##  Discovery  MAIN  block  ##
############################## 

def DiscoveryMain(Framework):

    logger.info('Starting HACMP Topology')
    OSHVResult = ObjectStateHolderVector()


    # Get Destination Attribute Section
    
    hostIP = Framework.getDestinationAttribute('ip_address')
    hostOS = Framework.getDestinationAttribute('host_os')
    hostOS = hostOS or 'NA'
    hostCmdbId = Framework.getDestinationAttribute('hostId')
            
    physicalHostOsh = modeling.createOshByCmdbId('host', hostCmdbId)
    #  Get Parameter Section
    
        
    AIX_ClusterPackageName = Framework.getParameter('AIX_ClusterPackageName') or 'cluster.license' 
    cldisp_command = Framework.getParameter('cldisp_command') or 'cldisp'
 
    try:
        client = Framework.createClient()
        shell = ShellUtils(client)

            # We got a good client connection , determine if HACMP is installed 
            # If we find HACMP then build a Cluster and Clustered Servers (Nodes) with storage and interfaces
            
        version = getClusterVersion(shell, hostOS, AIX_ClusterPackageName)
        if version is None:
            logger.warnException('')
            Framework.reportWarning("No HACMP package found")
        else:
            logger.info(concatenate('HACMP package version: ', version))
            hostOSH = createHostOSH(hostIP)                 
            OSHVResult.addAll(CreateCluster(shell, version, hostOSH,   hostIP,  cldisp_command,  Framework))
            OSHVResult.addAll(createstorage(shell, physicalHostOsh))
            OSHVResult.addAll(createinterfaces(shell, physicalHostOsh, Framework))
            client.close()
    except JavaException, ex:
        strException = ex.getMessage()
        logger.debugException('')
        Framework.reportError("Protocol Failure, Unable to connect to client")
    
    logger.info('Finished HACMP Topology')    
    return OSHVResult  