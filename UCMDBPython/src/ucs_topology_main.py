__author__ = 'gongze'
from ucs_connection_data_manager import FrameworkBasedConnectionDataManager
import ucs_pull_base
import logger
import ucs_client

ucs_client.CACHE_READ = False


class MyFramework(object):
    def __init__(self, Framework, destination=None, parameters=None):
        super(MyFramework, self).__init__()
        self.Framework = Framework
        self.destinationAttributes = destination or {}
        self.parameters = parameters or {}

    def __getattr__(self, item):
        if item == 'Framework':
            return self.Framework
        else:
            return self.Framework.__getattribute__(item)

    def getParameter(self, attr):
        if self.parameters.has_key(attr):
            return self.parameters[attr]
        else:
            return self.Framework.getParameter(attr)


def DiscoveryMain(Framework):
    ip = Framework.getTriggerCIData('ip_address')
    if not ip:
        logger.warn('No Application IP for UCS')
        Framework.reportError('No Application IP for UCS')
        return

    preferCredential = Framework.getTriggerCIData('credentialsId')
    if not preferCredential:
        logger.warn('No credential found on UCS')
        Framework.reportError('No credential found on UCS')
        return

    originFramework = Framework
    connectionManager = None
    params = {'credentialsId': preferCredential}
    tmpFramework = MyFramework(originFramework, parameters=params)
    logger.debug("Connect IP %s by credential Id %s" % (ip, preferCredential))
    manager = FrameworkBasedConnectionDataManager(tmpFramework, ip)
    try:
        client = manager.getClient()
        if client:
            logger.debug("Connected")
            connectionManager = manager
    except:
        logger.debugException('')

    if connectionManager:
        return ucs_pull_base.discovery(Framework, connectionManager)
    else:
        logger.error('The credential is invalid on ip %s' % ip)
        Framework.reportError('The credential is invalid on ip %s' % ip)