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
from typing import Optional, Union, Callable, Any, Iterator, Protocol
import typing
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
import tempfile
import signal
import traceback
import re
import collections
import enum


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
	match_=re.fullmatch("pytotex_pid=(\d+)\n", pytotex_pid_line)
	assert match_
	pytotex_pid=int(match_[1])

	connection_=open("/proc/" + str(pytotex_pid) + "/fd/0", "w", encoding='u8',
			buffering=1  # line buffering
			)

	def send_raw(s: str)->None:
		global connection_
		connection_.write(s)
		connection_.flush()  # just in case

else:
	assert False

# ======== done.

# https://stackoverflow.com/questions/5122465/can-i-fake-a-package-or-at-least-a-module-in-python-for-testing-purposes
from types import ModuleType
pythonimmediate: Any=ModuleType("pythonimmediate")
pythonimmediate.__file__="pythonimmediate.py"
sys.modules["pythonimmediate"]=pythonimmediate

pythonimmediate.debugging=True

def debugonly(s: str)->str:
	if pythonimmediate.debugging: return s
	return ""


def export_function_to_module(f: Callable)->Callable:
	"""
	the functions decorated with this decorator are accessible from user code with

	import pythonimmediate
	pythonimmediate.⟨function name⟩(...)
	"""
	setattr(pythonimmediate, f.__name__, f)
	return f

action_done=False


def check_not_finished()->None:
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

bootstrap_code: Optional[str]=""
def mark_bootstrap(code: str)->None:
	global bootstrap_code
	assert bootstrap_code is not None
	bootstrap_code+=code

def substitute_private(code: str)->str:
	return (code
		  #.replace("\n", ' ')  # because there are comments in code, cannot
		  .replace("__", "_" + "pythonimmediate" + "_")
		 )

def send_bootstrap_code()->None:
	global bootstrap_code
	assert bootstrap_code is not None
	send_raw(surround_delimiter(substitute_private(bootstrap_code)))
	bootstrap_code = None

# ========

# when 'i⟨string⟩' is sent from TeX to Python, the function with index ⟨string⟩ in this dict is called
TeX_handlers: dict[str, Callable[[], None]]={}

TeXToPyObjectType=Optional[str]

def run_main_loop()->TeXToPyObjectType:
	while True:
		line=readline()
		if not line: return None

		if line[0]=="i":
			TeX_handlers[line[1:]]()
		elif line[0]=="r":
			return line[1:]
		else:
			raise RuntimeError("Internal error: unexpected line "+line)

def run_main_loop_get_return_one()->str:
	line=readline()
	assert line is not None
	assert line[0]=="r"
	return line[1:]



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
"""
+ debugonly(
r"""
	\ifeof \__read_file
		\msg_error:nn {pythonimmediate} {internal-error}
	\fi
""") +
r"""
	%\begingroup
	%	\endlinechar=-1~
	%	\read \__read_file to \__line  % note that this uses \read to tokenize instead of \readline
	%	\expandafter
	%\endgroup
	%	\__line

	\ior_get:NN \__read_file \__line
	\__line
}
""")  # performance about the same it seems

@export_function_to_module
def run_tokenized_line_finish(line: str, *, check_braces: bool=True, check_newline: bool=True)->None:
	"""
	tokenize the whole line then execute it. line is some TeX code

	catcode-changing commands should not be used inside

	the line must be brace-balanced and has no new line

	note that the line is tokenized in the current catcode regime, but with \endlinechar set to -1, thus there's no trailing space
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
	"""
	this function is fatal to TeX, so we only run it when it's fatal to Python.
	Which we use atexit_function above.

	TODO what to do if the error is caught?

	Also we want to make sure the Python traceback is printed strictly before run_error_finish() is called.
	(thus atexit is used for now)
	"""
	check_not_finished()
	send_raw("err\n")


do_run_error_finish=True

if 1:
	import atexit
	def atexit_function()->None:
		global action_done
		#debug("======== exit ========")
		#traceback.print_stack(file=sys.stderr)
		if do_run_error_finish:
			action_done=False
			run_error_finish()
	atexit.register(atexit_function)




user_scope: dict[str, Any]={}  # consist of user's local variables etc.

# this makes sure if TeX process errors out everything will only be printed once
# (I think? run_main_loop() might be called recursively...)
# actually it's probably unnecessary because raise RuntimeError() will halt the Python process
# what if the error is caught?...
traceback_already_printed_on_TeX_error=False

