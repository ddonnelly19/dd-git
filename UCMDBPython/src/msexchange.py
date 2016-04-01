#coding=utf-8
import modeling
import re
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.text import SimpleDateFormat
from java.lang import NullPointerException


class ExchangeServer:
    def __init__(self):
        '''
        @type creationDate: java.util.Date
        '''
        self.name = None
        self.__guid = None
        self.fqdn = None
        self.roleNames = []
        self.dataPath = None
        self.creationDate = None
        self.exchangeVersion = None
        self.adminDisplayVersion = None
        self.organizationalUnit = None
        self.legacyDN = None
        self.site = None
        self.organization = None
        self.buildNumber = None
        self.version = None
        self.dagList = []
        self.clusteredMailBox = None
        self.mdbList = []

    def setCreationDate(self, dateString,
                        dateFormat=SimpleDateFormat("MM/dd/yyyy HH:mm:ss")):
        ''' Set creation date according to specified formatter
        string, java.text.DateFormat = SimpleDateFormat -> None
        @raise ValueError: dateString is None
        '''
        try:
            self.creationDate = dateFormat.parse(dateString)
        except NullPointerException, npe:
            raise ValueError(npe.getMessage())

    def setGuid(self, rawGuid):
        # string
        if rawGuid:
            self.__guid = re.sub("[-\ ]+", "", rawGuid).upper()

    def getGuid(self):
        # -> string
        return self.__guid


class Dag:
    def __init__(self):
        self.dagName = None
        self.dagServersList = None
        self.witnessServer = None
        self.witnessDirectory = None
        self.availIp = None
        self.guid = None


class ClusteredMailBox:
    def __init__(self):
        self.name = None
        self.exchOrgName = None
        self.serverList = []


RELATE_TO_DAG = 'DatabaseAvailabilityGroup'
RELATE_TO_SERVER = 'ExchangeServer'


class ExchangeHostInfo:
    def __init__(self, name=None):
        self.name = name
        self.ips = None


class MailboxDatabase:
    def __init__(self):
        self.name = None
        self.datafilePath = None
        self.serversString = None
        self.servers = []
        self.relateTo = RELATE_TO_SERVER
        self.containerName = None
        self.runningServer = None
        self.guid = None

    def __repr__(self):
        return "MailboxDatabase %s servers %s container %s" % (self.name,
                                            self.servers, self.containerName)


