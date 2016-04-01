'''
Created on Sep 23, 2011

Temporary module
'''
import netutils
from sun.net.util import IPAddressUtil
import modeling
from appilog.common.system.types import ObjectStateHolder

def _isValidIp(ip):
    r'@types: str -> bool'
    return _isValidIpV4(ip) or _isValidIpV6(ip)

def _isValidIpV4(ip):
    r'@types: str -> bool'
    return netutils.isValidIp(ip)

def _isValidIpV6(ip):
    r'@types: str -> bool'
    if ip and ip.replace('0','') in ('::1','::'):
        return None
    return IPAddressUtil.isIPv6LiteralAddress(ip)

def _buildIp(ipAddress, netmask=None, dnsname=None, ipProps = None):
    r'@types: str, str, str, dict -> bool'
    if _isValidIpV4(ipAddress):
        return modeling.createIpOSH(ipAddress, netmask, dnsname, ipProps)
    elif _isValidIpV6(ipAddress):
        return _buildIpV6(ipAddress, netmask, dnsname, ipProps)
    raise ValueError("Invalid IP format %s" % ipAddress)

def _buildIpV6(ipAddress, netmask=None, dnsname=None, ipProps = None):
    r'@types: str, str, str, dict -> bool'
    if not _isValidIpV6(ipAddress):
        raise ValueError( "Receive IP Address that is invalid: %s" % ipAddress )
    domainName = '${DefaultDomain}'

    ipOsh = ObjectStateHolder("ip")
    ipOsh.setStringAttribute("ip_address", ipAddress)
    ipOsh.setStringAttribute("ip_domain", domainName)

    if dnsname:
        ipOsh.setStringAttribute("ip_dnsname", dnsname)
    return ipOsh
