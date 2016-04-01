#coding=utf-8
import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
###################################################################################################
# Script:		SNMP_HR_OSUser_Jython.py
# Version:		1.0
# Module:		Host_Resources_By_SNMP_Jython
# Purpose:		
# Author:		Alon Lifshitz
# Created:		26-07-2006
# Notes:		
# Changes:		Ralf Schulz
#				14-11-2006 by Asi Garty - modified to be MAM 7.0 compliant
###################################################################################################

##############################################
########         FUNCTIONS          ##########
##############################################

# create the class instance for the CIT we created in the gui with the data_name 
def doOSUserOSH(name):
	sw_obj = ObjectStateHolder('winosuser')
	
	sw_obj.setAttribute('data_name', name)
	# return the object
	return sw_obj

def doQueryOSUsers(client, OSHVResult):
	_hostObj = modeling.createHostOSH(client.getIpAddress())
	data_name_mib = '1.3.6.1.4.1.77.1.2.25.1.1,1.3.6.1.4.1.77.1.2.25.1.2,string'
	resultSet = client.executeQuery(data_name_mib)#@@CMD_PERMISION snmp protocol execution
	while resultSet.next():
		UserName = resultSet.getString(2)
		########## send object ##############
		OSUserOSH = doOSUserOSH(UserName)
		OSUserOSH.setContainer(_hostObj)
		OSHVResult.add(OSUserOSH)

