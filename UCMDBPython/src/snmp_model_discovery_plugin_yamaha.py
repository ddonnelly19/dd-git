__author__ = 'ustinova'

from snmp_model_discovery import *
import re


@Supported('YAMAHA_RTX1000')
class YAMAHA_RTX1000(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.1182.2.2.10.1.2'
        fw_oid = '1.3.6.1.4.1.1182.2.2.3.0'

        sn = ds = NOT_FOUND_IN_MIB

        conf = self.snmpWalk(sn_oid)
        if conf:
            for c in conf:
                sn_temp = regex('serial=[A-Z0-9]+', c[1])
                if sn_temp:
                    snt = regex('[A-Z0-9]+', sn_temp[0])
                    if snt:
                        sn = snt[0]

        k = self.snmpGetValue(fw_oid)
        if k:
            r = regex('Rev[. 0-9]*', k)

            if r:
                s = regex('[0-9][. 0-9]*', r[0])
                if s:
                    ds = s[0]

        model.SerialNumber.Chassis[0].SerialNumber = sn
        model.SerialNumber.Chassis[0].FirmwareRev = ds
