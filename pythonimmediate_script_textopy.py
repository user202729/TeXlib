#!/bin/python3
"""
======== TeX-to-Py half ========

receive commands from TeX, then execute it here
print() might go to TeX's stdout, or somewhere else
"""


#from __future__ import annotations
import sys
import os
import inspect
import contextlib
import io
import functools
from typing import Optional, Union, Callable, Any, Iterator, Protocol, Iterable, Sequence, Type, Tuple, List, Dict
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

expansion_only_can_call_Python=False  # normally. May be different in LuaTeX etc.

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


# as the name implies, this reads one "command" from Python side and execute it.
# the command might do additional tasks e.g. read more \TeX\ code.
#
# e.g. if `block' is read from the communication channel, run |\__run_block:|.

mark_bootstrap(
r"""
\cs_new_protected:Npn \__read_do_one_command: {
	\begingroup
		\endlinechar=-1~
		\readline \__read_file to \__line
		\expandafter
	\endgroup % also this will give an error instead of silently do nothing when command is invalid
		\csname __run_ \__line :\endcsname
}

% read documentation of |_peek| commands for details what this command does.
\cs_new_protected:Npn \pythonimmediatecontinue #1 {
	\immediate\write \__write_file {r #1}
	\__read_do_one_command:
}

% internal function. Just send an arbitrary block of data to Python.
% the block itself will not be expanded.
\cs_new_protected:Npn \__send_block:n #1 {
	\immediate\write \__write_file {\unexpanded{
		#1 ^^J
		pythonimm?""" + '"""' + """?'''?  % following character will be newline
	}}
}

\AtEndDocument{
	\immediate\write \__write_file {r}
}
""")


# ========

# when 'i⟨string⟩' is sent from TeX to Python, the function with index ⟨string⟩ in this dict is called
TeX_handlers: Dict[str, Callable[[], None]]={}

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




user_scope: Dict[str, Any]={}  # consist of user's local variables etc.

def readline()->str:
	line=raw_readline()
	if not line:
		print("\n\nTraceback (most recent call last):", file=sys.stderr)
		traceback.print_stack(file=sys.stderr)
		print("RuntimeError: Fatal irrecoverable TeX error\n\n", file=sys.stderr)
		os._exit(1)


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
	lines: List[str]=[]
	while True:
		line=readline()
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

	@staticmethod
	def get_next()->"Token":
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

	@staticmethod
	def peek_next()->"Token":
		"""
		Get the following token without removing it from the input stream.

		Equivalent to get_next() then put_next() immediately. See documentation of get_next() for some notes.
		"""
		line=str(peek_next_()[0])
		t=TokenList.deserialize(line)
		assert len(t)==1, (line, t)
		return t[0]

	def put_next(self)->None:
		d=self.degree()
		if d==0:
			BalancedTokenList([self]).put_next()
		else:
			assert isinstance(self, CharacterToken)
			if d==1:
				put_next_bgroup(PTTInt(self.index))
			else:
				assert d==-1
				put_next_egroup(PTTInt(self.index))

	def degree(self)->int:
		if isinstance(self, CharacterToken):
			if self.catcode==Catcode.bgroup:
				return 1
			elif self.catcode==Catcode.egroup:
				return -1
		return 0



"""
TeX code for serializing and deserializing a token list.
Convert a token list from/to a string.
"""


