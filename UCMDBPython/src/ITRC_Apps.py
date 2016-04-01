#coding=utf-8
import logger

from appilog.common.system.types.vectors import ObjectStateHolderVector
from ITRCClient import ITRC_Client
 
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    username = '!cdchpud'
    password = 'kcaELaFaXM3xvm2RDFg'
    url = 'https://api.itrc.comcast.net/api/v3/apps'
    try:
        logger.debug(url)      
        client = ITRC_Client(Framework, 'https://api.itrc.comcast.net/api/v3/', username, password, True)
        params = {"include": "assignments,server-farms,endpoints,app-group,aliases"}      
        obj = client.get(url, params)        
        return client.getOSH(obj, True)
            
    except Exception, e:        
        msg = logger.prepareFullStackTrace("Error getting info for %s: " % (url), e)
        logger.error(msg)
        if Framework:
            Framework.reportError(msg)

    return OSHVResult

print(DiscoveryMain(None).toXmlString())