#coding=utf-8
"""
DNS domain module
@author:  vvitvitskiy 05.2010
"""

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import entity
import modeling
import ip_addr


class _enum:
    def __init__(self, **kwargs):
        self.__dict = kwargs
        self.__dict__.update(kwargs)

    def values(self):
        return self.__dict.values()

    @staticmethod
    def createFromSeq(seq):
        r'''Create enumeration from sequence. Each item will be considered as
        entry (key, value) of the same value.
        @types: seq[str] -> _enum
        '''
        entries = {}
        for item in seq:
            entries[item] = item
        return _enum(**entries)

_RECORD_TYPE = _enum.createFromSeq(
                ("A NS MD MF CNAME SOA MB MG MR NULL WKS PTR HINFO MINFO "
                 "MX TXT RP AFSDB X25 ISDN RT NSAP NSAP-PTR SIG KEY PX "
                 "GPOS AAAA LOC NXT EID NIMLOC SRV ATMA NAPTR KX CERT A6 "
                 "DNAME SINK OPT APL DS SSHFP IPSECKEY RRSIG NSEC DNSKEY "
                 "DHCID NSEC3 NSEC3PARAM Unassigned HIP NINFO RKEY TALINK "
                 "SPF UINFO UID GID UNSPEC TKEY TSIG IXFR AXFR MAILB MAILA "
                 "URI CAA TA DLV Private use Reserved").split())


class DiscoveryException(Exception):
    def __init__(self, value, details=None):
        self.value = value
        self.details = details

    def __str__(self):
        return "%s. %s" % (repr(self.value), self.details or '')


class ZoneListException(DiscoveryException):
    pass


class ZoneTransferException(DiscoveryException):
    pass


class ResourceRecord(entity.Immutable):
    'DNS resource record'
    Type = _RECORD_TYPE

    def __init__(self, name, recordType, cname):
        '''@types: str, str, str
        @param cname: canonical name
        @raise ValueError: Resource record name is empty
        @raise ValueError: Record canonical name is empty
        @raise ValueError: Record type is not recognized
        '''
        if not name:
            raise ValueError("Resource record name is empty")
        if not cname:
            raise ValueError("Record canonical name is empty")
        if recordType and not recordType in _RECORD_TYPE.values():
            raise ValueError("Record type is not recognized")
        self.name = name
        self.cname = cname
        self.type = recordType

    @staticmethod
    def createRecordWithFqdn(record, zone):
        '@types: ResourceRecord, Zone -> ResourceRecord'
        if record and zone:
            if not record.name.endswith(zone.name):
                fqdn = "%s.%s" % (record.name, zone.name)
                return ResourceRecord(fqdn, record.type, record.cname)
        return record

    def __key(self):
        return (self.name, self.type, self.cname)

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return (isinstance(other, ResourceRecord)
                and hash(self) == hash(other))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return 'Record(%s, %s, %s)' % (self.name, self.type, self.cname)


def createAddressRecord(name, ip):
    r''' Create record object of type A with corresponding address validation
    @types: str, str -> ResourceRecord
    @raise ValueError: IP Address is not valid
    '''
    ip = ip_addr.IPAddress(ip)
    recordType = (ip.version == 4
                  and ResourceRecord.Type.A
                  or  ResourceRecord.Type.AAAA)
    return ResourceRecord(name, recordType, ip)


class SoaResourceRecord(ResourceRecord):
    'Resource record of SOA type'
    def __init__(self, domain, primaryNameServer, adminMail=None):
        r'@types: str, str, str'
        ResourceRecord.__init__(self, domain, self.Type.SOA, primaryNameServer)
        self.adminMail = adminMail


class Domain(entity.Immutable):
    'DNS domain'
    def __init__(self, domainName):
        r'''@types: str
        @raise ValueError: Name is not specified
        '''
        if not domainName:
            raise ValueError("Name is not specified")
        self.name = domainName

    def __repr__(self):
        return str(self.name)


class Zone(entity.Immutable):
    'DNS zone'
    def __init__(self, name):
        r'''@types: str
        @raise ValueError: Name is not specified
        '''
        if not name:
            raise ValueError("Name is not specified")
        self.name = name

    def __eq__(self, other):
        return (isinstance(other, Zone)
                and self.name == other.name
    )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return str(self.name)


def isReverseZone(zone):
    r'@types: Zone -> bool'
    return zone.name.find('.arpa') > 0


def isLocalhostZone(zone):
    r'@types: Zone -> bool'
    return zone.name == 'localhost'


