#coding=utf-8
import logger
import errormessages
import modeling
import ITRCUtils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from ITRCClient import ITRC_Client

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    jobId = Framework.getDiscoveryJobId()
    id = Framework.getDestinationAttribute('id')
    url = Framework.getTriggerCIData('url') or None
    
    #protocolMgr = ProtocolDictionaryManager.getProtocolParameters("genericprotocol", "DEFAULT", None)[0]
    #username = protocolMgr.getProtocolAttribute('protocol_username')
    #password = protocolMgr.getProtocolAttribute('protocol_password')
    
    username = '!cdchpud'
    password = 'kcaELaFaXM3xvm2RDFg'
    
    try:        
        client = ITRC_Client('https://api.itrc.comcast.net/api/v3/', username, password, True)
        params = {
                    "include": "active-assignments,operational-status"
                  }      
        obj = client.get(url, params)
        return client.getDeviceOSH(obj, id, True)
            
    except Exception, e:
        msg = logger.prepareJythonStackTrace("Error getting device info for %s" % (url), e)
        errormessages.resolveAndReport(msg, jobId, Framework)
        logger.error(msg)

    return OSHVResult

params = {
                    "include": "os,active-assignments,operational-status"
        }  

client = ITRC_Client('https://api.itrc.comcast.net/api/v3/', '!cdchpud', 'kcaELaFaXM3xvm2RDFg', True)      
obj = client.get('https://api.itrc.comcast.net/api/v3/virtual-hosts/453575', params)
OSHVResult = client.getDeviceOSH(obj, None, True)
print(OSHVResult.toXmlString())