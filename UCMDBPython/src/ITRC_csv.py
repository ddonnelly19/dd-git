#coding=utf-8
import csv #csv reader module
import netutils
import modeling
import logger
import ip_addr
import errormessages
import ITRCUtils

from org.apache.commons.httpclient.methods import GetMethod, HeadMethod
from org.apache.commons.httpclient import HttpClient
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework): 
    try:
        print('here')

        url = 'https://itrc.comcast.net/devices.csv?device_search_id=1199278'
        data = netutils.doHttpGet(url, 100000) 
        print(data)  
        ca_reader = csv.reader(data.splitlines()) #split lines on \n since this is a string and not a file
        
        for row in ca_reader:
            try:
                OSHVResult = ObjectStateHolderVector()
                hostName = row[2] or row[1]
                ipAddress = row[10]
                hostOSH = modeling.createHostOSH(ipAddress, ITRCUtils.getNodeType(row[8]), row[15], hostName, None, None)
                hostOSH.setStringAttribute("itrc_id", str(row[0]))
                hostOSH.setAttribute("itrc_url", 'https://api.itrc.comcast.net/api/v3/devices/%s' % (row[0]))
                
                hostOSH.setAttribute("primary_dns_name", row[2])
                hostOSH.setAttribute("name", row[1])
                hostOSH.setAttribute("data_note", row[9])        
               
                modeling.setHostSerialNumberAttribute(hostOSH, row[19])
                                   
                hostOSH.setAttribute("bios_asset_tag", row[21])
                hostOSH.setAttribute("primary_ip_address", ipAddress) 
                            
                OSHVResult.add(hostOSH)
                            
                if ipAddress:                
                    ipOSH = modeling.createIpOSH(ipAddress, None, row[2], None)
                    OSHVResult.add(ipOSH)
                    OSHVResult.add(modeling.createLinkOSH('containment', hostOSH, ipOSH))
                        
                ip2 = row[31]
                if ip2:                
                    ip2OSH = modeling.createIpOSH(ip2, None, None, None)
                    OSHVResult.add(ip2OSH)
                    OSHVResult.add(modeling.createLinkOSH('containment', hostOSH, ip2OSH))     
                    
                if row[40]:
                    for appenv in row[40].split(";"):
                        appenv_spl = appenv.split("/")
                        app = appenv_spl[0].lstrip()
                        env = appenv_spl[1].lstrip()
                
                        if env != "Production":
                            app = "%s_%s" % (app,env)
                        
                        appOsh = ObjectStateHolder('business_application')
                        appOsh.setAttribute('name', app)
                        
                        OSHVResult.add(appOsh)
                        OSHVResult.add(modeling.createLinkOSH('containment', appOsh, hostOSH))
                        
                if row[5]:
                    locOSH = ObjectStateHolder('location')
                    locOSH.setAttribute("name", row[5])
                    locOSH.setAttribute("location_type", "site")  
                    
                    OSHVResult.add(locOSH)                 
                    OSHVResult.add(modeling.createLinkOSH('membership', locOSH, hostOSH))
                
                if Framework:
                    Framework.sendResults(OSHVResult)
                print(OSHVResult.toXmlString())
            except Exception, e:
                logger.warnException("Error searching for device", e)
    except Exception, e:
            logger.warnException("Error searching for device", e)
                      
    return ObjectStateHolderVector()

DiscoveryMain(None)