mark_bootstrap(
r"""
\RequirePackage{precattl}
\precattl_exec:n {

% here #1 is the target token list to store the result to, #2 is a string with the final '.'.
\cs_new_protected:Npn \__tldeserialize_dot:Nn #1 #2 {
	\begingroup
		\tl_set:Nn \__tmp {#2}
		\tl_replace_all:Nnn \__tmp {~} {\cO\ }

		\def \start ##1 { \csname ##1 \endcsname }

		\def \> ##1 ##2 \cO\   { \csname ##1 \endcsname ##2  \cU\  }
		\def \\ ##1 \cO\   ##2 { \expandafter \noexpand \csname ##1 \endcsname                                  \csname ##2 \endcsname }
		\def \1 ##1        ##2 { \char_generate:nn {`##1} {1}                                                   \csname ##2 \endcsname }
		\def \2 ##1        ##2 { \char_generate:nn {`##1} {2}                                                   \csname ##2 \endcsname }
		\def \3 ##1        ##2 { \char_generate:nn {`##1} {3}                                                   \csname ##2 \endcsname }
		\def \4 ##1        ##2 { \char_generate:nn {`##1} {4}                                                   \csname ##2 \endcsname }
		\def \6 ##1        ##2 { #### \char_generate:nn {`##1} {6}                                              \csname ##2 \endcsname }
		\def \7 ##1        ##2 { \char_generate:nn {`##1} {7}                                                   \csname ##2 \endcsname }
		\def \8 ##1        ##2 { \char_generate:nn {`##1} {8}                                                   \csname ##2 \endcsname }
		\def \A ##1        ##2 { \char_generate:nn {`##1} {10}                                                  \csname ##2 \endcsname }
		\def \B ##1        ##2 { \char_generate:nn {`##1} {11}                                                  \csname ##2 \endcsname }
		\def \C ##1        ##2 { \char_generate:nn {`##1} {12}                                                  \csname ##2 \endcsname }
		\def \D ##1        ##2 { \expandafter \expandafter \expandafter \noexpand \char_generate:nn {`##1} {13} \csname ##2 \endcsname }
		\def \R ##1            { \cFrozenRelax                                                                  \csname ##1 \endcsname }

		\let \. \empty

		\exp_args:NNNx
	\endgroup \tl_set:Nn #1 {\expandafter \start \__tmp}
}

\cs_new_protected:Npn \__tlserialize_char_unchecked:nnNN #1 #2 #3 #4 {
	% #1=token, #2=char code, #3=catcode, #4: callback (will be called exactly once and with nothing following the input stream)
	\int_compare:nNnTF {#2} = {-1} {
		% token is control sequence
		\tl_if_eq:onTF {#1} {\cFrozenRelax} {
			#4 {\cStr{ R }}
		} {
			\tl_if_eq:onTF {#1} { \cC{} } {
				#4 {\cStr{ \\\  }}
			} {
				\tl_set:Nx \__name { \expandafter \cs_to_str:N #1 }
				\exp_args:Nx #4 { \prg_replicate:nn {\str_count_spaces:N \__name} {>}  \cStr\\ \__name \cStr\  }
			}
		}
	} {
		% token is not control sequence
		% (hex catcode) (character) (or escape sequence with that character)
		\exp_args:Nx #4 { #3 \expandafter \string #1 }
	}
}

}

% deserialize as above but #2 does not end with '.'.
\cs_new_protected:Npn \__tldeserialize_nodot:Nn #1 #2 {
	\__tldeserialize_dot:Nn #1 {#2 .}
}

% serialize token list in #2 store to #1.
\cs_new_protected:Npn \__tlserialize_nodot_unchecked:Nn #1 #2 {
	\tl_build_begin:N #1
	\tl_set:Nn \__tlserialize_callback { \tl_build_put_right:Nn #1 }
	\tl_analysis_map_inline:nn {#2} {
		\__tlserialize_char_unchecked:nnNN {##1}{##2}##3 \__tlserialize_callback
	}
	\tl_build_end:N #1
}

% serialize token list in #2 store to #1. Call T or F branch depends on whether serialize is successful.
% #1 must be different from \__tlserialize_tmp.
\cs_new_protected:Npn \__tlserialize_nodot:NnTF #1 #2 {
	\__tlserialize_nodot_unchecked:Nn #1 {#2}
	\__tldeserialize_nodot:NV \__tlserialize_nodot_tmp #1

	\tl_if_eq:NnTF \__tlserialize_nodot_tmp {#2} % dangling
}

\cs_new_protected:Npn \__tlserialize_nodot:NnF #1 #2 {
	\__tlserialize_nodot:NnTF #1 {#2} {} % dangling
}

\cs_new_protected:Npn \__tlserialize_nodot:NnT #1 #2 #3 { \__tlserialize_nodot:NnTF #1 {#2} {#3} {} }

\msg_new:nnn {pythonimmediate} {cannot-serialize} {Token~list~cannot~be~serialized}

\cs_new_protected:Npn \__tlserialize_nodot:Nn #1 #2{
	\__tlserialize_nodot:NnF #1 {#2} {
		\msg_error:nn {pythonimmediate} {cannot-serialize}
	}
}

\cs_generate_variant:Nn \__tldeserialize_dot:Nn {NV}
\cs_generate_variant:Nn \__tldeserialize_nodot:Nn {NV}
\cs_generate_variant:Nn \__tlserialize_nodot:Nn {NV}
""")


