#####################################
# Created on Oct 10, 2010
#
# Author: Pat Odom
#
# Mainframe discovery of MQ Series
# Changed calls to use new Agent Rexx Function to fix defect QC 37346. (Limitation in IBM Console output to 32000 characters). This fix uses
# programatic calls in the Agent instead of console calls avoiding the 32000 limit.  P. Odom
# Fixed QCIM1H64777 MQ by Eview pattern fails with error code.
# CP15 - Add Model Queue to QTYPEMAP, defect QCCR1H79041
######################################

import string, re, logger, modeling
import eview_lib
import errorcodes, errorobject

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from eview_lib import isNotNull, isNull


# Variables

global Framework
UCMDB_VERSION = modeling._CMDB_CLASS_MODEL.version()
PARAM_HOST_ID = 'hostId'
DISCOVER_REMOTE_HOSTS = 'true'

# MQ Commands
_CMD_D_SYMBOLS = 'D SYMBOLS'
_CMD_PREFIX_DISPLAY_SYSTEM = 'DISPLAY SYSTEM'
#_CMD_PREFIX_DISPLAY_GROUP = '%s DISPLAY GROUP'
_CMD_PREFIX_DISPLAY_QMGR = 'DISPLAY QMGR ALL'
_CMD_PREFIX_DISPLAY_CHINIT = 'DISPLAY CHINIT'
_CMD_PREFIX_DISPLAY_QUEUE = 'DISPLAY QUEUE (*) RNAME,RQMNAME,XMITQ,USAGE,DESCR,CLUSTER,CLUSNL,TARGQ,PROCESS'
_CMD_PREFIX_DISPLAY_CHANNEL = 'DISPLAY CHANNEL (*) CHLTYPE TRPTYPE DESCR CLUSTER CLUSNL CONNAME XMITQ'
_CMD_PREFIX_DISPLAY_PROCESS = 'DISPLAY PROCESS (*) DESCR,APPLICID,USERDATA,APPLTYPE'

# Mapping for QUEUE OSH and Type
QTYPEMAP = {'QALIAS':'Alias Queue', 'QLOCAL':'Local Queue', 'QREMOTE':'Remote Queue', 'XMITQ':'Transmission Queue', 'SYSTEM':'System Queue', 'OTHER':'Other', 'QMODEL': 'Model Queue'}
QOSHTYPEMAP = {'QALIAS':'mqaliasqueue', 'QLOCAL':'mqlocalqueue', 'QREMOTE':'mqremotequeue', 'XMITQ':'mqtransmitqueue', 'SYSTEM':'mqqueue', 'OTHER':'mqqueue', 'QMODEL':'mqqueue'}
RECEIVERCHLTYPEMAP = {'CLUSRCVR':'Cluster Receiver Channel', 'RCVR':'Receiver Channel', 'CLNTCONN':'Client Connection Channel', 'RQSTR':'Requestor Channel'}
SENDERCHLTYPEMAP = {'CLUSSDR':'Cluster Sender Channel', 'SDR':'Sender Channel', 'SVRCONN':'Server Connection Channel', 'SVR':'Server Channel'}

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
	return ''.join(map(str,args))

# Class Definitions
#
class MQQueue:
	def __init__(self, qname, qtype, qdesc, qprocess, qusage, qcluster, qclusnl, qtarget, xmitq,rname,rqmname):
		self.id = id
		self.qname = qname
		self.qtype = qtype
		self.qdesc = qdesc
		self.qprocess = qprocess
		self.qusage = qusage
		self.qcluster = qcluster
		self.qclusnl = qclusnl
		self.qtarget = qtarget
		self.xmitq = xmitq
		self.rname = rname
		self.rqmname = rqmname


class MQChannel:
	def __init__(self, channel,chldesc,chltype,trptype,cluster,clusnl,conname,xmitq, host, port):
		self.id = id
		self.channel = channel
		self.chldesc = chldesc
		self.chltype = chltype
		self.trptype = trptype
		self.cluster = cluster
		self.clusnl = clusnl
		self.conname = conname
		self.xmitq = xmitq
		self.host = host
		self.port = port

class MQProcess:
	def __init__(self, process,procdescr,applicid,userdata,appltype,procdisp):
		self.id = id
		self.process = process
		self.procdescr = procdescr
		self.applicid = applicid
		self.userdata = userdata
		self.appltype = appltype
		self.procdisp = procdisp


# Methods

####################################
##  Create MQ subsystem OSH       ##
####################################
def testMQup (ls, subsystem):

	mqup = 1
	#subsystem = cmd_prefix.replace('%','')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_SYSTEM, '50', subsystem)
	#logger.debug('*** checkpoint 100')
	#output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_SYSTEM % cmd_prefix)

	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:

			# Look to see if we get a line that indicates that the Queue Manager is stopped.
			#line = "CSQ3106E %CSQ7    CSQ3EC0X - QUEUE MANAGER STOPPED. COMMAND NOT PROCESSED - %CSQ7 DISPLAY SYSTEM"
			r1 = re.compile('QUEUE MANAGER STOPPED',re.IGNORECASE)
			r2 = re.compile('reason=2059',re.IGNORECASE)
			r3 = re.compile('Unable to connect',re.IGNORECASE)
			if r1.search(line) or r2.search(line) or r3.search(line):
				mqup = 0
	return mqup

####################################
##  Create MQ subsystem OSH       ##
####################################
def createmqSubsystemOsh(lparOsh, mqSubsystem):
	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose

	mqSubsystemOsh = ObjectStateHolder('mainframe_subsystem')
	mqSubsystemOsh.setAttribute(str_name, mqSubsystem[0])
	mqSubsystemOsh.setAttribute(str_discovered_product_name, mqSubsystem[0])
	mqSubsystemOsh.setAttribute('type', 'MQ')
	mqSubsystemOsh.setAttribute('initialization_routine', mqSubsystem[1])      #INITRTN
	mqSubsystemOsh.setAttribute('initialization_parameters', mqSubsystem[2])   #INITPARM
	mqSubsystemOsh.setAttribute('command_prefix', mqSubsystem[3])
	mqSubsystemOsh.setContainer(lparOsh)
	return mqSubsystemOsh

######################################################
##  Get  Sysplex from the system if there is one   ##
######################################################

def getSysPlexOSH(ls):
	# process SYMLIST ----------------------------------------------------------
	symbolsMap = {} # {name:value}
	output = ls.evMvsCmd(_CMD_D_SYMBOLS)
	#logger.debug('*** checkpoint 101')
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		symbolsList = output.getValuesFromLineList('s', output.cmdResponseList, '&', '\.\s+=\s+"', '"')
		for symbols in symbolsList:
			if len(symbols) == 4:
				symbolName = symbols[1]
				symbolValue = symbols[2]
				if isNotNull(symbolName) and isNotNull(symbolValue):
					symbolsMap[symbolName] = symbolValue
	str_name = 'name'
	if UCMDB_VERSION  < 9:
		str_name = 'data_name'
	sysplexOsh = None
	if symbolsMap.has_key('SYSPLEX'):
		sysplexOsh = ObjectStateHolder('mainframe_sysplex')
		sysplexOsh.setAttribute(str_name, symbolsMap['SYSPLEX'])
	else:
		logger.warn("No sysplex found")

	return  sysplexOsh
