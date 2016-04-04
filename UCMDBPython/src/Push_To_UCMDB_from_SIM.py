#coding=utf-8
########################
# Push_To_Ucmdb.py
# author: K. Chhina
########################
import sys
import logger
import modeling
import traceback

from ext.MamUtils import MamUtils
from java.io import File
from org.jdom.input import SAXBuilder
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      VARIABLES             ##########
##############################################
SCRIPT_NAME = "Push_To_UCMDB_From_SIM.py"
mam_utils = MamUtils(SCRIPT_NAME + ' ')
dataTypeMap = {'StrProp':'String', 'StrListProp':'StringList', 'DoubleProp':'Double', 'IntProp':'Integer', 'BoolProp':'Boolean', 'LongProp':'Long'}
ucmdb8to9interfaceAttributeMap = {'interface_macaddr':'mac_address', 'data_name':'interface_name', 'data_description':'interface_description'}
windowsOsToVersionMap = {'7':'6.1', '2008 R2':'6.1', '2008':'6.0', 'Vista':'6.0', '2003':'5.2', 'XP 64':'5.2', 'XP':'5.1', '2000':'5.0'}

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str, args))


####################################
##  Convenient print info method  ##
####################################
def info(msg):
    if mam_utils.isInfoEnabled():
        mam_utils.info(msg)

#####################################
##  Convenient print debug method  ##
#####################################
def debug(msg):
    if mam_utils.isDebugEnabled():
        mam_utils.debug(msg)


def createOshFromId(ciDict, id):
    osh = None
    object = ciDict[id]
    # create the container osh
    if object != None:
        #logger.info(parent)
        id = object[0]
        type = object[1]
        props = object[2]
        osh = ObjectStateHolder(type)
        if props != None:
            for prop in props:
                #logger.info(parentProp)
                setAttribute(prop, osh)
    return osh


def processObjects(allObjects, ignoredCiTypes, ucmdb_version):
    vector = ObjectStateHolderVector()
    iter = allObjects.iterator()
    #ciList = [[id, type, props]]
    ciList = []
    ciDict = {}
    createCi = 1
    logger.info("Following CI types will be ignored: %s" % ignoredCiTypes)
    while iter.hasNext():
        #attributes = [name, type, key, value]
        attributes = []
        nodeRoleAttribute = ''
        osInstallType = ''
        objectElement = iter.next()
        mamId = objectElement.getAttribute('mamId').getValue()
        cit = objectElement.getAttribute('name').getValue()
        ## Skip memory CITs in 9.x
        if cit == 'memory':
            continue
        # Skip CIs defined in ignoredCiTypes
        if cit in ignoredCiTypes:
            continue
        if mamId != None and cit != None:
            # add the attributes...
            allAttributes = objectElement.getChildren('field')
            iterAtt = allAttributes.iterator()
            while iterAtt.hasNext():
                attElement = iterAtt.next()
                attName = attElement.getAttribute('name').getValue()
                #print 'GOT TYPE: ', attType
                attKey = attElement.getAttribute('key')
                attValue = attElement.getText()
                attType = attElement.getAttribute('datatype').getValue()

                ## Reset interface attribute names for UCMDB 9
                if cit == 'interface' and attName in ucmdb8to9interfaceAttributeMap.keys():
                    attName = ucmdb8to9interfaceAttributeMap[attName]
                ## Skip attributes not present in UCMDB 9
                if attName == 'cpu_speed' or attName == 'host_osinstalltype':
                    continue
                ## Set node role based on OS or model
                if attName == 'host_os' and attValue:
                    nodeRoleAttribute = 'server'
                    if attValue.lower().find('xp')>-1 or attValue.lower().find('vista')>-1 or attValue.lower().find('professional')>-1 or attValue.lower().find('windows 7')>-1:
                        nodeRoleAttribute = 'desktop'
                if attName == 'host_model' and attValue:
                    nodeRoleAttribute = 'server'
                    if attValue.lower().find('vmware')>-1 or attValue.lower().find('zone')>-1 or attValue.lower().find('virtual')>-1:
                        nodeRoleAttribute = 'virtualized_system'
                ## Set Host OS install Type to match HC jobs
                if attName == 'host_os' and attValue:
                    if attValue.lower().find('hp-ux')>-1 or attValue.lower().find('hpux')>-1:
                        osInstallType = 'HPUX'
                    elif attValue.lower().find('aix')>-1:
                        osInstallType = 'AIX'
                    elif attValue.lower().find('solaris')>-1 or attValue.lower().find('sun')>-1:
                        osInstallType = 'Solaris'
                    elif attValue.lower().find('linux')>-1 or attValue.lower().find('redhat')>-1:
                        osInstallType = 'Linux'
                    elif attValue.lower().find('enterprise x64 edition')>-1:
                        osInstallType = 'Server Enterprise x64 Edition'
                    elif attValue.lower().find('enterprise edition')>-1:
                        osInstallType = 'Server Enterprise Edition'
                    elif attValue.lower().find('server enterprise')>-1:
                        osInstallType = 'Server Enterprise'
                    elif attValue.lower().find('enterprise')>-1:
                        osInstallType = 'Enterprise'
                    elif attValue.lower().find('professional')>-1:
                        osInstallType = 'Professional'
                    elif attValue.lower().find('standard edition')>-1:
                        osInstallType = 'Server Standard Edition'
                    elif attValue.lower().find('standard')>-1:
                        osInstallType = 'Server Standard'
                    elif attValue.lower().find('server')>-1:
                        osInstallType = 'Server'
                    elif attValue.lower().find('business')>-1:
                        osInstallType = 'Business'
                ## Set OS Release to match HC jobs
                if attName == 'host_osrelease' and attValue and attValue.rfind('.')>-1:
                    attValue = attValue[attValue.rfind('.')+1:]
                ## Set Host OS to match HC jobs
                if attName == 'host_os' and attValue:
                    if attValue.lower().find('2003')>-1:
                        attValue = 'Windows 2003'
                    elif attValue.lower().find('2008')>-1:
                        attValue = 'Windows 2008'
                    elif attValue.lower().find('2008 R2')>-1:
                        attValue = 'Windows 2008 R2'
                    elif attValue.lower().find('2000')>-1:
                        attValue = 'Windows 2000'
                    elif attValue.lower().find('windows 7')>-1:
                        attValue = 'Windows 7'
                    elif attValue.lower().find('vista')>-1:
                        attValue = 'Windows Vista'
                    elif attValue.lower().find('xp')>-1:
                        attValue = 'Windows XP'
                    elif attValue.lower().find('aix')>-1:
                        attValue = 'AIX'
                    elif attValue.lower().find('solaris')>-1 or attValue.lower().find('sun')>-1:
                        attValue = 'Solaris'
                    elif attValue.lower().find('redhat')>-1 or attValue.lower().find('linux')>-1:
                        attValue = 'Linux'
                    elif attValue.lower().find('hp-ux')>-1 or attValue.lower().find('hpux')>-1:
                        attValue = 'HP-UX'
                    else:
                        attValue = ''

                if attType == None or attType == "":
                    attType = "string"
                if attKey == None or attKey == "":
                    attKey = "false"
                else:
                    attKey = attKey.getValue()
                if attName != "" and attType != "":
                    attributes.append([attName, attType, attKey, attValue])
                # create CI or not? Is key empty or none?
                if attKey == "true":