@export_function_to_module
@dataclass(repr=False, frozen=True)
class ControlSequenceToken(Token):
	csname: str
	def __str__(self)->str:
		if self.csname=="": return r"\csname\endcsname"
		return "\\"+self.csname
	def serialize(self)->str:
		return ">"*self.csname.count(" ") + "\\" + self.csname + " "
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

	def __call__(self, ch: Union[str, int])->"CharacterToken":
		"""
		Shorthand:
		Catcode.letter("a") = Catcode.letter(97) = CharacterToken(index=97, catcode=Catcode.letter)
		"""
		if isinstance(ch, str): ch=ord(ch)
		return CharacterToken(ch, self)

@export_function_to_module
@dataclass(repr=False, frozen=True)  # must be frozen because bgroup and egroup below are reused
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

bgroup=Catcode.bgroup("{")
egroup=Catcode.egroup("}")
space=Catcode.space(" ")


doc_catcode_table: Dict[int, Catcode]={}
doc_catcode_table[ord("{")]=Catcode.begin_group
doc_catcode_table[ord("}")]=Catcode.end_group
doc_catcode_table[ord("$")]=Catcode.math_toggle
doc_catcode_table[ord("&")]=Catcode.alignment
doc_catcode_table[ord("#")]=Catcode.parameter
doc_catcode_table[ord("^")]=Catcode.math_superscript
doc_catcode_table[ord("_")]=Catcode.math_subscript
doc_catcode_table[ord(" ")]=Catcode.space
doc_catcode_table[ord("~")]=Catcode.active
for ch in range(ord('a'), ord('z')+1): doc_catcode_table[ch]=Catcode.letter
for ch in range(ord('A'), ord('Z')+1): doc_catcode_table[ch]=Catcode.letter
doc_catcode_table[ord("\\")]=Catcode.escape
doc_catcode_table[ord("%")]=Catcode.comment

e3_catcode_table=dict(doc_catcode_table)
e3_catcode_table[ord("_")]=Catcode.letter
e3_catcode_table[ord(":")]=Catcode.letter
e3_catcode_table[ord(" ")]=Catcode.ignored
e3_catcode_table[ord("~")]=Catcode.space


T = typing.TypeVar("T", bound="TokenList")

if typing.TYPE_CHECKING:
	TokenListBaseClass = collections.UserList[Token]
else:  # Python 3.8 compatibility
	TokenListBaseClass = collections.UserList

