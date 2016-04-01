#coding=utf-8
#########################################
# exportTQL_for_ARIS_to_UCMDB.py
# author: D. Orbach
# last modified: Vinay Seshadri - Nov 18 2010
#########################################

# common framework imports
import logger

# Java imports
from java.io import File

# UCMDB imports
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

# Integration imports from Integration API
from com.hp.ucmdb.adapters.push9 import IntegrationAPI


########################
# a convenient print debug method
########################
def dbg(msg):
	if 1:
		info(msg)
	elif logger.isDebugEnabled():
		logger.debug(msg)

########################
# a convenient print info method
########################
def info(msg):
	if logger.isInfoEnabled():
		logger.info(msg)

########################
# a convenient strip method
########################
def strip(data):
	index = data.find ('({')
	if index != -1:
		data = data[0:index]
	return data


##############
## a convenient way to concatenate strings w/ any object type
##############
def concatenate(*args):
	return ''.join(map(str,args))


##############
## Call the export method in IntegrationAPI
##############
def exportTQL(ip, userExtDir):
	integrationAPI = IntegrationAPI(ip, "exportTQL_for_ARIS_to_UCMDB.py")
	integrationAPI.processDir(userExtDir)



########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################
def DiscoveryMain(Framework):

	logger.info('Start Phase 2 ....Apply Mapping file to ARIS CIs')

	userExtUcmdbDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\ARIS\\'

	inputFilesDirectory = File(userExtUcmdbDir + 'inter\\')
	inputFiles = inputFilesDirectory.listFiles()

	filePathDir = userExtUcmdbDir + 'results\\'
	directory = File(filePathDir)
	files = directory.listFiles()

	## Clean up the existing result XML files
	if (files != None):
		for file in files:
			file.delete()

	## Make sure we have XML files in the intermediate directory
	xmlFileInIntermediatesDirectory = 0
	for inputFile in inputFiles:
		inputFileName = inputFile.getName()
		if inputFileName[len(inputFileName)-4:].lower() == '.xml' and inputFile.length() > 0:
			xmlFileInIntermediatesDirectory = 1
	if not xmlFileInIntermediatesDirectory:
		logger.warn('Intermediate XML not found or invalid. Perhaps no data was received from ARIS or an error occurred in the Pull_from_ARIS script.')
		return

	## Connect to the UCMDB Server, retrieve the results of the TQL
	## and generate the output XML files in results directory
	ip = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
	exportTQL(ip, userExtUcmdbDir)

	logger.info('End Phase 2 ....Apply Mapping file to ARIS CIs')