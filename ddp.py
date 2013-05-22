#!/usr/bin/env python
#-*- coding:utf-8 -*-

# date:2013-01-10
# author: vinczhang

import sys, os
import platform
import logging, logging.config
import warnings
import re
import ConfigParser
import json
import copy
from multiprocessing import Process, Pipe, Value


libPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
sys.path.append( libPath )


#### DDP_ROOT_DIR is used in loggin.conf for relative log file path
DDP_ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
os.environ['DDP_ROOT_DIR'] = DDP_ROOT_DIR

loggingConfigFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conf/logging.conf')
logging.config.fileConfig( loggingConfigFile, disable_existing_loggers = False )
#logging.config.fileConfig( loggingConfigFile )
logger = logging.getLogger( __name__ )

import argparse
from cmdHostLY import cmdYacc
from cmdHostLY import hostYacc
from pyssh.PySSH import PySSH




#标志是否脚本方式使用
DDP_USED_AS_SCRIPT = False
#登陆时的重试次数
DDP_LOGIN_RETRY_TIMES = 3
#获取sshHomePath的重试次数
DDP_SSHHOMEPATH_RETRY_TIMES = 5


DDP_RUNNING_HOST = 10
DDP_RETRY_TIMES = 0
DDP_SUCCESS_HOSTS_FILE = "success_hosts.txt"
DDP_ERROR_HOSTS_FILE = "error_hosts.txt"
DDP_JSON_RESULT = 0
DDP_EXIT_USELESS_VALUE = -99999


## load config from config file ##
try:
	DDPConfigFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conf/ddp.conf')
	RCP = ConfigParser.RawConfigParser()
	RCP.read( DDPConfigFile )
	if RCP.has_section('ddp'):
		if RCP.has_option('ddp', 'running_host'):
			DDP_RUNNING_HOST = RCP.getint('ddp', 'running_host')
		if RCP.has_option('ddp', 'retry_times'):
			DDP_RETRY_TIMES = RCP.getint('ddp', 'retry_times')
		if RCP.has_option('ddp', 'success_hosts_file'):
			DDP_SUCCESS_HOSTS_FILE = RCP.get('ddp', 'success_hosts_file')
		if RCP.has_option('ddp', 'error_hosts_file'):
			DDP_ERROR_HOSTS_FILE = RCP.get('ddp', 'error_hosts_file')
		if RCP.has_option('ddp', 'json_result'):
			DDP_JSON_RESULT = RCP.getint('ddp', 'json_result')
		if RCP.has_option('ddp', 'exit_useless_value'):
			DDP_EXIT_USELESS_VALUE = RCP.getint('ddp', 'exit_useless_value')
except:
	logger.exception('load config from file exception, then define constant variable by code')

################################################################################################################


DDP_PRINT_PIPE_RECEIVER, DDP_PRINT_PIPE_SENDER = Pipe(duplex=False)
DDP_OPLOG_PIPE_RECEIVER, DDP_OPLOG_PIPE_SENDER = Pipe(duplex=False)
DDP_RESULT_PIPE_RECEIVER, DDP_RESULT_PIPE_SENDER = Pipe(duplex=False)


#################################################################################################################
def getHostList(hostsData):
	if not hostsData.strip():
		return {'code':-1019, 'msg':'no hosts'}
	parseRet = hostYacc.parseHostsFromData( hostsData )
	if 0 != parseRet['code']:
		return parseRet
	else:
		return {'code':0, 'hostList':parseRet['hostList']}

def getFirstCmdNode(cmdsData):
	if not cmdsData.strip():
		return {'code':-1020, 'msg':'no cmds'}
	parseRet = cmdYacc.parseCmdsFromData( cmdsData )
	if 0 != parseRet['code']:
		return parseRet
	else:
		return {'code':0, 'cmdNode':parseRet['cmdNode']}


#################################################################################################################

# for strip string
def stripCommandOutput(outputStr):
	headRule = re.compile( r'^[\r\n]*' )
	tailRule = re.compile( r'[\r\n]*$' )
	retStr = re.sub( headRule, '', outputStr)
	retStr = re.sub( tailRule, '', retStr)
	return retStr

####################################################################################################################
class PrintProcess(Process):
	def __init__(self):
		Process.__init__(self)
		self.switchFlag = Value('i', 1)
		self.receiver = DDP_PRINT_PIPE_RECEIVER
		self.sender = DDP_PRINT_PIPE_SENDER

	def turnOff(self):
		self.switchFlag.value = 0
		self.sender.send( None )		#there must be one more put into sender, or print may be block forever


	def run(self):
		while 1 == self.switchFlag.value or self.receiver.poll():
			tItem = self.receiver.recv()
			if tItem is None:
				continue
			print ""
			if isinstance(tItem, str):
				print tItem
			elif isinstance(tItem, list):
				for tStr in tItem:
					print tStr
			else:
				tDict = tItem
				tHost = tDict['host']
				print "host: %s" % tHost['hostName']
				tCmdNode = tDict['cmdNode']
				tExecRet = tDict['execRet']
				if 0 == cmp('exit', tCmdNode.category):
					if 0 == tExecRet['code']:
						print "exit: %d" % tCmdNode.value
						if 0 != cmp('', tExecRet['msg']):
							print "exit msg:\n%s" % stripCommandOutput( tExecRet['output'] )
					else:
						print "msg: !!!ERROR!!! error when exec EXIT command, error code:%d, reason:%r" % (tExecRet['code'], tExecRet['output'])
				elif tCmdNode.category in ['cmd', 'if', 'while', 'do_while',]:
					print "command: %s" % tExecRet['realCommand']
					if tExecRet['output'].strip():
						print "output:\n%s" % stripCommandOutput(tExecRet['output'])
					if 0 == cmp('cmd', tCmdNode.category):
						if 1 == tExecRet['code']:
							print "msg: %s" % 'exec failed, but no matter'
						elif 0 == tExecRet['code']:
							print "msg: %s" % 'exec ok'
						else:
							print "msg: %s" % '!!!ERROR!!! error code:%d' % tExecRet['code'] 
					else: 
						if 0 == tExecRet['code']:
							print "msg: exec ok, then following Y"
						else:
							print "msg: exec failed, error code:%d, then following N" % tExecRet['code']
				else:
					print "msg: %s" % "%%%%%% UNKNOWN CATEGORY %%%%%%"
		#close connection
		#self.sender.close()
		#self.receiver.close()
		#logger.debug('PrintProcess sender and receiver close')
					

