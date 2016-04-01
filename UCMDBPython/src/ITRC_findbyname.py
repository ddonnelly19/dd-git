#coding=utf-8
import logger
import errormessages
import modeling
import ITRCUtils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from ITRCClient import ITRC_Client
from java.util import Date

def findITRC(Framework, hostName, ips = [], cmdbid = None, url = None):
    OSHVResult = ObjectStateHolderVector()
    
    username = '!cdchpud'    
    password = 'kcaELaFaXM3xvm2RDFg'
     
    try:        
        client = ITRC_Client(Framework, 'https://api.itrc.comcast.net/api/v3/', username, password, True)
        if url:
            params = {
                    "include": "active-assignments,operational-status"
                  }      
            OSHVResult.addAll(client.getOSH(client.get(url, params)))      
        
        if OSHVResult.size() <= 0:     
            OSHVResult.addAll(client.findDeviceID(hostName, ips))
        
        if OSHVResult.size() <= 0:
            msg = "Cannot find ITRC ID for %s (%s)" % (hostName, ips)           
            logger.warn(msg)
            if Framework:
                Framework.reportWarning(msg)
        
        if cmdbid:
            try:
                CmdbOIDFactory = modeling.CmdbObjectID.Factory
                cmdbid = CmdbOIDFactory.restoreObjectID(cmdbid)
                if cmdbid and OSHVResult.size() > 0:
                    if not OSHVResult.contains(cmdbid):
                        hostOSH = modeling.createOshByCmdbId('node', cmdbid)
                        hostOSH.setDateAttribute('itrc_updated', Date())
                        hostOSH.setStringAttribute('itrc_data', msg)
                        if url:
                            hostOSH.setAttribute("itrc_id", None)
                            hostOSH.setAttribute("itrc_url", None)
                            logger.warn("Clearing ITRC ID on %s" % cmdbid)   
                        OSHVResult.add(hostOSH)
            except:
                pass
            
    except Exception, e:
        msg = logger.prepareJythonStackTrace("Error finding ITRC ID for %s (%s)" % (hostName, ips), e)
        if Framework:
            Framework.reportError(msg)
        logger.error(msg)
        
        '''
        if cmdbid:
            hostOSH = modeling.createOshByCmdbIdString('node', cmdbid)
            #hostOSH.setDateAttribute('itrc_updated', Date())
            hostOSH.setStringAttribute('itrc_data', msg)
            OSHVResult.add(hostOSH)
        '''
        
    return OSHVResult


def DiscoveryMain(Framework):
   
    jobId = Framework.getDiscoveryJobId()
    id = Framework.getDestinationAttribute('id')
    hostName = Framework.getTriggerCIData('display_label') 
    ips = Framework.getTriggerCIDataAsList('ips') or []
    url = Framework.getTriggerCIData('url') or 'udappg-as-1p.sys.comcast.net'
    
    return findITRC(Framework, hostName, ips,  id, url)
    
    #protocolMgr = ProtocolDictionaryManager.getProtocolParameters("genericprotocol", "DEFAULT", None)[0]
    #username = protocolMgr.getProtocolAttribute('protocol_username')
    #password = protocolMgr.getProtocolAttribute('protocol_password')
OSHVResult = ObjectStateHolderVector()
OSHVResult = findITRC(None, 'udappg-as-1p.sys.comcast.net') 
print(OSHVResult.toXmlString())
