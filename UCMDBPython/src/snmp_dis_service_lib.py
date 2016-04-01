#coding=utf-8
import logger
import modeling
from snmputils import SnmpAgent, SimpleTableWorker

###################################################################################################
# Script:		SNMP_HR_Software_Jython.py
# Version:		2.0
# Module:		Host_Resources_By_SNMP_Jython
# Purpose:		
# Author:		Kulak Michael, Boiko Oleh
# Created:		27-08-2008
# Notes:		
###################################################################################################

INSTALL_STATUS_DICT = {'1' : 'Uninstalled', '2' : 'Install-pending', '3' : 'Uninstall-pending', '4' : 'Installed'}
TRUE_FALSE_DICT = {'1' : 'False', '2' : 'True'}
OPERATING_STATUS_DICT = {'1' : 'Running', '2' : 'Running', '3' : 'Running', '4' : 'Stopped'}

def doQuerySNMPService(client, OSHVResult):
    _hostObj = modeling.createHostOSH(client.getIpAddress())
    snmpAgent = SnmpAgent('1.3.6.1.4.1.77', client, None)

    serviceTableWorker = SimpleTableWorker('1.2.3.1', 'service', snmpAgent)

    serviceTableWorker.defineMapping(1, 'data_name')
    serviceTableWorker.defineMappingByMap(2, 'service_installstatus', INSTALL_STATUS_DICT)
    serviceTableWorker.defineMappingByMap(3, 'service_operatingstatus', OPERATING_STATUS_DICT)
    serviceTableWorker.defineMappingByMap(4, 'service_canbeuninstalled', TRUE_FALSE_DICT)
    serviceTableWorker.defineMappingByMap(5, 'service_canbepaused', TRUE_FALSE_DICT)

    oshs = serviceTableWorker.createOSHs()

    for osh in oshs:
        osh.setContainer(_hostObj)
        OSHVResult.add(osh)