######################################################################################################################
class OPLogProcess(Process):
	def __init__(self, outputFilePath):
		Process.__init__(self)
		self.outputFilePath = outputFilePath
		self.switchFlag = Value('i', 1)
		self.receiver = DDP_OPLOG_PIPE_RECEIVER
		self.sender = DDP_OPLOG_PIPE_SENDER


	def turnOff(self):
		self.switchFlag.value = 0
		self.sender.send(None)		#there must be one more, or may be block forever

	def run(self):
		# open file to write
		wFile = open(self.outputFilePath, 'w')
		while 1 == self.switchFlag.value or self.receiver.poll():
			tElement = self.receiver.recv()
			if None is tElement:
				continue
			elif isinstance(tElement, str):
				wFile.write('\n')
				wFile.write('%s\n' % tElement)
				continue
			elif isinstance(tElement, list):
				wFile.write('\n')
				for tStr in tElement:
					wFile.write("%s\n" % tStr)
				continue
			tHost = tElement['host']
			tOPLogList = tElement['opLogList']
			# header
			wFile.write('---------------- START HOST: %s ---------------------\n' % tHost['hostName'])
			wFile.write('HOST: %s\n' % tHost['hostName'])
			if not 'TAG' in tHost or 0 == len(tHost['TAG']):
				wFile.write('NO TAG\n')
			else:
				tStr = ''
				for qStr in tHost['TAG']:
					tStr = "%s , %s" % (tStr, qStr)
				wFile.write("TAG: %s\n" % tStr[3:])
			# deal op log list
			for tItem in tOPLogList:
				if tItem is None:
					continue
				wFile.write('\n')
				if isinstance(tItem, str):
					wFile.write("%s\n" % tItem)
				elif isinstance(tItem, list):
					for tStr in tItem:
						wFile.write("%s\n" % tStr)
				else:
					tDict = tItem
					tCmdNode = tDict['cmdNode']
					tExecRet = tDict['execRet']
					if 0 == cmp('exit', tCmdNode.category):
						if 0 == tExecRet['code']:
							wFile.write("exit: %d\n" % tCmdNode.value)
							if 0 != cmp('', tExecRet['output']):
								wFile.write("exit msg:\n%s\n" % stripCommandOutput(tExecRet['output']))
						else:
							wFile.write("msg: !!!ERROR!!! exec EXIT command error, error code:%d, reason:%r\n" % (tExecRet['code'], tExecRet['output']))
					elif tCmdNode.category in ['cmd', 'if', 'while', 'do_while',]:
						wFile.write("command: %s\n" % tExecRet['realCommand'])
						if tExecRet['output'].strip():
							wFile.write("output:\n%s\n" % stripCommandOutput(tExecRet['output']))
						if 0 == cmp('cmd', tCmdNode.category):
							if 1 == tExecRet['code']:
								wFile.write("msg: %s\n" % 'exec failed, but no matter')
							elif 0 == tExecRet['code']:
								wFile.write("msg: %s\n" % 'exec ok')
							else:
								wFile.write("msg: !!!ERROR!!! error code:%d\n" % tExecRet['code'])
						else:
							if 0 == tExecRet['code']:
								wFile.write('msg: exec ok, then following Y\n')
							else:
								wFile.write('msg: exec failed, error code:%d, then following N\n' % tExecRet['code'])
					else:
						wFile.write("msg: %s\n" % "%%%%%% UNKNOWN CATEGORY %%%%%%")
			#footer
			wFile.write('================ END HOST: %s =====================\n\n' % tHost['hostName'])
			#flush
			wFile.flush()
		# close file
		wFile.close()



