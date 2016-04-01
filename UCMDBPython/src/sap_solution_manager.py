#coding=utf-8
import sys

import logger
import modeling
import saputils

from java.util import Properties
from java.util import HashMap
from java.lang import Boolean
from java.util import ArrayList

from appilog.common.utils import Protocol
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.lang import NoClassDefFoundError
from java.lang import ExceptionInInitializerError
from java.lang import Exception as JException
from com.hp.ucmdb.discovery.library.clients import MissingJarsException
import sap_solman_discoverer
from sap_abap_discoverer import TableQueryExecutor
from iteratortools import first, findFirst
import re
from sap_solman_discoverer import discoverSystems
import errormessages


SCENARIO_PATTERNS = map(re.compile, ('Business Scenarios', 'Gesch.ftsszenarios'))
PROCESS_PATTERNS = map(re.compile, ('Business Processes', 'Gesch.ftsprozesse'))


def _isBusinessObject(name, patterns):
    for pattern in patterns:
        if pattern.search(name):
            return True
    return False


def _isBusinessScenario(id_name_tuple):
    name = id_name_tuple[1]
    return _isBusinessObject(name, SCENARIO_PATTERNS)


def _isBusinessProcess(id_name_tuple):
    name = id_name_tuple[1]
    return _isBusinessObject(name, PROCESS_PATTERNS)


def discoverNodeIdToName(execute, objectId):
    return discover_ids_and_name(execute, objectId, sap_solman_discoverer.GetProcessNodeById)


def discoverProcessStepNodeIdToName(execute, objectId):
    return discover_ids_and_name(execute, objectId, sap_solman_discoverer.GetProcessStepNodeById)


def discover_ids_and_name(execute, objectId, query):
    # REFTREE_ID, NODE_ID, REFNODE_ID
    ids_triplets = filter(lambda x: x[0], execute(query(objectId)))
    ref_tree_ids = [triplet[0] for triplet in ids_triplets]
    id_to_name_ids_triplet = []
    if ref_tree_ids:
        query = sap_solman_discoverer.GetNameOfStructure(ref_tree_ids)
        id_to_name_pairs = execute(query)
        for item in zip(ids_triplets, id_to_name_pairs):
            ref_tree_id, node_id, ref_node_id = item[0]
            _, name = item[1]
            id_to_name_ids_triplet.append((ref_tree_id, name, node_id, ref_node_id))
    return id_to_name_ids_triplet


