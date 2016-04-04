import re
import ip_addr
from ip_addr import IPAddress
import socket
import logger
'''
Please, keep this module in "pure" Python as much as possible
Instead of JavaDnsResolver, use SocketDnsResolver
'''


class ResolveException(Exception):

    r'''Base exception class used for DNS resolving'''
    pass


_HOSTNAME_RESOLVE_EXCEPTION = ResolveException('Failed to resolve hostname')
_IP_RESOLVE_EXCEPTION = ResolveException('Failed to resolve IP')


class HostsFileDnsResolver(object):
    '''
    Uses remote's "hosts" file
    '''

    WINDOWS_HOSTS_CONFIG = '%SystemRoot%\system32\drivers\etc\hosts'
    UNIX_HOSTS_CONFIG = '/etc/hosts'

    def __init__(self, shell, hosts_filename=None):
        self.__shell = shell
        self.__set_hosts_filename(hosts_filename)

    def __set_hosts_filename(self, hosts_filename):
        self.__hosts_filename = hosts_filename
        if not self.__hosts_filename:
            if self.__shell.isWinOs():
                self.__hosts_filename = HostsFileDnsResolver.WINDOWS_HOSTS_CONFIG
            else:
                self.__hosts_filename = HostsFileDnsResolver.UNIX_HOSTS_CONFIG

    def resolve_ips(self, hostname):
        '''
        @types: str -> [ip_addr.IPAddress]
        @param hostname: the machine name to resolve IPs
        @return: list of IP addresses if resolved; empty list if not resolved
        '''
        return self.__resolve_ips_by_hosts_file(hostname)

    def resolve_hostnames(self, ip_string):
        raise NotImplementedError()

    def __resolve_ips_by_hosts_file(self, hostname):
        ip_objects = []
        if hostname:
            buffer = self.__get_hosts_file_contents()
            if buffer:
                for line in buffer.lower().split('\n'):
                    tokens = line.split()
                    if len(tokens) > 1:
                        if (self.__is_not_a_comment(tokens) and
                            self.__contains_hostname(tokens, hostname)):
                            try:
                                ip_obj = IPAddress(tokens[0])
                                valid = (not ip_obj.is_unspecified and
                                         not ip_obj.is_loopback)
                                if valid:
                                    ip_objects.append(ip_obj)
                            except ValueError:
                                pass
        return ip_objects

    def __is_not_a_comment(self, tokens):
        return tokens[0] != '#'

    def __contains_hostname(self, tokens, hostname):
        return hostname.lower() in tokens[1:]

    def __get_hosts_file_contents(self):
        buffer = self.__shell.safecat(self.__hosts_filename)
        if self.__shell.getLastCmdReturnCode() == 0:
            return buffer
        else:
            return None


