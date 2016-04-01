#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('ARROWPOINT_CS')
class ARROWPOINT_CS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        description_types = {'0': 'ws100', '1': 'ws800', '2': 'ws150', '3': 'ws50', '4': 'unknown'}
        k = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.2.0')
        if k:
            model.SerialNumber.Chassis[0].Description = description_types.get(k, k)
        pn = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.3.0')
        if pn:
            model.SerialNumber.Chassis[0].PhysicalName = pn
        v = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.4.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        sr = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.9.0')
        if sr:
            model.SerialNumber.Chassis[0].SoftwareRev = sr
        hr0 = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.14.0')
        hr1 = self.snmpGetValue('1.3.6.1.4.1.2467.1.34.15.0')
        if hr0 or hr1:
            model.SerialNumber.Chassis[0].HardwareRev = 'Major:' + (hr0 or '') + ' ' + 'Minor:' + (hr1 or '')
        pn = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.4')
        r = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.5')
        k = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.3')
        sl = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.2')
        hr_major = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.8')
        hr_minor = self.snmpWalkValue('1.3.6.1.4.1.2467.1.34.16.1.9')
        description_types = {'0': 'scm', '1': 'sfm', '2': 'scfm', '3': 'fem-t1', '4': 'dual-hssi',
                             '5': 'fem', '6': 'fenic', '7': 'genic', '8': 'gem', '9': 'unknown'}
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = description_types.get(k[i], k[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
            if sl and i < len(sl) and sl[i]:
                if pn and i < len(pn) and pn[i]:
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = 'Slot ' + sl[i] + ' \\(' + pn[i] + '\\)'
                else:
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = 'Slot ' + sl[i]
            elif pn and i < len(pn) and pn[i]:
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = pn[i]
            if (hr_major and i < len(hr_major) and hr_major[i]) or (hr_minor and i < len(hr_minor) and hr_minor[i]):
                hrmajor = hr_major[i] if hr_major and i < len(hr_major) and hr_major[i] else ''
                hrminor = hr_minor[i] if hr_minor and i < len(hr_minor) and hr_minor[i] else ''
                model.SerialNumber.Chassis[0].Module[i].HardwareRev = 'Major:' + hrmajor + ' ' + 'Minor:' + hrminor
