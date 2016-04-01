#####################################
# Created on Oct 10, 2010
#
# Author: Pat Odom
#
# Mainframe discovery of IMS Regions and IMS DB
# Updated to handle DBCTL only regions using SSI and Non-SSI parsing from the Agent
# Added discovery of IMS Programs and Transactions (CP9) 4-10-11 P. Odom
######################################

import string, re, logger, modeling
import eview_lib
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from eview_lib import isNotNull
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager
from java.lang import Boolean

# Variables
global Framework
UCMDB_VERSION = logger.Version().getVersion(ScriptsExecutionManager.getFramework())
logger.debug ('UCMDB Version is  ',UCMDB_VERSION )
PARAM_HOST_ID = 'hostId'
_DSP_IMS_ACT_REG = 'DISPLAY ACTIVE REGIONS'
_DSP_IMS_AREA_ALL = 'DISPLAY AREA ALL'
_DSP_IMS_DB_ALL = 'DISPLAY DATABASE ALL'
_DSP_IMS_TRN_ALL = 'DISPLAY TRAN ALL'


##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))

# Methods

####################################
##  Create IMS subsystem object  ##
####################################

def createIMSsubsystem(subsysname, ls, lparOsh):
    subsystemOSH = None
    subsystemOSH = ObjectStateHolder('mainframe_subsystem')
    subsystemOSH.setAttribute('type', 'IMS')
    #subsystemOSH.setAttribute('parmlib', proclib)
    subsystemOSH.setContainer(lparOsh)
    if UCMDB_VERSION < 9:
        subsystemOSH.setAttribute('data_name', subsysname)
    else:
        subsystemOSH.setAttribute('name', subsysname)
        subsystemOSH.setAttribute('discovered_product_name', subsysname)
    return subsystemOSH


######################################################
##  Create the IMS Region (aka. Address Space) OSH  ##
######################################################
def createAddressSpace(subsystemOSH, type, regionName):

    imsRegionOSH = ObjectStateHolder('mainframe_imsregion')
    imsRegionOSH.setAttribute('imsregion_type', type)
    #imsRegionOSH.setAttribute('imsregion_proclib', proclibName)
    #imsRegionOSH.setAttribute('imsregion_procvalue', procValue)
    #imsRegionOSH.setAttribute('imsregion_execvalue', execValue)
    imsRegionOSH.setContainer(subsystemOSH)
    if UCMDB_VERSION < 9:
        imsRegionOSH.setAttribute('data_name', regionName)
    else:
        imsRegionOSH.setAttribute('name', regionName)
    return imsRegionOSH

###############################################
##  Create IMS Database OSH  or DB Area      ##
###############################################
def createIMSdatabase(subsystemOSH, databaseName, databaseType, accessType, databaseAreaDictionary, databaseDictionary):

    imsDatabaseOSH = None
    if (databaseType != None and databaseType.upper() == 'AREA'):
        imsDatabaseOSH = ObjectStateHolder('mainframe_imsdbarea')
        imsDatabaseOSH.setContainer(subsystemOSH)
        databaseAreaDictionary[databaseName] = imsDatabaseOSH
        if UCMDB_VERSION < 9:
            imsDatabaseOSH.setAttribute('data_name', databaseName)
        else:
            imsDatabaseOSH.setAttribute('name', databaseName)
    else:
        ## Read only (RO)
        if (accessType.strip() == 'RO'):
            accessType = 'Read only'
        ## Read (RD)
        elif (accessType.strip() == 'RD'):
            accessType = 'Read'
        ## Update (UP)
        elif (accessType.strip() == 'UP'):
            accessType = 'Update'
        ## Exclusive (EX)
        elif (accessType.strip() == 'EX'):
            accessType = 'Exclusive'
            ## Exclusive (EX)
        elif (accessType.strip() == 'N/A'):
            accessType = 'Not Applicable'
        imsDatabaseOSH = ObjectStateHolder('mainframe_ims_database')
        imsDatabaseOSH.setContainer(subsystemOSH)
        imsDatabaseOSH.setAttribute('imsdb_dbtype', databaseType)
        imsDatabaseOSH.setAttribute('imsdb_accesstype', accessType)
        databaseDictionary[databaseName] = imsDatabaseOSH
        if UCMDB_VERSION < 9:
            imsDatabaseOSH.setAttribute('data_name', databaseName)
        else:
            imsDatabaseOSH.setAttribute('name', databaseName)

    return imsDatabaseOSH