def _discover_business_objects(framework, solman, component_to_system, should_discover_processes, should_discover_steps, reportCIsInChunks, sap_system_osh):
    queryExecutor = TableQueryExecutor(solman)
    execute = queryExecutor.executeQuery
    # get projects
    projects = execute(sap_solman_discoverer.GetProjects())
    processesByScenarioId = {}

    business_objects_tree = []

    for projectId, responsible in projects:
        # get project objects
        objectIds = execute(sap_solman_discoverer.GetProjectObjects(projectId))
        if not objectIds:
            continue
        objectId = first(objectIds)
        logger.debug("Project Name %s" % projectId)
        logger.debug("Project ObjectId %s" % objectId)
        project = BusinessProject(projectId, responsible, objectId)
        business_objects_tree.append(project)

        nameToIdPairs = discoverNodeIdToName(execute, objectId)
        scenarioInfo = findFirst(_isBusinessScenario, nameToIdPairs)
        if scenarioInfo:
            scenarioId, _, _, _ = scenarioInfo
            logger.debug("Scenario Structure ID %s" % scenarioId)
            businessScenarious = discoverNodeIdToName(execute, scenarioId)
            for sId, sName, s_node_id, s_ref_node_id in businessScenarious:

                logger.debug("Scenario Name %s" % sName)
                logger.debug("Scenario Node ID %s" % s_node_id)
                logger.debug("Scenario Ref. Node ID %s" % s_ref_node_id)
                logger.debug("Scenario Ref. Structure ID %s" % sId)

                scenario = BusinessScenario(sName, s_node_id, s_ref_node_id)
                project.add_child(scenario)

                if not should_discover_processes:
                    continue
                buisinessProcesses = discoverNodeIdToName(execute, sId)
                processInfo = findFirst(_isBusinessProcess, buisinessProcesses)
                if processInfo:
                    processId, _, _, _ = processInfo
                    logger.debug("Process Structure ID %s" % processId)
                    processes = discoverNodeIdToName(execute, processId)
                    processesByScenarioId[sName] = processes
                    for pId, pName, p_node_id, p_ref_node_id in processes:
                        logger.debug("Process Name %s" % pName)
                        logger.debug("Process Node ID %s" % p_node_id)
                        logger.debug("Process Ref. Node ID %s" % p_ref_node_id)
                        logger.debug("Process Ref. Structure ID %s" % pId)

                        process = BusinessProcess(pName, p_node_id)
                        scenario.add_child(process)

                        if not should_discover_steps:
                            continue
                        process_steps = discoverProcessStepNodeIdToName(execute, pId)
                        process_steps_tree = []
                        process_steps_tree.append(process)
                        if process_steps:
                            for step_ref_tree_id, step_name, step_node_id, step_ref_node_id in process_steps:
                                logger.debug("Process Step Name %s" % step_name)
                                logger.debug("Process Step Node ID %s" % step_node_id)
                                logger.debug("Process Step Ref. Node ID %s" % step_ref_node_id)
                                logger.debug("Process Step Ref. Structure ID %s" % step_ref_tree_id)
                                process_step = BusinessProcessStep(step_name, step_node_id)
                                process.add_child(process_step)

                                process_step_info = execute(sap_solman_discoverer.GetProcessSubStepById(step_ref_tree_id))
                                process_sub_steps_node_ids = []
                                system_name = None
                                # process_step_info should have length of 1
                                for process_step_ref_tree_id, node_id, tree_id, ref_node_id, component in process_step_info:
                                    logger.debug("Component %s" % component)
                                    process_step.set_component(component)
                                    process_sub_steps_node_ids.append(node_id)
                                    system_name = component_to_system.get(component)
                                logger.debug('unit test:', process_sub_steps_node_ids)
                                process_sub_sub_steps = execute(sap_solman_discoverer.GetProcessRefIdsByNodeIds(process_sub_steps_node_ids, only_tree=True))
                                process_sub_sub_steps_ref_objects = [a[0] for a in process_sub_sub_steps]
                                if process_sub_sub_steps_ref_objects:
                                    process_sub_sub_steps_tree = execute(sap_solman_discoverer.GetProcessNodeByTreeIds(process_sub_sub_steps_ref_objects))
                                    process_sub_sub_steps_tree_node_ids = [a[0] for a in process_sub_sub_steps_tree]
                                    if process_sub_sub_steps_tree_node_ids:
                                        transactions = execute(sap_solman_discoverer.GetProcessRefIdsByNodeIds(process_sub_sub_steps_tree_node_ids))
                                        for transaction_ref_obj, transaction_node in transactions:
                                            logger.debug("Transaction Ref Object %s" % transaction_ref_obj)
                                            transaction = BusinessTransaction(transaction_ref_obj, system_name)
                                            process_step.add_child(transaction)
                        if reportCIsInChunks:
                            report_chunk(framework, project, scenario, process_steps_tree, sap_system_osh)
                            process.clear_children()
    return business_objects_tree


class BusinessObjectNode(object):
    def __init__(self, node_id):
        self.__node_id = node_id
        self.__children = []

    def add_child(self, business_object_node):
        self.__children.append(business_object_node)

    def get_children(self):
        return self.__children

    def create_osh(self, parent_osh):
        osh = self._create_osh(parent_osh)
        self.set_additional_attributes(osh)
        return osh

    def clear_children(self):
        self.__children = []

    def set_additional_attributes(self, osh):
        if self.__node_id:
            osh.setAttribute('blueprint_element', self.__node_id)


class BusinessProject(BusinessObjectNode):

    def __init__(self, name, responsible, object_id):
        super(BusinessProject, self).__init__(object_id)
        self.__name = name
        self.__responsible = responsible

    def _create_osh(self, sap_system_osh):
        osh = ObjectStateHolder('sap_bp_project')
        osh.setAttribute('data_name', self.__name)
        osh.setAttribute('responsible', self.__responsible)
        osh.setContainer(sap_system_osh)
        return osh



class BusinessScenario(BusinessObjectNode):

    def __init__(self, name, node_id, ref_node_id):
        super(BusinessScenario, self).__init__(node_id)
        self.__name = name
        self.__project_node_id = ref_node_id

    def _create_osh(self, parent_osh):
        osh = ObjectStateHolder('sap_business_scenario')
        osh.setAttribute('data_name', self.__name)
        osh.setContainer(parent_osh)
        parent_osh.setAttribute('blueprint_element', self.__project_node_id)
        return osh


class BusinessProcess(BusinessObjectNode):

    def __init__(self, name, node_id):
        super(BusinessProcess, self).__init__(node_id)
        self.__name = name

    def _create_osh(self, parent_osh):
        osh = ObjectStateHolder('sap_business_process')
        osh.setAttribute('data_name', self.__name)
        osh.setContainer(parent_osh)
        return osh


class BusinessProcessStep(BusinessObjectNode):

    def __init__(self, name, node_id):
        super(BusinessProcessStep, self).__init__(node_id)
        self.__name = name
        self.__component = None

    def set_component(self, component):
        self.__component = component

    def _create_osh(self, parent_osh):
        osh = ObjectStateHolder('sap_process_step')
        osh.setAttribute('data_name', self.__name)
        if self.__component:
            osh.setAttribute('logical_component', self.__component)
        osh.setContainer(parent_osh)
        return osh


