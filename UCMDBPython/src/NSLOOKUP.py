#coding=utf-8
from __future__ import with_statement

import logger
import modeling

from java.util import Properties
from java.lang import Exception as JException

from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.common.domainscope import DiscoveryDomainData
import shellutils
import dns_discoverer
import dns
from contextlib import closing
import dns_flow
import flow
import re
import string


@dns_flow.simple_connection_by_shell
def DiscoveryMain(framework, credsManager):
    config = (flow.DiscoveryConfigBuilder(framework)
              .dest_data_required_params_as_str('Protocol')
              .dest_data_params_as_str(
                    language=None)
              .bool_params(discoverUnknownIPs=False)
              .params(
                    DNSServerName=None,
                    DNSServerDomain=None,
              )).build()

    warnings = []
    with closing(_createClient(framework, config.Protocol)) as client:
        shell = shellutils.ShellFactory().createShell(client)

        dnsServerAddress = config.DNSServerName
        domain = config.DNSServerDomain
        if not (domain and dnsServerAddress):
            logger.info("DNS Server address or domain is not specified. "
                        "Determine automatically")
            dnsServerAddress, domain = getServerAndDomain(framework, client, config)

        discoverer = dns_discoverer.createDiscovererByShell(shell, dnsServerAddress)
        types = (dns.ResourceRecord.Type.A,)  # @UndefinedVariable
        records = discoverer.transferZone(dns.Zone(domain), *types)
        logger.info("Found %s records" % len(records))
        oshs = _reportHosts(records, config.discoverUnknownIPs)
        return oshs,  warnings
    return [], warnings


def _isLocalShellRequired(protocol):
    '@types: str -> bool'
    return protocol == 'discoveryprobegateway'


def _createClient(framework, protocol):
    '''
    @types: Framework, str -> Client
    @raise flow.ConnectionException
    '''

    codePage = framework.getCodePage()
    properties = Properties()
    properties.put(BaseAgent.ENCODING, codePage)

    LOCAL_SHELL = ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME
    try:
        client = (_isLocalShellRequired(protocol)
                  and framework.createClient(LOCAL_SHELL)
                  or framework.createClient(properties))
        return client
    except JException, je:
        raise flow.ConnectionException(je.getMessage())


_getDomainByIp = DomainScopeManager.getDomainByIp


def _reportHosts(records, discoverUnknownIPs):
    '@types: list[dns.ResourceRecord] -> list[osh]'
    oshs = []
    for record in records:
        hostOsh = None

        ip = record.cname
        probeDomain = _getDomainByIp(ip)
        if (not discoverUnknownIPs
            and probeDomain == DiscoveryDomainData.UNKNOWN_DOMAIN):
            logger.debug('Skipping out IP from domain that is unknown: ', ip)
        else:
            ipOsh = modeling.createIpOSH(ip)
            oshs.append(ipOsh)

            if probeDomain != DiscoveryDomainData.UNKNOWN_DOMAIN:
                hostOsh = modeling.createHostOSH(ip)
                oshs.append(hostOsh)
                oshs.append(modeling.createLinkOSH('containment', hostOsh, ipOsh))
    return oshs


def getServerAndDomain(framework, shellClient, config):
    ''' Determine DNS server address and domain name for the destination
    @types: Framework, BaseClient, flow.DiscoveryConfigBuilder.Result -> tuple
    @raise flow.DiscoveryException: Failed to determine DNS server address and domain name
    '''
    protocol = config.Protocol
    bundle = getLangBund(framework, config.language)
    output = _getDnsDetails(shellClient, protocol)
    dnsDetails = _parseDnsDetails(output, bundle)
    if not all(dnsDetails):
        _raiseFailedToDetermineDnsDetails(shellClient.getIpAddress())
    return dnsDetails


def _getDnsDetails(shellClient, protocol):
    output = ' '
    try:          
        if protocol in ('telnet', 'ssh'):
            output = shellClient.executeCmdWithTimeOut('nslookup -')#@@CMD_PERMISION shell protocol execution
            shellClient.executeCmdWithTimeOut('exit')#@@CMD_PERMISION shell protocol execution
        else:
            output = shellClient.executeCmdWithTimeOut('echo exit | nslookup')#@@CMD_PERMISION shell protocol execution
    except Exception, e:
        logger.warn(str(e))
        _raiseFailedToDetermineDnsDetails()
    return output


def _parseDnsDetails(output, bundle):
    ''' Parse DNS server address and domain to which domain belongs
    @types: str, LanguageBundle -> tuple[str, str]
    @raise flow.DiscoveryException: Failed to parse DNS server address and domain name
    '''
    regGlobalServerDomain1 = bundle.getString('global_reg_nslookup_server_and_domain1')
    regGlobalServerDomain2 = bundle.getString('global_reg_nslookup_server_and_domain2')
    logger.debug('regGlobalServerDomain1 ' + str(regGlobalServerDomain1))
    res = (re.search(regGlobalServerDomain1, output)
           or re.search(regGlobalServerDomain2, output))
    if res:
        dnsServerAddress, domainName = map(string.strip, res.groups())
        return dnsServerAddress, domainName
    _raiseFailedToDetermineDnsDetails()


def _raiseFailedToDetermineDnsDetails(address=None):
    ''' Helper function to raise flow.DiscoveryException with the same message
    @types: str?
    @raise flow.DiscoveryException:
    '''
    if address:
        logger.warn("Cannot retrieve nslookup data from %s" % address)
    raise flow.DiscoveryException("Failed to determine DNS server address"
                                  " and domain name")


def getLangBund(framework, language):
    '@types: Framework, str -> LanguageBundle'
    language = framework.getDestinationAttribute('language')
    env = framework.getEnvironmentInformation()
    return (language
            and env.getBundle('langNetwork', language)
            or env.getBundle('langNetwork'))
