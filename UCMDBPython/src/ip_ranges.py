#coding=utf-8
#!/usr/bin/env python

import re

class IpRangeTester:
    NETMASKS = {
        '255.255.255.255': 32,
        '255.255.255.254': 31,
        '255.255.255.252': 30,
        '255.255.255.248': 29,
        '255.255.255.240': 28,
        '255.255.255.224': 27,
        '255.255.255.192': 26,
        '255.255.255.128': 25,
        '255.255.255.0': 24,
        '255.255.254.0': 23,
        '255.255.252.0': 22,
        '255.255.248.0': 21,
        '255.255.240.0': 20,
        '255.255.224.0': 19,
        '255.255.192.0': 18,
        '255.255.128.0': 17,
        '255.255.0.0': 16,
        '255.254.0.0': 15,
        '255.252.0.0': 14,
        '255.248.0.0': 13,
        '255.240.0.0': 12,
        '255.224.0.0': 11,
        '255.192.0.0': 10,
        '255.128.0.0': 9,
        '255.0.0.0': 8,
        '254.0.0.0': 7,
        '252.0.0.0': 6,
        '248.0.0.0': 5,
        '240.0.0.0': 4,
        '224.0.0.0': 3,
        '192.0.0.0': 2,
        '128.0.0.0': 1,
        '0.0.0.0': 0,
    }

    def __init__(self, ipranges):
        self.ipranges = self._split_ipranges(ipranges)

    def _split_ip(self, ip):
        octets = ip.split('.')
        if len(octets) != 4:
            raise ValueError('invalid octet count in IPv4')

        try:
            octets = map(int, octets)
        except ValueError:
            raise ValueError('IPv4 octet is not a number')

        for octet in octets:
            if not (0 <= octet <= 255):
                raise ValueError('IPv4 octet not in 0..255 range')

        return tuple(octets)

    def _split_ipranges(self, ipranges):
        brace_level = 0

        buff = []
        result = []

        for ch in ipranges:
            if ch == ',' and brace_level == 0:
                result.append(''.join(buff))
                buff = []
            else:
                if ch == '{':
                    brace_level += 1
                elif ch == '}':
                    brace_level -= 1

                buff.append(ch)

        result.append(''.join(buff))

        result = tuple(map(self._split_iprange, result))

        return tuple(result)

    def _split_ipspan(self, iprange):
        brace_level1, brace_level2 = 0, 0

        buff = []
        result = []

        for ch in iprange:
            if ch == '-' and (brace_level1 == 0) and (brace_level2 == 0):
                result.append(''.join(buff))
                buff = []
            else:
                if ch in '{':
                    brace_level1 += 1
                elif ch in '}':
                    brace_level1 -= 1
                elif ch in '[':
                    brace_level2 += 1
                elif ch in ']':
                    brace_level2 -= 1

                buff.append(ch)

        result.append(''.join(buff))

        return tuple(result)

    def _split_iprange(self, iprange):
        if ('-' in iprange) and ('/' in iprange):
            raise ValueError('span and network are mutually exclusive')

        if '/' in iprange:
            iprange_l = iprange.split('/')

            if len(iprange_l) != 2:
                raise ValueError('multiple "/" are not allowed')

            s_iprange = self._split_iprange_ip(iprange_l[0])

            try:
                ip = map(int, s_iprange)
            except ValueError:
                raise ValueError('malformed octet')

            for ip_part in ip:
                if not (0 <= ip_part <= 255):
                    raise ValueError('IP octet is not in range')

            ip = [[ip_part] for ip_part in ip]

            subnet = self._split_network(iprange_l[1])

            return (ip, subnet, 0)
        else:
            iprange_l = self._split_ipspan(iprange)

            if len(iprange_l) == 2:
                ip_from, ip_to = map(self._split_ip, iprange_l)

                f_oct = ip_from
                t_oct = ip_to
                s_oct = [f == t for (f, t) in zip(f_oct, t_oct)]
                r_oct = [xrange(f, t + 1) for (f, t) in zip(f_oct, t_oct)]

                return (zip(f_oct, t_oct, s_oct, r_oct), None, 1)

            elif len(iprange_l) == 1:
                # no netmask or subnet
                ip = self._split_iprange_ip(iprange_l[0])
                ip_exp = []

                for octet in ip:
                    ip_exp.append(self._expand_octet(octet))

                ip = ip_exp

                subnet = None

                return (ip, subnet, 0)
            else:
                raise ValueError('multiple "-" are not allowed')

    def _expand_octet(self, octet):
        if octet == '*':
            return range(0, 256) # 0..255 inclusive
        elif octet.startswith('[') and octet.endswith(']'):
            span_l = octet[1:-1].split('-')

            if len(span_l) == 2:
                span_from, span_to = map(int, span_l)

                return range(span_from, span_to + 1)
            else:
                raise ValueError('invalid octet span')
        elif octet.startswith('{') and octet.endswith('}'):
            result = []
            set_l = octet[1:-1].split(',')

            for set_i in set_l:
                set_span_l = set_i.split('-')
                len_set_span_l = len(set_span_l)

                if len_set_span_l == 2:
                    result.extend(range(int(set_span_l[0]), int(set_span_l[1]) + 1))
                elif len_set_span_l == 1:
                    result.append(int(set_i))
                else:
                    raise ValueError('invalid set element')

            # make list unique
            tmp = []

            for x in result:
                if x not in tmp:
                    tmp.append(x)

            return tmp
        else:
            try:
                return [int(octet)] # single
            except ValueError:
                raise ValueError('invalid octet value')

    def _split_network(self, network):
        try:
            subnet = int(network)
            if not (0 <= subnet <= 32):
                raise ValueError()

        except ValueError:
            # try netmask
            subnet = self.NETMASKS.get(network, None)
            if subnet is None:
                raise ValueError('invalid network')

        else:
            return subnet

    def _split_iprange_ip(self, iprange_ip):
        octets = iprange_ip.split('.')

        octet_count = len(octets)

        if octet_count > 4:
            raise ValueError('too much octets in iprange')
        elif octet_count == 0:
            raise ValueError('there should be at least one octet')
        else:
            if octets[-1] == '': # incomplete form
                del octets[-1]
                octets.extend(('*', ) * (4 - octet_count + 1))
            else:
                if octet_count != 4:
                    raise ValueError('not enough octets (end with dot to use incomplete form)')

        return octets

    def _test_iprange(self, ip, iprange):
        ip_l = self._split_ip(ip)
        iprange_l, subnet, isspan = iprange

        if subnet is not None:
            ip_long = long((ip_l[0] << 24) | (ip_l[1] << 16) | (ip_l[2] << 8) | ip_l[3])
            iprange_long = long((iprange_l[0][0] << 24) | (iprange_l[1][0] << 16) | (iprange_l[2][0] << 8) | iprange_l[3][0])
            subnet_long = long((2L ** 32) - (2L ** (32 - subnet)))

            if (ip_long & subnet_long) == (iprange_long & subnet_long):
                return 1
            else:
                return 0

        if isspan:
            (
                (f_oct0, t_oct0, s_oct0, r_oct0),
                (f_oct1, t_oct1, s_oct1, r_oct1),
                (f_oct2, t_oct2, s_oct2, r_oct2),
                (f_oct3, t_oct3, s_oct3, r_oct3),
            ) = iprange_l

            i_oct0, i_oct1, i_oct2, i_oct3 = ip_l

            if s_oct0 and s_oct1 and s_oct2 and s_oct3:
                return (i_oct0 == f_oct0) and (i_oct1 == f_oct1) and (i_oct2 == f_oct2) and (i_oct3 == f_oct3)
            elif s_oct0 and s_oct1 and s_oct2:
                return (i_oct0 == f_oct0) and (i_oct1 == f_oct1) and (i_oct2 == f_oct2) and (i_oct3 in r_oct3)
            elif s_oct0 and s_oct1:
                if not ((i_oct0 == f_oct0) and (i_oct1 == f_oct1)):
                    return 0

                if i_oct2 == f_oct2:
                    return i_oct3 >= f_oct3
                elif i_oct2 == t_oct2:
                    return i_oct3 <= t_oct3
                elif i_oct2 in xrange(f_oct2 + 1, t_oct2):
                    return 1

                return 0
            elif s_oct0:
                if not (i_oct0 == f_oct0):
                    return 0

                if i_oct1 == f_oct1:
                    return (i_oct2 >= f_oct2) and (i_oct3 >= f_oct3)
                elif i_oct1 == t_oct1:
                    return (i_oct2 <= t_oct2) and (i_oct3 <= t_oct3)
                elif i_oct1 in xrange(f_oct1 + 1, t_oct1):
                    return 1

                return 0
            else:
                if i_oct0 == f_oct0:
                    return (i_oct1 >= f_oct1) and (i_oct2 >= f_oct2) and (i_oct3 >= f_oct3)
                elif i_oct0 == t_oct0:
                    return (i_oct1 <= t_oct1) and (i_oct2 <= t_oct2) and (i_oct3 <= t_oct3)
                elif i_oct0 in xrange(f_oct0 + 1, t_oct0):
                    return 1

                return 0

            raise NotImplementedError()

        for src, dst in zip(ip_l, iprange_l):
            if src not in dst:
                return 0

        return 1

    def test(self, ip):
        for iprange in self.ipranges:
            if self._test_iprange(ip, iprange):
                return 1

        return 0

if __name__ == '__main__':
    import time

    tester = IpRangeTester('192.168.*.*')
    res = 0.0
    for x in xrange(100000):
        time1 = time.clock()
        tester.test('192.166.0.0')
        time2 = time.clock()
        res += time2 - time1


#r'''
#0.0.0.0
#0.0.0.  -> 0.0.0.*
#0.0.    -> 0.0.*.*
#0.      -> 0.*.*.*
#*.*.*.*
#0.0.0.0/0
#x.x.x.x/yy
#x.x.x.x/y.y.y.y
#x.x.[x-x].x
#x.x.{x,x,x,x-x,x-x,x}.x
#x.x.*.x
#x.x.x.x-y.y.y.y
#192.168.3.15-192.168.6.42
#3.15-3.255
#4.*
#5.*
#6.0-42
#
#1.0.0.0-2.0.0.0
#
#
#1.2.3.4,3.4.65.7,2.21.32.15,
#
#
#'''
