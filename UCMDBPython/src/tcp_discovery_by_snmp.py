#coding=utf-8
import logger
import errormessages
import process_discoverer
import Dis_TCP

from tcp_discovery_basic import TcpDiscoverer

from java.lang import Exception as JavaException

class SnmpTcpDiscoverer(TcpDiscoverer):

    def _discoverTcp(self):
        Dis_TCP.discoverTCPbySNMP(self.client, self.framework)
    
    def _discoverProcesses(self):
        hostId = self.framework.getDestinationAttribute('hostId')
        processes = []

        try:

            processDiscoverer = process_discoverer.getDiscovererBySnmp(self._getClient())
            processes = processDiscoverer.discoverAllProcesses()
            if not processes:
                raise ValueError()
        except:
            logger.warnException("Failed to discover processes by SNMP")

        if processes:
            process_discoverer.saveProcessesToProbeDb(processes, hostId, self.framework)


def DiscoveryMain(Framework):       
    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        SnmpTcpDiscoverer(Framework).discover()
    except JavaException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)