@export_function_to_module
class TokenList(TokenListBaseClass):
	@staticmethod
	def force_token_list(a: Iterable)->Iterable[Token]:
		for x in a:
			if isinstance(x, Token):
				yield x
			elif isinstance(x, Sequence):
				yield bgroup
				child=BalancedTokenList(x)
				assert child.is_balanced()
				yield from child
				yield egroup
			else:
				raise RuntimeError(f"Cannot make TokenList from object {x} of type {type(x)}")

	def is_balanced(self)->bool:
		"""
		check if this is balanced.
		"""
		degree=0
		for x in self:
			degree+=x.degree()
			if degree<0: return False
		return degree==0

	def check_balanced(self)->None:
		"""
		ensure that this is balanced.
		"""
		if not self.is_balanced():
			raise ValueError("Token list is not balanced")

	def balanced_parts(self)->"List[Union[BalancedTokenList, Token]]":
		"""
		split this TokenList into a list of balanced parts and unbalanced {/}tokens
		"""
		degree=0
		min_degree=0, 0
		for i, token in enumerate(self):
			degree+=token.degree()
			min_degree=min(min_degree, (degree, i+1))
		min_degree_pos=min_degree[1]

		left_half: List[Union[BalancedTokenList, Token]]=[]
		degree=0
		last_pos=0
		for i in range(min_degree_pos):
			d=self[i].degree()
			degree+=d
			if degree<0:
				degree=0
				if last_pos!=i:
					left_half.append(BalancedTokenList(self[last_pos:i]))
				left_half.append(self[i])
				last_pos=i+1
		if min_degree_pos!=last_pos:
			left_half.append(BalancedTokenList(self[last_pos:min_degree_pos]))

		right_half: List[Union[BalancedTokenList, Token]]=[]
		degree=0
		last_pos=len(self)
		for i in range(len(self)-1, min_degree_pos-1, -1):
			d=self[i].degree()
			degree-=d
			if degree<0:
				degree=0
				if i+1!=last_pos:
					right_half.append(BalancedTokenList(self[i+1:last_pos]))
				right_half.append(self[i])
				last_pos=i
		if min_degree_pos!=last_pos:
			right_half.append(BalancedTokenList(self[min_degree_pos:last_pos]))

		return left_half+right_half[::-1]

	def put_next(self)->None:
		for part in reversed(self.balanced_parts()): part.put_next()

	@property
	def balanced(self)->"BalancedTokenList":
		"""
		return a BalancedTokenList containing the content of this object.
		it must be balanced.
		"""
		return BalancedTokenList(self)

	def __init__(self, a: Iterable=())->None:
		super().__init__(TokenList.force_token_list(a))

	@staticmethod
	def iterable_from_string(s: str, get_catcode: Callable[[int], Catcode])->Iterable[Token]:
		"""
		refer to documentation of from_string() for details.
		"""
		i=0
		while i<len(s):
			ch=s[i]
			i+=1
			cat=get_catcode(ord(ch))
			if cat==Catcode.space:
				yield space
				# special case: collapse multiple spaces into one but only if character code is space
				if get_catcode(32) in (Catcode.space, Catcode.ignored):
					while i<len(s) and s[i]==' ':
						i+=1
			elif cat.for_token:
				yield cat(ch)
			elif cat==Catcode.ignored:
				continue
			else:
				assert cat==Catcode.escape, f"cannot create TokenList from string containing catcode {cat}"
				cat=get_catcode(ord(s[i]))
				if cat!=Catcode.letter:
					yield ControlSequenceToken(s[i])
					i+=1
				else:
					csname=s[i]
					i+=1
					while i<len(s) and get_catcode(ord(s[i]))==Catcode.letter:
						csname+=s[i]
						i+=1
					yield ControlSequenceToken(csname)
					# special case: remove spaces after control sequence but only if character code is space
					if get_catcode(32) in (Catcode.space, Catcode.ignored):
						while i<len(s) and s[i]==' ':
							i+=1

	@classmethod
	def from_string(cls: Type[T], s: str, get_catcode: Callable[[int], Catcode])->T:
		"""
		convert a string to a TokenList approximately.
		The tokenization algorithm is slightly different from TeX's in the following respect:

		* multiple spaces are collapsed to one space, but only if it has character code space (32).
		* spaces with character code different from space (32) after a control sequence is not ignored.
		* ^^ syntax are not supported. Use Python's escape syntax as usual.
		"""
		return cls(TokenList.iterable_from_string(s, get_catcode))

	@classmethod
	def e3(cls: Type[T], s: str)->T:
		"""
		approximate tokenizer in expl3 catcode, implemented in Python.
		refer to documentation of from_string() for details.
		"""
		return cls.from_string(s, lambda x: e3_catcode_table.get(x, Catcode.other))

	@classmethod
	def doc(cls: Type[T], s: str)->T:
		"""
		approximate tokenizer in document catcode, implemented in Python.
		refer to documentation of from_string() for details.
		"""
		return cls.from_string(s, lambda x: doc_catcode_table.get(x, Catcode.other))

	def serialize(self)->str:
		return "".join(t.serialize() for t in self)

	@classmethod
	def deserialize(cls: Type[T], data: str)->T:
		try:
			result=TokenList()
			i=0
			cs_skip_space_count=0
			while i<len(data):
				if data[i]==">":
					cs_skip_space_count+=1
					i+=1
				elif data[i]=="\\":
					j=data.index(' ', i+1)
					for __ in range(cs_skip_space_count):
						j=data.index(' ', j+1)
					cs_skip_space_count=0
					result.append(ControlSequenceToken(data[i+1:j]))
					i=j+1
				elif data[i]=="R":
					result.append(frozen_relax_token)
					i+=1
				else:
					result.append(CharacterToken(index=ord(data[i+1]), catcode=Catcode(int(data[i], 16))))
					i+=2
			return cls(result)
		except:
			print("error", repr(data))
			traceback.print_exc()
			raise

	def __repr__(self)->str:
		return '<' + type(self).__name__ + ': ' + ' '.join(t.repr1() for t in self) + '>'