def readline(allow_nothing=False)->Optional[str]:
	global traceback_already_printed_on_TeX_error
	line=raw_readline()
	if not line:
		if not traceback_already_printed_on_TeX_error:
			traceback_already_printed_on_TeX_error=True
			#print("\n\nTraceback (most recent call last):", file=sys.stderr)
			#traceback.print_stack(file=sys.stderr)
			#print("Runtime", file=sys.stderr)

		if allow_nothing:
			return None
		raise RuntimeError("Cannot receive message from TeX -- perhaps a TeX error occurred?")

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


@export_function_to_module
class Token(ABC):
	@abstractmethod
	def __str__(self)->str:
		...
	@abstractmethod
	def serialize(self)->str:
		...
	@abstractmethod
	def repr1(self)->str:
		...

	def __repr__(self)->str:
		return f"<Token: {self.repr1()}>"

@export_function_to_module
@dataclass(repr=False)
class ControlSequenceToken(Token):
	csname: str
	def __str__(self)->str:
		if self.csname=="": return r"\csname\endcsname"
		return "\\"+self.csname
	def serialize(self)->str:
		return "0"+self.csname+"/"
	def repr1(self)->str:
		return f"\\{self.csname}"

@export_function_to_module
class Catcode(enum.Enum):
	begin_group=bgroup=1
	end_group=egroup=2
	math_toggle=math=3
	alignment=4
	parameter=param=6
	math_superscript=superscript=7
	math_subscript=subscript=8
	space=10
	letter=11
	other=12
	active=13

	escape=0
	end_of_line=paragraph=line=5
	ignored=9
	comment=14
	invalid=15

	@property
	def for_token(self)->bool:
		"""
		Return whether a token may have this catcode.
		"""
		return self not in (Catcode.escape, Catcode.line, Catcode.ignored, Catcode.comment, Catcode.invalid)

@export_function_to_module
@dataclass(repr=False)
class CharacterToken(Token):
	index: int
	catcode: Catcode
	@property
	def chr(self)->str:
		return chr(self.index)
	def __post_init__(self)->None:
		assert self.catcode.for_token
	def __str__(self)->str:
		return self.chr
	def serialize(self)->str:
		return f"{self.catcode.value:X}{self.chr}"
	def repr1(self)->str:
		cat=str(self.catcode.value).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
		return f"{self.chr}{cat}"

class FrozenRelaxToken(Token):
	def __str__(self)->str:
		return r"\relax"
	def serialize(self)->str:
		return "R"
	def repr1(self)->str:
		return r"[frozen]\relax"

frozen_relax_token=FrozenRelaxToken()
pythonimmediate.frozen_relax_token=frozen_relax_token

# other special tokens later...

@export_function_to_module
class TokenList(collections.UserList[Token]):
	def serialize(self)->str:
		return "".join(t.serialize() for t in self)
	@staticmethod
	def deserialize(data: str)->"TokenList":
		result=TokenList()
		for match_ in re.finditer(r'0(.*?)/|(R)|(.)\\?(.) ?', data):
			groups=match_.groups()
			i=0
			while groups[i] is None: i+=1
			if i==0:
				result.append(ControlSequenceToken(groups[0]))
			elif i==1:
				result.append(frozen_relax_token)
			elif i==2:
				result.append(CharacterToken(index=ord(groups[3]), catcode=Catcode(int(groups[2], 16))))
			else:
				assert False
		return result
	def __repr__(self)->str:
		return '<TokenList: ' + ' '.join(t.repr1() for t in self) + '>'




class TeXToPyData(ABC):
	@staticmethod
	@abstractmethod
	def read()->"TeXToPyData":
		...
	@staticmethod
	@abstractmethod
	def send_code(arg: str)->str:
		pass
	@staticmethod
	@abstractmethod
	def send_code_var(var: str)->str:
		pass

# tried and failed
#@typing.runtime_checkable
#class TeXToPyData(Protocol):
#	@staticmethod
#	def read()->"TeXToPyData":
#		...
#
#	#send_code: str
#
#	#@staticmethod
#	#@property
#	#def send_code()->str:
#	#	...
	

class TTPLine(TeXToPyData, str):
	send_code=r"\immediate \write \__write_file {{\unexpanded{{ {} }}}}".format
	send_code_var=r"\immediate \write \__write_file {{\unexpanded{{ {} }}}}".format
	@staticmethod
	def read()->"TTPLine":
		line=readline()
		assert line is not None
		return TTPLine(line)

