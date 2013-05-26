#!/usr/bin/env python
#-*- coding:utf8 -*-



import sys, os
import re

libPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
sys.path.append( libPath )
from ply import *



## reserved words
reserved = {
	'DO' : 'DO',
	'DOWHILE' : 'DOWHILE',
	'WHILE' : 'WHILE',
	'ENDWHILE' : 'ENDWHILE',
	'IF' : 'IF',
	'ELSE' : 'ELSE',
	'ENDIF' : 'ENDIF',
	'EXIT' : 'EXIT',
	'NTOL' : 'NTOL',
	'TAG' : 'TAG',
	'VAR' : 'VAR',
	'NM' : 'NM',
	'ASSERT' : 'ASSERT',
	'TL' : 'TL',
	'SCP_PWD' : 'SCP_PWD',
	'SCP_LOCAL_PULL_PUSH' : 'SCP_LOCAL_PULL_PUSH',
	'SCP_LOCAL_PUSH_PULL' : 'SCP_LOCAL_PUSH_PULL',
	'LOCAL_USER' : 'LOCAL_USER',
	'LOCAL_PWD' : 'LOCAL_PWD',
	'LOCAL_PATH' : 'LOCAL_PATH',
	'LOCAL_INTF' : 'LOCAL_INTF',
	'LOCAL_PORT' : 'LOCAL_PORT',
	'LOCAL_ISDIR' : 'LOCAL_ISDIR',
	'SSH_HOST_PATH' : 'SSH_HOST_PATH',
	'ADD_USER' : 'ADD_USER',
	'USER_HOME' : 'USER_HOME',
	'USER_PWD' : 'USER_PWD',
	'USER_NAME' : 'USER_NAME',
	'GROUP_NAME' : 'GROUP_NAME',
}


tokens = [
	'COMMA',
	'SEMICOLON',
	'COMMENT',
	'BLANK',
	'COMMAND',
	'EOL',
	'SEP',
	'IDENTITY',
	'INTEGER',
	'STRING'
] + list( reserved.values() )



## regular expression rules for simple tokens
t_COMMA			= r','
t_SEMICOLON		= r';'
t_SEP			= r'::'


## regular expression rules with some action code

def t_COMMENT(t):
	r'\#.*'
	pass

def t_BLANK(t):
	r'[ \t]+'
	pass

def t_EOL(t):
	r'\n+'
	t.lexer.lineno += len(t.value)
	return t

def t_COMMAND(t):
	r'``|`(.*?)[^\\]`|`(.*?)[^\\](\\\\)+`'
	tString = t.value[1:-1]
	specialMap = {
		#'\\\\t' : '\t',
		#'\\\\n' : '\n',
		#'\\\\"' : '"',
		'\\\\`' : '`',
		#'\\\\\\\\' : '\\\\',
	}
	for (k, v) in specialMap.items():
		tString = re.sub(k, v, tString)
	t.value = tString
	return t

def t_IDENTITY(t):
	r'[a-zA-Z_][a-zA-Z_0-9]*'
	t.type = reserved.get(t.value, 'IDENTITY')    # Check for reserved words
	return t

def t_INTEGER(t):
	r'\-?\d+'
	t.value = int(t.value)
	return t

def t_STRING(t):
	r'""|"(\\\\)+"|"(.*?)[^\\](\\\\)+"|"(.*?)[^\\]"'
	tString = t.value[1:-1]
	specialMap = {
		'\\\\t' : '\t',
		'\\\\n' : '\n',
		'\\\\"' : '"',
		'\\\\\\\\' : '\\\\',
	}
	for (k, v) in specialMap.items():
		tString = re.sub(k, v, tString)
	t.value = tString
	return t


### error handling rule
def t_error(t):
	raise Exception("Illegalal token '%s', on lineno:%d" % (t.value[0], t.lexer.lineno))
	#print "Illegal character '%s'" % t.value[0]
	#t.lexer.skip(1)

cmdLexer = lex.lex(debug=0, optimize=1, lextab='cmdTab', nowarn=1, outputdir=os.path.dirname(os.path.realpath(__file__)))

################################################################################################################
if __name__ == '__main__':
	if len(sys.argv) == 2:
		data = open(sys.argv[1]).read()
		print "data:%r" % data
		cmdLexer.input(data)
		while True:
			tok = cmdLexer.token()
			if not tok: break
			print tok
	else:
		lex.runmain(cmdLexer)
