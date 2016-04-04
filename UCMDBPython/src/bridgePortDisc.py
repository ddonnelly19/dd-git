#coding=utf-8
import modeling
import re
import os
import md5
import SNMP_Networking_Utils
import netutils
import snmputils
import logger

from java.util import Properties
from java.util import Date
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from com.hp.ucmdb.discovery.library.clients import BaseClient
from appilog.common.system.defines import AppilogTypes
from com.hp.ucmdb.discovery.library.clients.protocols.snmp import SnmpConnectionTester
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
#################
##
## Classess here
##
#################
#++++++++++
class Switch:
#++++++++++
    ##########
    ##
    ## Class Vars
    ##
    ##########
    intfcMac = '1.3.6.1.2.1.2.2.1.6,1.3.6.1.2.1.2.2.1.7,hexa'
    dot1dStpPortDesignatedBridge = '1.3.6.1.2.1.17.2.15.1.8,1.3.6.1.2.1.17.2.15.1.9,hexa'
    dot1dStpPortDesignatedPort = '1.3.6.1.2.1.17.2.15.1.9,1.3.6.1.2.1.17.2.15.1.10,hexa'
    dot1dBasePortIfIndex = '1.3.6.1.2.1.17.1.4.1.2,1.3.6.1.2.1.17.1.4.1.3,int'
    dot1dBaseBridgeAddress = '1.3.6.1.2.1.17.1.1,1.3.6.1.2.1.17.1.2,hexa'
    dot1dTpFdbPort = '1.3.6.1.2.1.17.4.3.1.2,1.3.6.1.2.1.17.4.3.1.3,string'
    ifIndexDescr = '1.3.6.1.2.1.2.2.1.2,1.3.6.1.2.1.2.2.1.3,string'
    ifName = '1.3.6.1.2.1.31.1.1.1.1,1.3.6.1.2.1.31.1.1.1.2,string'
    
    def __init__(self, aBgId, aHostID, ucmdbversion = None, Framework = None):
        ################
        ##
        ## These are my instance variables
        ##
        ################
        self.ucmdbversion = ucmdbversion
        self.localBridgeId = aBgId            #compare to this guy when checking out STP conn.
        self.snmpClient = None                #SNMP info about this bridge including IP and commString
        self.swPortIfIndex = {}
        self.swPortRemoteBgIds = {}
        self.swPortRemotePtIds = {}
        self.swPortTermMacs = {}
        self.swIntfcMac = {}
        self.swIfIndexDescr = {}
        self.swIfName = {}
        self.hostOSH = modeling.createOshByCmdbIdString("host", aHostID)
        self.ifInd2Mac = {}
        self.ifIndToInterface = {}
        self.framework = Framework

    def getLocalInterfaces(self):
        ifList = SNMP_Networking_Utils.discoverInterfaceData(self.snmpClient, None)
        for interface in ifList:
            self.ifIndToInterface[interface.ifIndex] = interface
            logger.debug('Found local interface: index %s; mac %s; descr %s; name %s' % (interface.ifIndex, interface.ifMac, interface.ifDescr, interface.ifName))
            
    def getBsPorts(self):
        try:
            basePort2ifIndexMap = self.snmpClient.executeQuery(Switch.dot1dBasePortIfIndex).asTable()#@@CMD_PERMISION snmp protocol execution
            if basePort2ifIndexMap:
                for i in xrange(len(basePort2ifIndexMap)):
                    (basePort,ifIndex) = basePort2ifIndexMap[i]
                    basePort2ifIndexMap[i] = (basePort.upper(),ifIndex.upper())

        except:
            logger.error('error in retrieving ifIndex for ports')
        else:
            for basePort2ifIndex in basePort2ifIndexMap:
                self.swPortIfIndex.update({basePort2ifIndex[0]:basePort2ifIndex[1]})

    def getOwnBgId(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.dot1dBaseBridgeAddress).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.error('error in retrieving ownBdId')
        else:
            try:
                if (self.localBridgeId.upper() != aList[0][1].upper()):
                    logger.debug('the retrieved bridge Id is not the same as passed in bridgeId')
                self.localBridgeId = aList[0][1]
            except:
                logger.warn('the retrieved bridge Id is null')

    def getSTPStat(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.dot1dStpPortDesignatedBridge).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                logger.debug('List of bg-port is %d' % len(aList))
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())

        except:
            logger.debug('error in retrieving STP remote bg stats')
        else:
            for localPort in aList:
                if (localPort[1]) and (localPort[0]) and (self.cleanUpRemtBg(localPort[1]) != self.localBridgeId):
                    self.swPortRemoteBgIds.update({localPort[0]:(self.cleanUpRemtBg(localPort[1]))})
                    logger.debug('getSTPStat: Port ', localPort[0], ' has Remote Bridge Id of ', self.swPortRemoteBgIds.get(localPort[0]))
                elif (localPort[1]):
                    logger.debug('getSTPStat: Local Bridge ID %s is equal to Remote Bridge Id %s' % (self.localBridgeId, self.cleanUpRemtBg(localPort[1])))                    
        try:
            aPtList = self.snmpClient.executeQuery(Switch.dot1dStpPortDesignatedPort).asTable()#@@CMD_PERMISION snmp protocol execution
            if aPtList:
                for i in xrange(len(aPtList)):
                    (a,b) = aPtList[i]
                    aPtList[i] = (a.upper(),b.upper())

        except:
            logger.error('Error in retrieving STP port stats')
        else:
            for aPt in aPtList:
                if (self.swPortRemoteBgIds.has_key(aPt[0])):
                    self.swPortRemotePtIds.update({aPt[0]:(self.cleanUpPt(aPt[1]))})
                    logger.debug('port ', aPt[0], ' has remote port ', self.swPortRemotePtIds.get(aPt[0]))

    def getOwnIntfcMac(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.intfcMac).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.error('error in retrieving interface mac address')
        else:
            for aMac in aList:
                self.swIntfcMac.update({aMac[1]: aMac[0]})
                self.ifInd2Mac.update({aMac[0]: aMac[1]})

    def getMacByIfIndex(self, ifIndex):
        return self.ifInd2Mac.get(ifIndex)

    def getInterfaceByIfIndex(self, ifIndex):
        return self.ifIndToInterface.get(ifIndex)

    def getIfIndexDescr(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.ifIndexDescr).asTable()#@@CMD_PERMISION snmp protocol execution)
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.errorException('error in retrieving interface indexes')
        else:
            for ifIndexDescr in aList:
                self.swIfIndexDescr.update({ifIndexDescr[0]: ifIndexDescr[1]})

    def getIfName(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.ifName).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.errorException('error in retrieving interface mac address')
        else:
            for anIfName in aList:
                self.swIfName.update({anIfName[0]: anIfName[1]})

    def getTPStat(self):
        try:
            aList = self.snmpClient.executeQuery(Switch.dot1dTpFdbPort).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.error('error retrieving TP info')
        else:
            for x in aList:
                if (self.swPortTermMacs.has_key(x[1])):
                    portMacList = self.swPortTermMacs.get(x[1])
                    portMacList.append(x[0])
                else:
                    portMacList = [x[0]]
                self.swPortTermMacs.update({x[1]:portMacList})

    def hasIntfcMac(self, aMacAddr):
        if self.swIntfcMac.has_key(aMacAddr):
            return 1
        else:
            return 0

    def createMyPorts(self, ObjSHV, discInst):
        for x in self.swPortIfIndex.keys():
            aPt = SwitchPort(x, self, discInst, self.ucmdbversion, self.framework)
            aPt.setRemoteBdgId(self.swPortRemoteBgIds.get(x, None), self)
            aPt.setRemotePortId(self.swPortRemotePtIds.get(x, None), self )
            aPt.setInterfaceIndex(self.swPortIfIndex.get(x, None), self)
            aPt.setRemoteTermMac(self.swPortTermMacs.get(x, None), self, ObjSHV, discInst)
            aPt.addToOSHV(self, ObjSHV)

    def doWork(self, ObjSHV, discInst):
        self.getOwnIntfcMac()
        if self.ucmdbversion and self.ucmdbversion >= 9:
            self.getLocalInterfaces()
        self.getBsPorts()
        self.getOwnBgId()
        self.getSTPStat()
        self.getTPStat()
        self.getIfName()
        self.getIfIndexDescr()
        self.createMyPorts(ObjSHV, discInst)

    def cleanUpPt(self, aPt):
        return int(re.findall('...$', aPt)[0],16)

    def cleanUpRemtBg(self, aRemoteBg):
        return re.findall('............$', aRemoteBg)[0]


