#coding=utf-8
import modeling
import logger
import netutils
import dbutils

def doReadFile(shellUtils, fileName, OSHVResult, tnsFile):

	tns_entries = dbutils.parseTNSNames(tnsFile, '', shellUtils)
#	parseTnsEntries(fileName, shellUtils, tns_entries, OSHVResult)
	if (len(tns_entries)==0):
		logger.info('no entries returns from ',  fileName, '. Please verify if the file exists and it is valid TNS file.')
		return

	logger.debug('Found ', len(tns_entries), ' entries in tnsnames.ora file.')
	oracleList = []
	for tns_entry in tns_entries:
		try:
			db_type	= 'oracle'
			connectString = tns_entry[0]
			host_dns= tns_entry[1]
			db_port	= tns_entry[2]
			db_sid	= tns_entry[3].upper()
			host_ip	= tns_entry[5]
			if (netutils.isValidIp(host_ip)):
				hashName = host_ip + db_sid
				if ((hashName in oracleList) == 0) :
					oracleList.append(hashName)
					hostOSH = modeling.createHostOSH(host_ip)
					oracleOSH = modeling.createDatabaseOSH(db_type, db_sid, db_port, host_ip, hostOSH)
					oracleOSH.setAttribute('database_dbconnectstring', connectString)
					oracleOSH.setContainer(hostOSH)
					OSHVResult.add(hostOSH)
					OSHVResult.add(oracleOSH)
			else:
				logger.warn("Can not resolve the IP from the TNS entry's host name (", host_dns, ") - TNS entry skipped.")

		except:
			logger.debugException('Unexpected TNS Parsing Exception:')
