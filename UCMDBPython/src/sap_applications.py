#coding=utf-8
from java.io import File
from java.io import FileReader
import sapappsutils
import saputils
import logger
import modeling

from java.util import Properties
from java.util import HashMap
from java.text import ParsePosition
from java.text import SimpleDateFormat

from org.jdom.input import SAXBuilder

from appilog.common.utils import Protocol
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types.classmodel import CITRoot

from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from com.mercury.erp.sap.inspection import NoSuchChangeException

from java.lang import NoClassDefFoundError
from java.lang import ExceptionInInitializerError
from com.hp.ucmdb.discovery.library.clients import MissingJarsException
from com.hp.ucmdb.discovery.library.clients.query import SAPQueryClient
import sap
import sap_abap

def activeTransactions(sapUtils,mapDevcToOSH,siteOSH, SYSNAME, OSHVResult):
    transTable = sapUtils.getActiveTransactions()
    for trans in transTable:
        name = trans.getProperty('data_name')
        steps = trans.getProperty('dialog_steps')
        responseTime = trans.getProperty('total_response_time')
        averageResponseTime = trans.getProperty('average_response_time')
        cpuTime = trans.getProperty('total_cpu_time')
        averageCpuTime = trans.getProperty('average_cpu_time')
        dbTime = trans.getProperty('total_db_time')
        averageDbTime = trans.getProperty('average_db_time')
        users = trans.getProperty('saptransaction_averagedbtime')
        devclass = trans.getProperty('devclass')
        program = trans.getProperty('program')
        screen = trans.getProperty('screen')
        version = trans.getProperty('version')

        devcOSH = mapDevcToOSH.get(devclass)
        if devcOSH != None:
            addAppCompHierarchy(devcOSH, OSHVResult)
            transOSH = buildTransaction(name,devclass,program,screen,version,devcOSH,siteOSH, SYSNAME, OSHVResult)
            transOSH.setLongAttribute('dialog_steps', steps)
            transOSH.setLongAttribute('total_response_time', responseTime)
            transOSH.setLongAttribute('average_response_time', averageResponseTime)
            transOSH.setLongAttribute('total_cpu_time', cpuTime)
            transOSH.setLongAttribute('average_cpu_time', averageCpuTime)
            transOSH.setLongAttribute('total_db_time', dbTime)
            transOSH.setLongAttribute('average_db_time', averageDbTime)
        else:
            logger.warn('devclass [', name, '] is not found for transaction')


def transactions(sapUtils,mapDevcToOSH,siteOSH, SYSNAME, OSHVResult):
    trans = sapUtils.getTransactions()
    for tran in trans:
        name = tran.getProperty('data_name')
        devclass = tran.getProperty('devclass')
        devcOSH = mapDevcToOSH.get(devclass)
        if devcOSH != None:
            addAppCompHierarchy(devcOSH, OSHVResult)
            buildTransaction(name,devclass,"","","",devcOSH, siteOSH, SYSNAME, OSHVResult)
        else:
            logger.warn('devclass [',name,'] is not found for transaction')

def buildTransport(changeRequest,date,time,user,targetSystem,changeDescription,status, siteOSH, OSHVResult):
    transportOSH = ObjectStateHolder('sap_transport')
    transportOSH.setAttribute('data_name', changeRequest)
    transportOSH.setAttribute('date', date)
    transportOSH.setAttribute('user', user)
    transportOSH.setAttribute('target_system', targetSystem)
    transportOSH.setAttribute('description', changeDescription)
    transportOSH.setAttribute('status', 'N\A')
    transportOSH.setContainer(siteOSH)
    OSHVResult.add(transportOSH)

    # need to make update on the same object to generate change event in CMDB
    if status == '':
        status = 'N\A'

    transportOSH = ObjectStateHolder('sap_transport')
    transportOSH.setAttribute('data_name', changeRequest)
    transportOSH.setAttribute('status', status)
    transportOSH.setContainer(siteOSH)
    OSHVResult.add(transportOSH)

    return transportOSH