######################################################
##  Create the MQ System Paramter OSH               ##
######################################################
def createmqSysParamOSH(ls, lparOsh, sysParmNumeric, sysParmString, mqSubsystemOSH , xcfmember):

	# Define the mapping of the attribute names to the parameter names
	#
	sysParmAttrDict = { 'LOGLOAD': 'mqsystemparameters_logload',
						'WLMTIME': 'mqsystemparameters_wlmtime',
						'EXITTCB': 'mqsystemparameters_exittcb',
						'ROUTCDE': 'mqsystemparameters_routcde',
						'STATIME': 'mqsystemparameters_statime',
						'AGE': 'mqsystemparameters_otma_age',
						'TRACTBL': 'mqsystemparameters_tractbl',
						'TRACSTR': 'mqsystemparameters_tracstring',
						'DB2BLOB': 'mqsystemparameters_db2blob',
						'EXITLIM': 'mqsystemparameters_exitlim',
						'IDBACK': 'mqsystemparameters_idback',
						'QMCSSID': 'mqsystemparameters_qmccsid',
						'DB2SERV': 'mqsystemparameters_qsgdata_db2servers',
						'IDFORE': 'mqsystemparameters_idfore',
						'RESAUDIT': 'mqsystemparameters_resaudit',
						'SMFACCT': 'mqsystemparameters_smfacct',
						'CMDUSER': 'mqsystemparameters_cmduser',
						'CLCACHE': 'mqsystemparameters_clcache',
						'WLMTIMU': 'mqsystemparameters_wlmtimunit',
						'DRUEXIT': 'mqsystemparameters_otma_druexit',
						'SMFSTAT': 'mqsystemparameters_smfstat',
						'QINDXBLD': 'mqsystemparameters_qindxbld',
						'TPIPEPFX': 'mqsystemparameters_otma_tpipeprefix',
						'QSGNAME': 'mqsystemparameters_qsgdata_qsgname',
						'DSGNAME': 'mqsystemparameters_qsgdata_dsgname',
						'DB2NAME': 'mqsystemparameters_qsgdata_db2name',
						'GROUP': 'mqsystemparameters_otma_group',
						'MEMBER': 'mqsystemparameters_otma_member' }

	vector = ObjectStateHolderVector()
	sysplexOsh = None
	xcfGroupOsh = None
	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose

	mqSysParamOsh = ObjectStateHolder('mqsystemparameters')
	mqSysParamOsh.setContainer(mqSubsystemOSH)
	mqSysParamOsh.setAttribute(str_name, 'MQ System Parameters')
	#mqSysParamOsh.setAttribute(str_discovered_product_name, 'MQ System Parameters')
	for paramname in sysParmNumeric.keys():
		if sysParmAttrDict.has_key(paramname):
			attr = sysParmAttrDict[paramname]
			if paramname == 'AGE' or paramname == 'LOGLOAD':
				#logger.debug ('Creating Long parameter ===> ',  attr, '   ',sysParmNumeric[paramname])
				mqSysParamOsh.setLongAttribute(attr, sysParmNumeric[paramname] )
			else:
				#logger.debug ('Creating Integer parameter ===> ',  attr, '   ',sysParmNumeric[paramname])
				mqSysParamOsh.setIntegerAttribute(attr, sysParmNumeric[paramname])

	for paramname in sysParmString.keys():
		if sysParmAttrDict.has_key(paramname):
			attr = sysParmAttrDict[paramname]
			#logger.debug ('Creating String parameter ===> ',  attr, '   ',sysParmString[paramname])
			mqSysParamOsh.setAttribute(attr, sysParmString[paramname])

	vector.add ( mqSysParamOsh)
	#
	# QSGNAME is the name of the MQ Queue Sharing Group to which this Queue manager belongs
	# so create a queue sharing group for it and link it to the MQ subsystem
	#
	if sysParmString.has_key('QSGNAME'):
		queueSharingGroupOsh = ObjectStateHolder('mqqueuesharinggroup')
		queueSharingGroupOsh.setAttribute(str_name, sysParmString[paramname])
		#logger.debug ('Creating QSGNAME ===> ', '   ',sysParmString[paramname])
		vector.add (queueSharingGroupOsh)
		if UCMDB_VERSION < 9:
			vector.add (modeling.createLinkOSH('depend', queueSharingGroupOsh, mqSubsystemOSH))
		else:
			vector.add (modeling.createLinkOSH('dependency', queueSharingGroupOsh, mqSubsystemOSH))
	#
	# DSGNAME is the name of the DB2 Data Sharing Group to which this Queue manager belongs
	# so create a db2 sharing group for it and link it to the MQ subsystem
	#
	if  sysParmString.has_key('DSGNAME'):
		db2SharingGroupOsh = ObjectStateHolder('db2_datasharing_group')
		db2SharingGroupOsh.setAttribute(str_name, sysParmString[paramname])
		vector.add (db2SharingGroupOsh)
		#logger.debug ('Creating DSGNAME ===> ', '   ',sysParmString[paramname])
		if UCMDB_VERSION < 9:
			vector.add (modeling.createLinkOSH('depend', db2SharingGroupOsh, mqSubsystemOSH))
		else:
			vector.add (modeling.createLinkOSH('dependency', db2SharingGroupOsh, mqSubsystemOSH))
	#
	# GROUP is the name of the XCF Group to which this instance of MQ belongs
	# so create a XCF group for it
	#
	if  sysParmString.has_key('GROUP'):
		sysplexOsh = getSysPlexOSH(ls)
		if isNotNull(sysplexOsh):
			vector.add (sysplexOsh)
			xcfGroupOsh = ObjectStateHolder('mainframe_xcf_group')
			xcfGroupOsh.setAttribute(str_name, sysParmString[paramname])
			xcfGroupOsh.setContainer(sysplexOsh)
			#logger.debug ('Creating GROUP ===> ', '   ',sysParmString[paramname])
			vector.add(xcfGroupOsh)

			if isNotNull(xcfGroupOsh):
				if UCMDB_VERSION < 9:
					memberLinkOsh = modeling.createLinkOSH('member', sysplexOsh , lparOsh)
				else:
					memberLinkOsh = modeling.createLinkOSH('membership', sysplexOsh, lparOsh)
				vector.add(memberLinkOsh)
	#
	# MEMBER is the name of the XCF Member in the XCF Group
	# so create a XCF Member for it . We have to do this last becuase the GROUP may not exist until all
	# in the Dictionary is processed.
	#
	if isNotNull(xcfmember):
		if isNotNull(xcfGroupOsh):
			memberOsh = ObjectStateHolder('mainframe_xcf_member')
			memberOsh.setAttribute(str_name, xcfmember )
			memberOsh.setContainer(xcfGroupOsh)
			#logger.debug ('Creating MEMBER ===> ', '   ',sysParmString[paramname])
			vector.add(memberOsh)

	vector.add ( mqSysParamOsh)
	return vector

