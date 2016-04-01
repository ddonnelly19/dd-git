__author__ = 'yueyueys'

from snmp_model_discovery import *


class MiscModelDiscover(ModelDiscover):
    def add_resource(self, type, desc, sn, name, hw, fw, sw, mp, cp, unit):
        model = self.model
        if not model.total_resource:
            model.total_resource = 0
            tr = 0
        else:
            tr = model.total_resource

        model.ResourceList.Child[tr].Type = type
        model.ResourceList.Child[tr].Description = desc
        model.ResourceList.Child[tr].SN = sn
        model.ResourceList.Child[tr].Name = name
        model.ResourceList.Child[tr].HW = hw
        model.ResourceList.Child[tr].FW = fw
        model.ResourceList.Child[tr].SW = sw
        model.ResourceList.Child[tr].MountPoint = mp
        model.ResourceList.Child[tr].Capacity = cp
        model.ResourceList.Child[tr].Unit = unit

        model.total_resource += 1


@Supported('LIEBERT')
class LIEBERT(MiscModelDiscover):
    def discoverHostModelInformationList(self):
        # enterprises.emerson.liebertCorp.liebertGlobalProducts.lgpFoundation.lgpEnvironmental
        #.lgpEnvTemperature.lgpEnvTemperatureCelsius.lgpEnvTemperatureSettingDegC.0 = 20
        tempsetting_oid = '1.3.6.1.4.1.476.1.42.3.4.1.3.1.0'
        #.lgpEnvHumidity.lgpEnvHumidityRelative.lgpEnvHumiditySettingRel.0 = 35
        humsetting_oid = '1.3.6.1.4.1.476.1.42.3.4.2.2.1.0'

        #create temp and hum entries in serialnumber table...
        rv = self.snmpGetValue(tempsetting_oid)
        if rv:
            self.add_resource('misc', 'A/C temperature setting', '', '', '', '', '', '', rv, 'celsius')
        rv = self.snmpGetValue(humsetting_oid)
        if rv:
            self.add_resource('misc', 'A/C humidity setting', '', '', '', '', '', '', rv, 'percent')
