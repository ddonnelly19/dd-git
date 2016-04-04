#coding=utf-8
import sys

import logger

from com.hp.ucmdb.discovery.probe.services.network.ms import MsNetworkUtil
# Java imports
from java.lang import Long
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

def getMsDomainNameList (Framework):
	MsDomainsListStr = Framework.getParameter('MsDomainsList')
	MsDomainsList = None
	if MsDomainsListStr == '*':
		return MsDomainsList
	if MsDomainsListStr != None:
		MsDomainsList = MsDomainsListStr.split(',')
	return MsDomainsList

def DiscoveryMain(Framework):
	SV_TYPE_SERVER          = 0x00000002L
	SV_TYPE_DOMAIN_CTRL     = 0x00000008L
	SV_TYPE_DOMAIN_BAKCTRL  = 0x00000010L
	SV_TYPE_DOMAIN_ENUM     = 0x80000000L

	OSHVResult = ObjectStateHolderVector()

	probe_name	= Framework.getDestinationAttribute('probe_name')
	try:
		netUtil = MsNetworkUtil()
		domainsOutput = netUtil.doNetServerEnum('NULL', SV_TYPE_DOMAIN_ENUM, 'NULL')
		if domainsOutput != None:
			MsDomainsList = getMsDomainNameList (Framework)
			netUtilGetServer = MsNetworkUtil()
			for domainInfo in domainsOutput:
				domainName = domainInfo[0]
				domainType = Long.parseLong(domainInfo[1])
				#Check if the current domain is to be discovered (if not, just continue to the next domain)
				if (MsDomainsList != None) and (domainName not in MsDomainsList):
					continue
				oshMsDomain = ObjectStateHolder('msdomain')
				oshMsDomain.setStringAttribute('data_name', domainName)
				if (domainType & SV_TYPE_DOMAIN_CTRL) !=0:
					oshMsDomain.setStringAttribute('msdomain_type', 'PDC')
				elif (domainType & SV_TYPE_DOMAIN_BAKCTRL) != 0:
					oshMsDomain.setStringAttribute('msdomain_type', 'BDC')

				hostsOutput = netUtilGetServer.doNetServerEnum('NULL', SV_TYPE_SERVER, domainName)
				if hostsOutput != None:
					oshMsDomain.setStringAttribute('probe_name', probe_name)
					OSHVResult.add(oshMsDomain)
	except:
		errorMsg = str(sys.exc_info()[1]).strip()
		Framework.reportError('Failed to discovery MS Domains :' + errorMsg)
		logger.errorException('Failed to discovery MS Domains')
	return OSHVResult
