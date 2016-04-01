#coding=utf-8
import logger
import dns_discoverer
import dns
from dns_discoverer import DnsDiscoverer
import shellutils
from org.xbill.DNS import ZoneTransferIn, Lookup, Name, Type, NSRecord, Credibility, ExtendedResolver

from appilog.common.system.types.vectors import ObjectStateHolderVector 
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

class JavaDnsDiscoverer(DnsDiscoverer):
    def __init__(self, dnsServerAddress = None):
        if not isinstance(dnsServerAddress, list):
            dnsServerAddress = [dnsServerAddress]
        self.dnsServer = dnsServerAddress
        if dnsServerAddress:
            logger.info("Setting dns server to %s" % dnsServerAddress)
            Lookup.setDefaultResolver(ExtendedResolver(dnsServerAddress))
        
    def listZones(self):
        return DnsDiscoverer.listZones(self)
        

    def listRecords(self, domain, *types):
        ret = []
        lookup = Lookup(Name.fromString(domain.name), Type.ANY)
        lookup.setCredibility(Credibility.ANY)
        records = lookup.run() or []
        for record in records:
            ret.append(self._buildRecord(record))
        for alias in lookup.getAliases():
            ret.append(dns.ResourceRecord(domain.name, "CNAME", str(alias)))
        
        return ret
    
    def transferZone(self, zone, *types):
        ret = []
        nss = set()
        for dns in self.dnsServer:
            nss.add(dns)
        name = Name.fromString(zone.name)
        if zone.soa:
            nss.add(zone.soa)
        else:
            lookup = Lookup(name, Type.NS)
            lookup.setCredibility(Credibility.ANY)
            records = lookup.run() or []
            for record in records:
                if isinstance(record, NSRecord):
                    nss.add(record.getTarget().toString(True))
            
        for ns in nss: 
            try:
                logger.info("transferring zone %s from %s" % (name, ns))         
                xfr = ZoneTransferIn.newAXFR(name, ns, None);
                records  = xfr.run() or []
                for record in records:
                    ret.append(self._buildRecord(record))
                if ret:
                    return ret
            except:
                logger.warnException("error transferring zone %s from %s" % (name, ns))   
                pass
       
        return ret
    
    def _buildRecord(self, record):
        logger.info(record)
        recType = record.getType()
        if recType == Type.A or recType == Type.AAAA:
            return dns.createAddressRecord(str(record.getName()), record.getAddress().getHostAddress())
        elif recType == Type.SOA:
            return dns.SoaResourceRecord(str(record.getName()), str(record.getHost()), str(record.getAdmin()))
        elif recType == Type.CNAME or recType == Type.DNAME:
            return dns.ResourceRecord(str(record.getName()), Type.string(recType), str(record.getTarget()))
        else:
            return dns.ResourceRecord(str(record.getName()), Type.string(recType), str(record.getAdditionalName()))

def discoverDNS(dnsDiscoverer, zoneNameList):
    '''
    zoneList = set()           
    for domainName in zoneNameList:
        domainName = domainName.strip(".")
        names1 = domainName.split(".")
        names1.reverse()
        names = []
        for i in range(len(names1)):
            if names1[i].isdigit() or names1[i].find("ra01") > -1:
                break
            if len(names) == 0:
                names.append(names1[i])
            else:
                name = '%s.%s' % (names1[i], names[i-1])
                names.append(name)
                zoneList.add(name)
    '''
    topologies = dns_discoverer.discoverDnsZoneTopologies(dnsDiscoverer, zoneNameList, None, False)                  
    return dns_discoverer.reportTopologies(topologies, True, True)
                
def DiscoveryMain(Framework):
    zoneList = Framework.getTriggerCIDataAsList("domains") or []
    
    dnsDiscoverer = dns_discoverer.createDiscovererByShell(shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)))
    
    return discoverDNS(dnsDiscoverer, zoneList)


   
print(discoverDNS(JavaDnsDiscoverer(['192.168.12.2', '192.168.10.2']), ['herndon.pureintegration.com']).toXmlString())