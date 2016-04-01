#coding=utf-8
"""
Simple converters that can be used during importing
"""
from java.lang import Boolean
from java.lang import Double
from java.lang import String
from java.text import SimpleDateFormat

from appilog.common.utils.zip import ChecksumZipper

def toString(value):
	if value is not None:
		return str(value)
	else:
		return ''

def stringToInt(value):
	if value is not None:
		return int(value.strip())
	else:
		return 0

def stringToLong(value):	
	if value is not None:
		return long(value.strip())
	else:
		return long(0)
	
def stringToFloat(value):
	if value is not None:
		return float(value.strip())
	else:
		return float(0)

def stringToBoolean(value):
	value = value.strip()
	if value.lower() == 'yes' or value.lower() == 'true' or value.lower() == '1':
		return Boolean('true')
	else:
		return Boolean('false')
	
def stringToDate(value):
	"""
	Information about how to build your own date pattern is here:
	http://java.sun.com/j2se/1.5.0/docs/api/java/text/SimpleDateFormat.html
	"""
	dateFormat = SimpleDateFormat("dd MMM yyyy HH:mm")
	return dateFormat.parse(value)

def stringToDouble(value):
	return Double.parseDouble(value.strip())

def skipSpaces(value):
	return value.strip()

def binaryIntToBoolean(value):
	if value == 0:
		return Boolean('false')
	else:
		return Boolean('true')

def stringToBytesArray(value):
	if value is not None:
		return String(value).getBytes()
	else:
		return String().getBytes()

def stringToZippedBytesArray(value):
	zipper = ChecksumZipper()
	return zipper.zip(stringToBytesArray(value))