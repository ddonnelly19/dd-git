#coding=utf-8
import logger
import shellutils
import errormessages
import Dis_TCP

import process_discoverer

from tcp_discovery_basic import TcpDiscoverer

from java.lang import Exception as JavaException

class ShellTcpDiscoverer(TcpDiscoverer):

    def __init__(self, framework):
        TcpDiscoverer.__init__(self, framework)
        self.shell = self._createShell()

    def _createShell(self):
        return shellutils.ShellUtils(self._getClient())

    def _getShell(self):
        return self.shell

    def _discoverTcp(self):
        Dis_TCP.discoverTCPbyShell(self.client, self.framework, self.shell)

    def _discoverProcesses(self):
        hostId = self.framework.getDestinationAttribute('hostId')

        processes = []
        try:
            discoverer = process_discoverer.getDiscovererByShell(self._getShell())
            processes = discoverer.discoverAllProcesses()
            if not processes:
                raise ValueError()
        except:
            logger.warnException("Failed to discover processes")

        if processes:
            process_discoverer.saveProcessesToProbeDb(processes, hostId, self.framework)



def DiscoveryMain(Framework):
    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        discoverer = ShellTcpDiscoverer(Framework)
        discoverer.discover()
    except JavaException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    try:
        discoverer.shell and discoverer.shell.closeClient()
    except:
        logger.debugException('')
        logger.error('Unable to close shell')