@export_function_to_module
class BalancedTokenList(TokenList):
	"""
	Represents a balanced token list.
	Note that runtime checking is not strictly enforced,
	use `is_balanced()` method explicitly if you need to check.
	"""

	def __init__(self, a: Iterable=())->None:
		"""
		constructor. This must check for balanced-ness as balanced() method depends on this.
		"""
		super().__init__(a)
		self.check_balanced()

	def expand_o(self)->"TokenList":
		return TokenList(expand_o_(PTTBalancedTokenList(self))[0])  # type: ignore
	def expand_x(self)->"TokenList":
		return TokenList(expand_x_(PTTBalancedTokenList(self))[0])  # type: ignore
	def execute(self)->None:
		execute_(PTTBalancedTokenList(self))

	def put_next(self)->None:
		put_next_tokenlist(PTTBalancedTokenList(self))

	@staticmethod
	def get_next()->"BalancedTokenList":
		"""
		get an (undelimited) argument from the TeX input stream.
		"""
		return BalancedTokenList(get_argument_tokenlist_()[0])  # type: ignore





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
		return TTPLine(readline())

class TTPEmbeddedLine(TeXToPyData, str):
	@staticmethod
	def send_code(self):
		raise RuntimeError("Must be manually handled")
	@staticmethod
	def send_code_var(self):
		raise RuntimeError("Must be manually handled")
	@staticmethod
	def read()->"TTPEmbeddedLine":
		raise RuntimeError("Must be manually handled")




class TTPBlock(TeXToPyData, str):
	send_code=r"\__send_block:n {{ {} }}".format
	send_code_var=r"\__send_block:V {}".format
	@staticmethod
	def read()->"TTPBlock":
		return TTPBlock(read_block())