#                    print 'KEY ATTRIB <', attName, '> with value <', attValue, '> for CIT <', cit, '> with MAMID <', mamId, '>'
                    if attValue != None and attValue.strip() != "":
                        createCi = 1
                    else:
                        createCi = 0
                        break
            ## Add node role and OS install type if available
            if nodeRoleAttribute:
                attributes.append(['node_role', 'StrListProp', 'false', nodeRoleAttribute])
            if osInstallType:
                attributes.append(['host_osinstalltype', 'StrProp', 'false', osInstallType])
            #info (concatenate("Id: ", mamId, ", Type: ", cit, ", Properties: ", attributes))
            if createCi == 1:
                ciList.append([mamId, cit, attributes])
                ciDict[mamId] = [mamId, cit, attributes]
    for ciVal in ciList:
        dontCreateCI = 0
        #info("\tAdding %s [%s] => [%s]" % (ciVal[1], ciVal[0], ciVal[2]) )
        id = ciVal[0]
        type = ciVal[1]
        osh = ObjectStateHolder(type)
        if ciVal[2] != None:
            props = ciVal[2]
            createContainer = 0
            containerOsh = None
            for prop in props:
                if prop[0] == 'root_container':
                    if dontCreateCI or prop[3] not in ciDict.keys():
                        dontCreateCI = 1
                        continue
                    parent = ciDict[prop[3]]
                    # create the container osh
                    if parent != None:
                        parentId = parent[0]
                        parentType = parent[1]
                        parentProps = parent[2]
                        containerOsh = ObjectStateHolder(parentType)
                        if parentProps != None:
                            for parentProp in parentProps:
                                setAttribute(parentProp, containerOsh)
                        createContainer = 1
                #print 'Props <', prop, '>'
                try:
                    setAttribute(prop, osh)
                    if createContainer == 1:
                        osh.setContainer(containerOsh)
                except:
                    stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
                    logger.warn('Exception setting attribute <', prop[0], '> with value <', prop[3], '>:\n', stacktrace)
                    pass
            if dontCreateCI:
                continue
        vector.add(osh)
    return (vector, ciDict)


