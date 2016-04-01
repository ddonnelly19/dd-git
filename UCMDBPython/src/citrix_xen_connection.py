__author__ = 'gongze'
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from citrix_xen_models import Host

import modeling
import netutils
import logger
from citrix_xen_protocol import ConnectionManager


def DiscoveryMain(Framework):
    """
    @param Framework:
    @type Framework: com.hp.ucmdb.discovery.probe.services.dynamic.core.DynamicServiceFrameworkImpl
    @return:
    """
    vector = ObjectStateHolderVector()
    ip = Framework.getDestinationAttribute('ip_address')
    credentialId = Framework.getDestinationAttribute('credentialId')
    final_success = False
    try:
        credentials = netutils.getAvailableProtocols(Framework, 'http', ip)
        logger.debug('All http credentials to try:', credentials)
        if credentials:
            # if existing credential id, move it to the first one
            if credentialId and credentialId in credentials:
                credentials.remove(credentialId)
                credentials.insert(0, credentialId)
                logger.debug('Move existing credential to first one:', credentials)
            for creId in credentials:
                session = None
                try:
                    logger.debug('Try credential:', creId)
                    conn = ConnectionManager(Framework, ip, creId)
                    conn.validate()
                    logger.debug('Try login ...')
                    session = conn.getSession()
                    logger.debug('Login done, begin reporting related CIs')
                    host = Host.getAll(session)[0]
                    hostname = host.getHostName()
                    xen_server_osh = modeling.createHostOSH(ip, 'unix', None, hostname)
                    xen_server_osh.setStringAttribute('host_osinstalltype', 'XenServer')  # mark the unix as a XenServer
                    serialNumber = host.getSerialNumber()
                    if serialNumber:
                        xen_server_osh.setStringAttribute('serial_number', serialNumber)
                    virtual_osh = ObjectStateHolder('virtualization_layer')
                    virtual_osh.setStringAttribute('name', 'Citrix Xen Hypervisor')
                    virtual_osh.setStringAttribute('product_name', 'xen_hypervisor')
                    virtual_osh.setStringAttribute('application_ip', ip)
                    virtual_osh.setStringAttribute('credentials_id', conn.credentialsId)
                    virtual_osh.setContainer(xen_server_osh)
                    vector.add(virtual_osh)
                    vector.add(xen_server_osh)
                    final_success = True
                    break
                except:
                    logger.debugException('')
                finally:
                    if session:
                        try:
                            conn.closeSession()
                        except:
                            pass
        else:
            logger.warn('No http credential found for ip:', ip)
    except:
        logger.debugException('')
    if final_success:
        logger.debug('Success finally.')
    else:
        logger.debug('No Citrix Xen Server detected')
        Framework.reportWarning('No Citrix Xen Server detected')

    return vector