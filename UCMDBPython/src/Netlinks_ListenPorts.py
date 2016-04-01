#coding=utf-8
import sys

import logger
import modeling
import errorcodes
import errorobject

import Netlinks_Service

from appilog.common.system.types.vectors import ObjectStateHolderVector

class NetlinksListenPorts(Netlinks_Service.NetlinksService):
    def __init__(self, Framework):
        Netlinks_Service.NetlinksService.__init__(self, Framework)

    def discover_private(self):
        ports = self.servicesPorts(0)
        query = 'select ipaddress, port, Protocol from Port_Process '
        if (ports != None) and (len(ports) > 0):
            query = query + ' where listen and port IN (' + ports + ')'
        logger.debug('ListenPorts,sql:', query)
        conn = self.Framework.getProbeDatabaseConnection('TCPDISCOVERY')
        st = None
        result = None
        try:
            try:
                if logger.isDebugEnabled():
                    logger.debug(query)
                st = conn.createStatement()
                result = st.executeQuery(query)
                dataFound = 0
                while result.next():
                    dataFound = 1
                    address = result.getString('ipaddress');
                    port = result.getInt('port');
                    prot = result.getInt('Protocol');
                    if not self.shouldInclude(address, 1):
                        if logger.isDebugEnabled():
                            logger.debug("ignoring ip out of scope: " + address)
                        continue
                    ipOSH = modeling.createIpOSH(address)
                    self.Framework.sendObject(ipOSH)

                    hostOSH = modeling.createHostOSH(address)
                    portName = self.knownPortsConfigFile.getPortName(prot, port)
                    if portName == None:
                        portName = str(port)

                    portType = modeling.SERVICEADDRESS_TYPE_TCP
                    if prot == modeling.UDP_PROTOCOL:
                        portType = modeling.SERVICEADDRESS_TYPE_UDP

                    serverPortOSH = modeling.createServiceAddressOsh(hostOSH, address, port, portType, portName)
                    containedLinkOSH = modeling.createLinkOSH('contained', hostOSH, ipOSH)
                    self.Framework.sendObject(hostOSH)
                    self.Framework.sendObject(serverPortOSH)
                    self.Framework.sendObject(containedLinkOSH)
                if not dataFound:
                    self.Framework.reportWarning("No data to process, please check if Host Resources jobs had already run")
            except:
                msg = sys.exc_info()[1]
                exInfo = '%s' % msg
                if exInfo.find('ResultSet closed') != -1:
                    error = 'Connection to probe database closed'
                    details = str("Please increase job execution max time and/or configure parameter 'appilog.agent.netflow.heldTimeoutConnection' in DiscoveryProbe.properties file")
                    errobj = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [error, details], error + details)
                    logger.reportErrorObject(errobj)
                else:
                    errobj = errorobject.createError(errorcodes.FAILED_TO_EXECUTE_SQL, [exInfo], exInfo)
                    logger.reportErrorObject(errobj)
        finally:
            if result != None:
                try:
                    result.close
                except:
                    pass
            conn.close(st)
            conn.close()

def DiscoveryMain(Framework):
    logger.reportWarning('The job is deprecated. Use "Network Connectivity Data Analyzer" instead.')
    #    netlinks = NetlinksListenPorts(Framework)
    #    netlinks.discover()
    return ObjectStateHolderVector()
