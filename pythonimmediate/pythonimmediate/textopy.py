#!/bin/python3
"""
======== TeX-to-Py half ========

receive commands from TeX, then execute it here
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



#debug_file=open(Path(tempfile.gettempdir())/"pythonimmediate_debug_textopy.txt", "w", encoding='u8', buffering=2)
#debug=functools.partial(print, file=debug_file, flush=True)
debug=lambda *args, **kwargs: None



expansion_only_can_call_Python=False  # normally. May be different in LuaTeX etc.
from .engine import Engine, default_engine, ParentProcessEngine



pythonimmediate: Any
import pythonimmediate  # type: ignore

pythonimmediate.debugging=True
pythonimmediate.debug=debug

FunctionType = typing.TypeVar("FunctionType", bound=Callable)

def export_function_to_module(f: FunctionType)->FunctionType:
	"""
	the functions decorated with this decorator are accessible from user code with

	import pythonimmediate
	pythonimmediate.⟨function name⟩(...)
	"""
	setattr(pythonimmediate, f.__name__, f)
	return f

def send_raw(s: str, engine: Engine)->None:
	engine.write(s.encode('u8'))

def send_finish(s: str, engine: Engine)->None:
	engine.check_not_finished()
	engine.action_done=True
	assert s.endswith("\n")
	send_raw(s, engine=engine)


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

def substitute_private(code: str)->str:
	return (code
		  #.replace("\n", ' ')  # because there are comments in code, cannot
		  .replace("__", "_" + "pythonimmediate" + "_")
		 )

def send_bootstrap_code(engine: Engine)->None:
	send_raw(surround_delimiter(substitute_private(bootstrap_code)), engine=engine)

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

\cs_new_protected:Npn \pythonimmediatecontinuenoarg {
	\pythonimmediatecontinue {}
}

% internal function. Just send an arbitrary block of data to Python.
\cs_new_protected:Npn \__send_block:e #1 {
	\immediate\write \__write_file {
		#1 ^^J
		pythonimm?""" + '"""' + r"""?'''?  % following character will be newline
	}
}

\cs_new_protected:Npn \__send_block:n #1 {
	\__send_block:e {\unexpanded{#1}}
}

\AtEndDocument{
	\immediate\write \__write_file {r}
}
""")


# ========

# when 'i⟨string⟩' is sent from TeX to Python, the function with index ⟨string⟩ in this dict is called
TeX_handlers: Dict[str, Callable[[Engine], None]]={}

TeXToPyObjectType=Optional[str]

def run_main_loop(engine: Engine)->TeXToPyObjectType:
	while True:
		line=readline(engine=engine)
		if not line: return None

		if line[0]=="i":
			TeX_handlers[line[1:]](engine)
		elif line[0]=="r":
			return line[1:]
		else:
			raise RuntimeError("Internal error: unexpected line "+line)

def run_main_loop_get_return_one(engine: Engine)->str:
	line=readline(engine=engine)
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
def run_block_finish(block: str, engine: Engine=  default_engine)->None:
	send_finish("block\n" + surround_delimiter(block), engine=engine)


@user_documentation
@export_function_to_module
def execute(block: str, engine: Engine)->None:
	"""
	Run a block of \TeX\ code (might consist of multiple lines).
	Catcode-changing commands are allowed inside.

	A simple example is |pythonimmediate.run_block_local('123')| which simply typesets |123|.

	A more complicated example is |pythonimmediate.run_block_local(r'\verb+%+')|.
	"""
	run_block_local(block, engine=engine)

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




do_run_error_finish=True





user_scope: Dict[str, Any]={}  # consist of user's local variables etc.

def readline(engine: Engine)->str:
	line=engine.read().decode('u8')
	if not line:
		sys.stderr.write("\n\nTraceback (most recent call last):\n")
		traceback.print_stack(file=sys.stderr)
		sys.stderr.write("RuntimeError: Fatal irrecoverable TeX error\n\n")
		os._exit(1)


	assert line[-1]=='\n'
	line=line[:-1]
	debug("======== saw line", line)
	return line

block_delimiter: str="pythonimm?\"\"\"?'''?"

def read_block(engine: Engine)->str:
	"""
	Internal function to read one block sent from \TeX\ (including the final delimiter line,
	but the delimiter line is not returned)
	"""
	lines: List[str]=[]
	while True:
		line=readline(engine=engine)
		if line==block_delimiter:
			return '\n'.join(lines)
		else:
			lines.append(line)


@export_function_to_module
class NToken(ABC):
	"""
	Represent a possibly-notexpanded token.
	For convenience, a notexpanded token is called a blue token.
	It's not always possible to determine the notexpanded status of a following token in the input stream.
	Remark: Token objects must be frozen.
	"""

	@abstractmethod
	def __str__(self)->str: ...

	@abstractmethod
	def repr1(self)->str: ...

	@property
	@abstractmethod
	def assignable(self)->bool: ...

	def assign(self, other: "NToken", engine: Engine=default_engine)->None:
		assert self.assignable
		NTokenList([T.let, self, C.other("="), C.space(' '), other]).execute(engine=engine)

	def assign_future(self, engine: Engine=  default_engine)->None:
		assert self.assignable
		futurelet_(PTTBalancedTokenList(BalancedTokenList([self.no_blue])), engine=engine)

	def assign_futurenext(self, engine: Engine=  default_engine)->None:
		assert self.assignable
		futureletnext_(PTTBalancedTokenList(BalancedTokenList([self.no_blue])), engine=engine)

	def meaning_str(self, engine: Engine=  default_engine)->str:
		"""
		get the meaning of this token as a string.
		"""
		return NTokenList([T.meaning, self]).expand_x(engine=engine).str()

	@property
	@abstractmethod
	def blue(self)->"BlueToken": ...

	@property
	@abstractmethod
	def no_blue(self)->"Token": ...

	def meaning_equal(self, other: "Token", engine: Engine=  default_engine)->bool:
		return NTokenList([T.ifx, self, other, Catcode.other("1"), T["else"], Catcode.other("0"), T.fi]).expand_x(engine=engine).bool()

	def str(self)->str:
		"""
		self must represent a character of a TeX string. (i.e. equal to itself when detokenized)
		return the string content.

		default implementation below. Not necessarily correct.
		"""
		raise ValueError("Token does not represent a string!")

	def degree(self)->int:
		"""
		return the imbalance degree for this token ({ -> 1, } -> -1, everything else -> 0)

		default implementation below. Not necessarily correct.
		"""
		return 0


