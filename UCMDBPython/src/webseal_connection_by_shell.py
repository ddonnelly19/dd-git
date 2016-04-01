#coding=utf-8

import logger
import shellutils
import errormessages
import errorobject
import errorcodes
import modeling
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from pdadmin_shell_webseal_discoverer import WebSealShell
from java.lang import Exception as JException


def find_valid_credential(credential_ids, client, framework):
    webseal_shell = WebSealShell(framework, client, None)
    for credential_id in credential_ids:
        webseal_shell.webseal_credentials_id = credential_id
        try:
            webseal_shell.setup_command()
        except:
            logger.debugException('Failed to setup with error')
            continue
        try:
            if webseal_shell.get_output('server list'):
                return credential_id
        except (Exception, JException), e:
            logger.debugException('')

def reportWebSeal(host_id, credential_id):
    vector = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbId('node', host_id)
    websealOsh = ObjectStateHolder('isam_web')
    websealOsh.setContainer(hostOsh)
    websealOsh.setStringAttribute('discovered_product_name', 'IBM Security Access Manager')
    websealOsh.setStringAttribute('isam_credentials_id', credential_id)
    vector.add(hostOsh)
    vector.add(websealOsh)
    return vector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    host_id =  Framework.getDestinationAttribute('hostId')
    errorsList = []
    
    protocol = "ldap"
    credential_ids = Framework.getAvailableProtocols(ip, protocol)
    lastConnectedCredential = Framework.loadState()
    lastConnectedCredential and credential_ids.append(lastConnectedCredential)
    
    if not credential_ids:
        msg = errormessages.makeErrorMessage('webseal', pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, ['webseal'], msg)
        errorsList.append(errobj)
    
    client = Framework.createClient()
    credential_id = find_valid_credential(credential_ids, client, Framework)
        
    if credential_id:
        Framework.saveState(credential_id)
        OSHVResult.addAll(reportWebSeal(host_id, credential_id))
    else:
        Framework.clearState()
        msg = errormessages.makeErrorMessage('Shell', pattern=errormessages.ERROR_FAILED_TO_CONNECT_TO_SERVER)
        errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, ['webseal'], msg)
        errorsList.append(errobj)
        
    for errobj in errorsList:
        logger.reportErrorObject(errobj)
    
    return OSHVResult