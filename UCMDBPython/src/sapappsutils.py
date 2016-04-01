#coding=utf-8
import sys

import logger

import saputils

from java.util import ArrayList
from java.util import HashMap
from java.util import Properties
from java.util import Date

from java.lang import Boolean
from java.lang import String

from java.text import SimpleDateFormat

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# SapAppsUtils
# SAPApps Utility Class
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
class SapAppsUtils(saputils.SapUtils):
	def __init__(self, client, loadOnInit = 1, loadType = saputils.SapUtils.ALL_TYPES_LOAD):
		saputils.SapUtils.__init__(self, client, loadOnInit, loadType)
		self.__client = client
		
	def getApplicationHierarchy(self):
		appsProps = []
		params = HashMap()
		params.put('OBJECT_TYPE', 'FUGR')
		params.put('REFRESH', 'X')
#		function = self.__client.getFunction('RS_COMPONENT_VIEW')
#		function.getImportParameterList().setValue("FUGR", "OBJECT_TYPE");
#		function.getImportParameterList().setValue("X", "REFRESH");
		
		fields = ArrayList()
		fields.add('ID')
		fields.add('TYPE')
		fields.add('NAME')
		fields.add('PARENT')
		fields.add('TEXT')
		
		appsRS = self.__client.executeFunction('RS_COMPONENT_VIEW', params, 'NODETAB', fields)
		
		while appsRS.next():
			prop = Properties()
			prop.setProperty('id', appsRS.getString("ID"))
			prop.setProperty('type', appsRS.getString("TYPE"))
			prop.setProperty('data_name', appsRS.getString("NAME"))
			prop.setProperty('parent', appsRS.getString("PARENT"))
			prop.setProperty('description', appsRS.getString("TEXT"))
			appsProps.append(prop)

		return appsProps;

	def getTransactionChange(self):
		return self.__client.getTransactionChange()
		
	def getTransactions(self):
		transactions = []
		whereClauses = ArrayList()
		whereClauses.add("OBJECT = 'TRAN'")
		result = self.executeQuery('TADIR', whereClauses, 'OBJECT,OBJ_NAME,DEVCLASS')#@@CMD_PERMISION sap protocol execution
		while result.next():
			type = result.getString("OBJECT")
			if type == 'TRAN':
				transid = result.getString("OBJ_NAME");
				devClass = result.getString("DEVCLASS");
				prop = Properties()
				prop.setProperty('data_name',transid)
				prop.setProperty('devclass',devClass)
				transactions.append(prop)
		
		return transactions
		
	def getActiveTransactions(self):
		activeTransactions = []
		whereClauses = ArrayList()
		whereClauses.add("FUNCNAME IN ('SAPWL_TCODE_AGGREGATION','SAPWL_TCODE_AGGREGATION_COPY')");
		result = self.executeQuery("TFDIR", whereClauses, "FUNCNAME")#@@CMD_PERMISION sap protocol execution
		
		functionName = None
		if result.next():
			functionName = result.getString("FUNCNAME")

		if functionName == None:
			logger.warn('getActiveTransactions: active transaction function is not found')
			return activeTransactions
		
		day = self.__client.getProperty('from_date')
		if day == None:
			today = Date()
			sfDate = SimpleDateFormat("yyyyMMdd")
			day = sfDate.format(today)
		elif day.find('/') != -1:
			try:
				sfDate = SimpleDateFormat("MM/dd/yyyy")
				parsedDate = sfDate.parse(day)
				sfDate = SimpleDateFormat("yyyyMMdd")
				day = sfDate.format(parsedDate)
			except:
				logger.reportWarning('Failed to parse date ', day)
				
		logger.debug('Parsed start date:', day)
			

		logger.debug('Active transactions from data:', day)
		mapTransactionToUsers = None
		getUsers = Boolean.parseBoolean(self.__client.getProperty("get_users"))
		if getUsers:
			mapTransactionToUsers = HashMap()
			
			funcParams = HashMap()
			funcParams.put('READ_START_DATE', day)
			funcParams.put('READ_START_TIME', '000000')
			funcParams.put('READ_END_DATE', day)
			funcParams.put('READ_END_TIME', '235959')
			funcParams.put('READ_ONLY_MAINRECORDS', 'X')
			
			logger.debug('executing func:SAPWL_STATREC_FROM_REMOTE_SYS(', str(funcParams),')')
			
			fields = ArrayList()
			fields.add('TCODE')
			fields.add('ACCOUNT')
			usersResult = self.__client.executeFunction('SAPWL_STATREC_FROM_REMOTE_SYS', funcParams, 'NORMAL_RECORDS', fields)
			while usersResult.next():
				transaction = usersResult.getString('TCODE')
				if len(transaction) > 0:
					user = usersResult.getString("ACCOUNT");
					users = mapTransactionToUsers.get(transaction)
					if users == None:
						users = HashMap()
						mapTransactionToUsers.put(transaction,users)
					users.put(user,users);

		self.getSites()
		site = self.getSites().getCell(0,0)
		servers = self.getServers(site)
		numServers = servers.getRowCount()
		transactionToStats = HashMap()
		for j in range(numServers):
			try:
				instance = servers.getCell(j,0);
				logger.debug('getActiveTransactions:executing function[' + functionName + '] for instance [' + instance + ']')
				if functionName == 'SAPWL_TCODE_AGGREGATION_COPY':
					records = self.callSapwlTcodeAggregationCopy(instance,day)
	
					while records.next():
						transaction = (str(records.getString(0))).strip()
						mapUsers = None
						if mapTransactionToUsers != None:
							mapUsers = mapTransactionToUsers.get(transaction)
						if (transaction != None) and (len(transaction) > 0):
							stats = transactionToStats.get(transaction)
							if stats == None:
								stats = TransactionStatistics(transaction)
								transactionToStats.put(transaction,stats)
	
							if mapUsers != None:
								stats.users = ArrayList(mapUsers.keySet())
							if records.next():
								stats.steps = stats.steps + int(float(records.getString(0)))
							if records.next():
								stats.responseTime = stats.responseTime + int(float(records.getString(0)))
							if records.next():
								stats.cpuTime = stats.cpuTime + int(float(records.getString(0)))
							if records.next():
								stats.dbTime = stats.dbTime + int(float(records.getString(0)))
							if records.next():
								stats.guiTime = stats.guiTime + int(float(records.getString(0)))
							if records.next():
								stats.roundTrips = stats.roundTrips + int(float(records.getString(0)))
							if records.next():
								stats.text = (str(records.getString(0))).strip()
				else:
					fields = ArrayList()
					fields.add('ENTRY_ID')
					fields.add('COUNT')
					fields.add('RESPTI')
					fields.add('CPUTI')
					fields.add('DBTIME')
					fields.add('GUITIME')
					fields.add('GUICNT')
					fields.add('TEXT')
					records = self.getApplicationStatistics(functionName, instance, day, fields)

					while records.next():
						entryID = records.getString("ENTRY_ID");
						transaction = self.getTransactionFromEntryID(entryID);
						mapUsers = None
						if mapTransactionToUsers != None:
							mapUsers = mapTransactionToUsers.get(transaction)
						if (transaction != None) and (len(transaction) > 0):
							stats = transactionToStats.get(transaction)
							if(stats == None):
								stats = TransactionStatistics(transaction)
								transactionToStats.put(transaction,stats)

							if(mapUsers != None):
								stats.users = ArrayList(mapUsers.keySet())
							count = records.getString("COUNT")
							stats.steps = stats.steps + int(count)
							stats.responseTime = stats.responseTime + int(records.getString("RESPTI"))
							stats.cpuTime = stats.cpuTime + int(records.getString("CPUTI"))
							stats.dbTime = stats.dbTime + int(records.getString("DBTIME"))
							stats.guiTime = stats.guiTime + int(records.getString("GUITIME"))
							stats.roundTrips = stats.roundTrips + int(records.getString("GUICNT"))
							stats.text = records.getString("TEXT")
			except:
				msg = sys.exc_info()[1]
				strmsg = '%s' % msg
				if strmsg.find('NO_DATA_FOUND') != -1:
					logger.debug(strmsg)
					logger.reportWarning('No data found in the given time range')
				else:
					logger.debugException('Unexpected error getting transactions for function:' + str(functionName))
					logger.reportWarning('Unexpected error getting transactions for function:' + str(functionName) + ':' + strmsg)

		transactions = ArrayList(transactionToStats.keySet())
		logger.debug("getActiveTransactions: Found [" + str(transactions.size()) + "] active transactions")
		if logger.isDebugEnabled():
			logger.debug("getActiveTransactions: transactions = " + str(transactions))
		transactionsInfo = self.getTransactionsInfo(transactions)

		it = transactionToStats.values()
		for stats in it:
			prop = Properties()
			prop.setProperty('data_name', str(stats.transaction))
			prop.setProperty('dialog_steps', str(stats.steps))
			prop.setProperty('total_response_time', str(stats.responseTime))
			prop.setProperty('average_response_time', str(stats.getAverageCPUTime()))
			prop.setProperty('total_cpu_time', str(stats.cpuTime))
			prop.setProperty('average_cpu_time', str(stats.getAverageCPUTime()))
			prop.setProperty('round_trips', str(stats.roundTrips))
			prop.setProperty('total_db_time', str(stats.dbTime))
			prop.setProperty('average_db_time', str(stats.getAverageDBTime()))
			prop.setProperty('total_gui_time', str(stats.guiTime))
			prop.setProperty('average_gui_time', str(stats.getAverageGUITime()))
			prop.setProperty('text', stats.text)
			prop.setProperty('saptransaction_averagedbtime', str(stats.users.size()))

			info = transactionsInfo.get(stats.transaction)
			if info != None:
				prop.setProperty('devclass', info.devclass)
				prop.setProperty('program', info.program)
				prop.setProperty('screen', info.screen)
				prop.setProperty('', info.screen)
			else:
				prop.setProperty('devclass', "")
				prop.setProperty('program', "")
				prop.setProperty('screen', "")
				prop.setProperty('version', "")
				
			activeTransactions.append(prop)
		
		return activeTransactions

	def getApplicationStatistics(self, functionName, instanceName, day, desiredFields):
		params = HashMap()
		params.put("PERIODTYPE", "D")
		params.put("STARTDATE", day)
		params.put("INSTANCE", instanceName)
		logger.info("Getting aggregated data for [" + day + "] on [" + instanceName + "]...")
		logger.debug('executing func:', functionName, '(params=',str(params),'##APPLICATION_STATISTIC##;fields=', str(desiredFields),')')
		return self.__client.executeFunction(functionName, params, 'APPLICATION_STATISTIC', desiredFields)
	
	def getTransactionFromEntryID(self, entryID):
		if entryID[len(entryID) - 1] == 'T':
			#in case space not found index of find will be -1 and according to array bihaviour
			#string entryID will be reduced by one character (as expected from original java code in SAPAgent)
			return entryID[:entryID.find(' ')]
		else:
			return None
	
	def callSapwlTcodeAggregationCopy(self, instanceName, day):
		codeCallSapwlTcodeAggregationCopy = 		[
		"PROGRAM CALL_SAPWL_TCODE_AGGREGATION_COPY.", 
#		"INCLUDE RSBDCSUB.",
		"	 DATA: BEGIN OF CONTEXT_TABLE OCCURS 100.",
		"			 INCLUDE STRUCTURE SAPWLUSTCX.",
		"	 DATA: END OF CONTEXT_TABLE.",
		"	 DATA: BEGIN OF STATISTICS_TABLE OCCURS 100.",
		"			 INCLUDE STRUCTURE SAPWLTCAGG.",
		"	 DATA: END OF STATISTICS_TABLE.",
		"	 CALL FUNCTION 'SAPWL_TCODE_AGGREGATION_COPY'",
#		"		   EXPORTING HOSTID = 'TOTAL'",
	   	"			 EXPORTING INSTANCE = '" + instanceName + "'",
	   	"						 STARTDATE = '" + day + "'",
	   	"						 AGGR_LEVEL = 'H'",
	   	"						 PERIODTYPE = 'D'",
	   	"						 LANGU = 'E'",
	   	"		   TABLES APPLICATION_SAPWLUSTCX = CONTEXT_TABLE",
	   	"					APPLICATION_STATISTIC = STATISTICS_TABLE.",
	   	"	 LOOP AT STATISTICS_TABLE.",
	   	"		   IF STATISTICS_TABLE-TTYPE = '01'.",
#	   	"			   WRITE 3(12) STATISTICS_TABLE-ACCOUNT.",
	   	"				 WRITE (72) STATISTICS_TABLE-ENTRY_ID.",
	   	"				 WRITE (72) STATISTICS_TABLE-COUNT.",
#	   	"			   WRITE STATISTICS_TABLE-DCOUNT.",
#	    "			   WRITE STATISTICS_TABLE-UCOUNT.",
#	   	"			   WRITE STATISTICS_TABLE-BCOUNT.",
#	   	"			   WRITE STATISTICS_TABLE-ECOUNT.",
#	   	"			   WRITE STATISTICS_TABLE-SCOUNT.",
	   	"				 WRITE (72) STATISTICS_TABLE-RESPTI.",
	   	"				 WRITE (72) STATISTICS_TABLE-CPUTI.",
	   	"				 WRITE (72) STATISTICS_TABLE-DBTIME.",
	   	"				 WRITE (72) STATISTICS_TABLE-GUITIME.",
	   	"				 WRITE (72) STATISTICS_TABLE-GUICNT.",
	   	"				 WRITE (72) STATISTICS_TABLE-TEXT.",
#	   	"				 WRITE (72) STATISTICS_TABLE-ENTRY_ID.",
	   	"		   ENDIF.",
	   	"	 ENDLOOP.",
	   	]

		
		valuesTable = ArrayList()
		for line in codeCallSapwlTcodeAggregationCopy:
			lineList = ArrayList()
			lineList.add(String('LINE'))
			lineList.add(String(line))
			valuesTable.add(lineList)
		
		params = HashMap()
		params.put('PROGRAM,PROGTAB', valuesTable)
		return self.__client.executeFunction('RFC_ABAP_INSTALL_AND_RUN', params, 'WRITES', 1)

	def getTransactionsInfo(self, transactions):
		mapTransactionToInfo = HashMap()
		mapProgramToTransaction = HashMap()

		if (transactions == None) or (len(transactions) == 0):
			logger.info("getTransactionsInfo: transactions list is empty")
			return mapTransactionToInfo
		
		transactionsRS = self.__client.executeQuery('TSTC', '', 'TCODE', transactions, 'TCODE,PGMNA,DYPNO')#@@CMD_PERMISION sap protocol execution
		while transactionsRS.next():
			transaction = transactionsRS.getString("TCODE")
			program = transactionsRS.getString("PGMNA")
			screen = transactionsRS.getString("DYPNO")
			if logger.isDebugEnabled():
				logger.debug("-------------------------------------------------------")
				logger.debug("getTransactionsInfo: transaction = " + transaction)
				logger.debug("getTransactionsInfo: program = " + program)
				logger.debug("getTransactionsInfo: screen = " + screen)
				logger.debug("-------------------------------------------------------")

			if (program == None) or (len(program) == 0):
				program = "N/A"
				logger.info("getTransactionsInfo: program for transaction [" + str(transaction) + "] is no available - setting to N/A.")

			info = TransactionInfo(transaction,program,screen)
			mapTransactionToInfo.put(transaction,info)
			transForProgram = mapProgramToTransaction.get(program)
			if transForProgram == None:
				transForProgram = ArrayList()
				mapProgramToTransaction.put(program,transForProgram)
			transForProgram.add(transaction)

		if logger.isDebugEnabled():
			logger.debug("getTransactionsInfo: mapProgramToTransaction = " + str(mapProgramToTransaction))

		if len(mapProgramToTransaction) == 0:
			logger.info("getTransactionsInfo: failed to get programs for transactions " + str(transactions))
			return mapProgramToTransaction

		objNames = ArrayList(mapProgramToTransaction.keySet())
		objNames.addAll(mapTransactionToInfo.keySet())
		
		
		programsRS = self.__client.executeQuery('TADIR', "(OBJECT = 'PROG' OR OBJECT = 'TRAN') AND ", 'OBJ_NAME', objNames, 'OBJECT,OBJ_NAME,VERSID,DEVCLASS')#@@CMD_PERMISION sap protocol execution
		
		while programsRS.next():
			objectType = programsRS.getString("OBJECT")
			if objectType == "PROG":
				program = programsRS.getString("OBJ_NAME")
				version = programsRS.getString("VERSID")
				transForProgram = mapProgramToTransaction.get(program)
				if transForProgram != None:
					
					for ti in transForProgram:
						info = mapTransactionToInfo.get(ti)
						if info == None:
							logger.info("program: Failed to find info for transaction [" + str(transaction) + "]")
						else:
							info.version = version
				else:
					logger.info("getTransactionsInfo: failed getting transactions for program [" + str(program) + "]")
			else: # transaction
				devclass = programsRS.getString("DEVCLASS");
				transaction = programsRS.getString("OBJ_NAME")
				info = mapTransactionToInfo.get(transaction)
				if info == None:
					logger.info("transaction: Failed to find info for transaction [" + str(transaction) + "]")
					info = TransactionInfo(transaction,"N/A","")
					mapTransactionToInfo.put(transaction,info)
				info.devclass = devclass

		if logger.isDebugEnabled():
			logger.debug("--------------------------------------------------")
			logger.debug("getTransactionsInfo: returning transaction info " + str(mapTransactionToInfo))
			logger.debug("--------------------------------------------------")

		return mapTransactionToInfo