class TTPBalancedTokenList(TeXToPyData, TokenList):
	send_code=r"\__tlserialize_nodot:Nn \__tmp {{ {} }} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	send_code_var=r"\__tlserialize_nodot:NV \__tmp {} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	@staticmethod
	def read()->"TTPBalancedTokenList":
		return TTPBalancedTokenList(TokenList.deserialize(readline()))


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
	Represents a line to be tokenized verbatim. Internally the |\readline| primitive is used, as such, any trailing spaces are stripped.
	The trailing newline is not included, i.e. it's read under |\endlinechar=-1|.
	"""
	data: str
	read_code=r"\ior_str_get:NN \__read_file {} ".format
	def write(self)->None:
		assert "\n" not in self.data
		assert self.data.rstrip()==self.data, "Cannot send verbatim line with trailing spaces!"
		send_raw(self.data+"\n")

@dataclass
class PTTInt(PyToTeXData):
	data: int
	read_code=PTTVerbatimLine.read_code
	def write(self)->None:
		PTTVerbatimLine(str(self.data)).write()

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
	read_code=r"\__read_block:N {}".format
	def write(self)->None:
		send_raw(surround_delimiter(self.data))

@dataclass
class PTTBalancedTokenList(PyToTeXData):
	data: BalancedTokenList
	read_code=r"\ior_str_get:NN \__read_file {0}  \__tldeserialize_dot:NV {0} {0}".format
	def write(self)->None:
		PTTVerbatimLine(self.data.serialize()+".").write()


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


def define_TeX_call_Python(f: Callable[..., None], name: Optional[str]=None, argtypes: Optional[List[Type[TeXToPyData]]]=None, identifier: Optional[str]=None)->str:
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


		global action_done
		old_action_done=action_done

		action_done=False
		try:
			f(*args)
		except:
			if action_done:
				# error occurred after 'finish' is called, cannot signal the error to TeX, will just ignore (after printing out the traceback)...
				pass
			else:
				# TODO what should be done here? What if the error raised below is caught
				action_done=True
			raise
		finally:
			if not action_done:
				run_none_finish()
		
			action_done=old_action_done


	TeX_handlers[identifier]=g

	TeX_argspec = ""
	TeX_send_input_commands = ""
	for i, argtype in enumerate(argtypes):
		if isinstance(argtype, str):
			raise RuntimeError("string annotation or `from __future__ import annotations' not yet supported")
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

def exec_with_linecache(code: str, globals: Dict[str, Any])->None:
	exec_or_eval_with_linecache(code, globals, "exec")

def eval_with_linecache(code: str, globals: Dict[str, Any])->Any:
	return exec_or_eval_with_linecache(code, globals, "eval")


@define_internal_handler
def py(code: TTPBlock)->None:
	pythonimmediate.run_block_finish(str(eval_with_linecache(code, user_scope))+"%")

@define_internal_handler
def pyfile(filename: TTPLine)->None:
	with open(filename, "r") as f:
		source=f.read()
	exec(compile(source, filename, "exec"), user_scope)

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
\NewDocumentCommand\pycv{v}{\pyc{#1}}
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

def normalize_lines(lines: List[str])->List[str]:
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

#PythonCallTeXFunctionType=Callable[[PyToTeXData], Optional[Tuple[TeXToPyData, ...]]]

class PythonCallTeXFunctionType(Protocol):  # https://stackoverflow.com/questions/57658879/python-type-hint-for-callable-with-variable-number-of-str-same-type-arguments
	def __call__(self, *args: PyToTeXData)->Optional[Tuple[TeXToPyData, ...]]: ...

class PythonCallTeXSyncFunctionType(PythonCallTeXFunctionType, Protocol):  # https://stackoverflow.com/questions/57658879/python-type-hint-for-callable-with-variable-number-of-str-same-type-arguments
	def __call__(self, *args: PyToTeXData)->Tuple[TeXToPyData, ...]: ...

def define_Python_call_TeX(TeX_code: str, ptt_argtypes: List[Type[PyToTeXData]], ttp_argtypes: List[Type[TeXToPyData]],
						   *,
						   recursive: bool=True,
						   sync: Optional[bool]=None,
						   )->Tuple[str, PythonCallTeXFunctionType]:
	r"""
	|TeX_code| should be some expl3 code that defines a function with name |%name%| that when called should:
		* run some \TeX\ code (which includes reading the arguments, if any)
		* do the following if |sync|:
			* send |r| to Python (equivalently write %sync%)
			* send whatever needed for the output (as in |ttp_argtypes|)
		* call |\__read_do_one_command:|

		This is allowed to contain the following:
		* %name%: the name of the function to be defined as explained above.
		* %read_arg0(\var_name)%, %read_arg1(...)%: will be expanded to code that reads the input.
		* %send_arg0(...)%, %send_arg1(...)%: will be expanded to code that sends the content.
		* %send_arg0_var(\var_name)%, %send_arg1_var(...)%: will be expanded to code that sends the content in the variable.
		* %optional_sync%: expanded to code that writes |r| (to sync), if |sync| is True.

	ptt_argtypes: list of argument types to be sent from Python to TeX (i.e. input of the TeX function)

	ttp_argtypes: list of argument types to be sent from TeX to Python (i.e. output of the TeX function)

	recursive: whether the TeX_code might call another Python function. Default to True.
		It does not hurt to always specify True, but performance would be a bit slower.

	sync: whether the Python function need to wait for the TeX function to finish.
		Required if |ttp_argtypes| is not empty.
		This should be left to be the default None most of the time. (which will make it always sync if |debugging|,
		otherwise only sync if needed i.e. there's some output)

	Return some TeX_code to be executed, and a Python function object that when called will call the TeX function
	and return the result.

	Possible optimizations:
		* the |r| is not needed if not recursive and |ttp_argtypes| is nonempty
			(the output itself tells Python when the \TeX\ code finished)
		* the first line of the output may be on the same line as the |r| itself (done, use TTPEmbeddedLine type, although a bit hacky)
	"""
	if ttp_argtypes!=[]:
		assert sync!=False
		sync=True

	if sync is None:
		sync=pythonimmediate.debugging

		TeX_code=template_substitute(TeX_code, "%optional_sync%",
							   lambda _: r'\immediate\write\__write_file { r }' if sync else '',)

	TeX_code=template_substitute(TeX_code, "%sync%",
						   lambda _: r'\immediate\write\__write_file { r }' if sync else '', optional=True)

	assert sync is not None
	if ttp_argtypes: assert sync
	assert ttp_argtypes.count(TTPEmbeddedLine)<=1
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

	def f(*args)->Optional[Tuple[TeXToPyData, ...]]:
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

		result: List[TeXToPyData]=[]
		if TTPEmbeddedLine not in ttp_argtypes:
			assert not result_
		for argtype_ in ttp_argtypes:
			if argtype_==TTPEmbeddedLine:
				result.append(TTPEmbeddedLine(result_))
			else:
				result.append(argtype_.read())
		return tuple(result)

	return TeX_code, f

def define_Python_call_TeX_local(*args, **kwargs)->PythonCallTeXFunctionType:
	code, result=define_Python_call_TeX(*args, **kwargs)
	mark_bootstrap(code)
	return result

# essentially this is the same as the above, but just that the return type is guaranteed to be not None to satisfy type checkers
def define_Python_call_TeX_local_sync(*args, **kwargs)->PythonCallTeXSyncFunctionType:
	return define_Python_call_TeX_local(*args, **kwargs, sync=True)  # type: ignore


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
		, [PTTBalancedTokenList], [], recursive=False)

get_next_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__get_next_callback: #1 {
	\immediate\write \__write_file { r^^J #1 }
	\__read_do_one_command:
}

\cs_new_protected:Npn %name% {
	\peek_analysis_map_inline:n {
		\peek_analysis_map_break:n {
			\__tlserialize_char_unchecked:nnNN {##1}{##2}##3 \__get_next_callback:
		}
	}
}
""", [], [TTPLine], recursive=False)

