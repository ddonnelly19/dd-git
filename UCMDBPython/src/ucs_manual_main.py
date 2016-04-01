import ucs_pull_base

__author__ = 'gongze'
import logger
import netutils
import os

URL_LIST_FILE = 'ucs_url_list.conf'

import ucs_client
from ucs_connection_data_manager import FrameworkBasedConnectionDataManager
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

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


def getUCSURLs():
    mappingFileFolder = os.path.join(CollectorsParameters.BASE_PROBE_MGR_DIR,
                                     CollectorsParameters.getDiscoveryConfigFolder(),
                                     ucs_pull_base.MAPPING_CONFIG_FOLDER)
    ucsURLListFile = os.path.join(mappingFileFolder, URL_LIST_FILE)

    if not os.path.exists(ucsURLListFile):
        logger.error('UCS URL list file not found:', ucsURLListFile)
        return None

    listFile = open(ucsURLListFile)
    lines = listFile.readlines()
    lines = map(str.strip, lines)

    def validLine(line):
        return line and not line.startswith('#') and line.startswith('http')

    return filter(validLine, lines)


def discoverySingleUCS(Framework, url, credentialIds):
    for credentialId in credentialIds:
        logger.debug('Begin trying credential id:', credentialId)
        params = {'credentialsId': credentialId}
        tmpFramework = MyFramework(Framework, parameters=params)
        manager = FrameworkBasedConnectionDataManager(tmpFramework, url=url)
        try:
            client = manager.getClient()
            if client:
                logger.debug("UCS Connected on URL:", manager.getConnectionUrl)
                logger.debug("Begin discovery topology...")
                return ucs_pull_base.discovery(Framework, manager)
        except:
            logger.debugException('')
            logger.debug('Can not connection by credential:', credentialId)
        finally:
            if manager:
                manager.closeClient()
    else:
        logger.warn('All credentials have been tried. No credential can connect to UCS by url %s' % url)
        Framework.reportWarning('All credentials have been tried. No credential can connect to UCS by ip %s' % url)


def DiscoveryMain(Framework):
    credentialIds = netutils.getAvailableProtocols(Framework, 'ucs', None)
    if not credentialIds:
        logger.warn('No generic credential for UCS')
        Framework.reportWarning('No generic credential for UCS')
        return

    ucsURLList = getUCSURLs()
    if not ucsURLList:
        logger.error('UCS URL list file not found or Empty')
        Framework.reportError('UCS URL list file not found or Empty')
    else:
        for url in ucsURLList:
            logger.info('==========Begin working on:', url)
            resultVec = discoverySingleUCS(Framework, url, credentialIds)
            if resultVec:
                Framework.sendObjects(resultVec)
                Framework.flushObjects()
