import fptools
import ip_addr
r'''
Abstract class DnsDiscovererByShell has three methods
    listZones - list of zones owned by name server which we are connected to
    listRecords (domainName, recordTypes) - list of records for domain
    transferZone(zone, recordTypes) - list of all records for zone


There are two implementations of DNS discoverer for Windows platform and
for Unix-like OS.
Both use shell client.
To choose correct implementation use factory method createDiscovererByShell.

@author: vvitvitskiy
'''

import errorcodes
import errorobject
import logger
import dns
import re
import shell_interpreter
import netutils
from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector


RecordType = dns.ResourceRecord.Type


class DnsDiscoverer:
    def listZones(self):
        '''@types: -> seq[Zone]
        @raise ZoneListException: Failed zone listing'''
        raise NotImplementedError()

    def listRecords(self, domain, *types):
        '''@types: str, seq[str] -> seq[ResourceRecord]
        @raise DiscoveryException: Failed listing of records'''
        raise NotImplementedError()

    def transferZone(self, zone, *types):
        '''@types: Zone, seq[str] -> seq[ResourceRecord]
        @raise ZoneTransferException: Failed zone transfer'''
        raise NotImplementedError()


class DnsDiscovererByShell(DnsDiscoverer):
    'Base class for DNS discoverer by shell'
    def __init__(self, shell, dnsServerAddress):
        r'@types: shellutils.Shell, str'
        self.shell = shell
        self.nameServerAddress = dnsServerAddress
        self._onInit()

    def _onInit(self):
        r'template method for initialization'
        pass

    def _execCommand(self, cmd, timeout=0):
        r'@types: str, int -> tuple[int, str]'
        try:
            buffer = self.shell.execCmd(cmd, timeout)
            return (self.shell.getLastCmdReturnCode(), buffer)
        except JException, je:
            logger.error(je.getMessage())
            return (1, je.getMessage())


