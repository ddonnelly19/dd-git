__author__ = 'yueyueys'

from snmp_model_discovery import *


@Supported('OID_0_0')
class OID_0_0(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        if regex('VxWorks', self.snmpStateHolder.desc):
            modelinfo = self.snmpGetValue('1.3.6.1.4.1.42.2.170.1.9.17.0')
            if modelinfo:
                model.MiscInfo = 'SRV:' + modelinfo
        else:
            model.MiscInfo = 'PSM:N/A 2003-02-15;PM:N/A 2003-02-15;PNBR:N/A 2003-02-15'