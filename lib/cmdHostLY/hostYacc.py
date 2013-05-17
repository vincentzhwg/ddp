#!/usr/bin/env python
#-*- coding:utf8 -*-


import sys, os
import pprint


libPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
sys.path.append( libPath )
from ply import *

from hostLex import tokens
from hostLex import hostLexer



def concatStatement(first, second):
	if first.isTerminal():
		raise Exception("the command in lineno:%d would never be executed" % second.lineno)
	first.addChildAtLast( second )
	return first

start = 'host_file'

def p_host_file(p):
	'''host_file : end host_list end'''
	p[0] = p[2]

def p_host_list(p):
	'''host_list : host_list eol host
				 | host'''
	if 2 == len(p):
		p[0] = [ p[1] ]
	elif 4 == len(p):
		tDict = dict()
		for item in p[1]:
			tDict[ item['hostName'] ] = item['lineno']
		for (tHostName, tLineno) in tDict.items():
			if 0 == cmp(tHostName, p[3]['hostName']):
				raise Exception("host name[%s] in lineno:%d is duplicated with in lineno:%d" % (tHostName, p[3]['lineno'], tLineno))
		p[1].append( p[3] )
		p[0] = p[1]


def p_host(p):
	'''host : id_list SEP host_name delimiter STRING delimiter STRING delimiter INTEGER
			| id_list SEP host_name delimiter STRING delimiter STRING
			| id_list SEP host_name delimiter STRING
			| host_name delimiter STRING delimiter STRING delimiter INTEGER
			| host_name delimiter STRING delimiter STRING
			| host_name delimiter STRING'''
	if 4 == len(p):
		p[0] = {'lineno':p.lineno(3), 'TAG':list(), 'hostName':p[1], 'user':p[3], 'password':None, 'port':None}
	elif 6 == len(p) and 0 == cmp('::', p[2]):
		p[0] = {'lineno':p.lineno(2), 'TAG':p[1], 'hostName':p[3], 'user':p[5], 'password':None, 'port':None}
	elif 6 == len(p) and 0 != cmp('::', p[2]):
		if 0 == cmp('', p[5]): p[5] = None
		p[0] = {'lineno':p.lineno(3), 'TAG':list(), 'hostName':p[1], 'user':p[3], 'password':p[5], 'port':None}
	elif 8 == len(p) and 0 != cmp('::', p[2]):
		if 0 == cmp('', p[5]): p[5] = None
		if p[7] < 0 or p[7] > 65535:
			raise Exception("host port in lineno:%d is not proper" % p.lineno(3))
		p[0] = {'lineno':p.lineno(3), 'TAG':list(), 'hostName':p[1], 'user':p[3], 'password':p[5], 'port':p[7]}
	elif 8 == len(p) and 0 == cmp('::', p[2]):
		if 0 == cmp('', p[7]): p[7] = None
		p[0] = {'lineno':p.lineno(2), 'TAG':p[1], 'hostName':p[3], 'user':p[5], 'password':p[7], 'port':None}
	elif 10 == len(p):
		if 0 == cmp('', p[7]): p[7] = None
		if p[9] < 0 or p[9] > 65535:
			raise Exception("host port in lineno:%d is not proper" % p.lineno(2))
		p[0] = {'lineno':p.lineno(2), 'TAG':p[1], 'hostName':p[3], 'user':p[5], 'password':p[7], 'port':p[9]}
		


def p_host_name(p):
	'''host_name : INTEGER DOT INTEGER DOT INTEGER DOT INTEGER
				 | STRING'''
	if 2 == len(p):
		p[0] = p[1].strip()
	elif 8 == len(p):
		if (p[1] < 0 or p[1] > 255) or (p[3] < 0 or p[3] > 255) or (p[5] < 0 or p[5] > 255) or (p[7] < 0 or p[7] > 255):
			raise Exception("host ip address in lineno:%d is not proper" % p.lineno(2))
		p[0] = "%d.%d.%d.%d" % (p[1], p[3], p[5], p[7])

def p_id_list(p):
	'''id_list : IDENTITY
			| id_list COMMA IDENTITY'''
	if 2 == len(p):
		p[0] = [ p[1] ]
	elif 4 == len(p):
		p[1].append(p[3])
		p[0] = p[1]


def p_delimiter(p):
	'''delimiter : COMMA
				 | empty'''
	pass

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
		raise Exception("parsing error at the end of file. Syntax is not proper")
		#print("Syntax error at EOF")
	#then tell the parser it's okay.
	#yacc.errok()




###### AST Tree #######


hostParser = yacc.yacc(debug=0, tabmodule="host", optimize=1, errorlog=yacc.NullLogger(), outputdir=os.path.dirname(os.path.realpath(__file__)))

def parseHostsFromData(data):
	try:
		hostList = hostParser.parse(data, lexer=hostLexer, debug=0)
		return {'code':0 , 'hostList': hostList}
	except Exception, e:
		if str(e).startswith("Illegalal token"):
			return {'code':-2001, 'msg':str(e)} 
		elif str(e).startswith("parsing error"):
			return {'code':-2002, 'msg':str(e)} 
		else:
			return {'code':-2003, 'msg':'unknown error:%s' % str(e)}

	

if __name__ == '__main__':
	if len(sys.argv) == 2:
		data = open(sys.argv[1]).read()
		print "data:%r" % data
		parseRet = parseHostsFromData( data )
		if 0 == parseRet['code']:
			pprint.pprint(parseRet['hostList'], width=4)
		elif -1 == parseRet['code']:
			print "msg:", parseRet['msg']
	else:
		while True:
			try:
			   s = raw_input('pyssh > ')
			except EOFError:
				break
			if not s: continue
			parseRet = parseHostsFromData( data )
			if 0 == parseRet['code']:
				pprint.pprint(parseRet['hostList'], width=4)
			elif -1 == parseRet['code']:
				print parseRet['msg']