###############################################################
##  Create the MQ Queue Manager  OSH  and related Queues     ##
###############################################################
def createQMGROSH(ls, lparOsh,  sysParmString, mqSubsystemOSH ):

	qOshDict = {}
	# Define the mapping of the attribute names to the parameter names
	#
	sysParmAttrDict = { 'QMNAME': 'name', # Overridden below becuase of multiple versions / differnt attributes
						'DESCR': 'data_description',
						'QMID': 'mqqueuemanager_qmid',
						'QSGNAME': 'mqqueuemanager_qsgname',
						'COMMANDQ': 'mqqueuemanager_cmdqname',
						'DEADQ': 'mqqueuemanager_dlqname',
						'DEFXMITQ': 'mqqueuemanager_defaultxmitqname'}

	vector = ObjectStateHolderVector()

	# Handle the name attribute depending on the version of UCMDB

	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose

	#   ## Build Websphere MQ OSH for this MQ
	Mqname = concatenate('IBM WebSphere MQ ',mqSubsystemOSH.getAttribute(str_name).getValue())
	MqOSH = ObjectStateHolder('webspheremq')
	MqOSH.setAttribute(str_name, Mqname)
	MqOSH.setAttribute('vendor', 'ibm_corp')
	MqOSH.setAttribute('application_category', 'Messaging')
	modeling.setApplicationProductName(MqOSH,'IBM WebSphere MQ')
	MqOSH.setContainer(lparOsh)
	vector.add(MqOSH)
	mqQMGROsh = ObjectStateHolder('mqqueuemanager')
	commandQueueOSH = ObjectStateHolder('mqlocalqueue')
	xmitQueueOSH = ObjectStateHolder(QOSHTYPEMAP['XMITQ'])
	if sysParmString.has_key('QMNAME'):

		mqQMGROsh.setContainer(MqOSH)
		for paramname in sysParmString.keys():
			if sysParmAttrDict.has_key(paramname):
				if paramname == 'QMNAME':
					mqQMGROsh.setAttribute(str_name, sysParmString[paramname])
					#mqQMGROsh.setAttribute(str_discovered_product_name, sysParmString[paramname])
				else:
					attr = sysParmAttrDict[paramname]
					mqQMGROsh.setAttribute(attr, sysParmString[paramname])
					#logger.debug ('Creating String parameter ===> ',  attr, '   ',sysParmString[paramname])
		vector.add ( mqQMGROsh)
		#
		# COMMANDQ indicates that we have a Command Queue so we need to create the local queue OSH
		#
		#
		if  sysParmString.has_key('COMMANDQ'):

			commandQueueOSH.setAttribute(str_name, sysParmString['COMMANDQ'])
			commandQueueOSH.setContainer(mqQMGROsh)
			vector.add(commandQueueOSH)
			dependLinkOsh = modeling.createLinkOSH('depend' , commandQueueOSH , mqQMGROsh)
			vector.add(dependLinkOsh)
			keyname = sysParmString['COMMANDQ']+sysParmString['QMNAME'].strip()
			qOshDict[keyname] = commandQueueOSH
		#
		#
		# DEFXMITQ indicates that we have a the Default Transmission Queue.
		#
		#
		if  sysParmString.has_key('DEFXMITQ'):

			xmitQueueOSH.setStringAttribute(str_name, sysParmString['DEFXMITQ'])
			xmitQueueOSH.setStringAttribute('queue_type', QTYPEMAP['XMITQ'])
			xmitQueueOSH.setContainer(mqQMGROsh)
			vector.add(xmitQueueOSH)
			dependLinkOsh = modeling.createLinkOSH('depend', xmitQueueOSH , mqQMGROsh)
			vector.add(dependLinkOsh)
			keyname = sysParmString['DEFXMITQ']+sysParmString['QMNAME'].strip()
			qOshDict[keyname] = xmitQueueOSH



	return vector, mqQMGROsh,  qOshDict

###############################################################
##  Create the MQ Channel Initiator OSH                      ##
###############################################################
def createCHINITOSH(ls, lparOsh,  parmString, parmNumeric, mqSubsystemOSH ):

	# Define the mapping of the attribute names to the parameter names
	#
	parmAttrDict = {    'LPORT': 'mqchinit_tcplistenerport',
						'LADDR': 'mqchinit_tcplisteneraddr',
						'MAXCHAN': 'mqchinit_maxcurrentchannels',
						'MAXACTCHAN': 'mqchinit_maxactivechannels',
						'SUBSTARTED': 'mqchinit_maxcurrentstarted',
						'MAXTCP': 'mqchinit_maxtcpchannels',
						'MAXLU': 'mqchinit_maxluchannels',
						'TCPSYSNAME': 'mqchinit_tcpsystemname',
						'LNAME': 'mqchinit_tcplistenername',
						'LSTATUS': 'mqchinit_tcplistenerstatus',
						'LUSYSNAME': 'mqchinit_lusystemname',
						'LULSTATUS': 'mqchinit_lulistenerstatus'}

	vector = ObjectStateHolderVector()

	# Handle the name attribute depending on the version of UCMDB

	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose

	mqChannelInitiatorOSH = ObjectStateHolder('mqchinit')
	mqChannelInitiatorOSH.setContainer(mqSubsystemOSH)
	mqChannelInitiatorOSH.setAttribute(str_name, 'MQ Channel Initiator')
	#mqChannelInitiatorOSH.setAttribute(str_discovered_product_name, 'MQ Channel Initiator')
	for paramname in parmNumeric.keys():
		if parmAttrDict.has_key(paramname):
			attr = parmAttrDict[paramname]
			#logger.debug ('Creating Integer parameter ===> ',  attr, '   ', parmNumeric[paramname])
			mqChannelInitiatorOSH.setIntegerAttribute(attr, int(parmNumeric[paramname]))

	for paramname in parmString.keys():
		if parmAttrDict.has_key(paramname):
			attr = parmAttrDict[paramname]
			#logger.debug ('Creating String parameter ===> ',  attr, '   ', parmString[paramname])
			mqChannelInitiatorOSH.setAttribute(attr, parmString[paramname])

	vector.add ( mqChannelInitiatorOSH)
	return vector

