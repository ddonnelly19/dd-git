#coding=utf-8
from java.lang import Class
import logger


class SqlServerConnection:
    def __init__(self): pass

    def open(self): raise NotImplementedError, "open"

    def close(self): raise NotImplementedError, "close"

    def getTable(self, select): raise NotImplementedError, "getTable"

    def doCall(self, select): raise NotImplementedError, "doCall"

    def setWorkingDatabase(self, dbName): raise NotImplementedError, "doCall"

    def getWorkingDatabase(self, dbName): raise NotImplementedError, "doCall"


class DriverSqlServerConnection(SqlServerConnection):
    def __init__(self, url, driver, props):
        self.url = url
        self.props = props
        driverClass = Class.forName(driver)
        self.driver = driverClass.newInstance()

    def open(self):
        self.connection = self.driver.connect(self.url, self.props)

    def close(self):
        self.connection.close()

    def getTable(self, select):
        stmt = self.connection.createStatement()
        rs = stmt.executeQuery(select)#@@CMD_PERMISION sql protocol execution
        return MyResultSet(stmt, rs)

    def doCall(self, select):
        stmt = self.connection.prepareCall(select)
        stmt.execute()
        rs = stmt.getResultSet()
        return MyResultSet(stmt, rs)

    def setWorkingDatabase(self, dbName):
        self.connection.setCatalog(dbName)

    def getWorkingDatabase(self):
        return self.connection.getCatalog()


class ClientSqlServerConnection(SqlServerConnection):
    def __init__(self, connection):
        self.connection = connection

    def open(self):
        logger.debug('open connection')

    def close(self):
        self.connection.close()

    def getTable(self, select, timeout=-1):
        logger.debug('going to run query:', select)
        return self.connection.getTable(select, timeout)

    def doCall(self, select, timeout=-1):
        logger.debug("going to run call:" + select)
        return self.connection.doCall(select, timeout)

    def setWorkingDatabase(self, dbName):
        self.connection.setWorkingDatabase(dbName)

    def getWorkingDatabase(self):
        return self.connection.getWorkingDatabase()


class MyResultSet:
    def __init__(self, stmt, resultSet):
        self.stmt = stmt
        self.rs = resultSet

    def next(self):
        if self.rs is not None:
            return self.rs.next()
        return 0

    def close(self):
        self.stmt.close()

    def getTimestamp(self, name):
        return self.rs.getTimestamp(name)

    def getString(self, name):
        return self.rs.getString(name)

    def getInt(self, name):
        return self.rs.getInt(name)