class WindowsDnsDiscovererByShell(DnsDiscovererByShell):
    r''' Registry key, nslookup command used to get all information,
    @note: Support for WMI is planned
    '''

    def listZones(self):
        '''@types: -> seq[Zone]
        @raise ZoneListException: if reg command execution failed

        @command: reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DNS Server\Zones"
        @commandOutput: HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DNS Server\Zones\ucmdb-ex.dot
        '''

        keypath = 'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\DNS Server\Zones'
        cmd = 'reg query "%s"' % keypath
        rc, buffer = self._execCommand(cmd)
        if rc != 0 or not buffer:
            raise dns.ZoneListException('Failed to obtain zone information', buffer)
        return self._parseRegZoneInfoOutput(buffer)

    def _parseRegZoneInfoOutput(self, buffer):
        zones = []
        for line in buffer.splitlines():
            if not line:
                continue
            i = line.strip().rfind("\\")
            if i != -1:
                name = line[i + 1:]
                try:
                    zones.append(dns.Zone(name.strip()))
                except ValueError, ve:
                    logger.warn("%s. Zone name: %s. " % (str(ve), name))
            else:
                logger.warn('Unexpected "reg" command output format: %s' % line)
        return zones

    def listRecords(self, domain, *types):
        '''@types: str, seq[str] -> seq[ResourceRecord]

        @command: nslookup -type=any <domain> <name server address>
        @commandOutput:

            domain1.domain.com  nameserver = domain2.domain1.domain.com
            domain1.domain.com
                    primary name server = domain2.domain1.domain.com
                    responsible mail addr = admin.domain1.domain.com
                    serial  = 231493
                    refresh = 900 (15 mins)
                    retry   = 600 (10 mins)
                    expire  = 86400 (1 day)
                    default TTL = 3600 (1 hour)
            dc05-2.domain1.domain.com   internet address = 144.43.98.22
        '''
        rc, output = self._execCommand('nslookup -type=any %s %s' % (domain, self.nameServerAddress))
        if rc != 0:
            raise dns.DiscoveryException("Failed command execution to list records for specified domain", output)
        return self._parseNslookupListDomainRecordsOutput(domain, output)

    def _parseNslookupListDomainRecordsOutput(self, domain, buffer):
        records = []
        primaryNameServer = adminMail = None
        for line in buffer.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            pattern = '^(.*?)\s+(%s|%s)\s+=\s+(.*?)$'
            atype = 'internet address'  # A type records
            nstype = 'nameserver'  # NS type record
            matchObj = re.match(pattern % (atype, nstype), line)
            if matchObj:
                (domainName, _type, cname) = matchObj.groups()
                _type = _type == nstype and RecordType.NS or RecordType.A
                try:
                    record = dns.ResourceRecord(domainName, _type, cname)
                    records.append(record)
                except ValueError, e:
                    e = str(e)
                    logger.warn("Failed to create record (%s). %s" % (line, e))
            else:  # SOA record
                soaRegexpPattern = '\s*(%s)\s*=\s*(.*?)$'
                #mark as primary name server
                matchObj = re.match(soaRegexpPattern % 'primary name server', line)
                if matchObj:
                    primaryNameServer = matchObj.group(2)
                    continue
                matchObj = re.match(soaRegexpPattern % 'responsible mail addr', line)
                if matchObj:
                    adminMail = matchObj.group(2)
                    continue
                # available attributes
                #ttl, expire, retry, serial, refresh
        if primaryNameServer:
            try:
                soaRecord = dns.SoaResourceRecord(domain, primaryNameServer,
                                                  adminMail)
                records.append(soaRecord)
            except ValueError, e:
                logger.warn("Failed to create SOA record. %s" % e)
        return records

    def transferZone(self, zone, *types):
        '''@types: Zone, seq[str] -> seq[ResourceRecord]
        @raise ZoneTransferException: if zone transfer failed

        @param types: if types are not specified - all type of records are accepted

        @command: (echo ls -d <domain>) | nslookup - <nameserver address> & echo.
        @commandOoutput:

         domain.hp.com.                NS     dc05.domain.hp.com
         domain.hp.com.                A      134.44.98.22
         _kerberos._tcp.bill._sites.dc._msdcs SRV    priority=0, weight=100, port=88, dc05.domain.hp.com
         ad-alhp                       A      134.44.98.114
         ad-delkin-win7EN-vm            AAAA   2002:862c:61ef::862c:61ef
         am-fs                          CNAME  fs-02.domain.hp.com

        '''
        cmd = '(echo ls -d %s) | nslookup - %s & echo.' % (zone.name, self.nameServerAddress)
        rc, buffer = self._execCommand(cmd)
        if rc != 0 or buffer.count("Can't list domain"):
            logger.error("Cannot transfer zone %s. %s" % (zone.name, buffer));
            raise dns.ZoneTransferException("Cannot transfer zone records", buffer)
        records = self._parseNslookupZoneTransferOutput(buffer)
        #if types are specified - filter records by specified types
        if types:
            records = filter(lambda r, types=types: r.type in types, records)
        return records

    def _parseNslookupZoneTransferOutput(self, buffer):
        records = []
        for line in buffer.strip().splitlines():
            if not line:
                continue
            matchObj = re.search("([^\s]+?)\.?"     # name excluding dot
                                 "\s+([^\s]+)\s+"   # record type
                                 "(.*)",            # value itself
                                 line)
            if matchObj:
                (name, _type, cname) = matchObj.groups()
                try:
                    record = dns.ResourceRecord(name, _type, cname.strip())
                    records.append(record)
                except ValueError, e:
                    logger.warn("Failed to create record (%s). %s" % (line, e))
        return records