###############################################################
##  Create the MQ QUEUE OSH                                  ##
###############################################################
def createQUEUEOSH(ls, subsystem, lparOsh, queueList,  mqSubsystemOSH , mqQMGROsh, qOshDict):


	vector = ObjectStateHolderVector()
	if mqQMGROsh == None:
		return
	# Handle the name attribute depending on the version of UCMDB
	attrqtype = None
	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose
	# Process all the entries in the Queue List and build the OSH
	qMgrName = mqQMGROsh.getAttribute(str_name).getValue()
	#logger.debug('*** len of queueList = ', len(queueList))
	count = 0
	if isNotNull(queueList) and len(queueList) > 0:
		for (key, val) in queueList.items():
			count += 1
			#logger.debug('*** count2 = ', count)
			queuename = key
			queuedesc = val.qdesc
			queuetype = val.qtype
			queueusage = val.qusage
			queueprocess = val.qprocess
			queuecluster = val.qcluster
			queueclusnl = val.qclusnl
			queuetarget = val.qtarget
			xmitqueue = val.xmitq
			rname = val.rname
			rqmname = val.rqmname
			#logger.debug('*** checkpoint 1')
			dictkey = (queuename+qMgrName).strip()
			#logger.debug('*** checkpoint 2')
			if QOSHTYPEMAP.has_key(queuetype):
				OSHType = QOSHTYPEMAP[queuetype]
				if QTYPEMAP.has_key(queuetype):
					attrqtype = QTYPEMAP[queuetype]
			else:
				OSHType = 'mqqueue'
				attrqtype  = 'Other Queue'

			if not(dictkey) in qOshDict.keys():
				#logger.debug ('Creating Queue type ===> ',queuetype, '  Name ===> ',queuename,'qOshDict key ===> ',dictkey)
				mqQueueOsh = ObjectStateHolder(OSHType)
				mqQueueOsh.setContainer(mqQMGROsh)
				mqQueueOsh.setAttribute(str_name, queuename)
				mqQueueOsh.setAttribute('queue_type', attrqtype)
				vector.add(mqQueueOsh)
				qOshDict[dictkey] = mqQueueOsh
				#logger.debug('*** checkpoint 3')
			################################
			## Check if this Queue is associated with a cluster
			##############################
			if isNotNull(queuecluster):
				#logger.debug('*** checkpoint 300')
				clusterOsh = ObjectStateHolder('mqcluster')
				clusterOsh.setAttribute(str_name, queuecluster)
				#clusterOsh.setAttribute(str_discovered_product_name, queuecluster)
				vector.add(clusterOsh)
				vector.add(modeling.createLinkOSH('member', clusterOsh, mqQueueOsh))
				#logger.debug('*** checkpoint 301')
				vector.add(modeling.createLinkOSH('member', clusterOsh, mqQMGROsh))
				#logger.debug('*** checkpoint 4')
			################################
			## Check if this Queue is associated with a cluster namelist
			##############################
			if isNotNull(queueclusnl):
				#logger.debug('*** checkpoint 302')
				namelistOsh = ObjectStateHolder('mqnamelist')
				#qMgrName = mqQMGROsh.getAttribute('data_name')
				#logger.debug('*** checkpoint 302_1')
				#if mqQMGROsh != None:
				try:
					qMgrName = mqQMGROsh.getAttribute(str_name).getValue()
					#logger.debug('*** qMgrName = ', qMgrName)
					#logger.debug('*** qMgrName.getValue() = ', qMgrName.getValue())
					#logger.debug('*** setting queue name')
					namelistOsh.setAttribute(str_name, queueclusnl + '@' + qMgrName)
					namelistOsh.setContainer(mqQMGROsh)
					vector.add(namelistOsh)
					vector.add(modeling.createLinkOSH('member', namelistOsh, mqQueueOsh))
					#logger.debug('*** checkpoint 5')
				except:
					logger.debug('*** unable to get name of mqMGR')
			################################
			## Check if this Queue is associated with a process
			##############################
			if isNotNull(queueprocess):
				#logger.debug('*** checkpoint 303')
				processOsh = ObjectStateHolder('mqprocess')
				processOsh.setAttribute(str_name, queueprocess)
				processOsh.setContainer(mqSubsystemOSH)
				vector.add(processOsh)
				vector.add(modeling.createLinkOSH('use', processOsh, mqQueueOsh))
				#logger.debug('*** checkpoint 6')
			################################
			## If this is an ALIAS Queue, link it with the Queue for which it is an alias
			################################
			if queuetype == 'QALIAS':
				#logger.debug('*** inside if QALIAS')
				if isNotNull(queuetarget):
					#logger.debug('*** inside if qalias 2')
					if qOshDict.keys() != None:
						if (queuetarget+qMgrName) in qOshDict.keys():
							#logger.debug('*** qOshDict.keys() = ', qOshDict.keys())
							#logger.debug('*** calling modeling to create linkOSH')
							vector.add(modeling.createLinkOSH('realization', mqQueueOsh , qOshDict[queuetarget+qMgrName]))
							#logger.debug('*** checkpoint 7')
						else:
							targetQOSH = ObjectStateHolder('mqqueue')
							targetQOSH.setStringAttribute(str_name, queuetarget.strip())
							## Not setting Queue Type because it is unknown
							targetQOSH.setContainer(mqQMGROsh)
							vector.add(targetQOSH)
							vector.add(modeling.createLinkOSH('realization', mqQueueOsh, targetQOSH))
							qOshDict[queuetarget+qMgrName] = targetQOSH
							#logger.debug('*** checkpoint 8')
					else:
						pass
						#logger.debug('*** keys() was null')
			################################
			## If this is a REMOTE Queue, link it with its TRANSMIT Q
			################################
			if queuetype == 'QREMOTE':
				#logger.debug ('In Remote Queue create     ', xmitqueue+qMgrName)
				if isNull(xmitqueue):
					## Use the  default transmit Queue if one is defined
					try:
						xmitqueue = mqQMGROsh.getAttribute('mqqueuemanager_defaultxmitqname').getStringValue()
						#logger.debug('*** checkpoint 9')
					except:
						xmitqueue = ''
						#logger.debug ('xmitqueue set to null')
				if isNotNull(xmitqueue):
					#logger.debug('*** checkpoint 10')
					xmitdictkey = xmitqueue+qMgrName.strip()
					if (xmitdictkey) in qOshDict.keys():
						vector.add(modeling.createLinkOSH('use', mqQueueOsh, qOshDict[xmitqueue+qMgrName]))
					else:
						#logger.debug('*** checkpoint 11')
						#logger.debug ('Creating XMIT QUEUE ===> ', xmitqueue,  qMgrName)
						xmitQOSH = ObjectStateHolder(QOSHTYPEMAP['XMITQ'])
						xmitQOSH.setStringAttribute(str_name, xmitqueue.strip())
						xmitQOSH.setStringAttribute('queue_type', QTYPEMAP['XMITQ'])
						xmitQOSH.setContainer(mqQMGROsh)
						vector.add(xmitQOSH)
						vector.add(modeling.createLinkOSH('use', mqQueueOsh, xmitQOSH))
						qOshDict[xmitdictkey] = xmitQOSH

			################################
			## If TRANSMIT Q, Remote Q and Remote QMGR are known, add a link between them
			################################
			#logger.debug('*** checkpoint 12')
			if isNotNull(xmitqueue) and isNotNull(rqmname) and isNotNull (rname) and DISCOVER_REMOTE_HOSTS.strip().lower() in ['true', 'yes', 'y', '1']:
				#logger.debug ('Remote and Remote MGR not Null ====>', xmitqueue,rname,rqmname)
				#logger.debug('*** checkpoint 13')
				## Try to get remote server name/IP and port from the sender channel associated with this Qs' transmit Q
				remoteHost = None
				remotePort = None
				remoteHostOSH = None
				remoteQManagerOSH = None
				ipserverOSH = None
				remoteMqOSH = None
				xmitcmdqueue = xmitqueue.replace('.','..')
				remote_display_command = "DISPLAY CHANNEL (*) WHERE (XMITQ EQ " + xmitcmdqueue + ") TYPE(SDR) CONNAME"
				#logger.debug('*** checkpoint 14')
				output = ls.evSysInfoCmd(remote_display_command, '50', subsystem)
				#logger.debug('*** checkpoint 15')
				if output.isSuccess() and len(output.cmdResponseList) > 0:
					for line in output.cmdResponseList:
						#logger.debug ('Remote queue response ====>', line)
						#logger.debug('*** checkpoint 16')
						m = re.search('CONNAME\((\S+)', line)
						if (m):
							#logger.debug ('Found conname====> ',m.group(1).replace(')','',1))
							conname = m.group(1).replace(')','',1)
							m1 = re.search('(\d+.\d+.\d+.\d+)\((\d+)',conname)
							if (m1):
								#logger.debug ('Found remote host / remote port from conname====> ',m1.group(1),' ',m1.group(2))
								remoteHost = m1.group(1)
								remotePort = m1.group(2)
						continue
					if isNotNull(remoteHost):
						#logger.debug('*** checkpoint 17')
						remoteHostOSH = modeling.createHostOSH(remoteHost)
						ipserverOSH = modeling.createServiceAddressOsh(remoteHostOSH, remoteHost, int(remotePort), modeling.SERVICEADDRESS_TYPE_TCP, 'ibmmqseries')
						vector.add(ipserverOSH)
						vector.add(remoteHostOSH)
						## Create OSH for the remote queue manager
					if isNotNull(remoteHostOSH):
						#   ## Build Websphere MQ OSH
						#logger.debug('*** checkpoint 18')
						remoteMqOSH = ObjectStateHolder('webspheremq')
						remoteWSname = concatenate('IBM WebSphere MQ ',rqmname)
						remoteMqOSH.setAttribute(str_name, remoteWSname)
						remoteMqOSH.setAttribute('application_ip', remoteHost)
						remoteMqOSH.setAttribute('application_port', int(remotePort))
						remoteMqOSH.setAttribute('application_timeout', 50000)
						remoteMqOSH.setAttribute('vendor', 'ibm_corp')
						remoteMqOSH.setAttribute('application_category', 'Messaging')
						modeling.setApplicationProductName(remoteMqOSH,'IBM WebSphere MQ')
						remoteMqOSH.setContainer(remoteHostOSH)
						vector.add(remoteMqOSH)
						## Build Queue Manager CI on remote MQ
						remoteQManagerOSH = ObjectStateHolder('mqqueuemanager')
						remoteQManagerOSH.setAttribute(str_name, rqmname)
						remoteQManagerOSH.setContainer(remoteMqOSH)
						vector.add(remoteQManagerOSH)
					if isNotNull(ipserverOSH) and isNotNull(remoteMqOSH):
						#logger.debug('*** checkpoint 19')
						vector.add(modeling.createLinkOSH('use', remoteMqOSH, ipserverOSH))
						## If we have a remote Q name, create a Q without Q type
					if isNotNull(remoteQManagerOSH) and isNotNull(rname):
						#logger.debug('*** checkpoint 20')
						remoteQueueOSH = ObjectStateHolder('mqqueue')
						remoteQueueOSH.setAttribute(str_name, rname)
						remoteQueueOSH.setContainer(remoteQManagerOSH)
						vector.add(remoteQueueOSH)
						vector.add(modeling.createLinkOSH('realization', mqQueueOsh , remoteQueueOSH))
						## This is an alias Q manager because the remote Q name is blank
					elif isNotNull(remoteQManagerOSH):
						#logger.debug('*** checkpoint 21')
						mqQueueOsh.setAttribute('queue_type', QTYPEMAP['QREMOTE'])
						vector.add(modeling.createLinkOSH('realization', mqQueueOsh, remoteQManagerOSH))


	return vector , qOshDict