def buildTransaction(name, devc, program, screen, version, devcOSH,siteOSH, SYSNAME, OSHVResult):
    transOSH = ObjectStateHolder('sap_transaction')
    transOSH.setAttribute('data_name', name)
    transOSH.setAttribute('devclass', devc)
    transOSH.setAttribute('program', program)
    transOSH.setAttribute('screen', screen)
    transOSH.setAttribute('version', version)
    transOSH.setAttribute('system_name', SYSNAME)
    transOSH.setContainer(siteOSH)

    OSHVResult.add(transOSH)
    OSHVResult.add(modeling.createLinkOSH('contains',devcOSH,transOSH))
    return transOSH

def addAppCompHierarchy(devcOSH, OSHVResult):
#	print "addAppCompHierarchy devcOSH xml:"
#	print devcOSH.toXmlString()
    OSHVResult.add(devcOSH)
    container = devcOSH.getAttribute(CITRoot.ATTR_ROOT_CONTAINER)
    if (container != None):
        if (container.getValue() != None):
            addAppCompHierarchy(container.getValue(), OSHVResult)

# build application Hierarchy based on sap-application-components.xml
def readModules():
    mapCategoryToAppComponent = HashMap()
    try:
        builder = SAXBuilder(0)
        separator = CollectorsParameters.FILE_SEPARATOR
        fileLocation = CollectorsParameters.BASE_PROBE_MGR_DIR + separator + 'discoveryResources' + separator + 'sap-application-components.xml'
        doc = builder.build(FileReader(File(fileLocation)))
        root = doc.getRootElement()
        categories = root.getChildren('category')
        if categories != None:
            itCat = categories.iterator()
            while itCat.hasNext():
                categoryElem = itCat.next()
                category = categoryElem.getAttributeValue('name')
                applicationComponents = categoryElem.getChildren('application-component')
                itComp = applicationComponents.iterator()
                while itComp.hasNext():
                    component = itComp.next().getAttributeValue('name')
                    mapCategoryToAppComponent.put(component,category)
    except:
        logger.errorException('Failed to read modules')
    return mapCategoryToAppComponent

# build application Hierarchy based on sap-application-components.xml file and application component transaction using RS_COMPONENT_VIEW function based on transaction SE81 (TODO: document the relation between both)
# The purpose of the categories is to reduce number of nodes in the upper level.
# Retrieve application components hierarchy.
def buildAppHierarchy(sapUtils, systemOSH, report_app_components):
    mapCategoryToAppComponent = readModules()
    appTable = sapUtils.getApplicationHierarchy()
    # keep devclass OSH to connect transaction OSH
    mapDevcToOSH = HashMap()
    # use this map to build hierarchy (keep parent OSHs)
    mapIdToOSH = {}
    oshs = []
    for app in appTable:
        # read all fields
        appId = app.getProperty('id')
        appType = app.getProperty('type')
        name = app.getProperty('data_name')
        parent = app.getProperty('parent')
        description = app.getProperty('description')
        categoryOSH = None
        if appType == 'HF':
            category = mapCategoryToAppComponent.get(name)
            if category != None:
                categoryOSH = ObjectStateHolder('sap_application_component')
                categoryOSH.setAttribute('data_name', category)
                categoryOSH.setAttribute('short_name', category)
                categoryOSH.setAttribute('type', appType)
                categoryOSH.setAttribute('description', category)

        appOSH = ObjectStateHolder('sap_application_component')
        appOSH.setAttribute('data_name', name)
        appOSH.setAttribute('short_name', name)
        appOSH.setAttribute('type', appType)
        appOSH.setAttribute('description', description)
        mapIdToOSH[appId] = (appOSH, categoryOSH, parent, appType)

    for appId, (appOSH, categoryOSH, parent, appType) in mapIdToOSH.iteritems():
        if parent != None:
            parentData = mapIdToOSH.get(parent)
            if parentData != None:
                parentOSH, _, _, _ = parentData 

                if categoryOSH != None:
                    categoryOSH.setContainer(parentOSH)
                    parentOSH = categoryOSH

                appOSH.setContainer(parentOSH)

                # Devclasses have type 'DEVC' (devclass)
                # Parents of devclasses have type HF-DEVC
                # The rest has HF type
                if 'DEVC' == appType:
                    mapDevcToOSH.put(name, appOSH)
                    parentOSH.setAttribute('type', 'HF-DEVC')

            else:
                appOSH.setContainer(systemOSH)
            # check if need to send all the application components
            if report_app_components:
                # this check was meant to prevent DEVC reporting
