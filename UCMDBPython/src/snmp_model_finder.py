import re
from types import GeneratorType

import logger


SYS_OID = '1.3.6.1.2.1.1.2.0'
SYS_DESC = '1.3.6.1.2.1.1.1.0'
OID_TO_MODEL = {
    '0.0': ['OID_0_0'],
    '1.3.6.1.4.1.0.0.1': ['SNMP_001_PS'],
    '1.3.6.1.4.1.2.3.13': ['IBM_MVSO'],
    '1.3.6.1.4.1.2.3.37': ['IBM2212', 'IBM2212_REVERSE_ENDIAN'],
    '1.3.6.1.4.1.2.6.11': ['IBM_HOST'],
    '1.3.6.1.4.1.2.6.15': ['IBM8230'],
    '1.3.6.1.4.1.2.6.66.1.1.108': ['IBM8272'],
    '1.3.6.1.4.1.2.6.72': ['IBM2212'],
    '1.3.6.1.4.1.2.6.158.3': ['IBMBLDCOMM'],
    '1.3.6.1.4.1.2.6.158.5': ['IBMBLDCOMM'],
    '1.3.6.1.4.1.9.1.7': ['CISCO4K_Router'],
    '1.3.6.1.4.1.9.1.17': ['CISCO2500'],
    '1.3.6.1.4.1.9.1.23': ['CISCO2500'],
    '1.3.6.1.4.1.9.1.42': ['CISCO2516'],
    '1.3.6.1.4.1.9.1.44': ['CISCO1000'],
    '1.3.6.1.4.1.9.1.46': ['CISCO_7513'],
    '1.3.6.1.4.1.9.1.48': ['CISCO7K'],
    '1.3.6.1.4.1.9.1.49': ['CISCO1005'],
    '1.3.6.1.4.1.9.1.74': ['CISCO_async1'],
    '1.3.6.1.4.1.9.1.108': ['CISCO7206'],
    '1.3.6.1.4.1.9.1.109': ['CISCOAS5200'],
    '1.3.6.1.4.1.9.1.110': ['CISCO3640'],
    '1.3.6.1.4.1.9.1.122': ['CISCO3620'],
    '1.3.6.1.4.1.9.1.125': ['CISCO7K'],
    '1.3.6.1.4.1.9.1.147': ['FH316'],
    '1.3.6.1.4.1.9.1.148': ['FH316'],
    '1.3.6.1.4.1.9.1.150': ['FH316'],
    '1.3.6.1.4.1.9.1.151': ['FH316'],
    '1.3.6.1.4.1.9.1.162': ['CISCOAS5300'],
    '1.3.6.1.4.1.9.1.164': ['LS1010'],
    '1.3.6.1.4.1.9.1.168': ['CISCO5KRSM'],
    '1.3.6.1.4.1.9.1.177': ['FH316BMM'],
    '1.3.6.1.4.1.9.1.178': ['FH316BMM'],
    '1.3.6.1.4.1.9.1.185': ['CISCO2600_ARP'],
    '1.3.6.1.4.1.9.1.188': ['CISCOAS5800'],
    '1.3.6.1.4.1.9.1.211': ['CISCO_unknown_211'],
    '1.3.6.1.4.1.9.1.223': ['CISCO_unknown_223', 'CISCO2600_ARP'],
    '1.3.6.1.4.1.9.1.226': ['FH400'],
    '1.3.6.1.4.1.9.1.247': ['CISCO35xxXL'],
    '1.3.6.1.4.1.9.1.248': ['CISCO35xxXL'],
    '1.3.6.1.4.1.9.1.256': ['CISCO6MSM'],
    '1.3.6.1.4.1.9.1.257': ['CISCO5KRSM'],
    '1.3.6.1.4.1.9.1.258': ['CISCOMSFC'],
    '1.3.6.1.4.1.9.1.275': ['CISCO2948GL3'],
    '1.3.6.1.4.1.9.1.278': ['CISCO35xxXL'],
    '1.3.6.1.4.1.9.1.280': ['CISCO6K'],
    '1.3.6.1.4.1.9.1.282': ['CISCO6K'],
    '1.3.6.1.4.1.9.1.283': ['CISCO6K'],
    '1.3.6.1.4.1.9.1.287': ['CISCO3524'],
    '1.3.6.1.4.1.9.1.301': ['CISCOMSFC'],
    '1.3.6.1.4.1.9.1.323': ['CISCO2950'],
    '1.3.6.1.4.1.9.1.324': ['CISCO2950'],
    '1.3.6.1.4.1.9.1.325': ['CISCO2950'],
    '1.3.6.1.4.1.9.1.359': ['CISCO2950'],
    '1.3.6.1.4.1.9.1.366': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.367': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.368': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.380': ['CISCO350'],
    '1.3.6.1.4.1.9.1.391': ['CISCOPIX'],
    '1.3.6.1.4.1.9.1.417': ['CISCOPIX'],
    '1.3.6.1.4.1.9.1.429': ['CISCO2950'],
    '1.3.6.1.4.1.9.1.431': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.444': ['CISCO1721'],
    '1.3.6.1.4.1.9.1.448': ['CATALYST4K'],
    '1.3.6.1.4.1.9.1.449': ['CISCO6K'],
    '1.3.6.1.4.1.9.1.451': ['CISCOPIX'],
    '1.3.6.1.4.1.9.1.452': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.453': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.485': ['CISCO3550'],
    '1.3.6.1.4.1.9.1.516': ['CISCO37XX_SW'],
    '1.3.6.1.4.1.9.1.525': ['CISCO_AIRONET'],
    '1.3.6.1.4.1.9.1.557': ['CISCOMSFC'],
    '1.3.6.1.4.1.9.1.592': ['CISCOBLADE'],
    '1.3.6.1.4.1.9.1.653': ['CISCO_IDSM2'],
    '1.3.6.1.4.1.9.1.671': ['CISCO_ASA'],
    '1.3.6.1.4.1.9.5.1.3.1.1.2.223': ['CISCO_NAM'],
    '1.3.6.1.4.1.9.5.1.3.1.1.2.291': ['CISCO_NAM'],
    '1.3.6.1.4.1.9.5.7': ['CISCO5K'],
    '1.3.6.1.4.1.9.5.17': ['CISCO5K'],
    '1.3.6.1.4.1.9.5.18': ['CISCO1900'],
    '1.3.6.1.4.1.9.5.20': ['CISCO2820'],
    '1.3.6.1.4.1.9.5.23': ['CISCO3100'],
    '1.3.6.1.4.1.9.5.26': ['CISCO3001'],
    '1.3.6.1.4.1.9.5.28': ['CISCO1900'],
    '1.3.6.1.4.1.9.5.31': ['CISCO1900'],
    '1.3.6.1.4.1.9.5.34': ['CISCO5K'],
    '1.3.6.1.4.1.9.5.35': ['CISCO2926'],
    '1.3.6.1.4.1.9.5.36': ['CISCO5K'],
    '1.3.6.1.4.1.9.5.38': ['CISCOISL', 'CISCO6K'],
    '1.3.6.1.4.1.9.5.39': ['CISCOISL'],
    '1.3.6.1.4.1.9.5.40': ['CISCO4K'],
    '1.3.6.1.4.1.9.5.42': ['CISCO2948'],
    '1.3.6.1.4.1.9.5.44': ['CISCO6K'],
    '1.3.6.1.4.1.9.5.45': ['CISCO6K'],
    '1.3.6.1.4.1.9.5.46': ['CISCO4K'],
    '1.3.6.1.4.1.9.5.50': ['CISCO6K'],
    '1.3.6.1.4.1.9.5.175': ['CISCO1900'],
    '1.3.6.1.4.1.11.2.3.7.1.1': ['HP28673A'],
    '1.3.6.1.4.1.11.2.3.7.5.21': ['HP_J3303A'],
    '1.3.6.1.4.1.11.2.3.7.5.22': ['HP_J3303A'],
    '1.3.6.1.4.1.11.2.3.7.5.23': ['HP_J3303A'],
    '1.3.6.1.4.1.11.2.3.7.8.2.5': ['HP3210A'],
    '1.3.6.1.4.1.11.2.3.9.8.1.2': ['HPSureStore'],
    '1.3.6.1.4.1.11.2.51': ['HPStorageWorks'],
    '1.3.6.1.4.1.11.5.7.3.2': ['ILO_MP'],
    '1.3.6.1.4.1.11.10.2.1.3.7': ['HPMSL'],
    '1.3.6.1.4.1.11.10.2.1.3.25': ['HP_TAPE_AUTOLOADER'],
    '1.3.6.1.4.1.15.1.3.4': ['MICROANNEX'],
    '1.3.6.1.4.1.18.3': ['SYSTEM5000ROUTER'],
    '1.3.6.1.4.1.23.1.14.1': ['NOVELL_AGENT', 'NoByte', 'epson_printer'],
    '1.3.6.1.4.1.33.8.1.124.130': ['ITOUCH_IR8020', 'XYPLEX_TERM'],
    '1.3.6.1.4.1.35.1.1': ['ifSpeed_Mbps'],
    '1.3.6.1.4.1.36.2.15.1.6.2': ['dec_tcp_ip_fddi_service'],
    '1.3.6.1.4.1.36.2.15.2.3': ['COMPAQ_ALPHA', 'DEC_HOST'],
    '1.3.6.1.4.1.36.2.15.3.7.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.3.11.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.5.4.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.6.5.1': ['DECSERVER700'],
    '1.3.6.1.4.1.36.2.15.9.7.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.9.8.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.9.14.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.11.7.1': ['DEC900MODULE', 'MP_ROUTER'],
    '1.3.6.1.4.1.36.2.15.11.12.1': ['VNswitch', 'DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.11.13.1': ['VNswitch', 'DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.11.14.1': ['VNswitch', 'DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.11.17.1': ['DEC900MODULE'],
    '1.3.6.1.4.1.36.2.15.11.19.1': ['VNswitch'],
    '1.3.6.1.4.1.42': ['SUN_HOST'],
    '1.3.6.1.4.1.42.2.1.1': ['SUN_HOST'],
    '1.3.6.1.4.1.42.2.12.3.1.1': ['SUN_HOST'],
    '1.3.6.1.4.1.42.2.12.3.2.3': ['SUN_HOST'],
    '1.3.6.1.4.1.43.1.0.0': ['t3COMSWR400'],
    '1.3.6.1.4.1.43.1.4.22': ['T3COM_ppp'],
    '1.3.6.1.4.1.43.1.8.13': ['t3COMSSIIS1000', 't3COMSSIIS'],
    '1.3.6.1.4.1.43.1.8.22': ['t3COMSSIIS', 't3COMSSIIS3000'],
    '1.3.6.1.4.1.43.1.16.1.1.1.1': ['t3COMCB_3500_SN'],
    '1.3.6.1.4.1.43.1.16.2.2.1.2': ['t3COMSSIIS3900_36'],
    '1.3.6.1.4.1.43.1.16.2.2.2.1': ['t3COMSSIIS9300'],
    '1.3.6.1.4.1.43.10.27.4.1': ['t3COMSSPSHUB'],
    '1.3.6.1.4.1.43.10.27.4.1.1.1': ['t3COMSSDSHUB'],
    '1.3.6.1.4.1.43.10.27.4.1.2.1': ['t3COMSSIIS1100', 't3COMSSIIS'],
    '1.3.6.1.4.1.43.10.27.4.1.2.2': ['t3COMSSIIS', 't3COMSSIIS3300'],
    '1.3.6.1.4.1.43.10.27.4.1.2.4': ['t3COMSS3S4400', 't3COMSSIIS'],
    '1.3.6.1.4.1.43.10.27.4.1.2.5': ['t3COMSSIIS', 't3COMSS3S4900'],
    '1.3.6.1.4.1.43.10.27.4.1.2.10': ['t3COMSSIIS'],
    '1.3.6.1.4.1.43.10.27.4.1.2.11': ['t3COMSSIIS'],
    '1.3.6.1.4.1.45.3.13.1': ['SYSTEM5000HUB'],
    '1.3.6.1.4.1.45.3.21.1': ['SYSTEM5000HUB'],
    '1.3.6.1.4.1.45.3.22.1': ['BAYSTACK100'],
    '1.3.6.1.4.1.45.3.28.1': ['LATTICE28200'],
    '1.3.6.1.4.1.45.3.30.1': ['BAYSTACK350'],
    '1.3.6.1.4.1.45.3.30.2': ['BAYSTACK350'],
    '1.3.6.1.4.1.45.3.35.1': ['BAYSTACK450'],
    '1.3.6.1.4.1.45.3.40.1': ['BPS2000'],
    '1.3.6.1.4.1.45.3.43.1': ['BAYSTACK420'],
    '1.3.6.1.4.1.45.3.46.1': ['BAYSTACK470'],
    '1.3.6.1.4.1.45.3.65': ['NORTEL_SWITCH_5530'],
    '1.3.6.1.4.1.45.3.71.6': ['BAYSTACK100'],
    '1.3.6.1.4.1.49.2.3.7': ['t3COM5200M_MGT'],
    '1.3.6.1.4.1.49.2.3.8': ['t3COM5302M_MGT'],
    '1.3.6.1.4.1.52.3.9.1.10.7': ['CTRON_ELS100_S24TX2M'],
    '1.3.6.1.4.1.52.3.9.3.4.3': ['CTRON_REPEATER_V4'],
    '1.3.6.1.4.1.52.3.9.3.4.11': ['CTRON_REPEATER_V4'],
    '1.3.6.1.4.1.52.3.9.3.4.40': ['CTRON_REPEATER_V4'],
    '1.3.6.1.4.1.52.3.9.3.4.68': ['CTRON_2E4827R'],
    '1.3.6.1.4.1.52.3.9.3.4.80': ['CTRON_SSS2200'],
    '1.3.6.1.4.1.52.3.9.3.4.82': ['CTRON_SSS2200'],
    '1.3.6.1.4.1.52.3.9.3.4.84': ['CTRON_SSS2200'],
    '1.3.6.1.4.1.52.3.9.13.8': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.20.1.3': ['SSR_8000'],
    '1.3.6.1.4.1.52.3.9.20.1.4': ['SSR_8000'],
    '1.3.6.1.4.1.52.3.9.20.2.2': ['CTRONETHERNET', 'CTRONSS6000_MODULE'],
    '1.3.6.1.4.1.52.3.9.32.5.1': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.5.18': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.7': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.8': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.9': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.15': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.18': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.23': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.9.24': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.13.1': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.13.7': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.32.13.8': ['CTRONMMACPLUS'],
    '1.3.6.1.4.1.52.3.9.33.1.3': ['CTRON_SSR2100'],
    '1.3.6.1.4.1.72.8.4': ['RETIX4660'],
    '1.3.6.1.4.1.74.1.1': ['STARLAN10'],
    '1.3.6.1.4.1.74.1.1.0': ['STARLAN10'],
    '1.3.6.1.4.1.75.5.43.2': ['access4500_fddi_router'],
    '1.3.6.1.4.1.75.5.45.2': ['access4500_eth_router'],
    '1.3.6.1.4.1.75.5.80.1.1': ['UBhub'],
    '1.3.6.1.4.1.81.17.1.17': ['CAJUN_P330'],
    '1.3.6.1.4.1.89.1.1.62.2': ['RADWSD'],
    '1.3.6.1.4.1.89.1.1.62.5': ['NoByte'],
    '1.3.6.1.4.1.89.1.1.62.8': ['LINKPROOF_SWITCH'],
    '1.3.6.1.4.1.94.1.21.2.1.1': ['NOKIA_IP380'],
    '1.3.6.1.4.1.94.1.21.2.1.5': ['NOKIA_IP440'],
    '1.3.6.1.4.1.94.1.21.2.1.8': ['NOKIA_IP650'],
    '1.3.6.1.4.1.94.1.21.2.1.9': ['NOKIA_IP3XX'],
    '1.3.6.1.4.1.94.1.21.2.1.11': ['NOKIA_IP530'],
    '1.3.6.1.4.1.94.1.21.2.1.12': ['NOKIA_IP740'],
    '1.3.6.1.4.1.94.1.21.2.1.15': ['NOKIA_IP710'],
    '1.3.6.1.4.1.94.1.21.2.1.140': ['NOKIA_IP120'],
    '1.3.6.1.4.1.114.2.1.1.1.1.9': ['t3COMCB3500'],
    '1.3.6.1.4.1.116.3.10.1.3': ['Shiva'],
    '1.3.6.1.4.1.116.4.1.2': ['HITACHI_NP30'],
    '1.3.6.1.4.1.116.4.1.11.2': ['GR2000'],
    '1.3.6.1.4.1.116.4.25.1.3': ['GS4K'],
    '1.3.6.1.4.1.116.4.25.1.4': ['GS3K'],
    '1.3.6.1.4.1.119.1.0': ['ES100X112'],
    '1.3.6.1.4.1.119.1.14.2': ['NEC_ATM'],
    '1.3.6.1.4.1.119.1.14.8': ['NEC_ATM'],
    '1.3.6.1.4.1.119.1.14.9': ['NEC_ATM'],
    '1.3.6.1.4.1.119.1.25.14': ['MA25UX'],
    '1.3.6.1.4.1.119.1.25.15': ['ES100X112'],
    '1.3.6.1.4.1.119.1.25.19': ['ES100X'],
    '1.3.6.1.4.1.119.1.25.20': ['ES100X'],
    '1.3.6.1.4.1.119.1.25.21': ['ES100X'],
    '1.3.6.1.4.1.119.1.25.22': ['ES100X'],
    '1.3.6.1.4.1.119.1.40': ['NEC_PRINTER'],
    '1.3.6.1.4.1.119.1.50.3': ['ES100X112'],
    '1.3.6.1.4.1.119.1.50.11': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.50.12': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.50.16': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.79.1': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.79.3': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.79.4': ['NEC_IP8800'],
    '1.3.6.1.4.1.119.1.84.2.1': ['NEC_IX2010'],
    '1.3.6.1.4.1.119.1.84.2.2': ['NEC_IX2010'],
    '1.3.6.1.4.1.119.1.84.7.1': ['NEC_IX2010'],
    '1.3.6.1.4.1.119.1.126.43.3': ['NEC_VRP'],
    '1.3.6.1.4.1.122.5500.1.1': ['SONY_PCWA'],
    '1.3.6.1.4.1.128.2.2.2.2': ['Tektronix_Phaser_2'],
    '1.3.6.1.4.1.130.1.3': ['BANYAN_HOST'],
    '1.3.6.1.4.1.141.1.1.3210.2': ['DEC900MODULE'],
    '1.3.6.1.4.1.141.1.1.9200': ['NETSCOUT9200'],
    '1.3.6.1.4.1.141.1.1.9912': ['NETSCOUT9912ET'],
    '1.3.6.1.4.1.166.2.3': ['SHIVAROVER', 'DIALUPSWITCHES'],
    '1.3.6.1.4.1.166.2.8': ['DIALUPSWITCHES'],
    '1.3.6.1.4.1.166.2.9': ['DIALUPSWITCHES'],
    '1.3.6.1.4.1.166.2.11': ['DIALUPSWITCHES'],
    '1.3.6.1.4.1.166.6.101': ['NETSTRUCTURE'],
    '1.3.6.1.4.1.167.7.10.19.1.1': ['FN3524'],
    '1.3.6.1.4.1.171.10.9': ['dlink_eshub'],
    '1.3.6.1.4.1.171.10.10.1': ['d_link_printer'],
    '1.3.6.1.4.1.171.10.43.2': ['dlink_3224TGR'],
    '1.3.6.1.4.1.175.1.1.1.1.7': ['SUMITOMO_3500ME'],
    '1.3.6.1.4.1.175.1.1.14.1.5': ['SUMITOMO_2KLX'],
    '1.3.6.1.4.1.175.1.1.14.1.9': ['SUMITOMO_2000LX'],
    '1.3.6.1.4.1.181.1.13': ['ADCKENTROX'],
    '1.3.6.1.4.1.193.14.1': ['APX_HYBRID'],
    '1.3.6.1.4.1.197.2.5': ['CISCO3000'],
    '1.3.6.1.4.1.207.1.1.26': ['AR320'],
    '1.3.6.1.4.1.207.1.1.50': ['AT_AR410'],
    '1.3.6.1.4.1.207.1.2.1': ['AT3100_AT3600_HUBS', 'AT_36xxTR'],
    '1.3.6.1.4.1.207.1.2.2': ['AT_36xxTR'],
    '1.3.6.1.4.1.207.1.2.3': ['AT_36xxTR'],
    '1.3.6.1.4.1.207.1.2.4': ['AT_36xxTR'],
    '1.3.6.1.4.1.207.1.2.7': ['AT_36xxTR'],
    '1.3.6.1.4.1.207.1.2.65': ['ATTS_HUBS'],
    '1.3.6.1.4.1.207.1.4.10': ['CentreCOM_9006SX'],
    '1.3.6.1.4.1.207.1.4.20': ['CENTRECOM8008'],
    '1.3.6.1.4.1.207.1.4.25': ['CENTERCOM_82xx_XL'],
    '1.3.6.1.4.1.207.1.4.39': ['CENTERCOM_82xx_XL'],
    '1.3.6.1.4.1.207.1.4.63': ['CentreCOM_8216XL2'],
    '1.3.6.1.4.1.207.1.4.75': ['CentreCOM_8224SL'],
    '1.3.6.1.4.1.207.1.4.125.1.1': ['CG_MSW3'],
    '1.3.6.1.4.1.207.1.4.10001': ['ATOMIS3'],
    '1.3.6.1.4.1.207.1.10.1': ['CENTRECOMFH824u'],
    '1.3.6.1.4.1.207.1.10.2': ['CENTRECOMFH824u'],
    '1.3.6.1.4.1.211.1.127.4': ['LH16VA'],
    '1.3.6.1.4.1.211.1.127.18': ['fujitsu_Ex'],
    '1.3.6.1.4.1.211.1.127.24': ['FUJITSUEA1550'],
    '1.3.6.1.4.1.211.1.127.31': ['SR8800_5400'],
    '1.3.6.1.4.1.211.1.127.33': ['SR8800_5400'],
    '1.3.6.1.4.1.211.1.127.35': ['FUJITSU_LRX3050'],
    '1.3.6.1.4.1.211.1.127.110.1.1.5': ['FUJITSU_SH2510'],
    '1.3.6.1.4.1.211.1.127.110.1.1.23': ['FUJITSU_SH1630'],
    '1.3.6.1.4.1.211.1.127.113': ['FUJITEA1120'],
    '1.3.6.1.4.1.211.1.127.114.1.3.35.2': ['SH3440'],
    '1.3.6.1.4.1.211.1.127.115.1.1': ['FUJITSU_SH1631'],
    '1.3.6.1.4.1.211.1.127.116.1': ['LH1216VCA'],
    '1.3.6.1.4.1.211.1.127.116.2': ['LH1216VCA'],
    '1.3.6.1.4.1.211.1.127.118.10.1': ['FUJITSU_SH1816'],
    '1.3.6.1.4.1.211.1.127.118.11.1': ['FUJITSU_SH1824'],
    '1.3.6.1.4.1.211.1.127.118.13.1': ['FUJITSU_SH1816TF'],
    '1.3.6.1.4.1.211.1.127.118.40.1': ['FUJITSU_SH4124'],
    '1.3.6.1.4.1.211.1.127.118.43': ['FUJITSU_SH4124S'],
    '1.3.6.1.4.1.215.1.1.4.2.5': ['GeoStax24'],
    '1.3.6.1.4.1.215.1.1.4.2.4101': ['GeoStax24'],
    '1.3.6.1.4.1.236.11.5.1': ['SAMSUNG_PRINTER'],
    '1.3.6.1.4.1.253.8.62.1.1.20.1.3': ['XEROX_NC60'],
    '1.3.6.1.4.1.253.8.62.1.1.27.1.2': ['XEROX_NC60'],
    '1.3.6.1.4.1.253.8.62.1.2.3.2.1': ['XEROX_NC60'],
    '1.3.6.1.4.1.260.1.100': ['t3COMLBTRHUB'],
    '1.3.6.1.4.1.278.1.4.7.1.1.1.0': ['HCN7352'],
    '1.3.6.1.4.1.278.1.27.4': ['HITACHI_2024G'],
    '1.3.6.1.4.1.278.1.27.55': ['HITACHI_APRESIA'],
    '1.3.6.1.4.1.278.1.27.71': ['HITACHI_APRESIA'],
    '1.3.6.1.4.1.285.9.14': ['MADGE_CF860'],
    '1.3.6.1.4.1.295.6.1.1.1': ['WS9200'],
    '1.3.6.1.4.1.295.6.1.1.2': ['WS9200'],
    '1.3.6.1.4.1.297.1.11.93.1.18.3.1.1': ['FUJIXEROX_PRN1', 'BRAINTECH'],
    '1.3.6.1.4.1.297.1.11.93.1.19.5.1.1': ['FUJIXEROX_PRN1', 'BRAINTECH'],
    '1.3.6.1.4.1.297.4.2.1.1': ['FUJIXEROX_PRN1', 'NoByte'],
    '1.3.6.1.4.1.318': ['SMART_UPS'],
    '1.3.6.1.4.1.318.1.3.4.1': ['APC_MS'],
    '1.3.6.1.4.1.318.1.3.4.2': ['APC_MS'],
    '1.3.6.1.4.1.318.1.3.4.5': ['APC_MS'],
    '1.3.6.1.4.1.318.1.3.5.1': ['SMART_UPS'],
    '1.3.6.1.4.1.318.1.3.5.3': ['SMART_UPS'],
    '1.3.6.1.4.1.318.1.3.5.4': ['SMART_UPS'],
    '1.3.6.1.4.1.318.1.3.8.2': ['APC_ENV'],
    '1.3.6.1.4.1.322.1.8.3.2.1': ['LORAN_LMD'],
    '1.3.6.1.4.1.326.2.2': ['FORE_ASX'],
    '1.3.6.1.4.1.326.2.6.1.1': ['POWERHUBFORE_miscinfo', 'POWERHUBFORE'],
    '1.3.6.1.4.1.326.2.6.1.3': ['POWERHUBFORE'],
    '1.3.6.1.4.1.326.2.9.1.1.1': ['FORE_ES4810'],
    '1.3.6.1.4.1.343.2.4.5': ['NETPORT_PRINT_SERVER'],
    '1.3.6.1.4.1.343.2.4.12': ['NoByte', 'NETPORT_PS'],
    '1.3.6.1.4.1.343.5.1.6': ['INTEL510T'],
    '1.3.6.1.4.1.343.5.30': ['PRO2011'],
    '1.3.6.1.4.1.351.100': ['Stratacom'],
    '1.3.6.1.4.1.367.1.1': ['RICOH_PRINTER'],
    '1.3.6.1.4.1.368.1.1': ['NetHawk_PS'],
    '1.3.6.1.4.1.388.1.3': ['SPECTRUM'],
    '1.3.6.1.4.1.388.1.5': ['SPECTRUM'],
    '1.3.6.1.4.1.390.1.1': ['POWERHUB7000'],
    '1.3.6.1.4.1.429.2.9': ['USR_17SLOTS'],
    '1.3.6.1.4.1.442.1.1.1.9.0': ['PEER_NETWORKS'],
    '1.3.6.1.4.1.469.1000.1.6': ['INTERMEC_2001'],
    '1.3.6.1.4.1.469.1000.1.9': ['INTERMEC_2001'],
    '1.3.6.1.4.1.476.1.42': ['LIEBERT'],
    '1.3.6.1.4.1.480': ['QMS_printer'],
    '1.3.6.1.4.1.529.1.2.2': ['ASCEND'],
    '1.3.6.1.4.1.529.1.2.3': ['ASCEND_MAX2000'],
    '1.3.6.1.4.1.529.1.2.5': ['ASCEND_2'],
    '1.3.6.1.4.1.529.1.2.6': ['ASCEND'],
    '1.3.6.1.4.1.529.1.2.7': ['ASCEND_MAX6000'],
    '1.3.6.1.4.1.529.1.3.5': ['ASCEND_2'],
    '1.3.6.1.4.1.546': ['EMPIRE_MIB'],
    '1.3.6.1.4.1.551.2.1.74': ['AIRONET_AP2200E'],
    '1.3.6.1.4.1.551.2.1.76': ['AIRONET_AP2200E'],
    '1.3.6.1.4.1.551.2.1.77': ['AIRONET_BR500'],
    '1.3.6.1.4.1.551.2.1.86': ['AIRONET_UC2200E'],
    '1.3.6.1.4.1.551.2.1.123': ['WGB34X'],
    '1.3.6.1.4.1.551.2.1.124': ['WGB34X'],
    '1.3.6.1.4.1.562.3': ['NORTEL_CS1000'],
    '1.3.6.1.4.1.562.3.11.5': ['NORTEL_CS1000'],
    '1.3.6.1.4.1.562.3.21': ['NORTEL_CS1000'],
    '1.3.6.1.4.1.564.101.1': ['EL100'],
    '1.3.6.1.4.1.588.1': ['NoByte', 'WDAP'],
    '1.3.6.1.4.1.637.61.1': ['ASAM_637'],
    '1.3.6.1.4.1.664.1.219': ['ATLAS550'],
    '1.3.6.1.4.1.664.1.541': ['ADTRAN541'],
    '1.3.6.1.4.1.664.1.747': ['ADTRAN747'],
    '1.3.6.1.4.1.664.1.1123': ['ADTRAN1123'],
    '1.3.6.1.4.1.672.18.1.6': ['FLEXLAN_1'],
    '1.3.6.1.4.1.672.21.1.1': ['FLEXLAN_2'],
    '1.3.6.1.4.1.683.6': ['EXTENDNET100X'],
    '1.3.6.1.4.1.714.1.2.3': ['DELL_E200'],
    '1.3.6.1.4.1.714.1.2.6': ['WYSE_THIN_CLIENT'],
    '1.3.6.1.4.1.722.2.6.1': ['ZeroOne_PS'],
    '1.3.6.1.4.1.762.2': ['WAVEPOINT'],
    '1.3.6.1.4.1.800.3.1.1.1': ['XYLANOMNISWITCH'],
    '1.3.6.1.4.1.800.3.1.1.2': ['XYLANOMNISWITCH'],
    '1.3.6.1.4.1.800.3.1.1.3': ['XYLANOMNISWITCH'],
    '1.3.6.1.4.1.800.3.1.1.16': ['XYLANOMNISWITCH'],
    '1.3.6.1.4.1.838.5.1.1.0': ['ACCESS_POINT_100'],
    '1.3.6.1.4.1.848.1.5.1.1.1': ['STORAGEWK8-16'],
    '1.3.6.1.4.1.930.1.1': ['CENTILLION100'],
    '1.3.6.1.4.1.930.1.3': ['BAY301'],
    '1.3.6.1.4.1.930.1.4': ['SYSTEM5000SWITCH'],
    '1.3.6.1.4.1.1012.2.6.1.2': ['MARCONI_AXH600'],
    '1.3.6.1.4.1.1012.2.6.20.2': ['MARCONI_AXH1200'],
    '1.3.6.1.4.1.1019.2.1': ['KOMATSU_PRN_SRV'],
    '1.3.6.1.4.1.1019.2.1.1': ['KOMATSU_PRN_SRV'],
    '1.3.6.1.4.1.1022.9': ['TIMESTEP'],
    '1.3.6.1.4.1.1101.2.10.2': ['nu_switch'],
    '1.3.6.1.4.1.1182.1.23': ['YAMAHA_RTX1000'],
    '1.3.6.1.4.1.1226.1.3.1': ['FLUKE_ANALYZER'],
    '1.3.6.1.4.1.1347.41': ['KYOCERA_PRN'],
    '1.3.6.1.4.1.1347.43.5.1.1.1': ['KYOCERA_PRN'],
    '1.3.6.1.4.1.1548.2201.0': ['FLOWPOINT2200'],
    '1.3.6.1.4.1.1548.2210.0': ['FLOWPOINT_ATM'],
    '1.3.6.1.4.1.1569.2': ['MCKEXTENDER'],
    '1.3.6.1.4.1.1575.1.5': ['CMU_LINUX_AGENT'],
    '1.3.6.1.4.1.1602.1.5.1': ['NoByte', 'Canon'],
    '1.3.6.1.4.1.1602.4': ['NoByte', 'Canon'],
    '1.3.6.1.4.1.1602.4.2': ['NoByte', 'Canon'],
    '1.3.6.1.4.1.1602.4.7': ['NoByte', 'CANON_COLOR', 'Canon'],
    '1.3.6.1.4.1.1663.1.1.1.1.16': ['IBM_BLADE'],
    '1.3.6.1.4.1.1663.1.1.1.1.21': ['QLOGICBLADE'],
    '1.3.6.1.4.1.1723.2.1.3': ['LANTRONIX'],
    '1.3.6.1.4.1.1751.1.4.1': ['AP_1000'],
    '1.3.6.1.4.1.1751.1.4.2': ['WAVEPOINT_II'],
    '1.3.6.1.4.1.1751.1.4.5': ['AP_500'],
    '1.3.6.1.4.1.1751.1.4.6': ['AVAYA_AP3', 'AP_2000'],
    '1.3.6.1.4.1.1751.1.45.1': ['CAJUN_P550'],
    '1.3.6.1.4.1.1751.1.45.2': ['CAJUN_P550'],
    '1.3.6.1.4.1.1751.1.45.4': ['CAJUN_P220'],
    '1.3.6.1.4.1.1751.1.45.8': ['CAJUN_P550'],
    '1.3.6.1.4.1.1751.1.56.1.1.3': ['ALCATEL_LUCENT_VPNBRICK'],
    '1.3.6.1.4.1.1795.1.14.2.4.4.9': ['PARADYNE'],
    '1.3.6.1.4.1.1795.1.14.17.1.2': ['BITSTORM', 'Paradyne'],
    '1.3.6.1.4.1.1872.1.4': ['ALTEON_DIRECTOR_3'],
    '1.3.6.1.4.1.1872.1.6': ['ALTEON_DIRECTOR_3', 'ALTEON_D3_BLOB'],
    '1.3.6.1.4.1.1872.1.7': ['ALTEON_DIRECTOR_3'],
    '1.3.6.1.4.1.1872.1.10': ['ALTEON_DIRECTOR_4'],
    '1.3.6.1.4.1.1872.1.13.1.1': ['ALTEON_2424'],
    '1.3.6.1.4.1.1872.1.13.1.5': ['ALTEON_2208'],
    '1.3.6.1.4.1.1872.1.13.1.7': ['ALTEON_2424E'],
    '1.3.6.1.4.1.1872.1.13.1.9': ['ALTEON_2208E'],
    '1.3.6.1.4.1.1872.1.15': ['ALTEON_DIRECTOR_3'],
    '1.3.6.1.4.1.1872.1.18.1': ['NORTEL_SWITCH'],
    '1.3.6.1.4.1.1916.2.1': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.4': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.6': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.7': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.8': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.11': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.13': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.15': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.16': ['SUMMIT48_POLL', 'BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.17': ['ALPINE', 'BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.19': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.20': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.22': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.24': ['EXTREMEMSM64'],
    '1.3.6.1.4.1.1916.2.25': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.27': ['EXTREMEMSM64'],
    '1.3.6.1.4.1.1916.2.28': ['XTREMEBRIDGE'],
    '1.3.6.1.4.1.1916.2.30': ['EXTREMEPX1'],
    '1.3.6.1.4.1.1916.2.40': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.41': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.53': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.58': ['XTREMEBRIDGE', 'BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.62': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.93': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.111': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1916.2.112': ['BLACKDIAMOND'],
    '1.3.6.1.4.1.1991.1.1': ['SERVERIRON_SWITCH', 'SLB05003'],
    '1.3.6.1.4.1.1991.1.3.3.2': ['SERVERIRON_SWITCH'],
    '1.3.6.1.4.1.1991.1.3.6.2': ['FOUNDRY_IRONWARE', 'SERVERIRON_SWITCH'],
    '1.3.6.1.4.1.1991.1.3.7.2': ['FOUNDRY_IRONWARE', 'SERVERIRON_SWITCH'],
    '1.3.6.1.4.1.1991.1.3.21.1': ['FASTIRON4802', 'FOUNDRY_IRONWARE'],
    '1.3.6.1.4.1.1991.1.3.21.2': ['FASTIRON4802', 'FOUNDRY_IRONWARE'],
    '1.3.6.1.4.1.1991.1.3.25.1': ['FOUNDRY_FES2402'],
    '1.3.6.1.4.1.1991.1.3.30.2': ['FOUNDRY_IRONWARE', 'SERVERIRON_SWITCH'],
    '1.3.6.1.4.1.2011.2.78': ['HuaweiSwitch'],
    '1.3.6.1.4.1.2011.2.80.8': ['HuaweiSwitch'],
    '1.3.6.1.4.1.2011.10.1.44': ['HuaweiRouter'],
    '1.3.6.1.4.1.2021.250.3': ['UCD_LINUX_AGENT'],
    '1.3.6.1.4.1.2021.250.10': ['UCD_LINUX_AGENT'],
    '1.3.6.1.4.1.2021.250.255': ['UCD_WINDOWS'],
    '1.3.6.1.4.1.2154.1.1.1.2': ['ESX2400'],
    '1.3.6.1.4.1.2272.2': ['PASSPORT1100', 'ACCELAR'],
    '1.3.6.1.4.1.2272.7': ['ACCELAR'],
    '1.3.6.1.4.1.2272.8': ['ACCELAR'],
    '1.3.6.1.4.1.2272.30': ['PASSPORT8600'],
    '1.3.6.1.4.1.2272.31': ['PASSPORT8600'],
    '1.3.6.1.4.1.2272.32': ['PASSPORT8600'],
    '1.3.6.1.4.1.2272.34': ['PASSPORT8600'],
    '1.3.6.1.4.1.2334.1.1.4': ['PACKETSHAPER'],
    '1.3.6.1.4.1.2435.2.3.9.1': ['BROTHER_PRINTER'],
    '1.3.6.1.4.1.2467.4.1': ['ARROWPOINT_CS'],
    '1.3.6.1.4.1.2467.4.2': ['ARROWPOINT_CS'],
    '1.3.6.1.4.1.2467.4.3': ['ARROWPOINT_CS'],
    '1.3.6.1.4.1.2467.4.4': ['ARROWPOINT_CS'],
    '1.3.6.1.4.1.2505.5': ['NORTEL_ATI'],
    '1.3.6.1.4.1.2505.6': ['NORTEL_ATI'],
    '1.3.6.1.4.1.2636.1.1.1.2.2': ['CISCOM20'],
    '1.3.6.1.4.1.2636.1.1.1.2.31': ['JUNIPER'],
    '1.3.6.1.4.1.2636.1.1.1.2.32': ['JUNIPER'],
    '1.3.6.1.4.1.2636.1.1.1.2.35': ['JUNIPER'],
    '1.3.6.1.4.1.2636.1.1.1.2.40': ['JUNIPER'],
    '1.3.6.1.4.1.2745.1.4.2.2.1': ['INTLGNTMEDCVRT'],
    '1.3.6.1.4.1.2935': ['ADIC_SS'],
    '1.3.6.1.4.1.3003.2.2.2.1': ['OMNISWITCH_5052'],
    '1.3.6.1.4.1.3076.1.2.1.1.1.2': ['CISCO_VPN_3000'],
    '1.3.6.1.4.1.3076.1.2.1.1.2.1': ['CISCO_VPN_3000'],
    '1.3.6.1.4.1.3224.1.10': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.14': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.16': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.28': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.35': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.50': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.51': ['NETSCREEN'],
    '1.3.6.1.4.1.3224.1.53': ['NETSCREEN'],
    '1.3.6.1.4.1.3375.2.1.3.4.4': ['BIG_IP_Loadbalancer'],
    '1.3.6.1.4.1.3417.1.1.13': ['CACHEFLOW600'],
    '1.3.6.1.4.1.3764.1.10.10': ['ADIC_TAPELIB'],
    '1.3.6.1.4.1.3854.1.2.2.1.1': ['PROBE2'],
    '1.3.6.1.4.1.4068': ['ADCPATHWAY'],
    '1.3.6.1.4.1.4550': ['NEC_JEMA_UPS'],
    '1.3.6.1.4.1.4615.2.1': ['io_data_printer'],
    '1.3.6.1.4.1.5227.2': ['BUFFALO_LSM10_100_24'],
    '1.3.6.1.4.1.5227.16': ['MelcoBuffalo'],
    '1.3.6.1.4.1.5227.17': ['MelcoBuffalo'],
    '1.3.6.1.4.1.5624.2.1.3': ['CTRONSS6000_MODULE'],
    '1.3.6.1.4.1.5624.2.1.23': ['ENTERASYS_ER16'],
    '1.3.6.1.4.1.5624.2.1.30': ['ENTERASYS_RA_R2'],
    '1.3.6.1.4.1.5624.2.1.53': ['ENTERASYS_MXNS'],
    '1.3.6.1.4.1.5624.2.1.77': ['ENTERASYS_MXNS'],
    '1.3.6.1.4.1.5624.2.1.81': ['ENTERASYS_MX'],
    '1.3.6.1.4.1.5624.2.1.82': ['ENTERASYS_MX'],
    '1.3.6.1.4.1.5776.1': ['LSM10_100'],
    '1.3.6.1.4.1.5833.14.1': ['ULTRA_ACCESS'],
    '1.3.6.1.4.1.5912.1.1': ['JEMA_UPS'],
    '1.3.6.1.4.1.6027.1.3.7': ['FORCE10_S50NC'],
    '1.3.6.1.4.1.6411.2.1.1.1': ['SnapSNMP'],
    '1.3.6.1.4.1.6527.1.3.3': ['ALCATEL'],
    '1.3.6.1.4.1.6527.1.3.4': ['ALCATEL'],
    '1.3.6.1.4.1.6527.1.6.1': ['ALCATEL'],
    '1.3.6.1.4.1.6527.1.6.4': ['ALCATEL'],
    '1.3.6.1.4.1.6527.1.6.5': ['ALCATEL'],
    '1.3.6.1.4.1.6876.4.1': ['ESXi'],
    '1.3.6.1.4.1.6889.1.45.2': ['CAJUN_P550'],
    '1.3.6.1.4.1.6889.1.45.10': ['CAJUN_P550'],
    '1.3.6.1.4.1.7508': ['FUJI_ELECTRIC_JEMA_UPS'],
    '1.3.6.1.4.1.7779.1550.4.2.3.2': ['GRIDMASTER'],
    '1.3.6.1.4.1.8072.3.2.3': ['SUNOS_8072_3_2_3'],
    '1.3.6.1.4.1.8072.3.2.255': ['FREEBSD'],
    '1.3.6.1.4.1.10048': ['NEOWARE'],
    '1.3.6.1.4.1.10917.1': ['DATAMAX_PRINTER'],
    '1.3.6.1.4.1.12356.15.400': ['FORTIGATE'],
    '1.3.6.1.4.1.12356.15.1000': ['FORTIGATE'],
    '1.3.6.1.4.1.12962.2.2.4': ['NETAPP_DATAFORT'],
    '1.3.6.1.4.1.12962.2.4.1': ['NETAPP_DATAFORT'],
    '1.3.6.1.4.1.14360.1.1200': ['RMGC_MP1200'],
    '1.3.6.1.4.1.14685.1.3': ['DATAPOWER_XI50'],
    '1.3.6.1.4.1.16299.1.1.1': ['COREGA'],
    '1.3.6.1.4.1.16299.1.1.2': ['COREGA'],
    '1.3.6.1.4.1.16299.1.1.4': ['COREGA'],
    '1.3.6.1.4.1.25506.1.209': ['H3C_7506E'],
}

DESC_TO_MODEL = {
    'Cabletron SEHI Revision 1.10.04': ['CTRON_REPEATER_V4'],
    'Plaintree WaveBus Hub': ['WAVEBUS'],
}

OID_START_WITH_TO_MODEL = {
    '1.3.6.1.4.1.8072.3.2.10': ['LINUX_NET_SNMP'],
    '1.3.6.1.4.1.6889.1.69.1.': ['AVAYA_IPPHONE'],
    '1.3.6.1.4.1.6889.1.69.2.': ['AVAYA_IPPHONE_96XX'],
    '1.3.6.1.4.1.25506.1.': ['HuaweiRouter'],
    '1.3.6.1.4.1.1588.2.': ['BROCADE_FIBRE_CHANNEL'],
    '1.3.6.1.4.1.705.1.': ['MerlinGerinUPS'],
    '1.3.6.1.4.1.11.2.3.9.1': ['Brother'],
    '1.3.6.1.4.1.1701.1.1': ['KINNETICS'],
    '1.3.6.1.4.1.244.': ['LANTRONIXMSS'],
    '1.3.6.1.4.1.119.1.126.2.': ['NEC_VRP'],
    '1.3.6.1.4.1.3955.': ['LINKSYSHUB'],
    '1.3.6.1.4.1.494.': ['MADGE'],
    '1.3.6.1.4.1.2001.1.': ['MLET'],
    '1.3.6.1.4.1.449.': ['VANGUARD'],
    '1.3.6.1.4.1.50.1': ['ODE_ENC_CHASSIS'],
    '1.3.6.1.4.1.211.1.127.28': ['SB6400'],
    '1.3.6.1.4.1.1718.': ['SENTRYPWRBAR'],
    '1.3.6.1.4.1.16.1.6': ['TIMEPLEX_ROUTER'],
    '1.3.6.1.4.1.295.5.1.1': ['WS1K'],
    '1.3.6.1.4.1.33.8': ['XYPLEX_TERM'],
    '1.3.6.1.4.1.128.2.1.4': ['Tektronix_Phaser'],
    '1.3.6.1.4.1.52.3.9.20.2': ['CTRONSS6000_MODULE'],
    '1.3.6.1.4.1.52.3.9.20.1.1': ['CTRONSS6000_CHASSIS'],
    '1.3.6.1.4.1.2.6.98.1.1': ['IBM8271'],
    '1.3.6.1.4.1.789': ['NETAPP_HOST'],
    '1.3.6.1.4.1.318.1.3.2.': ['SMART_UPS'],
    '1.3.6.1.4.1.534.2.5.1': ['POWERWARE_UPS'],
    '1.3.6.1.4.1.674.10895.': ['DELL_SWITCH'],
    '1.3.6.1.4.1.1536.3.3.': ['Canon'],
    ('1.3.6.1.4.1.231.1.17.2', '1.3.6.1.4.1.231.1.17.1'): ['SIEMENS_RSB'],
    ('1.3.6.1.4.1.297.', '1.3.6.1.4.1.1602.'): ['NoByte'],
    ('1.3.6.1.4.1.1795.1.14.9.8', '1.3.6.1.4.1.1795.1.14.2.4.4.1', '1.3.6.1.4.1.1795.1.14.2.2.4',
     '1.3.6.1.4.1.1795.1.14.2.4.3.3', '1.3.6.1.4.1.1795.1.14.2.4.1.1'): ['Paradyne'],
}

DESC_REGEX_TO_MODEL = {
    '3Com CB5000 Advanced Distributed Management Module': ['t3COMCB5000'],
    '3Com CoreBuilder-9000 Enterprise Management Engine': ['t3COMCB9000'],
    'Model: Corebuilder 9000-': ['CB9000MOD'],
    '2900XL': ['CISCO2900'],
    'NBase Switch NH2016 Version': ['BROKEN_NBASE'],
    'Orion 4000 Broadband Access Mux': ['ORION'],
    'Gandalf Access Hub': ['Gandalf_Access_Hub'],
    'Bay Networks, Inc. BayStack 310': ['BAY303_310'],
    'Bay Networks, Inc. BayStack 303': ['BAY303_303'],
}


def is_offspring(child, parent):
    child = OID(child)
    parent = OID(parent)
    return child != parent and child.startswith(parent)


class OID(object):
    def __init__(self, *oid):
        super(OID, self).__init__()
        oid = map(lambda x: x.strip('.'), oid)
        self.oidStr = '.'.join(oid)
        self.pureOid = self.oidStr
        self.dataType = None
        if ',' in self.oidStr:
            comma = self.oidStr.index(',')
            self.pureOid = self.oidStr[:comma].strip()
            self.dataType = self.oidStr[comma + 1:].strip()
        if self.dataType:
            self.oidStr = self.pureOid + ',' + self.dataType


    def __eq__(self, other):
        return self.oidStr == other.oidStr

    def __str__(self):
        return self.oidStr

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return str(self).__hash__()

    def last(self):
        return self.pureOid.split('.')[-1]

    def size(self):
        return len(self.pureOid.split('.'))

    def serials(self):
        return self.pureOid.split('.')

    def intSerials(self):
        return map(int, self.pureOid.split('.'))

    def startswith(self, that):
        thatSerial = that.serials()
        thisSerial = self.serials()
        if len(thatSerial) < len(thisSerial):
            for i in range(0, len(thatSerial)):
                if thatSerial[i] != thisSerial[i]:
                    return False
            return True
        return False

    def value(self):
        return self.oidStr

    def getISOFormat(self):
        return '.' + self.value()

    def __lt__(self, other):
        return self.intSerials() < other.intSerials()

    def __gt__(self, other):
        return not self.__lt__(other) and not self.__eq__(other)

    @classmethod
    def normalize(cls, oid):
        return str(oid).lstrip('.')


class JayObject(object):
    def __init__(self):
        self._map = {}

    def __is_internal_attr(self, item):
        return item in ['_map']

    def __getattr__(self, item):
        if self.__is_internal_attr(item):
            return super(JayObject, self).__getattribute__(item)
        else:
            return self.__getitem__(item)

    def __setattr__(self, name, value):
        if self.__is_internal_attr(name):
            return super(JayObject, self).__setattr__(name, value)
        else:
            self.__setitem__(name, value)
            return value

    def keys(self):
        keys = self._map.keys()

        def validJay(key):
            value = self.__getattr__(key)
            if isinstance(value, JayObject):
                return bool(value)
            return True

        keys = filter(validJay, keys)
        return keys

    def values(self):
        validKeys = self.keys()
        return [self.getAttr(x) for x in validKeys]

    def hasAttr(self, attr):
        return attr in self._map

    def getAttr(self, attr):
        return self._map.get(attr)

    def removeAttr(self, attr):
        self.__delattr__(attr)

    def __len__(self):
        return len(self.keys())

    def __setitem__(self, key, value):
        key = str(key)
        self._map[key] = value

    def __getitem__(self, item):
        item = str(item)
        self._map.setdefault(item, JayObject())
        return self._map[item]

    def __delattr__(self, name):
        if name in self._map:
            del self._map[name]

    def __delitem__(self, key):
        key = str(key)
        self.__delattr__(key)

    def __repr__(self):
        for (key, value) in self._map.items():
            if isinstance(value, JayObject):
                if not value:
                    self.__delattr__(key)
        return self._map.__repr__()

    def __str__(self):
        if not self:
            return ''
        return super(JayObject, self).__str__()


class SnmpStateHolder(object):
    """
    A data model to store model information of a host
    """

    class ModelTypes(object):
        """
        A data class to store types of model
        """

        def __init__(self):
            super(SnmpStateHolder.ModelTypes, self).__init__()
            self.__types = []

        def _addType(self, modelType):
            if modelType not in self.__types:
                self.__types.append(modelType)
            self.__setattr__(modelType, True)

        def __getattribute__(self, name):
            x = False
            try:
                x = super(SnmpStateHolder.ModelTypes, self).__getattribute__(name)
            except AttributeError:
                pass
            return x

        def __str__(self):
            return str(self.__types)

        def __getitem__(self, item):
            return self.__getattribute__(item)

        def __setitem__(self, key, value):
            self.__setattr__(key, value)

        def _values(self):
            return self.__types

        def __delattr__(self, name):
            if self.__getattribute__(name):
                return super(SnmpStateHolder.ModelTypes, self).__delattr__(name)

    def __init__(self, oid=None, desc=None):
        super(SnmpStateHolder, self).__init__()
        if oid:
            self.sysOid = OID(oid).value()
        else:
            self.sysOid = None
        self.desc = desc

        self.types = self.ModelTypes()
        self.jay = JayObject()


    def addType(self, modelType):
        self.types._addType(modelType)

    def getTypes(self):
        return self.types._values()

    def hasTypes(self, *type):
        for x in type:
            if x not in self.types._values():
                return False
        return True

    def attr(self, key, value=None):
        pass
        # if not value:
        # return getattr(self.jay, key)
        # else:
        # setattr(self.jay, key, value)


class SnmpHelper(object):
    def __init__(self, stateHolder, snmpQueryHelper):
        super(SnmpHelper, self).__init__()
        self.snmpStateHolder = stateHolder
        self.snmpQueryHelper = snmpQueryHelper

    def hasValidOffspringSnmpNext(self, oid, comparedOid=None):
        if not comparedOid:
            comparedOid = oid
        result, _ = self.snmpQueryHelper.snmpNext(oid)
        return result and is_offspring(result, comparedOid)

    def snmpGet(self, *oid):
        return self.snmpQueryHelper.snmpGet(*oid)
    
    def _sanitizeValue(self, value):
        if value and str(value).lower() in ['none', 'nul', 'null', 'empty']:
            return None
        return value

    def snmpGetValue(self, oid):
        return self._sanitizeValue(self.snmpQueryHelper.snmpGet(oid)[1])

    def snmpWalkValue(self, oid):
        return [ self._sanitizeValue(x[1]) for x in self.snmpQueryHelper.snmpWalk(oid)]

    def snmpNext(self, oid):
        return self.snmpQueryHelper.snmpNext(oid)

    def snmpWalk(self, oid):
        return self.snmpQueryHelper.snmpWalk(oid)


class ModelTypeHelper(SnmpHelper):
    def _e(self, oid):
        """
        sys object id equals
        """
        return self.snmpStateHolder.sysOid == oid

    def _s(self, *oid):
        """
        sys object starts with
        """
        if self.snmpStateHolder.sysOid:
            for singleOid in oid:
                if self.snmpStateHolder.sysOid.startswith(singleOid):
                    return True
        return False

    def _r(self, *patterns):
        """
        search model description by regex in case sensitive
        sys description regex match
        """
        if self.snmpStateHolder.desc:
            for pattern in patterns:
                if re.search(pattern, self.snmpStateHolder.desc):
                    return True
        return False

    def _rci(self, *patterns):
        """
        search model description by regex in ignore case
        sys description regex match
        """
        if self.snmpStateHolder.desc:
            for pattern in patterns:
                if re.search(pattern, self.snmpStateHolder.desc, re.IGNORECASE):
                    return True
        return False

    def _rt(self, pattern, target=None):
        if target:
            return re.search(pattern, target)


class ModelTypeMatcher(ModelTypeHelper):
    """
    A class to try get model types of a host from snmp by trying different solutions,
    such as oid-mapping, oid-starts, description mapping...
    """

    def __init__(self, stateHolder, snmpQueryHelper):
        super(ModelTypeMatcher, self).__init__(stateHolder, snmpQueryHelper)

    def _match_oid_equal(self):
        logger.debug('execute match oid by equal')
        if self.snmpStateHolder.sysOid:
            return OID_TO_MODEL.get(self.snmpStateHolder.sysOid)

    def _addToModel(self, types):
        if types:
            types = filter(None, types)
        if types:
            for t in types:
                self.snmpStateHolder.addType(t)
            return True

    def match(self):
        self.ensureOidOrDesc()
        try:
            types = self._match_oid_equal() or self._match_oid_start_with() or self._match_desc_equal() or \
                    self._match_desc_regex() or self._extra_patterns() or []
            r1 = self._addToModel(types)
            specialX = self._specialX()
            r2 = self._addToModel(specialX)
            return r1 or r2
        except:
            logger.errorException('Something error happened')
            return False

    def _match_desc_equal(self):
        logger.debug('execute match desc by equal')
        if self.snmpStateHolder.desc:
            return DESC_TO_MODEL.get(self.snmpStateHolder.desc)

    def _match_oid_start_with(self):
        logger.debug('execute match oid by start with')
        if not self.snmpStateHolder.sysOid:
            return None
        matches = OID_START_WITH_TO_MODEL
        for oidKey, types in matches.items():
            oids = []
            if isinstance(oidKey, str):
                oids = [oidKey]
            elif isinstance(oidKey, tuple):
                oids = oidKey

            if self._s(*oids):
                return types
        return ExtraOidStartWithSpecialCaseHandler(self).handle()

    def _match_desc_regex(self):
        logger.debug('execute match desc by regex')
        if not self.snmpStateHolder.desc:
            return None
        matches = DESC_REGEX_TO_MODEL
        for pattern, types in matches.items():
            if self._r(pattern):
                return types
        return None

    def _extra_patterns(self):
        return CustomSpecialCaseHandler(self).handle()

    def _specialX(self):
        return SpecialXCaseHandler(self).handle()

    def ensureOidOrDesc(self):
        if not self.snmpStateHolder.sysOid and not self.snmpStateHolder.desc:
            if not self.snmpStateHolder.sysOid:
                sysOid = self.snmpGetValue(SYS_OID)
                if sysOid and sysOid != 'Null':
                    self.snmpStateHolder.sysOid = OID(sysOid).value()
            if not self.snmpStateHolder.desc:
                _, desc = self.snmpGet(SYS_DESC)
                if _ and desc != 'Null':
                    self.snmpStateHolder.desc = desc
        if not self.snmpStateHolder.sysOid and not self.snmpStateHolder.desc:
            raise Exception('Oid and desc should not be empty at the same time.')


class SpecialCaseHandler(ModelTypeHelper):
    """
      Handle special cases.
      Usage:
      1) add method to implement your business logic
      2) Implement getFunction, return a list of tuple, the first element is the method defined above, the second
      element is the model types which will also be returned if the first function's return is not empty
    """

    def __init__(self, modelTypeMatcher):
        super(SpecialCaseHandler, self).__init__(modelTypeMatcher.snmpStateHolder, modelTypeMatcher.snmpQueryHelper)

    @classmethod
    def makeRegistrar(cls):
        registry = []

        def registrar(func):
            registry.append(func.__name__)
            return func

        registrar.all = registry
        return registrar

    def _handleSpecialCase(self, fs):
        """
        Join function with logic 'OR' operator, return the result once the result is not None
        @param fs:
        @return: execution result of one of function which result not empty value
        """
        logger.debug('execute handle Special Case')
        finalResult = []
        for unit in fs:
            if isinstance(unit, tuple):
                fun, types = unit
            else:
                fun, types = unit, []
            logger.debug('Execute function:', fun.__name__)
            result = fun()
            if result:
                if isinstance(result, list):
                    finalResult.extend(result)
                elif isinstance(result, GeneratorType):
                    result = list(result)
                    if result:
                        finalResult.extend(result)
                    else:
                        continue
                finalResult.extend(types)
                if self.isNotReturn(fun):
                    continue
                return finalResult
        return finalResult

    def handle(self):
        logger.debug('exe extra patterns')
        fs = self.getFunctions()

        return self._handleSpecialCase(fs)

    def getFunctions(self):
        raise NotImplementedError()

    def hasValidSnmpGet(self, oid):
        _, _ = self.snmpQueryHelper.snmpGet(oid)
        return bool(_)

    def snmpGetByOid(self, oid):
        return self.snmpQueryHelper.snmpGet(oid)

    def isNotReturn(self, fun):
        return fun.__name__ in self.notReturn.all


class ExtraOidStartWithSpecialCaseHandler(SpecialCaseHandler):
    """
    Handle special cases for oid starts with. It migrated most of business logic from
    is_whatever_by_strncmp_sysoid method of is_whatever.jay
    """
    caseHandler = SpecialCaseHandler.makeRegistrar()
    notReturn = SpecialCaseHandler.makeRegistrar()

    def __init__(self, modelTypeMatcher):
        super(ExtraOidStartWithSpecialCaseHandler, self).__init__(modelTypeMatcher)

    def getFunctions(self):
        fs = [
            (lambda: self._s('1.3.6.1.4.1.641.1', '1.3.6.1.4.1.641.2.') or (
                self._e('1.3.6.1.4.1.8072.3.2.10') and self._r('Lexmark')),
             ['lexmarknet']),

            (lambda: self._s('1.3.6.1.4.1.11.2.3.9.') and not self._s('1.3.6.1.4.1.11.2.3.9.3.') and self._r(
                'JETDIRECT') or self._e('1.3.6.1.4.1.11.1'), ['hpprinter']),

            (lambda: self._e('1.3.6.1.4.1.11.2.3.9.1') and self._r('Brother'), ['brother']),

            (lambda: self._s('1.3.6.1.4.1.11.2.3.10.') and self._r('SunOS'), ['SUN_HOST']),
        ]
        registered = [self.__getattribute__(x) for x in self.caseHandler.all]
        fs.extend(registered)
        return fs

    @caseHandler
    def canon(self):
        if self._s('1.3.6.1.4.1.1536.3.3.'):
            yield 'Canon_extra'
            if self._e('1.3.6.1.4.1.1536.3.3.15.6'):
                yield 'Canon'

    @caseHandler
    def dell(self):
        if self._s('1.3.6.1.4.1.674.10895.'):
            yield 'DELL_SWITCH'
            if self._e('1.3.6.1.4.1.674.10895.1000'):
                yield 'DELL_PW5212'

    @caseHandler
    def _lanplex(self):
        if self._s('1.3.6.1.4.1.114.1.3.3.1', '1.3.6.1.4.1.114.1.3.3.2.7'):
            yield 'LANPLEX2500'
            if self._e('1.3.6.1.4.1.114.1.3.3.1.7'):
                yield 'COREBUILDER2500'

    @caseHandler
    def _hp_ux_server(self):
        if self._s('1.3.6.1.4.1.11.2.3.2.5'):
            yield 'hp_ux_server'
            if self._e('1.3.6.1.4.1.11.2.3.2.5'):
                yield 'ifSpeed_Mbps'

    @caseHandler
    def _HPUX(self):
        if self._s('1.3.6.1.4.1.11.2.3.2.3'):
            yield 'HP_UX'
            if self._e('1.3.6.1.4.1.11.2.3.2.3'):
                yield 'HP_FDDI'
                yield 'ifSpeed_Mbps'

    @caseHandler
    def _novell_agent(self):
        if self._s('1.3.6.1.4.1.23.'):
            yield 'NOVELL_AGENT'
            if self._e('1.3.6.1.4.1.23.1.6'):
                yield 'NOVELL_tcp'

    @caseHandler
    def _lanline(self):
        if self._s('1.3.6.1.4.1.64.'):
            bridge_oid = '1.3.6.1.4.1.64.2.2.10.1.2'
            result, _ = self.snmpQueryHelper.snmpNext(bridge_oid)
            if result and is_offspring(result, bridge_oid):
                yield 'LanLine'

    @caseHandler
    def _kinnectics(self):
        if self._s('1.3.6.1.4.1.1467'):
            yield 'KINNETICS'
            duplexoid = '1.3.6.1.4.1.1467.100.1.1.3'
            r, _ = self.snmpQueryHelper.snmpNext(duplexoid)
            if r and 1 == is_offspring(r, duplexoid):
                yield 'KINNETICS_with_NM'

            if self._e('1.3.6.1.4.1.1467.2.1'):
                yield 'KINNNETICS_buggy_HOST'

            if self._s('1.3.6.1.4.1.1467.3.2.') or self._s('1.3.6.1.4.1.1467.2.1.5'):
                yield 'UCD_LINUX_AGENT'
            if self._s('1.3.6.1.4.1.1467.2.1.5') and self._r('Peregrine Appliance 5.2.'):
                yield 'DONT_USE_hrFSTable'

    @caseHandler
    def _hpprocurve(self):
        if self._s('1.3.6.1.4.1.11.2.3.7.11'):
            if self._r('ProLiant'):
                yield 'HPProliantSwitch'
            yield "HPProCurve"
            if self._s('1.3.6.1.4.1.11.2.3.7.11.66'):
                yield 'PROCURVE9029'
            if self._s('1.3.6.1.4.1.11.2.3.7.11.33.4.1.1'):
                yield 'HPBlade_Proliant'


class CustomSpecialCaseHandler(SpecialCaseHandler):
    caseHandler = SpecialCaseHandler.makeRegistrar()
    notReturn = SpecialCaseHandler.makeRegistrar()

    def __init__(self, modelTypeMatcher):
        super(CustomSpecialCaseHandler, self).__init__(modelTypeMatcher)

    def getFunctions(self):
        logger.debug('All case handlers:', self.caseHandler.all)
        return [self.__getattribute__(x) for x in self.caseHandler.all]

    @caseHandler
    def _3comcb7000(self):
        if self._e('1.3.6.1.4.1.43.1.12.1') and self._r('CoreBuilder7000: ATM Switch'):
            yield 't3COMCB7000'

    @caseHandler
    def _t3COMLB10BTI(self):
        if self._r('3Com LinkBuilder 10BTi') or self._r('3Com SuperStack II Hub'):
            if self._e('1.3.6.1.4.1.43.1.8.2.1.30'):
                yield 't3COMLB10BTI'
            elif self._e('1.3.6.1.4.1.43.1.8.5'):
                yield 't3COMLINKBUILDER'

    @caseHandler
    def _decchassis(self):
        if self._e('1.3.6.1.4.1.36.2.15.10.3.1') and self._r('MultiSwitch'):
            if self.has_only_chassis_ip():
                yield 'DEC900CHASSISMODULE'
            yield 'DEC900CHASSIS'

    @caseHandler
    def _3comlinkbuilder(self):
        if self._r('3Com LinkBuilder MSH') and self._e('1.3.6.1.4.1.43.1.8.4'):
            yield 't3COMLINKBUILDERMSH'

    def has_only_chassis_ip(self):
        # todo strtok is an array? why chassis_ip is array?
        ip_oid = '1.3.6.1.4.1.36.2.18.11.1.1.1.2.2.1.11'
        is_single_ip = True
        # chassis_ip=strtok(model.Jaywalk.Address,":")#todo
        chassis_ip = ''
        entityid = ''
        while True:
            module_ip, value = self.snmpQueryHelper.snmpNext(ip_oid + entityid)
            if not module_ip or not is_offspring(module_ip, ip_oid):
                break
            if len(module_ip.split('.')) > 18:
                is_single_ip = False
                break

            if chassis_ip == value:
                is_single_ip = False
                break
            entityid = "." + module_ip[len(module_ip.split('.')) - 1]

        return is_single_ip

    @caseHandler
    def _t3COMSSDT(self):
        if self._r('3Com SuperStackII Desktop Switch') and self._e('1.3.6.1.4.1.43.1.8.29'):
            yield 't3COMSSDT'

    @caseHandler
    def alfafddi(self):
        if self._r('FDDI  CONCENTRATOR') and self._e('1.3.6.1.4.1.1288.1.2.3'):
            yield 'ALFAFDDI'

    @caseHandler
    def CENTRECOM2985(self):
        if self._r('Retix High Speed Local Ethernet Bridge Model 2985') and self._e('1.3.6.1.4.1.72.8.12'):
            yield 'CENTRECOM2985'

    @caseHandler
    def centercom8124(self):
        if self._r('CentreCOM 8124XL') and self._e('1.3.6.1.4.1.207.1.4.23'):
            yield 'CENTRECOM8124'

    @caseHandler
    def CONTEC1200S(self):
        pass
        if self._s('1.3.6.1.4.1.672.2.1'):
            if self.hasValidSnmpGet('1.3.6.1.2.1.22.1.1.1.0'):
                yield 'CONTEC1200S'

    @caseHandler
    def CTRON_SSR2000(self):
        if self._r('SSR 2000') and self._e('1.3.6.1.4.1.52.3.9.33.1.1'):
            yield 'CTRON_SSR2000'

    @caseHandler
    def FUJITSU_LR265_278(self):
        if self._e('1.3.6.1.4.1.211.1.127.14'):
            if self._r('LR255') or self._r('LR276'):
                yield 'LR276'

            yield 'FUJITSU_LR265_278'

    @caseHandler
    def fujitsu_lr550(self):
        if self._e('1.3.6.1.4.1.211.1.127.15'):
            if self._r('LR550') or self._r('LR750'):
                yield 'LR550'
            elif self._r('LR450') or self._r('LR460'):
                yield 'LR460'
            elif self._r('LR-X6030'):
                yield 'LRX6030'

    @caseHandler
    def IBM_BAD_MAC(self):
        if self._e('1.3.6.1.4.1.2.3.1.2.1.1.3'):
            yield 'IBM_BAD_MAC'
            if self._r('IBM RISC System/6000'):
                yield 'IBM_FDDI'
            if self._r('IBM PowerPC CHRP') or self._r('IBM PowerPC Personal ComputerMachine'):
                yield 'IBM_POWERPC'

    @caseHandler
    def dechub(self):
        if self._r('DECrepeater') and self._e('1.3.6.1.4.1.36.2.15.9.11.1'):
            if self.has_only_chassis_ip():
                yield 'DECHUB90'

    @caseHandler
    def EPSON(self):
        if self._s('1.3.6.1.4.1.1248.1.1.') or self._s('1.3.6.1.4.1.1248.3.1.'):
            yield 'epson_printer_model'
            if self._s('1.3.6.1.4.1.1248.1.1.2.1.3') or self._s('1.3.6.1.4.1.1248.1.1.2.2.1') \
                    or self._s('1.3.6.1.4.1.1248.1.1.2.2.2') or self._s('1.3.6.1.4.1.1248.1.1.2.2.3'):
                yield 'epson_printer'
                yield 'NoByte'

    @caseHandler
    def bay5000(self):
        oid = '1.3.6.1.4.1.45.1.6.5.1.1.1.1'
        result, _ = self.snmpQueryHelper.snmpNext(oid)
        if result and is_offspring(result, oid):
            yield 'BAY5K'

    @caseHandler
    def BAY102(self):
        oid = '1.3.6.1.4.1.45.1.6.6.1.1.1.1'
        result, _ = self.snmpQueryHelper.snmpNext(oid)
        if result and is_offspring(result, oid):
            yield 'BAY102'

    @caseHandler
    def CISCO1700(self):
        oid = '1.3.6.1.4.1.437.1.1.1.1.3.1.1.1'
        returnOid, result = self.snmpQueryHelper.snmpNext(oid)
        if returnOid and is_offspring(returnOid, oid) and int(result) > 0:
            yield 'CISCO1700'
            yield 'CISCO'

    @caseHandler
    def synoptics_281x_3000(self):
        if self._s('1.3.6.1.4.1.45.'):
            bridgeOid = '1.3.6.1.4.1.45.1.3.2.3.1.1.1'
            ver_string = '1.3.6.1.4.1.45.1.2.6.2.0'
            ethbrdId, ethbrdValue = self.snmpQueryHelper.snmpNext(bridgeOid + '.0.0')
            vers = self.snmpGetValue(ver_string)
            if ethbrdId and is_offspring(ethbrdId, bridgeOid):
                if vers and int(vers) <= 5:
                    yield 'OLDSYNOPTICS3000'
            if self.snmpStateHolder.hasTypes('OLDSYNOPTICS3000'):
                sac_type = self.get_repeater_sac_type()
                sac_var = None
                if sac_type:
                    if sac_type == 'NEW_SAC':
                        sac_var = '1.3.6.1.2.1.22.3.3.1.1.5.'
                    elif sac_type == 'OLD_SAC':
                        sac_var = '1.3.6.1.2.1.22.3.3.1.1.3.'
                else:
                    sac_var = "1.3.6.1.4.1.45.1.3.2.10.1.1.8"
                    result, value = self.snmpQueryHelper.snmpNext(sac_var)
                    if result and is_offspring(result, result):
                        sac_var = None
                if not sac_var:
                    sac_oid = "1.3.6.1.4.1.45.1.3.2.5.1.1.3"
                    result, value = self.snmpQueryHelper.snmpNext(sac_oid)
                    if result and is_offspring(result, result):
                        yield 'OLDSYNOPTICS3000wTABLE'

    def get_repeater_sac_type(self):
        if self.snmpStateHolder.types.AT_36xxTR:
            return None

        new_sac_string = '1.3.6.1.2.1.22.3.3.1.1.5'
        old_sac_string = '1.3.6.1.2.1.22.3.3.1.1.3'

        rv, value = self.snmpQueryHelper.snmpNext(new_sac_string)
        if rv and is_offspring(rv, new_sac_string):
            return 'NEW_SAC'

        rv, value = self.snmpQueryHelper.snmpNext(old_sac_string)
        if rv and is_offspring(rv, new_sac_string):
            return 'OLD_SAC'

    @caseHandler
    def DE1500(self):
        oid = '1.3.6.1.4.1.171.2.1.15.1.1'
        result, value = self.snmpQueryHelper.snmpNext(oid)
        if result and is_offspring(result, oid) and int(value) > 0:
            yield 'DE1500'

    @caseHandler
    def IRM2(self):
        oid = '1.3.6.1.4.1.52.1.2.2.4.1.1'
        result, value = self.snmpQueryHelper.snmpNext(oid)
        if result and is_offspring(result, oid) and int(value) > 0:
            yield 'IRM2'

    @caseHandler
    def HPHUB(self):
        oid = '1.3.6.1.4.1.11.2.14.2.1.0'
        value = self.snmpGetValue(oid)
        if value and (int(value) == 0 or int(value) == 1):
            yield 'HPHUB'
            if self._e('1.3.6.1.4.1.11.2.3.7.5.19'):
                yield 'HPJ3188AHUB'

    @caseHandler
    def MRXI2(self):
        oid = '1.3.6.1.4.1.52.1.2.1.1.2.0'
        value = self.snmpGetValue(oid)
        if value and int(value) == 5:
            yield 'MRXI2'

    @caseHandler
    def WAVERIDER(self):
        oid1 = '1.3.6.1.4.2979.2'
        oid2 = '1.3.6.1.4.1.2979.2'
        result1, value1 = self.snmpQueryHelper.snmpNext(oid1)
        if result1 and is_offspring(result1, oid1):
            yield 'WAVERIDER'
        else:
            result2, value2 = self.snmpQueryHelper.snmpNext(oid2)
            if result2 and is_offspring(result2, oid2):
                yield 'WAVERIDER'

    @caseHandler
    def waveswitch(self):
        oid = '1.3.6.1.4.1.295.3.2.1.1.1.19.0'
        value = self.snmpGetValue(oid)
        if value:
            if float(value) < 1.2:
                yield 'WS100_OLD'
            else:
                yield 'WS100_NEW'

    @caseHandler  #time-consuming
    def UPS(self):
        if self.hasValidOffspringSnmpNext('1.3.6.1.2.1.33.1.1.2'):
            yield 'STANDARD_UPS'


class SpecialXCaseHandler(SpecialCaseHandler):
    caseHandler = SpecialCaseHandler.makeRegistrar()
    notReturn = SpecialCaseHandler.makeRegistrar()

    def __init__(self, modelTypeMatcher):
        super(SpecialXCaseHandler, self).__init__(modelTypeMatcher)

    def getFunctions(self):
        logger.debug('All case handlers:', self.caseHandler.all)
        return [self.__getattribute__(x) for x in self.caseHandler.all]

    @caseHandler
    def BIG_IP(self):
        if self._s('1.3.6.1.4.1.3375.2.1.3.4.'):
            yield 'BIG_IP'

    @caseHandler
    def FUJITSU_ARP(self):
        if self._s('1.3.6.1.4.1.211.'):
            yield 'FUJITSU_ARP'

    @caseHandler
    def SUPERSTACK3(self):
        if self.snmpStateHolder.hasTypes('t3COMSSIIS') and self.snmpStateHolder.desc == '3Com SuperStack 3':
            yield 'SUPERSTACK3'

    @caseHandler
    def CISCO(self):
        if self._s('1.3.6.1.4.1.9.'):
            yield 'CISCO_HOST'
            yield 'CISCO'
            if self._e('1.3.6.1.4.1.9.1.209') and self._r('\\(C2600\\-IS\\-M\\)\\, Version 12\\.2\\(23\\)'):
                yield 'CISCO2600_BADHSRP'
            vm_oid = '1.3.6.1.4.1.9.9.68.1.2.2.1.2'
            if self.hasValidOffspringSnmpNext(vm_oid):
                yield 'CISCOHASVLANMEM'

            vm_oid = '1.3.6.1.4.1.9.9.368.1.14.1.4.1.2'
            if self.hasValidOffspringSnmpNext(vm_oid):
                yield 'CISCOCONTENTVLAN'

            status_oid = '1.3.6.1.4.1.9.5.1.3.1.1.10'
            if self.hasValidOffspringSnmpNext(status_oid):
                yield 'CISCOHASMODULE'
            if not self.snmpStateHolder.jay.Forwarding \
                    and (((self._r('C2600') or self._r('3600') or self._r('3700'))
                          and (self._r('Version 12\\.1\\(') or self._r('Version 12\\.2\\(')))
                         or (self._r('2800') and self._r('Version 12\\.4\\(')) or self._r('C3845')):
                self.snmpStateHolder.jay.arpEx = 1
                yield 'CISCO2600_ARP'

            if self._r('Version 12\\.2\\(40\\)SE'):
                yield 'CISCONONUCAST'

            if self._r('Version 12\.3\\('):
                if (self._e('1.3.6.1.4.1.9.1.469') and self._r('Version 12\.3\\(1a\\)')) or (
                            self._e('1.3.6.1.4.1.9.1.499') and self._r('Version 12\.3\\(8\\)')):
                    yield 'SKIP_ENTITY2'

            if self.snmpStateHolder.hasTypes('CISCO2950') and self._r('Version 12\\.1\\(6\\)EA2'):
                yield 'CISCO2950_BAD'

            if (self._e('1.3.6.1.4.1.9.1.220') or self._e('1.3.6.1.4.1.9.1.219') or self._e('1.3.6.1.4.1.9.1.218')) and self._r(
                    'Version 11\.2\\(8\\)SA4'):
                raise StopIteration()

            group_oid = '1.3.6.1.4.1.9.9.87.1.4.1.1.4'
            if self.hasValidOffspringSnmpNext(group_oid):
                yield 'MAPPING2900'
                # get_2900map_list(&model,address);

    @caseHandler
    def REMOTE_LIGHT_OUT(self):
        oid = '1.3.6.1.4.1.232.9.2.5.1.1.1'
        result, value = self.snmpQueryHelper.snmpNext(oid)
        if result and is_offspring(result, oid):
            if not self._rt('[a-z,A-Z]', value):
                yield 'REMOTE_LIGHT_OUT'

    @caseHandler
    def DELL_RAC(self):
        if self._s('1.3.6.1.4.1.674.10892.1.'):
            yield 'DELL_RAC_SERVER'
        elif self._s('1.3.6.1.4.1.674.10892.2.'):
            yield 'DELL_RAC'
        if self.hasValidSnmpGet('1.3.6.1.4.1.674.10892.2.1.1.2.0'):
            yield 'DELL_RAC'

    @caseHandler
    def CITRIX_NETSCALER(self):
        if self._s('1.3.6.1.4.1.5951.1'):
            yield 'CITRIX_NETSCALER'

    @caseHandler
    def IBM(self):
        if self._s('1.3.6.1.4.1.2.'):
            yield 'IBM'
            yield 'IBMMAP'

    @caseHandler
    def AIRONET(self):
        if self._s('1.3.6.1.4.1.551.2.1'):
            yield 'AIRONET'

    @caseHandler
    def NORTEL(self):
        if self._s('1.3.6.1.4.1.45.') or self._s('1.3.6.1.4.1.2272.'):
            yield 'NORTEL'

    @caseHandler
    def t3COMSYSBRIDGE(self):
        if self._s('1.3.6.1.4.1.43'):
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.43.29.4.10.5.1.4'):
                yield 't3COMSYSBRIDGE'
            if self._s('1.3.6.1.4.1.43.1.'):
                if self.hasValidSnmpGet('1.3.6.1.4.1.43.2.13.1.1.0'):
                    yield 't3COM_brouterMIB_SN'

    @caseHandler
    def AT3714(self):
        if self._r('AT-3714') and self._s('1.3.6.1.4.1.207.1.4'):
            yield 'AT3714'

    @caseHandler
    def CTRON_SFPS(self):
        if self._s('1.3.6.1.4.1.52.'):
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.52.4.2.4.2.2.3.5.1.1.7'):
                yield 'CTRON_SFPS'

    @caseHandler
    def SEC10_DBTABLE(self):
        if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.326.2.3.2.5.1.6'):
            yield 'SEC10_DBTABLE'

    @caseHandler
    def XYLANOMNISWITCH_MODEL(self):
        if self._s('1.3.6.1.4.1.800.3.1.1.'):
            if self.hasValidSnmpGet('1.3.6.1.4.1.800.2.1.1.2.0'):
                yield 'XYLANOMNISWITCH_MODEL'

    @caseHandler
    def NORTEL_TOK_RING(self):
        if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.45.1.3.3.3.1.1.2'):
            yield 'NORTEL_TOK_RING'

    @caseHandler
    def Foundry(self):
        if self._r('Foundry'):
            if self._r('02.00.05'):
                yield 'Foundry_Wg_Sw'
            yield 'Foundry'

    @notReturn
    @caseHandler
    def COMPAQ(self):
        if self._s('1.3.6.1.4.1.311.1.1.3.'):
            yield 'COMPAQ_HOST'
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.2.6.159.1.1.60.3.1.10'):
                yield 'IBMCOMPQ_SN'
            if self.hasValidSnmpGet('1.3.6.1.4.1.231.2.10.2.2.10.2.3.1.15.1') or self.hasValidSnmpGet(
                    '1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.3.0'):
                yield 'FUJITSU_WIN'

            value = self.snmpGetValue('1.3.6.1.4.1.12893.77.1.2.1.0')
            if value:
                self.snmpStateHolder.jay.MiscInfo = 'SRV:' + value
            base_oid = "1.3.6.1.4.1.674.10892.1.1900.30.1"
            bmc_oid = base_oid + ".3"
            if self.hasValidOffspringSnmpNext(base_oid, bmc_oid):
                yield 'DELL_RAC_SERVER'

            if self.hasValidSnmpGet('1.3.6.1.4.1.12893.1.15.1.2.1'):
                yield 'VISIOWAVE_CAMERA'

    @caseHandler
    def Fujitsu(self):
        if self._e('1.3.6.1.4.1.8072.3.2.10'):
            if self.hasValidSnmpGet('1.3.6.1.4.1.231.2.10.2.2.5.10.3.1.3.0'):
                yield 'FUJITSU_LINUX'
            if self.hasValidSnmpGet('1.3.6.1.4.1.12893.1.10.0'):
                yield 'VISIOWAVE_CAMERA'

    @caseHandler
    def windows(self):
        # todo handle BROKEN_WIN
        if self._rci('Microsoft Corp. Windows 98', 'Windows 2000 Version 5.0'):
            if self._rci('Windows 2000'):
                yield 'WINDOWS2K'
            else:
                yield None
        elif self._rci('Windows 2000'):
            yield 'WINDOWS2K'
        elif self._rci('Windows Version 5\\.2', 'Windows Server 2003', 'Windows 2000 Version 5\\.2',
                       'Windows Server 2000 Version 5\\.2'):
            yield 'WINDOWS2K3'
        elif self._rci('Windows Version 6\\.0 \\(Build 600[1,2]'):
            yield 'WINDOWS2K8'
        elif self._rci('Windows 2000 Version 6\\.0', 'Windows Version 6\\.0'):
            yield 'WINDOWSVISTA'

    @caseHandler
    def BLACKDIAMOND(self):
        if self._s('1.3.6.1.4.1.1916.'):
            yield 'SNMPv2BLACKDIAMOND'
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.1916.1.13.2.1.3'):
                yield 'HAS_EDP'
        if self.snmpStateHolder.hasTypes('BLACKDIAMOND'):
            if self._r(r'Version 6\.1\.[789]') or self.snmpStateHolder.hasTypes('SUMMIT48_POLL'):
                yield 'WEAKBLACKDIAMOND'

    @caseHandler
    def AUSPEX(self):
        if self.snmpStateHolder.hasTypes('SUN_HOST'):
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.80.3.2.2.1.2.1'):
                yield 'AUSPEX'

    @caseHandler
    def SUNAGENT(self):
        if self._r('Sun SNMP Agent,'):
            yield 'SUNAGENT'

    @caseHandler
    def LATTICE28115(self):
        if not self.snmpStateHolder.hasTypes('LATTICE28200'):
            if self.hasValidOffspringSnmpNext('1.3.6.1.4.1.45.1.7.6.2.1.1.1'):
                yield 'LATTICE28115'

    @caseHandler
    def CABLETRON_TRMM(self):
        if self._s('1.3.6.1.4.1.52.3.2') and self._r('TRMM'):
            yield 'CABLETRON_TRMM'

    @caseHandler
    def printer(self):
        if self.hasValidOffspringSnmpNext('1.3.6.1.2.1.43.11.1.1.2.1') and \
                self.hasValidOffspringSnmpNext('1.3.6.1.2.1.43.8.2.1.9.1'):
            yield 'PRINTER'
            if self._s('1.3.6.1.4.1.11.2.3.9.'):
                yield 'hpprinter'
        if self._s('1.3.6.1.4.1.253.8.62.1.'):
            yield 'XEROX_PRINTER'
        else:
            if self.snmpStateHolder.hasTypes('CANON_COLOR') and self._r('iR2220'):
                yield 'CANON_GOOD'
            if self.hasValidSnmpGet('1.3.6.1.2.1.43.5.1.1.17.1'):
                yield 'STANDARD_PRINTER_SN'


class SnmpQueryHelper(object):
    """
    A helper class for simply doing snmp get, getnext
    """

    def __init__(self, snmpClient):
        super(SnmpQueryHelper, self).__init__()
        self.snmpClient = snmpClient

    def _snmpGet(self, oid):
        resultSet = self.snmpClient.snmpGet(OID(oid).value(), 0)
        if resultSet.next():
            returnedOid = resultSet.getString(1)
            value = resultSet.getString(2)
            # snmp get will return 'noSuchObject' if there is no value for it
            if value not in ['noSuchObject', 'noSuchInstance']:
                return returnedOid, value
        return None, None

    def _snmpNext(self, oid):
        resultSet = self.snmpClient.snmpGetNext(OID(oid).value(), 0)
        if resultSet.next():
            returnedOid = resultSet.getString(1)
            value = resultSet.getString(2)
            if returnedOid != oid and value not in ['endOfMibView']:
                return returnedOid, value
        return None, None

    def snmpWalk(self, oid):
        resultSet = self.snmpClient.snmpWalk(OID(oid).value(), 0)
        resultMap = []
        while resultSet.next():
            returnedOid = resultSet.getString(1)
            value = resultSet.getString(2)
            if returnedOid == oid or value == 'endOfMibView' or value == 'noSuchObject':
                continue
            resultMap.append((returnedOid, value))
        # fix result in snmpwalk which doesn't return result in mib order
        resultMap.sort(key=lambda x: OID(x[0]))
        return resultMap

    def snmpGet(self, *oid):
        if oid:
            result = map(lambda x: self._snmpGet(x), oid)
            return result[0] if len(oid) == 1 else result

    def snmpNext(self, *oid):
        """
        @param oid: single oid or multiple oid
        @return: snmp getnext result, if input is one single oid, the result will be one,
            if input are multiple, the result will be an array
        @rtype str or str[]
        """
        if oid:
            result = map(lambda x: self._snmpNext(x), oid)
            return result[0] if len(oid) == 1 else result


class SnmpQueryHelperMock(SnmpQueryHelper):
    def __init__(self):
        super(SnmpQueryHelperMock, self).__init__('')
        self.__getMap = {}
        self.__getNextMap = {}
        self.__walkMap = {}

    def _snmpGet(self, oid):
        result = self.__getMap.get(oid)
        if not result:
            result = (None, None)
        logger.debug('Get oid by mock:%s, result:%s' % (oid, result))
        return result

    def _snmpNext(self, oid):
        result = self.__getNextMap.get(oid)
        if not result:
            result = (oid, None)
        logger.debug('Get Next oid by mock:%s, result:%s' % (oid, result))
        return result

    def snmpWalk(self, oid):
        result = self.__walkMap.get(oid)
        if not result:
            result = []
        logger.debug('Get walk result by mock:%s, result:%s' % (oid, result))
        return result

    def mockGet(self, oid, value):
        self.__getMap[oid] = (oid, value)

    def mockNext(self, oid, value):
        self.__getNextMap[oid] = value

    def mockWalk(self, oid, value):
        self.__walkMap[oid] = value


def find(oid, desc, client):
    snmpStateHolder = SnmpStateHolder(oid, desc)
    snmpQueryHelper = SnmpQueryHelper(client)
    mtm = ModelTypeMatcher(snmpStateHolder, snmpQueryHelper)
    mtm.match()
    return snmpStateHolder.getTypes()