##############################################################
##  Create the MQ Channel OSH                                  ##
###############################################################
def createChannelOSH(ls, lparOsh, channelList,  mqSubsystemOSH , mqQMGROsh, qOshDict):


	vector = ObjectStateHolderVector()
	# Handle the name attribute depending on the version of UCMDB
	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose
	# Process all the entries in the Queue List and build the OSH
	qMgrName = mqQMGROsh.getAttribute(str_name).getValue()
	if isNotNull(channelList) and len(channelList) > 0:
		for (key, val) in channelList.items():
			channel = key
			chldesc  = val.chldesc
			chltype = val.chltype
			trptype = val.trptype
			cluster  = val.cluster
			clusnl = val.clusnl
			conname = val.conname
			host = val.host
			port = val.port
			xmitqueue = val.xmitq

			#logger.debug ('Channel OSH ===> ',channel, ' ',chldesc, ' ',chltype,' ',trptype,' ',cluster, ' ',clusnl, ' ', conname, ' ', xmitqueue)

			## Make OSH
			channelOSH = None
			if chltype in ['CLNTCONN', 'CLUSRCVR', 'RCVR', 'RQSTR']:
				channelOSH = ObjectStateHolder('mqreceiverchannel')
				channelOSH.setStringAttribute('mqreceiverchannel_channeltype', RECEIVERCHLTYPEMAP[chltype])
			else:
				channelOSH = ObjectStateHolder('mqsenderchannel')
				channelOSH.setStringAttribute('mqsenderchannel_channeltype', SENDERCHLTYPEMAP[chltype])

			channelOSH.setStringAttribute(str_name, channel)
			#channelOSH.setStringAttribute(str_discovered_product_name, channel)
			channelOSH.setStringAttribute('data_description', chldesc)
			channelOSH.setStringAttribute('mqchannel_transporttype', trptype)
			channelOSH.setStringAttribute('mqchannel_conname', conname)
			channelOSH.setContainer(mqQMGROsh)
			vector.add(channelOSH)

			################################
			## Handle transmit Qs if any
			################################
			if isNull(xmitqueue):
				## Use the  default transmit Queue
				try:
					xmitqueue = mqQMGROsh.getAttribute('mqqueuemanager_defaultxmitqname').getStringValue()
				except:
					xmitqueue = ''
			else:
				if (xmitqueue+qMgrName) in qOshDict.keys():
					vector.add(modeling.createLinkOSH('use', channelOSH, qOshDict[xmitqueue+qMgrName]))

				else:
					xmitQOSH = ObjectStateHolder(QOSHTYPEMAP['XMITQ'])
					xmitQOSH.setStringAttribute(str_name, xmitqueue.strip())
					xmitQOSH.setStringAttribute('queue_type', QTYPEMAP['XMITQ'])
					xmitQOSH.setContainer(mqQMGROsh)
					vector.add(xmitQOSH)
					vector.add(modeling.createLinkOSH('use', channelOSH, xmitQOSH))
					qOshDict[xmitqueue+qMgrName] = xmitQOSH
			################################
			## Handle remote connections if any
			################################
			if isNotNull(conname):
				if host is not None:
					channelOSH.setAttribute('mqchannel_connip', host)
					channelOSH.setAttribute('mqchannel_connport', port)
					vector.add(channelOSH)
			################################
			## Handle clusters if any
			################################
			if isNotNull(cluster):
				clusterOSH = ObjectStateHolder('mqcluster')
				clusterOSH.setAttribute(str_name, cluster)
				vector.add(clusterOSH)
				vector.add(modeling.createLinkOSH('member', clusterOSH, channelOSH))
				vector.add(modeling.createLinkOSH('member', clusterOSH, mqQMGROsh))
			################################
			## Handle namelists, if any
			if isNotNull(clusnl):
				namelistOSH = ObjectStateHolder('mqnamelist')
				namelistOSH.setAttribute(str_name, clusnl + '@' + qMgrName)
				namelistOSH.setContainer(mqQMGROsh)
				vector.add(namelistOSH)
				vector.add(modeling.createLinkOSH('member', namelistOSH, channelOSH))

	return  vector