###############################################
##  Create IMS Transactons and Programs OSHs ##
###############################################
def createProgramTransactionOsh(linelist, programname, SSIflag, subsystemOSH):

    vector = ObjectStateHolderVector()
    IMSProgOSH = ObjectStateHolder('imsprogram')
    IMSTranOSH = ObjectStateHolder('imstransaction')
    tranname = None
    tranclass = 0
    enqueuecnt = 0
    queuecnt = 0
    limitcnt = 0
    proclimitcnt = 0
    currpriority = 0
    normalpriority = 0
    localpriority = 0
    segsize = 0
    seglimit = 0
    parlimit = "N/A"
    regioncnt = 0
    if SSIflag:
        if len(linelist) == 12:
            tranname = linelist[0]
            tranclass = int(linelist[1])
            enqueuecnt = int(linelist[2])
            queuecnt = int(linelist[3])
            limitcnt = int(linelist[4])
            proclimitcnt = int(linelist[5])
            currpriority = int(linelist[6])
            normalpriority = int(linelist[7])
            localpriority = int(linelist[8])
            segsize = int(linelist[9])
            seglimit = int(linelist[10])
            parlimit = linelist[11]
        elif len(linelist) == 2:
            tranname = linelist[1]
    else:
        if len(linelist) == 15:
            tranname = linelist[1]
            tranclass = int(linelist[2])
            enqueuecnt = int(linelist[3])
            queuecnt = int(linelist[4])
            limitcnt = int(linelist[5])
            proclimitcnt = int(linelist[6])
            currpriority = int(linelist[7])
            normalpriority = int(linelist[8])
            localpriority = int(linelist[9])
            segsize = int(linelist[10])
            seglimit = int(linelist[11])
            parlimit = linelist[12]
            regioncnt = int(linelist[13])
        elif len(linelist) == 4:
            tranname = linelist[1]

    if tranname != None:
        IMSTranOSH.setContainer(subsystemOSH)
        IMSTranOSH.setAttribute('name', tranname)
        IMSTranOSH.setIntegerAttribute('tran_class',tranclass)
        IMSTranOSH.setIntegerAttribute('enqueue_count',enqueuecnt)
        IMSTranOSH.setIntegerAttribute('queue_count',queuecnt)
        IMSTranOSH.setIntegerAttribute('limit_count',limitcnt)
        IMSTranOSH.setIntegerAttribute('proc_limit_count',proclimitcnt)
        IMSTranOSH.setIntegerAttribute('current_priority',currpriority)
        IMSTranOSH.setIntegerAttribute('normal_priority',normalpriority)
        IMSTranOSH.setIntegerAttribute('local_priority',localpriority)
        IMSTranOSH.setIntegerAttribute('segment_size',segsize)
        IMSTranOSH.setIntegerAttribute('segment_limit',seglimit)
        IMSTranOSH.setAttribute('parallel_limit',parlimit)
        IMSTranOSH.setIntegerAttribute('region_count',regioncnt)
        vector.add(IMSTranOSH)
        IMSProgOSH.setAttribute('name', programname)
        IMSProgOSH.setContainer(subsystemOSH)
        vector.add(IMSProgOSH)
        vector.add(modeling.createLinkOSH('usage', IMSProgOSH , IMSTranOSH ))
    return vector

#############################################################
##  Get the IMS Subsystems                                 ##
#############################################################
def getIMSSubSys(ls, lparOsh):
    IMSSubSysDict ={}
    #
    # First look for Active IMS subsytems
    #

    output = ls.evGetImsSubSys()
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        lines = output.cmdResponseList
        for line in lines:
            m = re.search('IMS Subsystem:\s*(\S+)\s*Command Prefix:\s*(\S+)',line)
            if m:
                subsystem =  m.group(1)
                prefix = m.group(2)
                if prefix == None or prefix == ' ':
                    prefix = '/'
                subsystemOSH = createIMSsubsystem(subsystem, ls, lparOsh)
                IMSSubSysDict[subsystem] = (subsystem,prefix, subsystemOSH)
    return  IMSSubSysDict