class QBridgeSwitch(Switch):
    DOT1Q_VLAN_FDB_ID = '1.3.6.1.2.1.17.7.1.4.2.1.3.0,1.3.6.1.2.1.17.7.1.4.2.1.3.1,integer'
    DOT1Q_TP_FDB_PORT = '1.3.6.1.2.1.17.7.1.2.2.1.2.%s,1.3.6.1.2.1.17.7.1.2.2.1.%s,string'
    HP_TP_FDB_PORT = '1.3.6.1.4.1.11.2.14.11.5.1.9.4.1.1.3.%s,1.3.6.1.4.1.11.2.14.11.5.1.9.4.1.1.3.%s,string'

    def __init__(self, vlan_id, bridge_id, host_id, ucmdb_version, framework):
        Switch.__init__(self, bridge_id, host_id, ucmdb_version, framework)
        self.vlan_id = vlan_id
        self.fdb_id = None

    def set_device_type_str(self, device_type_str):
        self.device_type_str = device_type_str

    def get_fdb_id(self):
        #For each VLAN switch collects own FDB
        self.fdb_id = self.vlan_id
        try:
            fdb_list = self.snmpClient.executeQuery(self.DOT1Q_VLAN_FDB_ID).asTable()#@@CMD_PERMISION snmp protocol execution
        except:
            logger.warnException('')
        else:
            if fdb_list and len(fdb_list) > 0:
                for (vlan_id,fdb_id) in fdb_list:
                    if int(vlan_id) == int(self.vlan_id):
                        logger.debug('Found FDB ID:%s for VLAN:%s' % (fdb_id, vlan_id))
                        self.fdb_id = fdb_id
        if self.fdb_id == self.vlan_id:
            logger.debug('Trying to get FDB info by VLAN ID: %s' % self.vlan_id)

    def getLayer2PerVlan(self):
        self.get_fdb_id()
        try:
            aList = self.snmpClient.executeQuery(self.DOT1Q_TP_FDB_PORT % (self.fdb_id, int(self.fdb_id) + 1)).asTable()#@@CMD_PERMISION snmp protocol execution
            if len(aList) == 0 and (self.device_type_str.find('hp')!=-1 or self.device_type_str.find('procurve')!=-1):
                #old HP ProCurve switches use HP private MIBs
                aList = self.snmpClient.executeQuery(self.HP_TP_FDB_PORT % (self.vlan_id, int(self.vlan_id) + 1)).asTable()#@@CMD_PERMISION snmp protocol execution
            if aList:
                for i in xrange(len(aList)):
                    (a,b) = aList[i]
                    aList[i] = (a.upper(),b.upper())
        except:
            logger.warnException('error retrieving TP info')
        else:
            for x in aList:
                if (self.swPortTermMacs.has_key(x[1])):
                    portMacList = self.swPortTermMacs.get(x[1])
                    portMacList.append(x[0])
                else:
                    portMacList = [x[0]]
                self.swPortTermMacs.update({x[1]:portMacList})
    getTPStat = getLayer2PerVlan


