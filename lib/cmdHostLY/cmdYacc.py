#!/usr/bin/env python
#-*- coding:utf8 -*-

import sys, os
import re

libPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
sys.path.append( libPath )
from ply import *

from cmdLex import tokens
from cmdLex import cmdLexer



def concatStatement(first, second):
	if first.isExit():
		raise Exception("the command in lineno:%d would never be executed" % second.lineno)
	first.addChildAtLast( second )
	return first

start = 'script'

def p_script(p):
	'''script : statement end
			  | eol statement end'''
	if 3 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = p[2]

def p_statement_cmd(p):
	'''statement : statement eol cmd
				 | cmd'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = concatStatement(p[1], p[3])

def p_statement_exit(p):
	'''statement : statement eol exit_block
				 | exit_block'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = concatStatement(p[1], p[3])
	
def p_exit_block(p):
	'''exit_block : EXIT INTEGER
				  | EXIT INTEGER COMMA STRING'''
	if 3 == len(p):
		p[0] = CmdNode(category='exit', lineno=p.lineno(1), value=p[2], msg='')
	elif 5 == len(p):
		p[0] = CmdNode(category='exit', lineno=p.lineno(1), value=p[2], msg=p[4])

def p_statement_while(p):
	'''statement : statement eol while_block
				 | while_block'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = concatStatement(p[1], p[3])

def p_while_block(p):
	'''while_block : WHILE SEP cmd eol statement eol ENDWHILE'''
	tCondition = p[3]
	if 'NM' in tCondition.adjs.keys():
		raise Exception("WHILE and NM can not be used at the same time")
	p[0] = CmdNode(category='while', condition=tCondition, Y=p[5], N=None, lineno=p.lineno(1))
	tLastChild = p[5].getLastChild()
	tLastChild.addChildAtLast( p[0] )


def p_statement_do_while(p):
	'''statement : statement eol do_while_block
				 | do_while_block'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = concatStatement(p[1], p[3])

def p_do_while_block(p):
	'''do_while_block : DO eol statement eol DOWHILE SEP cmd'''
	tCondition = p[7]
	if 'NM' in tCondition.adjs.keys():
		raise Exception("DOWHILE and NM can not be used at the same time")
	doWhileNode = CmdNode(category='do_while', condition=p[7], Y=p[3], N=None, lineno=p.lineno(5))
	p[3].addChildAtLast( doWhileNode )
	p[0] = p[3]
	
