#coding=utf-8
import logger
import modeling
import netutils
import errormessages

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

def getMainframeKey(mainframeMacList):
    smallMAC = 'ZZZZZZZZZZZZ'

    for currMainframeMac in mainframeMacList:
        if currMainframeMac[1]:
            if currMainframeMac[1] < smallMAC:
                smallMAC = currMainframeMac[1]

    if smallMAC == 'ZZZZZZZZZZZZ':
        return None
    else:
        return smallMAC

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    DISCOVERED_IP = Framework.getDestinationAttribute('ip_address')
    DISCOVERED_IP_ID = Framework.getDestinationAttribute('ip_id')    
#    ip = modeling.createOshByCmdbIdString('ip_address', DISCOVERED_IP_ID)
    ucmdbVersion = modeling.CmdbClassModel().version()
    if ucmdbVersion >= 9:
        ipClass = 'ip_address'
    else:
        ipClass = 'ip'

    protocols = Framework.getAvailableProtocols(DISCOVERED_IP, ClientsConsts.SNMP_PROTOCOL_NAME)

    if protocols.__len__() == 0:
        errStr = 'No credentials defined for the triggered ip'
        logger.debug(errStr)
        Framework.reportWarning(errStr)
    else:
        for protocol in protocols:
            sysplexNameList = None
            lparIpList = None
            
            snmpOSH = modeling.createSnmpOSH(DISCOVERED_IP, None)

            client = None
            try:
                client = Framework.createClient(protocol)
                logger.debug('got snmp agent for: ', DISCOVERED_IP)
                isMultiOid = client.supportMultiOid()
                
                sysplexNameList = client.executeQuery( '1.3.6.1.4.1.2.6.19.2.2.2.41,1.3.6.1.4.1.2.6.19.2.2.2.41,string,1.3.6.1.4.1.2.6.19.2.2.2.40,string' )#@@CMD_PERMISION snmp protocol execution
                sysplexNameList = sysplexNameList.asTable()

                lparIpList = client.executeQuery( '1.3.6.1.2.1.4.20.1.1,1.3.6.1.2.1.4.20.1.2,string' )#@@CMD_PERMISION snmp protocol execution
                lparIpList = lparIpList.asTable()

                mainframeMacList = client.executeQuery( '1.3.6.1.2.1.2.2.1.6,1.3.6.1.2.1.2.2.1.7,hexa' )#@@CMD_PERMISION snmp protocol execution
                mainframeMacList = mainframeMacList.asTable()
                snmpOSH.setAttribute('application_port', client.getPort())
                
                snmpOSH.setAttribute('application_timeout', client.getTimeout())
                snmpOSH.setAttribute('snmp_port', client.getPort())
                snmpOSH.setAttribute('credentials_id', client.getCredentialId())
                snmpOSH.setAttribute('snmp_retry', client.getRetries())
                snmpOSH.setAttribute('snmp_timeout', client.getTimeout())
                if isMultiOid == 1:
                    snmpOSH.setBoolAttribute('snmp_supportmultioid', 1)
                else:
                    snmpOSH.setBoolAttribute('snmp_supportmultioid', 0)
            except:
                logger.debugException('Unexpected SNMP_AGENT Exception:')
                continue

            if client != None:
                client.close()

            mainframeKey = getMainframeKey(mainframeMacList)
            if mainframeKey:
                mainframeOSH = modeling.createCompleteHostOSH('mainframe', mainframeKey, machineName = mainframeKey)
                modeling.setHostOsFamily(mainframeOSH, 'mainframe')
                OSHVResult.add(mainframeOSH)

                for currSysplex in sysplexNameList:
                    if logger.isDebugEnabled():
                        logger.debug( 'SYSPLEX : ', currSysplex[1] )
                        logger.debug( 'LPAR : ', currSysplex[2] )
                        logger.debug( 'MainframeKEY : ', mainframeKey )

                    lparKey = mainframeKey + ':' + currSysplex[2]
                    lparOSH = modeling.createCompleteHostOSH('lpar', lparKey, machineName = currSysplex[2])
                    OSHVResult.add(lparOSH)
                    
                    snmpOSH.setContainer(lparOSH)
                    OSHVResult.add(snmpOSH)

                    # Create contained link between discovered IP and lpar
                    OSHVResult.add(modeling.createLinkOSH('contained', lparOSH, modeling.createOshByCmdbIdString(ipClass, DISCOVERED_IP_ID)))

                    # Create member link between lpar and Mainframe
                    OSHVResult.add(modeling.createLinkOSH('member', mainframeOSH, lparOSH))

                    # Create sysplex
                    sysplexOSH = ObjectStateHolder('sysplex')
                    sysplexOSH.setAttribute('data_name', currSysplex[1])
                    OSHVResult.add(sysplexOSH)

                    # Create member link between lpar and sysplex
                    OSHVResult.add(modeling.createLinkOSH('member', sysplexOSH, lparOSH))

                    # Create member link between mainframe and sysplex
                    OSHVResult.add(modeling.createLinkOSH('member', mainframeOSH, sysplexOSH))

                    # connect all ips to lpar
                    for currLparIp in lparIpList:
                        if netutils.isLocalIp(currLparIp[1]):
                            continue

                        currIpOSH = modeling.createIpOSH(currLparIp[1])
                        OSHVResult.add(currIpOSH)
                        OSHVResult.add(modeling.createLinkOSH('contained', lparOSH, currIpOSH))
                break
            else:
                logger.debug("Failed to get Mainframe key.")
        else:
            errormessages.resolveAndReport("Could not perform snmp connection to %s" % DISCOVERED_IP, ClientsConsts.SNMP_PROTOCOL_NAME, Framework)

    return OSHVResult