#++++++++++
class SwitchPort:
#++++++++++
    def __init__(self, aNum, aSwitch, discInst, ucmdbversion, framework = None):        #sets my port number and the bridge I belong to
        self.framework = framework
        self.ucmdbversion = ucmdbversion
        self.portNumber = aNum
        self.remoteStpBgId = ''        #port_remotestpbgid
        self.remoteStpPortId = ''    #port_remotestpptid
        self.interfaceIndex = 0        #port_intfc
        self.remoteTermMac = ''        #port_nextmac
        self.remoteTermMacRaw = {}
        self.portName = ''
        self.snmpAgent = ''
        self.hostBgId = aSwitch.localBridgeId    #port_hostbgid
        self.data_name = ''
        self.discoveryInst = discInst.thisInst()

    def setRemoteBdgId(self, aBdId, aSwitch):
        if (aBdId):
            self.remoteStpBgId = aBdId
            logger.debug('setting my remote bg ', self.remoteStpBgId)

    def setRemotePortId(self, aPortId, aSwitch):
        if (aPortId):
            self.remoteStpPortId = str(aPortId)
            logger.debug('setting my remote port ', self.remoteStpPortId)

    def setInterfaceIndex(self, anIntfcIndex, aSwitch):
        if (anIntfcIndex):
            self.interfaceIndex = anIntfcIndex
        if (aSwitch.swIfName.get(anIntfcIndex)):
            self.data_name = aSwitch.swIfName.get(anIntfcIndex)
        elif (aSwitch.swIfIndexDescr.get(anIntfcIndex)):
            self.data_name = aSwitch.swIfIndexDescr.get(anIntfcIndex)
        else:
            return

    def setRemoteTermMac(self, macs, aSwitch, ObjSHV, discInst):
        self.macAddrs = []
        if (macs):
            for x in macs:
                aMacAddr = self.convertToHexString(x)
                if aMacAddr.upper().startswith('00005E') or aMacAddr.upper().startswith('00000C'):
                    logger.debug('skipping MAC %s as it is a virtual one and can not be a TermMAC' % aMacAddr)
                    continue 
                if aSwitch.hasIntfcMac(aMacAddr):
                    logger.debug('skipping ', aMacAddr, ' because it is an own infcmac')
                else:
                    self.macAddrs.append(aMacAddr)
                    self.remoteTermMacRaw[aMacAddr] = x
        else:
                logger.debug('port ', self.portNumber, ' is not connected at all')
                return

        if (len(self.macAddrs) == 0):
            logger.debug('port ', self.portNumber, ' is not connected at all')
            return
        elif (len(self.macAddrs) == 1):
            self.remoteTermMac = self.macAddrs[0]
            if self.ucmdbversion and self.ucmdbversion < 9:
                return
        else:
            self.remoteTermMac = aSwitch.localBridgeId + ":" + self.portNumber
        localInterface = None
        if self.ucmdbversion and self.ucmdbversion >= 9:
            localInterface = aSwitch.getInterfaceByIfIndex(self.interfaceIndex)
        if not localInterface and self.ucmdbversion and self.ucmdbversion >= 9:
            logger.debug('Failed to retrieve local interface using ifindex %s' % self.interfaceIndex)
        #added file removal
        if localInterface:
            vlan_id = self.framework.getDestinationAttribute('snmpCommunityPostfix')
            md5_obj = md5.new()
            updateValue = ''
            for value in [localInterface.ifMac.upper(), localInterface.ifDescr, localInterface.ifIndex, localInterface.ifType, localInterface.ifAdminStatus, localInterface.ifOperStatus, localInterface.ifSpeed, localInterface.ifName, localInterface.ifAlias]:
                if not updateValue:
                    updateValue = str(value)
                else:
                    updateValue = updateValue + ':::' + str(value)
            md5_obj.update(updateValue)
            if vlan_id:
                md5_obj.update(vlan_id)
            filename = md5_obj.hexdigest()
            filepath = os.path.join(CollectorsParameters.HOME_DIR, 'runtime/l2process/')
            try:
                if os.path.exists(filepath+filename):
                    os.remove(filepath+filename)
                    logger.debug('Removing old fs hashed file: %s' % filename)
            except:
                logger.debug('Failed to remove file %s' % filename)
        #end added file removal
        if len(macs) > 1:
            Concentrator(self.remoteTermMac, aSwitch, macs, ObjSHV, discInst, self.ucmdbversion, localInterface, self.framework)

    def addToOSHV (self, aSwitch, ObjSHV):
        aPtOSH = ObjectStateHolder("port")
        aPtOSH.setContainer(aSwitch.hostOSH)
        modeling.setPhysicalPortNumber(aPtOSH, self.portNumber)
        aPtOSH.setAttribute('port_remotestpbgid',self.remoteStpBgId)
        self.__setRemotePortNumber(aPtOSH, self.remoteStpPortId)
        aPtOSH.setAttribute('port_intfcindex',int(self.interfaceIndex))
        aPtOSH.setAttribute('port_nextmac',self.remoteTermMac)
        aPtOSH.setAttribute('port_hostbgid',self.hostBgId)
        aPtOSH.setAttribute('port_discoverylastrun',self.discoveryInst)
        aPtOSH.setAttribute('data_name',self.data_name)
        ObjSHV.add(aPtOSH)
        if self.ucmdbversion and self.ucmdbversion >= 9:
            interface = aSwitch.getInterfaceByIfIndex(self.interfaceIndex)
            if interface:
                intfOsh = modeling.createInterfaceOSH(interface.ifMac, aSwitch.hostOSH, interface.ifDescr, interface.ifIndex, interface.ifType, interface.ifAdminStatus, interface.ifOperStatus, interface.ifSpeed, interface.ifName, interface.ifAlias)
                if intfOsh:
                    ObjSHV.add(modeling.createLinkOSH('realization', aPtOSH, intfOsh))
            #in case we get a MAC for remote iface and this is a real MAC report a Layer2Connection between these interfaces
            if self.remoteTermMac and not self.remoteTermMac.endswith(":" + self.portNumber) and netutils.isValidMac(self.remoteTermMac):
                logger.debug('Created L2C from Ports')
                #write the reported layer2 info to file in order to post process in case of remote MAC "Multiple Match" 
                md5_obj = md5.new()
                updateValue = ''
                vlan_id = self.framework.getDestinationAttribute('snmpCommunityPostfix')
                for value in [interface.ifMac.upper(), interface.ifDescr, interface.ifIndex, interface.ifType, interface.ifAdminStatus, interface.ifOperStatus, interface.ifSpeed, interface.ifName, interface.ifAlias, vlan_id]:
                    if not updateValue:
                        updateValue = str(value)
                    else:
                        updateValue = updateValue + ':::' + str(value)
                md5_obj.update(updateValue)
                
                filename = md5_obj.hexdigest()
                filepath = os.path.join(CollectorsParameters.HOME_DIR, 'runtime/l2reported/')
                if not os.path.exists(filepath):
                    try:
                        os.mkdir(filepath)
                    except:
                        logger.debug('folder creation failed')
                f = open(filepath+filename,'w')
                f.write(updateValue+'\n')
                macsSeparated = ''
                for mac in [self.remoteTermMacRaw.get(self.remoteTermMac)]:
                    if mac.count('.'):
                        mac = self.convertToHexString(mac)
                    if not macsSeparated:
                        macsSeparated = mac
                    else:
                        macsSeparated = macsSeparated + ':::' + mac
                f.write(macsSeparated)
                f.close()
                
                ObjSHV.addAll(modeling.createLayer2ConnectionWithLinks([self.remoteTermMacRaw.get(self.remoteTermMac)], aSwitch, interface))
    
    def __setRemotePortNumber(self, portOsh, remoteNumber):
        'osh, number -> None'
        if remoteNumber:
            try:
                remoteIndex = int(remoteNumber)
            except:
                if not modeling.checkAttributeExists(portOsh.getObjectClass(), 'port_remote_index'):
                    portOsh.setAttribute('port_remotestpptid', remoteNumber)
            else:
                modeling._CMDB_CLASS_MODEL.setAttributeIfExists(portOsh, 'port_remote_index', remoteIndex, AppilogTypes.INTEGER_DEF)

    def convertToHexString(self, aDottedString):
        return(''.join([re.findall('..$', hex(int(x)).upper())[0] for  x in aDottedString.split('.')]).replace('X','0'))

