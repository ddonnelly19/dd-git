'''
Created on Feb 6, 2013

@author: vkravets
'''
# could be potentially replaced with
# https://github.com/antong/ldaptor/blob/master/ldaptor/protocols/ldap/distinguishedname.py
from javax.naming.ldap import LdapName


class DnParser(object):
    '''
        DistinguishedName parser
    '''

    def parse(self, raw):
        '''
        Parse DistinguishedName from string representation
        @types: str -> DistinguishedName
        '''
        ldapName = LdapName(raw)
        head = None
        for item in ldapName.getRdns():
            name = item.getType()
            value = str(item.getValue())
            head = DistinguishedName(name.strip(), value.strip(), head)
        return head


class DistinguishedName(object):

    def __init__(self, name, value, next=None):
        self.name = name
        self.value = value
        self.next = next

    def __eq__(self, other):
        if not isinstance(other, DistinguishedName):
            return NotImplemented
        return (other and
                self.name == other.name and
                self.value == other.value)

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq == NotImplemented:
            return eq
        return not eq

    def find_first(self, name):
        if self.name == name:
            return self
        return self.next and self.next.find_first(name)

    def lookup(self, name):
        res = []
        first = self.find_first(name)
        while first is not None:
            res.append(first)
            first = first.next.find_first(name)
        return res
