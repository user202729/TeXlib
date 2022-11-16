#!/bin/python3
"""
======== TeX-to-Py half ========

receive commands from TeX, then execute it here
print() might go to TeX's stdout, or somewhere else
"""


import sys
import inspect
import contextlib
import io
import functools
from typing import Optional, Union, Callable, Any
from pathlib import Path
import tempfile
import signal
import traceback
import time


def user_documentation(x: Union[Callable, str])->Any:
	return x



#debug=functools.partial(print, file=sys.stderr, flush=True)  # unfortunately this is async ... or so it seems...?
#debug_file=open(Path(tempfile.gettempdir())/"pythonimmediate_debug_textopy.txt", "w", encoding='u8', buffering=2)
#debug=functools.partial(print, file=debug_file, flush=True)
debug=lambda *args, **kwargs: None


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

bootstrap_code: str=""
def mark_bootstrap(code: str)->None:
	global bootstrap_code
	bootstrap_code+=code



user_documentation(
"""
All exported functions can be accessed through the module as |import pythonimmediate|.

The |_finish| functions are internal functions, which must be called \emph{at most} once in each
|\pythonimmediate:n| call from \TeX\ to tell \TeX\ what to do.

The |_local| functions simply execute the code. These functions will only return when
the \TeX\ code finishes executing; nevertheless, the \TeX\ code might recursively execute some Python code
inside it.

A simple example is |pythonimmediate.run_block_local('123')| which simply typesets |123|.

The |_peek| functions is the same as above; however, the \TeX\ code must contain an explicit command
|\pythonimmediatecontinue{...}|.

The argument of |\pythonimmediatecontinue| will be |e|-expanded
by |\write| (note that the written content must not contain any newline character,
otherwise the behavior is undefined), then returned as a string by the Python code.
The Python function will only return when |\pythonimmediatecontinue| is called.

In other words, |run_*_local(code)| is almost identical to |run_*_peek(code + "\pythonimmediatecontinue {}")|.
""")

@export_function_to_module
def run_block_finish(block: str)->None:
	send_finish("block\n" + surround_delimiter(block))

TeXToPyObjectType=Optional[str]

mark_bootstrap(
r"""
\cs_new_protected:Npn \__run_blockcont: {
	\__run_block:
	\pythonimmediatecontinue {}
}
""")

@export_function_to_module
def run_block_local(block: str)->TeXToPyObjectType:
	check_not_finished()
	send_raw("blockcont\n" + surround_delimiter(block))
	return run_main_loop()

@user_documentation
@export_function_to_module
def execute(block: str)->None:
	"""
	Run a block of \TeX\ code (might consist of multiple lines).
	Catcode-changing commands are allowed inside.

	A simple example is |pythonimmediate.run_block_local('123')| which simply typesets |123|.

	A more complicated example is |pythonimmediate.run_block_local(r'\verb+%+')|.
	"""
	run_block_local(block)

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



mark_bootstrap(
r"""
\cs_new_protected:Npn \__run_tokl: {
	\ifeof \__read_file
		\msg_error:nn {pythonimmediate} {internal-error}
	\fi
	\global \read \__read_file to \__line  % note that this uses \read to tokenize instead of \readline
	\__line
}
""")

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
	"""
	"""
	check_not_finished()
	check_line(line, braces=check_braces, newline=check_newline, continue_=(True if check_continue else None))
	send_raw("tokl\n" + line + "\n")
	return run_main_loop()

mark_bootstrap(
r"""
\cs_new_protected:Npn \__run_toklcont: {
	\__run_tokl:
	\pythonimmediatecontinue {}
}
""")

@export_function_to_module
def run_tokenized_line_local(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True)->TeXToPyObjectType:
	"""
	"""
	check_not_finished()
	check_line(line, braces=check_braces, newline=check_newline, continue_=(False if check_continue else None))
	send_raw("toklcont\n" + line + "\n")
	return run_main_loop()

mark_bootstrap(
r"""
\cs_new_eq:NN \__run_none: \relax
""")