#++++++++++
class Concentrator:
#++++++++++
    def convertToHexString(self, aDottedString):
        return(''.join([re.findall('..$', hex(int(x)).upper())[0] for  x in aDottedString.split('.')]).replace('X','0'))

    def __init__(self, myName, parentSwitch, listOfMacs, ObjSHV, discInst, ucmdbversion, localInterface = None, framework = None):
        self.parentSwitch = parentSwitch
        self.name = myName
        self.ports = None            # list of SwitchPort objects.
        self.localBridgeId = None
        vlan_id = framework.getDestinationAttribute('snmpCommunityPostfix')
        md5_obj = md5.new()
        updateValue = ''
        for value in [localInterface.ifMac.upper(), localInterface.ifDescr, localInterface.ifIndex, localInterface.ifType, localInterface.ifAdminStatus, localInterface.ifOperStatus, localInterface.ifSpeed, localInterface.ifName, localInterface.ifAlias]:
            if not updateValue:
                updateValue = str(value)
            else:
                updateValue = updateValue + ':::' + str(value)
        md5_obj.update(updateValue)
        if vlan_id:
            md5_obj.update(vlan_id)
        filename = md5_obj.hexdigest()
        filepath = os.path.join(CollectorsParameters.HOME_DIR, 'runtime/l2process/')
        if not os.path.exists(filepath):
            try:
                os.mkdir(filepath)
            except:
                logger.debug('folder creation failed')
        file = open(filepath+filename,'w')
        file.write(updateValue+'\n')
        macsSeparated = ''
        for mac in listOfMacs:
            if mac.count('.'):
                mac = self.convertToHexString(mac)
            if not macsSeparated:
                macsSeparated = mac
            else:
                macsSeparated = macsSeparated + ':::' + mac
        file.write(macsSeparated)
        file.close()
    def hasIntfcMac(self, aMacAddr):
        logger.debug('looking for mac in concentrator mac is ', aMacAddr)
        return (self.parentSwitch.hasIntfcMac(aMacAddr))