class TTPBlock(TeXToPyData, str):
	send_code=r"\__send_block:n {{ {} }}".format
	send_code_var=r"\__send_block:V {}".format
	@staticmethod
	def read()->"TTPBlock":
		return TTPBlock(read_block())

class TTPTokenList(TeXToPyData, TokenList):
	send_code=r"\tlserializeb:Nn \__tmp {{ {} }} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	send_code_var=r"\tlserializeb:NV \__tmp {} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	@staticmethod
	def read()->"TTPTokenList":
		line=readline()
		assert line is not None
		debug(line)
		return TTPTokenList(TokenList.deserialize(line))


class PyToTeXData(ABC):
	@staticmethod
	@abstractmethod
	def read_code(var: str)->str:
		...
	@abstractmethod
	def write(self)->None:
		...

@dataclass
class PTTVerbatimLine(PyToTeXData):
	"""
	Represents a line to be tokenized verbatim. Internally the |\readline| primitive is used.
	The trailing newline is not included, i.e. it's read under |\endlinechar=-1|.
	"""
	# TODO add test for PTTVerbatimLine that has trailing spaces
	data: str
	read_code=r"\ior_str_get:NN \__read_file {} ".format
	def write(self)->None:
		assert "\n" not in self.data
		send_raw(self.data+"\n")

@dataclass
class PTTTeXLine(PyToTeXData):
	"""
	Represents a line to be tokenized in \TeX's current catcode regime.
	The trailing newline is not included, i.e. it's tokenized under |\endlinechar=-1|.
	"""
	data: str
	read_code=r"\ior_get:NN \__read_file {} ".format
	def write(self)->None:
		assert "\n" not in self.data
		send_raw(self.data+"\n")

@dataclass
class PTTBlock(PyToTeXData):
	data: str
	read_code=r"\__read_block:n {}".format
	def write(self)->None:
		send_raw(surround_delimiter(self.data))

@dataclass
class PTTTokenList(PyToTeXData):
	data: TokenList
	read_code=r"\ior_str_get:NN \__read_file {0}  \tldeserializeb:NV {0} {0}".format
	def write(self)->None:
		send_raw(self.data.serialize()+"\n")


def wrap_executor(f: Callable[..., None])->Callable:
	"""
	some internal function. I don't know how to explain this but it works.

	Basically if this is something that might be directly executed from |run_main_loop()|
	then it must be a "executor"...?
	"""
	@functools.wraps(f)
	def result(*args, **kwargs)->None:
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
				# TODO what should be done here? What if the error raised below is caught
				action_done=True
				#do_run_error_finish=True  # it already is
			raise
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

assert "" not in TeX_handlers
TeX_handlers[""]=run_python_block


# ======== define TeX functions that execute Python code ========
# ======== implementation of |\py| etc. Doesn't support verbatim argument yet. ========

import itertools
import string

def random_identifiers()->Iterator[str]:  # do this to avoid TeX hash collision while keeping the length short
	for len_ in itertools.count(0):
		for value in range(1<<len_):
			for initial in string.ascii_letters:
				yield initial + f"{value:0{len_}b}".translate({ord("0"): "a", ord("1"): "b"})

random_identifier_iterable=random_identifiers()

def get_random_identifier()->str:
	return next(random_identifier_iterable)


def define_TeX_call_Python(f: Callable[..., None], name: str=None, argtypes: list[type[TeXToPyData]]=None, identifier: str=None)->str:
	"""
	This function setups some internal data structure, and
	returns the \TeX\ code to be executed on the \TeX\ side to define the macro.

	f: the Python function to be executed.
	It should take some arguments and eventually (optionally) call one of the |_finish| functions.

	name: the macro name on the \TeX\ side. This should only consist of letter characters in |expl3| catcode regime.

	argtypes: list of argument types. If it's None it will be automatically deduced from the function |f|'s signature.

	Returns: some code (to be executed in |expl3| catcode regime) as explained above.
	"""
	if argtypes is None: argtypes=[p.annotation for p in inspect.signature(f).parameters.values()]
	if name is None: name=f.__name__

	if identifier is None: identifier=get_random_identifier()
	assert identifier not in TeX_handlers

	@functools.wraps(f)
	def g()->None:
		assert argtypes is not None
		args=[argtype.read() for argtype in argtypes]
		wrap_executor(f)(*args)
	TeX_handlers[identifier]=g

	TeX_argspec = ""
	TeX_send_input_commands = ""
	for i, argtype in enumerate(argtypes):
		if not issubclass(argtype, TeXToPyData):
			raise RuntimeError(f"Argument type {argtype} is incorrect, should be a subclass of TeXToPyData")
		arg = f"#{i+1}"
		TeX_send_input_commands += argtype.send_code(arg)
		TeX_argspec += arg

	return """
	\\cs_new_protected:Npn \\""" + name + TeX_argspec + """ {
		\immediate \write \__write_file { i """ + identifier + """ }
		""" + TeX_send_input_commands + """
		\__read_do_one_command:
	}
	"""