put_next_bgroup=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__put_next_char_callback: {
	%sync%
	\__read_do_one_command:
}

\cs_new_protected:Npn %name% {
	%read_arg0(\__index)%
	\expandafter \expandafter \expandafter \__put_next_char_callback:
		\char_generate:nn {\__index} {1}
}
""", [PTTInt], [], recursive=False)

put_next_egroup=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__index)%
	\expandafter \expandafter \expandafter \__put_next_char_callback:
		\char_generate:nn {\__index} {2}
}
""", [PTTInt], [], recursive=False)


get_argument_tokenlist_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% #1 {
	%sync%
	%send_arg0(#1)%
	\__read_do_one_command:
}
""", [], [TTPBalancedTokenList], recursive=False)


run_tokenized_line_local_=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\__data
	%optional_sync%
	\__read_do_one_command:
}
""", [PTTTeXLine], [])

@export_function_to_module
def run_tokenized_line_local(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True)->None:
	check_line(line, braces=check_braces, newline=check_newline, continue_=(False if check_continue else None))
	run_tokenized_line_local_(PTTTeXLine(line))


run_tokenized_line_peek_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\__data
}
""", [PTTTeXLine], [TTPEmbeddedLine])

@export_function_to_module
def run_tokenized_line_peek(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True)->str:
	check_line(line, braces=check_braces, newline=check_newline, continue_=(True if check_continue else None))
	a=run_tokenized_line_peek_(PTTTeXLine(line))[0]
	assert isinstance(a, str)
	return str(a)


run_block_local_=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\begingroup \newlinechar=10~ \expandafter \endgroup
	\scantokens \expandafter{\__data}
	% trick described in https://tex.stackexchange.com/q/640274 to scantokens the code with \newlinechar=10

	%optional_sync%
	\__read_do_one_command:
}
""", [PTTBlock], [])

@export_function_to_module
def run_block_local(block: str)->None:
	run_block_local_(PTTBlock(block))
	
#mark_bootstrap(
#r"""
#\cs_new_protected:Npn \__run_blockcont: {
#	\__run_block:
#	\pythonimmediatecontinue {}
#}
#""")
#
#@export_function_to_module
#def run_block_local(block: str)->TeXToPyObjectType:
#	check_not_finished()
#	send_raw("blockcont\n" + surround_delimiter(block))
#	return run_main_loop()

expand_o_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\exp_args:NNV \tl_set:No \__data \__data
	%sync%
	%send_arg0_var(\__data)%
	\__read_do_one_command:
}
""", [PTTBalancedTokenList], [TTPBalancedTokenList], recursive=expansion_only_can_call_Python)

expand_x_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\tl_set:Nx \__data {\__data}
	%sync%
	%send_arg0_var(\__data)%
	\__read_do_one_command:
}
""", [PTTBalancedTokenList], [TTPBalancedTokenList], recursive=expansion_only_can_call_Python)

execute_=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\__data
	%optional_sync%
	\__read_do_one_command:
}
""", [PTTBalancedTokenList], [])

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
def get_arg_str()->str:
	"""
	Get a mandatory argument.
	"""
	return str(get_argument_detokenized_()[0])

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
def get_optional_arg_str()->Optional[str]:
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
def get_verb_arg()->str:
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
def get_multiline_verb_arg()->str:
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
def newcommand(x: Union[str, Callable, None]=None, f: Optional[Callable]=None)->Callable:
	"""
	Define a new \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return newcommand(x)(f)
	if x is None: return newcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(newcommand_, x)
	return newcommand_(x.__name__, x)

