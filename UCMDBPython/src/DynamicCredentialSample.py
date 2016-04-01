#coding=utf-8
from shellutils import ShellUtils
import shellutils
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):

	# Create our dynamic SSH credential entry	
	sshCredOSH = ObjectStateHolder('sshprotocol')
	sshCredOSH.setStringAttribute('sshprotocol_authmode','password')
	sshCredOSH.setStringAttribute('protocol_username','root')

	# Enter a real password here instead of <YOUR PASSWORD HERE> string
	sshCredOSH.setBytesAttribute('protocol_password', '<YOUR PASSWORD HERE>')
	
	# List of required attributes to create SQL credential:
	# protocol name - sqlprotocol
	# protocol_port (integer)
	# sqlprotocol_dbname (string) - for use with  db2
	# sqlprotocol_dbsid (string) - for use with oracle, MicrosoftSQLServerNTLM, 
	# sqlprotocol_dbtype (db_types) - can be one of the following: 
	# 	MicrosoftSQLServer, db2, Sybase, oracle, MicrosoftSQLServerNTLM
	
	# List of required attributes to create NTCMD credential:
	# protocol name - ntadminprotocol
	# ntadminprotocol_ntdomain (string) - Windows Domain name

	credentialId = Framework.createDynamicCredential(sshCredOSH)


	# Use our Dynamic credential in order to connect to the remote machine
	client = Framework.createClient(credentialId)
	
	# Create shellUtils
	shellUtils = ShellUtils(client)
	
	# Execute some command
	shellUtils.execCmd('uname -a')


	# Explicitly Release all our used resources
	shellUtils.closeClient()
	Framework.releaseDynamicCredential(credentialId)