#               if appType != 'DEVC' or parentData == None:
                oshs.append(appOSH)
                if parentData != None and categoryOSH != None:
                    oshs.append(categoryOSH)

    return mapDevcToOSH, oshs

def transactionChange(sapUtils, mapDevcToOSH, siteOSH, SYSNAME, OSHVResult):
    mapTransportToOSH = HashMap()
    transactionChange = sapUtils.getTransactionChange()
    count = transactionChange.getRowCount()
    for row in range(count):
        # read all fields
        transaction = transactionChange.getCell(row,0)
        devc = transactionChange.getCell(row,1)
        objectName = transactionChange.getCell(row,2)
        objectType = transactionChange.getCell(row,3)
        objectDescription = transactionChange.getCell(row,4)
        changeDescription = transactionChange.getCell(row,5)
        date = transactionChange.getCell(row,6)
        time = transactionChange.getCell(row,7)
        user = transactionChange.getCell(row,8)
        status = transactionChange.getCell(row,9)
        changeRequest = transactionChange.getCell(row,10)
        program = transactionChange.getCell(row,12)
        screen = transactionChange.getCell(row,13)
        programVersion = transactionChange.getCell(row,14)
        targetSystem = transactionChange.getCell(row,15)
        if logger.isDebugEnabled():
            logger.debug('--------------------------------------------')
            logger.debug('changeDescription = ', changeDescription)
            logger.debug('objectType = ', objectType)
            logger.debug('objectName = ', objectName)
            logger.debug('objectDescription = ', objectDescription)
            logger.debug('date = ', date)
            logger.debug('time = ', time)
            logger.debug('user = ', user)
            logger.debug('--------------------------------------------')

        sfDate = SimpleDateFormat('yyyy-MM-dd HH:mm:ss')
        dateObj = sfDate.parse(date + ' ' + time,ParsePosition(0))

        if devc is not None:
            devcOSH = mapDevcToOSH.get(devc)
            if devcOSH != None:

                # In case the application components were filtered then we need to send only the relevant
                # application components for this transport
                addAppCompHierarchy(devcOSH, OSHVResult)
                transactionOSH = buildTransaction(transaction, devc, program, screen, programVersion, devcOSH, siteOSH, SYSNAME, OSHVResult)
                ticketStatus = ''
                #
                # L - Modifiable
                # D - Modifiable, Protected
                if status == 'L' or status == 'D':
                    # (1) = Plan
                    # (9) = Critical
                    ticketStatus = 'In progress'
                else:
                    # (2) = New change
                    # (7) = Major
                    ticketStatus = 'Closed'

                transportOSH = mapTransportToOSH.get(changeRequest)
                if transportOSH == None:
                    transportOSH = buildTransport(changeRequest,dateObj,time,user,targetSystem,changeDescription,ticketStatus, siteOSH, OSHVResult)
                    mapTransportToOSH.put(changeRequest,transportOSH)
                OSHVResult.add(modeling.createLinkOSH('contains',transactionOSH,transportOSH));
                changeOSH = createTransportChange(transaction,objectType,objectName,transportOSH, OSHVResult)
                OSHVResult.add(modeling.createLinkOSH('use',changeOSH,transactionOSH));
            else:
                logger.warn('can not find devclass OSH for [', devc, ']')

def createTransportChange(transaction,objectType,objectName,transportOSH, OSHVResult):
    changeOSH = ObjectStateHolder('sap_transport_change')
    changeOSH.setAttribute('data_name', objectType + ':' + objectName)
    changeOSH.setAttribute('object_type', objectType)
    changeOSH.setAttribute('object_name', objectName)
    changeOSH.setContainer(transportOSH)
    OSHVResult.add(changeOSH)
    return changeOSH


