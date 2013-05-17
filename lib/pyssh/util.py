#!/usr/bin/env python
#-*- coding:utf-8 -*-

import logging

logger = logging.getLogger( "pyssh" )

def getIP(ifName):
	try:
		import socket
		import struct
		import fcntl
		s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0X8915, struct.pack('256s', ifName[:15]))[20:24])
	except:
		logger.exception('getIP exception')
		return None