class BusinessTransaction(BusinessObjectNode):

    def __init__(self, transaction_name, system_name):
        super(BusinessTransaction, self).__init__(None)
        self.__name = transaction_name
        self.__system_name = system_name

    def _create_osh(self, parent_osh):
        osh = ObjectStateHolder('sap_transaction')
        osh.setAttribute('data_name', self.__name)
        osh.setAttribute('system_name', self.__system_name)
        osh.setContainer(parent_osh)
        return osh


def report_tree(framework, business_object_node, parent_osh):
    vector = ObjectStateHolderVector()
    current_osh = business_object_node.create_osh(parent_osh)
    vector.add(current_osh)
    for node in business_object_node.get_children():
        vector.addAll(report_tree(framework, node, current_osh))
    return vector


def report(framework, business_objects_tree, sap_system_osh):
    for project in business_objects_tree:
        logger.debug("Reporting project %s" % project)
        vector = report_tree(framework, project, sap_system_osh)
        framework.sendObjects(vector)
        framework.flushObjects()

def report_chunk(framework, project, scenario, business_objects_tree, sap_system_osh):
    vector = ObjectStateHolderVector()
    project_osh = project._create_osh(sap_system_osh)
    vector.add(project_osh)
    scenario_osh = scenario._create_osh(project_osh)
    vector.add(scenario_osh)

    for process in business_objects_tree:
        vector.addAll(report_tree(framework, process, scenario_osh))
    framework.sendObjects(vector)
    framework.flushObjects()

def businessProcesses(Framework, solman, component2system, sapsystems, SITE_ID, GET_PROCESS_STEPS, reportCIsInChunks, discoverScenarioProcesses = 0):
    r'''
    @types: ? -> dict[str, list[tuple[str, str]]]
    @return: list of pairs for
    '''
    sap_system_osh = modeling.createOshByCmdbIdString('sap_system', SITE_ID)

    business_objects_tree = _discover_business_objects(Framework, solman, component2system, discoverScenarioProcesses, GET_PROCESS_STEPS, reportCIsInChunks, sap_system_osh)
    report(Framework, business_objects_tree, sap_system_osh)



#    business_projects = solman.getBusinessProcesses() # "TPROJECT","PROJECT_ID,RESPONSIBL"; "TOBJECTP","OBJECT_ID"
#    count = business_projects.getRowCount()
#    for row in range(count):
#        # read all fields
#        name = business_projects.getCell(row, 0)
#        logger.debug('Processing project ', name)
#        responsible = business_projects.getCell(row, 1)
#        mapProjectToScenario = business_projects.getCell(row, 2)
#        project_osh = BusinessProject(name, responsible).create_osh(sap_system_osh)
#        Framework.sendObject(project_osh)
#
#        itScenarious = mapProjectToScenario.keySet().iterator()
#        while itScenarious.hasNext():
#            scenario = itScenarious.next()
#            logger.debug('Processing scenario ', scenario)
#
#            scenarioOSH = ObjectStateHolder('sap_business_scenario')
#            scenarioOSH.setAttribute('data_name', scenario)
#            scenarioOSH.setContainer(project_osh)
#            Framework.sendObject(scenarioOSH)
#            if not discoverScenarioProcesses: continue
#            mapProcessToID = mapProjectToScenario.get(scenario)
#            itProcesses = mapProcessToID.keySet().iterator()
#            while itProcesses.hasNext():
#                process = itProcesses.next()
#                logger.debug('Processing business process ', process)
#                processOSH = ObjectStateHolder('sap_business_process')
#                processOSH.setAttribute('data_name', process)
#                processOSH.setContainer(scenarioOSH)
#                Framework.sendObject(processOSH)
#                if GET_PROCESS_STEPS:
##                    logger.debug('Bringing steps for process ', process, ' in scenario ', scenario)
#                    processID = mapProcessToID.get(process)
#                    mapStepToProperties = solman.getProcessSteps(scenario, process, processID)
#                    itSteps = mapStepToProperties.keySet().iterator()
#                    while itSteps.hasNext():
#                        step = itSteps.next()
#                        props = mapStepToProperties.get(step)
#                        transactions = props.get('transactions')
#                        logicalComponent = props.get('component')
#
#                        stepOSH = ObjectStateHolder('sap_process_step')
#                        stepOSH.setAttribute('data_name', step)
#                        stepOSH.setContainer(processOSH)
#                        stepOSH.setAttribute('logical_component', logicalComponent)
#                        Framework.sendObject(stepOSH)
#
#                        itTransactions = transactions.iterator()
#                        while itTransactions.hasNext():
#                            transaction = itTransactions.next()
#                            systemsList = component2system.get(logicalComponent.lower())
#                            if systemsList is not None:
#                                for systemName in systemsList:
#                                    sapSystem = sapsystems.get(systemName)
#                                    if sapSystem is not None:
#                                        transOSH = ObjectStateHolder('sap_transaction')
#                                        transOSH.setAttribute('data_name', transaction)
#                                        transOSH.setAttribute('system_name', systemName)
#                                        transOSH.setContainer(sapSystem.getOSH())
#                                        Framework.sendObject(transOSH)
#                                        Framework.sendObject(modeling.createLinkOSH('contains',stepOSH, transOSH))