class UnixDnsDiscovererByShell(DnsDiscovererByShell):
    r'''Configuration file parsing to find out information about owned zones
    and dig command
    '''

    def _onInit(self):
        self.__visitedConfigFiles = []

    def __obtainZonesFromNSConfigFiles(self, *paths):
        '''Find information about zones in configuration file
        @types: seq[str(path of config file]) -> seq[Zone]
        @command: cat <name server config file> | awk '/zone|include/ {print}'
        '''
        zones = []
        for path in paths:
            if not path or path in self.__visitedConfigFiles:
                continue
            #mark file as visited independently of result
            self.__visitedConfigFiles.append(path)

            logger.debug("process config file by path: %s" % path)
            rc, output = self._execCommand(r"""cat %s "
                                     "| awk '/zone|include/ {print}'""" % path)
            if rc == 0:
                for line in output.splitlines():
                    logger.debug(line)
                    matchObj = re.match("""zone\s+['"](.*?)['"]\s+""", line)
                    if matchObj:
                        try:
                            zones.append(dns.Zone(matchObj.group(1)))
                        except ValueError, ve:
                            logger.warn("Failed to create zone (%s). %s"
                                        % (line, ve))
                        continue
                    matchObj = re.match("""include\s+['"](.*?)['"]""", line)
                    if matchObj:
                        path = matchObj.group(1)
                        logger.debug("include file found: %s" % path)
                        zones.extend(self.__obtainZonesFromNSConfigFiles(path))
                if zones:
                    break
        return zones

    def __obtainConfigurationFromProcess(self):
        '''NS running process may contain path to folder where files of zones are
        located (-t flag) or path to the cofiguration file of name server (-c flag)
        Rude assumption that there is no spaces in the paths.

        @types: -> tuple(str(zone dire path) or None, str(configuration file path of named) or None)
        @command: ps -ef | grep named | awk '{for(i=11; i < NF; i++) {printf("%s ", $i)}printf("\n")}'
        '''
        zoneDirPath = None
        configFilePath = None

        cmd = (r"""ps -ef | grep named "
                "| awk '{for(i=11; i < NF; i++) {printf("%s ", $i)}printf("\n")}'""")
        rc, output = self._execCommand(cmd)
        if rc == 0 and output:
            for line in output.splitlines():
                tokens = re.split('\s+', line)
                #-t <value> is the location of files of zones
                if '-t' in tokens:
                    index = tokens.index('-t')
                    zoneDirPath = len(tokens) > index and tokens[index + 1]
                #-c <value> is the location of the name server config. file
                if '-c' in tokens:
                    index = tokens.index('-c')
                    configFilePath = len(tokens) > index and tokens[index + 1]
        return (zoneDirPath, configFilePath)

    def __obtainFeasibleRootDomainsByReversLookup(self):
        '''Guess root domain of zone by fetching domain names from the output
        of reverse lookup of name server IP
        @types: -> seq[str]
        @command: dig -x <name server address>
        '''
        digCmd = 'dig -x %s' % self.nameServerAddress
        records = self.__listRecordsByDig(digCmd,
                                          RecordType.NS,
                                          RecordType.SOA,
                                          RecordType.PTR)
        foundDomains = []
        # in resource record of specified type find domain which
        # can be root domain of zone
        for record in records:
            parentDomain = record.cname
            parentDomainIdx = parentDomain.find('.')
            while parentDomainIdx != -1:
                domain = parentDomain[parentDomainIdx + 1:]
                if domain in foundDomains:
                    parentDomainIdx = -1  # no need to check super-domain
                else:
                    foundDomains.append(domain.strip())
                    parentDomain = domain
                    parentDomainIdx = parentDomain.find('.')
        return foundDomains

    def __listRecordsByDig(self, digCmd, *types):
        '''@types: str, str, seq[str] -> seq[ResourceRecord]

        @command: dig <any kind of listing> | awk '/(A|CNAME)/{print $1, "\t", $4, "\t", $5}'
        @commandOutput:
        domain.hp.com.      NS      dc05-2.domain.hp.com.
        ;domain.hp.com.      NS      dc05-1.domain.hp.com.
        '''
        records = []

        typeFilter = types and '|'.join(types) or '.*?'
        filterCmd = r"""awk '/%s/{print $1, "\t", $4, "\t", $5}' """ % typeFilter
        rc, output = self._execCommand("%s | %s" % (digCmd, filterCmd))

        if not (rc == 0 and output) or output.count(digCmd):
            logger.warn(logger.prepareJythonStackTrace("Command failed"))
        else:
            records.extend(self._parseDigOutput(output))
            #filter records by specified types
            if types:
                records = filter(lambda r, types=types: r.type in types, records)
        return records

    def _parseDigOutput(self, buffer):
        records = []
        for line in buffer.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            matchObj = re.match("([^;].*?)\.?\s+(.*?)\s+(.*?)\.?$", line)
            if matchObj:
                (name, _type, cname) = matchObj.groups()
                try:
                    records.append(dns.ResourceRecord(name, _type, cname))
                except ValueError, e:
                    logger.warn("Failed to create record (%s). %s" % (line, e))
        return records

    def listZones(self):
        '''@types: -> seq[Zone]
        @raise ZoneListException'''

        zones = []
        #obtain name server configuration from process command line
        (zoneDirPath, configFilePath) = self.__obtainConfigurationFromProcess()
        #parsing configuration file to get zone names
        paths = [configFilePath, '/etc/named.conf', '/etc/namedb/named.conf']
        zones.extend(self.__obtainZonesFromNSConfigFiles(*paths))
        logger.debug("list of zones after config file processing: %s" % zones)
        if not zones:
            logger.warn("Zone configuration files are not found."
                        " Created zone for domain which NS belongs to")
            domains = self.__obtainFeasibleRootDomainsByReversLookup()
            if domains:
                zones.extend(map(dns.Zone, domains))
            else:
                raise dns.ZoneListException('Failed to obtain zone information')
        return zones

    def listRecords(self, domain, *types):
        '''List all records related to the <domain> of specified <types>
        @types: str, seq[str] -> seq[ResourceRecord]

        @command: dig @<name server address> <domain> ANY
        '''

        digCmd = r"""dig @%s %s ANY """ % (self.nameServerAddress, domain)
        records = self.__listRecordsByDig(digCmd, *types)
        if not records:
            raise dns.DiscoveryException("Failed list records for domain")
        return records

    def transferZone(self, zone, *types):
        ''' All records for <zone> of type in <types> will be transfered.
        @types: str, seq[str], bool -> seq[ResourceRecord]

        @raise ZoneTransferException: if failed to transfer zone
        @command: dig @<name server address> <domain> axfr
        '''

        digCmd = 'dig @%s %s axfr ' % (self.nameServerAddress, zone.name)
        records = self.__listRecordsByDig(digCmd, *types)
        if not records:
            raise dns.ZoneTransferException("Failed transfer zone resource records")
        return records


