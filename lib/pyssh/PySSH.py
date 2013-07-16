#!/usr/bin/env python
#-*- coding:utf-8 -*-

# date:2013-01-10
# author: vinczhang

import sys, os
import getpass
import logging, logging.config
import re
import time
import random
import ConfigParser


libPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
sys.path.append( libPath )

import pexpect
import PySSHUtil
import util

#### PYSSH_ROOT_DIR is used in loggin.conf for relative log file path
PYSSH_ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
os.environ['PYSSH_ROOT_DIR'] = PYSSH_ROOT_DIR

#loggingConfigFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conf/logging.conf')
#logging.config.fileConfig( loggingConfigFile, disable_existing_loggers = False )
#logging.config.fileConfig( loggingConfigFile )
logger = logging.getLogger( "pyssh" )




SLEEP_TIME_AFTER_SENDLINE = 0.05
SCP_TEST_TIMEOUT = 20
SCP_WAIT_TIMEOUT = 1200
LOGIN_WAIT_TIMEOUT = 20
PYSSH_DEFAULT_TIMEOUT = 20
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




#############################################################################################################################################
class PySSH:
	def __init__(self, hostName, user, password=None, port=None, timeout=PYSSH_DEFAULT_TIMEOUT):
		self.hostName = hostName
		self.user = user
		if None is password or not password.strip():
			self.password = None
		else:
			self.password = password
		self.port = port
		self.timeout = timeout
		self.needPassword = None

		#标识scp操作方向的标志，None表示未知，需要探测；True表示方向可通；False表示方向不可通
		self.scpPullFromLocalFlag = None	#ssh机器从操作机拉取的方向
		self.scpPushFromLocalFlag = None	#从操作机向ssh机器进行推送的方向

	def close(self):
		try:
			self.sshClient.sendline("exit")
			index = self.sshClient.expect([pexpect.EOF, "(?i)there are stopped jobs"])
			if index==1:
			    self.sshClient.sendline("exit")
			    #self.expect(EOF)
			self.sshClient.close(force=True)
		except:
			logger.exception("hostName:%s, occurs exception when closing", self.hostName)

	def getCommandOutput(self, originOutput):
		# originOutput often is self.sshClient.before

		# filter scp timeout output after sigint signal
		tStr = re.sub(r'warning:.*Connection Timed Out\r\r\n', '', originOutput)

		commandOutput = self.exceptFirstLine( tStr )
		return commandOutput


	def execLocalCommand(self, command, commandExt=None, timeout=-1):
		logger.info("hostName:%s, exec local command, parameter:command:%s, timeout:%r", self.hostName, command, timeout)
		#deal parameter
		if None is commandExt: commandExt = dict()
		
		tEvents = dict()
		if 'SCP_PWD' in commandExt:
			tEvents[ '(?i)password' ] = "%s" % commandExt['SCP_PWD']

		# add \n to every item in events
		for (k, v) in tEvents.items():
			tEvents[ k ] = "%s\n" % v

		try:
			logger.debug('events:%r', tEvents)
			tCommand = '/bin/sh -c "%s"' % command
			(commandOutput, exitCode) = pexpect.run(command=tCommand, events=tEvents, timeout=timeout, withexitstatus=True)
			logger.debug('hostName:%s, local command:%s, output:%r, exit:%d', self.hostName, command, commandOutput, exitCode)
			if 0 != exitCode:
				return {'code':-8001, 'output':commandOutput}
			else:
				return {'code':exitCode, 'output':commandOutput}
		except:
			logger.exception("hostName:%s, exec local command exception", self.hostName)
			return {'code': -8002, 'output':'exception occurs'}




	def execCommand(self, command, commandExt = None, timeout = -1):
		"""
		if the value of timeout is -1, then expect will use self.timeout
		code:
		0 : success
		"""
		logger.info("hostName:%s, parameter:command:%s, timeout:%r", self.hostName, command, timeout)

		# deal parameters
		if None is commandExt: commandExt = dict()
			
		if 0 == cmp('pyssh_scp_local_pull_push', command) or 0 == cmp('pyssh_scp_local_push_pull', command):
			tLocalIntf = LOCAL_INTERFACE
			if 'LOCAL_INTF' in commandExt:
				tLocalIntf = commandExt['LOCAL_INTF']
			tLocalPwd = None
			if 'LOCAL_PWD' in commandExt:
				tLocalPwd = commandExt['LOCAL_PWD']
			tLocalPort = None
			if 'LOCAL_PORT' in commandExt:
				tLocalPort = commandExt['LOCAL_PORT']
			tLocalIsDir = False
			if 'LOCAL_ISDIR' in commandExt:
				tLocalIsDir = commandExt['LOCAL_ISDIR']
			if 0 == cmp('pyssh_scp_local_pull_push', command):
				return self.scpFromLocalPullPush(localPassword=tLocalPwd, localPath=commandExt['LOCAL_PATH'], sshHostPath=commandExt['SSH_HOST_PATH'], localIsdir=tLocalIsDir, localIntf=tLocalIntf, localPort=tLocalPort, timeout=timeout)
			elif 0 == cmp('pyssh_scp_local_push_pull', command):
				return self.scpFromLocalPushPull(localPassword=tLocalPwd, localPath=commandExt['LOCAL_PATH'], sshHostPath=commandExt['SSH_HOST_PATH'], localIsdir=tLocalIsDir, localIntf=tLocalIntf, localPort=tLocalPort, timeout=timeout)
		elif 0 == cmp('pyssh_add_user', command):
			tUserPassword = None
			if 'USER_PWD' in commandExt:
				tUserPassword = commandExt['USER_PWD']
			tUserHomePath = None
			if 'USER_HOME' in commandExt:
				tUserHomePath = commandExt['USER_HOME']
			tGroupName = None
			if 'GROUP_NAME' in commandExt:
				tGroupName = commandExt['GROUP_NAME']
			return self.addUser(userName=commandExt['USER_NAME'], userPassword=tUserPassword, userHomePath=tUserHomePath, groupName=tGroupName)
		elif command.startswith('scp'):
			scpCommand = command
			if 'SCP_PWD' in commandExt:
				scpPassword = commandExt['SCP_PWD']
			else:
				scpPassword = None
			return self.execScpCommand(scpCommand, scpPassword, timeout=timeout)
		else:
			self.sshClient.sendline(command)
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			i = self.sshClient.expect([self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout)
			logger.info("hostName:%(hostName)s, command:%(command)s, commandExt:%(commandExt)r, expect['%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)r, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':command, 'commandExt':commandExt, 'prompt':self.prompt, 'timeout':timeout, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
			if i == 0:
				commandOutput = self.getCommandOutput( self.sshClient.before )

				if command.startswith('nohup') and self.sshClient.buffer:
					logger.info('hostName:%s, command starts with nohup, buffer:%r', self.hostName, self.sshClient.buffer)
					commandOutput = "%s%s" % (commandOutput, self.sshClient.buffer)
					#self.sshClient.buffer = ''
					self.clearOutputBuffer()

				exitRet = self.getPreCommandExitValue()
				if 0 != exitRet['code']:
					logger.error('hostName:%s, get command exec result failed, command:%s, get exit value result:%r', self.hostName, command, exitRet)
					return {'code':exitRet['code'], 'output':'error occurs when getting exit value for command:%s, reason:%r' % (command, exitRet['output'])}
				else:
					if 0 == exitRet['output']:
						logger.info('hostName:%s, exec command success, command:%s, output:%r', self.hostName, command, commandOutput)
						return {'code':0, 'output':commandOutput}
					else:
						logger.error('hostName:%s, exec command finished, but exit value is not 0, command:%s, output:%r', self.hostName, command, commandOutput)
						return {'code':-6009, 'output':commandOutput}
			elif i == 1:
				logger.error("hostName:%s, execute command, EOF occur, then send control signal C", self.hostName)
				#self.sshClient.sendcontrol('c')
				#self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code':-6007, 'output':'EOF occurs when executing command:%s' % command}
			else:
				logger.error("hostName:%s, execute command, timeout occur, then send control signal C", self.hostName)
				#self.sshClient.sendcontrol('c')
				self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code':-6008, 'output':'timeout occurs when executing command:%s' % command}


	def login(self):
		"""
		Return : int
		0: login success, and get the correct prompt which is stored in the attribute of prompt
		-4001: password is not correct
		-4002: ssh connection success, but can not get the prompt
		-4003: EOF
		-4004: timeout
		"""

		sshLoginCommand = ""
		if self.port:
			sshLoginCommand = 'ssh -l %s -p %d %s' % (self.user, self.port, self.hostName)
		else:
			sshLoginCommand = 'ssh -l %s %s' % (self.user, self.hostName)
		logger.info("hostName:%s, begin ssh login, ssh login command:%s", self.hostName, sshLoginCommand)

		self.sshClient = pexpect.spawn(sshLoginCommand, timeout = self.timeout, maxread=81920)
		#self.sshClient.logfile = open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'logs/pexpect.log'), 'w')

		i = self.sshClient.expect(['(?i)yes/no', '(?i)password', '(?i)last login', '(?i)welcome', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=LOGIN_WAIT_TIMEOUT)
		logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)yes/no', '(?i)password', '(?i)last login', '(?i)welcome', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':sshLoginCommand, 'timeout':LOGIN_WAIT_TIMEOUT, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 0:
			logger.info('hostName:%s, ssh logining, send yes', self.hostName)
			self.sshClient.sendline('yes')
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			i = self.sshClient.expect(['(?i)yes/no', '(?i)password', '(?i)last login', '(?i)welcome', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=LOGIN_WAIT_TIMEOUT)
			logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)yes/no', '(?i)password', '(?i)last login', '(?i)welcome', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':sshLoginCommand, 'timeout':LOGIN_WAIT_TIMEOUT, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 1:
			logger.info('hostName:%s, ssh loging, send password', self.hostName)

			self.needPassword = True

			self.sshClient.sendline(self.password)
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			p = self.sshClient.expect(['(?i)password', '(?i)denied', '(?i)last login', '(?i)welcome', pexpect.EOF, pexpect.TIMEOUT], timeout=LOGIN_WAIT_TIMEOUT)
			logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)password', '(?i)denied', '(?i)last login', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':sshLoginCommand, 'timeout':LOGIN_WAIT_TIMEOUT, 'index':p, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
			if p == 0 or p == 1:
				logger.error("hostName:%s, ssh password wrong", self.hostName)
				return {'code':-4001, 'output':'password is not correct'}
			elif p == 2 or p == 3:
				logger.info("hostName:%s, ssh login success, begin get prompt", self.hostName)
				self.prompt = self.getPrompt()
				if self.prompt:
					logger.info("hostName:%s, get prompt success:%r" % (self.hostName, self.prompt))
					return {'code':0, 'output':'login success'}
				else:
					logger.error("hostName:%s, can not get prompt" % self.hostName)
					return {'code':-4002, 'output':'login success, but can not get the prompt'}
			elif p == 4:
				logger.error("hostName:%s, ssh login failed, EOF occurs", self.hostName)
				return {'code':-4003, 'output':'login EOF occurs'}
			else:
				logger.error("hostName:%s, ssh login failed, timeout occurs", self.hostName)
				return {'code':-4004, 'output':'login timeout occurs'}
		elif i == 2 or i == 3:
			logger.info("hostName:%s, ssh login success, and don't need password" % self.hostName)

			self.needPassword = False

			self.prompt = self.getPrompt()
			if self.prompt:
				logger.info("hostName:%s, get prompt success:%r" % (self.hostName, self.prompt))
				return {'code':0, 'output':'login success'}
			else:
				logger.error("hostName:%s, can not get prompt" % self.hostName)
				return {'code':-4002, 'output':'can not get the prompt'}
		elif i == 4:
			logger.warning("hostName:%s, interrupted system call occurs, recall login method", self.hostName)
			return self.login()
		elif i == 5:
			logger.error("hostName:%s, ssh login failed, EOF occurs", self.hostName)
			return {'code':-4003, 'output':'login EOF occurs'}
		else:
			logger.error("hostName:%s, ssh login failed, timeout occurs", self.hostName)
			return {'code':-4004, 'output':'login timeout occurs'}
					

	def testPathExists(self, path):
		logger.info("hostName:%s, test path exists start, path:%s", self.hostName, path)
		tRet = self.execCommand('ls -l --color=never %s' % path)
		if 0 != tRet['code']:
			logger.warning("hostName:%s, test path[%s] failed, reason:%r", self.hostName, path, tRet['output'])
			return False
		else:
			logger.info("hostName:%s, test path[%s] success, output:%r", self.hostName, path, tRet['output'])
			return True



	def scpPushFromLocal(self, scpCommand, validation=None, validationCommand='', timeout=-1):
		if -1 == timeout:
			timeout = SCP_WAIT_TIMEOUT

		logger.info('hostName:%s, scpPushFromLocal starts, scpCommand:%s, validation:%r, validationCommand:%s, timeout:%r' % (self.hostName, scpCommand, validation, validationCommand, timeout))
	
		child = pexpect.spawn( scpCommand )
	
		#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		i = child.expect(['(?i)yes/no', '(?i)password', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
		logger.info("hostName:%s, scp push from local command:%s, expect ['(?i)yes/no', '(?i)password', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%r, index=%d, before:%r, after:%r, buffer:%r" % (self.hostName, scpCommand, timeout, i, child.before, child.after, child.buffer))
		if i == 0:
			logger.info("hostName:%s, scp push from local, send yes", self.hostName)
			# clear output before send
			PySSHUtil.pexpectClearOutputBuffer(child)
			child.sendline('yes')
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			i = child.expect(['(?i)yes/no', '(?i)password', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
			logger.info("hostName:%s, command:%s, expect ['(?i)yes/no', '(?i)password', '(?i)interrupted system call', pexpect.EOF, pexpect.TIMEOUT], timeout=%r, index=%d, before:%r, after:%r, buffer:%r" % (self.hostName, 'yes', timeout, i, child.before, child.after, child.buffer))
		if i == 1:
			logger.info("hostName:%s, scp push from local, need password", self.hostName)
			if None is self.password:
				logger.error("hostName:%s, scp push from local, need password, but not offer", self.hostName)
				return {'code':-5011, 'output':'scp push from local need password, but not offer'}
			# clear output before send
			PySSHUtil.pexpectClearOutputBuffer(child)
			child.sendline( self.password )
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			q = child.expect(['(?i)password', '(?i)denied', pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
			logger.info("hostName:%s, expect ['(?i)password', '(?i)denied', pexpect.EOF, pexpect.TIMEOUT], timeout=%r, index=%d, before:%r, after:%r, buffer:%r" % (self.hostName, timeout, q, child.before, child.after, child.buffer))
			if q == 0 or q == 1:
				logger.warn("hostName:%s, scp push from local failed, password not correct or permission denied, then send control signal C" % self.hostName)
				child.sendcontrol('c')
				PySSHUtil.pexpectClearOutputBuffer(child)
				return {'code':-5012, 'output':'scp push from local faild, because password is not correct or permission denied'}
			elif q == 2:
				if validation is None or validation is False:
					return {'code':0, 'output':'scp push from local success, but no validation'}
				else:
					logger.info("hostName:%s, scp push from local pass first step, wait to validation" % self.hostName)
					tRet = self.execCommand(validationCommand)
					logger.info("hostName:%s, scp push from local validation ret:%r", self.hostName, tRet)
					if 0 == tRet['code']:
						return {'code':0, 'output':'scp push from local success and pass validation'}
					else:
						return {'code':-5013, 'output':'scp push from local failed, can not pass validation comman:%s, reason:%r' % (validationCommand, tRet['output'])}
			else:
				logger.warn("hostName:%s, scp push from local failed, timeout[%r] occurs, then send control signal C", self.hostName, timeout)
				child.sendcontrol('c')
				PySSHUtil.pexpectClearOutputBuffer(child)
				return {'code':-5014, 'output':'scp push from local failed, timeout occurs'}
		elif i == 2:
			logger.warn("hostName:%s, scp push from local failed, send control signal C, then recall scpPushFromLocal" % self.hostName)
			child.sendcontrol('c')
			PySSHUtil.pexpectClearOutputBuffer(child)
			return self.scpPushFromLocal(scpCommand=scpCommand, validation=validation, validationCommand=validationCommand, timeout=timeout)
		elif i == 3:
			childOutput = child.before
			child.close()	# close child, then can get exit code from child.exitstatus
			logger.info("hostName:%s, scp push from local executed completely, exit status:%d", self.hostName, child.exitstatus)
			childReturnCode = child.exitstatus
			if 0 == childReturnCode:
				if validation is None or validation is False:
					return {'code':0, 'output':'scp push from local success, but no validation'}
				else:
					logger.info("hostName:%s, scp push from local pass first step, wait to validation" % self.hostName)
					tRet = self.execCommand(validationCommand)
					logger.info("hostName:%s, scp push from local validation ret:%r", self.hostName, tRet)
					if 0 == tRet['code']:
						return {'code':0, 'output':'scp push from local success and pass validation'}
					else:
						return {'code':-5015, 'output':'scp push from local failed, can not pass validation, reason:%r' % tRet['output']}
			else:
				return {'code':-5022, 'output':'scp push from local failed, reason:%r' % childOutput}
		elif i == 4:
			logger.warn("hostName:%s, scp push from local failed, timeout[%r] occurs, then send control signal C", self.hostName, timeout)
			child.sendcontrol('c')
			PySSHUtil.pexpectClearOutputBuffer(child)
			return {'code':-5016, 'output':'scp push from local failed, timeout occurs'}


	def scpPushFromLocalTest(self, sourceTempDir='/tmp/', destTempDir='/tmp/'):
		logger.info('hostName:%s, scpPushFromLocalTest starts, sourceTempDir:%s, destTempDir:%s', self.hostName, sourceTempDir, destTempDir)
	
		### create source temp file in local host ###
		tryCounter = 0
		while True:
			if 10 < tryCounter:
				logger.error('hostName:%s, test failed, can not create source temp file in local host', self.hostName)
				# set flag
				self.scpPushFromLocalFlag = False	
				return False
			sourceTempFileName = ''.join( random.sample('abcdefghijklmnopqrstuvwxyz1234567890', 25) )
			sourceTempFilePath = os.path.join(sourceTempDir, sourceTempFileName)
			if os.path.exists( sourceTempFilePath ) or self.testPathExists( os.path.join(destTempDir, sourceTempFileName) ):
				tryCounter += 1
			else:
				break
		sourceTempFile = open(sourceTempFilePath, 'w')
		sourceTempFile.write('pyssh scp push from local test')
		sourceTempFile.flush()
		sourceTempFile.close()
		logger.info('hostName:%s, create temp file success:%s', self.hostName, sourceTempFilePath)
	
		if not self.port is None:
			remotePort = '-P %d' % self.port
		else:
			remotePort = ''
		
		scpPushFromLocalTestCommand = 'scp %(port)s %(source)s %(user)s@%(hostName)s:%(dest)s' % {'port':remotePort, 'source':sourceTempFilePath, 'user':self.user, 'hostName':self.hostName, 'dest':destTempDir}
		scpPushFromLocalTestValidationCommand = 'ls -l --color=never %s' % os.path.join(destTempDir, sourceTempFileName)

		scpRet = self.scpPushFromLocal(scpCommand=scpPushFromLocalTestCommand, validation=True, validationCommand=scpPushFromLocalTestValidationCommand)
		logger.info('hostName:%s, scp test ret:%r', self.hostName, scpRet)

		### delete temp file in local
		os.remove( sourceTempFilePath )

		if 0 != scpRet['code']:
			logger.error('hostName:%s, scp push from locat test failed, reason:%s', self.hostName, scpRet['output'])
			# set flag
			self.scpPushFromLocalFlag = False	
			return False
		else:
			logger.info("hostName:%s, scp push from local test success, then delete self temp file, return True", self.hostName)
			### delete self temp file
			deleteTempFileCommand = 'rm -f %s' % os.path.join(destTempDir, sourceTempFileName)
			deleteRet = self.execCommand(deleteTempFileCommand)
			logger.info("hostName:%s, deleteTempFileCommand result:%r", self.hostName, deleteRet)
			# set flag
			self.scpPushFromLocalFlag = True
			return True





	def scpPushToDestTest(self, destUser, destHostName, destPassword=None, destPort=None, destTempDir='/tmp/', sourceTempDir='/tmp/'):
		logger.info("hostName:%s, scpPushToDestTest starts, destUser:%s, destHostName:%s, destPort:%r, destTempDir:%s, sourceTempDir:%s", self.hostName, destUser, destHostName, destPort, destTempDir, sourceTempDir)
		### create source temp file in source temp dir ###
		tryCounter = 0
		while True:
			if 10 < tryCounter:
				logger.error('hostName:%s, test failed, can not create source temp file', self.hostName)
				return False
			sourceTempFileName = ''.join( random.sample('abcdefghijklmnopqrstuvwxyz1234567890', 25) )
			sourceTempFilePath = os.path.join(sourceTempDir, sourceTempFileName)
			if self.testPathExists( sourceTempFilePath ):
				tryCounter += 1
			else:
				break
		createTempFileCommand = "echo 'pyssh scp push to dest test' > %s" % sourceTempFilePath
		deleteTempFileCommand = "rm -f %s" % sourceTempFilePath
		createRet = self.execCommand(createTempFileCommand)
		if 0 != createRet['code']:
			logger.error('hostName:%s, failed, execute create temp command failed, command:%s, reason:%s' % (self.hostName, createTempFileCommand, createRet['output']))
			return False
		logger.info('hostName:%s, create temp file success:%s', self.hostName, sourceTempFilePath)
		### scp port ###
		if destPort is None:
			tdPort = ''
		else:
			tdPort = '-P %d' % destPort
		scpPushToDestTestCommand = 'scp %(port)s %(source)s %(user)s@%(hostName)s:%(dest)s' % {'port':tdPort, 'source':sourceTempFilePath, 'user':destUser, 'hostName':destHostName, 'dest':destTempDir}
		logger.info('hostName:%s, scp push to dest test, command:%s, start test', self.hostName, scpPushToDestTestCommand)
		scpRet = self.execScpCommand(scpPushToDestTestCommand, destPassword, timeout=SCP_TEST_TIMEOUT)
		### delete temp file ###
		delTempFileRet = self.execCommand(deleteTempFileCommand)
		logger.info("hostName:%s, after execute scp command, delete temp file, delete result:%r", self.hostName, delTempFileRet)
		if 0 != scpRet['code']:
			logger.error('hostName:%s, scp push to dest test, command execute failed, execute result:%r', self.hostName, scpRet)
			return False
		else:
			return True



	def scpPullFromLocalTest(self, sourceUser, sourcePassword=None, sourceIfName=None, sourcePort=None, sourceTempDir='/tmp', destTempDir='/tmp', validation=True):
		# deal parameters
		if None is sourceIfName: sourceIfName = LOCAL_INTERFACE

		logger.info("hostName:%s, scpPullFromLocalTest starts, sourceIfName:%s, sourceUser:%s, sourcePort:%r, sourceTempDir:%s, destTempDir:%s, validation:%r", self.hostName, sourceIfName, sourceUser, sourcePort, sourceTempDir, destTempDir, validation)
		### get local host IP
		sourceHostName = util.getIP( sourceIfName )
		if sourceHostName is None:
			logger.error('hostName:%s, failed, can not get local IP', self.hostName)
			return False
		logger.info('hostName:%s, scp pull from local test, local IP:%s', self.hostName, sourceHostName)
		### create source temp file in local host ###
		tryCounter = 0
		while True:
			if 10 < tryCounter:
				logger.error('hostName:%s, test failed, can not create source temp file in local host', self.hostName)
				return False
			sourceTempFileName = ''.join( random.sample('abcdefghijklmnopqrstuvwxyz1234567890', 25) )
			sourceTempFilePath = os.path.join(sourceTempDir, sourceTempFileName)
			if os.path.exists( sourceTempFilePath ):
				tryCounter += 1
			else:
				break
		sourceTempFile = open(sourceTempFilePath, 'w')
		sourceTempFile.write('pyssh scp pull local test')
		sourceTempFile.flush()
		sourceTempFile.close()
		logger.info('hostName:%s, create temp file success:%s', self.hostName, sourceTempFilePath)

		tResult = self.scpPullToSelfTest(sourceHostName=sourceHostName, sourceUser=sourceUser, sourcePassword=sourcePassword, sourceFile=sourceTempFilePath, sourcePort=sourcePort, destTempDir=destTempDir, validation=validation)
		
		### delete local temp file
		try:
			os.remove( sourceTempFilePath )
		except:
			pass

		# set flag
		if tResult:
			self.scpPullFromLocalFlag = True
		else:
			self.scpPullFromLocalFlag = False
		
		return tResult



	def scpPullToSelfTest(self, sourceHostName, sourceUser, sourceFile, sourcePassword=None, sourcePort=None, destTempDir='/tmp/', validation=True):
		logger.info("hostName:%s, scpPullToSelfTest starts, sourceUser:%s, sourcePort:%r, sourceFile:%s, destTempDir:%s, validation:%r", self.hostName, sourceUser, sourcePort, sourceFile, destTempDir, validation)
		### scp port ###
		if sourcePort is None:
			tdPort = ''
		else:
			tdPort = '-P %d' % sourcePort
		scpPullToSelfTestCommand = 'scp %(port)s %(user)s@%(hostName)s:%(source)s %(dest)s' % {'port':tdPort, 'source':sourceFile, 'user':sourceUser, 'hostName':sourceHostName, 'dest':destTempDir}
		logger.info('hostName:%s, scp pull to self test, command:%s, start test', self.hostName, scpPullToSelfTestCommand)
		scpRet = self.execScpCommand(scpPullToSelfTestCommand, sourcePassword, timeout=SCP_TEST_TIMEOUT)
		logger.info("hostName:%s, after execute scp command, delete temp file", self.hostName)
		if 0 != scpRet['code']:
			logger.error('hostName:%s, scp pull to self test, command execute failed, execute result:%r', self.hostName, scpRet)
			return False
		else:
			### whether validation
			if validation:
				validationCommand = 'ls -l --color=never %s' % os.path.join(destTempDir, os.path.basename(sourceFile))
				logger.info('hostName:%s, scp pull to self test, validationCommand:%s', self.hostName, validationCommand)
				validRet = self.execCommand(validationCommand)
				if 0 != validRet['code']:
					logger.error('hostName:%s, scp pull to self test, file transmission success, but can not pass validation, validation result:%r', self.hostName, validRet)
					return False
			### delete test temp file
			deleteTempFileCommand = 'rm -rf %s' % os.path.join(destTempDir, os.path.basename(sourceFile))
			logger.info('hostName:%s, scp pull to self test, deleteTempFileCommand:%s', self.hostName, deleteTempFileCommand)
			deleteRet = self.execCommand(deleteTempFileCommand)
			logger.info('hostName:%s, scp pull to self test, deleteTempFileCommand result:%r', self.hostName, deleteRet)

			return True

	
	def getPreCommandExitValue(self):
		logger.debug('hostName:%s, getPreCommandExitValue starts', self.hostName)
		# clear output before get
		#self.clearOutputBuffer()
		self.sshClient.sendline('echo $?')
		#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		qqT = self.sshClient.expect([self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout = 10)
		logger.debug("hostName:%(hostName)s, command:%(command)s, expect['%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)r, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':'echo $?', 'prompt':self.prompt, 'timeout':5, 'index':qqT, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if 0 == qqT:
			tBf = self.sshClient.before
			# filter scp timeout output after sigint signal
			tBf = re.sub(r'warning:.*Connection Timed Out\r\r\n', '', tBf)
			tOp = self.exceptFirstLine(tBf).strip()
			try:
				tOpInt = int(tOp)
				return {'code':0, 'output':tOpInt}
			except Exception, e:
				logger.exception("hostName:%s, transfer to int occursexception" % self.hostName)
				#self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code':-6006, 'output':'exception occurs when getting pre command exit value, reason:%r' % tOp}
		elif 1 == qqT:
			logger.error("hostName:%s, getPreCommandExitValue EOF occurs", self.hostName)
			#self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code':-6004, 'output':'EOF occurs when getting pre command exit value'}
		else:
			logger.error("hostName:%s, getPreCommandExitValue timeout occurs", self.hostName)
			self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code':-6005, 'output':'TIMEOUT occurs when getting pre command exit value'}


	def execScpCommand(self, scpCommand, scpPassword = None, timeout = -1):
		if -1 == timeout:
			timeout = SCP_WAIT_TIMEOUT

		logger.info("hostName:%s, exec scp command starts, parameter:scpCommand:%s, timeout:%r" % (self.hostName, scpCommand, timeout))

		# clear output before exec command
		#self.clearOutputBuffer()

		self.sshClient.sendline(scpCommand)
		#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		i = self.sshClient.expect(['(?i)yes/no', '(?i)password', '(?i)authentication failed', '(?i)interrupted system call', self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
		logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)yes/no', '(?i)password', '(?i)authentication failed', '(?i)interrupted system call', '%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)r, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':scpCommand, 'prompt':self.prompt, 'timeout':timeout, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 0:
			logger.info("hostName:%s, exec scp, send yes", self.hostName)
			# clear output before exec command
			self.clearOutputBuffer()
			self.sshClient.sendline('yes')
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			i = self.sshClient.expect(['(?i)yes/no', '(?i)password', '(?i)authentication failed', '(?i)interrupted system call',self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
			logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)yes/no', '(?i)password', '(?i)authentication failed', '(?i)interrupted system call', '%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)r, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':scpCommand, 'prompt':self.prompt, 'timeout':timeout, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 1:
			logger.info("hostName:%s, exec scp, need password", self.hostName)
			if None is scpPassword:
				logger.error("hostName:%s, need password, but does not offer password", self.hostName)
				return {'code':-5005, 'output':'scp command need password, but not offer'}
			# clear output before exec command
			self.clearOutputBuffer()
			self.sshClient.sendline(scpPassword)
			#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
			q = self.sshClient.expect(['(?i)password', '(?i)denied', self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
			logger.info("hostName:%(hostName)s, send password, expect['(?i)password', '(?i)denied', '%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)r, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'prompt':self.prompt, 'timeout':timeout, 'index':q, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
			if q == 0 or q == 1:
				logger.error("hostName:%s, scp command:%s, password not correct, then send control signal C", self.hostName, scpCommand)
				#self.sshClient.sendcontrol('c')
				self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code':-5006, 'output':'scp command faild, because password is not correct or permission denied'}
			elif q == 2:
				logger.info("hostName:%s, scp exec finished, then validation", self.hostName)
				strBefore = self.sshClient.before
				commandOutput = self.exceptFirstLine(strBefore)
				exitRet = self.getPreCommandExitValue()
				if 0 == exitRet['code'] and 0 == exitRet['output']: 
					return {'code':0, 'output':PySSHUtil.dealScpOutput(commandOutput)}
				else:
					logger.error("hostName:%s, scp exec finished, but can not pass validation", self.hostName)
					return {'code':-5007, 'output':commandOutput}
			elif q == 3:
				logger.error("hostName:%s, scp EOF occurs, then send control signal C" % (self.hostName, timeout))
				#self.sshClient.sendcontrol('c')
				#self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code': -5008, 'output':"scp command failed, EOF occurs"}
			else:
				logger.error("hostName:%s, scp timeout[%d] occurs, then send control signal C" % (self.hostName, timeout))
				#self.sshClient.sendcontrol('c')
				self.sshClient.sendintr()
				self.clearOutputBuffer()
				return {'code': -5009, 'output':"scp command failed, timeout[%d] occurs" % timeout}
		elif i == 2 or i == 3:
			logger.warning("hostName:%s, scp failed, send control signal C, then retry again" % self.hostName)
			#self.sshClient.sendcontrol('c')
			self.sshClient.sendintr()
			self.clearOutputBuffer()
			return self.execScpCommand(scpCommand, scpPassword, timeout)
		elif i == 4:
			logger.warning("hostName:%s, scp finished, password no need, then validation" % self.hostName)
			strBefore = self.sshClient.before
			commandOutput = self.exceptFirstLine(strBefore)
			exitRet = self.getPreCommandExitValue()
			if 0 == exitRet['code'] and 0 == exitRet['output']: 
				return {'code':0, 'output':PySSHUtil.dealScpOutput(commandOutput)}
			else:
				logger.error("hostName:%s, scp exec finished, but can not pass validation", self.hostName)
				return {'code':-5010, 'output':commandOutput}
		elif i == 5:
			logger.error("hostName:%s, scp EOF occurs, then send control signal C" % (self.hostName, timeout))
			#self.sshClient.sendcontrol('c')
			#self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code': -5008, 'output':"scp command failed, EOF occurs"}
		else:
			logger.error("hostName:%s, scp timeout[%d] occurs, then send control signal C" % (self.hostName, timeout))
			#self.sshClient.sendcontrol('c')
			self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code': -5009, 'output':"scp command failed, timeout[%d] occurs" % timeout}


	def exceptFirstLine(self, s):
		ret = ""
		if s:
			l = re.split(r'\r\n', s, 1)
			if len(l) == 1:
				ret = l[0]
			else:
				ret = l[1]
		else:
			ret = s
		logger.debug("hostName:%s, exceptFirstLine, origin:%r, result:%r", self.hostName, s, ret)
		return ret


	def execExactCommand(self, command):
		self.sshClient.sendline(command)
		#time.sleep(SLEEP_TIME_AFTER_SENDLINE)
		self.sshClient.expect_exact(command)
		logger.debug("hostName:%s, exec exact command:%s; before:%r; after:%r; buffer:%r", self.hostName, command, self.sshClient.before, self.sshClient.after, self.sshClient.buffer)
		return {'before' : self.sshClient.before, 'after': self.sshClient.after}
	
	
	def splitStringToGetLast(self, s):
		l = re.split(r'\r\n', s)
		if len(l) > 0:
			return l[-1]
		else:
			return None

	def dealRegxSpecialChar(self, s):
		specialChars = ['^', '$', '(', ')', '*', '+', '.', '?', '\\', '|', '[', ']', '>', '<', '~', '-', ':', '@']
		ret = ""
		for c in s:
			if c in specialChars:
				ret = "%s\\%s" % (ret, c)
			else:
				ret = "%s%s" % (ret, c)
		return ret
	
	def clearOutputBuffer(self):
		time.sleep(0.5)
		try:
			self.sshClient.read_nonblocking(size=10000, timeout=1) # GAS: Clear out the cache
			#self.sshClient.buffer = ""
			#self.sshClient.after = ""
			#self.sshClient.before = ""
		except pexpect.TIMEOUT:
			logger.debug("%s read_nonblocking timeout, go on doing following stepts" % self.hostName)
			#self.sshClient.buffer = ""
			#self.sshClient.after = ""
			#self.sshClient.before = ""


	def getPrompt(self):
		logger.info("hostName:%s, starting get prompt, trying by setting prompt first", self.hostName)
		t = self.getPromptBySetPS1()
		if t:
			logger.info("hostName:%s, get prompt by setting prompt success, prompt:%s", self.hostName, t)
			return t
		else:
			logger.error("hostName:%s, get prompt failed", self.hostName)
			return ""

			#logger.warning("hostName:%s, can not get prompt by setting prompt, then try to get prompt by comparing" % self.hostName)
			#s = self.getPromptByCompare()
			#if s:
			#	logger.info("hostName:%s, get prompt by comparing success, prompt:%s", self.hostName, s)
			#	return s
			#else:
			#	logger.error("hostName:%s, get prompt failed", self.hostName)
			#	return ""
				



	def getPromptByCompare(self):

		self.clearOutputBuffer()
		self.execExactCommand('pwd')
	
		cmds = ['cd /bin', 'cd ~', 'cd /', 'cd ~', 'cd /tmp', 'cd ~', 'cd /usr', 'cd ~']
	
		baList = list()
		for c in cmds:
			ba = self.execExactCommand(c)
			baList.append(ba)
	
		strList = list()
		for i in baList:
			strBefore = i['before']
			t = self.splitStringToGetLast(strBefore)
			if t:
				strList.append(t)
		logger.debug("hostName:%s get last:%r" % (self.hostName, strList))
	
		if len(strList) <= 1:
			logger.error("hostName:%s, last list can not get more than 1, last:%r" % (self.hostName, strList))
			return ""

		promptPre = ""
		strT = strList[0]
		
		flag = True
		for j in range(1, len(strList)):
			if 0 != cmp(strT, strList[j]):
				flag = False
				break
		if flag:
			logger.debug("hostName:%s, all last elements are same:%r" % (self.hostName, strT))
			prompt = self.dealRegxSpecialChar(strT)
			k = self.sshClient.expect([prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=8)
			logger.debug("hostName:%s, validating prompt, expect[%r, pexpect.EOF, pexpect.TIMEOUT], index=%d, before:%r, after:%r, buffer:%r" % (self.hostName, prompt, k, self.sshClient.before, self.sshClient.after, self.sshClient.buffer))
			if 0 == k:
				if not self.sshClient.before.strip():
					return prompt
				else:
					return ""
			else:
				return ""

		for i in range(0, len(strT)):
			x = strT[i]
			flag = True
			for j in range(1, len(strList)):
				kk = strList[j]
				if i > len(kk) or 0 != cmp(x, kk[i]):
					flag = False
					break
			if flag:
				promptPre = "%s%s" % (promptPre, x)
			else:
				break
		logger.debug("hostName:%s, origin promptPre:%r" % (self.hostName, promptPre))
	
		tL = list()
		for j in range(1, len(strList)):
			kk = strList[j]
			tL.append( kk[::-1] )
		promptPost = ""
		strY = strT[::-1]
		for i in range(0, len(strY)):
			x = strY[i]
			flag = True
			for p in tL:
				if i > len(p) or 0 != cmp(x, p[i]):
					flag = False
					break
			if flag:
				promptPost = "%s%s" % (promptPost, x)
			else:
				break
		logger.debug("%s origin promptPost:%r" % (self.hostName, promptPost))
	
		if promptPre and promptPost:
			prompt = "%s.+%s" % (self.dealRegxSpecialChar(promptPre), self.dealRegxSpecialChar(promptPost[::-1]))
			logger.debug("hostName:%s, prompt:%r" % (self.hostName, prompt))
			k = self.sshClient.expect([prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=8)
			logger.debug("hostName:%s, validating prompt, expect[%r, pexpect.EOF, pexpect.TIMEOUT], index=%d, before:%r, after:%r, buffer:%r" % (self.hostName, prompt, k, self.sshClient.before, self.sshClient.after, self.sshClient.buffer))
			if 0 == k:
				if not self.sshClient.before.strip():
					return prompt
				else:
					return ""
			else:
				return ""
		else:
			return ""



	def getPromptBySetPS1(self):
		self.clearOutputBuffer()
		self.sshClient.sendline ("unset PROMPT_COMMAND")

		self.sshClient.sendline ( "PS1='#PYSSH_VINC_PEXPECT# '" ) # sh-style
		# validation
		self.clearOutputBuffer()
		self.sshClient.sendline()
		i = self.sshClient.expect_exact([pexpect.TIMEOUT, '#PYSSH_VINC_PEXPECT# '], timeout=10)
		self.clearOutputBuffer()
		if 1 == i:
			return '#PYSSH_VINC_PEXPECT# '
		if 0 == i:
			self.sshClient.sendline ("set prompt='#PYSSH_VINC_PEXPECT# '") # csh-style
			self.clearOutputBuffer()
			self.sshClient.sendline()
			j = self.sshClient.expect_exact([pexpect.TIMEOUT, '#PYSSH_VINC_PEXPECT# '], timeout=10)
			self.clearOutputBuffer()
			if 1 == j:
				return '#PYSSH_VINC_PEXPECT# '
			else:
				return ""

	def get64or32(self):
		cmdRet = self.execCommand('uname -m | grep 64 | wc -l')
		tOutput = cmdRet['output'].strip()
		if 0 != cmdRet['code'] or (0 != cmp('0', tOutput) and 0 != cmp('1', tOutput)):
			logger.error('hostName:%s, get64or32, cmdRet:%r' % (self.hostName, cmdRet))
			return {'code':-6003, 'output':'can not determine 64 or 32, reason:%r' % tOutput}
		else:
			if 0 == cmp('1', tOutput):
				return {'code': 0, 'bit': '64'}
			else:
				return {'code': 0, 'bit': '32'}

	def getCurrentDirPath(self):
		cmdRet = self.execCommand('pwd')
		if 0 != cmdRet['code']:
			logger.error("hostName:%s, command:'pwd', result:%r", self.hostName, cmdRet)
			return {'code':-6001, 'output':'can not get current dir path, reason:%r' % cmdRet['output']}
		else:
			logger.debug("hostName:%s, command:'pwd', result:%r", self.hostName, cmdRet)
			return {'code':0, 'path':cmdRet['output'].strip()}
	
	def getHomePath(self):
		cmdRet = self.execCommand('echo ~')
		if 0 != cmdRet['code']:
			logger.error("hostName:%s, command:'echo ~', result:%r", self.hostName, cmdRet)
			return {'code':-6002, 'output':'can not get home path, reason:%r' % cmdRet['output']}
		else:
			logger.debug("hostName:%s, command:'echo ~', result:%r", self.hostName, cmdRet)
			return {'code':0, 'path':cmdRet['output'].strip()}



	def scpFromLocalPull(self,  localPath, sshHostPath, localPassword=None, localIsdir=False, localIntf=None, localPort=None, timeout=-1):
		if None is localIntf:
			localIntf = LOCAL_INTERFACE
		# get local user name
		try:
			localUser = getpass.getuser()
		except:
			logger.exception('hostName:%s, get local user name occurs exception', self.hostName)
			return {'code':-5001, 'output':'get local user name occurs exception'}
		# get local ip address
		try:
			localIP = util.getIP( localIntf )
			if None is localIP:
				return {'code':-5002, 'output':'can not get local ip address'}
		except:
			logger.exception('hostName:%s, get local ip address occurs exception', self.hostName)
			return {'code':-5003, 'output':'get local ip address occurs exception'}
		# local path, whether absolute path
		if not os.path.isabs(localPath):
			logger.error('hostName:%s, local path [%s] should be absolute path', self.hostName, localPath)
			return {'code': -5004, 'output':'localPath should be absolute path'}
		# localIsdir
		tR = ""
		if localIsdir:
			tR = "-r"
		# localPort
		tLPort = ""
		if not None is localPort:
			tLPort = "-P %d" % localPort
		#begin pull first
		# test pull from local
		if True is self.scpPullFromLocalFlag or (None is self.scpPullFromLocalFlag and self.scpPullFromLocalTest(sourceUser=localUser, sourcePassword=localPassword, sourceIfName=localIntf, sourcePort=localPort)):
			scpPullCommand = "scp %(R)s %(P)s %(localUser)s@%(localIP)s:%(localPath)s %(sshHostPath)s" % {
				'R' : tR,
				'P' : tLPort,
				'localUser' : localUser,
				'localIP' : localIP,
				'localPath' : localPath,
				'sshHostPath' : sshHostPath,
			}
			scpRet = self.execScpCommand(scpPullCommand, localPassword, timeout)
			if 0 != scpRet['code']:
				logger.error('hostName:%s, scp from local pull failed, command:%s, result:%r', self.hostName, scpPullCommand, scpRet)
				return {'code':-5018, 'output':'scp pull from local failed, error code:%d, reason:%r' % (scpRet['code'], scpRet['output'])}
			else:
				logger.info('hostName:%s, scp from local pull success, command:%s, result:%r', self.hostName, scpPullCommand, scpRet)
				return {'code':0, 'output':'scp pull from local success'}
		else:
			return {'code':-5019, 'output':'scp pull from local failed, can not pass test'}


	def scpFromLocalPush(self,  localPath, sshHostPath, localIsdir=False, timeout=-1):
		# test push from local
		if True is self.scpPushFromLocalFlag or (None is self.scpPushFromLocalFlag and  self.scpPushFromLocalTest()):
			# ssh port
			tSPort = ""
			if not None is self.port:
				tSPort = "-P %d" % self.port
			# deal ssh host path
			tSPath = sshHostPath
			if not os.path.isabs( sshHostPath ):
				if 0 == cmp('.', sshHostPath[0]) and (1 == len(sshHostPath) or (1 < len(sshHostPath) and 0 == cmp('/', sshHostPath[1]))):
					getCurDirPathRet = self.getCurrentDirPath()
					if 0 != getCurDirPathRet['code']:
						return {'code': getCurDirPathRet['code'], 'output':'can not get current dir path on ssh host, reason:%r' % getCurDirPathRet['output']}
					else:
						tSPath = "%s/%s" % (getCurDirPathRet['path'], sshHostPath[2:])
				elif 0 == cmp('~', sshHostPath[0]) and (1 == len(sshHostPath) or (1 < len(sshHostPath) and 0 == cmp('/', sshHostPath[1]))):
					getHomePathRet = self.getHomePath()
					if 0 != getHomePathRet['code']:
						return {'code': getCurDirPathRet['code'], 'output':'can not get current dir path on ssh host, reason:%r' % getCurDirPathRet['output']}
					else:
						tSPath = "%s/%s" % (getHomePathRet['path'], sshHostPath[2:])
				elif sshHostPath.startswith('..') and (2 == len(sshHostPath) or (2 < len(sshHostPath) and 0 == cmp('/', sshHostPath[2]))):
					getCurDirPathRet = self.getCurrentDirPath()
					if 0 != getCurDirPathRet['code']:
						return {'code': getCurDirPathRet['code'], 'output':'can not get current dir path on ssh host, reason:%r' % getCurDirPathRet['output']}
					else:
						tSPath = "%s/%s" % (getCurDirPathRet['path'], sshHostPath)
				elif sshHostPath.startswith('$HOME') and (5 == len(sshHostPath) or (5 < len(sshHostPath) and 0 == cmp('/', sshHostPath[5]))):
					getHomePathRet = self.getHomePath()
					if 0 != getHomePathRet['code']:
						return {'code': getHomePathRet['code'], 'output':'can not get home path on ssh host, reason:%r' % getHomePathRet['output']}
					else:
						tSPath = "%s/%s" % (getHomePathRet['path'], sshHostPath[6:])
				else:
					return {'code':-24, 'output':'can not get absolute ssh host path:%s' % sshHostPath}
			# localIsdir
			tR = ""
			if localIsdir:
				tR = "-r"
			scpPushCommand = "scp %(R)s %(P)s %(localPath)s %(sshUser)s@%(sshHost)s:%(sshHostPath)s" % {
				'R' : tR,
				'P' : tSPort,
				'localPath' : localPath,
				'sshUser' : self.user,
				'sshHost' : self.hostName,
				'sshHostPath' : tSPath,
			}
			scpRet = self.scpPushFromLocal(scpCommand=scpPushCommand, timeout=timeout)
			if 0 != scpRet['code']:
				logger.error('hostName:%s, scp from local push failed, command:%s, result:%r', self.hostName, scpPushCommand, scpRet)
				return {'code':scpRet['code'], 'output':'scp push from local failed, reason:%r' % scpRet['output']}
			else:
				logger.info('hostName:%s, scp from local push success, command:%s, result:%r', self.hostName, scpPushCommand, scpRet)
				return {'code':0, 'output':'scp push from local success'}
		else:
			return {'code':-5020, 'output':'scp push from local failed, can not pass test'}
			
	
	def scpFromLocalPullPush(self,  localPath, sshHostPath, localPassword=None, localIsdir=False, localIntf=None, localPort=None, timeout=-1):
		pullRet = self.scpFromLocalPull(localPath=localPath, sshHostPath=sshHostPath, localPassword=localPassword, localIsdir=localIsdir, localIntf=localIntf, localPort=localPort, timeout=timeout)
		if 0 == pullRet['code']:
			return pullRet
		else:
			self.scpPullFromLocalFlag = False
			pushRet = self.scpFromLocalPush(localPath=localPath, sshHostPath=sshHostPath, localIsdir=localIsdir, timeout=timeout)
			if 0 == pushRet['code']:
				return pushRet
			else:
				self.scpPushFromLocalFlag = False
		logger.error('hostName:%s, SCP_LOCAL_PULL_PUSH both direction failed', self.hostName)
		return {'code':-5017, 'output':'both direction failed'}

	def scpFromLocalPushPull(self,  localPath, sshHostPath, localPassword=None, localIsdir=False, localIntf=None, localPort=None, timeout=-1):
		pushRet = self.scpFromLocalPush(localPath=localPath, sshHostPath=sshHostPath, localIsdir=localIsdir, timeout=timeout)
		if 0 == pushRet['code']:
			return pushRet
		else:
			self.scpPushFromLocalFlag = False
			pullRet = self.scpFromLocalPull(localPath=localPath, sshHostPath=sshHostPath, localPassword=localPassword, localIsdir=localIsdir, localIntf=localIntf, localPort=localPort, timeout=timeout)
			if 0 == pullRet['code']:
				return pullRet
			else:
				self.scpPullFromLocalFlag = False
		logger.error('hostName:%s, SCP_LOCAL_PUSH_PULL both direction failed', self.hostName)
		return {'code':-5021, 'output':'both direction failed'}

	def userExists(self, userName):
		'''
		output: 0 yes; other no
		'''
		userExistsCommand = 'id %s' % userName.strip()
		self.sshClient.sendline( userExistsCommand )
		i = self.sshClient.expect([self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=PYSSH_DEFAULT_TIMEOUT)
		logger.info("hostName:%(hostName)s, command:%(command)s, expect['%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':userExistsCommand, 'prompt':self.prompt, 'timeout':PYSSH_DEFAULT_TIMEOUT, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 0:
			#userExistsOutput = self.getCommandOutput( self.sshClient.before )
			exitRet = self.getPreCommandExitValue()
			if 0 != exitRet['code']:
				logger.error('hostName:%s, error occurs when getting exit value for command:%s, reason:%r', self.hostName, userExistsCommand, exitRet)
				return {'code':-6018, 'output':'error occurs when getting exit value for command:%s, reason:%r' % (userExistsCommand, exitRet['output'])}
			else:
				if 0 == exitRet['output']:
					return {'code':0, 'output':0}
				else:
					return {'code':0, 'output':exitRet['output']}
		elif i == 1:
			logger.error("hostName:%s, command:%s, EOF occur", self.hostName, userExistsCommand)
			self.clearOutputBuffer()
			return {'code':-6019, 'output':'EOF occurs when executing command:%s' % userExistsCommand}
		elif i == 2:
			logger.error("hostName:%s, command:%s, timeout[%d] occur, then send control signal C", self.hostName, userExistsCommand, PYSSH_DEFAULT_TIMEOUT)
			self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code':-6020, 'output':'timeout[%d] occurs when executing command:%s' % (PYSSH_DEFAULT_TIMEOUT, userExistsCommand)}
	

	def changeUserPassword(self, userName, userPassword):
		changePasswdCommand = "passwd %s" % userName
		self.sshClient.sendline( changePasswdCommand )
		i = self.sshClient.expect(['(?i)new.*password', self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=PYSSH_DEFAULT_TIMEOUT)
		logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)new.*password', '%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':changePasswdCommand, 'prompt':self.prompt, 'timeout':PYSSH_DEFAULT_TIMEOUT, 'index':i, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
		if i == 0:
			self.sshClient.sendline( userPassword )
			p = self.sshClient.expect(['(?i)retype new.*password', self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=PYSSH_DEFAULT_TIMEOUT)
			logger.info("hostName:%(hostName)s, command:%(command)s, expect['(?i)retype new.*password', '%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':changePasswdCommand, 'prompt':self.prompt, 'timeout':PYSSH_DEFAULT_TIMEOUT, 'index':p, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
			if p == 0:
				self.sshClient.sendline( userPassword )
				q = self.sshClient.expect([self.prompt, pexpect.EOF, pexpect.TIMEOUT], timeout=PYSSH_DEFAULT_TIMEOUT)
				logger.info("hostName:%(hostName)s, command:%(command)s, expect['%(prompt)s', pexpect.EOF, pexpect.TIMEOUT], timeout=%(timeout)d, index=%(index)d, before:%(before)r, after:%(after)r, buffer:%(buffer)r" % {'hostName':self.hostName, 'command':changePasswdCommand, 'prompt':self.prompt, 'timeout':PYSSH_DEFAULT_TIMEOUT, 'index':q, 'before':self.sshClient.before, 'after':self.sshClient.after, 'buffer':self.sshClient.buffer})
				#if q == 0:
				#	logger.error("hostName:%s, command:%s, error occurs when adding user, still need password after giving password 2 times, then send control signal C", self.hostName, changePasswdCommand)
				#	self.sshClient.sendintr()
				#	self.clearOutputBuffer()
				#	return {'code':-6015, 'output':'error occurs when adding user, still need password after giving password 2 times'}

		if 1 == i or 1 == p or 0 == q:
			changePasswdOutput = self.getCommandOutput( self.sshClient.before )
			exitRet = self.getPreCommandExitValue()
			if 0 != exitRet['code']:
				logger.error('hostName:%s, error occurs when getting exit value for command:%s, reason:%r', self.hostName, changePasswdCommand, exitRet)
				return {'code':-6013, 'output':'error occurs when getting exit value for command:%s, reason:%r' % (changePasswdCommand, exitRet['output'])}
			else:
				if 0 == exitRet['output']:
					return {'code':0, 'output':changePasswdOutput}
				else:
					logger.error('hostName:%s, exec command finished, but exit value is not 0, command:%s, output:%r, getExitValueRet:%r', self.hostName, changePasswdCommand, changePasswdOutput, exitRet)
					return {'code':-6014, 'output':'exec command fininshed, but its exit valus is not 0, command:%s, exit value:%r' % (changePasswdCommand, exitRet['output'])}
		if 2 == i or 2 == p or 1 == q:
			logger.error("hostName:%s, command:%s, EOF occur", self.hostName, changePasswdCommand)
			self.clearOutputBuffer()
			return {'code':-6016, 'output':'EOF occurs when executing command:%s' % changePasswdCommand}
		if 3 == i or 3 == p or 2 == q:
			logger.error("hostName:%s, command:%s, timeout[%d] occur, then send control signal C", self.hostName, changePasswdCommand, PYSSH_DEFAULT_TIMEOUT)
			self.sshClient.sendintr()
			self.clearOutputBuffer()
			return {'code':-6017, 'output':'timeout[%d] occurs when executing command:%s' % (PYSSH_DEFAULT_TIMEOUT, changePasswdCommand)}



	def addUser(self, userName, userPassword=None, userHomePath=None, groupName=None):
		if None is userName or not userName.strip():
			return {'code':-6011, 'output':'error when creating user, userName can not be empty'}
		# whether user alreay exists
		userExistsRet = self.userExists( userName )
		if 0 != userExistsRet['code']:
			return userExistsRet
		if 0 == userExistsRet['output']:
			# already exists
			return {'code':-6021, 'output':'user %s already exists' % userName}
		else:
			# not exists
			# deal home path
			if None is not userHomePath and userHomePath.strip():
				userHomePath = userHomePath.strip()
				while 0 == cmp('/', userHomePath[-1]):
					userHomePath = userHomePath[0:-1]
				# whether exists
				if not self.testPathExists( userHomePath ):
					baseDir = os.path.dirname( userHomePath )
					execRet = self.execCommand( 'mkdir -p %s' % baseDir )
					if 0 != execRet['code']:
						logger.error('hostName:%s, command:%s, execRet:%r', self.hostName, 'mkdir -p %s' % baseDir, execRet)
						return {'code':-6010, 'output':'error when creating user home directory, reason:%r' % execRet['output']}
			# add user
			addUserCommand = 'useradd "%s"'  % userName
			if None is not userHomePath and userHomePath:
				addUserCommand = '%s -m -d %s' % (addUserCommand, userHomePath)
			if None is not groupName and groupName.strip():
				addUserCommand = '%s -g %s' % (addUserCommand, groupName)
			execRet = self.execCommand( addUserCommand )
			if 0 != execRet['code']:
				logger.error('hostName:%s, command:%s, execRet:%r', self.hostName, addUserCommand, execRet)
				return {'code':-6012, 'output':'error when adding user, reason:%r' % execRet['output']}

		# whether password
		if None is userPassword or not userPassword.strip():
			return execRet
		else:
			return self.changeUserPassword(userName=userName, userPassword=userPassword)
			





#########################
def main():
	pass

if __name__ == '__main__':
	main()