#++++++++++
class SnmpAgent:
#++++++++++
    def __init__(self, anIP, commString, ptString, timeOutNum, retryNum):
        self.address = anIP
        self.community = commString
        self.port = ptString
        self.timeOut = timeOutNum
        self.retries = retryNum

#++++++++++
class RunInstance:
#++++++++++
    def __init__(self):
        self.inst = Date().toGMTString()

    def thisInst(self):
        return self.inst

#################
##
## Main Starts here
##
#################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ObjSHV = ObjectStateHolderVector()
    discInst = RunInstance()
    ipAddressList = Framework.getTriggerCIDataAsList('ip_address')
    credentialsList = Framework.getTriggerCIDataAsList('credentialsId')
    bridgeId = Framework.getDestinationAttribute('bridgeId')
    hostIdList = Framework.getTriggerCIDataAsList('hostId')
    ucmdbVersion = modeling.CmdbClassModel().version()
    
    
    snmpCommunityPostfix = ''
    try:
        snmpCommunityPostfix = Framework.getDestinationAttribute('snmpCommunityPostfix')
        hostModel = Framework.getDestinationAttribute('hostModel')
        hostOs = Framework.getDestinationAttribute('hostOs')
        snmpDescription = Framework.getDestinationAttribute('smpDescription')
    except:
        pass

    SwitchesNumber = len(credentialsList)
    for i in range(SwitchesNumber):
        ipAddress = ipAddressList[i]
        hostId = hostIdList[i]
        credId = credentialsList[i]
        
        properties = Properties()

        if credId and ipAddress:
            properties.setProperty('ip_address', ipAddress)
            properties.setProperty(BaseClient.CREDENTIALS_ID, credId)
        sw = Switch(bridgeId, hostId, ucmdbVersion, Framework)
        if (snmpCommunityPostfix != None) and (snmpCommunityPostfix != ''):
            device_type_str = '%s%s%s' % (hostModel.lower(),
                                          hostOs.lower(),
                                          snmpDescription.lower())
            if device_type_str.find('atalyst')!=-1 or device_type_str.find('cisco')!=-1:
                snmp_version = Framework.getProtocolProperty(credId, "snmpprotocol_version")
                if snmp_version == 'version 3':
                    props = Properties()
                    props.setProperty('ip_address', ipAddress)
                    props.setProperty(BaseClient.CREDENTIALS_ID, credId)
                    client = Framework.createClient(props)
                    vlan_context_dict = snmputils.get_snmp_vlan_context_dict(client)
                    client and client.close()

                    if not vlan_context_dict:
                        raise Exception, "Vlan Conext is not present on the device. No Vlan details might be discovered"
                    
                    vlan_context = vlan_context_dict.get(snmpCommunityPostfix)
                    if not vlan_context:
                        raise Exception, "Failed to find configured Vlan context for Vlan %s. Vlan will be skipped" % snmpCommunityPostfix
                    
                    properties.setProperty(SnmpQueries._postfix, '%s' % vlan_context)
                else:
                    properties.setProperty(SnmpQueries._postfix,'@%s' % snmpCommunityPostfix)
            else:
                sw = QBridgeSwitch(snmpCommunityPostfix, bridgeId, hostId, ucmdbVersion, Framework)
                sw.set_device_type_str(device_type_str)
        if logger.isDebugEnabled():
            logger.debug('ip', ipAddress)
            logger.debug('bridgeMac', bridgeId)
            logger.debug('Postfix', snmpCommunityPostfix)

        try:
            sw.snmpClient = Framework.createClient(properties)
            #SnmpConnectionTester(sw.snmpClient).testSnmpConnection()
            sw.doWork(ObjSHV, discInst)
            OSHVResult.addAll(ObjSHV)
        except:
            logger.debugException('')
            if (snmpCommunityPostfix != None) and (snmpCommunityPostfix != ''):
                logger.error('Failed to discover ip: ', ipAddress, ' on Vlan#: ', snmpCommunityPostfix)
            else:
                logger.error('Failed to discover ip: ', ipAddress )
        if sw.snmpClient != None:
            sw.snmpClient.close()
    return OSHVResult