def p_statement_if(p):
	'''statement : statement eol if_block
				 | if_block'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		p[0] = concatStatement(p[1], p[3])

def p_if_block(p):
	'''if_block : IF SEP cmd eol statement eol else_block'''
	tCondition = p[3]
	if 'NM' in tCondition.adjs.keys():
		raise Exception("IF and NM can not be used at the same time")
	p[0] = CmdNode(category='if', condition=p[3], Y=p[5], N=p[7], junction=None, lineno=p.lineno(1))

def p_else_block(p):
	'''else_block : ELSE eol statement eol ENDIF
				  | ENDIF'''
	if 2 == len(p):
		p[0] = None
	elif 6 == len(p):
		p[0] = p[3]


def p_cmd(p):
	'''cmd : adjs SEP COMMAND
		   | COMMAND'''
	if 2 == len(p):
		p[0] = CmdNode(category='cmd', command=p[1], lineno=p.lineno(1), child=None, adjs=dict())
		#if p[1].startswith('scp'):
		#	raise Exception("scp command should have SCP_PWD in lineno:%d" % p.lineno(1))
	elif 4 == len(p):
		if re.match(r'^scp[ \t]+.*', p[3]):
		#if p[3].startswith('scp'):
			#if not 'SCP_PWD' in p[1]:
			#	raise Exception("scp command should have SCP_PWD in lineno:%d" % p.lineno(2))
			if 'TL' in p[1]:
				raise Exception('TL can not be used in scp command in lineno:%d' % p.lineno(2))
			if 'NTOL' in p[1]:
				raise Exception('NTOL can not be used in scp command in lineno:%d' % p.lineno(2))
		p[0] = CmdNode(category='cmd', command=p[3], lineno=p.lineno(2), child=None, adjs=p[1])



def p_cmd_scp_local_push_pull(p):
	'''cmd : adjs SEP SCP_LOCAL_PUSH_PULL SEP scp_adjs
		   | SCP_LOCAL_PUSH_PULL SEP scp_adjs'''
	if 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_scp_local_push_pull', lineno=p.lineno(2), child=None, adjs=p[3])
	elif 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_scp_local_push_pull', lineno=p.lineno(2), child=None, adjs=dict(p[1], **(p[5])))
	tNotNeedKeys = ['LOCAL_USER', 'SCP_PWD', 'TL', 'NTOL']
	for k in tNotNeedKeys:
		if k in p[0].adjs:
			raise Exception('%s should not be used in SCP_LOCAL_PUSH_PULL in lineno:%d' % (k, p.lineno(2)))
	tNeedKeys = ['LOCAL_PATH', 'SSH_HOST_PATH']	
	for k in tNeedKeys:
		if not k in p[0].adjs:
			raise Exception('%s must be used in SCP_LOCAL_PUSH_PULL in lineno:%d' % (k, p.lineno(2)))
	if not 'LOCAL_ISDIR' in p[0].adjs:
		p[0].adjs['LOCAL_ISDIR'] = False
	if not 'LOCAL_PORT' in p[0].adjs:
		p[0].adjs['LOCAL_PORT'] = None
	if not 'LOCAL_PWD' in p[0].adjs:
		p[0].adjs['LOCAL_PWD'] = None




def p_cmd_scp_local_pull_push(p):
	'''cmd : adjs SEP SCP_LOCAL_PULL_PUSH SEP scp_adjs
		   | SCP_LOCAL_PULL_PUSH SEP scp_adjs'''
	if 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_scp_local_pull_push', lineno=p.lineno(2), child=None, adjs=p[3])
	elif 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_scp_local_pull_push', lineno=p.lineno(2), child=None, adjs=dict(p[1], **(p[5])))
	tNotNeedKeys = ['LOCAL_USER', 'SCP_PWD', 'TL', 'NTOL']
	for k in tNotNeedKeys:
		if k in p[0].adjs:
			raise Exception('%s should not be used in SCP_LOCAL_PULL_PUSH in lineno:%d' % (k, p.lineno(2)))
	tNeedKeys = ['LOCAL_PATH', 'SSH_HOST_PATH']	
	for k in tNeedKeys:
		if not k in p[0].adjs:
			raise Exception('%s must be used in SCP_LOCAL_PULL_PUSH in lineno:%d' % (k, p.lineno(2)))
	if not 'LOCAL_ISDIR' in p[0].adjs:
		p[0].adjs['LOCAL_ISDIR'] = False
	if not 'LOCAL_PORT' in p[0].adjs:
		p[0].adjs['LOCAL_PORT'] = None
	if not 'LOCAL_PWD' in p[0].adjs:
		p[0].adjs['LOCAL_PWD'] = None


def p_scp_adjs(p):
	'''scp_adjs : scp_adjunct
				| scp_adjs SEP scp_adjunct'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		for k in p[3].keys():
			if 0 != cmp('lineno', k) and k in p[1]:
				raise Exception('%s used duplicately in lineno:%d' % (k, p.lineno(2)))
		p[0] = dict(p[1], **(p[3]))

