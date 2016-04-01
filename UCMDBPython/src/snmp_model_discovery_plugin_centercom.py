#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('AR320')
class AR320(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.207.8.4.4.5.2.1.3.1')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        v = self.snmpGetValue('1.3.6.1.4.1.207.8.4.4.5.2.1.5.1')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v


@Supported('CentreCOM_8216XL2', 'CENTERCOM_82xx_XL', 'CentreCOM_9006SX')
class CentreCOM_8216XL2(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        s_oid = '1.3.6.1.4.1.207.8.32.5.1.1.3.1'
        type = {
            "1": "at-8324",
            "2": "at-8316F",
            "3": "at-8224",
            "4": "at-8216F",
            "5": "at-9006",
            "6": "at-8216XL",
            "20": "other"
        }
        k = self.snmpGetValue(s_oid)
        if k:
            if k in type:
                model.SerialNumber.Chassis[0].Description = type[k]

            else:
                model.SerialNumber.Chassis[0].Description = k


@Supported('CENTRECOMFH824u')
class CENTRECOMFH824u(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        modelSN = model.SerialNumber
        serial_oid = '1.3.6.1.4.1.207.8.1.20.3.11.1.1.2.1.1.6.1,hexa'
        serialno = self.snmpGetValue(serial_oid)
        if serialno:
            modelSN.Chassis[0].SerialNumber = serialno
        else:
            modelSN.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        descriptions = {'1': 'fh824u', '2': 'fh812u', '3': 'eh3024a', '4': 'eh3012a'}
        k = self.snmpGetValue('1.3.6.1.4.1.207.8.1.20.3.11.1.1.2.1.1.2.1')
        if k:
            modelSN.Chassis[0].Description = descriptions.get(k, k)
        else:
            modelSN.Chassis[0].Description = NOT_FOUND_IN_MIB