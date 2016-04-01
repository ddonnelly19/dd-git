#coding=utf-8
import string
import logger

from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.library.clients.agents import SiebelAgent
from com.hp.ucmdb.discovery.library.clients.siebel import SiebelClient
from java.util import Properties

FALSE = 0
TRUE = 1
STR_TABLE_END = SiebelAgent.SIEBEL_STR_TABLE_END
DELIMITER = SiebelAgent.SIEBEL_DELIMITER

PROPERTY_IP_ADDRESS = "ip_address"

def createClient(framework, ip, matchers=SiebelAgent.SIEBEL_DEFAULT_GATEWAY_MATCHERS, credentialsId=None, port=None):	
	properties = Properties()
	properties.put(AgentConstants.PROP_AGENT_OUTPUT_MATCHERS, matchers)
	properties.put(PROPERTY_IP_ADDRESS, ip)
	if port:
		properties.put(SiebelClient.PROPERTY_GATEWAY_PORT, port)
	if credentialsId:
		return framework.createClient(credentialsId, properties)
	else:
		return framework.createClient(properties)
	

###########################################################
## A basic error checking routine for a srvrmgr command
def containsError( output):
	try: 
		SiebelAgent.sanitizeOutputAndCheckForErrors(output)
		return FALSE
	except:
		return TRUE

###########################################################
## this routine parses the header of a list command output
## and returns a list of indices.
## each index says where this field's start location is in
## each data line.
## this is needed because simple tokenizing gets messy
## when names are separated by spaces or not all data in the
## line is present
##
## examples: (first row is not of output but marks indices)
## 1) missing data:
##
## 0             13         23 ...
## SBLSRVR_NAME  HOST_NAME  INSTALL_DIR         SBLMGR_PID  SV_DISP_STATE  SBLSRVR_STATE  START_TIME           END_TIME  SBLSRVR_STATUS
## ------------  ---------  ------------------  ----------  -------------  -------------  -------------------  --------  --------------------------------
## sblapp1_AS    sblapp1    d:\sea752\siebsrvr  1904        Running        Running        2004-08-10 15:43:46            7.5.3.3 [16172] LANG_INDEPENDENT
## sblapp2       sblapp2    d:\sea752\siebsrvr  1336        Running        Running        2004-08-01 03:29:42            7.5.3.3 [16172] LANG_INDEPENDENT
## sblapp1       sblapp1    d:\sea752\siebsrvr              LIBMsg: No strings available for this language setting
##
## 2) spaces in names
##
## 0                                        41          52 ...
## CG_NAME                                  CG_ALIAS    CG_DESC_TEXT                                        CG_DISP_ENABLE_ST  CG_NUM_COMP  SV_NAME     CA_RUN_STATE
## ---------------------------------------  ----------  --------------------------------------------------  -----------------  -----------  ----------  ------------
## Assignment Management                    AsgnMgmt    Assignment Management Components                    Enabled            2            sblapp1_AS  Online
## Communications Management                CommMgmt    Communications Management Components                Enabled            7            sblapp1_AS  Online
## Content Center                           ContCtr     Content Center Components                           Enabled            2            sblapp1_AS  Online
##
## here tokenizing would break the names of the components.
## instead of starting to calculate number of spaces etc. saving indexes
## is easier and also solves missing data problems.
##
## NOTE: the last index will be the end of the string to ease
## parsing code based on these indices (good for loops)
##
def buildHeaderIndices(header):
	indices = []
	index = 0
	inWord = FALSE
	for chr in header:
		if chr in string.whitespace:
			if inWord:
				inWord = FALSE
		else:
			if not inWord:
				inWord = TRUE
				indices += [index]
		index += 1

	# put the last index as the end of the string
	# makes this better for looping on this list
	# for parsing later
	indices += [len(header)]
	return indices

###########################################################
## a little wrapper to get a field from a row based on
## parsed indices
##
def getField(index, row, indices):
	return row[indices[index]:indices[index+1]].rstrip()

##########################################################
## return a list of all field values
def getFields(row, indices):
	fields = []
	# OLD CODE - START
	#
	# remove last index, it just marks the end of the line
	# it's not a starting index of a field
	#indiceNum = len(indices)-1
	#for index in range(indiceNum):
	#	fields += [self.getField(index, row, indices)]
	# OLD CODE - END

	columns = row.split(DELIMITER)
	for column in columns:
		fields += [column.rstrip()]
	return fields

def findDashedLine(rows):
	found = 0
	index = 0
	for row in rows:
		if string.find(row, '---') != 0:
			index += 1
		else:
			found = 1
			break
	if found:
		return index
	else:
		return -1

# make a table (list of lists) from a svrmgr table text listing
# the return table looks like this:
# [
# [fields, original_row]
# [fields, original_row]
# ...
# ]
# [fields] is a list of string representing the parsed attributes
# according to the header indices.
# original_row is a string of the row that was parsed - used for
# error purposes.
def makeTable(tableText):
	retTable = None
	if containsError(tableText):
		logger.error('error listing table:\n', tableText, '\n')
		return retTable
	rows = string.split(tableText, '\n')
	# look for the line of dashes representing the "table line"
	# a row above that is the header row, and data starts a row
	# below the dashed line.
	dashedLineIndex = findDashedLine(rows)
	header = rows[dashedLineIndex-1]
	# TODO: might want to check the headers haven't changed in the future
##    self.verifyServerHeader(header)
	indices = buildHeaderIndices(header)
	# actual data starts at the 4th row (0 indexed)
	dataRows = rows[dashedLineIndex+1:]
	retTable = []
	for dataRow in dataRows:
		if string.find(dataRow, STR_TABLE_END) > -1:
			logger.debug('reached end of table:', dataRow)
			break
		if string.strip(dataRow) != '':
			logger.debug('row:', dataRow)
			fields = getFields(dataRow, indices)
			logger.debug('fields:', string.join(fields))
			# add dataRow at the end for error conditions
			retTable += [[fields] + [dataRow]]
		else:
			continue
	logger.debug('finished parsing output table')
	return retTable
