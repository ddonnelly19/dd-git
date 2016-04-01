#coding=utf-8
import logger
import modeling
import netutils
import errormessages
import errorobject
import errorcodes

import cim
import cim_discover
import smis
import smis_discoverer

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException




def DiscoveryMain(Framework):
    warningsList = []
    errorsList = []
    vector = ObjectStateHolderVector()
    ip_address = Framework.getDestinationAttribute('ip_address')
    ip_domain = Framework.getDestinationAttribute('ip_domain')
    protocolName = cim.Protocol.DISPLAY
    
    credentials = netutils.getAvailableProtocols(Framework, cim.Protocol.FULL, ip_address, ip_domain)
    credentials = smis_discoverer.getSmisCredentials(credentials, Framework)
    if len(credentials) == 0:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        warningsList.append(errobj)
        logger.debug(msg)
    
    smisNamespaces = smis_discoverer.getSmisNamespaces(Framework)
    if not smisNamespaces:
        msg = errormessages.makeErrorMessage(protocolName, "No SMI-S namespaces found")
        errobj = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [cim.Protocol.DISPLAY, msg], msg)
        errorsList.append(errobj)
        logger.reportErrorObject(errobj)
        return vector
    
    for credential in credentials:
        testedNamespace = None
        for namespaceObject in smisNamespaces:
            try:
    
                testedNamespace = cim_discover.testConnectionWithNamespace(Framework, ip_address, credential, namespaceObject)
                break
            except JException, ex:
                msg = ex.getMessage()
                msg = cim_discover.translateErrorMessage(msg)
                errormessages.resolveAndAddToObjectsCollections(msg, protocolName, warningsList, errorsList)
            except:
                trace = logger.prepareJythonStackTrace('')
                errormessages.resolveAndAddToObjectsCollections(trace, protocolName, warningsList, errorsList)
        
        if testedNamespace is not None:
            hostOsh = modeling.createHostOSH(ip_address)
            smisOsh = cim.createCimOsh(ip_address, hostOsh, credential, smis.CimCategory.SMIS)
            smisOsh.setStringAttribute('application_category', 'Storage')
            vector.add(hostOsh)
            vector.add(smisOsh)
            warningsList = []
            errorsList = []
            break

    if vector.size() <= 0:
        Framework.clearState()
        if (len(warningsList) == 0) and (len(errorsList) == 0):
                msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_GENERIC)
                logger.debug(msg)
                errobj = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL, [protocolName], msg)
                errorsList.append(errobj)
    if errorsList:
        for errorObj in errorsList:
            logger.reportErrorObject(errorObj)
    if warningsList:
        for warnObj in warningsList:
            logger.reportErrorObject(warnObj)
    return vector