##############################################################
##  Create the MQ Process OSH                                  ##
###############################################################
def createProcessOSH(ls, lparOsh, processList,  mqSubsystemOSH , mqQMGROsh, qOshDict):


	vector = ObjectStateHolderVector()
	# Handle the name attribute depending on the version of UCMDB
	str_name = 'name'
	str_discovered_product_name = 'discovered_product_name'
	if UCMDB_VERSION < 9:
		str_name = 'data_name'
		str_discovered_product_name = 'data_name' # duplicated on purpose
	# Process all the entries in the Queue List and build the OSH
	#logger.debug('*** len of processList = ', len(processList))
	plcount = 0
	if isNotNull(processList) and len(processList) > 0:
		for (key, val) in processList.items():
			plcount += 1
			#logger.debug('*** plcount = ', plcount)
			if val == None or key == None:
				#logger.debug('*** key = ', key)
				#logger.debug('*** val = ', val)
				continue
			process = key
			#logger.debug('*** val = ', val)
			try:
				procdescr = val.procdescr
				#logger.debug('*** val.procdescr = ', val.procdescr)
				applicid = val.applicid
				#logger.debug('val.applicid = ', val.applicid)
				userdata = val.userdata
				#logger.debug('val.userdata = ', val.userdata)
				appltype = val.appltype
				#logger.debug('val.appltype = ', val.appltype)
				procdisp = val.procdisp
				#logger.debug('val.procdisp = ', val.procdisp)
				#logger.debug ('Process OSH ===> ',channel, ' ',chldesc, ' ',chltype,' ',trptype,' ',cluster, ' ',clusnl, ' ', conname, ' ', xmitqueue)
			except:
				logger.debug('*** error getting data from val')

			## Make OSH
			processOSH = None
			#logger.debug('*** creating mqprocess osh')
			processOSH = ObjectStateHolder('mqprocess')
			processOSH.setStringAttribute(str_name, process)
			#logger.debug('*** mqprocess name = ', process)
			#processOSH.setStringAttribute(str_discovered_product_name, process)
			processOSH.setStringAttribute('data_description', procdescr)
			processOSH.setStringAttribute('mqprocess_appid', applicid)
			processOSH.setStringAttribute('mqprocess_userdata', userdata)
			processOSH.setStringAttribute('mqprocess_apptype', appltype)
			processOSH.setStringAttribute('mqprocess_disposition', procdisp)
			#logger.debug('*** setting container')
			processOSH.setContainer(mqSubsystemOSH)
			#logger.debug('*** adding to vector')
			vector.add(processOSH)
	return vector
###############################################
##  Get the MQ System Parameter information  ##
###############################################
def get_systemParamInfo(ls, lparOsh , subsystem, mqSubsystemOSH ):
	sysParmNumeric = {}
	sysParmString = {}
	xcfmember = None
	vector = None
	#subsystem = cmd_prefix.replace('%','')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_SYSTEM, '50', subsystem)
	#logger.debug('*** checkpoint 102')
	#output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_SYSTEM % cmd_prefix)
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:

		# Skip Headers and Footers and sub-headers
			if (re.search('SET\s*value', line) or
				re.search('-------', line) or
				re.search('CSQJ322I', line) or
				re.search('CSQN205I', line) or
				re.search('CSQ9022I', line) or
				re.search('End\s*of\s*SYSTEM\s*report', line) or
				re.search('OTMACON', line) or
				re.search('QSGDATA', line)):
				continue
			## Special case for the TRACSTR value, it can be an integer or a string depending on the configuration
			## we will treat it as a string
			#logger.debug ('Line ====> ',line)
			m = re.search('^\s*(\S+)\s+(\S+)', line)
			if (m):
				#logger.debug (line)
				parameter = m.group(1)
				value = m.group(2)
				if parameter == 'TRACSTR':
					sysParmString[parameter] = value
					continue

			## Look for numeric values

			m = re.search('^\s*(\S+)\s+(\d+)', line)
			if (m):
				parameter = m.group(1)
				value = m.group(2)
				sysParmNumeric[parameter] = value

			## Look for string values and verify it is not already in the numeric Dictionary

			m = re.search('^\s*(\S+)\s+(\S+)', line)
			if (m) and not (sysParmNumeric.has_key(m.group(1))):
				parameter = m.group(1)
				value = m.group(2)
				sysParmString[parameter] = value
				if parameter == 'MEMBER':
					xcfmember = value


		vector = createmqSysParamOSH(ls, lparOsh, sysParmNumeric, sysParmString, mqSubsystemOSH, xcfmember )


	return vector
#############################################################
##  Find the MQ Subsystem and retrieve the prefix         ##
#############################################################

def get_subsystemOutput(ls):
	mqSubsystems = []  # [name, initrtn, initparm, cmd_prefix]
	output = ls.evGetSubSysCmd()
	#logger.debug('*** checkpoint 103')
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		mqInitRoutineRegex = r"CSQ\d"
		for line in output.cmdResponseList:
			#logger.debug (line)
			if len(line) == 3 and isNotNull(line[1]):
				m = re.match(mqInitRoutineRegex, line[1], re.IGNORECASE)
				if isNotNull(m) and isNotNull(line[2]):
					initParm = string.replace(line[2], "'", "")
					initParmSplit = string.split(initParm, ",")
					cmd_prefix = ''
					if isNotNull(initParmSplit) and len(initParmSplit) > 1 and isNotNull(initParmSplit[1]):
						cmd_prefix = initParmSplit[1]
					mqSubsystems.append([line[0], line[1], initParm, cmd_prefix])
	#logger.debug (mqSubsystems)
	return mqSubsystems

##############################################################
##  Search all the Proc libs for the MQ Subsystems and then ##
## get the MQ System Paramter Information                   ##
##############################################################

def getMQSubsytems(ls, lparOsh):

	mqSubsystemOSH = None
	cmd_prefix = None
	#
	#  look for MQ Subsystems
	#
	mqSubsystems = get_subsystemOutput(ls)
	for mq in mqSubsystems:
		cmd_prefix = mq[3]
		mqSubsystemOSH = createmqSubsystemOsh(lparOsh, mq)
	return mqSubsystemOSH, cmd_prefix

###############################################
##  Get the MQ Queue Manager Information     ##
###############################################

def get_QueueManagerInfo(ls, lparOsh , subsystem, mqSubsystemOSH ):

	sysParmDict = {}
	vector = None
	mqQMGROsh = None
	qOshDict = {}
	#subsystem = cmd_prefix.replace('%','')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_QMGR, '50', subsystem)
	#logger.debug('*** checkpoint 104')
	#output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_QMGR % cmd_prefix)
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:

			# Skip Headers and Footers


			if  (re.search('CSQN205I', line) or
				re.search('END QMGR DETAILS', line) or
				re.search('CSQ9022I', line)):
				continue

			line = line.replace(') ',')|')
			splitline = line.split('|')

			for entries in splitline:

			## Parse out the values and build a Dictionary
				m = re.search('([A-Z]+)\((.+)', entries)
				if (m):
					parameter = m.group(1)
					value = m.group(2).replace(')','')
					#logger.debug ('Parameter ====> ',  parameter, ' ', value)
					if value != '':
						sysParmDict[parameter] = value


		vector, mqQMGROsh, qOshDict = createQMGROSH(ls, lparOsh,  sysParmDict, mqSubsystemOSH )
	return vector, mqQMGROsh, qOshDict

