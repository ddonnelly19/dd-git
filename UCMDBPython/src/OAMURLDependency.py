#coding=utf-8

import logger
import re

import errormessages
import errorcodes
import errorobject
import modeling
import netutils
import shellutils

from java.lang import String
from java.lang import Byte
from java.util import Properties
from java.net import InetSocketAddress
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.utils.zip import ChecksumZipper
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from OAMPolicy import parse_oam_policy, get_redirect_policies


def getunZippedContent(content):
    zipper = ChecksumZipper()
    zippedArray = content.split(',')
    zippedList = []
    for zippedByte in zippedArray:
        zippedList.append(Byte.parseByte(zippedByte))
    unzipBytes = zipper.unzip(zippedList)
    buffer = str(String(unzipBytes))
    return buffer


def find_matched_redirect_policies(context, policies):
    """
    Get the oam redirect policies whose resource url met the given context.
    """
    logger.debug('context: %s' % context)
    if context == '/' or context == '/*':
        context = '/.*'
    context = '^%s' % context if context[0] != '^' else context
    context = '%s$' % context if context[-1] != '$' else context
    pattern = re.compile(context)
    return [policy for policy in policies if pattern.match(policy.resource_url)]


def createHttpContextOsh(apacheOsh, webgateHttpContextOsh, uri, default_address, resultsVector):
    """
    Create Http Context under apache for the given uri.
    Create httpcontext.xml configuration document for Http Context.
    Create c-p link from webgate Http Context to the new Http Context
    """
    logger.debug('add oam uri to result vector: ', uri)

    uri_pattern = re.compile(r"^(?P<protocol>http|https)://(?P<ip>[\w\.\-]+)(:(?P<port>\d+))?(?P<root>/.*?)?$")
    match = uri_pattern.match(uri)
    if not match:
        if uri[0] != '/':
            uri = '/%s' % uri
        uri = 'http://%s%s' % (default_address, uri)
        logger.debug('use absolute uri: ', uri)
        match = uri_pattern.match(uri)
    if match:
        protocol = match.group('protocol')
        ip = match.group('ip')
        port = match.group('port')
        root = match.group('root') or '/'

        compositeKey = "_".join([root, ip, port or ''])
        logger.debug('compositeKey:', compositeKey)
        httpContextOsh = ObjectStateHolder('httpcontext')
        httpContextOsh.setAttribute('data_name', compositeKey)
        httpContextOsh.setAttribute('httpcontext_webapplicationcontext', root)
        if ip and netutils.isValidIp(ip):
            httpContextOsh.setAttribute('httpcontext_webapplicationip', ip)
        elif ip:
            httpContextOsh.setAttribute('httpcontext_webapplicationhost', ip)
        if protocol:
            httpContextOsh.setAttribute('applicationresource_type', protocol)

        httpContextOsh.setContainer(apacheOsh)
        contextConfigOsh = modeling.createConfigurationDocumentOSH('httpcontext.txt', '', uri, httpContextOsh)
        contextConfigLinkOsh = modeling.createLinkOSH('usage', httpContextOsh, contextConfigOsh)
        httpConfigCPLinkOsh = modeling.createLinkOSH('consumer_provider', webgateHttpContextOsh, httpContextOsh)
        resultsVector.add(httpContextOsh)
        resultsVector.add(contextConfigOsh)
        resultsVector.add(contextConfigLinkOsh)
        resultsVector.add(httpConfigCPLinkOsh)
    else:
        logger.debug('Skip invalid uri %s' % uri)
    return resultsVector


def addResultsToVector(resultsVector, ohsOsh, ohsContextOsh, matched_policies, default_address):
    for policy in matched_policies:
        createHttpContextOsh(ohsOsh, ohsContextOsh, policy.redirect_url, default_address, resultsVector)
    return resultsVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    policy_files = Framework.getTriggerCIDataAsList('POLICY_FILE')
    ohs_context = Framework.getTriggerCIData('OHS_CONTEXT')
    ohs_context_id = Framework.getTriggerCIData('OHS_CONTEXT_ID')
    ohs_id = Framework.getTriggerCIData('OHS_ID')
    ohs_address = Framework.getTriggerCIData('OHS_ADDRESS')

    ohsOsh = modeling.createOshByCmdbId('apache', ohs_id)
    ohsContextOsh = modeling.createOshByCmdbId('httpcontext', ohs_context_id)

    for policy_file in policy_files:
        policy_conent = getunZippedContent(policy_file)
        authorization_policies = parse_oam_policy(policy_conent)
        redirect_policies = get_redirect_policies(authorization_policies)
        matched_policies = find_matched_redirect_policies(ohs_context, redirect_policies)
        addResultsToVector(OSHVResult, ohsOsh, ohsContextOsh, matched_policies, ohs_address)

    return OSHVResult