class SocketDnsResolver(object):
    '''
    Uses dns resolver on the probe
    '''

    def __init__(self):
        pass

    def resolve_ips(self, hostname):
        '''
        @types: str -> [str]
        @param hostname: the machine name to resolve IPs
        @return: non-empty list of IP addresses
        @raise ResolveException: Failed to resolve
        '''
        return self.__resolve_ips_by_local_dns(hostname)

    def resolve_hostnames(self, ip_string):
        '''
        @types: str -> [str]
        @return: non-empty list of hostnames
        @raise ResolveException: Failed to resolve hostnames
        @raise ValueError: ip_string is not valid
        '''
        return self.__resolve_hostnames_by_local_dns(ip_string)

    def __resolve_hostnames_by_local_dns(self, ip_string):
        if not ip_addr.isValidIpAddress(ip_string):
            raise ValueError(ip_string + ' is not a valid address')
        try:
            hostname, aliaslist, _ = socket.gethostbyaddr(ip_string)
            if not hostname or hostname == ip_string:
                raise _HOSTNAME_RESOLVE_EXCEPTION
            return [hostname] + aliaslist
        except socket.herror:
            raise _HOSTNAME_RESOLVE_EXCEPTION

    def __resolve_ips_by_local_dns(self, hostname):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve IPs
        '''
        if not hostname:
            raise ValueError("hostname is not specified")
        ips = []
        for family in [socket.AF_INET, socket.AF_INET6]:
            try:
                ips += self.__resolve_ips_family(hostname, family)
            except socket.gaierror:
                pass
        if not ips:
            raise _IP_RESOLVE_EXCEPTION
        return ips

    def __resolve_ips_family(self, hostname, family):
        ips = []
        # returns an array of tuples (_, _, _, domain, (ip, port))
        addr_infos = socket.getaddrinfo(hostname, 0, family)
        for addr_info in addr_infos:
            ips += [IPAddress(addr_info[4][0])]
        return ips


class NsLookupDnsResolver(object):
    '''
    Uses nslookup command on destination
    '''

    def __init__(self, shell, dns_server=None):
        '''
        @param shell: the shell used to execute nslookup
        @param dns_server: the dns server used by nslookup
        '''
        self.__shell = shell
        self.__dns_server = dns_server or ''

    def resolve_ips(self, hostname):
        '''
        @types: str -> [str]
        @param hostname: the machine name to resolve IPs
        '''
        return self.__resolve_ips_by_nslookup(hostname)

    def resolve_ips_without_filter(self, hostname):
        '''
        @types: str -> [str]
        @param hostname: the machine name to resolve IPs
        '''
        return self.__resolve_ips_by_nslookup_without_filter(hostname)


    def resolve_hostnames(self, ip_string):
        '''
        @types: str -> [str]
        @param dnsName: the machine name to resolve IPs
        @raise ValueError: ip_string is not valid
        '''
        return self.__resolve_hostnames_by_nslookup(ip_string)

    def resolve_fqdn(self, hostname):
        '''
        @types: str -> str
        If can't resolve fqdn, returns hostname
        '''
        return self.__resolve_fqdn_by_nslookup(hostname)

    def __resolve_ips_by_nslookup(self, hostname):
        def _get_ip(buffer, hostname):
            if buffer is not None:
                matchPat = "Name:\s+%s(?:\.[\w\.-]+)?\s*Address(?:es)?:\s*([\d\.:a-z\,\s]+)" % re.escape(hostname)
                matched = re.search(matchPat, buffer, re.I)
                if not matched:
                    logger.debug('No name based match found. Checking Alias based match.')
                    matchPat = "Address(?:es)?:\s*([\d\.:a-z\,\s]+)Aliases:.+%s(?:\.[\w\.-]+)?\s*" % re.escape(hostname)
                    matched = re.search(matchPat, buffer, re.I | re.DOTALL)
                if matched:
                    rawAddr = matched.group(1).strip()
                    addrs = re.split('[,\s]+', rawAddr)
                    for addr in addrs:
                        addr = addr.strip()
                        if addr:
                            try:
                                ip_obj = ip_addr.IPAddress(addr)
                                valid = (not ip_obj.is_unspecified and
                                         not ip_obj.is_loopback)
                                if valid:
                                    ipAddressList.append(ip_obj)
                            except ValueError:
                                pass
            return ipAddressList

        ipAddressList = []
        buffer = self.__get_nslookup_result(hostname)
        if buffer is not None:
            ipAddressList = _get_ip(buffer, hostname)

            # If we cannot resolve the hostname, try canonical name, for example:
            # 127.0.0.1
            # Address:	127.0.0.1#53
            # Non-authoritative answer:
            # vhnatdf1db.hec.ngrid.net	canonical name = vhnatdf1db01.stl.hec.ngrid.net.
            # Name:	vhnatdf1db01.stl.hec.ngrid.net
            # Address: 10.29.121.4
            if not ipAddressList:
                logger.warn("Failed to resolve '%s', try canonical name" % hostname)
                canonical_name_pattern = "%s(?:\.[\w\.-]+)?\s*%s\s*\=\s*([^\.]*)(?:\.[\w\.-]+)?\s*" % (re.escape(hostname), re.escape('canonical name'))
                canonical_matched = re.search(canonical_name_pattern, buffer, re.I)
                if canonical_matched:
                    canonical_name = canonical_matched.group(1).strip()
                    ipAddressList = _get_ip(buffer, canonical_name)
        return ipAddressList

    def __resolve_ips_by_nslookup_without_filter(self, hostname):
        ipAddressList = []
        buffer = self.__get_nslookup_result(hostname)
        if buffer is not None:
            matchPat = "Name:\s+.+(?:\.[\w\.-]+)?\s*Address(?:es)?:\s*([\d\.:a-z\,\s]+)"
            matched = re.search(matchPat, buffer, re.I)
            if matched:
                rawAddr = matched.group(1).strip()
                addrs = re.split('[,\s]+', rawAddr)
                for addr in addrs:
                    addr = addr.strip()
                    if addr:
                        try:
                            ip_obj = ip_addr.IPAddress(addr)
                            valid = (not ip_obj.is_unspecified and
                                     not ip_obj.is_loopback)
                            if valid:
                                ipAddressList.append(ip_obj)
                        except ValueError:
                            pass
        return ipAddressList


    def __resolve_fqdn_by_nslookup(self, hostname):
        buffer = self.__get_nslookup_result(hostname)
        if buffer:
            nodeFQDN = hostname
            matchPat = ".*Name:\s+(" + re.escape(hostname) + "\S*)\s*"
            fqdnMatch = re.search(matchPat, buffer, re.S)
            if fqdnMatch:
                nodeFQDN = fqdnMatch.group(1).strip()
            return nodeFQDN

    def __resolve_hostnames_by_nslookup(self, ip_string):
        dns_names = []
        buffer = self.__get_nslookup_result(ip_string)
        if buffer is not None:
            matchPat = ".*Name:\s+(.*?)\n"
            dnsName = re.search(matchPat, buffer, re.S)
            if not dnsName:
                matchPat = ".*arpa\s+name\s*=\s*(.*?)\.\s*\n"
                dnsName = re.search(matchPat, buffer, re.S)
            if dnsName:
                dns_names.append(dnsName.group(1).strip())
        return dns_names

    def __get_nslookup_result(self, hostname):
        buffer = None
        if hostname:
            from shellutils import WinShell
            currentCodePage = WinShell.DEFAULT_ENGLISH_CODEPAGE
            try:
                if self.__shell.isWinOs():
                    currentCodePage = self.__shell.getCodePage()
                    if currentCodePage != WinShell.DEFAULT_ENGLISH_CODEPAGE:
                        self.__shell.setCodePage(WinShell.DEFAULT_ENGLISH_CODEPAGE)
            except:
                pass
            try:
                buffer = self.__shell.execCmd('nslookup %s %s' % (hostname, self.__dns_server), useCache=1)
                if buffer.find('can\'t find') != -1 or self.__shell.getLastCmdReturnCode() != 0:
                    buffer = None
            finally:
                try:
                    if self.__shell.isWinOs() and currentCodePage != WinShell.DEFAULT_ENGLISH_CODEPAGE:
                        self.__shell.setCodePage(currentCodePage)
                except:
                    pass
        return buffer


class FallbackResolver(object):
    '''
    Implementation of DNS resolving using fallback different resolvers
    '''

    def __init__(self, resolvers):
        '''
        resolvers a list of objects with interface implemented in:
        NsLookupDnsResolver, SocketDnsResolver or HostsFileDnsResolver
        '''
        self.__resolvers = resolvers

    def resolve_hostnames(self, ip_string):
        '''
        tries to resolve hostnames using each resolver

        @types: str -> [str]
        '''
        for resolver in self.__resolvers:
            try:
                hostnames = resolver.resolve_hostnames(ip_string)
                if hostnames:
                    return hostnames
            except ResolveException, re:
                logger.warn(str(re))
        raise _HOSTNAME_RESOLVE_EXCEPTION

    def resolve_ips(self, hostname):
        '''
        tries to resolve ips using each resolver

        @types: str -> [ip_addr.IPAddress]
        '''
        for resolver in self.__resolvers:
            try:
                ips = resolver.resolve_ips(hostname)
                if ips:
                    return ips
                logger.warn("Failed to resolve '%s' with %s" % (hostname,
                                                              resolver))
            except ResolveException, re:
                logger.warn(str(re))
        raise _IP_RESOLVE_EXCEPTION


def create(shell=None, local_shell=None, dns_server=None, hosts_filename=None):
    '''
    Creates fallback resolver having such order
    NsLookupDnsResolver for remote shell if provided
    NsLookupDnsResolver for local shell if provided
    SocketDnsResolver
    HostsFileDnsResolver for remote shell if provided
    HostsFileDnsResolver for local shell if provided
    @types: shellutils.Shell, shellutils.Shell, str, str -> FallbackResolver
    '''
    resolvers = []
    if shell:
        resolvers.append(NsLookupDnsResolver(shell, dns_server=dns_server))
    if local_shell:
        resolvers.append(NsLookupDnsResolver(local_shell, dns_server=dns_server))
    resolvers.append(SocketDnsResolver())
    if shell:
        resolvers.append(HostsFileDnsResolver(shell, hosts_filename=hosts_filename))
    if local_shell:
        resolvers.append(HostsFileDnsResolver(local_shell, hosts_filename=hosts_filename))

    return FallbackResolver(resolvers)