#####################################################################################################################
class SSHHost(Process):
	def __init__(self, host, firstCmdNode, cmdVars=dict(), retryTimes=None, quietMode=False, outputFileQuietMode=True):
		Process.__init__(self)
		self.host = copy.deepcopy( host )
		self.firstCmdNode = firstCmdNode

		self.quietMode = quietMode
		self.outputFileQuietMode = outputFileQuietMode

		#set process name
		self.name = host['hostName']

		self.printSender = DDP_PRINT_PIPE_SENDER
		self.resultSender = DDP_RESULT_PIPE_SENDER
		self.opLogSender = DDP_OPLOG_PIPE_SENDER

		self.opLogList = list()

		if None is cmdVars:
			self.cmdVars = dict()
		else:
			self.cmdVars = copy.deepcopy( cmdVars )
		# put host['cmdVars'] into self.cmdVars
		if 'cmdVars' in host:
			for (k, v) in host['cmdVars'].items():
				self.cmdVars[ k ]  = v
		# put sshHostName, sshIP(if hostName is ip address), sshUser, sshPort(if not None) to cmdVars
		if re.match(r'\d+\.\d+\.\d+\.\d+', host['hostName']):
			self.cmdVars['sshIP'] = host['hostName']
		self.cmdVars['sshHostName'] = self.host['hostName']
		self.cmdVars['sshUser'] = host['user']
		if not None is host['port']:
			self.cmdVars['sshPort'] = host['port']

		if None is retryTimes: self.retryTimes = DDP_RETRY_TIMES
		else: self.retryTimes = retryTimes		# retry times after error
		self.retry = list()					# retry error info

		logger.debug('processName:%s, init SSHHost, hostName:%s, user:%s, port:%r, cmdVars:%r', self.name, self.host['hostName'], self.host['user'], self.host['port'], self.cmdVars)



	def execCmdNode(self, cmdNode):
		'''
		code:
			0 : exec success
			1 : exec faild, but NM (no matter)
			< 0 : failed
		'''
		logger.debug("processName:%s, exec cmdNode:%s, cmdVars:%r", self.name, cmdNode, self.cmdVars)
		if 'TL' in cmdNode.adjs:
			tTimeout = cmdNode.adjs['TL']
		elif 'NTOL' in cmdNode.adjs and True is cmdNode.adjs['NTOL']:
			tTimeout = None
		else:
			tTimeout = -1
		# replace vars in adjs and command, to avoid changing origin cmdNode then should use a copy
		realAdjs = copy.deepcopy( cmdNode.adjs )
		realCommand = cmdNode.command
		tIdentityRule = re.compile( r'[a-zA-Z_][a-zA-Z_0-9]*' )
		tRule = re.compile( r'(\{#(.*?)#\})' )
		tFList = re.findall( tRule, realCommand )
		for item in tFList:
			if not re.match(tIdentityRule, item[1]):
				return {'realCommand':realCommand, 'realAdjs':realAdjs, 'code':-7003, 'output':'%s is not proper' % item[0]}
			if item[1] in self.cmdVars:
				realCommand = realCommand.replace( item[0], self.cmdVars[item[1]] )
			else:
				return {'realCommand':realCommand, 'realAdjs':realAdjs, 'code':-7004, 'output':'%s is not a define variable' % item[0]}
		for (k, v) in realAdjs.items():
			if isinstance(v, str):
				tFList = re.findall( tRule, v )
				for item in tFList:
					if not re.match(tIdentityRule, item[1]):
						return {'realCommand':realCommand, 'realAdjs':realAdjs, 'code':-7005, 'output':'%s in %s is not proper' % (item[0], k)}
					if item[1] in self.cmdVars:
						realAdjs[k] = realAdjs[k].replace( item[0], self.cmdVars[item[1]] )
					else:
						return {'realCommand':realCommand, 'realAdjs':realAdjs, 'code':-7006, 'output':'%s in %s is not a define variable' % (item[0], k)}
		# exec realCommand, then deal result
		execRet = self.pysshAgent.execCommand(command=realCommand, commandExt=realAdjs, timeout=tTimeout)
		retDict = {
			'realCommand' : realCommand,
			'realAdjs' : realAdjs,
		}
		if 0 != execRet['code']:
			# failed
			if 'NM' in realAdjs and realAdjs['NM'] is True:
				logger.warning('processName:%s, command:%s, execRet:%r', self.name, realCommand, execRet)
				retDict['code'] = 1
				retDict['output'] = execRet['output']
			else:
				logger.error('processName:%s, command:%s, execRet:%r', self.name, realCommand, execRet)
				retDict['code'] = execRet['code']
				retDict['output'] = execRet['output']
		else:
			# success
			if 'VAR' in realAdjs:
				self.cmdVars[ realAdjs['VAR'] ] = execRet['output'].strip()
			if 'ASSERT' in realAdjs:
				if 0 == cmp(realAdjs['ASSERT'], execRet['output'].strip()):
					logger.debug('processName:%s, command:%s, execRet:%r', self.name, realCommand, execRet)
					# assert success
					retDict['code'] = execRet['code']
					retDict['output'] = execRet['output']
				else:
					logger.error('processName:%s, command:%s, execRet:%r', self.name, realCommand, execRet)
					# assert failed
					retDict['code'] = -7007
					retDict['output'] = "ASSERT failed, assert:%s, output:%r" % (realAdjs['ASSERT'], execRet['output'].strip())
			else:
				logger.debug('processName:%s, command:%s, execRet:%r', self.name, realCommand, execRet)
				retDict['code'] = execRet['code']
				retDict['output'] = execRet['output']
		return retDict

	
	def isBelongsSelfCmdNode(self, cmdNode):
		if not 'TAG' in cmdNode.adjs or 0 == len(cmdNode.adjs['TAG']):
			return True
		else:
			if not 'TAG' in self.host or 0 == len(self.host['TAG']):
				return False
			else:
				for item in cmdNode.adjs['TAG']:
					if item in self.host['TAG']:
						return True
				return False

	def printOP(self, obj):
		if True is self.quietMode:
			return
		self.printSender.send( obj )

	def outputOP(self, obj):
		if True is self.outputFileQuietMode:
			return
		self.opLogSender.send( obj )


	def run(self):
		'''
		result type:
			1 : success, terminal because of exit command
			0 : success, and no meet with EXIT command
			-1 : login failed
			-2 : exec command failed
			-3 : exec EXIT command failed
			-4 : error when getting sshHomePath
		'''
		logger.info('process start:%s', self.name)

		loginRetryCounter = 0
		# login
		self.pysshAgent = PySSH(hostName=self.host['hostName'], user=self.host['user'], password=self.host['password'], port=self.host['port'])
		while True:
			loginRet = self.pysshAgent.login()
			if 0 != loginRet['code']:
				if loginRetryCounter >= DDP_LOGIN_RETRY_TIMES:
					logger.error('processName:%s, login error, login ret:%r', self.name, loginRet)
					self.printOP( ['host: %s' % self.host['hostName'], 'msg: @@@LOGIN FAILED@@@ reason:%r' % loginRet['output']] )
					self.resultSender.send( {'host':self.host, 'type':-1, 'loginRet':loginRet} )
					self.opLogList.append( ['@@@LOGIN FAILED@@@', 'login error code:%d' % loginRet['code'], 'reason:%r' % loginRet['output']] )
					self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
					return 
				else:
					loginRetryCounter += 1
					logger.warning('processName:%s, login failed, login result:%r, but retry again, retryTimes:%d, retryCounter:%d', self.name, loginRet, DDP_LOGIN_RETRY_TIMES, loginRetryCounter)
					#self.printOP( ['host: %s' % self.host['hostName'], 'msg: login failed, login result:%r, but retry again, retryTimes:%d, retryCounter:%d' % (loginRet, DDP_LOGIN_RETRY_TIMES, loginRetryCounter), ] )
					#self.opLogList.append( ['@@@LOGIN FAILED@@@', 'login error code:%d' % loginRet['code'], 'reason:%r' % loginRet['output'], 'msg: retry again, retryTimes:%d, retryCounter:%d' % (DDP_LOGIN_RETRY_TIMES, loginRetryCounter)] )
					continue
			else:
				logger.info('processName:%s, login success, loginRet:%r', self.name, loginRet)
				self.printOP( ['host: %s' % self.host['hostName'], 'msg: login success'] )
				self.opLogList.append( ['msg: login success',] )
				break

		#set sshHomePath in cmdVars
		getHomePathRetryCounter = 0
		while True:
			execRet = self.pysshAgent.execCommand( "cd ~" )
			if 0 != execRet['code']:
				if getHomePathRetryCounter >= DDP_SSHHOMEPATH_RETRY_TIMES:
					logger.error('processName:%s, exec [cd ~] command error when getting sshHomePath error, ret:%r', self.name, execRet)
					self.resultSender.send( {'host':self.host, 'type':-4, 'execRet':execRet} )
					self.opLogList.append( ['!!!ERROR!!! exec [cd ~] command error when getting sshHomePath', 'error code:%d, reason:%r' % (execRet['code'], execRet['output'])] )
					self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
					return 
				else:
					getHomePathRetryCounter += 1
					continue
			else:
				execRet = self.pysshAgent.execCommand( "pwd" )
				if 0 != execRet['code']:
					if getHomePathRetryCounter >= DDP_SSHHOMEPATH_RETRY_TIMES:
						logger.error('processName:%s, exec [pwd] command error when getting sshHomePath error, ret:%r', self.name, execRet)
						self.resultSender.send( {'host':self.host, 'type':-4, 'execRet':execRet} )
						self.opLogList.append( ['!!!ERROR!!! exec [pwd] command error when getting sshHomePath', 'error code:%d, reason:%r' % (execRet['code'], execRet['output'])] )
						self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
						return 
					else:
						getHomePathRetryCounter += 1
						continue
				else:
					self.cmdVars[ 'sshHomePath' ] = execRet['output'].strip()
					logger.info('processName:%s, get sshHomePath success:%s', self.name, self.cmdVars['sshHomePath'])
					break


		# init retry counter
		retryCounter = 0
		# execute cmds
		curCmdNode = self.firstCmdNode
		while not curCmdNode is None:
			if 0 == cmp('exit', curCmdNode.category):
				# replace exit msg with vars
				realExitMsg = curCmdNode.msg
				tIdentityRule = re.compile( r'[a-zA-Z_][a-zA-Z_0-9]*' )
				tRule = re.compile( r'(\{#(.*?)#\})' )
				tFList = re.findall( tRule, curCmdNode.msg )
				tCode = 0
				for item in tFList:
					if not re.match(tIdentityRule, item[1]):
						tCode = -7001
						tMsg = '%s is not proper' % item[0]
						break
					if item[1] in self.cmdVars:
						realExitMsg = realExitMsg.replace( item[0], self.cmdVars[item[1]] )
					else:
						tCode = -7002
						tMsg = '%s is not a define variable' % item[0]
						break
				if tCode == 0:
					logger.info('processName:%s, meet EXIT command, exit value:%d, msg:%r', self.name, curCmdNode.value, realExitMsg)
					self.printOP( {'host':self.host, 'cmdNode':curCmdNode, 'execRet':{'code':0, 'output':realExitMsg},} )
					self.resultSender.send( {'host':self.host, 'type':1, 'exit':curCmdNode.value, 'msg':realExitMsg} )
					self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':{'code':0, 'output':realExitMsg}} )
					self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
				else:
					logger.error('processName:%s, meet EXIT command error, error code:%d, reason:%s', self.name, tCode, tMsg)
					self.printOP( ['host: %s' % self.host['hostName'], 'msg: !!!ERROR!!!, EXIT command error, error code:%d, reason:%s' % (tCode, tMsg), ] )
					self.resultSender.send( {'host':self.host, 'type':-3, 'errorCmdNode':curCmdNode, 'execRet':{'code':tCode, 'output':tMsg}} )
					self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':{'code':tCode, 'output':tMsg}} )
					self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
				return 
			elif 0 == cmp('cmd', curCmdNode.category):
				if not self.isBelongsSelfCmdNode(curCmdNode):
					logger.debug('processName:%s, this CmdNode not bellongs self, continue, curCmdNode:%s', self.name, curCmdNode)
					curCmdNode = curCmdNode.child
					continue
				execRet = self.execCmdNode(curCmdNode)
				self.printOP( {'host':self.host, 'cmdNode':curCmdNode, 'execRet':execRet} )
				if execRet['code'] >= 0:
					logger.info('processName:%s, command:%s, result code:%d, output:%r', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':execRet} )
					curCmdNode = curCmdNode.child
				else:
					if retryCounter >= self.retryTimes:
						logger.error('processName:%s, command:%s, result code:%d, output:%r', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
						self.resultSender.send( {'host':self.host, 'type':-2, 'errorCmdNode':curCmdNode, 'execRet':execRet} )
						self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':execRet} )
						self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )
						return
					else:
						retryCounter += 1
						logger.warning('processName:%s, exec command failed, command:%s, code:%d, reason:%r, but retry again, retryTimes:%d, retryCounter:%d', self.name, execRet['realCommand'], execRet['code'], execRet['output'], self.retryTimes, retryCounter)
						self.retry.append( 'retryTimes:%d, retryCounter:%d, exec command failed, command:%s, error code:%d, reason:%r' % (self.retryTimes, retryCounter, execRet['realCommand'], execRet['code'], execRet['output']) )
						self.printOP( ['host: %s' % self.host['hostName'], 'command: %s' % execRet['realCommand'], 'output:\n%s' % stripCommandOutput(execRet['output']), 'msg: exec command failed, but retry again, retryTimes:%d, retryCounter:%d' % (self.retryTimes, retryCounter), ] )
						self.opLogList.append( ['command: %s' % execRet['realCommand'], 'output:\n%s' % stripCommandOutput(execRet['output']), 'msg: retry again, retryTimes:%d, retryCounter:%d' % (self.retryTimes, retryCounter)] )
						#curCmdNode = self.firstCmdNode
						continue
			elif 0 == cmp('if', curCmdNode.category):
				if not self.isBelongsSelfCmdNode(curCmdNode.condition):
					logger.debug('processName:%s, this CmdNode not bellongs self, continue, curCmdNode:%s', self.name, curCmdNode)
					curCmdNode = curCmdNode.junction
					continue
				execRet = self.execCmdNode( curCmdNode.condition )
				self.printOP( {'host':self.host, 'cmdNode':curCmdNode, 'execRet':execRet} )
				self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':execRet} )
				if 0 == execRet['code']:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following Y', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.Y
				else:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following N', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.N
			elif 0 == cmp('while', curCmdNode.category):
				if not self.isBelongsSelfCmdNode(curCmdNode.condition):
					logger.debug('processName:%s, this CmdNode not bellongs self, continue, curCmdNode:%s', self.name, curCmdNode)
					curCmdNode = curCmdNode.N
					continue
				execRet = self.execCmdNode( curCmdNode.condition )
				self.printOP( {'host':self.host, 'cmdNode':curCmdNode, 'execRet':execRet} )
				self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':execRet} )
				if 0 == execRet['code']:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following Y', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.Y
				else:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following N', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.N
			elif 0 == cmp('do_while', curCmdNode.category):
				if not self.isBelongsSelfCmdNode(curCmdNode.condition):
					logger.debug('processName:%s, this CmdNode not bellongs self, continue, curCmdNode:%s', self.name, curCmdNode)
					curCmdNode = curCmdNode.N
					continue
				execRet = self.execCmdNode( curCmdNode.condition )
				self.printOP( {'host':self.host, 'cmdNode':curCmdNode, 'execRet':execRet} )
				self.opLogList.append( {'cmdNode':curCmdNode, 'execRet':execRet} )
				if 0 == execRet['code']:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following Y', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.Y
				else:
					logger.info('processName:%s, command:%s, result code:%d, output:%r, following N', self.name, execRet['realCommand'], execRet['code'], execRet['output'])
					curCmdNode = curCmdNode.N
		# exec all cmds, and no meet with EXIT command
		logger.info('processName:%s, fininsh all cmds and no meet with EXIT command', self.name)
		self.printOP( ['hosts: %s' % self.host['hostName'], 'msg: success, finish all cmds, and no meet with EXIT command'] )
		self.resultSender.send( {'host':self.host, 'type':0} )
		self.opLogList.append( ['finish all cmds, and no meet with EXIT command'] )
		self.outputOP( {'host':self.host, 'opLogList':self.opLogList} )

		# close pyssh
		self.pysshAgent.close()

		logger.info('process finished:%s', self.name)
		



##################################################################################################################

class ResultProcess(Process):
	def __init__(self, cmdsData=None, quietFiles=False, successHostsFile=None, errorHostsFile=None):
		Process.__init__(self)
		
		self.receiver = DDP_RESULT_PIPE_RECEIVER
		self.sender = DDP_RESULT_PIPE_SENDER

		self.opLogSender = DDP_OPLOG_PIPE_SENDER
		self.printSender = DDP_PRINT_PIPE_SENDER

		# deal parameters
		if None is successHostsFile: self.successHostsFile = DDP_SUCCESS_HOSTS_FILE
		else: self.successHostsFile = successHostsFile

		if None is errorHostsFile: self.errorHostsFile = DDP_ERROR_HOSTS_FILE
		else: self.errorHostsFile = errorHostsFile

		self.quietFiles = quietFiles
		self.cmdsData = cmdsData

		self.switchFlag = Value('i', 1)

		self.sFile = None
		self.eFile = None


	def turnOff(self):
		self.switchFlag.value = 0
		self.sender.send( None )

	def closeSucc(self):
		if None is self.sFile:
			return
		self.sFile.close()

	def closeErr(self):
		if None is self.eFile:
			return
		self.eFile.close()


	def writeSucc(self, obj):
		if None is self.sFile:
			return
		if isinstance(obj, list):
			self.sFile.write("%s\n" % "\n".join(obj))
		else:
			self.sFile.write("%s\n" % obj)
		self.sFile.flush()
	
	def writeErr(self, obj):
		if None is self.eFile:
			return
		if isinstance(obj, list):
			self.eFile.write("%s\n" % "\n".join(obj))
		else:
			self.eFile.write("%s\n" % obj)
		self.eFile.flush()

	def run(self):
		logger.info("result worker starts")
	
		if not self.quietFiles:
			# success host file
			self.sFile = open(self.successHostsFile, 'w')
			# error host file
			self.eFile = open(self.errorHostsFile, 'w')
	
		# get cmds content except comments
		if not None is self.cmdsData:
			tCmdList = re.split(r';|\r?\n', self.cmdsData)
			tList = list()
			for line in tCmdList:
				if line.strip() and not line.strip().startswith('#'):
					tList.append( '#%s' % line )
			self.writeSucc(tList)
			self.writeErr(tList)
	
		# insert decorate lines
		self.writeSucc('#-----------------------------------------------------------------------------------')
		self.writeErr('#-----------------------------------------------------------------------------------')
	
		resultStatDict = {
			'success': {1:0, 0:0},
			'error' : {-1:0, -2:0, -3:0, -4:0},
		}
		unknownCounter = 0
		errorHostCounter = 0
		hostResultDict = dict()
		errorHostList = list()
		while 1 == self.switchFlag.value or self.receiver.poll():
			tResultItem = self.receiver.recv()
			if None is tResultItem:
				continue
			tHost = tResultItem['host']
			# generate host string
			tHostStr = ""
			if 'TAG' in tHost and 0 < len(tHost['TAG']):
				for tTag in tHost['TAG']:
					tHostStr = "%s , %s" % (tHostStr, tTag)
				tHostStr = "%s :: " % tHostStr[3:]
			if re.match(r'\d+\.\d+\.\d+\.\d+', tHost['hostName']):
				tHostStr = "%s%s" % (tHostStr, tHost['hostName'])
			else:
				tHostStr = '%s"%s"' % (tHostStr, tHost['hostName'])
			tHostStr = '%s\t"%s"' % (tHostStr, tHost['user'])
			if not None is tHost['password'] and 0 != cmp("", tHost['password']):
				tHostStr = '%s\t"%s"' % (tHostStr, tHost['password'])
			if not None is tHost['port']:
				tHostStr = '%s\t%d' % (tHostStr, tHost['port'])
	
			# generate comment string
			if 1 == tResultItem['type']:
				resultStatDict['success'][1] += 1
				self.writeSucc("%s\t#%s" % (tHostStr, 'EXIT %d' % tResultItem['exit']))
				hostResultDict[ tHost['hostName'] ] = {'code':0, 'exit':tResultItem['exit'], 'msg':tResultItem['msg']}
			elif 0 == tResultItem['type']: 
				resultStatDict['success'][0] += 1
				self.writeSucc("%s\t#%s" % (tHostStr, 'fininshed'))
				hostResultDict[ tHost['hostName'] ] = {'code':0, 'exit':0, 'msg':''}
			elif -1 == tResultItem['type']:
				resultStatDict['error'][-1] += 1
				errorHostCounter += 1
				errorHostList.append( tHost['hostName'] )
				tLoginRet = tResultItem['loginRet']
				self.writeErr("%s\t#%s" % (tHostStr, '@@@LOGIN FAILED@@@, error code:%d, reason:%r' % (tLoginRet['code'], tLoginRet['output'])))
				hostResultDict[ tHost['hostName'] ] = {'code':1, 'exit':tLoginRet['code'], 'msg': "%r" % tLoginRet['output']}
			elif -2 == tResultItem['type']:
				resultStatDict['error'][-2] += 1
				errorHostCounter += 1
				errorHostList.append( tHost['hostName'] )
				tErrorCmdNode = tResultItem['errorCmdNode']
				tExecRet = tResultItem['execRet']
				self.writeErr("%s\t#%s" % (tHostStr, '!!!ERROR!!!, command lineno:%d, command:%s, error code:%d, reason:%r' % (tErrorCmdNode.lineno, tExecRet['realCommand'], tExecRet['code'], tExecRet['output'])))
				hostResultDict[ tHost['hostName'] ] = {'code':2, 'exit':tExecRet['code'], 'msg':'exec command failed, command:%s, reason:%r' % (tExecRet['realCommand'], tExecRet['output'])}
			elif -3 == tResultItem['type']:
				resultStatDict['error'][-3] += 1
				errorHostCounter += 1
				errorHostList.append( tHost['hostName'] )
				tErrorCmdNode = tResultItem['errorCmdNode']
				tExecRet = tResultItem['execRet']
				self.writeErr("%s\t#%s" % (tHostStr, '!!!ERROR!!!, exec EXIT command error, lineno:%d, error code:%d, reason:%r' % (tErrorCmdNode.lineno, tExecRet['code'], tExecRet['output'])))
				hostResultDict[ tHost['hostName'] ] = {'code':3, 'exit':tExecRet['code'], 'msg':'exec EXIT command failed, reason:%r' % tExecRet['output']}
			elif -4 == tResultItem['type']:
				resultStatDict['error'][-4] += 1
				errorHostCounter += 1
				errorHostList.append( tHost['hostName'] )
				tExecRet = tResultItem['execRet']
				self.writeErr("%s\t#%s" % (tHostStr, '!!!ERROR!!! error when getting sshHomePath, error code:%d, reason:%r' % (tExecRet['code'], tExecRet['output'])))
				hostResultDict[ tHost['hostName'] ] = {'code':4, 'exit':tExecRet['code'], 'msg':'error when getting sshHomePath, reason:%r' % tExecRet['output']}
			else:
				unknownCounter += 1
				errorHostList.append( tHost['hostName'] )
				logger.error("unknown result item in resultQueue:%r", tResultItem)
				self.printSender.send( "!!!ERROR!!!: unknown result item:%r", tResultItem)
				hostResultDict[ tHost['hostName'] ] = {'code':4, 'exit':DDP_EXIT_USELESS_VALUE, 'msg':'unknown'}
	
		# insert decorate lines
		self.writeSucc('#-----------------------------------------------------------------------------------')
		self.writeErr('#-----------------------------------------------------------------------------------')
		# stat infos
		tStrList = list()
		tStrList.append("FININSHED ALL HOSTS, STATISTICS INFO")
		tStrList.append("success and no meet with EXIT command host's counter: %d" % resultStatDict['success'][0])
		tStrList.append("success, terminal because of EXIT command host's counter: %d" % resultStatDict['success'][1])
		tStrList.append("error, login failed host's counter: %d" % resultStatDict['error'][-1])
		tStrList.append("error, command failed host's counter: %d" % resultStatDict['error'][-2])
		tStrList.append("error, EXIT command failed host's counter: %d" % resultStatDict['error'][-3])
		tStrList.append("error, get sshHomePath failed host's counter: %d" % resultStatDict['error'][-4])
		if unknownCounter > 0:
			tStrList.append("unknown result counter:%d" % unknownCounter)
		self.printSender.send( tStrList )
		self.opLogSender.send( tStrList )

		for tStr in tStrList:
			self.writeSucc( '#%s' % tStr )
			self.writeErr( '#%s' % tStr )
		
		#close files
		self.closeSucc()
		self.closeErr()
	
		errorHostCounter += unknownCounter
		tRetDict = {
			'code': errorHostCounter,
			'msg': ';'.join(errorHostList),
			'hosts': hostResultDict,
		}

		# return final result by result pipe
		#self.retDict.value = json.dumps( tRetDict )
		self.sender.send( tRetDict )

#################################################################################################################################################


def setGlobalVar(retryTimes=None, workersNO=None, successHostsFile=None, errorHostsFile=None):
	global DDP_RUNNING_HOST
	global DDP_RETRY_TIMES
	global DDP_SUCCESS_HOSTS_FILE
	global DDP_ERROR_HOSTS_FILE
	global DDP_QUIET_MODE
	global DDP_OUTPUT_MODE

	if not None is workersNO:
		if workersNO < 1: DDP_RUNNING_HOST = 1
		else: DDP_RUNNING_HOST = workersNO
	if not None is retryTimes:
		if retryTimes < 0: DDP_RETRY_TIMES = 0
		else: DDP_RETRY_TIMES = retryTimes
	if not None is successHostsFile:
		DDP_SUCCESS_HOSTS_FILE = successHostsFile.strip()
	if not None is errorHostsFile:
		DDP_ERROR_HOSTS_FILE = errorHostsFile.strip()
		

def checkArgs(hostsFile=None, cmdsFile=None, output=None, successHostsFile=None, errorHostsFile=None, quietFiles=False):
	# hostsFile
	if hostsFile and hostsFile.strip():
		hostsFile = hostsFile.strip()
		if not os.path.isfile( hostsFile ):
			return {'code':-1002, 'msg':'hostsFile [%s] is not a file' % hostsFile}
		if not os.access(hostsFile, os.R_OK):
			return {'code':-1003, 'msg':'hostsFile [%s] can not be read' % hostsFile}
	# cmdsFile
	if cmdsFile and cmdsFile.strip():
		cmdsFile = cmdsFile.strip()
		if not os.path.isfile( cmdsFile ):
			return {'code':-1004, 'msg':'cmdsFile [%s] is not a file' % cmdsFile}
		if not os.access(cmdsFile, os.R_OK):
			return {'code':-1005, 'msg':'cmdsFile [%s] can not be read' % cmdsFile}
	# quietFiles
	if not quietFiles:
		# errorHostsFile
		if errorHostsFile and errorHostsFile.strip():
			errorHostsFile = errorHostsFile.strip()
			if os.path.exists( errorHostsFile ):
				if not os.path.isfile( errorHostsFile ):
					return {'code':-1006, 'msg':'errorHostsFile [%s] existed before, but it is not a file' % errorHostsFile}
				if not os.access(errorHostsFile, os.W_OK):
					return {'code':-1007, 'msg':'errorHostsFile [%s] can not be writed' % errorHostsFile}
			else:
				try:
					tFile = open(errorHostsFile, 'a')
					tFile.close()
					os.remove( tFile.name )
				except:
					return {'code':-1008, 'msg':'errorHostsFile [%s] can not be created' % errorHostsFile}
		# successHostsFile
		if successHostsFile and successHostsFile.strip():
			successHostsFile = successHostsFile.strip()
			if os.path.exists( successHostsFile ):
				if not os.path.isfile( successHostsFile ):
					return {'code':-1009, 'msg':'successHostsFile [%s] existed before, but it is not a file' % successHostsFile}
				if not os.access(successHostsFile, os.W_OK):
					return {'code':-1010, 'msg':'successHostsFile [%s] can not be writed' % successHostsFile}
			else:
				try:
					tFile = open(successHostsFile, 'a')
					tFile.close()
					os.remove( tFile.name )
				except:
					return {'code':-1011, 'msg':'successHostsFile [%s] can not be created' % successHostsFile}
	# output
	if output and output.strip():
		output = output.strip()
		if os.path.exists( output ):
			if not os.path.isfile( output ):
				return {'code':-1012, 'msg':'output [%s] existed before, but it is not a file' % output}
			if not os.access(output, os.W_OK):
				return {'code':-1013, 'msg':'output [%s] can not be writed' % output}
		else:
			try:
				tFile = open(output, 'a')
				tFile.close()
				os.remove( tFile.name )
			except:
				return {'code':-1014, 'msg':'output [%s] can not be created' % output}

	return {'code':0, 'msg':'pass check'}



def argsDefine():
	argsParser = argparse.ArgumentParser(prog="ddp", description = "ddp is a python ssh script")
	argsParser.add_argument('-v', '--version', action='version', version='%(prog)s, author:vincentzhwg@gmail.com, version: 1.1.1')
	argsParser.add_argument('-l', '--hostsFile', help="the path of hostsFile, this parameter can not used with hostsString at the same time")
	argsParser.add_argument('-s', '--hostsString', help="hosts string, this parameter can not used with hostsFile at the same time")
	argsParser.add_argument('-c', '--cmdsFile', help="the path of cmdsFile, this parameter can not used with execCmds at the same time")
	argsParser.add_argument('-e', '--execCmds', help="commands to execute, this parameter can not used with cmdsFile at the same time")
	argsParser.add_argument('-eh', '--errorHostsFile', help="the path of error hosts file")
	argsParser.add_argument('-sh', '--successHostsFile', help="the path of success hosts file")
	argsParser.add_argument('-r', '--retryTimes', type=int, help="retry times after error")
	argsParser.add_argument('-w', '--workersNO', type=int, help="number of concurrent running hosts. less than or equal 1 means serial execution; greater than 1 means concurrent execution")
	argsParser.add_argument('-q', '--quiet', action='store_true', help="quiet mode, no std output")
	argsParser.add_argument('-qq', '--quietFiles', action='store_true', help="not generate successHostsFile and errorHostsFile")
	argsParser.add_argument('-j', '--jsonFormat', action='store_true', help="return result as json string")
	argsParser.add_argument('-pr', '--printResult', action='store_true', help="print result")
	argsParser.add_argument('-o', '--output', help="output executing logs to file")
	return argsParser



def ddpRun(hostList, firstCmdNode, retryTimes=None, workersNO=None, cmdVars=dict(), quietMode=False, outputFileQuietMode=True):
	# deal parameters
	if None is retryTimes: retryTimes = DDP_RETRY_TIMES
	if None is workersNO: workersNO = DDP_RUNNING_HOST

	sshHostProcesses = list()
	for tHost in hostList:
		sshHostProcesses.append( SSHHost(host=tHost, firstCmdNode=firstCmdNode, retryTimes=retryTimes, cmdVars=cmdVars, quietMode=quietMode, outputFileQuietMode=outputFileQuietMode) )
	
	# running 
	if workersNO > 1:
		for p in sshHostProcesses:
			p.start()
		for p in sshHostProcesses:
			p.join()
	else:
		for tP in sshHostProcesses:
			tP.start()
			tP.join()
	




def ddp(hostList, firstCmdNode, output=None, retryTimes=None, workersNO=None, quiet=False, jsonFormat=False, quietFiles=False, printResult=False, successHostsFile=None, errorHostsFile=None):
	# set global var by args
	setGlobalVar(retryTimes=retryTimes, workersNO=workersNO, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile)
	logger.info("conf parameter final values:")
	logger.info("DDP_EXIT_USELESS_VALUE:%d", DDP_EXIT_USELESS_VALUE)
	logger.info("DDP_RUNNING_HOST:%d", DDP_RUNNING_HOST)
	logger.info("DDP_RETRY_TIMES:%d", DDP_RETRY_TIMES)
	logger.info("DDP_SUCCESS_HOSTS_FILE:%s", DDP_SUCCESS_HOSTS_FILE)
	logger.info("DDP_ERROR_HOSTS_FILE:%s", DDP_ERROR_HOSTS_FILE)
	logger.info("DDP_USED_AS_SCRIPT:%r", DDP_USED_AS_SCRIPT)

	# deal parameters
	if None is retryTimes: retryTimes = DDP_RETRY_TIMES
	if None is workersNO: workersNO = DDP_RUNNING_HOST
	if None is successHostsFile: successHostsFile = DDP_SUCCESS_HOSTS_FILE
	if None is errorHostsFile: errorHostsFile = DDP_ERROR_HOSTS_FILE
	
	# check args
	checkRet = checkArgs(output=output, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile, quietFiles=quietFiles)
	if 0 != checkRet['code']:
		logger.error('can not pass args check, checkRet:%r', checkRet)
		retDict = {'code':checkRet['code'], 'msg':checkRet['msg'], 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if printResult:
			print retDict
		return retDict


	# start print worker if not in quiet mode
	if not quiet:
		printWorker = PrintProcess()
		logger.info("start print worker")
		printWorker.start()
	# start oplog write worker if -o
	if output:
		opLogWorker = OPLogProcess( output )
		opLogWorker.start()
		
	# start result worker 
	resultWorker = ResultProcess(quietFiles=quietFiles, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile)
	logger.info("start result worker")
	resultWorker.start()

	# execute ssh command
	if output: outputFileQuietMode = False
	else: outputFileQuietMode = True
	ddpRun(hostList, firstCmdNode, retryTimes=retryTimes, workersNO=workersNO, quietMode=quiet, outputFileQuietMode=outputFileQuietMode)
	
	# stop result worker
	resultWorker.turnOff()
	resultWorker.join()

	# stop print worker
	if not quiet:
		logger.info("turn off print worker")
		printWorker.turnOff()
		printWorker.join()
	# stop oplog write worker
	if output:
		logger.info("turn off oplog worker")
		opLogWorker.turnOff()
		opLogWorker.join()
	
	
	retDict = DDP_RESULT_PIPE_RECEIVER.recv()
	if jsonFormat:
		retDict = json.dumps( retDict )
	if printResult:
		print retDict
	return retDict




def main(hostsFile=None, cmdsFile=None, hostsString=None, execCmds=None, output=None, retryTimes=None, workersNO=None, quiet=False, jsonFormat=False, quietFiles=False, printResult=False, successHostsFile=None, errorHostsFile=None):

	# set global var by args
	setGlobalVar(retryTimes=retryTimes, workersNO=workersNO, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile)
	logger.info("conf parameter final values:")
	logger.info("DDP_EXIT_USELESS_VALUE:%d", DDP_EXIT_USELESS_VALUE)
	logger.info("DDP_RUNNING_HOST:%d", DDP_RUNNING_HOST)
	logger.info("DDP_RETRY_TIMES:%d", DDP_RETRY_TIMES)
	logger.info("DDP_SUCCESS_HOSTS_FILE:%s", DDP_SUCCESS_HOSTS_FILE)
	logger.info("DDP_ERROR_HOSTS_FILE:%s", DDP_ERROR_HOSTS_FILE)
	logger.info("DDP_USED_AS_SCRIPT:%r", DDP_USED_AS_SCRIPT)

	# deal parameters
	if None is retryTimes: retryTimes = DDP_RETRY_TIMES
	if None is workersNO: workersNO = DDP_RUNNING_HOST
	if None is successHostsFile: successHostsFile = DDP_SUCCESS_HOSTS_FILE
	if None is errorHostsFile: errorHostsFile = DDP_ERROR_HOSTS_FILE
	
	# check args
	checkRet = checkArgs(hostsFile=hostsFile, cmdsFile=cmdsFile, output=output, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile, quietFiles=quietFiles)
	if 0 != checkRet['code']:
		logger.error('can not pass args check, checkRet:%r', checkRet)
		retDict = {'code':checkRet['code'], 'msg':checkRet['msg'], 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if DDP_USED_AS_SCRIPT:
			sys.exit( retDict )
		else:
			if printResult:
				print retDict
			return retDict
	

	# start print worker if not in quiet mode
	if not quiet:
		printWorker = PrintProcess()
		printWorker.start()
		logger.info("start print worker")
	# start oplog write worker if -o
	if output:
		opLogWorker = OPLogProcess( output )
		opLogWorker.start()
		logger.info("start opLog worker")

	# hosts and cmds source
	if None is hostsFile and not None is hostsString:
		hostsData = hostsString	
	elif not None is hostsFile and None is hostsString:
		tFile = open(hostsFile, 'r')
		hostsData = tFile.read()
		tFile.close()
	else:
		logger.error('should use either hostsFile or hostsString, but can not use them together at the same time')
		retDict = {'code':-1017, 'msg':'should use either hostsFile or hostsString, but can not use them together at the same time', 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if DDP_USED_AS_SCRIPT:
			sys.exit( retDict )
		else:
			if printResult:
				print retDict
			return retDict
	if None is cmdsFile and not None is execCmds:
		cmdsData = execCmds
	elif not None is cmdsFile and None is execCmds:
		tFile = open(cmdsFile, 'r')
		cmdsData = tFile.read()
		tFile.close()
	else:
		logger.error('should use either cmdsFile or execCmds, but can not use them together at the same time')
		retDict = {'code':-1018, 'msg':'should use either cmdsFile or execCmds, but can not use them together at the same time', 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if DDP_USED_AS_SCRIPT:
			sys.exit( retDict )
		else:
			if printResult:
				print retDict
			return retDict


	# get hostList
	getRet = getHostList(hostsData)
	if 0 != getRet['code']:
		logger.error( 'error when parsing hosts file:%s, reason:%r', hostsFile, getRet )
		retDict = {'code':getRet['code'], 'msg':getRet['msg'], 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if DDP_USED_AS_SCRIPT:
			sys.exit( retDict )
		else:
			if printResult:
				print retDict
			return retDict
	else:
		hostList = getRet['hostList']
		tList = list()
		for item in hostList:
			tList.append("hostName:%16s; user:%10s, port:%5r; TAG:%r" % (item['hostName'], item['user'], item['port'], item['TAG']))
		logger.info("get hosts list from hosts file [%s] success, hosts infoes except password are following:\n%s", hostsFile, '\n'.join(tList))

	# get firstCmdNode
	getRet = getFirstCmdNode(cmdsData)
	if 0 != getRet['code']:
		logger.error( 'error when parsing cmds file:%s, reason:%r', cmdsFile, getRet )
		retDict = {'code':getRet['code'], 'msg':getRet['msg'], 'hosts':dict()}
		if jsonFormat:
			retDict = json.dumps( retDict )
		if DDP_USED_AS_SCRIPT:
			sys.exit( retDict )
		else:
			if printResult:
				print retDict
			return retDict
	else:
		firstCmdNode = getRet['cmdNode']
		logger.info("get cmds from cmds file [%s] success, cmds are following:%s", cmdsFile, firstCmdNode.depthTraversal())

	# start result worker
	resultWorker = ResultProcess(cmdsData=cmdsData, quietFiles=quietFiles, successHostsFile=successHostsFile, errorHostsFile=errorHostsFile)
	resultWorker.start()

	# execute ssh command
	if output: outputFileQuietMode = False
	else: outputFileQuietMode = True
	ddpRun(hostList, firstCmdNode, retryTimes=retryTimes, workersNO=workersNO, quietMode=quiet, outputFileQuietMode=outputFileQuietMode)
	
	# stop result worker
	resultWorker.turnOff()
	resultWorker.join()

	# stop print worker
	if not quiet:
		logger.info("turn off print worker")
		printWorker.turnOff()
		printWorker.join()
	# stop oplog worker
	if output:
		logger.info("turn off oplog worker")
		opLogWorker.turnOff()
		opLogWorker.join()
	
	

	retDict = DDP_RESULT_PIPE_RECEIVER.recv()
	totalCode = retDict['code']
	if jsonFormat:
		retDict = json.dumps( retDict )
	if printResult:
		print retDict
	if DDP_USED_AS_SCRIPT:
		if 0 == totalCode:
			sys.exit( 0 )
		else:
			sys.exit( 1 )
	else:
		return retDict

	


##########################################################################################################################
if __name__ == '__main__':
	#标明是用脚本方式使用
	DDP_USED_AS_SCRIPT = True

	#备份原有的warnings过滤器
	warningsFilter = warnings.filters[:]
	# 新增一条忽略DeprecationWarning的过滤规则
	warnings.simplefilter('ignore', DeprecationWarning)

	# parse argv
	logger.info('sys.argv:%r', sys.argv)
	args = sys.argv
	if len(args) == 1:
		args.append('-h')
	#with warnings.catch_warnings():
	#	warnings.filterwarnings("ignore",category=DeprecationWarning)
	argsParser = argsDefine()
	#args = argsParser.parse_args( args[1:] )
	#logger.info('args:%r' % args)
	try:
		args = argsParser.parse_args( args[1:] )
		logger.info('args:%r' % args)
	except:
		#logger.exception("occurs exception when parsing args, exit 1")
		retDict = {'code':-1001, 'msg':'parameters can not be recognized', 'hosts':dict()}
		sys.exit( json.dumps(retDict) )
		
	#print "args:%r" % args
	#sys.exit(1)
	
	main(hostsFile=args.hostsFile, cmdsFile=args.cmdsFile, hostsString=args.hostsString, execCmds=args.execCmds, output=args.output, quiet=args.quiet, quietFiles=args.quietFiles, retryTimes=args.retryTimes, workersNO=args.workersNO, jsonFormat=args.jsonFormat, printResult=args.printResult, successHostsFile=args.successHostsFile, errorHostsFile=args.errorHostsFile)