def createDiscovererByShell(shell, dnsServerAddress='localhost'):
    r'''Factory method for the proper discoverer implementation based on
    the provided shell type
    For Unix OS system variable PATH extended to include more wide range of
    commands (/usr/sbin)

    @types: shellutils.Shell, str -> DnsDiscoverer
    @param dnsServerAddress: hostname or IP address of DNS server
    '''
    cls = None
    if shell.isWinOs():
        cls = WindowsDnsDiscovererByShell
    else:
        environment = shell_interpreter.Factory().create(shell).getEnvironment()
        environment.appendPath('PATH', '/usr/sbin')
        cls = UnixDnsDiscovererByShell
    return cls(shell, dnsServerAddress)


class _MapWalker:
    ''''Contains helper method to process mapping of name to record according
    to some programmatical logic. For instance for provided alias find all
    referenced address records'''

    def __init__(self, nameToRecord):
        '@types: dict[str, ResourceRecord]'
        self.__map = nameToRecord
        #mark elements which have IPs
        self.__aliasToAddrRecord = {}
        #mark elements which have been visited
        self.__visited = {}

    def findAddressRecords(self, record):
        r''' For specified alias record find refered address records
        @types: ResourceRecord -> seq[ResourceRecord]'''
        # check cached values
        if record in self.__aliasToAddrRecord:
            return self.__aliasToAddrRecord[record]
        # leaf we are interested in
        if record.type == RecordType.A:
            return (record,)

        addresses = []
        if record.type == RecordType.CNAME:
            #mark record as visited
            self.__visited[record] = None
            #resolve canonical resource
            name = record.cname
            records = self.__map.get(name.lower())
            if not records:
                subDomainName = name[:name.find('.')]
                records = self.__map.get(subDomainName.lower()) or ()
            for r in records:
                #check for cycles or visited records
                if r not in self.__visited:
                    buffer = self.findAddressRecords(r)
                    if buffer:
                        addresses.extend(buffer)
                        self.__aliasToAddrRecord[r] = buffer
        return addresses


def _isIpInProbeRange(ip):
    '@types: str -> bool'
    return not netutils.DOMAIN_SCOPE_MANAGER.isIpOutOfScope(ip)


class ZoneTopology:
    r'Reporting related to combine zone and records in it'
    def __init__(self, zone):
        '@types: Zone -> ZoneTopology'
        assert zone
        self.zone = zone
        self.records = []


_isValidIp = fptools.safeFunc(ip_addr.IPAddress)


