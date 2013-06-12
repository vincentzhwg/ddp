#!/usr/bin/env python
#-*- coding:utf-8 -*-

import os
import logging, logging.config
import random
import ConfigParser
import time
import pexpect
import re

logger = logging.getLogger( "pyssh" )

SLEEP_TIME_AFTER_SENDLINE = 0.05
SCP_TEST_TIMEOUT = 30
SCP_WAIT_TIMEOUT = 1200
LOGIN_WAIT_TIMEOUT = 20
PYSSH_DEFAULT_TIMEOUT = 30
CONF_PATH = ""
LOCAL_INTERFACE = 'eth0'

## load config from config file ##
try:
	pysshConfigFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conf/pyssh.conf')
	RCP = ConfigParser.RawConfigParser()
	RCP.read( pysshConfigFile )
	if RCP.has_section('pyssh'):
		if RCP.has_option('pyssh', 'sleep_time_after_sendline_sec'):
			SLEEP_TIME_AFTER_SENDLINE = RCP.getfloat('pyssh', 'sleep_time_after_sendline_sec')
		else:
			SLEEP_TIME_AFTER_SENDLINE = 0.05
		if RCP.has_option('pyssh', 'scp_wait_timeout_sec'):
			SCP_WAIT_TIMEOUT = RCP.getint('pyssh', 'scp_wait_timeout_sec') 
		else:
			SCP_TEST_TIMEOUT = 30
		if RCP.has_option('pyssh', 'scp_test_timeout_sec'):
			SCP_TEST_TIMEOUT = RCP.getint('pyssh', 'scp_test_timeout_sec')
		else:
			SCP_WAIT_TIMEOUT = 1200
		if RCP.has_option('pyssh', 'login_wait_timeout_sec'):
			LOGIN_WAIT_TIMEOUT = RCP.getint('pyssh', 'login_wait_timeout_sec')
		else:
			LOGIN_WAIT_TIMEOUT = 20
		if RCP.has_option('pyssh', 'pyssh_default_timeout'):
			PYSSH_DEFAULT_TIMEOUT = RCP.getint('pyssh', 'pyssh_default_timeout')
		else:
			PYSSH_DEFAULT_TIMEOUT = 30
		if RCP.has_option('pyssh', 'conf_path'):	
			CONF_PATH = RCP.get('pyssh', 'conf_path')
		else:
			CONF_PATH = ""
		if RCP.has_option('pyssh', 'local_interface'):
			LOCAL_INTERFACE = RCP.get('pyssh', 'local_interface')
		else:
			LOCAL_INTERFACE = 'eth0'
except:
	logger.exception('load config from file exception')


def loadConfigParam(confFilePath):
	global SLEEP_TIME_AFTER_SENDLINE
	global SCP_WAIT_TIMEOUT
	global SCP_TEST_TIMEOUT
	global LOGIN_WAIT_TIMEOUT
	global PYSSH_DEFAULT_TIMEOUT
	global LOCAL_INTERFACE
	# whether absolute path
	if not os.path.isabs(confFilePath):
		curDirPath = os.path.dirname( os.path.realpath(__file__) )
		confFilePath = os.path.join( curDirPath, confFilePath )
	if not os.path.exists( confFilePath ):
		logger.error('config file path is not exists:%s', confFilePath)
		return 
	logger.info('load config parameters from file:%s', confFilePath)
	RCP = ConfigParser.RawConfigParser()
	RCP.read( confFilePath )
	if RCP.has_section('pyssh'):
		if RCP.has_option('pyssh', 'sleep_time_after_sendline_sec'):
			SLEEP_TIME_AFTER_SENDLINE = RCP.getfloat('pyssh', 'sleep_time_after_sendline_sec')
			logger.info('SLEEP_TIME_AFTER_SENDLINE:%r', SLEEP_TIME_AFTER_SENDLINE)
		if RCP.has_option('pyssh', 'scp_wait_timeout_sec'):
			SCP_WAIT_TIMEOUT = RCP.getint('pyssh', 'scp_wait_timeout_sec') 
			logger.info('SCP_WAIT_TIMEOUT:%r', SCP_WAIT_TIMEOUT)
		if RCP.has_option('pyssh', 'scp_test_timeout_sec'):
			SCP_TEST_TIMEOUT = RCP.getint('pyssh', 'scp_test_timeout_sec')
			logger.info('SCP_TEST_TIMEOUT:%r', SCP_TEST_TIMEOUT)
		if RCP.has_option('pyssh', 'login_wait_timeout_sec'):
			LOGIN_WAIT_TIMEOUT = RCP.getint('pyssh', 'login_wait_timeout_sec')
			logger.info('LOGIN_WAIT_TIMEOUT:%r', LOGIN_WAIT_TIMEOUT)
		if RCP.has_option('pyssh', 'pyssh_default_timeout'):
			PYSSH_DEFAULT_TIMEOUT = RCP.getint('pyssh', 'pyssh_default_timeout')
			logger.info('PYSSH_DEFAULT_TIMEOUT:%r', PYSSH_DEFAULT_TIMEOUT)
		if RCP.has_option('pyssh', 'local_interface'):
			LOCAL_INTERFACE = RCP.get('pyssh', 'local_interface')
			logger.info('LOCAL_INTERFACE:%r', LOCAL_INTERFACE)

#### load config from conf path
tList = re.split(r';', CONF_PATH)
tList = [item.strip() for item in tList if item.strip()] 
for item in tList[::-1]:
	loadConfigParam(item)