def p_scp_adjunct(p):
	'''scp_adjunct : LOCAL_INTF SEP STRING
				  | LOCAL_PORT SEP INTEGER
				  | LOCAL_USER SEP STRING
				  | LOCAL_PWD SEP STRING
				  | LOCAL_PATH SEP STRING
				  | SSH_HOST_PATH SEP STRING
				  | LOCAL_ISDIR'''
	if 2 == len(p) and 'LOCAL_ISDIR' == p[1]:
		p[0] = {'LOCAL_ISDIR' : True }
	if 4 == len(p) and 'LOCAL_INTF' == p[1]:
		p[0] = { 'LOCAL_INTF' : p[3].strip() }
	elif 4 == len(p) and 'LOCAL_PORT' == p[1]:
		p[0] = { 'LOCAL_PORT' : p[3] }
	elif 4 == len(p) and 'LOCAL_USER' == p[1]:
		p[0] = { 'LOCAL_USER' : p[3].strip() }
	elif 4 == len(p) and 'LOCAL_PWD' == p[1]:
		p[0] = { 'LOCAL_PWD' : p[3] }
	elif 4 == len(p) and 'LOCAL_PATH' == p[1]:
		p[0] = { 'LOCAL_PATH' : p[3].strip() }
	elif 4 == len(p) and 'SSH_HOST_PATH' == p[1]:
		p[0] = { 'SSH_HOST_PATH' : p[3].strip() }
	if 'LOCAL_INTF' in p[0] and not p[0]['LOCAL_INTF']:
		raise Exception('LOCAL_INTF can not be empty in lineno:%d' % p.lineno(2))
	if 'LOCAL_PORT' in p[0] and (0 > p[0]['LOCAL_PORT'] or 65535 < p[0]['LOCAL_PORT']):
		raise Exception('LOCAL_PORT not proper in lineno:%d' % p.lineno(2))
	if 'LOCAL_USER' in p[0] and not p[0]['LOCAL_USER']:
		raise Exception('LOCAL_USER can not be empty in lineno:%d' % p.lineno(2))
	if 'LOCAL_PATH' in p[0] and not p[0]['LOCAL_PATH']:
		raise Exception('LOCAL_PATH can not be empty in lineno:%d' % p.lineno(2))
	if 'SSH_HOST_PATH' in p[0] and not p[0]['SSH_HOST_PATH']:
		raise Exception('SSH_HOST_PATH can not be empty in lineno:%d' % p.lineno(2))

def p_cmd_add_user(p):
	'''cmd : ADD_USER SEP add_user_adjs
		   | adjs SEP ADD_USER SEP add_user_adjs'''
	if 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_add_user', lineno=p.lineno(2), child=None, adjs=p[3])
	elif 4 == len(p):
		p[0] = CmdNode(category='cmd', command='pyssh_add_user', lineno=p.lineno(2), child=None, adjs=dict(p[1], **(p[5])))
	tNotNeedKeys = ['LOCAL_USER', 'SCP_PWD', 'TL', 'NTOL']
	for k in tNotNeedKeys:
		if k in p[0].adjs:
			raise Exception('%s should not be used in ADD_USER in lineno:%d' % (k, p.lineno(2)))
	tNeedKeys = ['USER_NAME',]	
	for k in tNeedKeys:
		if not k in p[0].adjs:
			raise Exception('%s must be used in ADD_USER in lineno:%d' % (k, p.lineno(2)))
	if not 'USER_PWD' in p[0].adjs:
		p[0].adjs['USER_PWD'] = None
	if not 'USER_HOME' in p[0].adjs:
		p[0].adjs['USER_HOME'] = None
	if not 'GROUP_NAME' in p[0].adjs:
		p[0].adjs['GROUP_NAME'] = None
	
	
