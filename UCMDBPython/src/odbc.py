# coding=utf-8
import entity
from itertools import imap
from pyargs_validator import not_none, validate

class DSNInfo(entity.Immutable):

    """
    Data object which reflect info about DSN
    """

    @validate(basestring, basestring, int, basestring, basestring)
    def __init__(self, name, address, port, database, driver):
        """
        :param name: name of the DSN
        :param address: host or ip of DSN
        :param port: port of DSN
        :param database: name of DSN

        :type name: str
        :type address: str
        :type port: str or int
        """
        self.name = name
        self.address = address
        self.port = port
        self.database = database
        self.driver = driver

    def __repr__(self):
        return 'odbc.DSNInfo(%s)' % (', '.join(imap(repr,
                                                         (self.name,
                                                          self.address,
                                                          self.port,
                                                          self.database,
                                                          self.driver)
                                                         )
                                                    )
                                              )

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        if isinstance(other, DSNInfo):
            return self.name == other.name and \
                   self.driver == other.driver and \
                   self.database == other.database and \
                   self.address == other.address and \
                   self.port == other.port
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result