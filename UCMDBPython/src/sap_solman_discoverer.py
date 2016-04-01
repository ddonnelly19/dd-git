#coding=utf-8
'''
Created on Mar 4, 2013

@author: vvitvitskiy
'''

import operator
from itertools import ifilter

import logger
import fptools
from iteratortools import first

import sap
import sap_abap_discoverer
from sap_abap_discoverer import TableQueryRfc

from appilog.common.system.types.vectors import ObjectStateHolderVector


class _SolutionManagerTableQuery(TableQueryRfc):

    def isValidResultItem(self, result):
        return True

    def parseResult(self, resultSet):
        r'@types: ResultSet -> list[?]'
        iResultSet = self.asIterator(resultSet)
        iResultSet = ifilter(self.isValidResultItem, iResultSet)
        return map(self.parseResultItem, iResultSet)

    def parseResultItem(self, result):
        r'@types: ResultSet -> ?'
        raise NotImplementedError()


class GetProjects(_SolutionManagerTableQuery):
    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, "TPROJECT",
                                            ("PROJECT_ID", "RESPONSIBL"))

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> tuple[str, str]
        @return: list of pairs of project ID and responsible person
        '''
        return result.getString("PROJECT_ID"), result.getString("RESPONSIBL")


class GetProcessNodeById(_SolutionManagerTableQuery):
    'Read Structure repository for process model objects: Node table'

    def __init__(self, id_):
        whereClause = "TREE_ID = '%s'" % id_
        _SolutionManagerTableQuery.__init__(self, "DFTNODE01", ("REFTREE_ID","NODE_ID","REFNODE_ID"),
                                            whereClause)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> str
        @return: list of pairs of project ID and responsible person
        '''
        return result.getString("REFTREE_ID"), result.getString("NODE_ID"), result.getString("REFNODE_ID")


class GetProcessStepNodeById(_SolutionManagerTableQuery):
    'Read Structure repository for process model objects: Node table'

    def __init__(self, id_):
        whereClause = "TREE_ID = '%s'" % id_
        _SolutionManagerTableQuery.__init__(self, "BMTNODE01", ("REFTREE_ID","NODE_ID","REFNODE_ID"),
                                            whereClause)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> str
        @return: list of pairs of project ID and responsible person
        '''
        return result.getString("REFTREE_ID"), result.getString("NODE_ID"), result.getString("REFNODE_ID")


class GetProcessSubStepById(_SolutionManagerTableQuery):

    def __init__(self, id_):
        whereClause = "NODE_TYPE = 'BMPC' AND TREE_ID = '%s'" % id_
        _SolutionManagerTableQuery.__init__(self, "BMTNODE01", ("REFTREE_ID", "NODE_ID", "TREE_ID", "REFNODE_ID", "COMPONENT"),
                                            whereClause)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> str
        '''
        return result.getString("REFTREE_ID"), result.getString("NODE_ID"), result.getString("TREE_ID"), result.getString("REFNODE_ID"), result.getString("COMPONENT")


class GetProcessRefIdsByNodeIds(_SolutionManagerTableQuery):

    def __init__(self, ids, only_tree=False):
        whereClause = None
        if only_tree:
            whereClause = "REF_TYPE = 'TREE' AND "
        _SolutionManagerTableQuery.__init__(self, "BMTNODE01R", ("REF_OBJECT", "NODE_ID"),
                                            whereClause, inField="NODE_ID", inFieldValues=ids)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> str
        '''
        return result.getString("REF_OBJECT"), result.getString("NODE_ID")


class GetProcessNodeByTreeIds(_SolutionManagerTableQuery):

    def __init__(self, ids):
        whereClause = "NODE_TYPE = 'BMTA' AND "
        _SolutionManagerTableQuery.__init__(self, "BMTNODE01", ("NODE_ID", "TREE_ID"),
                                            whereClause, inField="TREE_ID", inFieldValues=ids)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> str
        '''
        return result.getString("NODE_ID"), result.getString("TREE_ID")


class GetNameOfStructure(_SolutionManagerTableQuery):
    'Read Name of a structure'

    def __init__(self, ids):
        _SolutionManagerTableQuery.__init__(self, "TTREET", ("ID", "TEXT"),
                               inField="ID", inFieldValues=ids)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> tuple[str, str]
        '''
        return result.getString("ID"), result.getString("TEXT")


class GetProjectObjects(_SolutionManagerTableQuery):
    r'Query objects assigned to project'
    def __init__(self, projectId):
        whereClause = "PROJECT_ID = '%s' AND OBJ_TYPE = 'CUST'" % projectId
        _SolutionManagerTableQuery.__init__(self, "TOBJECTP", ("OBJECT_ID",),
                                            whereClause)

    @staticmethod
    def parseResultItem(result):
        r'@types: ResultSet -> str'
        return result.getString("OBJECT_ID")


class GetSystems(_SolutionManagerTableQuery):
    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, 'SMSY_SYSTEM_SAP',
                ('SYSTEMNAME', 'SYSNR', 'MESSSERVER', 'SYSTEMTYPE'),
                inField='VERSION', inFieldValues=('ACTIVE',))

    @staticmethod
    def parseResultItem(result):
        r'@types: ResultSet -> tuple[System, str, str?]'
        name = GetSystems._getSystemName(result)
        msgServerHost = GetSystems._getMsgServerHostname(result)
        ciNr = result.getString("SYSNR")
        return sap.System(name), msgServerHost, ciNr

    @staticmethod
    def isValidResultItem(result):
        # there are ephemeral SAP System entries in database which actually
        # can be translated to the real sap systems.
        # i.e. G11 and G1100080, SMN and SMN00065, etc.
        msgHostname = GetSystems._getMsgServerHostname(result)
        systemName = GetSystems._getSystemName(result)
        r = operator.truth(msgHostname and sap.isCorrectSystemName(systemName))
        if not r:
            logger.warn("System %s (msg: %s) will be skipped" %
                        (systemName, msgHostname))
        return r

    @staticmethod
    def _getSystemName(result):
        return result.getString("SYSTEMNAME")

    @staticmethod
    def _getMsgServerHostname(result):
        return result.getString("MESSSERVER")


def discoverSystems(solman):
    r'@types: saputils.SapSolman -> oshv, list[tuple[System, osh]]'
    logger.info('Discover SAP Systems')
    getSystemsQuery = GetSystems()
    queryExecutor = sap_abap_discoverer.TableQueryExecutor(solman)
    systemDetails = queryExecutor.executeQuery(getSystemsQuery)
    systems = map(first, systemDetails)
    reporter = sap.Reporter(sap.Builder())
    oshs = map(reporter.reportSystem, systems)
    logger.info("Discovered %s systems" % len(oshs))
    vector = ObjectStateHolderVector()
    fptools.each(vector.add, oshs)
    return vector, zip(systems, oshs)
