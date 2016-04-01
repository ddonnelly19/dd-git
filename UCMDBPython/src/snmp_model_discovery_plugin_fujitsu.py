#__author__ = 'gengt'

from snmp_model_discovery import *


class FUJITSU_OPERTATION(ModelDiscover):
    def discoverSerialNumber(self):
        """
        sc2RemcsId    enterprises.231.2.10.2.2.10.2.3.1.15.1 = 00PMRGYRX100S4PGR1044AA###EFST748A00037#
            sc2RemcsId OBJECT-TYPE
            SYNTAX       DisplayString
            ACCESS       read-only
            STATUS       mandatory
            DESCRIPTION  "REMCS system identification string (binary data):
                Format of Fujitsu REMCS ID (40byte)
                    Format = TTMMMMMMMMMMMMmmmmmmmmmmmmCCnnnnnnnnnnnn
                    TT     :  2byte : Type ID for Company Name
                    MM...M : 12byte : Model Name
                    mm...m : 12byte : Device Name
                    CC     :  2byte : Checksum
                    nn...n : 12byte : Serial number"
                ::= { sc2Units 15 }
        """
        model = self.model
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        remcsid = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.10.2.3.1.15.1')
        if remcsid:
            serialno = remcsid[-12:].rstrip('#')
            if serialno != '':
                model.SerialNumber.Chassis[0].SerialNumber = serialno

            desc = remcsid[2:14]
            if desc != '':
                model.SerialNumber.Chassis[0].Description = desc
    
        kser = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.3.0')
        if kser:
            model.SerialNumber.Chassis[0].SerialNumber = kser
        kdesc = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.4.0')
        if kdesc:
            model.SerialNumber.Chassis[0].Description = kdesc


@Supported('FUJITSU_LINUX')
class FUJITSU_LINUX(FUJITSU_OPERTATION):
    pass

@Supported('FUJITSU_WIN')
class FUJITSU_WIN(FUJITSU_OPERTATION):
    def discoverMoreModelInfo(self):
        oid = '1.3.6.1.4.1.231.2.10.2.2.10.2.3.1.5.1'
        r = self.snmpGetValue(oid)
        if r:
            self.model.MiscInfo = "SRV:" + r
