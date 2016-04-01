#coding=utf-8
import logger
import errorcodes
import errorobject

from java.sql import Types
from java.util import HashMap

class DiscoveryDbEntity:
	def __init__(self): pass
	def getEntityType(self): raise NotImplementedError,"getEntityType"
	def setValues(self, statement): raise NotImplementedError,"setValues"
	def getNewEntity(self, resultset): raise NotImplementedError,"getNewEntity"
	def getInsertSQL(self, resultset): raise NotImplementedError,"getInsertSQL"
	def setValue(self, st, index, value):
		if value == None:
			st.setNull(index, Types.VARCHAR)
		else:
			st.setString(index, value)

class DiscoveryDbUtils:
	def __init__(self, Framework, context = 'common'):
		self.Framework = Framework
		self.conn = self.Framework.getProbeDatabaseConnection(context)
		self.typeBulks = HashMap()

	def close(self):
		self.conn.close()
		
	def addToBulk(self, entity):
		entitiesbulk = self.typeBulks.get(entity.getEntityType())
		if entitiesbulk == None:
			entitiesbulk = []
			self.typeBulks.put(entity.getEntityType(), entitiesbulk)
		entitiesbulk.append(entity)

	def executeBulk(self, entityType):
		entitiesbulk = self.typeBulks.get(entityType)
		if (entitiesbulk != None) and (len(entitiesbulk) > 0):
			self.insertEntitiesProbeDb(entitiesbulk)
			del entitiesbulk[:]
				
	def insertEntitiesProbeDb(self, entitiesbulk):
		st = None
		try:
			try:
				sql = entitiesbulk[0].getInsertSQL()
				st = self.conn.prepareStatement(sql)
				for entity in entitiesbulk:
					entity.setValues(st)
					st.addBatch()
				st.executeBatch()
			except:
				error = 'Failed to add entities of type ' + str(entitiesbulk[0].getEntityType()) + ' to Probe database'
				logger.errorException(error)
				errobj = errorobject.createError(errorcodes.FAILED_ADDING_ENTITIES_TO_PROBE_DB, [str(entitiesbulk[0].getEntityType())], error)
				logger.reportErrorObject(errobj)
		finally:
			self.closeStatement(st)
				
	def executeUpdate(self, sql):
		st = None
		try:
			try:
				st = self.conn.createStatement()
				return st.executeUpdate(sql)
			except:
				error = 'Failed to execute sql ' + sql
				logger.errorException(error)
				errobj = errorobject.createError(errorcodes.FAILED_TO_EXECUTE_SQL, [sql], error)
				logger.reportErrorObject(errobj)
		finally:
			self.closeStatement(st)
		
	#each statement created by this tool should be closed by calling closeStatement method	
	def prepareStatement(self, sql):
		return self.conn.prepareStatement(sql)
		
	def createStatement(self):
		return self.conn.createStatement()
		
	def closeStatement(self, st):
		st.close()

