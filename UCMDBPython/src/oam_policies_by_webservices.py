# coding=utf-8
import string
import re

import logger
import modeling
import xml.etree.ElementTree as ET
import errormessages
import errorcodes
import errorobject

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Properties
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from java.lang import Exception as JException
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.http.ApacheHttpClientWrapper import UnauthorizedException


APPDOMAIN = 'appdomain'
AUTHNPOLICY = 'authnpolicy'
AUTHZPOLICY = 'authzpolicy'
RESOURCE = 'resource'

# Tags used in XML
ROOT_TAG = 'Policies'
APPDOMAIN_TAG = 'ApplicationDomain'
AUTHNPOLICY_ROOT = 'AuthenticationPolicies'
AUTHNPOLICY_TAG = 'AuthenticationPolicy'
AUTHZPOLICY_ROOT = 'AuthorizationPolicies'
AUTHZPOLICY_TAG = 'AuthorizationPolicy'
SUCCESS_REDIRECT_URL_TAG = 'successRedirectURL'
FAILURE_REDIRECT_URL_TAG = 'failureRedirectURL'
RESOURCE_ROOT = 'Resources'
RESOURCE_TAG = 'Resource'


class PolicyBuilder:
    def __init__(self, ip, port, version, client):
        self.__ip = ip
        self.__port = port
        self.__version = version
        self.__client = client

    def _getService(self, service, appdomain='', id=''):
        domainFilter = ('?appdomain=' + appdomain.replace(' ', '%20')) if appdomain else ''
        idFilter = ('&id=' + id) if appdomain and id else ''
        url = 'http://%s:%s/oam/services/rest/%s/ssa/policyadmin/%s%s%s' % (self.__ip, self.__port, self.__version, service, domainFilter, idFilter)
        return self.__client.getAsString(url)

    def _getAppDomainNames(self):
        root = ET.fromstring(self._getService(service=APPDOMAIN))
        return [node.text for node in root.findall('.//ApplicationDomain/name')]

    def _buildResources(self, appdomain, resourceIds):
        resourceRoot = ET.Element(RESOURCE_ROOT)
        for id in resourceIds:
            resource = ET.Element(RESOURCE_TAG)
            root = ET.fromstring(self._getService(RESOURCE, appdomain, id))
            resource.append(root.find('.//name'))
            resource.append(root.find('.//protectionLevel'))
            resource.append(root.find('.//resourceURL'))
            resourceRoot.append(resource)
        return resourceRoot

    def _buildAuthnPolicies(self, appdomains):
        policyRoot = ET.Element(AUTHNPOLICY_ROOT)

        for appdomain in appdomains:
            root = ET.fromstring(self._getService(AUTHNPOLICY, appdomain))
            for node in root.findall('./AuthenticationPolicy'):
                policy = ET.Element(AUTHNPOLICY_TAG)
                policy.append(node.find('./name'))
                policy.append(node.find('./applicationDomainName'))

                successUrl = node.find('./successRedirectURL')
                if successUrl is not None:
                    policy.append(successUrl)
                else:
                    policy.append(ET.Element(SUCCESS_REDIRECT_URL_TAG))

                failureUrl = node.find('./failureRedirectURL')
                if failureUrl is not None:
                    policy.append(failureUrl)
                else:
                    policy.append(ET.Element(FAILURE_REDIRECT_URL_TAG))

                resourceIds = [resource.text for resource in node.findall('.//Resources/Resource') or []]
                policy.append(self._buildResources(appdomain, resourceIds))

                policyRoot.append(policy)

        return policyRoot

    def _buildAuthzPolicies(self, appdomains):
        policyRoot = ET.Element(AUTHZPOLICY_ROOT)

        for appdomain in appdomains:
            root = ET.fromstring(self._getService(AUTHZPOLICY, appdomain))
            for node in root.findall('./AuthorizationPolicy'):
                policy = ET.Element(AUTHZPOLICY_TAG)
                policy.append(node.find('./name'))
                policy.append(node.find('./applicationDomainName'))

                successUrl = node.find('./successRedirectURL')
                if successUrl is not None:
                    policy.append(successUrl)
                else:
                    policy.append(ET.Element(SUCCESS_REDIRECT_URL_TAG))

                failureUrl = node.find('./failureRedirectURL')
                if failureUrl is not None:
                    policy.append(failureUrl)
                else:
                    policy.append(ET.Element(FAILURE_REDIRECT_URL_TAG))

                resourceIds = [resource.text for resource in node.findall('.//Resources/Resource') or []]
                policy.append(self._buildResources(appdomain, resourceIds))

                policyRoot.append(policy)

        return policyRoot

    def createPolicyDoc(self):
        appDomainNames = self._getAppDomainNames()
        authnPolicyRoot = self._buildAuthnPolicies(appDomainNames)
        authzPolicyRoot = self._buildAuthzPolicies(appDomainNames)

        root = ET.Element(ROOT_TAG)
        root.append(authnPolicyRoot)
        root.append(authzPolicyRoot)

        return '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n' + ET.tostring(root)


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ip = Framework.getDestinationAttribute('ip_address')
    credential_id = Framework.getDestinationAttribute('credential_id')
    version = Framework.getDestinationAttribute('version')
    cmdb_id = Framework.getDestinationAttribute('cmdb_id')

    protocol = ProtocolManager.getProtocolById(credential_id)
    host = protocol.getProtocolAttribute('host')
    port = protocol.getProtocolAttribute('protocol_port')

    protocolName = ClientsConsts.HTTP_PROTOCOL_NAME

    if (host and ip != host) or not port:
        msg = errormessages.makeErrorMessage(protocolName, 'Invalid ip address or missing port in HTTP credential', pattern=errormessages.ERROR_OPERATION_FAILED)
        errobj = errorobject.createError(errorcodes.OPERATION_FAILED, [protocolName], msg)
        logger.reportErrorObject(errobj)
    else:
        props = Properties()
        props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credential_id)
        props.setProperty('autoAcceptCerts', 'true')
        props.setProperty('host', ip)

        try:
            httpClient = Framework.createClient(props)
            builder = PolicyBuilder(ip, port, version, httpClient)
            doc = builder.createPolicyDoc()

            oamServerOSH = modeling.createOshByCmdbIdString('running_software', cmdb_id)
            policyOSH = modeling.createConfigurationDocumentOSH('policy.xml', '', doc, oamServerOSH)
            linkOSH = modeling.createLinkOSH('composition', oamServerOSH, policyOSH)
            OSHVResult.add(oamServerOSH)
            OSHVResult.add(policyOSH)
            OSHVResult.add(linkOSH)
        except UnauthorizedException, e:
            msg = 'Failed to authenticate: ' + e.getMessage()
            errobj = errorobject.createError(errorcodes.INVALID_USERNAME_PASSWORD, [protocolName], msg)
            logger.reportErrorObject(errobj)
        except JException, e:
            msg = 'URL is not accessable: ' + e.getMessage()
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
            logger.reportErrorObject(errobj)
        finally:
            if httpClient is not None:
                httpClient.close()

    return OSHVResult