def p_add_user_adjs(p):
	'''add_user_adjs : add_user_adjunct
					 | add_user_adjs SEP add_user_adjunct'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		for k in p[3].keys():
			if 0 != cmp('lineno', k) and k in p[1]:
				raise Exception('%s used duplicately in lineno:%d' % (k, p.lineno(2)))
		p[0] = dict(p[1], **(p[3]))



def p_add_user_adjunct(p):
	'''add_user_adjunct : USER_NAME SEP STRING
						| USER_PWD SEP STRING
						| USER_HOME SEP STRING
						| GROUP_NAME SEP STRING'''
	if 4 == len(p) and 0 == cmp('USER_NAME', p[1]):
		p[0] = {'USER_NAME' : p[3].strip()}
	elif 4 == len(p) and 0 == cmp('USER_PWD', p[1]):
		p[0] = {'USER_PWD' : p[3]}
	elif 4 == len(p) and 0 == cmp('USER_HOME', p[1]):
		p[0] = {'USER_HOME' : p[3].strip()}
	elif 4 == len(p) and 0 == cmp('GROUP_NAME', p[1]):
		p[0] = {'GROUP_NAME' : p[3].strip()}
	noEmptyList = ['USER_NAME', 'USER_HOME', 'GROUP_NAME']
	for item in noEmptyList:
		if item in p[0] and not p[0][item]:
			raise Exception('%s can not be empty in lineno:%d' % (item, p.lineno(2)))
	
def p_adjs(p):
	'''adjs : adjunct
			| adjs SEP adjunct'''
	if 2 == len(p):
		p[0] = p[1]
	elif 4 == len(p):
		for k in p[3].keys():
			if k in p[1].keys():
				raise Exception("%s is duplicated in lineno:%d" % (k, p.lineno(2)))
		p[0] = dict(p[1], **(p[3]))
		if 'NM' in p[0].keys() and 'ASSERT' in p[0].keys():
			raise Exception("NM and ASSERT can not be used at the same time")
		if 'TL' in p[0].keys() and 'NTOL' in p[0].keys():
			raise Exception("TL and NTOL can not be used at the same time")
	#print "adjs:%r" % p[0]

def p_adjunct(p):
	'''adjunct : NTOL
			   | NM
			   | TAG SEP id_list
			   | VAR SEP IDENTITY
			   | SCP_PWD SEP STRING
			   | ASSERT SEP STRING
			   | ASSERT SEP INTEGER
			   | TL SEP INTEGER'''
	if 2 == len(p) and 'NTOL' == p[1]:
		p[0] = { 'NTOL' : True }
	elif 2 == len(p) and 'NM' == p[1]:
		p[0] = { 'NM' : True }
	elif 4 == len(p) and 'TAG' == p[1]:
		p[0] = { 'TAG' : p[3] }
	elif 4 == len(p) and 'VAR' == p[1]:
		p[0] = { 'VAR' : p[3] }
	elif 4 == len(p) and 'SCP_PWD' == p[1]:
		p[0] = { 'SCP_PWD' : p[3] }
	elif 4 == len(p) and 'ASSERT' == p[1] and isinstance(p[3], str):
		p[0] = { 'ASSERT' : p[3] }
	elif 4 == len(p) and 'ASSERT' == p[1] and isinstance(p[3], int):
		p[0] = { 'ASSERT' : str(p[3]) }
	elif 4 == len(p) and 'TL' == p[1]:
		p[0] = { 'TL' : p[3] }
	

def p_id_list(p):
	'''id_list : IDENTITY
			| id_list COMMA IDENTITY'''
	if 2 == len(p):
		p[0] = [ p[1] ]
	elif 4 == len(p):
		p[1].append(p[3])
		p[0] = p[1]


def p_end(p):
	'''end : eol
		  | empty'''
	pass

def p_eol(p):
	'''eol : EOL
		   | SEMICOLON
		   | eol SEMICOLON
		   | eol EOL'''
	pass

def p_empty(p):
	'''empty :'''
	pass


### error rule for syntax errors
def p_error(p):
	if p:
		raise Exception("parsing error on lineno:%d, token:[%r]. Syntax is not proper" % (p.lineno, p.value))
	else:
		raise Exception("parsing error at the end. Syntax is not proper")
		#print("Syntax error at EOF")
	#then tell the parser it's okay.
	#yacc.errok()




###### AST Tree #######
class CmdNode(object):
	nodeId = 0
	def __init__(self, category, **kwargs):
		# set nodeId
		self.nodeId = self.__class__.nodeId
		self.__class__.nodeId += 1

		self.category = category	# if or cmd
		for (key, value) in kwargs.items():
			self.__dict__[ key ] = value

	def getLastChild(self):
		'''get last child, if don't have child, return itself'''
		cur = self
		while cur:
			if 0 == cmp('exit', cur.category):
				return cur
			elif 0 == cmp('cmd', cur.category):
				if not None is cur.child:
					cur = cur.child
				else:
					return cur
			elif 0 == cmp('if', cur.category):
				if not None is cur.junction:
					cur = cur.junction
				else:
					return cur
			elif 0 == cmp('do_while', cur.category):
				if None is cur.N:
					return cur
				else:
					cur = cur.N
			elif 0 == cmp('while', cur.category):
				if None is cur.N:
					return cur
				else:
					cur = cur.N

	def isExit(self):
		if 0 == cmp('exit', self.category):
			return True
		elif 0 == cmp('cmd', self.category):
			if None is self.child:
				return False
			else:
				return self.child.isExit()
		elif 0 == cmp('if', self.category):
			if None is self.junction:
				if None is self.N:
					return False
				else:
					return self.N.isExit() and self.Y.isExit()
			else:
				return self.junction.isExit()
		elif 0 == cmp('do_while', self.category):
			if None is self.N:
				return False
			else:
				return self.N.isExit()
		elif 0 == cmp('while', self.category):
			if None is self.N:
				return False
			else:
				return self.N.isExit()


	def addChildAtLast(self, child):
		if 0 == cmp('exit', self.category):
			pass
		elif 0 == cmp('cmd', self.category):
			if None is self.child:
				self.child = child
			else:
				self.child.addChildAtLast( child )
		elif 0 == cmp('if', self.category):
			if None is self.junction:
				NChild = self.N
				if None is NChild:
					self.N = child
				else:
					NChild.addChildAtLast( child )
				YChild = self.Y
				YChild.addChildAtLast( child )
				self.junction = child
			else:
				self.junction.addChildAtLast( child )
		elif 0 == cmp('do_while', self.category):
			if None is self.N:
				self.N = child
			else:
				self.N.addChildAtLast( child )
		elif 0 == cmp('while', self.category):
			if None is self.N:
				self.N = child
			else:
				self.N.addChildAtLast( child )


	def __str__(self):
		retStr = "nodeId:%2d; category:%8s; lineno:%2d" % (self.nodeId, self.category, self.lineno)
		if 0 == cmp('cmd', self.category) or 0 == cmp('exit', self.category):
			for (k, v) in self.__dict__.items():
				if 0 == cmp('category', k) or 0 == cmp('lineno', k) or 0 == cmp('nodeId', k):
					continue
				elif 0 == cmp('child', k):
					if None is v:
						retStr = "%s; child:%s" % (retStr, 'None')
					else:
						retStr = "%s; child.nodeId:%2d" % (retStr, v.nodeId)
				elif 0 == cmp('adjs', k):
					tAdjStr = ''
					for (s, t) in v.items():
						if s in ['SCP_PWD', 'LOCAL_PWD']:
							continue
						else:
							tAdjStr = "%s , %r:%r" % (tAdjStr, s, t)
					retStr = "%s; adjs:{%s}" % (retStr, tAdjStr[3:])
				else:
					retStr = "%s; %r:%r" % (retStr, k, v)
		elif 0 == cmp('if', self.category) or 0 == cmp('while', self.category) or 0 == cmp('do_while', self.category):
			retStr = "%s; Y.nodeId:%2d" % (retStr, self.Y.nodeId)
			if None is self.N:
				retStr = "%s; N:%s" % (retStr, 'None')
			else:
				retStr = "%s; N.nodeId:%2d" % (retStr, self.N.nodeId)
			for (k, v) in self.__dict__.items():
				if 0 == cmp('category', k) or 0 == cmp('lineno', k) or 0 == cmp('nodeId', k):
					continue
				elif 0 == cmp('Y', k) or 0 == cmp('N', k):
					continue
				elif 0 ==cmp('junction', k):
					if None is v:
						retStr = "%s; junction:%s" % (retStr, 'None')
					else:
						retStr = "%s; junction.nodeId:%2d" % (retStr, v.nodeId)
				elif 0 == cmp('condition', k):
					retStr = "%s; condition:(%s)" % (retStr, v)
				elif 0 == cmp('adjs', k):
					tAdjStr = ''
					for (s, t) in v.items():
						if s in ['SCP_PWD', 'LOCAL_PWD']:
							continue
						else:
							tAdjStr = "%s , %r:%r" % (tAdjStr, s, t)
					retStr = "%s; adjs:{%s}" % (retStr, tAdjStr[3:])
				else:
					retStr = "%s; %r:%r" % (retStr, k, v)
		return retStr


	def breadthTraversal(self):
		visited = list()
		tQueue = list()
		tQueue.append(self)
		visited.append( self.nodeId )
		retStr = ""
		while tQueue:
			tNode = tQueue.pop( 0 )
			retStr = "%s\n%s" % (retStr, tNode)
			#print tNode
			if 0 == cmp('exit', tNode.category):
				pass
			elif 0 == cmp('cmd', tNode.category):
				if not None is tNode.child and not tNode.child.nodeId in visited:
					tQueue.append( tNode.child )
					visited.append( tNode.child.nodeId )
			else:
				if not tNode.Y.nodeId in visited:
					tQueue.append( tNode.Y )
					visited.append( tNode.Y.nodeId )
				if not None is tNode.N and not tNode.N.nodeId in visited:
					tQueue.append( tNode.N )
					visited.append( tNode.N.nodeId )
		return retStr

	def depthTraversal(self):
		visited = list()
		tStack = list()
		tStack.append(self)
		visited.append( self.nodeId )
		retStr = ""
		while tStack:
			tNode = tStack.pop()
			retStr = "%s\n%s" % (retStr, tNode)
			#print tNode
			if 0 == cmp('exit', tNode.category):
				pass
			elif 0 == cmp('cmd', tNode.category):
				if not None is tNode.child and not tNode.child.nodeId in visited:
					tStack.append( tNode.child )
					visited.append( tNode.child.nodeId )
			else:
				if not None is tNode.N and not tNode.N.nodeId in visited:
					tStack.append( tNode.N )
					visited.append( tNode.N.nodeId )
				if not tNode.Y.nodeId in visited:
					tStack.append( tNode.Y )
					visited.append( tNode.Y.nodeId )
		return retStr


