#coding=utf-8
from java.net import URL
from java.net import MalformedURLException
from java.net import InetSocketAddress

import ip_addr
import logger
import modeling
import netutils
import errormessages
import dns_resolver

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    urlId = Framework.getDestinationAttribute('id') 
    urlString = Framework.getDestinationAttribute('url')
    jobId = Framework.getDiscoveryJobId()