def logicalComponents(systemNames, solman):
    r'@types: list[str], saputils.SapSolman -> HashMap[str, list]'
    namesCount = len(systemNames)
    pageSize = 50
    pageOffset = 0

    product2sysname = HashMap()

    while (pageOffset < namesCount):
        pageEndPosition = pageOffset + pageSize
        if pageEndPosition > namesCount:
            pageEndPosition = namesCount
        namesForQuery = systemNames[pageOffset:pageEndPosition]
        pageOffset = pageOffset + pageSize

        names = ArrayList(len(namesForQuery))
        for name in namesForQuery:
            names.add(name)
        try:
            result = solman.execute('SMSY_SYSTEMS', 'SYSTEMNAME, PRODUCT', 'SYSTEMNAME', names)
            while result.next():
                product = result.getString("PRODUCT")
                system = result.getString("SYSTEMNAME")
                if saputils.isEmptyValue(product) or saputils.isEmptyValue(system):
                    continue
                systemsList = product2sysname.get(product.lower())
                if systemsList is None:
                    systemsList = ArrayList()
                    product2sysname.put(product.lower(), systemsList)
                systemsList.add(system.lower())
        except (Exception, JException):
            logger.warnException("Failed to get products")

    component2system = HashMap()

    result = solman.execute('SMSY_LOG_COMP', 'LOG_COMP, PRODUCT')
    while result.next():
        product = result.getString("PRODUCT")
        component = result.getString("LOG_COMP")
        if saputils.isEmptyValue(product) or saputils.isEmptyValue(component):
            continue
        systemsList = product2sysname.get(product.lower())
        if systemsList is not None:
            component2system.put(component.lower(), systemsList)
    return component2system


def DiscoveryMain(Framework):
    properties = Properties()

    SITE_ID = Framework.getDestinationAttribute('SITE_ID')
    instance_number = Framework.getDestinationAttribute('instance_number')
    connection_client = Framework.getDestinationAttribute('connection_client')
    logger.debug('Connecting to a SAP instance number:', str(instance_number))
    properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER, instance_number)

    if (connection_client is not None) and (connection_client != 'NA'):
        logger.debug('Connecting to a SAP system with client:', str(connection_client))
        properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT, connection_client)
    discoverScenarioProcesses = Boolean.parseBoolean(Framework.getParameter('discoverScenarioProcesses'))
    GET_PROCESS_STEPS = Boolean.parseBoolean(Framework.getParameter('getProcessSteps'))
    reportCIsInChunks = Boolean.parseBoolean(Framework.getParameter('reportCIsInChunks'))

    errormsg = ''
    client = None
    try:
        try:
            client = Framework.createClient(properties)
            solman = saputils.SapSolman(client)
        except (NoClassDefFoundError, MissingJarsException, ExceptionInInitializerError):
            errormsg = 'SAP drivers are missing'
            logger.debugException(errormsg)
        except:
            errormsg = 'Connection failed'
            logger.debugException(errormsg)
        else:
            try:
                sVector, sysToOshPairs = discoverSystems(solman)
                Framework.sendObjects(sVector)
                sVector.clear()
                sysNames = [system.getName() for system, _ in sysToOshPairs]
                sys_name_to_system = {}
                for system, _ in sysToOshPairs:
                    sys_name_to_system[system.getName()] = system

                component2system = logicalComponents(sysNames, solman)
                businessProcesses(Framework, solman, component2system,
                                  sys_name_to_system, SITE_ID, GET_PROCESS_STEPS, reportCIsInChunks,
                                  discoverScenarioProcesses)
            except:
                strmsg = str(sys.exc_info()[1])
                if (strmsg.upper().find('TABLE_NOT_AVAILABLE') > -1):
                    errmsg = 'No solution manager found'
                    logger.debugException(errmsg)
                    Framework.reportError(errmsg)
                else:
                    # unknown exception caught
                    raise
    except JException, ex:
        ex_info = ex.getMessage()
        errormessages.resolveAndReport(ex_info, 'SAP JCO', Framework)
    except:
        ex_info = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(ex_info, 'SAP JCO', Framework)
    finally:
        if client is not None:
            client.close()
        if errormsg:
            Framework.reportError(errormsg)
    return ObjectStateHolderVector()