cmdParser = yacc.yacc(debug=0, tabmodule="cmd", optimize=1, outputdir= os.path.dirname(os.path.realpath(__file__)), errorlog=yacc.NullLogger() )
#cmdParser = yacc.yacc(debug=1, tabmodule="cmd", optimize=0, outputdir= os.path.dirname(os.path.realpath(__file__)))

def parseCmdsFromData(data):
	try:
		cmdNode = cmdParser.parse(data,  lexer=cmdLexer, debug=0)
		return {'code':0 , 'cmdNode': cmdNode}
	except Exception, e:
		#print e
		if str(e).startswith("Illegalal token"):
			return {'code':-3001, 'msg':str(e)} 
		else:
			return {'code':-3002, 'msg':str(e)} 
		#elif str(e).startswith("parsing error"):
		#	return {'code':-3002, 'msg':str(e)} 
		#else:
		#	return {'code':-3003, 'msg':'unknown error:%s' % str(e)}
	


if __name__ == '__main__':
	if len(sys.argv) == 2:
		data = open(sys.argv[1]).read()
		print "data:%r" % data
		parseRet = parseCmdsFromData( data )
		if 0 == parseRet['code']:
			print parseRet['cmdNode'].depthTraversal()
		elif -1 == parseRet['code']:
			print "msg:", parseRet['msg']
	else:
		while True:
			try:
			   s = raw_input('pyssh > ')
			except EOFError:
				break
			if not s: continue
			parseRet = parseCmdsFromData( data )
			if 0 == parseRet['code']:
				print parseRet['cmdNode'].depthTraversal()
			elif -1 == parseRet['code']:
				print parseRet['msg']
