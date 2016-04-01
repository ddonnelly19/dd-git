#coding=utf-8
import netutils


from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.types.vectors import StringVector


class Protocol:
    SHORT = 'cim'
    FULL = 'cimprotocol'
    DISPLAY = 'CIM'


class CimCategory: 
    NO_CATEGORY = "No Category"


class CimNamespace:
    INTEROP = "root/interop"
    CIMV2 = "root/cimv2"
    


class ClientProperty:
    IP_ADDRESS = 'ip_address'
    CREDENTIALS_ID = 'credentialsId'
    NAMESPACE = 'cim_namespace'


class ProtocolProperty:
    CATEGORY = "cim_category"



def createCimOsh(ipAddress, containerOsh, credentialId, category=None):
    '''
    Builds a CIM OSH representing successful connection.
    @param ipAddress: string
    @param containerOsh: corresponding container OSH
    @param credentialId: protocol entry
    @raise ValueError: no credential or no IP.  
    @return: OSH
    '''
    if not credentialId:
        raise ValueError('CredentialsId must be set')
    if not netutils.isValidIp(ipAddress):
        raise ValueError('IP Address must be set')
    
    cimOsh = ObjectStateHolder('cim')
    cimOsh.setAttribute('data_name', Protocol.FULL)
    cimOsh.setAttribute('credentials_id', credentialId)
    cimOsh.setAttribute('application_ip', ipAddress)
    cimOsh.setContainer(containerOsh)
    
    if category:
        list_ = StringVector((category,))
        categoryAttribute = AttributeStateHolder('cim_category', list_)
        cimOsh.addAttributeToList(categoryAttribute)
    
    return cimOsh
