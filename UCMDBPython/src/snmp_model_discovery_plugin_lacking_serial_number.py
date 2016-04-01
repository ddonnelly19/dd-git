# __author__ = 'gengt'

from snmp_model_discovery import *


@Supported('SUNOS_8072_3_2_3', 'FREEBSD', 'dlink_3224TGR', 'PEER_NETWORKS', 'DECSERVER700', 'CISCO_VPN_3000',
           'LANTRONIXMSS', 'LORAN_LMD', 'NETPORT_PS', 'STORAGEWK8-16', 'HPMSL', 'HPSureStore', 'ITOUCH_IR8020',
           'FLUKE_ANALYZER', 'DELL_E200', 't3COMLINKBUILDER', 'HP_FDDI', 'ALTEON_DIRECTOR_3', 'UBhub', 'AT3714',
           'ATTS_HUBS', 'Canon', 'IBM_BAD_MAC')
class SUNOS_8072_3_2_3(ModelDiscover):
    def discoverSerialNumber(self):
        self.add_lacking_serial_number()