def define_internal_handler(f: Callable)->Callable:
	mark_bootstrap(define_TeX_call_Python(f))
	return f


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
	return (exec if mode=="exec" else eval)(compiled_code, globals)

	#del linecache.cache[sourcename]
	# we never delete the cache, in case some function is defined here then later are called...

def exec_with_linecache(code: str, globals: dict[str, Any])->None:
	exec_or_eval_with_linecache(code, globals, "exec")

def eval_with_linecache(code: str, globals: dict[str, Any])->Any:
	return exec_or_eval_with_linecache(code, globals, "eval")


@define_internal_handler
def py(code: TTPBlock)->None:
	pythonimmediate.run_block_finish(str(eval_with_linecache(code, user_scope))+"%")

def print_TeX(*args, **kwargs)->None:
	if not hasattr(pythonimmediate, "file"):
		raise RuntimeError("Internal error: attempt to print to TeX outside any environment!")
	if pythonimmediate.file is not None:
		functools.partial(print, file=pythonimmediate.file)(*args, **kwargs)  # allow user to override `file` kwarg
pythonimmediate.print=print_TeX

class RedirectPrintTeX:
	def __init__(self, t)->None:
		self.t=t

	def __enter__(self)->None:
		if hasattr(pythonimmediate, "file"):
			self.old=pythonimmediate.file
		pythonimmediate.file=self.t

	def __exit__(self, exc_type, exc_value, tb)->None:
		if hasattr(self, "old"):
			pythonimmediate.file=self.old
		else:
			del pythonimmediate.file

def run_code_redirect_print_TeX(f: Callable[[], Any])->None:
	with io.StringIO() as t:
		with RedirectPrintTeX(t):
			result=f()
			if result is not None:
				t.write(str(result)+"%")
		content=t.getvalue()
		if content.endswith("\n"):
			content=content[:-1]
		else:
			#content+=r"\empty"  # this works too
			content+="%"
		pythonimmediate.run_block_finish(content)

@define_internal_handler
def pyc(code: TTPBlock)->None:
	run_code_redirect_print_TeX(lambda: exec_with_linecache(code, user_scope))

@define_internal_handler
def pycq(code: TTPBlock)->None:
	with RedirectPrintTeX(None):
		exec_with_linecache(code, user_scope)
	run_none_finish()

mark_bootstrap(
r"""
\NewDocumentCommand\pyv{v}{\py{#1}}
""")

# ======== implementation of |pycode| environment
mark_bootstrap(
r"""
\NewDocumentEnvironment{pycode}{}{
	\saveenvreinsert \__code {
		\exp_last_unbraced:Nx \__pycodex {{\__code ^^J} {\the\inputlineno} {
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

@define_internal_handler
def __pycodex(code: TTPBlock, lineno_: TTPLine, filename: TTPLine, fileabspath: TTPLine)->None:
	if not code.strip(): return  # currently saveenv returns empty string + single newline both when there's 0 or 1 empty line between environment body. TODO later fix the bug properly

	lineno=int(lineno_)
	# find where the code comes from... (for easy meaningful traceback)
	target_filename: Optional[str] = None

	code_lines_normalized=normalize_lines(code.splitlines(keepends=True))

	for f in (fileabspath, filename):
		if not f: continue
		p=Path(f)
		if not p.is_file(): continue
		file_lines=p.read_text().splitlines(keepends=True)[lineno-len(code_lines_normalized)-1:lineno-1]
		#print()
		#print()
		#print("========")
		#for line in normalize_lines(file_lines): print(line)
		#print("========")
		#for line in code_lines_normalized: print(line)
		#print(repr(code))
		#print("========")
		#print(lineno)
		#print()
		#print()
		if normalize_lines(file_lines)==code_lines_normalized:
			target_filename=f
			break

	if not target_filename:
		raise RuntimeError("Source file not found! (attempted {})".format((fileabspath, filename)))

	with io.StringIO() as t:
		with RedirectPrintTeX(t):
			if target_filename:
				code_=''.join(file_lines)  # restore missing trailing spaces
			code_="\n"*(lineno-len(code_lines_normalized)-1)+code_
			if target_filename:
				compiled_code=compile(code_, target_filename, "exec")
				exec(compiled_code, user_scope)
			else:
				exec(code_, user_scope)
		pythonimmediate.run_block_finish(t.getvalue())

# ======== Python-call-TeX functions
# ======== additional functions...

user_documentation(
r"""
These functions get an argument in the input stream and returns it detokenized.

Which means, for example, |#| are doubled, multiple spaces might be collapsed into one, spaces might be introduced
after a control sequence.

It's undefined behavior if the message's "string representation" contains a "newline character".
""")

def template_substitute(template: str, pattern: str, substitute: Union[str, Callable[[re.Match], str]], optional: bool=False)->str:
	"""
	pattern is a regex
	"""
	if not optional:
		#assert template.count(pattern)==1
		assert len(re.findall(pattern, template))==1
	return re.sub(pattern, substitute, template)

#typing.TypeVarTuple(PyToTeXData)

#PythonCallTeXFunctionType=Callable[[PyToTeXData], Optional[tuple[TeXToPyData, ...]]]

class PythonCallTeXFunctionType(Protocol):  # https://stackoverflow.com/questions/57658879/python-type-hint-for-callable-with-variable-number-of-str-same-type-arguments
	def __call__(self, *args: PyToTeXData)->Optional[tuple[TeXToPyData, ...]]: ...

class PythonCallTeXSyncFunctionType(PythonCallTeXFunctionType):  # https://stackoverflow.com/questions/57658879/python-type-hint-for-callable-with-variable-number-of-str-same-type-arguments
	def __call__(self, *args: PyToTeXData)->tuple[TeXToPyData, ...]: ...

def define_Python_call_TeX(TeX_code: str, ptt_argtypes: list[type[PyToTeXData]], ttp_argtypes: list[type[TeXToPyData]],
						   *,
						   recursive: bool=True,
						   sync: bool=None,
						   )->tuple[str, PythonCallTeXFunctionType]:
	"""
	|TeX_code| should be some expl3 code that defines a function with name |%name%| that when called should:
		* run some \TeX\ code (which includes reading the arguments, if any)
		* do the following if |sync|:
			* send |r| to Python
			* send whatever needed for the output (as in |ttp_argtypes|)
		* call |\__read_do_one_command:|

		This is allowed to contain the following:
		* %name%: the name of the function to be defined as explained above.
		* %read_arg0(...)%, %read_arg1(...)%: will be expanded to code that reads the input.
		* %send_arg0(...)%, %send_arg1(...)%: will be expanded to code that sends the content.
		* %send_arg0_var(...)%, %send_arg1_var(...)%: will be expanded to code that sends the content in the variable.
		* %optional_sync%: expanded to code that writes |r| (to sync), if |sync| is True.

	ptt_argtypes: list of argument types to be sent from Python to TeX (i.e. input of the TeX function)

	ttp_argtypes: list of argument types to be sent from TeX to Python (i.e. output of the TeX function)

	recursive: whether the TeX_code might call another Python function. Default to True.
		It does not hurt to always specify True, but performance would be a bit slower.

	sync: whether the Python function need to wait for the TeX function to finish. Default to true.
		Required if |ttp_argtypes| is not empty.
		This should be left to be the default None most of the time. (which will make it always sync if |debugging|,
		otherwise only sync if needed i.e. there's some output)

	Return some TeX_code to be executed, and a Python function object that when called will call the TeX function
	and return the result.

	Possible optimizations:
		* the |r| is not needed if not recursive and |ttp_argtypes| is nonempty
			(the output itself tells Python when the \TeX\ code finished)
		* the first line of the output may be on the same line as the |r| itself
	"""
	if sync is None:
		if pythonimmediate.debugging: sync=True
		else: sync=ttp_argtypes!=[]

		TeX_code=template_substitute(TeX_code, "%optional_sync%",
							   lambda _: r'\immediate\write\__write_file { r }' if sync else '',)

	TeX_code=template_substitute(TeX_code, "%sync%",
						   lambda _: r'\immediate\write\__write_file { r }' if sync else '', optional=True)

	assert sync is not None
	if ttp_argtypes: assert sync
	identifier=get_random_identifier()  # TODO to be fair it isn't necessary to make the identifier both ways distinct, can reuse

	TeX_code=template_substitute(TeX_code, "%name%", lambda _: r"\__run_" + identifier + ":")

	for i, argtype_ in enumerate(ptt_argtypes):
		TeX_code=template_substitute(TeX_code, r"%read_arg" + str(i) + r"\(([^)]*)\)%",
							   lambda match: argtype_.read_code(match[1]),
							   optional=True)

	for i, argtype in enumerate(ttp_argtypes):
		TeX_code=template_substitute(TeX_code, f"%send_arg{i}" + r"\(([^)]*)\)%",
							   lambda match: argtype.send_code(match[1]),
							   optional=True)
		TeX_code=template_substitute(TeX_code, f"%send_arg{i}_var" + r"\(([^)]*)\)%",
							   lambda match: argtype.send_code_var(match[1]),
							   optional=True)

	def f(*args)->Optional[tuple[TeXToPyData, ...]]:
		assert len(args)==len(ptt_argtypes)

		# send function header
		check_not_finished()
		send_raw(identifier+"\n")

		# send function args
		for arg, argtype in zip(args, ptt_argtypes):
			assert isinstance(arg, argtype)
			arg.write()

		if not sync: return None

		# wait for the result
		if recursive:
			result_=run_main_loop()
		else:
			result_=run_main_loop_get_return_one()
		assert not result_

		result=[]
		for argtype_ in ttp_argtypes:
			result.append(argtype_.read())
		return tuple(result)

	
	return TeX_code, f

def define_Python_call_TeX_local(*args, **kwargs)->PythonCallTeXFunctionType:
	code, result=define_Python_call_TeX(*args, **kwargs)
	mark_bootstrap(code)
	return result

def define_Python_call_TeX_local_sync(*args, **kwargs)->PythonCallTeXSyncFunctionType:
	return define_Python_call_TeX_local(*args, **kwargs, sync=True)  # type: ignore

get_argument_detokenized_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% #1 {
	\immediate\write\__write_file { \unexpanded {
		r ^^J
		#1
	}}
	\__read_do_one_command:
}
""", [], [TTPLine], recursive=False)
@export_function_to_module
@user_documentation
def get_argument_detokenized()->str:
	"""
	Get a mandatory argument.
	"""
	return str(get_argument_detokenized_()[0])

get_argument_tokenlist_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% #1 {
	%sync%
	%send_arg0(#1)%
	\__read_do_one_command:
}
""", [], [TTPTokenList], recursive=False)
@export_function_to_module
@user_documentation
def get_argument_tokenlist()->TokenList:
	"""
	Get a mandatory argument as a TokenList
	"""
	return TokenList(get_argument_tokenlist_()[0])  # type: ignore

get_optional_argument_detokenized_=define_Python_call_TeX_local_sync(
r"""
\NewDocumentCommand %name% {o} {
	\immediate\write \__write_file {
		r ^^J
		\IfNoValueTF {#1} {
			0
		} {
			\unexpanded{1 #1}
		}
	}
	\__read_do_one_command:
}
""", [], [TTPLine], recursive=False)
@export_function_to_module
@user_documentation
def get_optional_argument_detokenized()->Optional[str]:
	"""
	Get an optional argument.
	"""
	[result]=get_optional_argument_detokenized_()
	result_=str(result)
	if result_=="0": return None
	assert result_[0]=="1", result_
	return result_[1:]


get_verbatim_argument_=define_Python_call_TeX_local_sync(
r"""
\NewDocumentCommand %name% {v} {
	\immediate\write\__write_file { \unexpanded {
		r ^^J
		#1
	}}
	\__read_do_one_command:
}
""", [], [TTPLine], recursive=False)
@export_function_to_module
@user_documentation
def get_verbatim_argument()->str:
	"""
	Get a verbatim argument. Since it's verbatim, there's no worry of |#| being doubled,
	but it can only be used at top level.
	"""
	return str(get_verbatim_argument_()[0])

get_multiline_verbatim_argument_=define_Python_call_TeX_local_sync(
r"""
\NewDocumentCommand %name% {+v} {
	\immediate\write\__write_file { r }
	\begingroup
		\newlinechar=13~  % this is what +v argument type in xparse uses
		\__send_block:n { #1 }
	\endgroup
	\__read_do_one_command:
}
""", [], [TTPBlock], recursive=False)
@export_function_to_module
@user_documentation
def get_multiline_verbatim_argument()->str:
	"""
	Get a multi-line verbatim argument.
	"""
	return str(get_multiline_verbatim_argument_()[0])

newcommand2=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn %name% {
	\begingroup
		\endlinechar=-1~
		%read_arg0(\__line)%
		%read_arg1(\__identifier)%
		\cs_new_protected:cpx {\__line} {
			\unexpanded{\immediate\write \__write_file} { i \__identifier }
			\unexpanded{\__read_do_one_command:}
		}
	\endgroup
	%optional_sync%
	\__read_do_one_command:
}
""", [PTTVerbatimLine, PTTVerbatimLine], [], recursive=False)

renewcommand2=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn %name% {
	\begingroup
		\endlinechar=-1~
		\readline \__read_file to \__line
		\readline \__read_file to \__identifier
		\exp_args:Ncx \renewcommand {\__line} {
			\unexpanded{\immediate\write \__write_file} { i \__identifier }
			\unexpanded{\__read_do_one_command:}
		}
		\exp_args:Nc \MakeRobust {\__line}  % also make the command global
	\endgroup
	%optional_sync%
	\__read_do_one_command:
}
""", [PTTVerbatimLine, PTTVerbatimLine], [], recursive=False)

def check_function_name(name: str)->None:
	if not re.fullmatch("[A-Za-z]+", name) or (len(name)==1 and ord(name)<=0x7f):
		raise RuntimeError("Invalid function name: "+name)

def newcommand_(name: str, f: Callable)->Callable:
	identifier=get_random_identifier()

	newcommand2(PTTVerbatimLine(name), PTTVerbatimLine(identifier))

	_code=define_TeX_call_Python(
			lambda: run_code_redirect_print_TeX(f),
			name, argtypes=[], identifier=identifier)
	# ignore _code, already executed something equivalent in \__run_[re]newc:
	return f

def renewcommand_(name: str, f: Callable)->Callable:
	identifier=get_random_identifier()

	renewcommand2(PTTVerbatimLine(name), PTTVerbatimLine(identifier))
	# TODO remove the redundant entry from TeX_handlers (although technically is not very necessary, just cause slight memory leak)
	#try: del TeX_handlers["u"+name]
	#except KeyError: pass

	_code=define_TeX_call_Python(
			lambda: run_code_redirect_print_TeX(f),
			name, argtypes=[], identifier=identifier)
	# ignore _code, already executed something equivalent in \__run_[re]newc:
	return f

	

@export_function_to_module
def newcommand(x: Union[str, Callable]=None, f: Callable=None)->Callable:
	"""
	Define a new \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return newcommand(x)(f)
	if x is None: return newcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(newcommand_, x)
	return newcommand_(x.__name__, x)

@export_function_to_module
def renewcommand(x: Union[str, Callable]=None, f: Callable=None)->Callable:
	"""
	Redefine a \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return newcommand(x)(f)
	if x is None: return newcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(renewcommand_, x)
	return renewcommand_(x.__name__, x)


# ========

put_next_tokenlist=define_Python_call_TeX_local(
r"""
\tl_gset:Nn \__put_next_tmp {
	%optional_sync%
	\__read_do_one_command:
}
\cs_new_protected:Npn %name% {
	%read_arg0(\__target)%
	\expandafter \__put_next_tmp \__target
}
"""
		, [PTTTokenList], [], recursive=False)
put_next_TeX_line=define_Python_call_TeX_local(
r"""
\tl_gset:Nn \__put_next_tmpa {
	%optional_sync%
	\__read_do_one_command:
}
\cs_new_protected:Npn %name% {
	%read_arg0(\__target)%
	\expandafter \__put_next_tmpa \__target
}
"""
		, [PTTTeXLine], [], recursive=False)

@export_function_to_module
@user_documentation
def put_next(arg: Union[str, Token, TokenList])->None:
	"""
	Put some content forward in the input stream.

	arg: has type |str| (will be tokenized in the current catcode regime, must be a single line),
	or |TokenList|.
	"""
	if isinstance(arg, Token): arg=TokenList([arg])
	if isinstance(arg, str): put_next_TeX_line(PTTTeXLine(arg))
	else: put_next_tokenlist(PTTTokenList(arg))

get_next_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__get_next_callback: #1 {
	\immediate\write \__write_file { r^^J #1 }
	\__read_do_one_command:
}

\cs_new_protected:Npn %name% {
	\peek_analysis_map_inline:n {
		\peek_analysis_map_break:n {
			\tlserializeb_char_unchecked:nnNN {##1}{##2}##3 \__get_next_callback:
		}
	}
}
""", [], [TTPLine], recursive=False)

@export_function_to_module
@user_documentation
def get_next_token()->Token:
	"""
	Get the following token.

	Note: in LaTeX3 versions without the commit |https://github.com/latex3/latex3/commit/24f7188904d6|
	sometimes this may error out.

	Note: because of the internal implementation of |\peek_analysis_map_inline:n|, this may
	tokenize up to 2 tokens ahead (including the returned token),
	as well as occasionally return the wrong token in unavoidable cases.
	"""
	line=str(get_next_()[0])
	t=TokenList.deserialize(line)
	assert len(t)==1
	return t[0]


peek_next_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__peek_next_callback: #1 {
	\immediate\write \__write_file { r^^J #1 }
	\expandafter  % expand the ##1 in (*)
		\__read_do_one_command:
}

\cs_new_protected:Npn %name% {
	\peek_analysis_map_inline:n {
		\peek_analysis_map_break:n {
			\tlserializeb_char_unchecked:nnNN {##1}{##2}##3 \__peek_next_callback: ##1 % (*)
		}
	}
}
""", [], [TTPLine], recursive=False)

@export_function_to_module
@user_documentation
def peek_next_token()->Token:
	"""
	Get the following token without removing it from the input stream.

	Note: in LaTeX3 versions without the commit |https://github.com/latex3/latex3/commit/24f7188904d6|
	sometimes this may error out.

	Note: because of the internal implementation of |\peek_analysis_map_inline:n|, this may
	tokenize up to 2 tokens ahead (including the returned token),
	as well as occasionally return the wrong token in unavoidable cases.
	"""
	line=str(peek_next_()[0])
	t=TokenList.deserialize(line)
	assert len(t)==1, (line, t)
	return t[0]


peek_next_meaning_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__peek_next_meaning_callback: {
	\edef \__tmp {\meaning \__tmp}  % just in case |\__tmp| is outer, |\write| will not be able to handle it
	%\immediate\write \__write_file { r^^J \unexpanded\expandafter{\__tmp} }
	\immediate\write \__write_file { r^^J \__tmp }
	\__read_do_one_command:
}
\cs_new_protected:Npn %name% {
	\futurelet \__tmp \__peek_next_meaning_callback:
}
""", [], [TTPLine], recursive=False)
# TODO I wonder which one is faster. Need to benchmark...
@export_function_to_module
@user_documentation
def peek_next_meaning()->str:
	"""
	Get the meaning of the following token, as a string, using the current |\escapechar|.
	
	This is recommended over |peek_next_token()| as it will not tokenize an extra token.

	It's undefined behavior if there's a newline (|\newlinechar| or |^^J|, the latter is OS-specific)
	in the meaning string.
	"""
	return str(peek_next_meaning_()[0])


peek_next_char_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__peek_next_char_callback: {
	\edef \__tmpb { \expandafter\str_item:nn\expandafter{\meaning \__tmp} {-1} }  % \expandafter just in case \__tmp is \outer
	\if \__tmp \__tmpb  % is a character
		\immediate\write \__write_file { r^^J \__tmp }
	\else  % is not?
		\immediate\write \__write_file { r^^J }
	\fi
	\__read_do_one_command:
}
\cs_new_protected:Npn %name% {
	\futurelet \__tmp \__peek_next_char_callback:
}
""", [], [TTPLine], recursive=False)
@export_function_to_module
@user_documentation
def peek_next_char()->str:
	"""
	Get the meaning of the following token, as a string, using the current |\escapechar|.
	
	This is recommended over |peek_next_token()| as it will not tokenize an extra token.

	It's undefined behavior if there's a newline (|\newlinechar| or |^^J|, the latter is OS-specific)
	in the meaning string.
	"""
	return str(peek_next_meaning_()[0])


# ========

send_bootstrap_code()
run_main_loop()  # if this returns cleanly TeX has no error. Otherwise some readline() will reach eof and print out a stack trace

assert readline(allow_nothing=True)==None, "Internal error: TeX sends extra line"
do_run_error_finish=False


