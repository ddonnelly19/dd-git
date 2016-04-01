__author__ = 'gongze'
import logger
import modeling
import netutils

from appilog.common.system.types.vectors import ObjectStateHolderVector

import ucs_client
from ucs_connection_data_manager import FrameworkBasedConnectionDataManager

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
    credentialIds = netutils.getAvailableProtocols(Framework, 'ucs', ip)
    if not credentialIds:
        logger.warn('No generic credential for UCS')
        Framework.reportWarning('No generic credential for UCS')
        return

    ucs_id = Framework.getTriggerCIData('ucs_id')

    originFramework = Framework
    connectionManager = None
    connectedCredentialId = None
    for credentialId in credentialIds:
        logger.debug('Begin trying credential id:', credentialId)
        params = {'credentialsId': credentialId}
        tmpFramework = MyFramework(originFramework, parameters=params)
        manager = FrameworkBasedConnectionDataManager(tmpFramework, ip)
        try:
            client = manager.getClient()
            if client:
                logger.debug("Connected")
                connectionManager = manager
                connectedCredentialId = credentialId
                break
        except:
            logger.debugException('')
            logger.debug('Can not connection by credential:', credentialId)
        finally:
            if connectionManager:
                connectionManager.closeClient()

    if connectionManager:
        logger.debug('Connected by credential Id:', connectedCredentialId)
        vec = ObjectStateHolderVector()
        hostOsh = modeling.createHostOSH(ip)
        appOsh = modeling.createApplicationOSH('running_software', 'UCS', hostOsh, vendor='Cisco')
        appOsh.setAttribute('application_ip', ip)
        appOsh.setAttribute('credentials_id', connectedCredentialId)
        vec.add(hostOsh)
        vec.add(appOsh)
        return vec
    else:
        if ucs_id:
            logger.debug('Delete the ucs since it can not be connected:%s' % ucs_id)
            softwareOsh = modeling.createOshByCmdbId('running_software', ucs_id)
            Framework.deleteObject(softwareOsh)

        logger.warn('All credentials have been tried. No credential can connect to UCS by ip %s' % ip)
        Framework.reportWarning('All credentials have been tried. No credential can connect to UCS by ip %s' % ip)