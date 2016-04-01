#coding=utf-8
'''
Created on Sep 1, 2011

@author: vvitvitskiy
'''
import entity
import aws


class Engine(entity.HasName):
    r'Database engine'
    def __init__(self, name, version, description=None):
        r'@types: str'
        entity.HasName.__init__(self)
        self.setName(name)
        self.__version = version
        self.__description = description

    def __repr__(self):
        return r'rds.Engine("%s", "%s", "%s")' % (
                        self.getName(), self.__version, self.__description)


class Instance(aws.HasId):
    def __init__(self, id_, type_, engineName, status, server,
                 masterUsername=None):
        r'@types: str, str, str, str, db.DatabaseServer, str'
        aws.HasId.__init__(self, id_)
        self.__type = type_
        self.__status = status

        self.engineName = engineName
        self.masterUsername = masterUsername

        self.server = server
