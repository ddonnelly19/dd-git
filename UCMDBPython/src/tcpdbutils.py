#coding=utf-8
from com.hp.ucmdb.discovery.common import CollectorsConstants
import logger
import modeling

import discoverydbutils

from java.lang import System
from java.util import Hashtable

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile



class PortToProcess(discoverydbutils.DiscoveryDbEntity):
	DELETESQL = 'delete from %s where hostid=\'%s\' and stamp < %s'
	PORTTOPROCESSTYPE = 'porttoprocess'

	PREPAREDSQL  = '''
	WITH new_values(hostid, ipaddress, port, pid, Protocol, listen, ProcessName, stamp)
	AS (VALUES (?,?,?,?,?,?,?,?)),
	upsert AS (UPDATE Port_Process p
			SET hostid = nv.hostid,
			listen = nv.listen,
			ProcessName = nv.ProcessName,
			stamp = nv.stamp,
			pid = CASE WHEN nv.pid > 0 THEN nv.pid else p.pid END
			FROM new_values AS nv
			WHERE p.ipaddress = nv.ipaddress AND p.port = nv.port
			AND p.pid = nv.pid AND p.protocol = nv.protocol AND p.listen = nv.listen
			RETURNING p.ipaddress
	)
	INSERT INTO Port_Process(hostid, ipaddress, port, pid, Protocol, listen, ProcessName, stamp)
	SELECT hostid, ipaddress, port, pid, Protocol, listen, ProcessName, stamp
	FROM new_values
	WHERE NOT EXISTS (SELECT 1 FROM upsert)'''

	def __init__(self, hostid, ip, port, pid, protocol, listen, ProcessName):
		self.hostid = hostid
		self.ip = ip
		self.port = int(port)
		self.pid = int(pid)
		self.protocol = protocol
		self.listen = listen
		self.ProcessName = ProcessName

	def getEntityType(self):
		return PortToProcess.PORTTOPROCESSTYPE

	def getInsertSQL(self):
		return PortToProcess.PREPAREDSQL

	def setValues(self, statement):
		statement.setString(1, self.hostid)
		statement.setString(2, self.ip)
		statement.setInt(3, self.port)
		statement.setInt(4, self.pid)
		statement.setInt(5, self.protocol)
		statement.setBoolean(6, self.listen)
		statement.setString(7, self.ProcessName)
		statement.setLong(8, System.currentTimeMillis())

class TcpConnection(discoverydbutils.DiscoveryDbEntity):
	DELETESQL = 'delete from %s where hostid=\'%s\' and stamp < NOW() - INTERVAL \'%s hours\''
	TCPCONNECTIONTYPE = 'tcpconnection'

	#We set in the sql below 16(0x0010) for acknowledged and 6 for tcp type since in tcp discovery these are the only values
	#while in netflow they can be different
	PREPAREDSQL  = '''
	WITH new_values (RouterIP, SysUptime, SrcAddr, DstAddr, SrcPort, DstPort, Tcp_Flags, Prot, Stamp, hostid)
	AS (VALUES('TCP_Discoverer', ?, ?, ?, ?, ?, 16, 6, now(), ?)),
	upsert AS (UPDATE Agg_V5 p
	SET Stamp=now(),
	SysUptime = nv.SysUptime
	FROM new_values as nv
	WHERE p.srcaddr = nv.srcaddr AND p.dstaddr = nv.dstaddr
		AND p.srcport = nv.srcport AND p.dstport = nv.dstport AND p.prot = nv.prot
	RETURNING p.prot
	)
	INSERT INTO Agg_V5 (RouterIP, SysUptime, SrcAddr, DstAddr, SrcPort, DstPort, Tcp_Flags, Prot, Stamp, hostid)
	SELECT RouterIP, SysUptime, SrcAddr, DstAddr, SrcPort, DstPort, Tcp_Flags, Prot, Stamp, hostid
	FROM new_values
	WHERE NOT EXISTS (SELECT 1 from upsert)
	'''
	def __init__(self, hostid, srcAddr, dstAddr, srcPort, dstPort):
		self.hostid = hostid
		self.srcAddr = srcAddr
		self.dstAddr = dstAddr
		self.srcPort = srcPort
		self.dstPort = dstPort

	def getEntityType(self):
		return TcpConnection.TCPCONNECTIONTYPE

	def getInsertSQL(self):
		return TcpConnection.PREPAREDSQL

	def setValues(self, statement):
		statement.setLong(1, System.currentTimeMillis())
		statement.setString(2, self.srcAddr)
		statement.setString(3, self.dstAddr)
		statement.setInt(4, self.srcPort)
		statement.setInt(5, self.dstPort)
		statement.setString(6, self.hostid)


