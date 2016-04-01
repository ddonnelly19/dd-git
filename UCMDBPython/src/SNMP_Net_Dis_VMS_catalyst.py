#coding=utf-8
import modeling
import logger
import snmputils

from java.util import Properties

from com.hp.ucmdb.discovery.library.clients import BaseClient
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.protocols.snmp import SnmpConnectionTester

##############################################
########         FUNCTIONS          ##########
##############################################
def doAll(snmpClient, hostOSH, vlanOSH, OSHVResult, ucmdbversion):

    baseMacTableMib        = '1.3.6.1.2.1.17.1.1,1.3.6.1.2.1.17.1.2,hexa'
    portNumIfIndexTableMib    = '1.3.6.1.2.1.17.1.4.1.2,1.3.6.1.2.1.17.1.4.1.3,string'

    baseMacTableRes = snmpClient.executeQuery(baseMacTableMib)#@@CMD_PERMISION snmp protocol execution
    portNumIfIndexTableRes = snmpClient.executeQuery(portNumIfIndexTableMib)#@@CMD_PERMISION snmp protocol execution

    baseMacTable = baseMacTableRes.asTable()
    portNumIfIndexTable = portNumIfIndexTableRes.asTable()
    bridgeOSH = None
    if (len(baseMacTable) > 0) and (baseMacTable[0][1] != None) and (baseMacTable[0][1] != '') and (baseMacTable[0][1] != '000000000000'):

        bridgeOSH = ObjectStateHolder('bridge')
        bridgeOSH.setContainer(hostOSH)
        bridgeOSH.setAttribute('bridge_basemacaddr', baseMacTable[0][1])
        OSHVResult.add(bridgeOSH)
        
        vlanOSH.setAttribute('vlan_bridgemac', baseMacTable[0][1])
        OSHVResult.add(vlanOSH)
    
    if len(portNumIfIndexTable) == 0:
        raise ValueError, "Failed to get physical port information from the device."
    for i in range(len(portNumIfIndexTable)):
        port = portNumIfIndexTable[i][0]

        portOSH = ObjectStateHolder('port')
        portOSH.setContainer(hostOSH)
        modeling.setPhysicalPortNumber(portOSH, port)
        OSHVResult.add(portOSH)

        if ucmdbversion < 9:
            member_link = modeling.createLinkOSH('member', portOSH, vlanOSH)
        else:
            member_link = modeling.createLinkOSH('member', vlanOSH, portOSH)
        OSHVResult.add(member_link)
        if (bridgeOSH != None):
            contains_link = modeling.createLinkOSH('contains',bridgeOSH,portOSH)
            OSHVResult.add(contains_link)
            depend_link = modeling.createLinkOSH('depend',vlanOSH,bridgeOSH)
            OSHVResult.add(depend_link)
        
########################################
########    MAIN        ########
########################################
def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    ucmdbversion = modeling.CmdbClassModel().version()
    
    snmpCommunityPostfixList = ''
    try:
        snmpCommunityPostfixList = Framework.getTriggerCIDataAsList('snmpCommunityPostfix')
        if not snmpCommunityPostfixList:
            raise Exception, "No Vlans defined on switch"
    except:
        Framework.reportError('Failed to discover destination. No Vlans properly configured.')
        return OSHVResult

    hostId    = Framework.getDestinationAttribute('hostId')
    hostOSH = modeling.createOshByCmdbIdString('host', hostId)
    
    vlan_context_dict = {}
    snmp_version = Framework.getProtocolProperty(credentialsId, "snmpprotocol_version")
    if snmp_version == 'version 3':
        client = Framework.createClient()
        vlan_context_dict = snmputils.get_snmp_vlan_context_dict(client)
        client and client.close()
        
    vlanOSH = None
    failedToDiscoverCounter = 0
    for snmpCommunityPostfix in snmpCommunityPostfixList:
        vlanOSH = modeling.createVlanOsh(snmpCommunityPostfix, hostOSH)
        vlanOSH.setContainer(hostOSH)

        properties = Properties()
        if credentialsId and ipAddress:
            properties.setProperty('ip_address', ipAddress)
            properties.setProperty(BaseClient.CREDENTIALS_ID, credentialsId)

        if (snmpCommunityPostfix != None) and (snmpCommunityPostfix != ''):
            if snmp_version == 'version 3':
                if not vlan_context_dict:
                    logger.warn("Vlan Conext is not present on the device. No Vlan details might be discovered")
                    continue
                
                vlan_context = vlan_context_dict.get(snmpCommunityPostfix)
                if not vlan_context:
                    logger.warn("Failed to find configured Vlan context for Vlan %s. Vlan will be skipped" % snmpCommunityPostfix)
                    continue
                properties.setProperty(SnmpQueries._postfix, '%s' % vlan_context)
            else:
                properties.setProperty(SnmpQueries._postfix, '%s%s' % ('@', snmpCommunityPostfix))
        

        snmpClient = None
        try:
            snmpClient = Framework.createClient(properties)
            #SnmpConnectionTester(snmpClient).testSnmpConnection()
            doAll(snmpClient, hostOSH, vlanOSH, OSHVResult, ucmdbversion)
            Framework.sendObjects(OSHVResult)
            Framework.flushObjects()
            logger.debug('Vlan %s successfully discovered. Result vector contains %d objects.' % (snmpCommunityPostfix, OSHVResult.size()))
            OSHVResult = ObjectStateHolderVector()
        except:
            logger.debugException('')
            failedToDiscoverCounter =+ 1
            logger.debugException('Failed to discover ip: %s on Vlan#: %s. ' % (ipAddress, snmpCommunityPostfix))
        if snmpClient != None:
            snmpClient.close()

    if failedToDiscoverCounter == len(snmpCommunityPostfixList):
        Framework.reportError('Failed to discover all Vlans on the destination.')
    elif failedToDiscoverCounter:
        Framework.reportWarning('Failed to discover one or more Vlans on the destination')
    
    if snmpClient != None:
        snmpClient.close()
    return OSHVResult
