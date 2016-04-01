#coding=utf-8
#!/usr/bin/python
#
# Copyright 2007 Google Inc.
#  Licensed to PSF under a Contributor Agreement.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""A fast, lightweight IPv4/IPv6 manipulation library in Python.

This library is used to create/poke/manipulate IPv4 and IPv6 addresses
and networks.

"""
from appilog.common.utils import RangeType
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

__version__ = '2.1.9'
import struct
import types
IPV4LENGTH = 32L
IPV6LENGTH = 128L


def enumerate(iterable):
    return [(i, iterable[i]) for i in xrange(len(iterable))]


class AddressValueError(ValueError):
    """A Value Error related to the address."""


class NetmaskValueError(ValueError):
    """A Value Error related to the netmask."""


def IPAddress(address, version=None):
    """Take an IP string/int and return an object of the correct type.

    Args:
        address: A string or integer, the IP address.  Either IPv4 or
          IPv6 addresses may be supplied; integers less than 2**32 will
          be considered to be IPv4 by default.
        version: An Integer, 4 or 6. If set, don't try to automatically
          determine what the IP address type is. important for things
          like IPAddress(1), which could be IPv4, '0.0.0.1',  or IPv6,
          '::1'.

    Returns:
        An IPv4Address or IPv6Address object.

    Raises:
        ValueError: if the string passed isn't either a v4 or a v6
          address.

    """
    if version:
        if version == 4:
            return IPv4Address(address)
        elif version == 6:
            return IPv6Address(address)

    try:
        return IPv4Address(address)
    except (AddressValueError, NetmaskValueError):
        pass

    try:
        return IPv6Address(address)
    except (AddressValueError, NetmaskValueError):
        pass

    raise ValueError('%r does not appear to be an IPv4 or IPv6 address' %
                     address)


def IPNetwork(address, version=None, strict=None):
    """Take an IP string/int and return an object of the correct type.

    Args:
        address: A string or integer, the IP address.  Either IPv4 or
          IPv6 addresses may be supplied; integers less than 2**32 will
          be considered to be IPv4 by default.
        version: An Integer, if set, don't try to automatically
          determine what the IP address type is. important for things
          like IPNetwork(1), which could be IPv4, '0.0.0.1/32', or IPv6,
          '::1/128'.

    Returns:
        An IPv4Network or IPv6Network object.

    Raises:
        ValueError: if the string passed isn't either a v4 or a v6
          address. Or if a strict network was requested and a strict
          network wasn't given.

    """
    if version:
        if version == 4:
            return IPv4Network(address, strict)
        elif version == 6:
            return IPv6Network(address, strict)

    try:
        return IPv4Network(address, strict)
    except (AddressValueError, NetmaskValueError):
        pass

    try:
        return IPv6Network(address, strict)
    except (AddressValueError, NetmaskValueError):
        pass

    raise ValueError('%r does not appear to be an IPv4 or IPv6 network' %
                     address)


def v4_int_to_packed(address):
    """The binary representation of this address.

    Args:
        address: An integer representation of an IPv4 IP address.

    Returns:
        The binary representation of this address.

    Raises:
        ValueError: If the integer is too large to be an IPv4 IP
          address.
    """
    if address > _BaseV4._ALL_ONES:
        raise ValueError('Address too large for IPv4')
    return struct.pack('!I', address)


def v6_int_to_packed(address):
    """The binary representation of this address.

    Args:
        address: An integer representation of an IPv4 IP address.

    Returns:
        The binary representation of this address.
    """
    return struct.pack('!QQ', address >> 64, address & (2 ** 64 - 1))


def _find_address_range(addresses):
    """Find a sequence of addresses.

    Args:
        addresses: a list of IPv4 or IPv6 addresses.

    Returns:
        A tuple containing the first and last IP addresses in the sequence.

    """
    first = last = addresses[0]
    for ip in addresses[1:]:
        if ip._ip == last._ip + 1:
            last = ip
        else:
            break
    return (first, last)


def _get_prefix_length(number1, number2, bits):
    """Get the number of leading bits that are same for two numbers.

    Args:
        number1: an integer.
        number2: another integer.
        bits: the maximum number of bits to compare.

    Returns:
        The number of leading bits that are the same for two numbers.

    """
    for i in range(bits):
        if number1 >> i == number2 >> i:
            return bits - i
    return 0


def _count_righthand_zero_bits(number, bits):
    """Count the number of zero bits on the right hand side.

    Args:
        number: an integer.
        bits: maximum number of bits to count.

    Returns:
        The number of zero bits on the right hand side of the number.

    """
    if number == 0:
        return bits
    for i in range(bits):
        if (number >> i) % 2:
            return i


def summarize_address_range(first, last):
    """Summarize a network range given the first and last IP addresses.

    Example:
        >>> summarize_address_range(IPv4Address('1.1.1.0'),
            IPv4Address('1.1.1.130'))
        [IPv4Network('1.1.1.0/25'), IPv4Network('1.1.1.128/31'),
        IPv4Network('1.1.1.130/32')]

    Args:
        first: the first IPv4Address or IPv6Address in the range.
        last: the last IPv4Address or IPv6Address in the range.

    Returns:
        The address range collapsed to a list of IPv4Network's or
        IPv6Network's.

    Raise:
        TypeError:
            If the first and last objects are not IP addresses.
            If the first and last objects are not the same version.
        ValueError:
            If the last object is not greater than the first.
            If the version is not 4 or 6.

    """
    if not (isinstance(first, _BaseIP) and isinstance(last, _BaseIP)):
        raise TypeError('first and last must be IP addresses, not networks')
    if first.version != last.version:
        raise TypeError("%s and %s are not of the same version" % (
                str(first), str(last)))
    if first > last:
        raise ValueError('last IP address must be greater than first')

    networks = []

    if first.version == 4:
        ip = IPv4Network
    elif first.version == 6:
        ip = IPv6Network
    else:
        raise ValueError('unknown IP version')

    ip_bits = first._max_prefixlen
    first_int = first._ip
    last_int = last._ip
    while first_int <= last_int:
        nbits = _count_righthand_zero_bits(first_int, ip_bits)
        current = None
        while nbits >= 0:
            addend = 2 ** nbits - 1
            current = first_int + addend
            nbits -= 1
            if current <= last_int:
                break
        prefix = _get_prefix_length(first_int, current, ip_bits)
        net = ip('%s/%d' % (str(first), prefix))
        networks.append(net)
        if current == ip._ALL_ONES:
            break
        first_int = current + 1
        first = IPAddress(first_int, version=first._version)
    return networks


def _collapse_address_list_recursive(addresses):
    """Loops through the addresses, collapsing concurrent netblocks.

    Example:

        ip1 = IPv4Network'1.1.0.0/24')
        ip2 = IPv4Network'1.1.1.0/24')
        ip3 = IPv4Network'1.1.2.0/24')
        ip4 = IPv4Network'1.1.3.0/24')
        ip5 = IPv4Network'1.1.4.0/24')
        ip6 = IPv4Network'1.1.0.1/22')

        _collapse_address_list_recursive([ip1, ip2, ip3, ip4, ip5, ip6]) ->
          [IPv4Network('1.1.0.0/22'), IPv4Network('1.1.4.0/24')]

        This shouldn't be called directly; it is called via
          collapse_address_list([]).

    Args:
        addresses: A list of IPv4Network's or IPv6Network's

    Returns:
        A list of IPv4Network's or IPv6Network's depending on what we were
        passed.

    """
    ret_array = []
    optimized = None

    for cur_addr in addresses:
        if not ret_array:
            ret_array.append(cur_addr)
            continue
        if cur_addr in ret_array[-1]:
            optimized = 1
        elif cur_addr == ret_array[-1].supernet().subnet()[1]:
            ret_array.append(ret_array.pop().supernet())
            optimized = 1
        else:
            ret_array.append(cur_addr)

    if optimized:
        return _collapse_address_list_recursive(ret_array)

    return ret_array


def collapse_address_list(addresses):
    """Collapse a list of IP objects.

    Example:
        collapse_address_list([IPv4('1.1.0.0/24'), IPv4('1.1.1.0/24')]) ->
          [IPv4('1.1.0.0/23')]

    Args:
        addresses: A list of IPv4Network or IPv6Network objects.

    Returns:
        A list of IPv4Network or IPv6Network objects depending on what we
        were passed.

    Raises:
        TypeError: If passed a list of mixed version objects.

    """
    i = 0
    addrs = []
    ips = []
    nets = []

    # split IP addresses and networks
    for ip in addresses:
        if isinstance(ip, _BaseIP):
            if ips and ips[-1]._version != ip._version:
                raise TypeError("%s and %s are not of the same version" % (
                        str(ip), str(ips[-1])))
            ips.append(ip)
        elif ip._prefixlen == ip._max_prefixlen:
            if ips and ips[-1]._version != ip._version:
                raise TypeError("%s and %s are not of the same version" % (
                        str(ip), str(ips[-1])))
            ips.append(ip.ip)
        else:
            if nets and nets[-1]._version != ip._version:
                raise TypeError("%s and %s are not of the same version" % (
                        str(ip), str(ips[-1])))
            nets.append(ip)

    # sort and dedup
    ips.sort()
    nets.sort()

    while i < len(ips):
        (first, last) = _find_address_range(ips[i:])
        i = ips.index(last) + 1
        addrs.extend(summarize_address_range(first, last))
    all = addrs + nets
    return _collapse_address_list_recursive(all.sort(key=_BaseNet._get_networks_key))

# backwards compatibility
CollapseAddrList = collapse_address_list

# Test whether this Python implementation supports byte objects that
# are not identical to str ones.
# We need to exclude platforms where bytes == str so that we can
# distinguish between packed representations and strings, for example
# b'12::' (the IPv4 address 49.50.58.58) and '12::' (an IPv6 address).
try:
    _compat_has_real_bytes = bytes is not str
except NameError:  # <Python2.6
    _compat_has_real_bytes = None


def get_mixed_type_key(obj):
    """Return a key suitable for sorting between networks and addresses.

    Address and Network objects are not sortable by default; they're
    fundamentally different so the expression

        IPv4Address('1.1.1.1') <= IPv4Network('1.1.1.1/24')

    doesn't make any sense.  There are some times however, where you may wish
    to have ipaddr sort these for you anyway. If you need to do this, you
    can use this function as the key= argument to sorted().

    Args:
      obj: either a Network or Address object.
    Returns:
      appropriate key.

    """
    if isinstance(obj, _BaseNet):
        return obj._get_networks_key()
    elif isinstance(obj, _BaseIP):
        return obj._get_address_key()
    return NotImplemented


class _IPAddrBase:

    """The mother class."""

    def __index__(self):
        return self._ip

    def __int__(self):
        return self._ip

    def __long__(self):
        return long(self._ip)

    def __hex__(self):
        return hex(self._ip)

    def get_exploded(self):
        """Return the longhand version of the IP address as a string."""
        return self._explode_shorthand_ip_string()

    def get_compressed(self):
        """Return the shorthand version of the IP address as a string."""
        return str(self)

    def __getattr__(self, name):
        if name == 'compressed':
            return self.get_compressed()
        if name == 'exploded':
            return self.get_exploded()


class _BaseIP(_IPAddrBase):

    """A generic IP object.

    This IP class contains the version independent methods which are
    used by single IP addresses.

    """

    def __init__(self, address):
        if (not (_compat_has_real_bytes and isinstance(address, bytes))
            and '/' in str(address)):
            raise AddressValueError(address)

    def __eq__(self, other):
        try:
            return (self._ip == other._ip
                    and self._version == other._version)
        except AttributeError:
            return NotImplemented

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __le__(self, other):
        gt = self.__gt__(other)
        if gt is NotImplemented:
            return NotImplemented
        return not gt

    def __ge__(self, other):
        lt = self.__lt__(other)
        if lt is NotImplemented:
            return NotImplemented
        return not lt

    def __lt__(self, other):
        if self._version != other._version:
            raise TypeError('%s and %s are not of the same version' % (
                    str(self), str(other)))
        if not isinstance(other, _BaseIP):
            raise TypeError('%s and %s are not of the same type' % (
                    str(self), str(other)))
        if self._ip != other._ip:
            return self._ip < other._ip
        return None

    def __gt__(self, other):
        if self._version != other._version:
            raise TypeError('%s and %s are not of the same version' % (
                    str(self), str(other)))
        if not isinstance(other, _BaseIP):
            raise TypeError('%s and %s are not of the same type' % (
                    str(self), str(other)))
        if self._ip != other._ip:
            return self._ip > other._ip
        return None

    # Shorthand for Integer addition and subtraction. This is not
    # meant to ever support addition/subtraction of addresses.
    def __add__(self, other):
        if not isinstance(other, types.IntType):
            return NotImplemented
        return IPAddress(int(self) + other, version=self._version)

    def __sub__(self, other):
        if not isinstance(other, types.IntType):
            return NotImplemented
        return IPAddress(int(self) - other, version=self._version)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, str(self))

    def __str__(self):
        return  '%s' % self._string_from_ip_int(self._ip)

    def __hash__(self):
        return hash(hex(long(self._ip)))

    def __nonzero__(self):
        return 1

    def _get_address_key(self):
        return (self._version, self)

    def get_version(self):
        raise NotImplementedError('BaseIP has no version')

    def __getattr__(self, name):
        if name == 'version':
            return self.get_version()


class _BaseNet(_IPAddrBase):

    """A generic IP object.

    This IP class contains the version independent methods which are
    used by networks.

    """

    def __init__(self, address):
        self._cache = {}

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, str(self))

    def iterhosts(self):
        """Generate Iterator over usable hosts in a network.

           This is like __iter__ except it doesn't return the network
           or broadcast addresses.

        """
        cur = int(self.network) + 1
        bcast = int(self.broadcast) - 1
        result = []
        while cur <= bcast:
            cur += 1
            result.append(IPAddress(cur - 1, version=self._version))
        return result

    def __iter__(self):
        cur = int(self.network)
        bcast = int(self.broadcast)
        result = []
        while cur <= bcast:
            cur += 1
            result.append(IPAddress(cur - 1, version=self._version))
        return result

    def __getitem__(self, n):
        network = int(self.network)
        broadcast = int(self.broadcast)
        if n >= 0:
            if network + n > broadcast:
                raise IndexError
            return IPAddress(network + n, version=self._version)
        else:
            n += 1
            if broadcast + n < network:
                raise IndexError
            return IPAddress(broadcast + n, version=self._version)

    def __lt__(self, other):
        if self._version != other._version:
            raise TypeError('%s and %s are not of the same version' % (
                    str(self), str(other)))
        if not isinstance(other, _BaseNet):
            raise TypeError('%s and %s are not of the same type' % (
                    str(self), str(other)))
        if self.network != other.network:
            return self.network < other.network
        if self.netmask != other.netmask:
            return self.netmask < other.netmask
        return None

    def __gt__(self, other):
        if self._version != other._version:
            raise TypeError('%s and %s are not of the same version' % (
                    str(self), str(other)))
        if not isinstance(other, _BaseNet):
            raise TypeError('%s and %s are not of the same type' % (
                    str(self), str(other)))
        if self.network != other.network:
            return self.network > other.network
        if self.netmask != other.netmask:
            return self.netmask > other.netmask
        return None

    def __le__(self, other):
        gt = self.__gt__(other)
        if gt is NotImplemented:
            return NotImplemented
        return not gt

    def __ge__(self, other):
        lt = self.__lt__(other)
        if lt is NotImplemented:
            return NotImplemented
        return not lt

    def __eq__(self, other):
        try:
            return (self._version == other._version
                    and self.network == other.network
                    and int(self.netmask) == int(other.netmask))
        except AttributeError:
            if isinstance(other, _BaseIP):
                return (self._version == other._version
                        and self._ip == other._ip)

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __str__(self):
        return  '%s/%s' % (str(self.ip),
                           str(self._prefixlen))

    def __hash__(self):
        return hash(int(self.network) ^ int(self.netmask))

    def __contains__(self, other):
        # always None if one is v4 and the other is v6.
        if self._version != other._version:
            return None
        # dealing with another network.
        if isinstance(other, _BaseNet):
            return (self.network <= other.network and
                    self.broadcast >= other.broadcast)
        # dealing with another address
        else:
            return (long(self.network) <= long(other._ip) <=
                    long(self.broadcast))

    def overlaps(self, other):
        """Tell if self is partly contained in other."""
        return self.network in other or self.broadcast in other or (
            other.network in self or other.broadcast in self)

    def __nonzero__(self):
        return 1

    def __getattr__(self, name):
        if name == 'network':
            return self.get_network()
        if name == 'broadcast':
            return self.get_broadcast()
        if name == 'hostmask':
            return self.get_hostmask()
        if name == 'with_prefixlen':
            return self.get_with_prefixlen()
        if name == 'with_netmask':
            return self.get_with_netmask()
        if name == 'with_hostmask':
            return self.get_with_hostmask()
        if name == 'numhosts':
            return self.get_numhosts()
        if name == 'version':
            return self.get_version()
        if name == 'prefixlen':
            return self.get_prefixlen()

    def get_network(self):
        x = self._cache.get('network')
        if x is None:
            x = IPAddress(long(self._ip) & long(self.netmask), version=self._version)
            self._cache['network'] = x
        return x

    def get_broadcast(self):
        x = self._cache.get('broadcast')
        if x is None:
            x = IPAddress(long(self._ip) | long(self.hostmask), version=self._version)
            self._cache['broadcast'] = x
        return x

    def get_hostmask(self):
        x = self._cache.get('hostmask')
        if x is None:
            x = IPAddress(long(self.netmask) ^ self._ALL_ONES,
                          version=self._version)
            self._cache['hostmask'] = x
        return x

    def get_with_prefixlen(self):
        return '%s/%d' % (str(self.ip), self._prefixlen)

    def get_with_netmask(self):
        return '%s/%s' % (str(self.ip), str(self.netmask))

    def get_with_hostmask(self):
        return '%s/%s' % (str(self.ip), str(self.hostmask))

    def get_numhosts(self):
        """Number of hosts in the current subnet."""
        return long(self.broadcast) - long(self.network) + 1

    def get_version(self):
        raise NotImplementedError('BaseNet has no version')

    def get_prefixlen(self):
        return self._prefixlen

    def address_exclude(self, other):
        """Remove an address from a larger block.

        For example:

            addr1 = IPNetwork('10.1.1.0/24')
            addr2 = IPNetwork('10.1.1.0/26')
            addr1.address_exclude(addr2) =
                [IPNetwork('10.1.1.64/26'), IPNetwork('10.1.1.128/25')]

        or IPv6:

            addr1 = IPNetwork('::1/32')
            addr2 = IPNetwork('::1/128')
            addr1.address_exclude(addr2) = [IPNetwork('::0/128'),
                IPNetwork('::2/127'),
                IPNetwork('::4/126'),
                IPNetwork('::8/125'),
                ...
                IPNetwork('0:0:8000::/33')]

        Args:
            other: An IPvXNetwork object of the same type.

        Returns:
            A sorted list of IPvXNetwork objects addresses which is self
            minus other.

        Raises:
            TypeError: If self and other are of difffering address
              versions, or if other is not a network object.
            ValueError: If other is not completely contained by self.

        """
        if not self._version == other._version:
            raise TypeError("%s and %s are not of the same version" % (
                str(self), str(other)))

        if not isinstance(other, _BaseNet):
            raise TypeError("%s is not a network object" % str(other))

        if other not in self:
            raise ValueError('%s not contained in %s' % (str(other),
                                                         str(self)))
        if other == self:
            return []

        ret_addrs = []

        # Make sure we're comparing the network of other.
        other = IPNetwork('%s/%s' % (str(other.network), str(other.prefixlen)),
                   version=other._version)

        s1, s2 = self.subnet()
        while s1 != other and s2 != other:
            if other in s1:
                ret_addrs.append(s2)
                s1, s2 = s1.subnet()
            elif other in s2:
                ret_addrs.append(s1)
                s1, s2 = s2.subnet()
            else:
                # If we got here, there's a bug somewhere.
                raise ValueError('Error performing exclusion: '
                                       's1: %s s2: %s other: %s' %
                                       (str(s1), str(s2), str(other)))
        if s1 == other:
            ret_addrs.append(s2)
        elif s2 == other:
            ret_addrs.append(s1)
        else:
            # If we got here, there's a bug somewhere.
            raise ValueError('Error performing exclusion: '
                                   's1: %s s2: %s other: %s' %
                                   (str(s1), str(s2), str(other)))

        return ret_addrs.sort(key=_BaseNet._get_networks_key)

    def compare_networks(self, other):
        """Compare two IP objects.

        This is only concerned about the comparison of the integer
        representation of the network addresses.  This means that the
        host bits aren't considered at all in this method.  If you want
        to compare host bits, you can easily enough do a
        'HostA._ip < HostB._ip'

        Args:
            other: An IP object.

        Returns:
            If the IP versions of self and other are the same, returns:

            -1 if self < other:
              eg: IPv4('1.1.1.0/24') < IPv4('1.1.2.0/24')
              IPv6('1080::200C:417A') < IPv6('1080::200B:417B')
            0 if self == other
              eg: IPv4('1.1.1.1/24') == IPv4('1.1.1.2/24')
              IPv6('1080::200C:417A/96') == IPv6('1080::200C:417B/96')
            1 if self > other
              eg: IPv4('1.1.1.0/24') > IPv4('1.1.0.0/24')
              IPv6('1080::1:200C:417A/112') >
              IPv6('1080::0:200C:417A/112')

            If the IP versions of self and other are different, returns:

            -1 if self._version < other._version
              eg: IPv4('10.0.0.1/24') < IPv6('::1/128')
            1 if self._version > other._version
              eg: IPv6('::1/128') > IPv4('255.255.255.0/24')

        """
        if self._version < other._version:
            return -1
        if self._version > other._version:
            return 1
        # self._version == other._version below here:
        if self.network < other.network:
            return -1
        if self.network > other.network:
            return 1
        # self.network == other.network below here:
        if self.netmask < other.netmask:
            return -1
        if self.netmask > other.netmask:
            return 1
        # self.network == other.network and self.netmask == other.netmask
        return 0

    def _get_networks_key(self):
        """Network-only key function.

        Returns an object that identifies this address' network and
        netmask. This function is a suitable "key" argument for sorted()
        and list.sort().

        """
        return (self._version, self.network, self.netmask)

    def _ip_int_from_prefix(self, prefixlen=None):
        """Turn the prefix length netmask into a int for comparison.

        Args:
            prefixlen: An integer, the prefix length.

        Returns:
            An integer.

        """
        if not prefixlen and prefixlen != 0:
            prefixlen = self._prefixlen
        return self._ALL_ONES ^ (self._ALL_ONES >> prefixlen)

    def _prefix_from_ip_int(self, ip_int, mask=32):
        """Return prefix length from the decimal netmask.

        Args:
            ip_int: An integer, the IP address.
            mask: The netmask.  Defaults to 32.

        Returns:
            An integer, the prefix length.

        """
        while mask:
            if ip_int & 1 == 1:
                break
            ip_int >>= 1
            mask -= 1

        return mask

    def _ip_string_from_prefix(self, prefixlen=None):
        """Turn a prefix length into a dotted decimal string.

        Args:
            prefixlen: An integer, the netmask prefix length.

        Returns:
            A string, the dotted decimal netmask string.

        """
        if not prefixlen:
            prefixlen = self._prefixlen
        return self._string_from_ip_int(self._ip_int_from_prefix(prefixlen))

    def iter_subnets(self, prefixlen_diff=1, new_prefix=None):
        """The subnets which join to make the current subnet.

        In the case that self contains only one IP
        (self._prefixlen == 32 for IPv4 or self._prefixlen == 128
        for IPv6), return a list with just ourself.

        Args:
            prefixlen_diff: An integer, the amount the prefix length
              should be increased by. This should not be set if
              new_prefix is also set.
            new_prefix: The desired new prefix length. This must be a
              larger number (smaller prefix) than the existing prefix.
              This should not be set if prefixlen_diff is also set.

        Returns:
            An iterator of IPv(4|6) objects.

        Raises:
            ValueError: The prefixlen_diff is too small or too large.
                OR
            prefixlen_diff and new_prefix are both set or new_prefix
              is a smaller number than the current prefix (smaller
              number means a larger network)

        """
        if self._prefixlen == self._max_prefixlen:
            return self

        if new_prefix is not None:
            if new_prefix < self._prefixlen:
                raise ValueError('new prefix must be longer')
            if prefixlen_diff != 1:
                raise ValueError('cannot set prefixlen_diff and new_prefix')
            prefixlen_diff = new_prefix - self._prefixlen

        if prefixlen_diff < 0:
            raise ValueError('prefix length diff must be > 0')
        new_prefixlen = self._prefixlen + prefixlen_diff

        if not self._is_valid_netmask(str(new_prefixlen)):
            raise ValueError(
                'prefix length diff %d is invalid for netblock %s' % (
                    new_prefixlen, str(self)))

        first = IPNetwork('%s/%s' % (str(self.network),
                                     str(self._prefixlen + prefixlen_diff)),
                         version=self._version)

        return first
        current = first
        while 1:
            broadcast = current.broadcast
            if broadcast == self.broadcast:
                return
            new_addr = IPAddress(int(broadcast) + 1, version=self._version)
            current = IPNetwork('%s/%s' % (str(new_addr), str(new_prefixlen)),
                                version=self._version)

            return current

    def masked(self):
        """Return the network object with the host bits masked out."""
        return IPNetwork('%s/%d' % (self.network, self._prefixlen),
                         version=self._version)

    def subnet(self, prefixlen_diff=1, new_prefix=None):
        """Return a list of subnets, rather than an iterator."""
        return list(self.iter_subnets(prefixlen_diff, new_prefix))

    def supernet(self, prefixlen_diff=1, new_prefix=None):
        """The supernet containing the current network.

        Args:
            prefixlen_diff: An integer, the amount the prefix length of
              the network should be decreased by.  For example, given a
              /24 network and a prefixlen_diff of 3, a supernet with a
              /21 netmask is returned.

        Returns:
            An IPv4 network object.

        Raises:
            ValueError: If self.prefixlen - prefixlen_diff < 0. I.e., you have a
              negative prefix length.
                OR
            If prefixlen_diff and new_prefix are both set or new_prefix is a
              larger number than the current prefix (larger number means a
              smaller network)

        """
        if self._prefixlen == 0:
            return self

        if new_prefix is not None:
            if new_prefix > self._prefixlen:
                raise ValueError('new prefix must be shorter')
            if prefixlen_diff != 1:
                raise ValueError('cannot set prefixlen_diff and new_prefix')
            prefixlen_diff = self._prefixlen - new_prefix

        if self.prefixlen - prefixlen_diff < 0:
            raise ValueError(
                'current prefixlen is %d, cannot have a prefixlen_diff of %d' %
                (self.prefixlen, prefixlen_diff))
        return IPNetwork('%s/%s' % (str(self.network),
                                    str(self.prefixlen - prefixlen_diff)),
                         version=self._version)

    # backwards compatibility
    Subnet = subnet
    Supernet = supernet
    AddressExclude = address_exclude
    CompareNetworks = compare_networks
    Contains = __contains__


class _BaseV4:

    """Base IPv4 object.

    The following methods are used by IPv4 objects in both single IP
    addresses and networks.

    """

    # Equivalent to 255.255.255.255 or 32 bits of 1's.
    _ALL_ONES = (2 ** IPV4LENGTH) - 1

    def __init__(self, address):
        self._version = 4
        self._max_prefixlen = IPV4LENGTH

    def _explode_shorthand_ip_string(self, ip_str=None):
        if not ip_str:
            ip_str = str(self)
        return ip_str

    def _ip_int_from_string(self, ip_str):
        """Turn the given IP string into an integer for comparison.

        Args:
            ip_str: A string, the IP ip_str.

        Returns:
            The IP ip_str as an integer.

        Raises:
            AddressValueError: if the string isn't a valid IP string.

        """
        packed_ip = 0
        octets = ip_str.split('.')
        if len(octets) != 4:
            raise AddressValueError(ip_str)
        for oc in octets:
            try:
                packed_ip = (packed_ip << 8) | int(oc)
            except ValueError:
                raise AddressValueError(ip_str)
        return packed_ip

    def _string_from_ip_int(self, ip_int):
        """Turns a 32-bit integer into dotted decimal notation.

        Args:
            ip_int: An integer, the IP address.

        Returns:
            The IP address as a string in dotted decimal notation.

        """
        octets = []
        for _ in xrange(4):
            octets.insert(0, str(ip_int & 0xFF))
            ip_int >>= 8
        return '.'.join(octets)

    def _is_valid_ip(self, address):
        """Validate the dotted decimal notation IP/netmask string.

        Args:
            address: A string, either representing a quad-dotted ip
                or an integer which is a valid IPv4 IP address.

        Returns:
            A boolean, True if the string is a valid dotted decimal IP
            string.

        """
        octets = address.split('.')
        if len(octets) == 1:
            # We have an integer rather than a dotted decimal IP.
            try:
                return int(address) >= 0 and int(address) <= self._ALL_ONES
            except ValueError:
                return None

        if len(octets) != 4:
            return None

        for octet in octets:
            try:
                if not 0 <= int(octet) <= 255:
                    return None
            except ValueError:
                return None
        return 1

    def __getattr__(self, name):
        if name == 'max_prefixlen':
            return self.get_max_prefixlen()
        if name == 'packed':
            return self.get_packed()
        if name == 'version':
            return self.get_version()
        if name == 'is_reserved':
            return self.get_is_reserved()
        if name == 'is_private':
            return self.get_is_private()
        if name == 'is_multicast':
            return self.get_is_multicast()
        if name == 'is_unspecified':
            return self.get_is_unspecified()
        if name == 'is_loopback':
            return self.get_is_loopback()
        if name == 'is_link_local':
            return self.get_is_link_local()
        if name == 'network':
            return self.get_network()
        if name == 'broadcast':
            return self.get_broadcast()
        if name == 'hostmask':
            return self.get_hostmask()
        if name == 'with_prefixlen':
            return self.get_with_prefixlen()
        if name == 'with_netmask':
            return self.get_with_netmask()
        if name == 'with_hostmask':
            return self.get_with_hostmask()
        if name == 'numhosts':
            return self.get_numhosts()
        if name == 'version':
            return self.get_version()
        if name == 'prefixlen':
            return self.get_prefixlen()
        if name == 'compressed':
            return self.get_compressed()
        if name == 'exploded':
            return self.get_exploded()

    def get_max_prefixlen(self):
        return self._max_prefixlen

    def get_packed(self):
        """The binary representation of this address."""
        return v4_int_to_packed(self._ip)

    def get_version(self):
        return self._version

    def get_is_reserved(self):
        """Test if the address is otherwise IETF reserved.
         Returns:
             A boolean, True if the address is within the
             reserved IPv4 Network range.
        """
        return self in IPv4Network('240.0.0.0/4')

    def get_is_private(self):
        """Test if this address is allocated for private networks.

        Returns:
            A boolean, True if the address is reserved per RFC 1918.

        """
        return (self in IPv4Network('10.0.0.0/8') or
                self in IPv4Network('172.16.0.0/12') or
                self in IPv4Network('192.168.0.0/16'))

    def get_is_multicast(self):
        """Test if the address is reserved for multicast use.

        Returns:
            A boolean, True if the address is multicast.
            See RFC 3171 for details.

        """
        return self in IPv4Network('224.0.0.0/4')

    def get_is_unspecified(self):
        """Test if the address is unspecified.

        Returns:
            A boolean, True if this is the unspecified address as defined in
            RFC 5735 3.

        """
        return self in IPv4Network('0.0.0.0')

    def get_is_loopback(self):
        """Test if the address is a loopback address.

        Returns:
            A boolean, True if the address is a loopback per RFC 3330.

        """
        return self in IPv4Network('127.0.0.0/8')

    def get_is_link_local(self):
        """Test if the address is reserved for link-local.

        Returns:
            A boolean, True if the address is link-local per RFC 3927.

        """
        return self in IPv4Network('169.254.0.0/16')


class IPv4Address(_BaseV4, _BaseIP):

    """Represent and manipulate single IPv4 Addresses."""

    def __init__(self, address):

        """
        Args:
            address: A string or integer representing the IP
              '192.168.1.1'

              Additionally, an integer can be passed, so
              IPv4Address('192.168.1.1') == IPv4Address(3232235777).
              or, more generally
              IPv4Address(int(IPv4Address('192.168.1.1'))) ==
                IPv4Address('192.168.1.1')

        Raises:
            AddressValueError: If ipaddr isn't a valid IPv4 address.

        """
        _BaseIP.__init__(self, address)
        _BaseV4.__init__(self, address)

        # Efficient constructor from integer.
        if isinstance(address, types.IntType) or isinstance(address, types.LongType):
            self._ip = address
            if address < 0 or address > self._ALL_ONES:
                raise AddressValueError(address)
            return

        # Constructing from a packed address
        if _compat_has_real_bytes:
            if isinstance(address, bytes) and len(address) == 4:
                self._ip = struct.unpack('!I', address)[0]
                return

        # Assume input argument to be string or any object representation
        # which converts into a formatted IP string.
        addr_str = str(address)
        if not self._is_valid_ip(addr_str):
            raise AddressValueError(addr_str)

        self._ip = self._ip_int_from_string(addr_str)


class IPv4Network(_BaseV4, _BaseNet):

    """This class represents and manipulates 32-bit IPv4 networks.

    Attributes: [examples for IPv4Network('1.2.3.4/27')]
        ._ip: 16909060
        .ip: IPv4Address('1.2.3.4')
        .network: IPv4Address('1.2.3.0')
        .hostmask: IPv4Address('0.0.0.31')
        .broadcast: IPv4Address('1.2.3.31')
        .netmask: IPv4Address('255.255.255.224')
        .prefixlen: 27

    """

    # the valid octets for host and netmasks. only useful for IPv4.
    _valid_mask_octets = (255, 254, 252, 248, 240, 224, 192, 128, 0)

    def __init__(self, address, strict=None):
        """Instantiate a new IPv4 network object.

        Args:
            address: A string or integer representing the IP [& network].
              '192.168.1.1/24'
              '192.168.1.1/255.255.255.0'
              '192.168.1.1/0.0.0.255'
              are all functionally the same in IPv4. Similarly,
              '192.168.1.1'
              '192.168.1.1/255.255.255.255'
              '192.168.1.1/32'
              are also functionaly equivalent. That is to say, failing to
              provide a subnetmask will create an object with a mask of /32.

              If the mask (portion after the / in the argument) is given in
              dotted quad form, it is treated as a netmask if it starts with a
              non-zero field (e.g. /255.0.0.0 == /8) and as a hostmask if it
              starts with a zero field (e.g. 0.255.255.255 == /8), with the
              single exception of an all-zero mask which is treated as a
              netmask == /0. If no mask is given, a default of /32 is used.

              Additionally, an integer can be passed, so
              IPv4Network('192.168.1.1') == IPv4Network(3232235777).
              or, more generally
              IPv4Network(int(IPv4Network('192.168.1.1'))) ==
                IPv4Network('192.168.1.1')

            strict: A boolean. If true, ensure that we have been passed
              A true network address, eg, 192.168.1.0/24 and not an
              IP address on a network, eg, 192.168.1.1/24.

        Raises:
            AddressValueError: If ipaddr isn't a valid IPv4 address.
            NetmaskValueError: If the netmask isn't valid for
              an IPv4 address.
            ValueError: If strict was True and a network address was not
              supplied.

        """
        _BaseNet.__init__(self, address)
        _BaseV4.__init__(self, address)

        # Efficient constructor from integer.
        if isinstance(address, (types.IntType, types.LongType)):
            self._ip = address
            self.ip = IPv4Address(self._ip)
            self._prefixlen = self._max_prefixlen
            self.netmask = IPv4Address(self._ALL_ONES)
            if address < 0 or address > self._ALL_ONES:
                raise AddressValueError(address)
            return

        # Constructing from a packed address
        if _compat_has_real_bytes:
            if isinstance(address, bytes) and len(address) == 4:
                self._ip = struct.unpack('!I', address)[0]
                self.ip = IPv4Address(self._ip)
                self._prefixlen = self._max_prefixlen
                self.netmask = IPv4Address(self._ALL_ONES)
                return

        # Assume input argument to be string or any object representation
        # which converts into a formatted IP prefix string.
        addr = str(address).split('/')

        if len(addr) > 2:
            raise AddressValueError(address)

        if not self._is_valid_ip(addr[0]):
            raise AddressValueError(addr[0])

        self._ip = self._ip_int_from_string(addr[0])
        self.ip = IPv4Address(self._ip)

        if len(addr) == 2:
            mask = addr[1].split('.')
            if len(mask) == 4:
                # We have dotted decimal netmask.
                if self._is_valid_netmask(addr[1]):
                    self.netmask = IPv4Address(self._ip_int_from_string(
                            addr[1]))
                elif self._is_hostmask(addr[1]):
                    self.netmask = IPv4Address(
                        self._ip_int_from_string(addr[1]) ^ self._ALL_ONES)
                else:
                    raise NetmaskValueError('%s is not a valid netmask'
                                                     % addr[1])

                self._prefixlen = self._prefix_from_ip_int(int(self.netmask))
            else:
                # We have a netmask in prefix length form.
                if not self._is_valid_netmask(addr[1]):
                    raise NetmaskValueError(addr[1])
                self._prefixlen = int(addr[1])
                self.netmask = IPv4Address(self._ip_int_from_prefix(
                    self._prefixlen))
        else:
            self._prefixlen = self._max_prefixlen
            self.netmask = IPv4Address(self._ip_int_from_prefix(
                self._prefixlen))
        if strict:
            if self.ip != self.network:
                raise ValueError('%s has host bits set' %
                                 self.ip)

    def _is_hostmask(self, ip_str):
        """Test if the IP string is a hostmask (rather than a netmask).

        Args:
            ip_str: A string, the potential hostmask.

        Returns:
            A boolean, True if the IP string is a hostmask.

        """
        bits = ip_str.split('.')
        try:
            parts = [int(x) for x in bits if int(x) in self._valid_mask_octets]
        except ValueError:
            return None
        if len(parts) != len(bits):
            return None
        if parts[0] < parts[-1]:
            return 1
        return None

    def _is_valid_netmask(self, netmask):
        """Verify that the netmask is valid.

        Args:
            netmask: A string, either a prefix or dotted decimal
              netmask.

        Returns:
            A boolean, True if the prefix represents a valid IPv4
            netmask.

        """
        mask = netmask.split('.')
        if len(mask) == 4:
            if [x for x in mask if int(x) not in self._valid_mask_octets]:
                return None
            if [y for idx, y in enumerate(mask) if idx > 0 and
                y > mask[idx - 1]]:
                return None
            return 1
        try:
            netmask = int(netmask)
        except ValueError:
            return None
        return 0 <= netmask <= self._max_prefixlen

    # backwards compatibility
    IsRFC1918 = lambda self: self.is_private
    IsMulticast = lambda self: self.is_multicast
    IsLoopback = lambda self: self.is_loopback
    IsLinkLocal = lambda self: self.is_link_local


class _BaseV6:

    """Base IPv6 object.

    The following methods are used by IPv6 objects in both single IP
    addresses and networks.

    """

    _ALL_ONES = (2 ** IPV6LENGTH) - 1

    def __init__(self, address):
        self._version = 6
        self._max_prefixlen = IPV6LENGTH

    def _ip_int_from_string(self, ip_str=None):
        """Turn an IPv6 ip_str into an integer.

        Args:
            ip_str: A string, the IPv6 ip_str.

        Returns:
            A long, the IPv6 ip_str.

        Raises:
           AddressValueError: if ip_str isn't a valid IP Address.

        """
        if not ip_str:
            ip_str = str(self.ip)

        ip_int = 0L

        # Do we have an IPv4 mapped (::ffff:a.b.c.d) or compact (::a.b.c.d)
        # ip_str?
        fields = ip_str.split(':')
        if fields[-1].count('.') == 3:
            ipv4_string = fields.pop()
            ipv4_int = IPv4Network(ipv4_string)._ip
            octets = []
            for _ in xrange(2):
                octets.append(hex(ipv4_int & 0xFFFF).lstrip('0x').rstrip('L'))
                ipv4_int >>= 16
            octets.reverse()
            fields.extend(octets)
            ip_str = ':'.join(fields)

        fields = self._explode_shorthand_ip_string(ip_str).split(':')
        for field in fields:
            try:
                ip_int = (ip_int << 16) + int(field or '0', 16)
            except ValueError:
                raise AddressValueError(ip_str)

        return ip_int

    def _compress_hextets(self, hextets):
        """Compresses a list of hextets.

        Compresses a list of strings, replacing the longest continuous
        sequence of "0" in the list with "" and adding empty strings at
        the beginning or at the end of the string such that subsequently
        calling ":".join(hextets) will produce the compressed version of
        the IPv6 address.

        Args:
            hextets: A list of strings, the hextets to compress.

        Returns:
            A list of strings.

        """
        best_doublecolon_start = -1
        best_doublecolon_len = 0
        doublecolon_start = -1
        doublecolon_len = 0
        for index in range(len(hextets)):
            if hextets[index] == '0':
                doublecolon_len += 1
                if doublecolon_start == -1:
                    # Start of a sequence of zeros.
                    doublecolon_start = index
                if doublecolon_len > best_doublecolon_len:
                    # This is the longest sequence of zeros so far.
                    best_doublecolon_len = doublecolon_len
                    best_doublecolon_start = doublecolon_start
            else:
                doublecolon_len = 0
                doublecolon_start = -1

        if best_doublecolon_len > 1:
            best_doublecolon_end = (best_doublecolon_start +
                                    best_doublecolon_len)
            # For zeros at the end of the address.
            if best_doublecolon_end == len(hextets):
                hextets += ['']
            hextets[best_doublecolon_start:best_doublecolon_end] = ['']
            # For zeros at the beginning of the address.
            if best_doublecolon_start == 0:
                hextets = [''] + hextets

        return hextets

    def _string_from_ip_int(self, ip_int=None):
        """Turns a 128-bit integer into hexadecimal notation.

        Args:
            ip_int: An integer, the IP address.

        Returns:
            A string, the hexadecimal representation of the address.

        Raises:
            ValueError: The address is bigger than 128 bits of all ones.

        """
        if not ip_int and ip_int != 0:
            ip_int = int(self._ip)

        if ip_int > self._ALL_ONES:
            raise ValueError('IPv6 address is too large')

        hex_str = '%032x' % ip_int
        hextets = []
        for x in range(0, 32, 4):
            hextets.append('%x' % int(hex_str[x: x + 4], 16))

        hextets = self._compress_hextets(hextets)
        return ':'.join(hextets)

    def _explode_shorthand_ip_string(self, ip_str=None):
        """Expand a shortened IPv6 address.

        Args:
            ip_str: A string, the IPv6 address.

        Returns:
            A string, the expanded IPv6 address.

        """
        if not ip_str:
            ip_str = str(self)
            if isinstance(self, _BaseNet):
                ip_str = str(self.ip)

        if self._is_shorthand_ip(ip_str):
            new_ip = []
            hextet = ip_str.split('::')

            if len(hextet) > 1:
                sep = len(hextet[0].split(':')) + len(hextet[1].split(':'))
                new_ip = hextet[0].split(':')

                for _ in xrange(8 - sep):
                    new_ip.append('0000')
                new_ip += hextet[1].split(':')

            else:
                new_ip = ip_str.split(':')
            # Now need to make sure every hextet is 4 lower case characters.
            # If a hextet is < 4 characters, we've got missing leading 0's.
            ret_ip = []
            for hextet in new_ip:
                ret_ip.append(('0' * (4 - len(hextet)) + hextet).lower())
            return ':'.join(ret_ip)
        # We've already got a longhand ip_str.
        return ip_str

    def _is_valid_ip(self, ip_str):
        """Ensure we have a valid IPv6 address.

        Probably not as exhaustive as it should be.

        Args:
            ip_str: A string, the IPv6 address.

        Returns:
            A boolean, True if this is a valid IPv6 address.

        """
        # We need to have at least one ':'.
        if ':' not in ip_str:
            return None

        # We can only have one '::' shortener.
        if ip_str.count('::') > 1:
            return None

        # '::' should be encompassed by start, digits or end.
        if ip_str.find(':::') != -1:
            return None

        # A single colon can neither start nor end an address.
        if ((ip_str.startswith(':') and not ip_str.startswith('::')) or
                (ip_str.endswith(':') and not ip_str.endswith('::'))):
            return None

        # If we have no concatenation, we need to have 8 fields with 7 ':'.
        if ip_str.find('::') == -1 and ip_str.count(':') != 7:
            # We might have an IPv4 mapped address.
            if ip_str.count('.') != 3:
                return None

        ip_str = self._explode_shorthand_ip_string(ip_str)

        # Now that we have that all squared away, let's check that each of the
        # hextets are between 0x0 and 0xFFFF.
        for hextet in ip_str.split(':'):
            if hextet.count('.') == 3:
                # If we have an IPv4 mapped address, the IPv4 portion has to
                # be at the end of the IPv6 portion.
                if not ip_str.split(':')[-1] == hextet:
                    return None
                try:
                    IPv4Network(hextet)
                except AddressValueError:
                    return None
            else:
                try:
                    # a value error here means that we got a bad hextet,
                    # something like 0xzzzz
                    if int(hextet, 16) < 0x0 or int(hextet, 16) > 0xFFFF:
                        return None
                except ValueError:
                    return None
        return 1

    def _is_shorthand_ip(self, ip_str=None):
        """Determine if the address is shortened.

        Args:
            ip_str: A string, the IPv6 address.

        Returns:
            A boolean, True if the address is shortened.

        """
        if ip_str.count('::') == 1:
            return 1
        if filter(lambda x: len(x) < 4, ip_str.split(':')):
            return 1
        return None

    def __getattr__(self, name):
        if name == 'max_prefixlen':
            return self.get_max_prefixlen()
        if name == 'packed':
            return self.get_packed()
        if name == 'version':
            return self.get_version()
        if name == 'is_multicast':
            return self.get_is_multicast()
        if name == 'is_reserved':
            return self.get_is_reserved()
        if name == 'is_unspecified':
            return self.get_is_unspecified()
        if name == 'is_loopback':
            return self.get_is_loopback()
        if name == 'is_link_local':
            return self.get_is_link_local()
        if name == 'is_site_local':
            return self.get_is_site_local()
        if name == 'is_private':
            return self.get_is_private()
        if name == 'ipv4_mapped':
            return self.get_ipv4_mapped()
        if name == 'teredo':
            return self.get_teredo()
        if name == 'sixtofour':
            return self.get_sixtofour()
        if name == 'compressed':
            return self.get_compressed()
        if name == 'exploded':
            return self.get_exploded()
        if name == 'network':
            return self.get_network()
        if name == 'broadcast':
            return self.get_broadcast()

    def get_max_prefixlen(self):
        return self._max_prefixlen

    def get_packed(self):
        """The binary representation of this address."""
        return v6_int_to_packed(self._ip)

    def get_version(self):
        return self._version

    def get_is_multicast(self):
        """Test if the address is reserved for multicast use.

        Returns:
            A boolean, True if the address is a multicast address.
            See RFC 2373 2.7 for details.

        """
        return self in IPv6Network('ff00::/8')

    def get_is_reserved(self):
        """Test if the address is otherwise IETF reserved.

        Returns:
            A boolean, True if the address is within one of the
            reserved IPv6 Network ranges.

        """
        return (self in IPv6Network('::/8') or
                self in IPv6Network('100::/8') or
                self in IPv6Network('200::/7') or
                self in IPv6Network('400::/6') or
                self in IPv6Network('800::/5') or
                self in IPv6Network('1000::/4') or
                self in IPv6Network('4000::/3') or
                self in IPv6Network('6000::/3') or
                self in IPv6Network('8000::/3') or
                self in IPv6Network('A000::/3') or
                self in IPv6Network('C000::/3') or
                self in IPv6Network('E000::/4') or
                self in IPv6Network('F000::/5') or
                self in IPv6Network('F800::/6') or
                self in IPv6Network('FE00::/9'))

    def get_is_unspecified(self):
        """Test if the address is unspecified.

        Returns:
            A boolean, True if this is the unspecified address as defined in
            RFC 2373 2.5.2.

        """
        _prefixlen = getattr(self, '_prefixlen')
        if _prefixlen is None:
            _prefixlen = 128
        return self._ip == 0 and _prefixlen == 128

    def get_is_loopback(self):
        """Test if the address is a loopback address.

        Returns:
            A boolean, True if the address is a loopback address as defined in
            RFC 2373 2.5.3.

        """
        _prefixlen = getattr(self, '_prefixlen')
        if _prefixlen is None:
            _prefixlen = 128
        return self._ip == 1 and _prefixlen == 128

    def get_is_link_local(self):
        """Test if the address is reserved for link-local.

        Returns:
            A boolean, True if the address is reserved per RFC 4291.

        """
        return self in IPv6Network('fe80::/10')

    def get_is_site_local(self):
        """Test if the address is reserved for site-local.

        Note that the site-local address space has been deprecated by RFC 3879.
        Use is_private to test if this address is in the space of unique local
        addresses as defined by RFC 4193.

        Returns:
            A boolean, True if the address is reserved per RFC 3513 2.5.6.

        """
        return self in IPv6Network('fec0::/10')

    def get_is_private(self):
        """Test if this address is allocated for private networks.

        Returns:
            A boolean, True if the address is reserved per RFC 4193.

        """
        return self in IPv6Network('fc00::/7')

    def get_ipv4_mapped(self):
        """Return the IPv4 mapped address.

        Returns:
            If the IPv6 address is a v4 mapped address, return the
            IPv4 mapped address. Return None otherwise.

        """
        hextets = self._explode_shorthand_ip_string().split(':')
        if hextets[-3] != 'ffff':
            return None
        try:
            return IPv4Address(int('%s%s' % (hextets[-2], hextets[-1]), 16))
        except AddressValueError:
            return None

    def get_teredo(self):
        """Tuple of embedded teredo IPs.

        Returns:
            Tuple of the (server, client) IPs or None if the address
            doesn't appear to be a teredo address (doesn't start with
            2001)

        """
        bits = self._explode_shorthand_ip_string().split(':')
        if not bits[0] == '2001':
            return None
        return (IPv4Address(int(''.join(bits[2:4]), 16)),
                IPv4Address(int(''.join(bits[6:]), 16) ^ 0xFFFFFFFF))

    def get_sixtofour(self):
        """Return the IPv4 6to4 embedded address.

        Returns:
            The IPv4 6to4-embedded address if present or None if the
            address doesn't appear to contain a 6to4 embedded address.

        """
        bits = self._explode_shorthand_ip_string().split(':')
        if not bits[0] == '2002':
            return None
        return IPv4Address(int(''.join(bits[1:3]), 16))


class IPv6Address(_BaseV6, _BaseIP):

    """Represent and manipulate single IPv6 Addresses.
    """

    def __init__(self, address):
        """Instantiate a new IPv6 address object.

        Args:
            address: A string or integer representing the IP

              Additionally, an integer can be passed, so
              IPv6Address('2001:4860::') ==
                IPv6Address(42541956101370907050197289607612071936L).
              or, more generally
              IPv6Address(IPv6Address('2001:4860::')._ip) ==
                IPv6Address('2001:4860::')

        Raises:
            AddressValueError: If address isn't a valid IPv6 address.

        """
        _BaseIP.__init__(self, address)
        _BaseV6.__init__(self, address)

        # Efficient constructor from integer.
        if isinstance(address, types.IntType) or  isinstance(address, types.LongType):
            self._ip = address
            if address < 0 or address > self._ALL_ONES:
                raise AddressValueError(address)
            return

        # Constructing from a packed address
        if _compat_has_real_bytes:
            if isinstance(address, bytes) and len(address) == 16:
                tmp = struct.unpack('!QQ', address)
                self._ip = (tmp[0] << 64) | tmp[1]
                return

        # Assume input argument to be string or any object representation
        # which converts into a formatted IP string.
        addr_str = str(address)
        if not addr_str:
            raise AddressValueError('')

        if not self._is_valid_ip(addr_str):
            raise AddressValueError(addr_str)

        self._ip = self._ip_int_from_string(addr_str)


class IPv6Network(_BaseV6, _BaseNet):

    """This class represents and manipulates 128-bit IPv6 networks.

    Attributes: [examples for IPv6('2001:658:22A:CAFE:200::1/64')]
        .ip: IPv6Address('2001:658:22a:cafe:200::1')
        .network: IPv6Address('2001:658:22a:cafe::')
        .hostmask: IPv6Address('::ffff:ffff:ffff:ffff')
        .broadcast: IPv6Address('2001:658:22a:cafe:ffff:ffff:ffff:ffff')
        .netmask: IPv6Address('ffff:ffff:ffff:ffff::')
        .prefixlen: 64

    """

    def __init__(self, address, strict=None):
        """Instantiate a new IPv6 Network object.

        Args:
            address: A string or integer representing the IPv6 network or the IP
              and prefix/netmask.
              '2001:4860::/128'
              '2001:4860:0000:0000:0000:0000:0000:0000/128'
              '2001:4860::'
              are all functionally the same in IPv6.  That is to say,
              failing to provide a subnetmask will create an object with
              a mask of /128.

              Additionally, an integer can be passed, so
              IPv6Network('2001:4860::') ==
                IPv6Network(42541956101370907050197289607612071936L).
              or, more generally
              IPv6Network(IPv6Network('2001:4860::')._ip) ==
                IPv6Network('2001:4860::')

            strict: A boolean. If true, ensure that we have been passed
              A true network address, eg, 192.168.1.0/24 and not an
              IP address on a network, eg, 192.168.1.1/24.

        Raises:
            AddressValueError: If address isn't a valid IPv6 address.
            NetmaskValueError: If the netmask isn't valid for
              an IPv6 address.
            ValueError: If strict was True and a network address was not
              supplied.

        """
        _BaseNet.__init__(self, address)
        _BaseV6.__init__(self, address)

        # Efficient constructor from integer.
        if isinstance(address, types.IntType) or isinstance(address, types.LongType):
            self._ip = address
            self.ip = IPv6Address(self._ip)
            self._prefixlen = self._max_prefixlen
            self.netmask = IPv6Address(self._ALL_ONES)
            if address < 0 or address > self._ALL_ONES:
                raise AddressValueError(address)
            return

        # Constructing from a packed address
        if _compat_has_real_bytes:
            if isinstance(address, bytes) and len(address) == 16:
                tmp = struct.unpack('!QQ', address)
                self._ip = (tmp[0] << 64) | tmp[1]
                self.ip = IPv6Address(self._ip)
                self._prefixlen = self._max_prefixlen
                self.netmask = IPv6Address(self._ALL_ONES)
                return

        # Assume input argument to be string or any object representation
        # which converts into a formatted IP prefix string.
        addr = str(address).split('/')

        if len(addr) > 2:
            raise AddressValueError(address)

        if not self._is_valid_ip(addr[0]):
            raise AddressValueError(addr[0])

        if len(addr) == 2:
            if self._is_valid_netmask(addr[1]):
                self._prefixlen = int(addr[1])
            else:
                raise NetmaskValueError(addr[1])
        else:
            self._prefixlen = self._max_prefixlen

        self.netmask = IPv6Address(self._ip_int_from_prefix(self._prefixlen))

        self._ip = self._ip_int_from_string(addr[0])
        self.ip = IPv6Address(self._ip)

        if strict:
            if self.ip != self.network:
                raise ValueError('%s has host bits set' %
                                 self.ip)

    def _is_valid_netmask(self, prefixlen):
        """Verify that the netmask/prefixlen is valid.

        Args:
            prefixlen: A string, the netmask in prefix length format.

        Returns:
            A boolean, True if the prefix represents a valid IPv6
            netmask.

        """
        try:
            prefixlen = int(prefixlen)
        except ValueError:
            return None
        return 0 <= prefixlen <= self._max_prefixlen

    def __getattr__(self, name):
        if name == 'with_netmask':
            return self.get_with_netmask()
        if name == 'max_prefixlen':
            return self.get_max_prefixlen()
        if name == 'packed':
            return self.get_packed()
        if name == 'version':
            return self.get_version()
        if name == 'is_multicast':
            return self.get_is_multicast()
        if name == 'is_reserved':
            return self.get_is_reserved()
        if name == 'is_unspecified':
            return self.get_is_unspecified()
        if name == 'is_loopback':
            return self.get_is_loopback()
        if name == 'is_link_local':
            return self.get_is_link_local()
        if name == 'is_site_local':
            return self.get_is_site_local()
        if name == 'is_private':
            return self.get_is_private()
        if name == 'ipv4_mapped':
            return self.get_ipv4_mapped()
        if name == 'teredo':
            return self.get_teredo()
        if name == 'sixtofour':
            return self.get_sixtofour()
        if name == 'compressed':
            return self.get_compressed()
        if name == 'exploded':
            return self.get_exploded()
        if name == 'network':
            return self.get_network()
        if name == 'broadcast':
            return self.get_broadcast()
        if name == 'hostmask':
            return self.get_hostmask()

    def get_with_netmask(self):
        return self.with_prefixlen


def isValidIpAddress(ipAddr, filter_client_ip=None):
    """
    Checks whether the given IP address is valid. Supports both IPv4 and IPv6 types
    @param ipAddr: IP address to check
    @type ipAddr: string
    @return: true if the IP is valid, else false
    @rtype: Boolean
    """
    address = ipAddr
    if filter_client_ip:
        ipType = DomainScopeManager.getRangeTypeByIp(str(address))
        if ipType and ipType.equals(RangeType.CLIENT):
            return False

    if not isinstance(address, (IPv4Address, IPv6Address)):
        #in case of win old bug such address migh appear as valid interface ip
        #we want to ignore such ips while they are valid for the os
        if ipAddr and ipAddr.strip() == '255.255.255.255':
            return False
        try:
            address = IPAddress(address)
        except ValueError:
            return False
    return True

def isValidIpAddressNotZero(ipAddr, filter_client_ip=None):
    """
    Checks whether the given IP address is valid. Supports both IPv4 and IPv6 types
    @param ipAddr: IP address to check
    @type ipAddr: string
    @return: true if the IP is valid, else false
    @rtype: Boolean
    """
    address = ipAddr
    if filter_client_ip:
        ipType = DomainScopeManager.getRangeTypeByIp(str(address))
        if ipType and ipType.equals(RangeType.CLIENT):
            return False

    if not isinstance(address, (IPv4Address, IPv6Address)):
        #in case of win old bug such address migh appear as valid interface ip
        #we want to ignore such ips while they are valid for the os
        if ipAddr and ipAddr.strip() == '255.255.255.255':
            return False
        if ipAddr and ipAddr.strip() == '0.0.0.0':
            return False
        try:
            address = IPAddress(address)
        except ValueError:
            return False
    return True

def isIpAddressInRangeList(ipAddr, ipRangeList):
    """
    @param ipAddr: IP Address to check
    @param ipRangeList: A list contains either IPAddress object or IPNetwork object
    @return: true if the IP exists in the ip range list
    """
    flag = False
    if ipRangeList:
        for item in ipRangeList:
            if isinstance(item, _BaseIP):
                if ipAddr == item:
                    flag = True
            elif isinstance(item, _BaseNet):
                if ipAddr in item:
                    flag = True
            if flag:
                break
    return flag


def isValidNetmaskNotZero(netmask):
    """
    Check the given netmask is valid and not all-Zero
    @param netmask: netmask to check
    @return: Boolean
    """
    return IPv4Network("1.1.1.1")._is_valid_netmask(netmask) and netmask.strip()!='0.0.0.0'


