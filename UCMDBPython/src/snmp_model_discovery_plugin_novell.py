__author__ = 'yueyueys'

from snmp_model_discovery import *


@Supported('NOVELL_tcp')
class NOVELL_tcp(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # enterprises.novell.mibDoc.nwServer.nwSystem.nwSysServerName.0 = NW5TEST1
        #.1.3.6.1.4.1.23.2.28.1.1.0
        #enterprises.novell.mibDoc.nwServer.nwSystem.nwSysSerialNumber.0 = 30678b8b
        #.1.3.6.1.4.1.23.2.28.1.2.0
        #enterprises.novell.mibDoc.nwServer.nwSystem.nwSysOSDescription.0 = Novell NetWare 5.60.03
        #.1.3.6.1.4.1.23.2.28.1.9.0

        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_DEFINED_IN_MIB

        k = self.snmpGetValue('1.3.6.1.4.1.23.2.28.1.2.0')
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k

        k = self.snmpGetValue('1.3.6.1.4.1.23.2.28.1.9.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k