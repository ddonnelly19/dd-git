#coding=utf-8
########################
# exportTQL_for_Remedy_to_UCMDB.py
# author: D. Orbach
# last modified: Vinay Seshadri - Aug 13, 2010
########################

# common framework imports
import sys
import string
import traceback
from java.lang import *
from java.util import *
from org.jdom import *
from org.jdom.input import *
from org.jdom.output import *
from java.io import *
from com.hp.ucmdb.discovery.probe.util import HostKeyUtil
from com.hp.ucmdb.discovery.probe.util import NetworkXmlUtil
from appilog.common.utils.parser import OperatorParser
from appilog.common.utils import Protocol
from appilog.common.system.defines import AppilogTypes
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
# Integration imports from wrapper.jar
from com.hp.ucmdb.adapters.push9 import IntegrationAPI

# log4j stuff
from org.apache.log4j import Category

# get the logger instance for this script
logger = Category.getInstance('PATTERNS_DEBUG')

if logger.isInfoEnabled():
	logger.info('Start exportTQL_for_SIM_to_UCMDB.py')

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

def exportTQL (ip, userExtDir):
	integrationAPI = IntegrationAPI (ip, "exportTQL_for_SIM_to_UCMDB.py")
	integrationAPI.processDir(userExtDir)



########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework):
	fileSeparator = File.separator
	# Destination Data
	userExtUcmdbDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + fileSeparator + 'TQLExport' + fileSeparator + 'hpsim' + fileSeparator

	inputFilesDirectory = File(userExtUcmdbDir + 'inter' + fileSeparator)
	inputFiles = inputFilesDirectory.listFiles()

	filePathDir = userExtUcmdbDir + 'results' + fileSeparator
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
		logger.warn('Intermediate XML not found or invalid. Perhaps no data was received from SIM or an error occurred in the SIM_Discovery script.')
		return

	## Connect to the UCMDB Server, retrieve the results of the TQL
	## and generate the output XML files in results directory
	ip = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
	exportTQL(ip, userExtUcmdbDir)
	info('End exportTQL_for_SIM_to_UCMDB.py')


