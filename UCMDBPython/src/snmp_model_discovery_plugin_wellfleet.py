from snmp_model_discovery import *


@Supported('SYSTEM5000ROUTER')
class SYSTEM5000ROUTER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        type = {'1': 'acefn', '2': 'aceln', '3': 'acecn', '4': 'afn', '5': 'in', '16': 'an', '32': 'arn',
                '34': 'fbr4slot', '36': 'lite', '5000': 'sys5000', '16640': 'freln', '16896': 'frecn',
                '17152': 'frerbln', '20480': 'asn', '20736': 'asnzcable', '20992': 'asnbcable', '24576': 'sn',
                '26368': 'v15k'}
        k = self.snmpGetValue('1.3.6.1.4.1.18.3.1.1.1.0') or NOT_FOUND_IN_MIB
        v = self.snmpGetValue('1.3.6.1.4.1.18.3.1.1.3.0') or NOT_FOUND_IN_MIB
        if k:
            if type[k]:
                model.SerialNumber.Chassis[0].Description = type[k]
        else:
            model.SerialNumber.Chassis[0].Description = k
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = tohexstring(v)
        type = {'512': 'spex', '768': 'spexhss', '769': 'spexhsd', '1280': 'denm', '1281': 'denmhwf', '1408': 'iqe',
                '1536': 'dsnmnn', '1537': 'dsnmn1', '1538': 'dsnmn2', '1540': 'dsnm1n', '1541': 'dsnm11',
                '1542': 'dsnm12', '1544': 'dsnm2n', '1545': 'dsnm21', '1546': 'dsnm22', '1584': 'dsnmnnisdn',
                '1585': 'dsnmn1isdn', '1586': 'dsnmn2isdn', '1588': 'dsnm1nisdn', '1589': 'dsnm11isdn',
                '1590': 'dsnm12isdn', '1592': 'dsnm2nisdn', '1593': 'dsnm21isdn', '1594': 'dsnm22isdn',
                '1664': 'qsyncnm', '1792': 'mmfsdsas', '1793': 'mmfsddas', '1800': 'smfsdsas', '1801': 'smfsddas',
                '1808': 'mmscsas', '1809': 'mmscdas', '1825': 'smammbdas', '1833': 'mmasmbdas', '1856': 'mmfsdsashwf',
                '1857': 'mmfsddashwf', '1864': 'smfsdsashwf', '1865': 'smfsddashwf', '1872': 'mmscsashwf',
                '1873': 'mmscdashwf', '1889': 'smammbdashwf', '1897': 'mmasmbdashwf', '2048': 'dtnm', '2049': 'cam',
                '2176': 'iqtok', '2304': 'se100nm', '2560': 'asnqbri', '2816': 'mce1nm', '2944': 'dmct1nm',
                '3072': 'hwcompnm32', '3073': 'hwcompnm128', '3328': 'ahwcompnm32', '3329': 'ahwcompnm128',
                '3330': 'ahwcompnm256', '3584': 'shssinm', '8160': 'ds1e1atm', '8320': 'pmcdsync', '8000': 'fbrmbdfen',
                '8500': 'fvoippmcc', '8501': 'fvoipt1e1pmc', '8704': 'arnmbstr', '8720': 'arnmbsen',
                '8728': 'arnmbsfetx', '8729': 'arnmbsfefx', '8736': 'arnssync', '8752': 'arnv34', '8768': 'arndcsu',
                '8776': 'arnft1', '8780': 'arnfe1', '8784': 'arnisdns', '8800': 'arnisdnu', '8808': 'arnisdb',
                '8816': 'arnstkrg', '8832': 'arnsenet', '8848': 'arntsync', '8864': 'arnentsync', '8872': 'arne7sync',
                '8873': 'arn7sync', '8890': 'arnvoice', '8891': 'arnvoicedsync', '8972': 'arnpbe7sx10',
                '8880': 'arntrtsync', '8896': 'arnmbenx10', '8912': 'arnmbtrx10', '8928': 'arnpbenx10',
                '8944': 'arnpbtrx10', '8960': 'arnpbtenx10', '8976': 'arnpbttrx10', '16384': 'snm10t16',
                '16640': 'snm100t2', '16896': 'snmatmoc31mm', '16897': 'snmatmoc31dmm', '16898': 'snmatmoc31sm',
                '16899': 'snmatmoc31dsm', '17152': 'snmfddismm', '17153': 'snmfddisms', '17154': 'snmfddissm',
                '17155': 'snmfddisss', '17408': 'snm10f8', '17664': 'snm100f2', '17920': 'snm10t16p4',
                '18176': 'snm100t2p4', '18432': 'snm10t14100t1', '18688': 'snm100t16', '18944': 'snm10t14100f1',
                '524288': 'atm5000ah', '524544': 'atm5000bh'}
        k = self.snmpWalkValue('1.3.6.1.4.1.18.3.1.4.1.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.18.3.1.4.1.1.5')
        if k or r:
            if sizeof(k) >= sizeof(r):
                loop = sizeof(k)
            else:
                loop = sizeof(r)


        else:
            loop = 0
        for i in range(loop):
            if k[i]:
                if k[i] in type:
                    model.SerialNumber.Chassis[0].Module[i].Description = type[k[i]]
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = tohexstring(r[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB

