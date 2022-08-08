#!/bin/python3
"""
======== TeX-to-Py half ========

receive commands from TeX, then execute it here
print() might go to TeX's stdout, or somewhere else
"""


import sys
import functools
from typing import Optional
from pathlib import Path
import tempfile

#debug=functools.partial(print, file=sys.stderr)  # unfortunately this is async ... or so it seems...?
debug_file=open(Path(tempfile.gettempdir())/"pythonimmediate_debug_textopy.txt", "w", encoding='u8', buffering=2)
debug=functools.partial(print, file=debug_file, flush=True)

import argparse
parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("mode", choices=["multiprocessing_network", "unnamed_pipe"])
args=parser.parse_args()

# ======== setup communication method. Requires raw_readline() and send_raw() methods.

if True:
	sys.stdin=None  # type: ignore
	# avoid user mistakenly read

	raw_readline=sys.__stdin__.readline  # raw_readline() should return "⟨line⟩\n" or "" (if EOF) on each call

if args.mode=="multiprocessing_network":
	address=("localhost", 7348)  # this must be identical to that of the other half-script
	#address="./pythonimmediate.socket"

	from multiprocessing.connection import Client
	connection=Client(address)
	debug("connected")

	def send_raw(s: str)->None:  # send_raw() should get pass the s = "⟨line⟩\n"
		global connection
		connection.send_bytes(s.encode('u8'))

elif args.mode=="unnamed_pipe":
	pytotex_pid_line=raw_readline()
	import re
	match_=re.fullmatch("pytotex_pid=(\d+)\n", pytotex_pid_line)
	pytotex_pid=int(match_[1])

	connection=open("/proc/" + str(pytotex_pid) + "/fd/0", "w", encoding='u8',
			buffering=1  # line buffering
			)

	def send_raw(s: str)->None:
		global connection
		connection.write(s)
		connection.flush()  # just in case

else:
	assert False

# ======== done.

# https://stackoverflow.com/questions/5122465/can-i-fake-a-package-or-at-least-a-module-in-python-for-testing-purposes
from types import ModuleType
pythonimmediate=ModuleType("pythonimmediate")
pythonimmediate.__file__="pythonimmediate.py"
sys.modules["pythonimmediate"]=pythonimmediate


def export_function_to_module(f):
	"""
	the functions decorated with this decorator are accessible from user code with

	import pythonimmediate
	pythonimmediate.⟨function name⟩(...)
	"""
	setattr(pythonimmediate, f.__name__, f)
	return f

action_done=False


def check_not_finished():
	global action_done
	if action_done:
		raise RuntimeError("can only do one action per block!")
	
def send_finish(s: str)->None:
	check_not_finished()
	global action_done
	action_done=True
	send_raw(s)

@export_function_to_module
def run_cmd(cmd: str)->None:
	"""
	run a single command e.g. cmd="relax" (actually this is not very useful)
	"""
	send_finish(cmd+'\n')


import random
def surround_delimiter(block: str)->str:
	while True:
		delimiter=str(random.randint(0, 10**12))
		if delimiter not in block: break
	return delimiter + "\n" + block + "\n" + delimiter + "\n"
	
@export_function_to_module
def run_block_finish(block: str)->None:
	"""
	run a block of code, catcode-changing commands are allowed inside

	block is some TeX code. It might consist of multiple lines
	"""
	send_finish("block\n" + surround_delimiter(block))

TeXToPyObjectType=Optional[str]

@export_function_to_module
def run_block_local(block: str)->TeXToPyObjectType:
	check_not_finished()
	send_raw("blockcont\n" + surround_delimiter(block))
	return run_main_loop()

def check_line(line: str, *, braces: bool, newline: bool, continue_: Optional[bool])->None:
	"""
	check user-provided line before sending to TeX for execution
	"""
	if braces:
		assert line.count("{") == line.count("}")
	if newline:
		assert '\n' not in line
		assert '\r' not in line  # this is not the line separator but just in case
	if continue_==True: assert "pythonimmediatecontinue" in line
	elif continue_==False: assert "pythonimmediatecontinue" not in line

@export_function_to_module
def run_tokenized_line_finish(line: str, *, check_braces: bool=True, check_newline: bool=True)->None:
	"""
	tokenize the whole line then execute it. line is some TeX code

	catcode-changing commands should not be used inside

	the line must be brace-balanced and has no new line
	"""
	check_line(line, braces=check_braces, newline=check_newline, continue_=False)
	send_finish("tokl\n" + line + "\n")

@export_function_to_module
def run_tokenized_line_peek(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True)->TeXToPyObjectType:
	check_not_finished()
	check_line(line, braces=check_braces, newline=check_newline, continue_=(True if check_continue else None))
	send_raw("tokl\n" + line + "\n")
	return run_main_loop()

@export_function_to_module
def run_tokenized_line_local(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True)->TeXToPyObjectType:
	check_not_finished()
	check_line(line, braces=check_braces, newline=check_newline, continue_=(False if check_continue else None))
	send_raw("toklcont\n" + line + "\n")
	return run_main_loop()





import signal
def on_signal_function(signal_number, stack_frame):
	debug("======== signal")
	traceback.print_stack(file=sys.stderr)
	
signal.signal(signal.SIGHUP, on_signal_function)

import traceback

if 0:
	import atexit
	def atexit_function():
		debug("======== die")
		traceback.print_stack(file=sys.stderr)
	atexit.register(atexit_function)


import time


user_scope: dict={}  # consist of user's local variables etc.

traceback_already_printed_on_TeX_error=False

def readline()->Optional[str]:
	global traceback_already_printed_on_TeX_error
	line=raw_readline()
	if not line:
		if not traceback_already_printed_on_TeX_error:
			traceback.print_stack(file=sys.stderr)
			traceback_already_printed_on_TeX_error=True
		return None
	assert line[-1]=='\n'
	line=line[:-1]
	debug("======== saw line", line)
	return line

def run_python_block()->None:
	global action_done
	old_action_done=action_done

	lines: list[str]=[]
	while True:
		line=readline()
		assert line is not None, "internal error TeX does not send complete data"
		if line=="pythonimm?\"\"\"?'''?":
			debug("executing", "".join(lines))

			action_done=False
			exec('\n'.join(lines), user_scope)
			if not action_done:
				send_raw("none\n")
			break
		else:
			lines.append(line)
	
	action_done=old_action_done


def run_main_loop()->TeXToPyObjectType:
	while True:
		line=readline()
		if not line: return None

		if line=="i":
			run_python_block()
		elif line[0]=="r":
			return line[1:]
		else:
			raise RuntimeError("Internal error: unexpected line "+line)



run_main_loop()  # if this returns cleanly TeX has no error. Otherwise some readline() will reach eof and print out a stack trace