#############################################################
##  Get the Active IMS Regions                             ##
#############################################################

def getIMSActRegions(ls,lparOsh, IMSSubSysDict ):

    vector = ObjectStateHolderVector()
    regionDict = {}
    #
    for subsystem in  IMSSubSysDict.keys():
        (sub,prefix,subsystemOSH) = IMSSubSysDict[subsystem]
        vector.add(subsystemOSH)
        command =  concatenate(prefix,_DSP_IMS_ACT_REG)
        output = ls.evExecImsCommand(subsystem, command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            # Determine if the command output is from Subsystem Interface (SSI)
            # This respose will be preceeded with a DFS000I at the beginning of the line
            # If it is a DBCTL with no outstanding response then there will be no DFS000I at the start of the line
            for line in output.cmdResponseList:
                splitline = line.split()
                if (re.search('DFS4444I', line) or re.search('REGID JOBNAME', line) or  re.search('\*\d+', line)):
                    continue
                m = re.search('DFS000I',line)
                if m:
                    #logger.debug ('Non SSI Parsing  ')
                    region = splitline[2]
                    type = splitline[3]
                    regionDict[region] = (region,type, subsystem)

                else:
                    #logger.debug (' SSI Parsing ')

                    if len(splitline) == 2 or  len(splitline) == 3:
                        region = splitline[0].strip()
                        type = splitline[1].strip()
                        regionDict[region] = (region,type, subsystem)
                    if len(splitline) > 3:
                        region = splitline[1].strip()
                        type = splitline[2].strip()
                        regionDict[region] = (region,type, subsystem)
    #
    # Create the  regions found
    #
    for region in regionDict.keys():

        (reg, type, subsystem) = regionDict[region]
        (sub,prefix,subsystemOSH) = IMSSubSysDict[subsystem]
        #logger.debug  ('Region =====>',  region, '   ', type)
        vector.add(createAddressSpace(subsystemOSH, type, region))



    return vector
#############################################################
##  Query the Mainframe for Databases in the IMS Subsystem ##
#############################################################

def getIMSDB(ls, IMSSubSysDict,  databaseAreaDictionary , databaseDictionary):

#Sample Output
#
#DATABASE  TYPE  TOTAL UNUSED  TOTAL UNUSED ACC  CONDITIONS
#  DD41M702  DL/I                             EX   NOTOPEN
#  DD41M803  DL/I                             EX   NOTOPEN
#  DEDBJN21  DEDB    SEQ DEPEND DIRECT ADDRES EX   NOTOPEN
#  DB21AR0   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR1   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR2   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR3   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR4   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR5   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR6   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR7   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR8   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR9   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR10  AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB21AR11  AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DEDBJN22  DEDB    SEQ DEPEND DIRECT ADDRES EX   NOTOPEN
#  DB22AR0   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB22AR1   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DEDBJN23  DEDB    SEQ DEPEND DIRECT ADDRES EX   NOTOPEN
#  DB23AR0   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DB23AR1   AREA    N/A    N/A    N/A    N/A      NOTOPEN
#  DIMSRNO1  DL/I                             EX   NOTOPEN
#  DIMSRNO2  DL/I                             EX   NOTOPEN
#  DIMSRNO3  DL/I                             EX   NOTOPEN
#  *89184/142639
#
    vector = ObjectStateHolderVector()
    dbDict = {}
    for subsystem in  IMSSubSysDict.keys():
        (sub,prefix,subsystemOSH) = IMSSubSysDict[subsystem]
        # Query the mainframe for the IMS Databases
        command =  concatenate(prefix,_DSP_IMS_DB_ALL )
        output = ls.evExecImsCommand(subsystem, command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            # Determine if the command output is from Subsystem Interface (SSI)
            # This respose will be preceeded with a DFS000I at the beginning of the line
            # If it is a DBCTL with no outstanding response then there will be no DFS000I at the start of the line
            for line in output.cmdResponseList:
                if (re.search('DFS4444I', line) or re.search('DATABASE', line) or  re.search('\*\d+', line)):
                        continue
                m = re.search('DFS000I',line)
                if m:

                    #logger.debug ('Non SSI Parsing  ')
                    splitline = line.split()
                    accessType = 'N/A'
                    #logger.debug (splitline)
                    databaseName = splitline[1]
                    databaseType = splitline[2]
                    if  len(splitline) == 10:
                        accessType = splitline[7]
                    elif  len(splitline) == 7:
                        accessType = splitline[3]

                    dbDict[databaseName] = (databaseName , databaseType ,  accessType)

                else:
                    #logger.debug (' SSI Parsing ')
                    splitline = line.split()
                    #logger.debug ('Splitline    ',splitline, '  ', len(splitline))
                    accessType = 'N/A'
                    databaseName = splitline[0]
                    databaseType = splitline[1]
                    if len(splitline) > 2:
                        accessType =  splitline[2]
                    dbDict[databaseName] = (databaseName , databaseType ,  accessType)
        for db in dbDict.keys():
            (databaseName , databaseType ,  accessType) = dbDict[db]
            #logger.debug  ('Database =====>',databaseName  , '   ', databaseType)
            vector.add(createIMSdatabase(subsystemOSH, databaseName, databaseType, accessType, databaseAreaDictionary, databaseDictionary))

    return  vector


#############################################################
##  Parse DB Areas and link DBs to their respective Areas  ##
#############################################################
def getAREAs(ls,  IMSSubSysDict,  databaseAreaDictionary , databaseDictionary):

    ## Sample output:
    #######################################################
    ## /DISPLAY AREA ALL  LINE 001 PTERM 001.
    ## .    AREANAME  EQECT   TOTAL UNUSED  TOTAL UNUSED      DBNAME EEQECT CONDITIONS       LINE 001 PTERM 001.
    ## .     DDNAME   REMAIN SEQ DEPENDENT DIR ADDRESSABLE                         LINE 001 PTERM 001.
    ## CUSDB       N/A     N/A     N/A     N/A     N/A    DBFSAMD3   0 NOTOPEN LINE 001 PTERM 001.
    ## DFSIVD3A    N/A     N/A     N/A     N/A     N/A    IVPDB3     0 NOTOPEN LINE 001 PTERM 001.
    ## DFSIVD3B    N/A     N/A     N/A     N/A     N/A    IVPDB3     0 NOTOPEN LINE 001 PTERM 001.
    ## *08279/141449* LINE 001 PTERM 001.
    ##
    #######################################################
    vector = ObjectStateHolderVector()
    databaseName = None
    areaName = None
    areaDict = {}
    for subsystem in  IMSSubSysDict.keys():
        (sub,prefix,subsystemOSH) = IMSSubSysDict[subsystem]
        command =  concatenate(prefix,_DSP_IMS_AREA_ALL )
        output = ls.evExecImsCommand(subsystem, command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            for line in output.cmdResponseList:
                # Fall out of the parsing , go to the next subsystem. KEYWORD IS INVALID indicates the area does not exist.
                if re.search('KEYWORD IS INVALID', line):
                    break
                m = re.search('DFS000I',line)
                if m:
                    #logger.debug (' Non SSI Parsing  ')
                    if (re.search('DFS4444I', line) or re.search('AREANAME', line) or re.search('DDNAME', line) or  re.search('\*\d+', line)):
                        continue
                    if re.search('KEYWORD IS INVALID', line):
                        continue
                    splitline = line.split()
                    if len(splitline) == 11:
                        areaName= splitline[1].strip()
                        databaseName = splitline[7].strip()
                        areaDict[areaName] = (areaName , databaseName)
                else:
                    #logger.debug (' SSI Parsing ')

                    if (re.search('DFS4444I', line) or re.search('AREANAME', line) or re.search('DDNAME', line) or  re.search('\*\d+', line)):
                        continue
                    splitline = line.split()
                    if len(splitline) == 9:
                        areaName= splitline[0].strip()
                        databaseName = splitline[6].strip()
                        areaDict[areaName] = (areaName , databaseName)
        for area in areaDict.keys():
            (areaName , databaseName) = areaDict[area]
            #logger.debug  ('Area =====>',  areaName, '   ', databaseName)
            if (databaseName != 'N/A') or (databaseName != " "):
                if databaseDictionary.has_key(databaseName) and databaseAreaDictionary.has_key(area):
                    ## Link the two together
                    #logger.debug ("Linking DatabaseName = ", databaseName, "to  DatabaseArea = ", areaName)
                    if UCMDB_VERSION < 9:
                        vector.add(modeling.createLinkOSH('member', databaseDictionary[databaseName] , databaseAreaDictionary[areaName] ))
                    else:
                        vector.add(modeling.createLinkOSH('membership', databaseDictionary[databaseName],databaseAreaDictionary[areaName] ))

    return vector

#############################################################
##  Get the Programs and the Transactions and build OSHs   ##
#############################################################
def getIMSPrograms(ls,  IMSSubSysDict ):

    vector = ObjectStateHolderVector()
    # Query the mainframe for IMS Programs
    for subsystem in  IMSSubSysDict.keys():
        (sub,prefix,subsystemOSH) = IMSSubSysDict[subsystem]
        command =  concatenate(prefix,_DSP_IMS_TRN_ALL )
        output = ls.evExecImsCommand(subsystem, command)
        if output.isSuccess() and len(output.cmdResponseList) > 0:
            firstlinelist = []
            for line in output.cmdResponseList:
                if (re.search('TRAN\s+CLS', line)  or  re.search('IEE600I', line) or  re.search('DFS996I', line) or  re.search('DFS4444I', line) or  re.search('\*\d+\/\d+\*', line)):
                    continue
                m = re.search('DFS000I',line)
                if m:
                    #logger.debug (' Non SSI Parsing  ')
                    SSIflag = 0
                    #logger.debug (line)
                    if re.search('PSBNAME:', line):
                        secondlinelist = line.split()
                        programname = secondlinelist[2]
                        vector.addAll (createProgramTransactionOsh(firstlinelist, programname,SSIflag, subsystemOSH))
                    else:
                        firstlinelist =  line.split()
                else:
                    #logger.debug (' SSI Parsing ')
                    SSIflag = 1
                    #logger.debug (line)
                    if re.search('PSBNAME:', line):
                        secondlinelist = line.split()
                        programname = secondlinelist[1]
                        vector.addAll (createProgramTransactionOsh(firstlinelist, programname, SSIflag, subsystemOSH))
                    else:
                        firstlinelist =  line.split()
    return vector

#############################################################
# Discover the IMS Programs and Transactions
#############################################################
def processPrograms(ls,IMSSubSysDict,Framework):

    _vector = ObjectStateHolderVector()
    discoverPrograms = Framework.getParameter('discover_ims_programs')
    if isNotNull(discoverPrograms ) and string.lower(discoverPrograms ) == 'true':
        discoverPrograms = 1
    else:
        discoverPrograms = 0
    if discoverPrograms:
        _vector = getIMSPrograms(ls, IMSSubSysDict)

    return _vector


############################
#    MAIN
############################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    logger.info ("Starting IMS Discovery")
    DiscoverIMSDB = Boolean.parseBoolean(Framework.getParameter('DiscoverIMSDB'))

    # create LPAR node from the ID passed in
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    lparOsh = None

    if eview_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)

    ls = eview_lib.EvShell(Framework)
    IMSSubSysDict = getIMSSubSys(ls, lparOsh)
    OSHVResult.addAll(getIMSActRegions(ls,lparOsh, IMSSubSysDict ))


    if DiscoverIMSDB and len(IMSSubSysDict) > 0:
        databaseAreaDictionary = {}
        databaseDictionary = {}
        OSHVResult.addAll(getIMSDB(ls, IMSSubSysDict,  databaseAreaDictionary , databaseDictionary))
        OSHVResult.addAll(getAREAs(ls, IMSSubSysDict,  databaseAreaDictionary , databaseDictionary))
        OSHVResult.addAll(processPrograms(ls,IMSSubSysDict, Framework))
    ls.closeClient()

    logger.info ("Finished IMS Discovery")
    return OSHVResult