class TcpDbUtils(discoverydbutils.DiscoveryDbUtils):
	CONTEXT = 'tcpdiscovery'

	TCP_EXECUTED_JOBS = Hashtable()

	def __init__(self, Framework):
		discoverydbutils.DiscoveryDbUtils.__init__(self, Framework, TcpDbUtils.CONTEXT)
		self.knownPortsConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
		self.applicSignConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_APPLICATIONSIGNATURE)
		self.hostID = Framework.getDestinationAttribute('hostId')

		globalSettings = GeneralSettingsConfigFile.getInstance()
		#hours
		self.TCP_EXPIRATION_PERIOD = globalSettings.getPropertyIntegerValue('tcpExpirationTime', 24)
		#milliseconds
		self.PORT_EXPIRATION_PERIOD = globalSettings.getPropertyIntegerValue('portExpirationTime', 60) * 1000L

	def addPortToProcess(self, ipaddress, port, process_pid, listen = 0, prot = modeling.TCP_PROTOCOL, ProcessName = None):
		pid = -1
		if process_pid != None:
			pid = int(process_pid)
		port2process = PortToProcess(self.hostID, ipaddress, int(port), pid, prot, listen, ProcessName)
		self.addToBulk(port2process)

	def flushPortToProcesses(self):
		self.executeUpdate(PortToProcess.DELETESQL % ('Port_Process', self.hostID, str(System.currentTimeMillis() - self.PORT_EXPIRATION_PERIOD)))
		self.executeBulk(PortToProcess.PORTTOPROCESSTYPE);
		TcpDbUtils.TCP_EXECUTED_JOBS.clear()

	def addTcpConnection(self, srcAddr, srcPort, dstAddr, dstPort):
		tcpConnection = TcpConnection(self.hostID,srcAddr, dstAddr, srcPort, dstPort)
		self.addToBulk(tcpConnection)

	def flushTcpConnection(self):
		self.executeUpdate(TcpConnection.DELETESQL % ('Agg_V5', self.hostID, self.TCP_EXPIRATION_PERIOD))
		self.executeBulk(TcpConnection.TCPCONNECTIONTYPE)
		TcpDbUtils.TCP_EXECUTED_JOBS.clear()

def shouldDiscoverTCP(Framework):
	from com.hp.ucmdb.discovery.probe.services.netlinks.dal import NetLinksSqlDAO
	executionSignaturePrefix = getExecutionSignaturePrefix(Framework)
	executionSignatureParameters = getExecutionSignatureParameters(Framework)
	executionSignature = executionSignaturePrefix + '->' + executionSignatureParameters
	if logger.isDebugEnabled():
		logger.debug('New processes execution signature:', executionSignature)
	oldExecutionSignature = TcpDbUtils.TCP_EXECUTED_JOBS.put(executionSignaturePrefix, executionSignature)
	if logger.isDebugEnabled():
		if oldExecutionSignature != None:
			logger.debug('Previous processes execution signature:', oldExecutionSignature)
	return NetLinksSqlDAO.shouldExecuteQuery(executionSignature) or (oldExecutionSignature == None) or (oldExecutionSignature != executionSignature)

def getExecutionSignaturePrefix(Framework):
	destId = Framework.getTriggerCIData(CollectorsConstants.DESTINATION_DATA_ID)
	return Framework.getDiscoveryJobId() + '_' + destId

def getExecutionSignatureParameters(Framework):
	signature = ''
	parameters = Framework.getDeclaredParameters()
	if parameters != None:
		signature = str(parameters)

		ip_address = Framework.getDestinationAttribute('ip_address')
		if ip_address != None:
			signature = signature + ip_address

	return signature


def resetShouldDiscoverTCP(Framework):
	executionSignaturePrefix = getExecutionSignaturePrefix(Framework)
	TcpDbUtils.TCP_EXECUTED_JOBS.remove(executionSignaturePrefix)