@export_function_to_module
def renewcommand(x: Union[str, Callable, None]=None, f: Optional[Callable]=None)->Callable:
	"""
	Redefine a \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return newcommand(x)(f)
	if x is None: return newcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(renewcommand_, x)
	return renewcommand_(x.__name__, x)


# ========

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
def put_next(arg: Union[str, Token, BalancedTokenList])->None:
	"""
	Put some content forward in the input stream.

	arg: has type |str| (will be tokenized in the current catcode regime, must be a single line),
	or |BalancedTokenList|.
	"""
	if isinstance(arg, str): put_next_TeX_line(PTTTeXLine(arg))
	else: arg.put_next()

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
			\__tlserialize_char_unchecked:nnNN {##1}{##2}##3 \__peek_next_callback: ##1 % (*)
		}
	}
}
""", [], [TTPLine], recursive=False)


peek_next_meaning_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn \__peek_next_meaning_callback: {

	\edef \__tmp {\meaning \__tmp}  % just in case |\__tmp| is outer, |\write| will not be able to handle it
	%\immediate\write \__write_file { r \unexpanded\expandafter{\__tmp} }
	\immediate\write \__write_file { r \__tmp }

	\__read_do_one_command:
}
\cs_new_protected:Npn %name% {
	\futurelet \__tmp \__peek_next_meaning_callback:
}
""", [], [TTPEmbeddedLine], recursive=False)
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


if 0:
	peek_next_char_=define_Python_call_TeX_local_sync(

	# first attempt. Slower than peek_next_meaning.
	r"""
	\cs_new_protected:Npn \__peek_next_char_callback: {
		\edef \__tmpb { \expandafter\str_item:nn\expandafter{\meaning \__tmp} {-1} }  % \expandafter just in case \__tmp is \outer
		\if \noexpand\__tmp \__tmpb  % is a character
			\immediate\write \__write_file { r^^J \__tmpb . }
		\else  % is not?
			\immediate\write \__write_file { r^^J }
		\fi
		\__read_do_one_command:
	}
	\cs_new_protected:Npn %name% {
		\futurelet \__tmp \__peek_next_char_callback:
	}
	"""

	# second attempt. Faster than before but still slower than peek_next_meaning.
	#r"""
	#\cs_new_protected:Npn %name% {
	#	\futurelet \__tmp \__peek_next_char_callback:
	#}
	#
	#\cs_new_protected:Npn \__peek_next_char_callback: {
	#	%\if \noexpand\__tmp \c_space_token  % there's also this case and that \__tmp is some TeX primitive conditional...
	#	\expandafter \__peek_next_char_callback_b: \meaning \__tmp \relax
	#}
	#
	#\cs_new_protected:Npn \__peek_next_char_callback_b: #1 #2 {
	#	\ifx #2 \relax
	#		\if \noexpand\__tmp #1  % is a character
	#			\immediate\write \__write_file { r^^J #1 }
	#		\else  % is not?
	#			\immediate\write \__write_file { r^^J }
	#		\fi
	#		\expandafter \__read_do_one_command:
	#	\else
	#		\expandafter \__peek_next_char_callback_b: \expandafter #2
	#	\fi
	#}
	#
	#"""

	, [], [TTPLine], recursive=False)


@export_function_to_module
@user_documentation
def peek_next_char()->str:
	"""
	Get the character of the following token, or empty string if it's not a character.
	Will also return nonempty if the next token is an implicit character token.

	Uses peek_next_meaning() under the hood to get the meaning of the following token. See peek_next_meaning() for a warning on undefined behavior.
	"""

	#return str(peek_next_char_()[0])
	# too slow (marginally slower than peek_next_meaning)

	s=peek_next_meaning()
	if s and s[:-1] in [
		"begin-group character ",
		"end-group character ",
		"math shift character ",
		"alignment tab character ",
		"macro parameter character ",
		"superscript character ",
		"subscript character ",
		"blank space ",
		"the letter ",
		"the character ",
		]: return s[-1]
	return ""

@export_function_to_module
def get_next_char()->str:
	result=Token.get_next()
	assert isinstance(result, CharacterToken), "Next token is not a character!"
	return result.chr

# ========

send_bootstrap_code()
run_main_loop()  # if this returns cleanly TeX has no error. Otherwise some readline() will reach eof and print out a stack trace
assert raw_readline()==None, "Internal error: TeX sends extra line"