logger.info("conf parameter final values:")
logger.info('CONF_PATH:%r', CONF_PATH)
logger.info('SLEEP_TIME_AFTER_SENDLINE:%r', SLEEP_TIME_AFTER_SENDLINE)
logger.info('SCP_WAIT_TIMEOUT:%r', SCP_WAIT_TIMEOUT)
logger.info('SCP_TEST_TIMEOUT:%r', SCP_TEST_TIMEOUT)
logger.info('LOGIN_WAIT_TIMEOUT:%r', LOGIN_WAIT_TIMEOUT)
logger.info('PYSSH_DEFAULT_TIMEOUT:%r', PYSSH_DEFAULT_TIMEOUT)
logger.info('LOCAL_INTERFACE:%r', LOCAL_INTERFACE)


######################################################################################################################
def pexpectClearOutputBuffer(child):
	time.sleep(0.05)
	try:
		#child.read_nonblocking(size=10000, timeout=1) # GAS: Clear out the cache
		child.before = ""
		child.after = ""
		child.buffer = ""
	except pexpect.TIMEOUT:
		logger.error("pexpectClearOutputBuffer read_nonblocking timeout, go on doing following stepts")
		child.before = ""
		child.after = ""
		child.buffer = ""



def dealScpOutput(scpOutput):
	return re.sub(r'\r.*\r(?!\n)', '', scpOutput)






def scpPush(pyssh, scpPushCommand, scpPushValidation=None, scpPushValidationCommand=''):
	logger.info('host:%s, scpPush starts, scpPushCommand:%s, scpPushValidation:%r' % (pyssh.host, scpPushCommand, scpPushValidation))

	child = pexpect.spawn( scpPushCommand )

	time.sleep(SLEEP_TIME_AFTER_SENDLINE)
	i = child.expect(['yes/no', '[Pp]assword', '[Ii]nterrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=SCP_WAIT_TIMEOUT)
	logger.info("host:%s, scp push command:%s, expect ['yes/no', '[Pp]assword', '[Ii]nterrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%d, index=%d, before:%r, after:%r, buffer:%r" % (pyssh.host, scpPushCommand, SCP_WAIT_TIMEOUT, i, child.before, child.after, child.buffer))
	if i == 0:
		logger.info("host:%s, scp push, send yes", pyssh.host)
		child.sendline('yes')
		time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		i = child.expect(['yes/no', '[Pp]assword', '[Ii]nterrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=SCP_WAIT_TIMEOUT)
		logger.info("host:%s, command:%s, expect ['yes/no', '[Pp]assword', '[Ii]nterrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%d, index=%d, before:%r, after:%r, buffer:%r" % (pyssh.host, 'yes', SCP_WAIT_TIMEOUT, i, child.before, child.after, child.buffer))
	if i == 1:
		logger.info("host:%s, scp push, send password:%s", pyssh.host, pyssh.password)
		child.sendline( pyssh.password )
		time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		q = child.expect(['[Pp]assword', 'denied', pexpect.EOF, pexpect.TIMEOUT], timeout=SCP_WAIT_TIMEOUT)
		logger.info("host:%s, password:%s, expect ['[Pp]assword', 'denied', pexpect.EOF, pexpect.TIMEOUT], timeout=%d, index=%d, before:%r, after:%r, buffer:%r" % (pyssh.host, pyssh.password, SCP_WAIT_TIMEOUT, q, child.before, child.after, child.buffer))
		if q == 0 or q == 1:
			logger.warn("host:%s, scp push failed, password not correct or permission denied, then send control signal C" % pyssh.host)
			child.sendcontrol('c')
			pexpectClearOutputBuffer(child)
			return {'code':-3, 'output':'scp push faild, because password is not correct or permission denied\r\n'}
		elif q == 2:
			if scpPushValidation is None or scpPushValidation is False:
				return {'code':0, 'output':'scp push success, but no validation'}
			else:
				logger.info("host:%s, scp push pass first step, wait to validation" % pyssh.host)
				tRet = pyssh.execCommand(scpPushValidationCommand)
				logger.info("host:%s, scp push validation ret:%r", pyssh.host, tRet)
				if 0 == tRet['code']:
					return {'code':0, 'output':'scp push success and pass validation'}
				else:
					return {'code':-9, 'output':'scp push failed, can not pass validation, reason:%s' % tRet['output']}
		else:
			logger.warn("host:%s, scp push failed, timeout occurs, then send control signal C" % pyssh.host)
			child.sendcontrol('c')
			pexpectClearOutputBuffer(child)
			return {'code':-8, 'output':'scp push failed, timeout occurs\r\n'}
	elif i == 2:
		logger.warn("host:%s, scp push failed, send control signal C, then recall scpPush" % pyssh.host)
		child.sendcontrol('c')
		pexpectClearOutputBuffer(child)
		return scpPush(pyssh, scpPushCommand, scpPushValidation, scpPushValidationCommand)
	elif i == 3:
		if scpPushValidation is None or scpPushValidation is False:
			return {'code':0, 'output':'scp push success, but no validation'}
		else:
			logger.info("host:%s, scp push pass first step, wait to validation" % pyssh.host)
			tRet = pyssh.execCommand(scpPushValidationCommand)
			logger.info("host:%s, scp push validation ret:%r", pyssh.host, tRet)
			if 0 == tRet['code']:
				return {'code':0, 'output':'scp push success and pass validation'}
			else:
				return {'code':-9, 'output':'scp push failed, can not pass validation, reason:%s' % tRet['output']}
	elif i == 4:
		logger.warn("host:%s, scp push failed, timeout occurs, then send control signal C" % pyssh.host)
		child.sendcontrol('c')
		pexpectClearOutputBuffer(child)
		return {'code':-8, 'output':'scp push failed, timeout occurs\r\n'}

