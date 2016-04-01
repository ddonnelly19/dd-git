from snmp_model_discovery import *


@Supported('SIEMENS_RSB')
class SIEMENS_RSB(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        kser = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.3.0')
        kdesc = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.4.0')
        if kser and kdesc:
            model.SerialNumber2.Child[1].Type = 'chassis'
            model.SerialNumber2.Child[1].Description = trim(clean_nonprintable_characters(kdesc))
            model.SerialNumber2.Child[1].SN = trim(clean_nonprintable_characters(kser))
            model.MiscInfo = 'SRV:' + kdesc

        oser = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.10.0')
        odesc = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.12.0')
        if oser and odesc:
            model.SerialNumber2.Child[1].Child[1].Type = 'other'
            model.SerialNumber2.Child[1].Child[1].Description = 'Board:' + trim(clean_nonprintable_characters(odesc))
            model.SerialNumber2.Child[1].Child[1].SN = trim(clean_nonprintable_characters(oser))

        orev = self.snmpGetValue('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.11.0')
        if orev and orev != '-1':
            model.SerialNumber2.Child[1].Child[1].HW = trim(orev)