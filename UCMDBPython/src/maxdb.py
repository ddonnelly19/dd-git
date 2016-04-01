#coding=utf-8
'''
Created on Jan 31, 2012

@author: ekondrashev
'''
import db
import db_builder
import db_platform
import modeling
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder


class MaxDbUser(db.User):
    def __init__(self, name, creationDate=None, createdBy=None):
        db.User.__init__(self, name, creationDate)
        self.createdBy = createdBy

class MaxDbSchema(db.Schema):
    def __init__(self, name, creationDate=None, createdBy=None):
        db.Schema.__init__(self, name, creationDate)
        self.createdBy = createdBy

class BackupFile:
    def __init__(self, name, startDate=None, endDate=None):
        self.name = name
        self.startDate = startDate
        self.endDate = endDate


class MaxDatabase(db.DatabaseServer):
    def __init__(self, address=None, port=None, instance=None, databases=None,
                 vendor=None,
                 versionDescription=None,
                 platform=None,
                 version=None,
                 description=None,
                 state=None,
                 autosave=None,
                 scheduler=None,
                 autoextend=None):
        db.DatabaseServer.__init__(self, address, port, instance, databases,
                                   vendor, versionDescription, platform,
                                   version, description)
        self.state = state
        self.autosave = autosave
        self.scheduler = scheduler
        self.autoextend = autoextend


class MaxDb(db_builder.TopologyBuilder):

    CIT = 'maxdb'

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        osh = self._buildDatabaseServerOsh(db_platform.MaxDb(), server,
                                           self.CIT)
        server.state and  osh.setStringAttribute('db_state', server.state)
        if server.autosave and server.autosave == 'ON':
            osh.setBoolAttribute('autosave', 1)
        if server.autoextend:
            osh.setStringAttribute('autoextend', server.autoextend)
        if server.scheduler and server.scheduler == 'ON':
            osh.setBoolAttribute('scheduler_state', 1)
        hostOsh = modeling.createHostOSH(server.address, 'node')
        osh.setContainer(hostOsh)
        return osh

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.MaxDb)

    def buildConfigFile(self, configFileContent, databaseOsh):
        return modeling.createConfigurationDocumentOSH('MaxDB Config',
                                'MaxDB Config', configFileContent, databaseOsh)

    def buildUsersOsh(self, dbUsers, databaseOsh):
        '@types: list[MaxDbUser], osh -> oshv'
        oshv = ObjectStateHolderVector()
        for user in dbUsers:
            osh = self.buildUserOsh(user)
            osh.setContainer(databaseOsh)
            if user.createdBy:
                label = user.createdBy + ":" + user.name
                osh.setStringAttribute('user_label', label)
                ownerOsh = self.buildUserOsh(db.User(user.createdBy))
                ownerOsh.setContainer(databaseOsh)
                oshv.add(modeling.createLinkOSH('ownership', ownerOsh, osh))
                oshv.add(ownerOsh)
            oshv.add(osh)
        return oshv

    def buildSchemaTopology(self, schema, serverOsh):
        oshv = ObjectStateHolderVector()
        osh = self._buildDbSchemaOsh('database_instance', schema.name, schema.create_time)
        osh.setContainer(serverOsh)
        oshv.add(osh)
        if schema.createdBy:
            ownerOsh = self.buildUserOsh(db.User(schema.createdBy))
            ownerOsh.setContainer(serverOsh)
            oshv.add(modeling.createLinkOSH('ownership', ownerOsh, osh))
            oshv.add(ownerOsh)
        return oshv

    def buildDatafiles(self, dataFiles, databaseOsh):
        oshv = ObjectStateHolderVector()
        for dataFile in dataFiles:
            osh = self.buildDataFileOsh(dataFile)
            osh.setContainer(databaseOsh)
            oshv.add(osh)
        return oshv

    def _buildBackupFileOsh(self, backupFile):
        osh = ObjectStateHolder('sqlbackup')
        osh.setStringAttribute('name', backupFile.name)
        osh.setStringAttribute('sqlbackup_startdate', backupFile.startDate)
        osh.setStringAttribute('sqlbackup_finishdate', backupFile.endDate)
        return osh

    def buildBackupFiles(self, backupFiles, databaseOsh):
        oshv = ObjectStateHolderVector()
        for backupFile in backupFiles:
            osh = self._buildBackupFileOsh(backupFile)
            osh.setContainer(databaseOsh)
            oshv.add(osh)
        return oshv