def reportTopologies(zoneTopologies, includeOutscopeIPs=0,
                     isBrokenAliasesReported=0):
    '@types: seq[ZoneTopology], bool, bool -> ObjectStateHolderVector'

    vector = ObjectStateHolderVector()
    zoneBuilder = dns.ZoneBuilder()
    reporter = dns.ResourceRecordReporter(dns.ResourceRecordBuilder())
    recordWithFqdn = dns.ResourceRecord.createRecordWithFqdn

    for topology in zoneTopologies:
        zone = topology.zone
        zoneOsh = zoneBuilder.buildZone(zone)
        vector.add(zoneOsh)

        # we can have several address records with the same name
        # - so value is the list
        nameToRecords = {}
        for record in topology.records:
            nameToRecords.setdefault(record.name.lower(), []).append(record)

        mapWalker = _MapWalker(nameToRecords)

        for records in nameToRecords.values():
            for record in records:
                #record type is an alias
                if record.type == RecordType.CNAME:
                    v = _reportAliasRecord(record, zone, zoneOsh, mapWalker,
                                           includeOutscopeIPs,
                                           isBrokenAliasesReported, reporter)
                    v and vector.addAll(v)
                #record type is an address
                elif (record.type in (RecordType.A, RecordType.AAAA)
                      and (_isIpInProbeRange(record.cname)
                           or includeOutscopeIPs)):
                    #build resource records with FQDN
                    record = recordWithFqdn(record, zone)
                    (ipOsh, recordOsh, vec) = reporter.reportAddressRecord(record, zoneOsh)
                    vector.addAll(vec)
    return vector


def _reportAliasRecord(record, zone, zoneOsh, mapWalker, includeOutscopeIPs,
                       isBrokenAliasesReported, reporter):
    r'''Report alias record with resolving refered record
    @types: dns.ResourceRecord, dns.Zone, ObjectStateHolder, _MapWalker, \
    bool, bool, dns.ResourceRecordReporter -> ObjectStateHolderVector
    '''
    alias = dns.ResourceRecord.createRecordWithFqdn(record, zone)
    aRecords = mapWalker.findAddressRecords(record)
    vec = None
    if aRecords:
        for aRecord in aRecords:
            #skip IPs that are out of bound of Probe range
            ip = aRecord.cname
            if (_isValidIp(ip)
                and (_isIpInProbeRange(ip)
                     or includeOutscopeIPs)):
                aRecord = dns.ResourceRecord.createRecordWithFqdn(aRecord, zone)
                (ipOsh, aRecordOsh, vec1) = reporter.reportAddressRecord(aRecord, zoneOsh)
                (aliasOsh, vec2) = reporter.reportAliasRecord(alias, aRecordOsh, zoneOsh)
                vec = vec1
                vec.addAll(vec2)
    elif isBrokenAliasesReported:
        refRecord = dns.ResourceRecord(record.cname, None, record.cname)
        refRecordOsh = reporter.reportRecord(refRecord, zoneOsh)
        (aliasOsh, vec) = reporter.reportAliasRecord(alias, refRecordOsh, zoneOsh)
    return vec


def discoverDnsZoneTopologies(dnsDiscoverer, zoneList, protocolName):
    r'''DnsDiscoverer, seq[str], str -> seq[_ZoneTopology]
    @note: make error reporting to the UI
    '''

    topologies = []
    try:
        zoneList = zoneList and map(dns.Zone, zoneList)
        zones = zoneList or dnsDiscoverer.listZones()
        isError = 0
        for zone in zones:
            if (dns.isLocalhostZone(zone)
                or dns.isReverseZone(zone)
                or dns.isRootZone(zone)):
                continue
            topology = ZoneTopology(zone)
            try:
                logger.debug('transfer zone: %s' % zone)
                types = (RecordType.A,      # IPv4 address
                         RecordType.CNAME,  # Alias
                         RecordType.AAAA)   # IPv6 address
                records = dnsDiscoverer.transferZone(zone, *types)
                topology.records.extend(records)
            except dns.DiscoveryException, dde:
                logger.warn('Failed to transfer zone "%s"' % zone)
                logger.debugException(str(dde))
                isError = 1
            else:
                topologies.append(topology)
        if isError:
            errCode = errorcodes.FAILED_TRANSFER_DNS_ZONE
            message = "Failed to transfer zone records for one or more zones"
            errobj = errorobject.createError(errCode, [protocolName], message)
            logger.reportWarningObject(errobj)
    except dns.ZoneListException, ex:
        logger.error("No zone found. %s" % str(ex))
        logger.reportError(str(ex))
    return topologies