#-------------------------------
# 		Main
#-------------------------------
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    SYSNAME = Framework.getDestinationAttribute('system_name')
    GET_TX_ACTIVE = Framework.getParameter('getActiveTransactions') == 'true'
    GET_TX_CHANGE = Framework.getParameter('getTransChanges') == 'true'
    GET_TX_ALL = Framework.getParameter('getAllTransactions') == 'true'
    report_app_components = Framework.getParameter('getAppComponents') == 'true'

    properties = Properties()
    instance_number =  Framework.getDestinationAttribute('instance_nr')
    ip_address =  Framework.getDestinationAttribute('ip_address')
    connection_client =  Framework.getDestinationAttribute('connection_client')
    logger.debug('Connecting to a SAP system number:', str(instance_number))
    properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER, instance_number)
    if (connection_client is not None) and (connection_client != 'NA'):
        logger.debug('Connecting to a SAP system with client:', str(connection_client))
        properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT, connection_client)
    if GET_TX_CHANGE:
        # get transaction change only parameters
        FROM_DATE = Framework.getParameter('transChangesFromDate')
        FROM_TIME = Framework.getParameter('transChangesFromTime')
        TO_DATE = Framework.getParameter('transChangesToDate')
        TO_TIME = Framework.getParameter('transChangesToTime')
        INTERVAL = Framework.getParameter('transChangesDaysInterval')

        if logger.isDebugEnabled():
            logger.debug('FROM_DATE = ', FROM_DATE)
            logger.debug('FROM_TIME = ', FROM_TIME)
            logger.debug('TO_DATE = ', TO_DATE)
            logger.debug('TO_TIME = ', TO_TIME)

        properties.setProperty(SAPQueryClient.PARAM_FROM_DATE,FROM_DATE)
        properties.setProperty(SAPQueryClient.PARAM_FROM_TIME,FROM_TIME)
        properties.setProperty(SAPQueryClient.PARAM_TO_DATE,TO_DATE)
        properties.setProperty(SAPQueryClient.PARAM_TO_TIME,TO_TIME)
        if ( (INTERVAL != None) and (INTERVAL != '0') and (INTERVAL != '') ):
            properties.setProperty(SAPQueryClient.PARAM_INTERVAL,INTERVAL)

    loadOnInit = 0
    if GET_TX_ACTIVE:
        properties.setProperty(SAPQueryClient.PARAM_FLAG_GET_USERS,'false')
        loadOnInit = 1

    errormsg = ''
    client = None
    try:
        try:
            # create SAP client
            client = Framework.createClient(properties)
            sapUtils = sapappsutils.SapAppsUtils(client, loadOnInit, saputils.SapUtils.NO_LOAD)
        except (NoClassDefFoundError, MissingJarsException, ExceptionInInitializerError):
            errormsg = 'SAP drivers are missing'
            logger.debugException(errormsg)
        except:
            errormsg = 'Connection failed'
            logger.debugException(errormsg)
        else:
            systemOsh, oshs = sap_abap.report_system(SYSNAME, instance_number, ip_address)
            OSHVResult.addAll(oshs)

            # Check if we need to collect all the application component.
            # (we can discover up to 60000 CIs per System - don't discover if it is not needed)
            if not report_app_components:
                logger.debug('Not sending application components to server')

            # build the application hierarchy even if not all of it is sent to the server
            mapDevcToOSH = None
            if GET_TX_CHANGE or GET_TX_ALL or GET_TX_ACTIVE or report_app_components:
                mapDevcToOSH, oshs = buildAppHierarchy(sapUtils, systemOsh, report_app_components)
                OSHVResult.addAll(oshs)

            # Check if we need to collect the changed transactions
            if GET_TX_CHANGE:
                try:
                    logger.debug('Getting transaction change...')
                    transactionChange(sapUtils, mapDevcToOSH, systemOsh, SYSNAME, OSHVResult)
                except NoSuchChangeException:
                    Framework.reportWarning('No changes found in the given time range')
                except:
                    logger.errorException('Failed retrieving transactions change')
                    Framework.reportError('Failed retrieving transactions change')

            # Check if we need to collect all the transactions
            if GET_TX_ALL:
                try:
                    logger.debug('Getting all transactions...')
                    transactions(sapUtils, mapDevcToOSH, systemOsh, SYSNAME, OSHVResult)
                except:
                    logger.errorException('Failed to get transactions')
                    Framework.reportWarning('Failed to get transactions')

            # Check if we need to collect the active transactions
            if GET_TX_ACTIVE:
                try:
                    logger.debug('Getting active transactions...')
                    activeTransactions(sapUtils, mapDevcToOSH, systemOsh, SYSNAME, OSHVResult)
                except:
                    logger.errorException('Failed retrieving active transactions')
                    Framework.reportError('Failed retrieving active transactions')
    finally:
        if client is not None:
            client.close()
        if errormsg:
            Framework.reportError(errormsg)
    return OSHVResult
