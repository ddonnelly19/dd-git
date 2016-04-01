# coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''

import entity
from datetime import datetime
from itertools import imap
import db
from db2_pyarg_validator import validate, not_none, optional


class VersionInfo:
    @entity.immutable
    def __init__(self, release_number, service_level, build_level,
                 program_temp_fix, fixpack_number):
        self.release_number = release_number
        self.service_level = service_level
        self.build_level = build_level
        self.program_temp_fix = program_temp_fix
        self.fixpack_number = fixpack_number

    def __str__(self):
        return ('release_number="%s", '
                'service level="%s", '
                'build level="%s", '
                'program temporarty fix="%s", '
                'fixpack number="%s"') % (self.release_number,
                                          self.service_level, self.build_level,
                                          self.program_temp_fix,
                                          self.fixpack_number)

    def __repr__(self):
        return 'db2_model.VersionInfo(%s)' % (', '.join(imap(repr,
                                                             (self.release_number,
                                                              self.service_level,
                                                              self.build_level,
                                                              self.program_temp_fix,
                                                              self.fixpack_number)
                                                             )
                                                        )
                                              )


class Database(db.Database):

    @validate(basestring, optional)
    def __init__(self, name, aliases=None):
        db.Database.__init__(self, name)
        self.aliases = aliases and tuple(aliases) or ()

    @property
    def name(self):
        return self.getName()

    def __eq__(self, other):
        if isinstance(other, Database):
            return self.name == other.name
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db2_model.Database(%s)' % (', '.join(imap(repr, (self.name,
                                                       self.aliases))))


class TableType:
    A = 'A'  # Alias
    G = 'G'  # Global temporary table
    H = 'H'  # Hierarchy table
    L = 'L'  # Detached table
    N = 'N'  # Nickname
    S = 'S'  # Materialized query table
    T = 'T'  # Table (untyped)
    U = 'U'  # Typed table
    V = 'V'  # View (untyped)
    W = 'W'  # Typed view

    @staticmethod
    def values():
        return (TableType.A, TableType.G, TableType.H, TableType.L,
                TableType.N, TableType.S, TableType.T, TableType.U,
                TableType.V, TableType.W)


class Table(db.Table):

    def __init__(self, id_, name, type_, create_time=None):
        db.Table.__init__(self, id_, name, create_time)
        if not type_ in TableType.values():
            raise ValueError('Invalid type')
        self.type = type_

    def __keys(self):
        return (self.id, self.name, self.type, self.create_time)

    def __hash__(self):
        return hash(self.__keys())

    def __eq__(self, other):
        if isinstance(other, Table):
            return (self.id == other.id
                    and self.name == other.name
                    and self.type == other.type
                    and self.create_time == other.create_time)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db2_model.Table(%s)' % (', '.join(imap(repr, (self.id,
                                                       self.name,
                                                       self.type,
                                                       self.create_time))))


class BufferPool(entity.Immutable):

    @validate(int, unicode, int, int, int, int)
    def __init__(self, id_, name, default_page_number, page_size,
                 block_page_number, block_size):
        self.id = id_
        self.name = name
        self.default_page_number = default_page_number
        self.page_size = page_size
        self.block_page_number = block_page_number
        self.block_size = block_size

    def __eq__(self, other):
        if isinstance(other, BufferPool):
            return (self.id == other.id
                    and self.name == other.name
                    and self.default_page_number == other.default_page_number
                    and self.page_size == other.page_size
                    and self.block_page_number == other.block_page_number
                    and self.block_size == other.block_size)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        attrs = imap(repr, (self.id,
                            self.name,
                            self.default_page_number,
                            self.page_size,
                            self.block_page_number,
                            self.block_size))
        return 'db2_model.BufferPool(%s)' % (', '.join(attrs))


class Partition(entity.Immutable):

    @validate(int)
    def __init__(self, number):
        self.number = number

    def __eq__(self, other):
        if isinstance(other, Partition):
            return self.number == other.number
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db2_model.Partition(%s)' % (', '.join(imap(repr,
                                                           (self.number,))))


class PartitionGroup(entity.Immutable):
    @validate(not_none, datetime)
    def __init__(self, name, create_time):
        self.name = name
        self.create_time = create_time

    def __eq__(self, other):
        if isinstance(other, PartitionGroup):
            return (self.name == other.name
                    and self.create_time == other.create_time)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db2_model.PartitionGroup(%s)' % (', '.join(imap(repr,
                                                                (self.name,
                                                        self.create_time))))
