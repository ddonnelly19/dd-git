# coding=utf-8
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
import xml.etree.ElementTree as ET


SUPPORTED_OAM_VERSION = ('11.1.2.0.0',)

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
    def __init__(self, protocol, ip, port, version, client):
        self.__protocol = protocol
        self.__ip = ip
        self.__port = port
        self.__version = version
        self.__client = client

    def _getService(self, service, appdomain='', id=''):
        domainFilter = ('?appdomain=' + appdomain.replace(' ', '%20')) if appdomain else ''
        idFilter = ('&id=' + id) if appdomain and id else ''
        url = '%s://%s:%s/oam/services/rest/%s/ssa/policyadmin/%s%s%s' % (
            self.__protocol, self.__ip, self.__port, self.__version, service, domainFilter, idFilter)
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