def run_none_finish()->None:
	check_not_finished()
	send_raw("none\n")

mark_bootstrap(
r"""
\msg_new:nnn {pythonimmediate} {python-error} {Python~error.}
\cs_new_protected:Npn \__run_err: { 
    \msg_error:nn {pythonimmediate} {python-error}
}
""")
def run_error_finish()->None:
	check_not_finished()
	send_raw("err\n")



#def on_signal_function(signal_number, stack_frame):
#	debug("======== signal")
#	traceback.print_stack(file=sys.stderr)
#	
#signal.signal(signal.SIGHUP, on_signal_function)


if 0:
	import atexit
	def atexit_function():
		debug("======== die")
		traceback.print_stack(file=sys.stderr)
	atexit.register(atexit_function)




user_scope: dict={}  # consist of user's local variables etc.

traceback_already_printed_on_TeX_error=False

def readline()->Optional[str]:
	global traceback_already_printed_on_TeX_error
	line=raw_readline()
	if not line:
		if not traceback_already_printed_on_TeX_error:
			traceback_already_printed_on_TeX_error=True
			#print("\n\nTraceback (most recent call last):", file=sys.stderr)
			#traceback.print_stack(file=sys.stderr)
			#print("Runtime", file=sys.stderr)
			raise RuntimeError("Cannot receive message from TeX -- perhaps a TeX error occurred?")
		
		return None
	assert line[-1]=='\n'
	line=line[:-1]
	debug("======== saw line", line)
	return line

block_delimiter: str="pythonimm?\"\"\"?'''?"

def read_block()->str:
	"""
	Internal function to read one block sent from \TeX\ (including the final delimiter line,
	but the delimiter line is not returned)
	"""
	lines: list[str]=[]
	while True:
		line=readline()
		assert line is not None, "internal error TeX does not send complete data"
		if line==block_delimiter:
			return '\n'.join(lines)
		else:
			lines.append(line)

def wrap_executor(f):
	"""
	some internal function. I don't know how to explain this but it works.

	Basically if this is something that might be directly executed from |run_main_loop()|
	then it must be a "executor"...?
	"""
	@functools.wraps(f)
	def result(*args, **kwargs):
		global action_done
		old_action_done=action_done

		action_done=False
		try:
			f(*args, **kwargs)
		except:
			if action_done:
				# error occurred after 'finish' is called, cannot signal the error to TeX, will just ignore (after printing out the traceback)...
				pass
			else:
				run_error_finish()
			traceback.print_exc()
		finally:
			if not action_done:
				run_none_finish()
		
		action_done=old_action_done
	return result

@wrap_executor
def run_python_block()->None:
	"""
	Internal function to read one \emph{Python} block sent from \TeX\ (excluding the initial |i| line)
	and execute it in |user_scope|.
	"""
	content=read_block()
	debug("executing", content)
	exec(content, user_scope)

def send_bootstrap_code()->None:
	global bootstrap_code
	code = (bootstrap_code
		  #.replace("\n", ' ')
		  .replace("__", "_" + "pythonimmediate" + "_")
		 )
	send_raw(surround_delimiter(code))

def run_main_loop()->TeXToPyObjectType:
	while True:
		line=readline()
		if not line: return None

		if line[0]=="i":
			if len(line)==1:
				run_python_block()
			else:
				globals()[line[1:]]()
		elif line[0]=="r":
			return line[1:]
		else:
			raise RuntimeError("Internal error: unexpected line "+line)

# ======== implementation of |\py| etc. Doesn't support verbatim argument yet. ========