###############################################
##  Get the MQ Channel Initiator Information ##
###############################################

def get_ChannelInitiatorInfo(ls, lparOsh , subsystem, mqSubsystemOSH ):

	ParmString = {}
	ParmInt = {}
	vector = None
	#subsystem = cmd_prefix.replace('%','')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_CHINIT, '50', subsystem)
	#logger.debug('*** checkpoint 105')
	#output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_CHINIT % cmd_prefix)
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:


			if  (re.search('CSQM131I', line)):
				#logger.debug ('Cannot Discover Channel Initiator - CHANNEL INITIATOR NOT ACTIVE')
				break

			# Skip Headers and Footers

			if  (re.search('CSQN205I', line) or
				re.search('CSQ9022I', line)):
				continue
			#logger.debug ('CHINIT LINE====> ',line)


			# Pull out the port and the address for the listener
			m = re.search('for\s+port\s+(\d+)\s+address\s(\S+)', line)
			if (m):
				ParmInt['LPORT'] = m.group(1)
				ParmString['LADDR'] = m.group(2)


			# Pull out the  maximum channels
			m = re.search('channels\s+current,\s+maximum\s+(\d+)', line)
			if (m):
				ParmInt['MAXCHAN'] = m.group(1)

			# Pull out the  maximum active channels
			m = re.search('channels\s+active,\s+maximum\s+(\d+)', line)
			if (m):
				ParmInt['MAXACTCHAN'] = m.group(1)


			# Pull out the  subtasks that are started
			m = re.search('SSL\s+server\s+subtasks\s+started,\s+(\d+)', line)
			if (m):
				ParmInt['SUBSTARTED'] = m.group(1)


			# Pull out the  max TCP Channels and max LU Channels
			m = re.search('Maximum\s+channels\s+\-\s+TCP/IP\s+(\d+),\s+LU\s+\S+\s+(\d+)', line)
			if (m):
				ParmInt['MAXTCP'] = m.group(1)
				ParmInt['MAXLU'] = m.group(2)


			# Pull out the TCP System Name
			m = re.search('TCP/IP\s+system\s+name\s+is\s+(\S+)', line)
			if (m):
				ParmString['TCPSYSNAME'] = m.group(1)


			# Pull out the TCP Listener Name and the TCP Listener Status
			m = re.search('TCP/IP\s+[Ll]istener\s+INDISP\s*=\s*(\S+)(\s+\S+.*)', line)
			if (m):
				ParmString['LNAME'] = m.group(1)
				ParmString['LSTATUS'] = m.group(2).replace(',','')


			# Pull out the   LU System Name and the LU Listener Status
			m = re.search('LU\s+\S+\s+[Ll]istener\s+INDISP\s*=\s*(\S+)(\s+\S+.*)', line)
			if (m):
				ParmString['LUSYSNAME'] = m.group(1)
				ParmString['LULSTATUS'] = m.group(2)


		#logger.debug ('CHINIT PARMString ===> ', ParmString)
		#logger.debug ('CHINIT ParmInt===> ', ParmInt)
		vector = createCHINITOSH(ls, lparOsh,  ParmString, ParmInt, mqSubsystemOSH )



	return vector
###############################################
##  Get the MQ Queue Information             ##
###############################################

def get_QueueInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict):

	queueList = {}
	qname = None
	qdesc = None
	qtype = None
	qprocess = None
	qusage = None
	qcluster = None
	qclusnl = None
	qtarget = None
	xmitq = None
	rname = None
	rqmname = None
	vector = None
	#logger.debug('*** in get_queueInfo: executing get queue info')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_QUEUE, '50', subsystem)
	#logger.debug('*** checkpoint 106')
	#logger.debug('*** command ended')
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:
			# Skip Headers and Footers

			if  (re.search('CSQN205I', line) or
				re.search('CSQ9022I', line)):
				continue
			#logger.debug ('QUEUE LINE====> ',line)

			m = re.search('QUEUE\((\S+)', line)
			if (m):
				qname =  m.group(1).replace(')','')
				#logger.debug('*** qname = ', qname)

			m = re.search('TYPE\((\S+)', line)
			if (m):
				qtype = m.group(1).replace(')','')
				#logger.debug('*** qtype = ', qtype)

			m = re.search('DESCR\(([a-zA-Z-\s\\0-9]+)', line)
			if (m):
				qdesc = m.group(1).replace(')','')

			m = re.search('PROCESS\((\S+)', line)
			if (m):
				qprocess = m.group(1).replace(')','')
				#logger.debug('*** qprocess = ', qprocess)

			m = re.search('USAGE\((\S+)', line)
			if (m):
				qusage = m.group(1).replace(')','')
				#logger.debug('*** qusuage = ', qusage)

			m = re.search('CLUSTER\((\S+)', line)
			if (m):
				qcluster = m.group(1).replace(')','')
				#logger.debug('*** qcluster = ', qcluster)

			m = re.search('TARGET\((\S+)', line)
			if (m):
				qtarget = m.group(1).replace(')','')
				#logger.debug('*** qtarget = ', qtarget)

			m = re.search('CLUSNL\((\S+)', line)
			if (m):
				qclusnl = m.group(1).replace(')','')
				#logger.debug('*** qclusnl = ', qclusnl)

			m = re.search('RNAME\((\S+)', line)
			if (m):
				rname = m.group(1).replace(')','')
				#logger.debug('*** rname = ', rname)

			m = re.search('RQMNAME\((\S+)', line)
			if (m):
				rqmname = m.group(1).replace(')','')
				#logger.debug('*** rqmname = ', rqmname)

			m = re.search('XMITQ\((\S+)', line)
			if (m):
				xmitq = m.group(1).replace(')','')
				#logger.debug('*** xmitq = ', xmitq)

			#logger.debug ('Found ====> ',qname,' ',qdesc,' ',qtype,' ',qprocess,' ',qusage,' ',qcluster,' ',qclusnl,' ',qtarget,' ',xmitq,' ',rname,' ',rqmname)
			queueList[qname] = MQQueue(qname, qtype, qdesc, qprocess, qusage, qcluster, qclusnl, qtarget,xmitq,rname,rqmname)
			qname = None
			qdesc = None
			qtype = None
			qprocess = None
			qusage = None
			qcluster = None
			qclusnl = None
			qtarget = None
			xmitq = None
			rname = None
			rqmname = None
			continue
		vector, qOshDict = createQUEUEOSH(ls, subsystem, lparOsh, queueList,  mqSubsystemOSH , mqQMGROsh, qOshDict)
	return vector, qOshDict
###############################################
##  Get the MQ Channel Information           ##
###############################################