def isRootZone(zone):
    r'@types: Zone -> bool'
    return zone.name == '.'


class ZoneBuilder:

    def buildZone(self, zone):
        '@types: Zone -> ObjectStateHolder'
        osh = ObjectStateHolder('dnszone')
        osh.setStringAttribute("data_name", zone.name.lower())
        return osh


def _getRecordTypeSet(model):
    r''' Get set of DNS record types declared in list dns_record_type
    @types: modeling.CmdbClassModel -> set[str]'''
    typeDef = model.getTypeDefinition('dns_record_type')
    iterator = typeDef.getValuesIterator()
    entries = set()
    while iterator.hasNext():
        entries.add(iterator.next().getListValue())
    return entries


class ResourceRecordBuilder:

    def __init__(self, classModel=modeling._CMDB_CLASS_MODEL):
        self._RECORD_TYPE_SET = _getRecordTypeSet(classModel)

    def buildRecord(self, record):
        '''@types: ResourceRecord -> ObjectStateHolder
        @raise ValueError: Unresolved record type
        '''
        osh = ObjectStateHolder('dns_record')
        osh.setStringAttribute("data_name", record.name.lower())
        if record.type:
            _type = record.type.upper()
            # validate record type against class model type enumeration
            if not _type in self._RECORD_TYPE_SET:
                raise ValueError("Unresolved record type")
            osh.setAttribute("type", _type)
        return osh


class ResourceRecordReporter:

    def __init__(self, builder):
        r'''@types: ResourceRecordBuilder
        @raise ValueError: Builder is not specified
        '''
        if not builder:
            raise ValueError("Builder is not specified")
        self.__builder = builder

    def reportRecord(self, record, zoneOsh):
        r'''@types: ResourceRecord, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: Record is not specified
        @raise ValueError: Zone OSH is not specified
        '''
        if not record:
            raise ValueError("Record is not specified")
        if not zoneOsh:
            raise ValueError("Zone OSH is not specified")
        osh = self.__builder.buildRecord(record)
        osh.setContainer(zoneOsh)
        return osh

    def reportAddressRecord(self, record, zoneOsh):
        r''' Report address `realization` link between `dns_record`
        and `ip_address`
        @types: ResourceRecord, ObjectStateHolder \
        -> tuple[ObjectStateHolder, ObjectStateHolder, ObjectStateHolderVector]
        @raise ValueError: Record is not specified
        @raise ValueError: Record is not of A type (address)
        @raise ValueError: Zone OSH is not specified
        @raise ValueError: Canonical name is not IP address
        @return: tuple of IP OSH, record OSH itself and resulted vector
        '''
        if not record:
            raise ValueError("Record is not specified")
        if not record.type in (ResourceRecord.Type.A,
                               ResourceRecord.Type.AAAA):
            raise ValueError("Record is not of A type (address)")
        if not zoneOsh:
            raise ValueError("Zone OSH is not specified")
        ipAddress = ip_addr.IPAddress(record.cname)
        ipOsh = modeling.createIpOSH(ipAddress)
        recordOsh = self.reportRecord(record, zoneOsh)
        vector = ObjectStateHolderVector()
        vector.add(modeling.createLinkOSH('realization', recordOsh, ipOsh))
        vector.add(ipOsh)
        vector.add(recordOsh)
        return (ipOsh, recordOsh, vector)

    def reportAliasRecord(self, alias, canonicalRecordOsh, zoneOsh):
        r'''@types: ResourceRecord, ObjectStateHolder, ObjectStateHolder\
         -> tuple[ObjectStateHolder, ObjectStateHolderVector]
        @raise ValueError: Alias record is not specified
        @raise ValueError: Alias record is not of CNAME type
        @raise ValueError: Referred record OSH is not specified
        @raise ValueError: Zone OSH is not specified
        '''
        if not alias:
            raise ValueError("Alias record is not specified")
        if not alias.type == ResourceRecord.Type.CNAME:
            raise ValueError("Alias record is not of CNAME type")
        if not canonicalRecordOsh:
            raise ValueError("Referred record OSH is not specified")
        if not zoneOsh:
            raise ValueError("Zone OSH is not specified")

        aliasOsh = self.reportRecord(alias, zoneOsh)
        vector = ObjectStateHolderVector()
        vector.add(modeling.createLinkOSH('realization', aliasOsh,
                                          canonicalRecordOsh))
        vector.add(aliasOsh)
        vector.add(canonicalRecordOsh)
        return (aliasOsh, vector)