class TopologyBuilder:
    MAIL_BOX_ROLE = 'Exchange Mailbox Server'
    CLIENT_ACCESS_ROLE = 'Exchange Client Access Server'
    UNIFIED_MESSAGING_ROLE = 'Exchange Unified Messaging Server'
    HUB_TRANSPORT_ROLE = 'Exchange Hub Transport Server'
    EDGE_TRANSPORT_ROLE = 'Exchange Edge Transport Server'

    def __init__(self, exchangeServer, hostOsh, ipAddress, credentialsId):
        # string, osh, string, string
        self.exchangeServer = exchangeServer
        self.hostOsh = hostOsh
        self.ipAddress = ipAddress
        self.credentialsId = credentialsId

    def buildExchangeServerOsh(self, exchangeServer, hostOsh, ipAddress, credentialsId):
        # string, osh, string, string -> osh
        exchangeServerOsh = modeling.createExchangeServer(hostOsh, ipAddress, credentialsId, exchangeServer.version)
        exchangeServerOsh.setAttribute('guid', exchangeServer.getGuid())
        exchangeServerOsh.setAttribute('fqdn', exchangeServer.fqdn)
        exchangeServerOsh.setAttribute('build_number', exchangeServer.buildNumber)
        exchangeServerOsh.setAttribute('application_version_number', exchangeServer.version)
        exchangeServerOsh.setAttribute('application_version', exchangeServer.adminDisplayVersion)
        exchangeServerOsh.setDateAttribute('creation_date', exchangeServer.creationDate)
        return exchangeServerOsh

    def buildServerRoles(self, exchangeServerOsh, exchangeServer):
        # osh, do -> list of osh
        ROLE = {
         'Mailbox' : (lambda: __buildCI('exchangemailserver', TopologyBuilder.MAIL_BOX_ROLE)),
         'ClientAccess' : (lambda: __buildCI('exchangeclientaccessserver', TopologyBuilder.CLIENT_ACCESS_ROLE)),
         'HubTransport' : (lambda: __buildCI('exchangehubserver', TopologyBuilder.HUB_TRANSPORT_ROLE)),
         'UnifiedMessaging' : (lambda: __buildCI('exchangeunifiedmessagingserver', TopologyBuilder.UNIFIED_MESSAGING_ROLE)),
         'Edge' : (lambda: __buildCI('exchangeedgeserver', TopologyBuilder.EDGE_TRANSPORT_ROLE)) }

        OSHVResult = ObjectStateHolderVector()
        for roleName in exchangeServer.roleNames:
            if ROLE.has_key(roleName):
                roleOsh = ROLE[roleName]()
                roleOsh.setContainer(exchangeServerOsh)
                OSHVResult.add(roleOsh)
        return OSHVResult

    def buildExchangeOrganization(self, exchOrgName):
        if exchOrgName:
            osh = ObjectStateHolder('exchangesystem')
            osh.setAttribute('data_name', exchOrgName)
            return osh

    def buildExchAdminGrOsh(self, orgOsh, exchAdminGrName):
        if exchAdminGrName and orgOsh:
            osh = ObjectStateHolder('exchange_administrative_group')
            osh.setAttribute('data_name', exchAdminGrName)
            osh.setContainer(orgOsh)
            return osh

    def buildDag(self, orgOsh, dag):
        if orgOsh and dag and dag.dagName:
            osh = ObjectStateHolder('ms_exchange_dag')
            osh.setAttribute('data_name', dag.dagName)
            osh.setAttribute('name', dag.dagName)
            if dag.witnessDirectory:
                osh.setStringAttribute('witness_directory', dag.witnessDirectory)
            if dag.availIp:
                osh.setStringAttribute('avail_ip', dag.availIp)
            if dag.guid:
                osh.setStringAttribute('dag_guid', dag.guid)
            osh.setContainer(orgOsh)
            return osh

    def buildDagRelatedTopology(self, exchangeServerOsh, dagList):
        OSHVResult = ObjectStateHolderVector()
        for dag in dagList:
            exchOrgOsh = self.buildExchangeOrganization(dag.exchOrgName)
            if exchOrgOsh:
                exchAdminGrOsh = self.buildExchAdminGrOsh(exchOrgOsh, dag.exchAdminGrName)
                OSHVResult.add(modeling.createLinkOSH('membership', exchAdminGrOsh, exchangeServerOsh))
                dagOsh = self.buildDag(exchOrgOsh, dag)
                if dagOsh:
                    OSHVResult.add(modeling.createLinkOSH('membership', dagOsh, exchangeServerOsh))
                    OSHVResult.add(exchOrgOsh)
                    OSHVResult.add(exchAdminGrOsh)
                    OSHVResult.add(dagOsh)
        return OSHVResult

    def buildClusteredMailBox(self, orgOsh, clusteredMailBox):
        if orgOsh and clusteredMailBox and clusteredMailBox.name:
            osh = ObjectStateHolder('ms_exchange_clustered_mailbox')
            osh.setAttribute('data_name', clusteredMailBox.name)
            osh.setAttribute('name', clusteredMailBox.name)
            osh.setContainer(orgOsh)
            return osh

    def buildClusteredMailBoxRelatedTopology(self, exchangeServerOsh, clusteredMailBox):
        OSHVResult = ObjectStateHolderVector()
        exchOrgOsh = self.buildExchangeOrganization(clusteredMailBox.exchOrgName)
        if exchOrgOsh:
            clusteredMailBoxOsh = self.buildClusteredMailBox(exchOrgOsh, clusteredMailBox)
            if clusteredMailBoxOsh:
                OSHVResult.add(modeling.createLinkOSH('membership', clusteredMailBoxOsh, exchangeServerOsh))
                OSHVResult.add(exchOrgOsh)
                OSHVResult.add(clusteredMailBoxOsh)
        return OSHVResult

    def buildMailboxDatabase(self, mdb, containerOsh):
        if mdb and mdb.name and containerOsh:
            osh = ObjectStateHolder('ms_exchange_mailbox_database')
            osh.setStringAttribute('name', mdb.name)
            osh.setStringAttribute('data_name', mdb.name)
            if mdb.guid:
                osh.setStringAttribute('data_guid', mdb.guid)
            osh.setContainer(containerOsh)
            if mdb.datafilePath:
                osh.setStringAttribute('database_path', mdb.datafilePath)
            return osh

    def build(self):
        #@return: oshv
        OSHVResult = ObjectStateHolderVector()
        exchageOsh = self.buildExchangeServerOsh(self.exchangeServer,
                            self.hostOsh, self.ipAddress, self.credentialsId)

        if self.exchangeServer.organization:
            exchOrgOsh = self.buildExchangeOrganization(self.exchangeServer.organization)
            OSHVResult.add(exchOrgOsh)
            OSHVResult.add(modeling.createLinkOSH('member', exchOrgOsh, exchageOsh))
            if self.exchangeServer.organizationalUnit:
                adminGrOsh = self.buildExchAdminGrOsh(exchOrgOsh, self.exchangeServer.organizationalUnit)
                OSHVResult.add(adminGrOsh)
                OSHVResult.add(modeling.createLinkOSH('member', adminGrOsh, exchageOsh))

        if self.exchangeServer.dagList:
            OSHVResult.addAll(self.buildDagRelatedTopology(exchageOsh, self.exchangeServer.dagList))

        if self.exchangeServer.clusteredMailBox:
            self.exchangeServer.clusteredMailBox.exchOrgName = self.exchangeServer.clusteredMailBox.exchOrgName or self.exchangeServer.organization
            OSHVResult.addAll(self.buildClusteredMailBoxRelatedTopology(exchageOsh, self.exchangeServer.clusteredMailBox))

        if self.exchangeServer.mdbList:
            for mdb in self.exchangeServer.mdbList:
                containerOsh = None
                if mdb.relateTo == RELATE_TO_DAG:
                    if self.exchangeServer.dagList:
                        for dag in self.exchangeServer.dagList:
                            if dag.dagName == mdb.containerName:
                                exchOrgOsh = self.buildExchangeOrganization(dag.exchOrgName)
                                containerOsh = self.buildDag(exchOrgOsh, dag)
                if containerOsh:
                    mdbOsh = self.buildMailboxDatabase(mdb, containerOsh)
                    if mdbOsh:
                        OSHVResult.add(containerOsh)
                        OSHVResult.add(mdbOsh)
                        if mdb.servers:
                            for server in mdb.servers:
                                if server.ips:
                                    hostOsh = modeling.createHostOSH(str(server.ips[0]))
                                    exchangeServerOsh = modeling.createExchangeServer(hostOsh)
                                    linkOsh = modeling.createLinkOSH('ownership', exchangeServerOsh, mdbOsh)
                                    OSHVResult.add(exchangeServerOsh)
                                    OSHVResult.add(linkOsh)
                                    OSHVResult.add(hostOsh)
                                    if server.name == mdb.runningServer:
                                        linkOsh = modeling.createLinkOSH('run', exchangeServerOsh, mdbOsh)
                                        OSHVResult.add(linkOsh)
        OSHVResult.add(exchageOsh)
        OSHVResult.addAll(self.buildServerRoles(exchageOsh, self.exchangeServer))
        OSHVResult.add(self.hostOsh)
        return OSHVResult


def __buildCI(citName, dataName):
    #string , string -> osh
    osh = ObjectStateHolder(citName)
    osh.setAttribute('data_name', dataName)
    return osh