def get_ChannelInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict  ):

	channelList = {}
	channel = None
	chldesc = None
	chltype = None
	trptype = None
	cluster = None
	clusnl = None
	conname = None
	xmitq = None
	host = None
	port = None
	vector = None

	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_CHANNEL, '50', subsystem)
	#logger.debug('*** checkpoint 107')
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		for line in output.cmdResponseList:

			# Skip Headers and Footers

			if  (re.search('CSQN205I', line) or
				re.search('CSQ9022I', line)):
				continue
			#logger.debug ('CHANNEL LINE====> ',line)

			m = re.search('CHANNEL\((\S+)', line)
			if (m):
				channel =  m.group(1).replace(')','')

			m = re.search('CHLTYPE\((\S+)', line)
			if (m):
				chltype = m.group(1).replace(')','')

			m = re.search('DESCR\(([a-zA-Z-\s\\0-9]+)', line)
			if (m):
				chldesc = m.group(1).replace(')','')

			m = re.search('TRPTYPE\((\S+)', line)
			if (m):
				trptype = m.group(1).replace(')','')


			m = re.search('CLUSTER\((\S+)', line)
			if (m):
				cluster = m.group(1).replace(')','')


			m = re.search('CLUSNL\((\S+)', line)
			if (m):
				clusnl = m.group(1).replace(')','')

			m = re.search('CONNAME\((\S+)', line)
			if (m):
				conname = m.group(1).replace(')','',1)
				m1 = re.search('(\d+.\d+.\d+.\d+)\((\d+)',conname)
				if (m1):
					host = m1.group(1)
					port = m1.group(2)

			m = re.search('XMITQ\((\S+)', line)
			if (m):
				xmitq= m.group(1).replace(')','')


			#logger.debug ('Found ====> ',channel,' ',chldesc,' ',chltype,' ',trptype,' ',cluster,' ',clusnl,' ',conname,' ',xmitq,' ',host,' ',port)
			channelList[channel] = MQChannel(channel,chldesc,chltype,trptype,cluster,clusnl,conname,xmitq,host,port)
			channel = None
			chldesc = None
			chltype = None
			trptype = None
			cluster = None
			clusnl = None
			conname = None
			host = None
			port = None
			xmitq = None
			continue
		vector = createChannelOSH(ls, lparOsh, channelList,  mqSubsystemOSH , mqQMGROsh, qOshDict)

	return vector
###############################################
##  Get the MQ Process Information           ##
###############################################

def get_ProcessInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict  ):

	processList = {}
	process = None
	procdescr = None
	applicid = None
	userdata = None
	appltype = None
	procdisp = None
	vector = None

	#logger.debug('*** executing command _CMD_PREFIX_DISPLAY_PROCESS')
	output = ls.evSysInfoCmd(_CMD_PREFIX_DISPLAY_PROCESS, '50', subsystem)
	#logger.debug('*** checkpoint 108')
	#logger.debug('*** cmd execution ended')
	#output = ls.evMvsCmd(_CMD_PREFIX_DISPLAY_PROCESS % cmd_prefix)
	if output.isSuccess() and len(output.cmdResponseList) > 0:
		#logger.debug('*** len of output: ', len(output.cmdResponseList))
		count = 0
		for line in output.cmdResponseList:

			# Skip Headers and Footers
			if  (re.search('CSQN205I', line) or
				re.search('CSQ9022I', line)):
				continue

			#logger.debug('*** processing line number:', count)
			count += 1
			#logger.debug ('Process LINE====> ',line)

			m = re.search('PROCESS\((\S+)', line)
			if (m):

				process =  m.group(1).replace(')','')

			m = re.search('QSGDISP\((\S+)', line)
			if (m):

				procdisp = m.group(1).replace(')','')

			m = re.search('DESCR\((\S+)', line)
			if (m):

				procdescr = m.group(1).replace(')','')

			m = re.search('APPLTYPE\((\S+)', line)
			if (m):

				appltype = m.group(1).replace(')','')

			m = re.search('APPLICID\((\S+)', line)
			if (m):

				applicid = m.group(1).replace(')','')

			m = re.search('USERDATA\((\S+)', line)
			if (m):

				userdata = m.group(1).replace(')','')

			#logger.debug('*** calling MQProcess with params: ', process,procdescr,applicid,userdata,appltype,procdisp)
			processList[process] = MQProcess(process,procdescr,applicid,userdata,appltype,procdisp)
			#logger.debug('*** pass this  point?')
			process = None
			procdescr = None
			applicid = None
			userdata = None
			appltype = None
			procdisp = None
			continue
		vector = createProcessOSH(ls, lparOsh, processList,  mqSubsystemOSH , mqQMGROsh, qOshDict)

	return vector
###############################################
##  Get all the MQ Subsystems               ##
###############################################
def discover_MQ (ls, lparOsh):

	OSHVResult = ObjectStateHolderVector()
	mqSubsystemOSH = None
	subsystem = None
	mqup = 0
	mqSubsystems = []
	#
	#  look for MQ Subsystems
	#
	#logger.debug('*** in discover_MQ')
	mqSubsystems = get_subsystemOutput(ls)
	count = 0
	for mq in mqSubsystems:
		count = count + 1
		#logger.debug('*** count = ', count)
		subsystem = mq[0]
		#logger.debug('*** creating mqsubsystemOSH')
		mqSubsystemOSH = createmqSubsystemOsh(lparOsh, mq)
		OSHVResult.add(mqSubsystemOSH)
		# Test to see if MQ is up before we continue
		mqup = testMQup (ls,  subsystem)
		if mqup:
			#logger.debug('*** get_systemParamInfo')
			OSHVResult.addAll(get_systemParamInfo(ls, lparOsh , subsystem, mqSubsystemOSH ))
			#logger.debug('*** get_QueueManagerInfo')
			qmgrvector, mqQMGROsh , qOshDict = get_QueueManagerInfo(ls, lparOsh , subsystem, mqSubsystemOSH)
			OSHVResult.addAll(qmgrvector)
			OSHVResult.addAll(get_ChannelInitiatorInfo(ls, lparOsh ,  subsystem, mqSubsystemOSH ))
			#logger.debug('*** get_QueueInfo')
			queuevector, qOshDict =  get_QueueInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict )
			OSHVResult.addAll(queuevector)
			#logger.debug('*** get_ChannelInfo')
			OSHVResult.addAll(get_ChannelInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict ))
			#logger.debug('*** get_ProcessInfo')
			OSHVResult.addAll(get_ProcessInfo(ls, lparOsh , subsystem, mqSubsystemOSH , mqQMGROsh, qOshDict ))
			#logger.debug('*** finished get_ProcessInfo')
	return OSHVResult
############################
#    MAIN
############################
def DiscoveryMain(Framework):
	global DISCOVER_REMOTE_HOSTS
	OSHVResult = ObjectStateHolderVector()
	logger.info ("Starting MQ Discovery")
	DISCOVER_REMOTE_HOSTS = Framework.getParameter('discover_remote_hosts') or 'true'

	# create LPAR node from the ID passed in
	hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
	lparOsh = None
	mqSubsystemOSH = None
	qmgrvector = None
	mqQMGROsh = None
	qOshDict = None

	if eview_lib.isNotNull(hostId):
		lparOsh = modeling.createOshByCmdbIdString('host_node', hostId)

	ls = eview_lib.EvShell(Framework)
	try:
		OSHVResult = discover_MQ (ls, lparOsh)
		ls.closeClient()
	except:
		altErr = errorobject.createError(errorcodes.INTERNAL_ERROR ,None , 'Error communicating with Mainframe')
		logger.reportErrorObject(altErr)
	logger.info ("Finished MQ Discovery")
	return OSHVResult