@export_function_to_module
class Token(NToken):
	"""
	Represent a TeX token, excluding the notexpanded possibility.
	See also documentation of NToken.
	"""

	@abstractmethod
	def serialize(self)->str: ...

	def value(self, engine: Engine=  default_engine)->"BalancedTokenList":
		"""
		given self is a TokenList variable, return the content.
		"""
		return BalancedTokenList([self]).expand_o(engine=engine)

	def value_str(self, engine: Engine=  default_engine)->str:
		"""
		given self is a str variable, return the content.
		"""
		return self.value(engine=engine).str()

	@property
	def blue(self)->"BlueToken": return BlueToken(self)

	@property
	def no_blue(self)->"Token": return self

	def __repr__(self)->str:
		return f"<Token: {self.repr1()}>"

	@staticmethod
	def deserialize(s: str)->"Token":
		t=TokenList.deserialize(s)
		assert len(t)==1
		return t[0]

	@staticmethod
	def get_next(engine: Engine=  default_engine)->"Token":
		"""
		Get the following token.

		Note: in LaTeX3 versions without the commit |https://github.com/latex3/latex3/commit/24f7188904d6|
		sometimes this may error out.

		Note: because of the internal implementation of |\peek_analysis_map_inline:n|, this may
		tokenize up to 2 tokens ahead (including the returned token),
		as well as occasionally return the wrong token in unavoidable cases.
		"""
		return Token.deserialize(str(get_next_(engine=engine)[0]))

	@staticmethod
	def peek_next(engine: Engine=  default_engine)->"Token":
		"""
		Get the following token without removing it from the input stream.

		Equivalent to get_next() then put_next() immediately. See documentation of get_next() for some notes.
		"""
		t=Token.get_next(engine=engine)
		t.put_next(engine=engine)
		return t

	def put_next(self, engine: Engine=  default_engine)->None:
		d=self.degree()
		if d==0:
			BalancedTokenList([self]).put_next(engine=engine)
		else:
			assert isinstance(self, CharacterToken)
			if d==1:
				put_next_bgroup(PTTInt(self.index), engine=engine)
			else:
				assert d==-1
				put_next_egroup(PTTInt(self.index), engine=engine)






"""
TeX code for serializing and deserializing a token list.
Convert a token list from/to a string.
"""


