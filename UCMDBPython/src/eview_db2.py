'''
Created on Sep 20, 2010

@author: kchhina

CP9 - Fixed defect with no sharing group found  4/11/2011 P. Odom
CP9 - Added check for DB2 subsytem Active prior to discovery 5/5/2011 P. Odom
CP10 - QCIM1H62155, QCCR1H63597: Fixed defect with a single period in the cmd_prefix 7/26/11   P.Odom
CP10 - QCCR1H62700 :Fixed defect if DB2 was defined in a Sysplex, the discovery would try to execute on nodes other than the current Lpar.
CP11 - Fixed DB2 DSG DISPLAY command handling to handle output for DB2 version 10
CP12 - Change DB2 status check from D OPDATA to D A command
'''
import string, re, logger, modeling
import eview_lib
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from eview_lib import isNotNull, isNull, printSeparator, isnumeric
from string import upper
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager
#from modeling import _CMDB_CLASS_MODEL

''' Variables '''
global Framework
PARAM_HOST_ID = 'hostId'
UCMDB_VERSION = logger.Version().getVersion(ScriptsExecutionManager.getFramework())


_CMD_PREFIX_DISPLAY_DDF = '%s DISPLAY DDF'
_CMD_PREFIX_DISPLAY_GROUP = '%s DISPLAY GROUP'
_CMD_PREFIX_DISPLAY_OPDATA = 'D OPDATA'
_QRY_LOCATIONS = 'SELECT LOCATION, LINKNAME, PORT, DBALIAS FROM SYSIBM.LOCATIONS'
_QRY_DATABASE = 'SELECT NAME, CREATOR, STGROUP, ENCODING_SCHEME, CREATEDTS FROM SYSIBM.SYSDATABASE'
_QRY_TABLESPACES = 'SELECT * FROM SYSIBM.SYSTABLESPACE'

''' Classes '''

class Dsg:
    name = ''
    level = ''
    protocolLevel = ''
    attachName = ''
    mode = ''
    members = []
    def dump(self):
        printSeparator('#', ' DSG Dump')
        logger.debug('\tname = ', self.name)
        logger.debug('\tlevel = ', self.level)
        logger.debug('\tprotocolLevel = ', self.protocolLevel)
        logger.debug('\tattachName = ', self.attachName)
        logger.debug('\tmode = ', self.mode)
        for member in self.members:
            logger.debug('\t\tdb2Member = ', member.db2Member)
            logger.debug('\t\tid = ', member.id)
            logger.debug('\t\tsubsys = ', member.subsys)
            logger.debug('\t\tcmdPref = ', member.cmdPref)
            logger.debug('\t\tstatus = ', member.status)
            logger.debug('\t\tdb2Level = ', member.db2Level)
            logger.debug('\t\tsystemName = ', member.systemName)
            logger.debug('\t\tirlmSubsys = ', member.irlmSubsys)
            logger.debug('\t\tirlmProc = ', member.irlmProc)

class DsgMember:
    db2Member = ''
    id = ''
    subsys = ''
    cmdPref = ''
    status = ''
    db2Level = ''
    systemName = ''
    irlmSubsys = ''
    irlmProc = ''

class Ddf:
    status = ''
    locationName = ''
    locationLuName = ''
    locationGenericLuName = ''
    ipAddress = ''
    tcpPort = ''
    sqlDomain = ''
    ddfAlias = []
    def dump(self):
        printSeparator('#', ' DDF Dump')
        logger.debug('\tstatus = ', self.status)
        logger.debug('\tlocationName = ', self.locationName)
        logger.debug('\tlocationLuName = ', self.locationLuName)
        logger.debug('\tlocationGenericLuName = ', self.locationGenericLuName)
        logger.debug('\tipAddress = ', self.ipAddress)
        logger.debug('\ttcpPort = ', self.tcpPort)
        logger.debug('\tsqlDomain = ', self.sqlDomain)
        for alias in self.ddfAlias:
            printSeparator('-', ' DDF Member Dump')
            logger.debug('\t\taliasName = ', alias.aliasName)
            logger.debug('\t\taliasPort = ', alias.aliasPort)