def setAttribute(prop, osh):
    try:
        if prop[1] == 'StrProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setStringAttribute(prop[0], prop[3])
        elif prop[1] == 'StrListProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setListAttribute(prop[0], [prop[3]])
        elif prop[1] == 'DoubleProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setDoubleAttribute(prop[0], prop[3])
        elif prop[1] == 'FloatProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setFloatAttribute(prop[0], prop[3])
        elif prop[1] == 'IntProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setIntegerAttribute(prop[0], prop[3])
        elif prop[1] == 'LongProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setLongAttribute(prop[0], prop[3])
        elif prop[1] == 'BoolProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setBoolAttribute(prop[0], prop[3])
        elif prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
            osh.setAttribute(prop[0], prop[3])
    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        logger.warn('Exception setting attribute <', prop[0], '> with value <', prop[3], '>:\n', stacktrace)
        pass


def processLinks(allLinks, ciDict):
    vector = ObjectStateHolderVector()
    iter = allLinks.iterator()
    #relList = [[type, end1, end2]]
    relList = []
    while iter.hasNext():
        linkElement = iter.next()
        linkType = linkElement.getAttribute('targetRelationshipClass').getValue()
        linkId = linkElement.getAttribute('mamId').getValue()
        if linkId != None and linkType != None:
            # get the end points
            allAttributes = linkElement.getChildren('field')
            iterAtt = allAttributes.iterator()
            end1IdBase = None
            end2IdBase = None
            while iterAtt.hasNext():
                attElement = iterAtt.next()
                attName = attElement.getAttribute('name').getValue()
                if attName == 'DiscoveryID1':
                    end1IdBase = attElement.getText()
                if attName == 'DiscoveryID2':
                    end2IdBase = attElement.getText()
            if end1IdBase == None or end2IdBase == None:
                break
            relList.append([linkType, end1IdBase, end2IdBase])
            #info("Adding %s: End1: %s, End2: %s" % (linkType, end1IdBase, end2IdBase) )

    for relVal in relList:
        #info("\tAdding tempStr %s [%s --> %s]" % (relVal[0], relVal[1], relVal[2]) )
        linkType = relVal[0]
        linkEnd1 = relVal[1]
        linkEnd2 = relVal[2]

        if linkType != 'container_f' and linkEnd1 in ciDict.keys() and linkEnd2 in ciDict.keys():
            end1Osh = createOshFromId(ciDict, linkEnd1)
            end2Osh = createOshFromId(ciDict, linkEnd2)
            linkOsh = modeling.createLinkOSH(linkType, end1Osh, end2Osh)
            vector.add(linkOsh)
    return vector


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    fileSeparator = File.separator

    DebugMode = Framework.getParameter('DebugMode')
    userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + fileSeparator

    filePathDir = userExtDir + 'TQLExport' + fileSeparator + 'hpsim' + fileSeparator + 'results' + fileSeparator
    directory = File(filePathDir)
    files = directory.listFiles()

    if files == None:
        logger.warn('Results XML not found. Perhaps no data was received from SIM or an error occurred in the SIM_Discovery script.')
        return

    ## Read ignored Ci types from integration configuration
    ignoredCiTypes = []
    rawIgnoredCiTypes = Framework.getParameter('IgnoredCiTypes')
    tempIgnoredCiTypes = eval(rawIgnoredCiTypes)
    if tempIgnoredCiTypes is not None:
        for item in tempIgnoredCiTypes:
            item != 'None' and ignoredCiTypes.append(item)

    ## Identify UCMDB version
    ucmdbVersion = modeling.CmdbClassModel().version()

    try:
        ## Start the work
        for file in files:
            if file != None or file != '':
                builder = SAXBuilder()
                doc = builder.build(file)
                # Process CIs #
                info("Start processing CIs to update in the destination server...")
                allObjects = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                (objVector, ciDict) = processObjects(allObjects, ignoredCiTypes, ucmdbVersion)

                OSHVResult.addAll(objVector)
                # Process Relations #
                info("Start processing Relationships to update in the destination server...")
                allLinks = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
                linkVector = processLinks(allLinks, ciDict)
                OSHVResult.addAll(linkVector)
    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        info(concatenate('Failure: ():\n', stacktrace))

    if (DebugMode != None):
        DebugMode = DebugMode.lower()
        if DebugMode == "true":
            mam_utils.info ('[NOTE] UCMDB Integration is running in DEBUG mode. No data will be pushed to the destination server.')
            print OSHVResult.toXmlString()
            return None
        else:
            #print OSHVResult.toXmlString()
            return OSHVResult