mark_bootstrap(
r"""
\precattl_exec:n {

% here #1 is the target token list to store the result to, #2 is a string with the final '.'.
\cs_new_protected:Npn \__tldeserialize_dot:Nn #1 #2 {
	\begingroup
		\tl_gset:Nn \__gtmp {#2}
		\tl_greplace_all:Nnn \__gtmp {~} {\cO\ }

		\def \start ##1 { \csname ##1 \endcsname }

		\def \^ ##1 ##2        { \csname ##1 \expandafter \expandafter \expandafter \endcsname \char_generate:nn {`##2-64} {12} }
		\def \> ##1 ##2 \cO\   { \csname ##1 \endcsname ##2  \cU\  }
		\def \* ##1 ##2 \cO\  ##3 { \csname ##1 \endcsname ##2  \char_generate:nn {`##3-64} {12} }
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
		\tl_gset:Nx \__gtmp {\expandafter \start \__gtmp}
	\endgroup
	\tl_set_eq:NN #1 \__gtmp
}

"""

+

# callback will be called exactly once with the serialized result
# and, as usual, with nothing leftover following in the input stream

# the token itself can be gobbled or \edef-ed to discard it.
# if it's active outer or control sequence outer then gobble fails.
# if it's { or } then edef fails.
(

r"""

\cs_new_protected:Npn \__char_unchecked:nNnN #char #cat {
	\int_compare:nNnTF {
		\if #cat 1  1 \fi 
		\if #cat 2  1 \fi 
		0
	} = {0} {
		% it's neither 1 nor 2, can edef
		\tl_set:Nn \__process_after_edef { \__continue_after_edef {#char} #cat }
		\afterassignment \__process_after_edef
		\edef \__the_token
	} {
		% it's either 1 or 2
		% might not be able to edef, but can gobble
		\__process_gobble {#char} #cat
	}
}

\def \__frozen_relax_container { \cFrozenRelax }
\def \__null_cs_container { \cC{} }

%\edef \__endwrite_container { \noexpand \cEndwrite }
%\tl_if_eq:NnT \__endwrite_container { \cC{cEndwrite} } {
%	\errmessage { endwrite~token~not~supported }
%}

\cs_new:Npn \__prefix_escaper #1 {
	\int_compare:nNnT {`#1} < {33} { * }
}
\cs_new:Npn \__content_escaper #1 {
	\int_compare:nNnTF {`#1} < {33} { \cStr\  \char_generate:nn {`#1+64} {12} } {#1}
}

\cs_new_protected:Npn \__continue_after_edef #char #cat #callback {
	\token_if_eq_charcode:NNTF #cat 0 {
		\tl_if_eq:NNTF \__the_token \__frozen_relax_container {
			#callback {\cStr{ R }}
		} {
			\tl_if_eq:NNTF \__the_token \__null_cs_container {
				#callback {\cStr{ \\\  }}
			} {
				\tl_set:Nx \__name { \expandafter \cs_to_str:N \__the_token }
				\exp_args:Nx #callback {
					\str_map_function:NN \__name \__prefix_escaper
					\cStr\\
					\str_map_function:NN \__name \__content_escaper
					\cStr\  }
			}
		}
	} {
		\int_compare:nNnTF { #char } < {16} {
			\exp_args:Nx #callback { \cStr{^} #cat \char_generate:nn {#char+64} {12} }
		} {
			\exp_args:Nx #callback { #cat \expandafter \string \__the_token }
		}
	}
}
"""
.replace("#char", "#1")
.replace("#cat", "#2")
.replace("#callback", "#3")

+

r"""
\cs_new_protected:Npn \__process_gobble #char #cat #token #callback {
	\int_compare:nNnTF { #char } < {16} {
		\exp_args:Nx #callback { \cStr{^} #cat \char_generate:nn {#char+64} {12} }
	} {
		\exp_args:Nx #callback { #cat \expandafter \string #token }
	}
}
"""
.replace("#char", "#1")
.replace("#cat", "#2")
.replace("#token", "#3")
.replace("#callback", "#4")

).replace("__", "__tlserialize_")

+

r"""

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
		\__tlserialize_char_unchecked:nNnN {##2}##3{##1} \__tlserialize_callback
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


class ControlSequenceTokenMaker:
	"""
	shorthand to create control sequence objects in Python easier.
	"""
	def __init__(self, prefix: str)->None:
		self.prefix=prefix
	def __getattribute__(self, a: str)->"ControlSequenceToken":
		return ControlSequenceToken(object.__getattribute__(self, "prefix")+a)
	def __getitem__(self, a: str)->"ControlSequenceToken":
		return ControlSequenceToken(object.__getattribute__(self, "prefix")+a)


@export_function_to_module
@dataclass(repr=False, frozen=True)
class ControlSequenceToken(Token):
	make=typing.cast(ControlSequenceTokenMaker, None)  # some interference makes this incorrect. Manually assign below
	csname: str
	@property
	def assignable(self)->bool:
		return True
	def __str__(self)->str:
		if self.csname=="": return r"\csname\endcsname"
		return "\\"+self.csname

	def serialize(self)->str:
		return (
				"*"*sum(1 for x in self.csname if ord(x)<33) +
				"\\" +
				"".join(' '+chr(ord(x)+64) if ord(x)<33 else x   for x in self.csname)
				+ " ")

	def repr1(self)->str:
		return f"\\" + repr(self.csname.replace(' ', "␣"))[1:-1]


ControlSequenceToken.make=ControlSequenceTokenMaker("")

T=ControlSequenceToken.make
P=ControlSequenceTokenMaker("_pythonimmediate_")  # create private tokens

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

C=Catcode

@export_function_to_module
@dataclass(repr=False, frozen=True)  # must be frozen because bgroup and egroup below are reused
class CharacterToken(Token):
	index: int
	catcode: Catcode
	@property
	def chr(self)->str:
		return chr(self.index)
	def __post_init__(self)->None:
		assert isinstance(self.index, int)
		assert self.index>=0
		assert self.catcode.for_token
	def __str__(self)->str:
		return self.chr
	def serialize(self)->str:
		if self.index<0x10:
			return f"^{self.catcode.value:X}{chr(self.index+0x40)}"
		else:
			return f"{self.catcode.value:X}{self.chr}"
	def repr1(self)->str:
		cat=str(self.catcode.value).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
		return f"{repr(self.chr)[1:-1]}{cat}"
	@property
	def assignable(self)->bool:
		return self.catcode==Catcode.active
	def degree(self)->int:
		if self.catcode==Catcode.bgroup:
			return 1
		elif self.catcode==Catcode.egroup:
			return -1
		else:
			return 0
	def str(self)->str:
		catcode=Catcode.space if self.index==32 else Catcode.other
		if catcode!=self.catcode:
			raise ValueError("this CharacterToken does not represent a string!")
		return self.chr

class FrozenRelaxToken(Token):
	def __str__(self)->str:
		return r"\relax"
	def serialize(self)->str:
		return "R"
	def repr1(self)->str:
		return r"[frozen]\relax"
	@property
	def assignable(self)->bool:
		return False

frozen_relax_token=FrozenRelaxToken()
pythonimmediate.frozen_relax_token=frozen_relax_token

# other special tokens later...

bgroup=Catcode.bgroup("{")
egroup=Catcode.egroup("}")
space=Catcode.space(" ")



@export_function_to_module
@dataclass(frozen=True)
class BlueToken(NToken):
	token: Token

	@property
	def blue(self)->"BlueToken": return self

	@property
	def no_blue(self)->"Token": return self.token

	def __str__(self)->str: return str(self.token)

	def repr1(self)->str: return "notexpanded:"+self.token.repr1()

	@property
	def assignable(self)->bool: return self.token.assignable

	def put_next(self, engine: Engine=  default_engine)->None:
		put_next_blue(PTTBalancedTokenList(BalancedTokenList([self.token])), engine=engine)


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


TokenListType = typing.TypeVar("TokenListType", bound="TokenList")

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

	def put_next(self, engine: Engine=  default_engine)->None:
		for part in reversed(self.balanced_parts()): part.put_next(engine=engine)

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
	def from_string(cls: Type[TokenListType], s: str, get_catcode: Callable[[int], Catcode])->TokenListType:
		"""
		convert a string to a TokenList approximately.
		The tokenization algorithm is slightly different from TeX's in the following respect:

		* multiple spaces are collapsed to one space, but only if it has character code space (32).
		* spaces with character code different from space (32) after a control sequence is not ignored.
		* ^^ syntax are not supported. Use Python's escape syntax as usual.
		"""
		return cls(TokenList.iterable_from_string(s, get_catcode))

	@classmethod
	def e3(cls: Type[TokenListType], s: str)->TokenListType:
		"""
		approximate tokenizer in expl3 catcode, implemented in Python.
		refer to documentation of from_string() for details.
		"""
		return cls.from_string(s, lambda x: e3_catcode_table.get(x, Catcode.other))

	@classmethod
	def doc(cls: Type[TokenListType], s: str)->TokenListType:
		"""
		approximate tokenizer in document catcode, implemented in Python.
		refer to documentation of from_string() for details.
		"""
		return cls.from_string(s, lambda x: doc_catcode_table.get(x, Catcode.other))

	def serialize(self)->str:
		return "".join(t.serialize() for t in self)

	@classmethod
	def deserialize(cls: Type[TokenListType], data: str)->TokenListType:
		result: List[Token]=[]
		i=0
		while i<len(data):

			if data[i] in "\\>*":
				start=data.find("\\", i)
				pos=start+1
				csname=""
				for op in data[i:start]:
					if op==">":
						assert False
					elif op=="*":
						n=data.find(' ', pos)+2
						csname+=data[pos:n-2]+chr(ord(data[n-1])-64)
						pos=n
					else:
						assert False

				i=data.find(' ', pos)+1
				csname+=data[pos:i-1]
				result.append(ControlSequenceToken(csname))

			elif data[i]=="R":
				result.append(frozen_relax_token)
				i+=1
			elif data[i]=="^":
				result.append(CharacterToken(index=ord(data[i+2])-0x40, catcode=Catcode(int(data[i+1], 16))))
				i+=3
			else:
				result.append(CharacterToken(index=ord(data[i+1]), catcode=Catcode(int(data[i], 16))))
				i+=2
		return cls(result)

	def __repr__(self)->str:
		return '<' + type(self).__name__ + ': ' + ' '.join(t.repr1() for t in self) + '>'

	def execute(self, engine: Engine=  default_engine)->None:
		NTokenList(self).execute(engine=engine)

	def expand_x(self, engine: Engine=  default_engine)->"BalancedTokenList":
		return NTokenList(self).expand_x(engine=engine)

	def bool(self)->bool:
		return NTokenList(self).bool()

	def str(self)->str:
		return NTokenList(self).str()



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

	def expand_o(self, engine: Engine=  default_engine)->"BalancedTokenList":
		return BalancedTokenList(expand_o_(PTTBalancedTokenList(self), engine=engine)[0])  # type: ignore
	def expand_x(self, engine: Engine=  default_engine)->"BalancedTokenList":
		return BalancedTokenList(expand_x_(PTTBalancedTokenList(self), engine=engine)[0])  # type: ignore
	def execute(self, engine: Engine=  default_engine)->None:
		execute_(PTTBalancedTokenList(self), engine=engine)

	def put_next(self, engine: Engine=  default_engine)->None:
		put_next_tokenlist(PTTBalancedTokenList(self), engine=engine)

	@staticmethod
	def get_next(engine: Engine=  default_engine)->"BalancedTokenList":
		"""
		get an (undelimited) argument from the TeX input stream.
		"""
		return BalancedTokenList(get_argument_tokenlist_(engine=engine)[0])  # type: ignore

	def detokenize(self, engine: Engine=  default_engine)->str:
		return BalancedTokenList([T.detokenize, self]).expand_x(engine=engine).str()


if typing.TYPE_CHECKING:
	NTokenListBaseClass = collections.UserList[NToken]
else:  # Python 3.8 compatibility
	NTokenListBaseClass = collections.UserList

@export_function_to_module
class NTokenList(NTokenListBaseClass):
	@staticmethod
	def force_token_list(a: Iterable)->Iterable[NToken]:
		for x in a:
			if isinstance(x, NToken):
				yield x
			elif isinstance(x, Sequence):
				yield bgroup
				child=NTokenList(x)
				assert child.is_balanced()
				yield from child
				yield egroup
			else:
				raise RuntimeError(f"Cannot make NTokenList from object {x} of type {type(x)}")

	def __init__(self, a: Iterable=())->None:
		super().__init__(NTokenList.force_token_list(a))

	def is_balanced(self)->bool:
		return TokenList(self).is_balanced()  # a bit inefficient (need to construct a TokenList) but good enough

	def simple_parts(self)->List[Union[BalancedTokenList, Token, BlueToken]]:
		"""
		Split this NTokenList into a list of balanced non-blue parts, unbalanced {/} tokens, and blue tokens.
		"""
		parts: List[Union[TokenList, BlueToken]]=[TokenList()]
		for i in self:
			if isinstance(i, BlueToken):
				parts+=i, TokenList()
			else:
				assert isinstance(i, Token)
				last_part=parts[-1]
				assert isinstance(last_part, TokenList)
				last_part.append(i)
		result: List[Union[BalancedTokenList, Token, BlueToken]]=[]
		for large_part in parts:
			if isinstance(large_part, BlueToken):
				result.append(large_part)
			else:
				result+=large_part.balanced_parts()
		return result

	def put_next(self, engine: Engine=  default_engine)->None:
		for part in reversed(self.simple_parts()): part.put_next(engine=engine)
		
	def execute(self, engine: Engine=  default_engine)->None:
		"""
		Execute self.
		"""
		parts=self.simple_parts()
		if len(parts)==1:
			x=parts[0]
			if isinstance(x, BalancedTokenList):
				x.execute(engine=engine)
				return
		NTokenList([*self, T.pythonimmediatecontinue, []]).put_next(engine=engine)
		continue_until_passed_back()

	def expand_x(self, engine: Engine=  default_engine)->BalancedTokenList:
		"""
		x-expand self. The result must be balanced.
		"""
		NTokenList([T.edef, P.tmp, bgroup, *self, egroup]).execute(engine=engine)
		return BalancedTokenList([P.tmp]).expand_o(engine=engine)

	def str(self)->str:
		"""
		self must represent a TeX string. (i.e. equal to itself when detokenized)
		return the string content.
		"""
		return "".join(t.str() for t in self)

	def bool(self)->bool:
		s=self.str()
		return {"0": False, "1": True}[s]


class TeXToPyData(ABC):
	@staticmethod
	@abstractmethod
	def read(engine: Engine)->"TeXToPyData":
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
	def read(engine: Engine)->"TTPLine":
		return TTPLine(readline(engine=engine))

# some old commands e.g. \$, \^, \_, \~ require \set@display@protect to be robust.
# ~ needs to be redefined directly.
mark_bootstrap(
r"""
\precattl_exec:n {
	\cs_new_protected:Npn \__begingroup_setup_estr: {
		\begingroup
			\escapechar=-1~
			\cC{set@display@protect}
			\let  \cA\~  \relax
	}
}
""")

class TTPELine(TeXToPyData, str):
	"""
	Same as TTPEBlock, but for a single line only.
	"""
	send_code=r"\__begingroup_setup_estr: \immediate \write \__write_file {{ {} }} \endgroup".format
	send_code_var=r"\__begingroup_setup_estr: \immediate \write \__write_file {{ {} }} \endgroup".format
	@staticmethod
	def read(engine: Engine)->"TTPELine":
		return TTPELine(readline(engine=engine))

class TTPEmbeddedLine(TeXToPyData, str):
	@staticmethod
	def send_code(self)->str:
		raise RuntimeError("Must be manually handled")
	@staticmethod
	def send_code_var(self)->str:
		raise RuntimeError("Must be manually handled")
	@staticmethod
	def read(engine: Engine)->"TTPEmbeddedLine":
		raise RuntimeError("Must be manually handled")

class TTPBlock(TeXToPyData, str):
	send_code=r"\__send_block:n {{ {} }}".format
	send_code_var=r"\__send_block:V {}".format
	@staticmethod
	def read(engine: Engine)->"TTPBlock":
		return TTPBlock(read_block(engine=engine))

class TTPEBlock(TeXToPyData, str):
	"""
	A kind of argument that interprets "escaped string" and fully expand anything inside.
	For example, {\\} sends a single backslash to Python, {\{} sends a single '{' to Python.
	Done by fully expand the argument in \escapechar=-1 and convert it to a string.
	Additional precaution is needed, see the note above.
	"""
	send_code=r"\__begingroup_setup_estr: \__send_block:e {{ {} }} \endgroup".format
	send_code_var=r"\__begingroup_setup_estr: \__send_block:e {} \endgroup".format
	@staticmethod
	def read(engine: Engine)->"TTPEBlock":
		return TTPEBlock(read_block(engine=engine))

class TTPBalancedTokenList(TeXToPyData, BalancedTokenList):
	send_code=r"\__tlserialize_nodot:Nn \__tmp {{ {} }} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	send_code_var=r"\__tlserialize_nodot:NV \__tmp {} \immediate \write \__write_file {{\unexpanded\expandafter{{ \__tmp }}}}".format
	@staticmethod
	def read(engine: Engine)->"TTPBalancedTokenList":
		return TTPBalancedTokenList(BalancedTokenList.deserialize(readline(engine=engine)))


class PyToTeXData(ABC):
	@staticmethod
	@abstractmethod
	def read_code(var: str)->str:
		...
	@abstractmethod
	def write(self, engine: Engine)->None:
		...

@dataclass
class PTTVerbatimLine(PyToTeXData):
	"""
	Represents a line to be tokenized verbatim. Internally the |\readline| primitive is used, as such, any trailing spaces are stripped.
	The trailing newline is not included, i.e. it's read under |\endlinechar=-1|.
	"""
	data: str
	read_code=r"\__str_get:N {} ".format
	def write(self, engine: Engine)->None:
		assert "\n" not in self.data
		assert self.data.rstrip()==self.data, "Cannot send verbatim line with trailing spaces!"
		send_raw(self.data+"\n", engine=engine)

@dataclass
class PTTInt(PyToTeXData):
	data: int
	read_code=PTTVerbatimLine.read_code
	def write(self, engine: Engine)->None:
		PTTVerbatimLine(str(self.data)).write(engine=engine)

@dataclass
class PTTTeXLine(PyToTeXData):
	"""
	Represents a line to be tokenized in \TeX's current catcode regime.
	The trailing newline is not included, i.e. it's tokenized under |\endlinechar=-1|.
	"""
	data: str
	read_code=r"\ior_get:NN \__read_file {} ".format
	def write(self, engine: Engine)->None:
		assert "\n" not in self.data
		send_raw(self.data+"\n", engine=engine)

@dataclass
class PTTBlock(PyToTeXData):
	data: str
	read_code=r"\__read_block:N {}".format
	def write(self, engine: Engine)->None:
		send_raw(surround_delimiter(self.data), engine=engine)

@dataclass
class PTTBalancedTokenList(PyToTeXData):
	data: BalancedTokenList
	read_code=r"\__str_get:N {0}  \__tldeserialize_dot:NV {0} {0}".format
	def write(self, engine: Engine)->None:
		PTTVerbatimLine(self.data.serialize()+".").write(engine=engine)


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
	It should take some arguments plus a keyword argument `engine` and eventually (optionally) call one of the |_finish| functions.

	name: the macro name on the \TeX\ side. This should only consist of letter characters in |expl3| catcode regime.

	argtypes: list of argument types. If it's None it will be automatically deduced from the function |f|'s signature.

	Returns: some code (to be executed in |expl3| catcode regime) as explained above.
	"""
	if argtypes is None:
		argtypes=[p.annotation for p in inspect.signature(f).parameters.values()]
		argtypes=[t for t in argtypes if t!=Engine]
	if name is None: name=f.__name__

	if identifier is None: identifier=get_random_identifier()
	assert identifier not in TeX_handlers

	@functools.wraps(f)
	def g(engine: Engine)->None:
		assert argtypes is not None
		args=[argtype.read(engine=engine) for argtype in argtypes]


		old_action_done=engine.action_done

		engine.action_done=False
		try:
			f(*args, engine=engine)
		except:
			if engine.action_done:
				# error occurred after 'finish' is called, cannot signal the error to TeX, will just ignore (after printing out the traceback)...
				pass
			else:
				# TODO what should be done here? What if the error raised below is caught
				engine.action_done=True
			raise
		finally:
			if not engine.action_done:
				run_none_finish(engine=engine)
		
			engine.action_done=old_action_done


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
	"""
	define a TeX function with TeX name = f.__name__ that calls f().

	this does not define the specified function in any particular engine, just add them to the bootstrap_code.
		essert self.process is not None, "process is already closed!"
	"""
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
def py(code: TTPEBlock, engine: Engine)->None:
	pythonimmediate.run_block_finish(str(eval_with_linecache(code, user_scope))+"%", engine=engine)

@define_internal_handler
def pyfile(filename: TTPELine, engine: Engine)->None:
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

def run_code_redirect_print_TeX(f: Callable[[], Any], engine: Engine)->None:
	with io.StringIO() as t:
		with RedirectPrintTeX(t):
			result=f()
			if result is not None:
				t.write(str(result)+"%")
		content=t.getvalue()
		if content.endswith("\n"):
			content=content[:-1]
		elif not content:
			run_none_finish(engine=engine)
			return
		else:
			#content+=r"\empty"  # this works too
			content+="%"
		run_block_finish(content, engine=engine)

@define_internal_handler
def pyc(code: TTPEBlock, engine: Engine)->None:
	run_code_redirect_print_TeX(lambda: exec_with_linecache(code, user_scope), engine=engine)

@define_internal_handler
def pycq(code: TTPEBlock, engine: Engine)->None:
	with RedirectPrintTeX(None):
		exec_with_linecache(code, user_scope)
	run_none_finish(engine=engine)

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
		\exp_last_unbraced:Nx \__pycodex {{\__code} {\the\inputlineno} {
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
def __pycodex(code: TTPBlock, lineno_: TTPLine, filename: TTPLine, fileabspath: TTPLine, engine: Engine)->None:
	if not code: return

	lineno=int(lineno_)
	# find where the code comes from... (for easy meaningful traceback)
	target_filename: Optional[str] = None

	code_lines_normalized=normalize_lines(code.splitlines(keepends=True))

	for f in (fileabspath, filename):
		if not f: continue
		p=Path(f)
		if not p.is_file(): continue
		file_lines=p.read_text().splitlines(keepends=True)[lineno-len(code_lines_normalized)-1:lineno-1]
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
		run_block_finish(t.getvalue(), engine=engine)

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
	def __call__(self, *args: PyToTeXData, engine: Engine)->Optional[Tuple[TeXToPyData, ...]]: ...

class PythonCallTeXSyncFunctionType(PythonCallTeXFunctionType, Protocol):  # https://stackoverflow.com/questions/57658879/python-type-hint-for-callable-with-variable-number-of-str-same-type-arguments
	def __call__(self, *args: PyToTeXData, engine: Engine)->Tuple[TeXToPyData, ...]: ...


@dataclass(frozen=True)
class Python_call_TeX_data:
	TeX_code: str
	recursive: bool
	finish: bool
	sync: Optional[bool]

@dataclass(frozen=True)
class Python_call_TeX_extra:
	ptt_argtypes: Tuple[Type[PyToTeXData], ...]
	ttp_argtypes: Union[Type[TeXToPyData], Tuple[Type[TeXToPyData], ...]]

Python_call_TeX_defined: Dict[Python_call_TeX_data, Tuple[Python_call_TeX_extra, Callable]]={}

def Python_call_TeX_local(TeX_code: str, *, recursive: bool=True, sync: Optional[bool]=None, finish: bool=False)->Callable:
	data=Python_call_TeX_data(
			TeX_code=TeX_code, recursive=recursive, sync=sync, finish=finish
			)
	return Python_call_TeX_defined[data][1]

def build_Python_call_TeX(T: Type, TeX_code: str, *, recursive: bool=True, sync: Optional[bool]=None, finish: bool=False)->None:
	"""
	T has the form Callable[[T1, T2], Tuple[U1, U2]]
	where the Tx are subclasses of PyToTeXData and the Ux are subclasses of TeXToPyData

	The Tuple[...] can optionally be a single type, then it is almost equivalent to a tuple of one element
	It can also be None
	"""

	assert T.__origin__ == typing.Callable[[], None].__origin__  # type: ignore
	# might be typing.Callable or collections.abc.Callable depends on Python version
	data=Python_call_TeX_data(
			TeX_code=TeX_code, recursive=recursive, sync=sync, finish=finish
			)

	# T.__args__ consist of the argument types int

	Tx=T.__args__[:-1]
	assert Tx and Tx[-1]==Engine
	Tx=Tx[:-1]

	for Ti in Tx: assert issubclass(Ti, PyToTeXData)

	result_type: Any = T.__args__[-1]  # Tuple[U1, U2]
	ttp_argtypes: Union[Type[TeXToPyData], Tuple[Type[TeXToPyData], ...]]
	if result_type is type(None):
		ttp_argtypes = ()
	elif isinstance(result_type, type) and issubclass(result_type, TeXToPyData):
		# special case, return a single object instead of a tuple of length 1
		ttp_argtypes = result_type
	else:
		ttp_argtypes = result_type.__args__  # type: ignore

	extra=Python_call_TeX_extra(
			ptt_argtypes=Tx,
			ttp_argtypes=ttp_argtypes
			)  # type: ignore
	if data in Python_call_TeX_defined:
		assert Python_call_TeX_defined[data][0]==extra
	else:
		if  isinstance(ttp_argtypes, type) and issubclass(ttp_argtypes, TeXToPyData):
			# special case, return a single object instead of a tuple of length 1
			code, result1=define_Python_call_TeX(TeX_code=TeX_code, ptt_argtypes=[*extra.ptt_argtypes], ttp_argtypes=[ttp_argtypes],
																  recursive=recursive, sync=sync, finish=finish,
																  )
			def result(*args, engine: Engine):
				tmp=result1(*args, engine=engine)
				assert tmp is not None
				assert len(tmp)==1
				return tmp[0]
		else:

			for t in ttp_argtypes:
				assert issubclass(t, TeXToPyData)

			code, result=define_Python_call_TeX(TeX_code=TeX_code, ptt_argtypes=[*extra.ptt_argtypes], ttp_argtypes=[*ttp_argtypes],
																  recursive=recursive, sync=sync, finish=finish,
																  )
		mark_bootstrap(code)

		def result2(*args):
			engine=args[-1]
			assert isinstance(engine, Engine)
			return result(*args[:-1], engine=engine)
		Python_call_TeX_defined[data]=extra, result2

def scan_Python_call_TeX(sourcecode: str)->None:
	"""
	scan the file in filename for occurrences of typing.cast(T, Python_call_TeX_local(...)), then call build_Python_call_TeX(T, ...) for each occurrence.

	Don't use on untrusted code.
	"""
	import ast
	from copy import deepcopy
	for node in ast.walk(ast.parse(sourcecode, mode="exec")):
		try:
			if isinstance(node, ast.Call):
				if (
						isinstance(node.func, ast.Attribute) and
						isinstance(node.func.value, ast.Name) and
						node.func.value.id == "typing" and
						node.func.attr == "cast"
						):
					T = node.args[0]
					if isinstance(node.args[1], ast.Call):
						f_call = node.args[1]
						if isinstance(f_call.func, ast.Name):
							if f_call.func.id == "Python_call_TeX_local":
								f_call=deepcopy(f_call)
								assert isinstance(f_call.func, ast.Name)
								f_call.func.id="build_Python_call_TeX"
								f_call.args=[T]+f_call.args
								eval(compile(ast.Expression(body=f_call), "<string>", "eval"))
		except:
			print("======== error on line", node.lineno, "========", file=sys.stderr)
			raise

def define_Python_call_TeX(TeX_code: str, ptt_argtypes: List[Type[PyToTeXData]], ttp_argtypes: List[Type[TeXToPyData]],
						   *,
						   recursive: bool=True,
						   sync: Optional[bool]=None,
						   finish: bool=False,
						   )->Tuple[str, PythonCallTeXFunctionType]:
	r"""
	|TeX_code| should be some expl3 code that defines a function with name |%name%| that when called should:
		* run some \TeX\ code (which includes reading the arguments, if any)
		* do the following if |sync|:
			* send |r| to Python (equivalently write %sync%)
			* send whatever needed for the output (as in |ttp_argtypes|)
		* call |\__read_do_one_command:| iff not |finish|.

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

	finish: Include this if and only if |\__read_do_one_command:| is omitted.
		Normally this is not needed, but it can be used as a slight optimization; and it's needed internally to implement
		|run_none_finish| among others.
		For each TeX-call-Python layer, \emph{exactly one} |finish| call can be made. If the function itself doesn't call
		any |finish| call (which happens most of the time), then the wrapper will call |run_none_finish|.

	Return some TeX code to be executed, and a Python function object that when called will call the TeX function
	on the passed-in TeX engine and return the result.

	Note that the TeX_code must eventually be executed on the corresponding engine for the program to work correctly.

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

	def f(*args, engine: Engine)->Optional[Tuple[TeXToPyData, ...]]:
		assert len(args)==len(ptt_argtypes)

		# send function header
		engine.check_not_finished()
		if finish:
			engine.action_done=True
		send_raw(identifier+"\n", engine=engine)

		# send function args
		for arg, argtype in zip(args, ptt_argtypes):
			assert isinstance(arg, argtype)
			arg.write(engine=engine)

		if not sync: return None

		# wait for the result
		if recursive:
			result_=run_main_loop(engine=engine)
		else:
			result_=run_main_loop_get_return_one(engine=engine)

		result: List[TeXToPyData]=[]
		if TTPEmbeddedLine not in ttp_argtypes:
			assert not result_
		for argtype_ in ttp_argtypes:
			if argtype_==TTPEmbeddedLine:
				result.append(TTPEmbeddedLine(result_))
			else:
				result.append(argtype_.read(engine))
		return tuple(result)

	return TeX_code, f

scan_Python_call_TeX(inspect.getsource(sys.modules[__name__]))

def define_Python_call_TeX_local(*args, **kwargs)->PythonCallTeXFunctionType:
	"""
	used to define "local" handlers i.e. used by this library.
	The code will be included in mark_bootstrap().
	"""
	code, result=define_Python_call_TeX(*args, **kwargs)
	mark_bootstrap(code)
	return result

# essentially this is the same as the above, but just that the return type is guaranteed to be not None to satisfy type checkers
def define_Python_call_TeX_local_sync(*args, **kwargs)->PythonCallTeXSyncFunctionType:
	return define_Python_call_TeX_local(*args, **kwargs, sync=True)  # type: ignore

run_none_finish=define_Python_call_TeX_local(
r"""
\cs_new_eq:NN %name% \relax
""", [], [], finish=True, sync=False)


"""
|run_error_finish| is fatal to TeX, so we only run it when it's fatal to Python.

We want to make sure the Python traceback is printed strictly before run_error_finish() is called,
so that the Python traceback is not interleaved with TeX error messages.
"""
run_error_finish=define_Python_call_TeX_local(
r"""
\msg_new:nnn {pythonimmediate} {python-error} {Python~error.}
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\wlog{^^JPython~error~traceback:^^J\__data^^J}
    \msg_error:nn {pythonimmediate} {python-error}
}
""", [PTTBlock], [], finish=True, sync=False)


put_next_blue=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn \__put_next_blue_tmp {
	%optional_sync%
	\expandafter \__read_do_one_command: \noexpand
}
\cs_new_protected:Npn %name% {
	%read_arg0(\__target)%
	\expandafter \__put_next_blue_tmp \__target
}
"""
		, [PTTBalancedTokenList], [], recursive=False)


put_next_tokenlist=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn \__put_next_tmp {
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
\cs_new_protected:Npn \__get_next_callback #1 {
	\peek_analysis_map_break:n { \pythonimmediatecontinue {#1} }
}
\cs_new_protected:Npn %name% {
	\peek_analysis_map_inline:n {
		\__tlserialize_char_unchecked:nNnN {##2}##3{##1} \__get_next_callback
	}
}
""", [], [TTPEmbeddedLine], recursive=False)

put_next_bgroup=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__index)%
	\expandafter \expandafter \expandafter \pythonimmediatecontinuenoarg
		\char_generate:nn {\__index} {1}
}
""", [PTTInt], [], recursive=False)

put_next_egroup=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__index)%
	\expandafter \expandafter \expandafter \pythonimmediatecontinuenoarg
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
def run_tokenized_line_local(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True, engine: Engine=  default_engine)->None:
	check_line(line, braces=check_braces, newline=check_newline, continue_=(False if check_continue else None))
	run_tokenized_line_local_(PTTTeXLine(line), engine=engine)



@export_function_to_module
def run_tokenized_line_peek(line: str, *, check_braces: bool=True, check_newline: bool=True, check_continue: bool=True, engine: Engine=  default_engine)->str:
	check_line(line, braces=check_braces, newline=check_newline, continue_=(True if check_continue else None))
	return typing.cast(
			Callable[[PTTTeXLine, Engine], Tuple[TTPEmbeddedLine]],
			Python_call_TeX_local(
				r"""
				\cs_new_protected:Npn %name% {
					%read_arg0(\__data)%
					\__data
				}
				""")
			)(PTTTeXLine(line), engine)[0]


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
def run_block_local(block: str, engine: Engine=  default_engine)->None:
	run_block_local_(PTTBlock(block), engine=engine)

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

futurelet_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\expandafter \futurelet \__data \pythonimmediatecontinuenoarg
}
""", [PTTBalancedTokenList], [])

futureletnext_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% {
	%read_arg0(\__data)%
	\afterassignment \pythonimmediatecontinuenoarg \expandafter \futurelet \__data 
}
""", [PTTBalancedTokenList], [])

continue_until_passed_back_=define_Python_call_TeX_local_sync(
r"""
\cs_new_eq:NN %name% \relax
""", [], [TTPEmbeddedLine])

@export_function_to_module
def continue_until_passed_back_str(engine: Engine=  default_engine)->str:
	"""
	Usage:

	First put some tokens in the input stream that includes |\pythonimmediatecontinue{...}|
	(or |%sync% \__read_do_one_command:|), then call |continue_until_passed_back()|.

	The function will only return when the |\pythonimmediatecontinue| is called.
	"""
	return str(continue_until_passed_back_(engine=engine)[0])

@export_function_to_module
def continue_until_passed_back(engine: Engine=  default_engine)->None:
	"""
	Same as |continue_until_passed_back_str()| but nothing can be returned from TeX to Python.
	"""
	result=continue_until_passed_back_str()
	assert not result


@export_function_to_module
def expand_once(engine: Engine=  default_engine)->None:
	typing.cast(Callable[[Engine], None], Python_call_TeX_local(
		r"""
		\cs_new_protected:Npn %name% { \expandafter \pythonimmediatecontinuenoarg }
		""", recursive=False, sync=True))(engine)


@export_function_to_module
@user_documentation
def get_arg_str(engine: Engine=  default_engine)->str:
	"""
	Get a mandatory argument.
	"""
	return typing.cast(Callable[[Engine], TTPEmbeddedLine], Python_call_TeX_local(
		r"""
		\cs_new_protected:Npn %name% #1 {
			\immediate\write\__write_file { \unexpanded {
				r #1
			}}
			\__read_do_one_command:
		}
		""", recursive=False))(engine)

get_arg_estr_=define_Python_call_TeX_local_sync(
r"""
\cs_new_protected:Npn %name% #1 {
	%sync%
	%send_arg0(#1)%
	\__read_do_one_command:
}
""", [], [TTPEBlock], recursive=False)
@export_function_to_module
@user_documentation
def get_arg_estr(engine: Engine=  default_engine)->str:
	return str(get_arg_estr_(engine=engine)[0])


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
def get_optional_arg_str(engine: Engine=  default_engine)->Optional[str]:
	"""
	Get an optional argument.
	"""
	[result]=get_optional_argument_detokenized_(engine=engine)
	result_=str(result)
	if result_=="0": return None
	assert result_[0]=="1", result_
	return result_[1:]


get_optional_arg_estr_=define_Python_call_TeX_local_sync(
r"""
\NewDocumentCommand %name% {o} {
	%sync%
	\IfNoValueTF {#1} {
		%send_arg0(0)%
	} {
		%send_arg0(1 #1)%
	}
	\__read_do_one_command:
}
""", [], [TTPEBlock], recursive=False)

@export_function_to_module
@user_documentation
def get_optional_arg_estr(engine: Engine=  default_engine)->Optional[str]:
	[result]=get_optional_arg_estr_(engine=engine)
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
def get_verb_arg(engine: Engine=  default_engine)->str:
	"""
	Get a verbatim argument. Since it's verbatim, there's no worry of |#| being doubled,
	but it can only be used at top level.
	"""
	return str(get_verbatim_argument_(engine=engine)[0])

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
def get_multiline_verb_arg(engine: Engine=  default_engine)->str:
	"""
	Get a multi-line verbatim argument.
	"""
	return str(get_multiline_verbatim_argument_(engine=engine)[0])

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

def newcommand_(name: str, f: Callable, engine: Engine)->Callable:
	identifier=get_random_identifier()

	newcommand2(PTTVerbatimLine(name), PTTVerbatimLine(identifier), engine=engine)

	_code=define_TeX_call_Python(
			lambda engine: run_code_redirect_print_TeX(f, engine=engine),
			name, argtypes=[], identifier=identifier)
	# ignore _code, already executed something equivalent in the TeX command
	return f

def renewcommand_(name: str, f: Callable, engine: Engine)->Callable:
	identifier=get_random_identifier()

	renewcommand2(PTTVerbatimLine(name), PTTVerbatimLine(identifier), engine=engine)
	# TODO remove the redundant entry from TeX_handlers (although technically is not very necessary, just cause slight memory leak)
	#try: del TeX_handlers["u"+name]
	#except KeyError: pass

	_code=define_TeX_call_Python(
			lambda engine: run_code_redirect_print_TeX(f, engine=engine),
			name, argtypes=[], identifier=identifier)
	# ignore _code, already executed something equivalent in the TeX command
	return f

	

@export_function_to_module
def newcommand(x: Union[str, Callable, None]=None, f: Optional[Callable]=None, engine: Engine=  default_engine)->Callable:
	"""
	Define a new \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return newcommand(x, engine=engine)(f)
	if x is None: return newcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(newcommand_, x, engine=engine)
	return newcommand_(x.__name__, x, engine=engine)

@export_function_to_module
def renewcommand(x: Union[str, Callable, None]=None, f: Optional[Callable]=None, engine: Engine=  default_engine)->Callable:
	"""
	Redefine a \TeX\ command.
	If name is not provided, it's automatically deduced from the function.
	"""
	if f is not None: return renewcommand(x, engine=engine)(f)
	if x is None: return renewcommand  # weird design but okay (allow |@newcommand()| as well as |@newcommand|)
	if isinstance(x, str): return functools.partial(renewcommand_, x, engine=engine)
	return renewcommand_(x.__name__, x, engine=engine)


# ========

put_next_TeX_line=define_Python_call_TeX_local(
r"""
\cs_new_protected:Npn \__put_next_tmpa {
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
def put_next(arg: Union[str, Token, BalancedTokenList], engine: Engine=  default_engine)->None:
	"""
	Put some content forward in the input stream.

	arg: has type |str| (will be tokenized in the current catcode regime, must be a single line),
	or |BalancedTokenList|.
	"""
	if isinstance(arg, str): put_next_TeX_line(PTTTeXLine(arg), engine=engine)
	else: arg.put_next(engine=engine)



# TODO I wonder which one is faster. Need to benchmark...
@export_function_to_module
@user_documentation
def peek_next_meaning(engine: Engine=  default_engine)->str:
	"""
	Get the meaning of the following token, as a string, using the current |\escapechar|.
	
	This is recommended over |peek_next_token()| as it will not tokenize an extra token.

	It's undefined behavior if there's a newline (|\newlinechar| or |^^J|, the latter is OS-specific)
	in the meaning string.
	"""
	return typing.cast(Callable[[Engine], TTPEmbeddedLine], Python_call_TeX_local(
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
			""", recursive=False))(engine)


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



meaning_str_to_catcode: Dict[str, Catcode]={
		"begin-group character ": Catcode.bgroup,
		"end-group character ": Catcode.egroup,
		"math shift character ": Catcode.math,
		"alignment tab character ": Catcode.alignment,
		"macro parameter character ": Catcode.parameter,
		"superscript character ": Catcode.superscript,
		"subscript character ": Catcode.subscript,
		"blank space ": Catcode.space,
		"the letter ": Catcode.letter,
		"the character ": Catcode.other,
		}

def parse_meaning_str(s: str)->Optional[Tuple[Catcode, str]]:
	if s and s[:-1] in meaning_str_to_catcode:
		return meaning_str_to_catcode[s[:-1]], s[-1]
	return None

@export_function_to_module
@user_documentation
def peek_next_char(engine: Engine=  default_engine)->str:
	"""
	Get the character of the following token, or empty string if it's not a character.
	Will also return nonempty if the next token is an implicit character token.

	Uses peek_next_meaning() under the hood to get the meaning of the following token. See peek_next_meaning() for a warning on undefined behavior.
	"""

	#return str(peek_next_char_()[0])
	# too slow (marginally slower than peek_next_meaning)

	r=parse_meaning_str(peek_next_meaning())
	if r is None:
		return ""
	return r[1]

@export_function_to_module
def get_next_char(engine: Engine=  default_engine)->str:
	result=Token.get_next(engine=engine)
	assert isinstance(result, CharacterToken), "Next token is not a character!"
	return result.chr

# ========

def parent_process_main():
	try:
		engine=ParentProcessEngine()
		default_engine.set_engine(engine)
		send_bootstrap_code(engine=engine)
		run_main_loop(engine=engine)  # if this returns cleanly TeX has no error. Otherwise some readline() will reach eof and print out a stack trace
		assert not engine.read(), "Internal error: TeX sends extra line"

	except:
		# see also documentation of run_error_finish.
		sys.stderr.write("\n")
		traceback.print_exc(file=sys.stderr)

		if do_run_error_finish:
			engine.action_done=False  # force run it
			run_error_finish(PTTBlock("".join(traceback.format_exc())), engine=engine)

		os._exit(0)