class DdfAlias:
    aliasName = ''
    aliasPort = ''


''' Methods '''

def ev1_subsystemOutput(ls):
    db2Subsystems = []  # [name, initrtn, initparm, cmd_prefix]
    output = ls.evGetSubSysCmd()
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        db2InitRoutineRegex = r"DSN\dINI"
        for line in output.cmdResponseList:
            if len(line) == 3 and isNotNull(line[1]):
                m = re.match(db2InitRoutineRegex, line[1], re.IGNORECASE)
                if isNotNull(m) and isNotNull(line[2]):
                    initParm = string.replace(line[2], "'", "")
                    initParmSplit = string.split(initParm, ",")
                    cmd_prefix = ''
                    if isNotNull(initParmSplit) and len(initParmSplit) > 1 and isNotNull(initParmSplit[1]):
                        cmd_prefix = initParmSplit[1]
                    db2Subsystems.append([line[0], line[1], initParm, cmd_prefix])
    else:
        if isNotNull(output) and isNotNull(output.errorDump) and output.errorDump.find('is not recognized as'):
            errMsg = 'Perl is required on the probe system path for this command to work. \nPlease install Perl as described in the EView agent documentation and retry this discovery'
            logger.error(errMsg)
            logger.reportError(errMsg)
    return db2Subsystems