class TransactionStatistics:
	def __init__(self, transaction):
		self.transaction = transaction
		self.servers = 0
		self.steps = 0 
		self.responseTime = 0
		self.cpuTime = 0
		self.dbTime = 0
		self.guiTime = 0
		self.roundTrips = 0
		self.text = ''
		self.users = ArrayList()

	def getAverageResponseTime(self):
		return self.getAverage(self.responseTime)

	def getAverageCPUTime(self):
		return self.getAverage(self.cpuTime)

	def getAverageDBTime(self):
		return self.getAverage(self.dbTime)

	def getAverageGUITime(self):
		return self.getAverage(self.guiTime)

	def getAverage(self, counter):
		if self.steps == 0:
			return self.steps
		return counter / self.steps

class TransactionInfo:
	def __init__(self, name, program, screen):
		self.name = name
		self.program = program
		self.screen = screen
		self.devclass = ""
		self.version = ""

	def toString(self):
		stringList = []
		stringList.append('{')
		stringList.append("program = ")
		stringList.append(self.program)
		stringList.append(", devclass = ")
		stringList.append(self.devclass)
		stringList.append(", version = ")
		stringList.append(self.version)
		stringList.append(", screen = ")
		stringList.append(self.screen)
		stringList.append('}')
		return ''.join(stringList)
