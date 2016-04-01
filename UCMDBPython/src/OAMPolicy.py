#coding=utf-8
import logger
from javax.xml.parsers import DocumentBuilderFactory
from java.io import ByteArrayInputStream
from java.lang import String
from javax.xml.xpath import XPathFactory, XPathConstants

import modeling
import netutils


class Resource(object):
    """
    OAM Resource
    """
    def __init__(self, name, protectionLevel, resourceURL):
        self.name = name
        self.protectionLevel = protectionLevel
        self.resourceURL = resourceURL

    def __repr__(self):
        return 'Resource(%s(%s): %s)' % (self.name, self.protectionLevel, self.resourceURL)


class Policy(object):
    """
    OAM Authentication and Authorization policy
    """
    def __init__(self, type, name, applicationDomainName, successRedirectURL, failureRedirectURL, resources):
        self.type = type
        self.name = name
        self.applicationDomainName = applicationDomainName
        self.successRedirectURL = successRedirectURL
        self.failureRedirectURL = failureRedirectURL
        self.resources = resources

    def add_resource(self, resource):
        if self.resources is None:
            self.resources = []
        self.resources.append(resource)

    def __repr__(self):
        return '%s(%s - applicationDomainName: %s, successRedirectURL: %s, failureRedirectURL: %s, resources: %s)' % (
            self.type or 'Policy', self.name, self.applicationDomainName, self.successRedirectURL,
            self.failureRedirectURL, self.resources)


def _buildDocumentForXpath(content, namespaceAware=1):
    r'@types: str, int -> org.w3c.dom.Document'
    xmlFact = DocumentBuilderFactory.newInstance()
    xmlFact.setNamespaceAware(namespaceAware)
    builder = xmlFact.newDocumentBuilder()
    return builder.parse(ByteArrayInputStream(String(content).getBytes()))


def _getXpath():
    r'@types: -> javax.xml.xpath.XPath'
    return XPathFactory.newInstance().newXPath()


def parse_oam_policy(policy_content):
    """
    Parse oam policy.xml to get oam policies
    :param policy_content:
    :return: list of oam policy
    :rtype: Policy
    """
    logger.debug('parse oam policy.xml')
    oam_policies = []
    root = _buildDocumentForXpath(policy_content, 0)
    xpath = _getXpath()
    policies = xpath.evaluate('//AuthenticationPolicy | //AuthorizationPolicy', root, XPathConstants.NODESET)
    for i in range(0, policies.getLength()):
        policy = policies.item(i)
        policy_type = policy.getNodeName()
        policy_name = xpath.evaluate('name', policy, XPathConstants.STRING)
        applicationDomainName = xpath.evaluate('applicationDomainName', policy, XPathConstants.STRING)
        successRedirectURL = xpath.evaluate('successRedirectURL', policy, XPathConstants.STRING)
        failureRedirectURL = xpath.evaluate('failureRedirectURL', policy, XPathConstants.STRING)
        oam_policy = Policy(
            policy_type, policy_name, applicationDomainName, successRedirectURL, failureRedirectURL, [])
        oam_policies.append(oam_policy)
        resources = xpath.evaluate('Resources/Resource', policy, XPathConstants.NODESET)
        for j in range(0, resources.getLength()):
            resource = resources.item(j)
            resource_name = xpath.evaluate('name', resource, XPathConstants.STRING)
            protectionLevel = xpath.evaluate('protectionLevel', resource, XPathConstants.STRING)
            resourceURL = xpath.evaluate('resourceURL', resource, XPathConstants.STRING)
            oam_resource = Resource(resource_name, protectionLevel, resourceURL)
            oam_policy.add_resource(oam_resource)
        logger.debug('find policy: %s' % oam_policy)
    return oam_policies


class RedirectPolicy(object):
    """
    Pair of resource url and redirect url
    """
    def __init__(self, resource_url, redirect_url):
        self.resource_url = resource_url
        self.redirect_url = redirect_url

    def __repr__(self):
        return "RedirectPolicy(resource: %s, redirect: %s)" % (self.resource_url, self.redirect_url)

    def __eq__(self, other):
        return self.resource_url == other.resource_url and self.redirect_url == other.redirect_url


def get_redirect_policies(policies):
    """
    Get list of resource url - redirect url pair
    :param policies: list of oam policy
    :return: list of resource url - redirect url pair
    :rtype: list of RedirectPolicy
    """
    redirect_policies = []
    for policy in policies:
        success_redirect_url = policy.successRedirectURL
        failure_redirect_url = policy.failureRedirectURL
        resources = policy.resources
        if success_redirect_url or failure_redirect_url:
            for resource in resources:
                resource_url = resource.resourceURL
                if resource_url and success_redirect_url:
                    redirect_policy = RedirectPolicy(resource_url, success_redirect_url)
                    if redirect_policy not in redirect_policies:
                        redirect_policies.append(redirect_policy)
                if resource_url and failure_redirect_url:
                    redirect_policy = RedirectPolicy(resource_url, failure_redirect_url)
                    if redirect_policy not in redirect_policies:
                        redirect_policies.append(redirect_policy)
    return redirect_policies