def define_handler(f: Callable)->Callable:
	num_arg = len(inspect.signature(f).parameters)
	assert f.__name__.endswith("_handler")
	name = f.__name__.removesuffix("_handler")

	TeX_send_block_commands = ""
	TeX_argspec = ""
	for i in range(1, num_arg+1):
		TeX_send_block_commands += r"\__send_block:n {#" + str(i) + r"}"
		TeX_argspec += "#" + str(i)

	mark_bootstrap(
	"""
	\\cs_new_protected:Npn \\""" + name + TeX_argspec + """ {
		\immediate \write \__write_file { i """ + name + """_handler }
		""" + TeX_send_block_commands + """
		\__read_do_one_command:
	}
	""")
	@functools.wraps(f)
	def result():
		args=[read_block() for _ in range(num_arg)]
		return wrap_executor(f)(*args)
	return result


import linecache

# https://stackoverflow.com/questions/47183305/file-string-traceback-with-line-preview
def exec_or_eval_with_linecache(code: str, globals: dict, mode: str)->Any:
	sourcename: str="<usercode>"
	i=0
	while sourcename in linecache.cache:
		sourcename="<usercode" + str(i) + ">"
		i+=1

	lines=code.splitlines(keepends=True)
	linecache.cache[sourcename] = len(code), None, lines, sourcename

	compiled_code=compile(code, sourcename, mode)
	result=(exec if mode=="exec" else eval)(compiled_code, globals)

	# here the cache data is deleted; however it's **not** deleted if the code throws an error...
	# which is a bit wasteful but overall not a big issue
	del linecache.cache[sourcename]

	return result

def exec_with_linecache(code: str, globals: dict)->None:
	exec_or_eval_with_linecache(code, globals, "exec")

def eval_with_linecache(code: str, globals: dict)->Any:
	return exec_or_eval_with_linecache(code, globals, "eval")


@define_handler
def py_handler(code: str)->None:
	pythonimmediate.run_block_finish(str(eval_with_linecache(code, user_scope))+"%")

@define_handler
def pyc_handler(code: str)->None:
	with io.StringIO() as t:
		with contextlib.redirect_stdout(t):
			exec_with_linecache(code, user_scope)
		content=t.getvalue()
		if content.endswith("\n"):
			content=content[:-1]
		else:
			#content+=r"\empty"  # this works too
			content+="%"
		pythonimmediate.run_block_finish(content)

@define_handler
def pycq_handler(code: str)->None:
	with contextlib.redirect_stdout(None):
		exec_with_linecache(code, user_scope)
	run_none_finish()


# ======== implementation of |pycode| environment
mark_bootstrap(
r"""
\NewDocumentEnvironment{pycode}{}{
	\saveenvreinsert \__code {
		\exp_last_unbraced:Nx \pycodex {{\__code} {\the\inputlineno} {
			\ifdefined\currfilename \currfilename \fi
		} {
			\ifdefined\currfileabspath \currfileabspath \fi
		}}
	}
}{
	\endsaveenvreinsert
}
""")

def normalize_lines(lines: list[str])->list[str]:
	return [line.rstrip() for line in lines]

@define_handler
def pycodex_handler(code: str, lineno_: str, filename: str, fileabspath: str)->None:
	lineno=int(lineno_)
	# find where the code comes from... (for easy meaningful traceback)
	target_filename: Optional[str] = None

	code_lines_normalized=normalize_lines(code.splitlines())

	for f in (fileabspath, filename):
		if not f: continue
		p=Path(f)
		if not p.is_file(): continue
		file_lines=p.read_text().splitlines()[lineno-len(code_lines_normalized)-1:lineno-1]
		if normalize_lines(file_lines)==code_lines_normalized:
			target_filename=f
			break

	if not target_filename:
		raise RuntimeError("Source file not found!")

	with io.StringIO() as t:
		with contextlib.redirect_stdout(t):
			if target_filename:
				code='\n'.join(file_lines)  # restore missing trailing spaces
			code="\n"*(lineno-len(code_lines_normalized)-1)+code
			if target_filename:
				compiled_code=compile(code, target_filename, "exec")
				exec(compiled_code, user_scope)
			else:
				exec(code, user_scope)
		pythonimmediate.run_block_finish(t.getvalue())
	

send_bootstrap_code()
run_main_loop()  # if this returns cleanly TeX has no error. Otherwise some readline() will reach eof and print out a stack trace