def ev2_ddfOutput(ls, cmd_prefix):
    if isNull(cmd_prefix):
        return []
    ddfObjs = []
    cmd_prefix = string.replace(cmd_prefix, '.', '..')
    output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_DDF % cmd_prefix)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        ddfObj = Ddf()
        # status ---------------------------------------------------------------
        statusTemp = output.getValuesFromLineList('s', output.cmdResponseList, 'STATUS=')
        if isNotNull(statusTemp) and len(statusTemp) == 1 and isNotNull(statusTemp[0][1]):
            ddfObj.status = statusTemp[0][1]

        # remove first 9 characters from every line for processing table columns
        tableList = []
        for line in output.cmdResponseList:
            if isNotNull(line) and len(line) >= 9:
                tempLine = line[9:len(line)]
                if isNotNull(tempLine):
                    tableList.append(tempLine)

        # location info --------------------------------------------------------
        for i in range(len(output.cmdResponseList)):
            m = re.match('.*LOCATION\s+LUNAME\s+GENERICLU.*', output.cmdResponseList[i])
            if isNotNull(m):
                locationLine = output.cmdResponseList[i+1]
                locationLine = locationLine[9:len(locationLine)]
                location = output.getValuesFromLine('i', locationLine, '\s+', '\.', '\s+')
                if len(location) == 4:
                    ddfObj.locationName = location[0]
                    ddfObj.locationLuName = '%s.%s' % (location[1], location[2])
                    ddfObj.locationGenericLuName = location[3]
                    continue

        # Alias info -----------------------------------------------------------
        # first try for version 9 headers --------------------------------------
        headerColumns = ['ALIAS', 'PORT', 'SECPORT']
        tableBeginPattern = 'DOMAIN='
        tableEndPattern = 'MEMBER IPADDR'
        firstColumnPaddingChar = ''
        includeRegexPattern = ''
        ignorePatterns = []
        aliasTable = output.getTableValues(tableList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
        if isNotNull(aliasTable) and len(aliasTable) > 0:
            headerFound = 0
            for i in range(0, len(aliasTable)):
                if len(aliasTable[i]) == 3 and isNotNull(aliasTable[i][0]):
                    if aliasTable[i][0] != 'ALIAS' and not headerFound:
                        continue
                    if aliasTable[i][0] == 'ALIAS':
                        headerFound = 1
                        continue
                    if aliasTable[i][0][0:8] != 'DSNLTDDF':
                        ddfAliasObj = DdfAlias()
                        ddfAliasObj.aliasName = aliasTable[i][0]
                        ddfAliasObj.aliasPort = aliasTable[i][1]
                        ddfObj.ddfAlias.append(ddfAliasObj)
        # if return is empty look for version 8 headers ------------------------
        else:
            headerColumns = ['ALIAS', 'PORT']
            aliasTable = output.getTableValues(tableList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
            if isNotNull(aliasTable) and len(aliasTable) > 0:
                headerFound = 0
                for i in range(1, len(aliasTable)):
                    if len(aliasTable[i]) == 2 and isNotNull(aliasTable[i][0]):
                        if aliasTable[i][0] != 'ALIAS' and not headerFound:
                            continue
                        if aliasTable[i][0] == 'ALIAS':
                            headerFound = 1
                            continue
                        if aliasTable[i][0][0:8] != 'DSNLTDDF':
                            ddfAliasObj = DdfAlias()
                            ddfAliasObj.aliasName = aliasTable[i][0]
                            ddfAliasObj.aliasPort = aliasTable[i][1]
                            ddfObj.ddfAlias.append(ddfAliasObj)

        # IP info --------------------------------------------------------------
        # first try the DB2 version 8 format -----------------------------------
        for i in range(len(output.cmdResponseList)):
            m = re.match('.*IPADDR\s+TCPPORT\s+RESPORT.*', output.cmdResponseList[i])
            if isNotNull(m):
                ipLine = output.cmdResponseList[i+1]
                ipLine = ipLine[9:len(ipLine)]
                ips = output.getRegexedValues(ipLine, '(.*)\s+(\d+)\s+(\d+)')
                if isNotNull(ips) and len(ips) == 3:
                    ddfObj.ipAddress = ips[0]
                    ddfObj.tcpPort = ips[1]
                    continue
        if isNull(ddfObj.ipAddress):
            # try the DB2 version 9 format -------------------------------------
            ipAddrList = output.getValuesFromLineList('s', output.cmdResponseList, 'I IPADDR=')
            if isNotNull(ipAddrList) and len(ipAddrList) > 0 and isNotNull(ipAddrList[0][1]):
                ddfObj.ipAddress = ipAddrList[0][1]

        if isNull(ddfObj.tcpPort):
            # try the DB2 version 9 format -------------------------------------
            tcpList = output.getValuesFromLineList('s', output.cmdResponseList, 'TCPPORT=', 'SECPORT=')
            if isNotNull(tcpList) and len(tcpList) > 0 and isNotNull(tcpList[0][1]):
                ddfObj.tcpPort = tcpList[0][1]

        # SQL Domain -----------------------------------------------------------
        sqlDomainList = output.getValuesFromLineList('s', output.cmdResponseList, 'SQL', 'DOMAIN=')
        if isNotNull(sqlDomainList) and len(sqlDomainList) > 0 and isNotNull(sqlDomainList[0]) and len(sqlDomainList[0]) >=2:
            ddfObj.sqlDomain = sqlDomainList[0][2]
        ddfObjs.append(ddfObj)
    return ddfObjs

def ev3_locationOutput(ls, db2SubsystemName):
    ##SELECT * FROM SYSIBM..LOCATIONS
    locations = [] # [name, linkName, port, dbAlias]
    output = ls.evExecDb2Query(db2SubsystemName, _QRY_LOCATIONS)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for i in range(1, len(output.cmdResponseList)):
            if len(output.cmdResponseList[i]) == 4:
                if isNotNull(output.cmdResponseList[i][0]):
                    locations.append(output.cmdResponseList[i])
    return locations

def ev4_dataSharingGroupsOutput(ls, cmd_prefix):
    if isNull(cmd_prefix):
        return []
    dsgs = []
    cmd_prefix = string.replace(cmd_prefix, '.', '..')
    output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_GROUP % cmd_prefix)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        dsg = Dsg()
        # first get the data sharing group info ------------------------------------
        # first try version 9/10 format -------------------------------------------
        dsgInfo1 = output.getValuesFromLineList('s', output.cmdResponseList, 'DISPLAY OF GROUP\(', '\).+LEVEL\(', '\) MODE\(', '\)')
        if isNotNull(dsgInfo1) and len(dsgInfo1) > 0 and isNotNull(dsgInfo1[0]) and len(dsgInfo1[0]) == 5:
            if isNotNull(dsgInfo1[0][1]) and string.find(dsgInfo1[0][1], '.......') < 0:
                dsg.name = dsgInfo1[0][1]
                dsg.level = dsgInfo1[0][2]
                dsg.mode = dsgInfo1[0][3]
        else:
            # try version 8 format ---------------------------------------------
            dsgInfo2 = output.getValuesFromLineList('s', output.cmdResponseList, 'DISPLAY OF GROUP\(', '\) GROUP LEVEL\(', '\)')
            if isNotNull(dsgInfo2) and len(dsgInfo2) > 0 and isNotNull(dsgInfo2[0]) and len(dsgInfo2[0]) == 4:
                if isNotNull(dsgInfo2[0][1]) and dsgInfo2[0][1] != '.......':
                    dsg.name = dsgInfo2[0][1]
                    dsg.level = dsgInfo2[0][2]

        if isNull(dsg.name):
            logger.warn("No Data sharing group found")
        else:
            # next get more information about the DSG --------------------------
            dsgInfo3 = output.getValuesFromLineList('s', output.cmdResponseList, 'PROTOCOL LEVEL\(', '\)\s+GROUP ATTACH NAME\(', '\)')
            if isNotNull(dsgInfo3) and len(dsgInfo3) > 0 and isNotNull(dsgInfo3[0]) and len(dsgInfo3[0]) == 4:
                dsg.protocolLevel = dsgInfo3[0][1]
                dsg.attachName = dsgInfo3[0][2]

            # next get the DSG member info -------------------------------------
            headerColumns = ['MEMBER', 'ID', 'SUBSYS', 'CMDPREF', 'STATUS', 'LVL', 'NAME', 'SUBSYS', 'IRLMPROC']
            tableBeginPattern = 'DB2 SYSTEM'
            tableEndPattern = '----------------------------'
            firstColumnPaddingChar = ''
            includeRegexPattern = ''
            ignorePatterns = ['------']
            aliasTable = output.getTableValues(output.cmdResponseList, headerColumns, tableBeginPattern, tableEndPattern, firstColumnPaddingChar, includeRegexPattern, ignorePatterns)
            if isNotNull(aliasTable) and len(aliasTable) > 0:
                for i in range(1, len(aliasTable)):
                    if len(aliasTable[i]) == 9:
                        if isNotNull(aliasTable[i][0]) and string.find(aliasTable[i][0], '.......') < 0:
                            dsgMember = DsgMember()
                            dsgMember.db2Member = aliasTable[i][0]
                            dsgMember.id = aliasTable[i][1]
                            dsgMember.subsys = aliasTable[i][2]
                            dsgMember.cmdPref = aliasTable[i][3]
                            dsgMember.status = aliasTable[i][4]
                            dsgMember.db2Level = aliasTable[i][5]
                            dsgMember.systemName = aliasTable[i][6]
                            dsgMember.irlmSubsys = aliasTable[i][7]
                            dsgMember.irlmProc = aliasTable[i][8]
                            dsg.members.append(dsgMember)
        dsgs.append(dsg)
    return dsgs

def ev5_databasesByDsnRexxOutput(ls, db2SubsystemName):
    ## SELECT NAME, CREATOR, ENCODING_SCHEME FROM SYSIBM.SYSDATABASE
    dbs = [] # [name, creator, encoding]
    output = ls.evExecDb2Query(db2SubsystemName, _QRY_DATABASE)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        for i in range(1, len(output.cmdResponseList)):
            if len(output.cmdResponseList[i]) == 5:
                if isNotNull(output.cmdResponseList[i][0]):
                    dbs.append(output.cmdResponseList[i])
    return dbs

def ev6_tableSpacesByDsnRexxOutput(ls, db2SubsystemName):
    tbs = [] # [name, status, type, encoding, pgSize, dsSize, nTables, nPartitions, created]
    tbsDict = {} # {name:[name, status, type, encoding, pgSize, dsSize, nTables, nPartitions, created]}
    output = ls.evExecDb2Query(db2SubsystemName, _QRY_TABLESPACES)
    if output.isSuccess() and len(output.cmdResponseList) > 0:
        tbs = output.getDb2ValuesForColumns('NAME', 'STATUS', 'TYPE', 'ENCODING_SCHEME', 'PGSIZE', 'DSSIZE', 'NTABLES', 'PARTITIONS', 'CREATEDTS')

    for tb in tbs:
        if isNotNull(tb) and isNotNull(tb[0]):
            tbsDict[tb[0]] = tb
    return tbsDict

def ev7_checksubsysstatus (ls, ssid):
    db2up = 1
    output = ls.evMvsCmd("D A," + ssid + "MSTR")
    cmdResponse = output.cmdResponseList

    for line in cmdResponse:
        if line.find('NOT FOUND') != -1:
            db2up = 0
        
   
    return db2up




def osh_createDb2SubsystemOsh(lparOsh, db2Subsystem):
    str_name = 'name'
    str_discovered_product_name = 'discovered_product_name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'
        str_discovered_product_name = 'data_name' # duplicated on purpose

    db2SubsystemOsh = ObjectStateHolder('mainframe_subsystem')
    db2SubsystemOsh.setAttribute(str_name, db2Subsystem[0])
    db2SubsystemOsh.setAttribute(str_discovered_product_name, db2Subsystem[0])
    db2SubsystemOsh.setAttribute('type', 'DB2')
    db2SubsystemOsh.setAttribute('initialization_routine', db2Subsystem[1])      #INITRTN
    db2SubsystemOsh.setAttribute('initialization_parameters', db2Subsystem[2])   #INITPARM
    db2SubsystemOsh.setAttribute('command_prefix', db2Subsystem[3])
    db2SubsystemOsh.setContainer(lparOsh)
    return db2SubsystemOsh

def osh_createDdfOsh(db2SubsystemOsh, ddfObj):
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'

    _vector = ObjectStateHolderVector()
    if isNotNull(ddfObj.locationName):
        ddfOsh = ObjectStateHolder('db2_ddf')
        ddfOsh.setAttribute(str_name, ddfObj.locationName)
        ddfOsh.setAttribute('ddf_status', ddfObj.status)
        ddfOsh.setAttribute('ddf_luname', ddfObj.locationLuName)
        ddfOsh.setAttribute('ddf_generic_luname', ddfObj.locationGenericLuName)
        ddfOsh.setAttribute('ddf_ip_address', ddfObj.ipAddress)
        if isNotNull(ddfObj.ipAddress) and isnumeric(ddfObj.ipAddress):
            ddfOsh.setAttribute('ddf_tcp_port', int(ddfObj.tcpPort))
        ddfOsh.setAttribute('ddf_sql_domain', ddfObj.sqlDomain)
        ddfOsh.setContainer(db2SubsystemOsh)
        _vector.add(ddfOsh)
        for alias in ddfObj.ddfAlias:
            ddfAliasOsh = ObjectStateHolder('db2_ddf_alias')
            ddfAliasOsh.setAttribute(str_name, alias.aliasName)
            if isNotNull(alias.aliasPort) and isnumeric(alias.aliasPort):
                ddfAliasOsh.setIntegerAttribute('ddf_alias_port', int(alias.aliasPort))
            ddfAliasOsh.setContainer(ddfOsh)
            _vector.add(ddfAliasOsh)
    return _vector

def osh_createLocationOsh(db2SubsystemOsh, location):
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'

    locationOsh = ObjectStateHolder('db2_location')
    locationOsh.setAttribute(str_name, location[0])
    locationOsh.setAttribute('location_link_name', location[1])
    locationOsh.setAttribute('location_port', location[2])
    locationOsh.setAttribute('location_db_alias', location[3])
    locationOsh.setContainer(db2SubsystemOsh)
    return locationOsh

def osh_createDsgAndMemberOsh(db2SubsystemName, db2SubsystemOsh, dsg):
    str_name = 'name'
    str_membership = 'membership'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'
        str_membership = 'member'

    _vector = ObjectStateHolderVector()
    if isNotNull(dsg) and isNotNull(dsg.name):
        dsgOsh = ObjectStateHolder('db2_datasharing_group')
        dsgOsh.setAttribute(str_name, dsg.name)
        dsgOsh.setAttribute('group_attach_name', dsg.attachName)
        dsgOsh.setAttribute('group_mode', dsg.mode)
        if isNotNull(dsg.level) and isnumeric(dsg.level):
            dsgOsh.setIntegerAttribute('group_level', int(dsg.level))
        if isNotNull(dsg.protocolLevel) and isnumeric(dsg.protocolLevel):
            dsgOsh.setIntegerAttribute('group_protocol_level', int(dsg.protocolLevel))
        _vector.add(dsgOsh)
        for member in dsg.members:
            if isNotNull(member) and isNotNull(member.db2Member) and isNotNull(member.subsys) and upper(member.subsys) == db2SubsystemName:
                dsgMemberOsh = ObjectStateHolder('db2_datasharing_group_member')
                dsgMemberOsh.setAttribute(str_name, member.db2Member)
                dsgMemberOsh.setAttribute('member_id', member.id)
                dsgMemberOsh.setAttribute('member_level', member.db2Level)
                dsgMemberOsh.setAttribute('member_status', member.status)
                dsgMemberOsh.setContainer(db2SubsystemOsh)
                _vector.add(dsgMemberOsh)

                # if DSG Member available, make subsystem member of DSB --------s
                memberLinkOsh = modeling.createLinkOSH(str_membership, dsgOsh, db2SubsystemOsh)
                _vector.add(memberLinkOsh)
    return _vector

def osh_createDb2Schema(db2SubsystemOsh, db):
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'

    if isNotNull(db) and isNotNull(db[0]):
        db2DbOsh = ObjectStateHolder('mainframe_db2_database')
        db2DbOsh.setAttribute(str_name, db[0])
        db2DbOsh.setAttribute('creator', db[1])
        db2DbOsh.setAttribute('stgroup', db[2])
        db2DbOsh.setAttribute('encoding_scheme', db[3])
        db2DbOsh.setAttribute('createdate', db[4])
        db2DbOsh.setContainer(db2SubsystemOsh)
        return db2DbOsh

def osh_createDb2Tablespace(db2SubsystemOsh, tb):
    str_name = 'name'
    if UCMDB_VERSION < 9:
        str_name = 'data_name'

    if isNotNull(tb) and isNotNull(tb[0]):
        tbOsh = ObjectStateHolder('mainframe_db2_tablespace')
        tbOsh.setAttribute(str_name, tb[0])
        tbOsh.setAttribute('dbtablespace_status', tb[1])
        tbOsh.setAttribute('type', tb[2])
        tbOsh.setAttribute('encoding_scheme', tb[3])
        tbOsh.setAttribute('dbtablespace_initialextent', tb[4])
        if isNotNull(tb[5]) and isnumeric(tb[5]):
            tbOsh.setIntegerAttribute('max_dataset_size', int(tb[5]))
        if isNotNull(tb[6]) and isnumeric(tb[6]):
            tbOsh.setIntegerAttribute('number_tables', int(tb[6]))
        if isNotNull(tb[7]) and isnumeric(tb[7]):
            tbOsh.setIntegerAttribute('number_partitions', int(tb[7]))
        try:
            if len(tb[8]) > 19:
                tb[8] = tb[8][0:18]
                created = modeling.getDateFromString(tb[8], 'yyyy-MM-dd-kk.mm.ss', None)
                tbOsh.setDateAttribute('create_date', created)
        except:
            logger.debug("Ignoring create_date. Unable to parse date string")
        tbOsh.setContainer(db2SubsystemOsh)
        return tbOsh
    return None

def processDb2Subsystem(ls, Framework, lparOsh, lparname, useDsnRexx = 1):
    _vector = ObjectStateHolderVector()

    # get DB2 subsystems -------------------------------------------------------
    db2Subsystems = ev1_subsystemOutput(ls)
    #db2Subsystems = [['DB9G', 'DSN3INI', 'DSN3EPX,-DB9G,S', '-DB9G']]

    for db2 in db2Subsystems:
        # Verify that the DB2 is active prior to doing any Discovery
        db2up = ev7_checksubsysstatus (ls, db2[0] )
        if not db2up:
            logger.warn("DB2 subsystem " + db2[0] + " not active")
            continue
        # Verify this DB2 is running on this LPAR. If in a Sysplaex it could be on a differnt LPAR
        str_name = 'name'
        str_discovered_product_name = 'discovered_product_name'
        if UCMDB_VERSION < 9:
            str_name = 'data_name'
            str_discovered_product_name = 'data_name' # duplicated on purpose

        # create DB2 subsystem OSH ---------------------------------------------
        db2SubsystemOsh = osh_createDb2SubsystemOsh(lparOsh, db2)
        _vector.add(db2SubsystemOsh)

        if isNotNull(db2[0]) and isNotNull(db2[3]):
            name = db2[0]
            cmd_prefix = db2[3]

            createDDF = Framework.getParameter('discover_DDF')
            if isNotNull(createDDF) and string.lower(createDDF) == 'true':
                ''' get DDF and DDF alias info '''
                ddfObjs = ev2_ddfOutput(ls, cmd_prefix)

                ''' create DDF and alias OSH '''
                for ddfObj in ddfObjs:
                    _vector.addAll(osh_createDdfOsh(db2SubsystemOsh, ddfObj))

            createLocations = Framework.getParameter('discover_Locations')
            if isNotNull(createLocations) and string.lower(createLocations) == 'true':
                ''' get location info '''
                locations = ev3_locationOutput(ls, name)

                ''' create location OSH '''
                for location in locations:
                    _vector.add(osh_createLocationOsh(db2SubsystemOsh, location))

            createDsgs = Framework.getParameter('discover_DataSharingGroups')
            if isNotNull(createDsgs) and string.lower(createDsgs) == 'true':
                ''' get the db2 datasharing groups '''
                dsgs = ev4_dataSharingGroupsOutput(ls, cmd_prefix)

                ''' create DSG and member OSH '''
                for dsg in dsgs:
                    _vector.addAll(osh_createDsgAndMemberOsh(name, db2SubsystemOsh, dsg))

            createDbs = Framework.getParameter('discover_Databases')
            if isNotNull(createDbs) and string.lower(createDbs) == 'true':
                ''' get the mainframe DB2 databases '''
                dbs = [] # [name, creator, storageGroup, encoding, created]
                if useDsnRexx:
                    dbs = ev5_databasesByDsnRexxOutput(ls, name)
                    for db in dbs:
                        db2Osh = osh_createDb2Schema(db2SubsystemOsh, db)
                        if isNotNull(db2Osh):
                            _vector.add(db2Osh)

            createTbs = Framework.getParameter('discover_Tablespaces')
            if isNotNull(createTbs) and string.lower(createTbs) == 'true':
                ''' get the mainframe DB2 table spaces '''
                tbs = [] # [name, status, type, encoding, pgSize, dsSize, nTables, nPartitions, created]
                if useDsnRexx:
                    tbs = ev6_tableSpacesByDsnRexxOutput(ls, name)

                    ''' create tablespace OSH '''
                    for (tbName, tb) in tbs.items():
                        tbOsh = osh_createDb2Tablespace(db2SubsystemOsh, tb)
                        if isNotNull(tbOsh):
                            _vector.add(tbOsh)

    return _vector


'''
MAIN
'''

'''
* Flow of discovery -
    - DB2 Subsystem
    - DDF and alias
    - Location
    - DSG and member
    - DB2 databases
    - Tablespaces

'''

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    lparname = None
    # create LPAR node
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    lparOsh = None
    if eview_lib.isNotNull(hostId):
        lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)

    ls = eview_lib.EvShell(Framework)
    lparname = Framework.getTriggerCIData('LparName')
    OSHVResult = processDb2Subsystem(ls, Framework, lparOsh, lparname)
    ls.closeClient()


    return OSHVResult