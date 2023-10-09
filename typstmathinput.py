# to run tests:
# pytest --doctest-modules typstmathinput.py

import tempfile
from pathlib import Path
import itertools
import subprocess
import shutil
import hashlib
import re
import typing
from typing import Dict, Union, Optional, MutableMapping
import atexit
from functools import lru_cache
import traceback
import textwrap
import sys
import unicodedata
from dataclasses import dataclass


standalone_mode=False

if "pytest" in sys.modules:
	from pythonimmediate.engine import default_engine
	assert default_engine.engine is None
	from pythonimmediate.engine import ChildProcessEngine
	default_engine.set_engine(ChildProcessEngine("pdftex"))
	from pythonimmediate import execute
	execute(r"""\ExplSyntaxOn""")
elif __name__=="__main__":
	standalone_mode=True

if not standalone_mode:
	import pythonimmediate
	from pythonimmediate import*
	from pythonimmediate import simple
	from pythonimmediate.engine import default_engine


debug_=lambda *args, **kwargs: None

if standalone_mode:
	cache_location=""
	cache_format="shelve"
	watch_template_change=False
else:
	execute(r"""
	\RequirePackage{l3keys2e}
	\keys_define:nn{typstmathinput}{
		cache-location.tl_set:N=\_typstmathinput_cache_location,
		cache-location.initial:n={},

		cache-format.choices:nn={ shelve,json }{
			\str_set:Nx \_typstmathinput_cache_format {\l_keys_choice_tl}
		},
		cache-format.initial:n = { shelve },


		watch-template-change.bool_set:N=\_typstmathinput_watch_template_change,
	}
	\ProcessKeysOptions{typstmathinput}
	""")
	P=ControlSequenceTokenMaker("_typstmathinput_")
	cache_location=P.cache_location.tl().expand_estr()
	cache_format=P.cache_format.tl().expand_estr()
	watch_template_change=P.watch_template_change.bool()

#	rewrite-at-begin.tl_set:N=\_typstmathinput_rewrite_at_begin,
#	rewrite-at-begin.initial:n={},
#rewrite_at_begin=P.rewrite_at_begin.tl().expand_estr()

@lru_cache(maxsize=1)
def initialize_tmpdir()->Path:
	tmpdir=Path(tempfile.gettempdir())/".typstmathinput-tmp"
	tmpdir.mkdir(exist_ok=True)
	return tmpdir

@lru_cache(maxsize=1)
def initialize_template()->str:
	tmpdir=initialize_tmpdir()
	template_file=Path(__file__).parent/"typstmathinput-template.typ"
	shutil.copy(template_file, tmpdir)
	template_hash=hashlib.sha256((tmpdir/template_file.name).read_bytes()).hexdigest()
	return template_hash

@lru_cache(maxsize=1)
def initialize_cache()->MutableMapping[str, str]:
	global cache_location
	if not cache_location:
		tmpdir=initialize_tmpdir()
		cache_location=str(tmpdir/"cache")
	cache: MutableMapping[str, str]
	if cache_format=="shelve":
		import shelve
		cache=shelve.open(cache_location)
	else:

		from collections import UserDict
		# implement a cache that writes to json at location cache_location
		import json
		class Cache(UserDict):
			def __init__(self, *args, **kwargs)->None:
				super().__init__(*args, **kwargs)
				self.load()
			def load(self)->None:
				# TODO handle the case of corrupted cache
				try: self.data=json.loads(Path(cache_location).read_text(encoding='u8'))
				except FileNotFoundError: pass
			def save(self)->None:
				self.data={k: self.data[k] for k in sorted(self.data.keys())}
				Path(cache_location).write_text(json.dumps(self.data, indent=0, ensure_ascii=False), encoding='u8')
			def __setitem__(self, key: str, value: str)->None:
				super().__setitem__(key, value)
				self.save()
			def __delitem__(self, key: str)->None:
				super().__delitem__(key)
				self.save()
		cache=Cache()

	if watch_template_change:
		template_hash_cache_key="_template_hash_"
		template_hash=initialize_template()
		if cache.get(template_hash_cache_key)!=template_hash:
			cache.clear()
			cache[template_hash_cache_key]=template_hash
	return cache


@dataclass(frozen=True)
class Input:
	s: str  # the formula. Must not start or end with "$", but the return value will be wrapped in \(...\) or similar
	extra_preamble: str
	def hash(self)->str:
		return hashlib.sha256((str(len(self.s)) + "|" + self.s + self.extra_preamble).encode('u8')).hexdigest()

def fix_line_count(a: str, b: int)->str:
	r"""
	Rewrite TeX code ``a`` such that it has exactly ``b`` newline characters.

	>>> fix_line_count("a", 3)
	'a%\n%\n%\n'
	"""
	missing=b-a.count('\n')
	assert missing>=0
	return a+'%\n'*missing

def typst_formulas_to_tex(l: list[str], extra_preamble: str)->list[str]:
	"""
	Pass multiple formulas to Typst to process.

	No caching is done.

	The preamble of those formulas must be the same.

	..seealso:: :func:`typst_formulas_to_tex_tolerant_cached`, :func:`typst_formulas_to_tex_tolerant_use_cache`.
	"""
	initialize_template()
	tmpdir=initialize_tmpdir()
	delimiter = "XXXtypstmathinput-delimiterXXX"
	with tempfile.NamedTemporaryFile(dir=tmpdir, prefix="", suffix=".typ", delete=False, mode="w") as f:
		n=Path(f.name)
		f.write(r"""
#import "typstmathinput-template.typ": equation_to_latex
""" + extra_preamble + r"""
#set page(width: 10000cm)
#raw("<start>""" + delimiter + r"""\n")
""" + # we do the above to avoid pdftotext removing spaces when they coincide with newlines

(r'#raw("\n' + delimiter + r'\n")').join(
r"""
#raw(equation_to_latex($""" + s + r"""$))
""" for s in l)
		  )
		# .replace(" ", "<SP>")

	def invalid_formula_error(errortext: str)->None:
		if len(l)==1:
			raise RuntimeError(f"Formula ${l[0]}$ is invalid: {errortext}")
		else:
			raise RuntimeError(f"Some formula is invalid: {errortext}")

	try:
		process=subprocess.run(["typst", "compile", n, n.with_suffix(".pdf")], cwd=tmpdir, stderr=subprocess.PIPE)
		if process.returncode!=0:
			try: errortext="\n"+process.stderr.decode('u8')
			except UnicodeDecodeError: errortext="\n"+repr(process.stderr)
			invalid_formula_error(errortext)
	finally: n.unlink(missing_ok=True)

	if not n.with_suffix(".pdf").is_file():
		invalid_formula_error("Typst finishes but does not provide PDF")

	try: subprocess.run(["pdftotext", n.with_suffix(".pdf")], cwd=tmpdir, check=True)
	finally: n.with_suffix(".pdf").unlink(missing_ok=True)

	try: result=n.with_suffix(".txt").read_text(encoding='u8').replace("\n", "").replace("\x0c", "")
	finally: n.with_suffix(".txt").unlink(missing_ok=True)
	
	result=unicodedata.normalize("NFC", result)

	result_=result.split(delimiter)
	assert result_, "Internal error, output PDF is empty?"
	if result_[0]!="<start>":
		raise RuntimeError(f"Preamble contain {result_[0].removesuffix('<start>')!r}, should be empty")
	del result_[0]
	assert len(result_)==len(l), "Internal error"
	return [s.strip() for s in result_]


formula_counter: int=0
total_formula_counter: int=0
pending_formulas: list[Input]=[]
pending_formulas_set: set[Input]=set()

def typst_formulas_to_tex_tolerant_cached(l: list[str], extra_preamble: str, *, print_only_if_error: bool=True)->bool:  # return whether it's successful
	"""
	No caching is done. Saves result to cache.

	:param extra_preamble: Obvious.
	:param print_only_if_error: Default to True. If this is False then on error it will raise an error.
	"""
	def pending_formulas_index(i: Input)->int:
		try: return pending_formulas.index(i)
		except ValueError: return -1
	debug_(f"+ process {len(l)} [{pending_formulas_index(Input(l[0], extra_preamble))} - {pending_formulas_index(Input(l[-1], extra_preamble))}]")
	result: Optional[List[str]]=None
	try:
		result=typst_formulas_to_tex(l, extra_preamble)
	except:
		# "binary search" for the first error location
		if len(l)==1:
			if print_only_if_error:
				debug_(" ↑ fail ×")
				traceback.print_exc()
				return False
			else: raise

	if result is None:  # we don't do this in except block to avoid making the traceback long
		if not typst_formulas_to_tex_tolerant_cached(l[:len(l)//2], extra_preamble, print_only_if_error=print_only_if_error): return False
		return typst_formulas_to_tex_tolerant_cached(l[len(l)//2:], extra_preamble, print_only_if_error=print_only_if_error)

	assert len(l)==len(result)
	cache=initialize_cache()
	for f, r in zip(l, result):
		cache[Input(f, extra_preamble).hash()]=r
	debug_(" ↑ success")
	return True

def typst_formulas_to_tex_tolerant_use_cache(l: list[str], extra_preamble: str)->Optional[list[str]]:
	r"""
	Given a list of Typst formulas with a preamble, return a list of converted TeX formulas.

	Do the most sensible thing: read from the cache, if it's not available then run Typst then store the result to cache.

	If an error happens, then raise the error.

	Uses :func:`preprocess_formula` under the hood.

	>>> typst_formulas_to_tex_tolerant_use_cache(["1²", "b'²", "abc", r"∤∤2\#", r'#`!!\def\abc#1{#1}`.text'], "#let abc=$a b$")
	['\\(1^{2}\\)', "\\(b'^{2}\\)", '\\(ab\\)', '\\(∤∤2\\#\\)', '\\(\\def\\abc#1{#1}\\)']
	>>> typst_formulas_to_tex_tolerant_use_cache(["1", "#?"], "")
	Traceback (most recent call last):
		...
	RuntimeError: Formula $#?$ is invalid: ...
	>>> typst_formulas_to_tex_tolerant_use_cache(["1"], "x")
	Traceback (most recent call last):
		...
	RuntimeError: Preamble contain 'x', should be empty
	"""
	cache=initialize_cache()
	inputs=[Input(preprocess_formula(x), extra_preamble) for x in l]
	remaining=[*{i: None for i in inputs if i.hash() not in cache}]
	if remaining:
		if not typst_formulas_to_tex_tolerant_cached([i.s for i in inputs], extra_preamble, print_only_if_error=False):
			return None
	return [cache[i.hash()] for i in inputs]

def fix_line_count_multiple(a: list[str], b: list[str])->list[str]:
	r"""
	See :func:`fix_line_count`.

		>>> fix_line_count_multiple(["a", "b"], ["a\n\n", "b\n\n\n"])
		['a%\n%\n', 'b%\n%\n%\n']

	:param a: List of code that should have line count fixed.
	:param b: List of code with correct line count.
		Note that unlike :func:`fix_line_count`, ``b`` is a list of code itself, not line-count integer values.
	:return: TeX code that is functionally the same as ``a``, but with line counts fixed.
	"""
	assert len(a)==len(b), (a, b)
	return [fix_line_count(a, b.count('\n')) for a, b in zip(a, b)]

def process_pending_formulas()->None:
	"""
	Process ``pending_formulas`` and store it to the cache to be used in the next run.
	"""
	# group pending_formulas by preamble
	key=lambda f: f.extra_preamble
	if pending_formulas:
		typeout("Typstmathinput has pending formulas. Rerun.")
	for k, g_ in itertools.groupby(sorted(pending_formulas, key=key), key=key):
		g=list(g_)
		debug_(f":: process {len(g)}")
		typst_formulas_to_tex_tolerant_cached([x.s for x in g], k)

atexit.register(process_pending_formulas)

def preprocess_formula(s: str)->str:
	"""
	Preprocess a formula before passing to Typst.

	>>> preprocess_formula("ab + c²³ + √d")
	'ab + c^(23) +  sqrt(d)'
	"""
	superscript: Dict[str, Union[str, int, None]] = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-="))
	subscript: Dict[str, Union[str, int, None]] = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-="))
	s = re.sub('[' + "".join(superscript) + ']+', lambda x: "^(" + x[0].translate(str.maketrans(superscript)) + ")" , s)
	s = re.sub('[' + "".join(subscript) + ']+', lambda x: "_(" + x[0].translate(str.maketrans(subscript)) + ")" , s)
	s = re.sub(r'√\s*\(', ' sqrt(', s)
	s = re.sub(r'√\s*(\d+|\w+)', r' sqrt(\1)', s)
	return s

enabled: set[str]=set()

def check_valid_delimiter(s: str)->str:
	r"""
	Check ``s`` is a valid value to be passed in ``\typstmathinputenable`` etc.
	and return the processed delimiter.

	>>> check_valid_delimiter("??")
	Traceback (most recent call last):
		...
	RuntimeError: '??' is not supported!
	>>> check_valid_delimiter(r"\$")
	'$'
	"""
	if len(s)==2 and s[0]=="\\": s=s[1]
	if not (len(s)==1 and (s=="$" or ord(s)>=0x80)):
		raise RuntimeError(f"'{s}' is not supported!")
	return s

def get_formulas_in_body_before_preprocess(body: str, delimiter: str)->list[str]:
	r"""
	>>> get_formulas_in_body_before_preprocess('a $1+2$ b $3+4²$', '$')
	['1+2', '3+4²']
	>>> get_formulas_in_body_before_preprocess(
	... r'''
	... $1$
	...	  \typstmathinputdisable{\$}
	... $2$
	...  \typstmathinputenable{\$}
	... $3$
	...	\typstmathinputdisable\$
	... $4$
	... \typstmathinputenable\$
	... ''', '$')
	['1', '3']
	>>> get_formulas_in_body_before_preprocess('$', '$')
	Traceback (most recent call last):
		...
	RuntimeError: Stray or commented-out $ in document!
	"""
	parts=re.split(r"\\typstmathinput(disable|enable)(\{?\\?.\}?)", body)
	assert len(parts)%3==1
	# parts should have the form ['<some text where delimiter is enabled>', 'disable', '\$',
	#    '<some text where delimiter is enabled>', 'enable', '\$', '<text...>]
	for i in range(1, len(parts), 6): assert parts[i]=="disable", (i, parts[i])
	for i in range(4, len(parts), 6): assert parts[i]=="enable", (i, parts[i])
	for i in range(2, len(parts), 3): assert check_valid_delimiter(strip_optional_braces(parts[i]))==delimiter, (i, parts[i])
	result=[]
	for i in range(0, len(parts), 6):
		parts2=parts[i].split(delimiter)
		if len(parts2)%2==0: raise RuntimeError(f"Stray or commented-out {delimiter} in document!")
		result+=parts2[1::2]
	return result

def rewrite_body(body: str, delimiter: str)->str:
	formulas=get_formulas_in_body_before_preprocess(body, delimiter)
	formulas_converted=typst_formulas_to_tex_tolerant_use_cache(formulas, extra_preamble)
	if formulas_converted is None:
		return r"\textbf{??}"
	cache=initialize_cache()
	parts=body.split(delimiter)
	parts[1::2] = fix_line_count_multiple(formulas_converted, parts[1::2])
	result="".join(parts)
	return result

extra_preamble: str=""

def run_standalone_mode()->None:
	r"""
	The script can be run as a standalone Python script in order to preprocess some TeX code.

	>>> import subprocess
	>>> subprocess.run(["python", "typstmathinput.py"], input=r"123 $4^56+7⁸⁹+f^\#$", stdout=subprocess.PIPE, text=True, encoding='u8').stdout
	'123 \\(4^{56}+7^{89}+f^{\\#}\\)'
	"""
	content=sys.stdin.read()
	delimiter="$"

	if "%%% original source code %%%" in content:
		r"""
		This is a little feature, where if the input has the format

			\csname @gobble\endcsname{  %%% original source code %%%

			<some code...>

			%%% end original source code, start generated code %%%
			}

			<some more code...>

		then only the code inside <some code...> will be processed.
		"""
		content=content.split("%%% end original source code, start generated code %%%", maxsplit=1
				)[0].split("%%% original source code %%%", maxsplit=1)[1].strip()
		sys.stdout.write(
				r"\csname @gobble\endcsname{  %%% original source code %%%" + '\n' +
				content + '\n' +
				r"%%% end original source code, start generated code %%%" + '\n' +
				r"}" + '\n' +
				rewrite_body(content, delimiter) + '\n' +
				r"%%% end generated code %%%" + '\n')
	else:
		sys.stdout.write(rewrite_body(content, delimiter))
	sys.exit()

if standalone_mode:
	run_standalone_mode()

def _end_to_end_test_raw(code: str)->str:
	r"""
	Helper function to launch a TeX process. Only used for testing purposes.

		>>> _end_to_end_test_raw(r"\documentclass{article}\begin{document}\pagenumbering{gobble}hello\end{document}")
		'hello'
	"""
	with tempfile.TemporaryDirectory(prefix="typstmathinput-test-") as tmpdir:
		with tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".tex", mode="w", encoding='u8', delete=False) as tmpfile:
			tmpfile.write(code)
			tmpfile.close()
			process=subprocess.Popen(["lualatex", "--recorder", "--shell-escape", "--jobname=output", tmpfile.name], stdin=subprocess.DEVNULL,
				  stdout=subprocess.PIPE, cwd=tmpdir)
			if process.wait(timeout=10)!=0:
				assert process.stdout
				raise RuntimeError("Error:\n"+process.stdout.read().decode('u8'))
			subprocess.run(["pdftotext", "output.pdf"], cwd=tmpdir, check=True)
			return (Path(tmpdir)/"output.txt").read_text(encoding='u8').replace("\x0c", "").strip()

def _end_to_end_test(body: str)->str:
	r"""
	>>> _end_to_end_test(r"hello world")
	'hello world'
	"""
	with tempfile.TemporaryDirectory(prefix="typstmathinput-test-") as tmpdir:
		return _end_to_end_test_raw(textwrap.dedent(r"""
				\documentclass{article}
				\usepackage{unicode-math}
				\usepackage[cache-location="""+str(Path(tmpdir)/"cache.json")+r""", cache-format=json]{typstmathinput}
				\begin{document}
				\pagenumbering{gobble}
				""") + body + '\n' + r"\end{document}")
	# we use unicode-math so the output symbols will be correct (maybe there's a better way, TODO)

def handle_formula()->None:
	r"""
	Function called when a formula is seen (not in rewrite mode).

	>>> _end_to_end_test(r'\typstmathinputenable{\$}${integral x² dif x\{}$')
	'{∫ 𝑥2 d𝑥{}'
	"""
	global total_formula_counter
	total_formula_counter += 1

	with group:  # we use the group to set the catcode temporarily
		# if catcode is already fixed, the function still works, although a bit more limited
		# (most frequent issue is probably that the braces inside must be balanced --
		# although this can be fixed by escaping the braces with minimal harm)
		catcode[" "]=catcode["\\"]=catcode["{"]=catcode["}"]=catcode["&"]=catcode["^"]=Catcode.other
		delimiter: BalancedTokenList=BalancedTokenList.get_next()
		s: str=BalancedTokenList([
			(Catcode.other(t.chr) if isinstance(t, CharacterToken) and t.catcode==Catcode.param else
				Catcode.other("\n") if t==T.par else t)
				for t in BalancedTokenList.get_until(delimiter, remove_braces=False)
			]).detokenize()

	s=preprocess_formula(s)

	input_=Input(s, extra_preamble)
	input_hash=input_.hash()
	cache=initialize_cache()
	tmp=cache.get(input_hash)
	if tmp is not None:
		debug_(f":: cached <{total_formula_counter}>")
		put_next_tokenized(tmp+"%")
	else:
		global formula_counter
		formula_counter+=1
		if formula_counter>=5:
			TokenList(r"\textbf{??}").execute()
			if input_ in pending_formulas_set:
				debug_(f":: already cached <{total_formula_counter}>")
			else:
				debug_(f":: add to pending {len(pending_formulas)} <{total_formula_counter}>")
				pending_formulas.append(input_)
				pending_formulas_set.add(input_)
		else:
			debug_(f":: one-shot process <{total_formula_counter}>")
			tmp_: str=typst_formulas_to_tex([s], input_.extra_preamble)[0]
			cache[input_hash]=tmp_
			put_next_tokenized(tmp_+"%")
handle_formula_identifier = add_handler(handle_formula)


def set_extra_preamble()->None:
	global extra_preamble
	extra_preamble=T.typstmathinputextrapreamble.str()

def add_extra_preamble()->None:
	global extra_preamble
	extra_preamble+=T.typstmathinputextrapreamble.str()

set_extra_preamble_identifier = add_handler(set_extra_preamble)
add_extra_preamble_identifier = add_handler(add_extra_preamble)
BalancedTokenList(r"""
\NewDocumentEnvironment{typstmathinputsetextrapreamble}{}{
	\saveenv\typstmathinputextrapreamble
}{
	\endsaveenv\pythonimmediatecallhandler{""" + set_extra_preamble_identifier + r"""}
}
\NewDocumentEnvironment{typstmathinputaddextrapreamble}{}{
	\saveenv\typstmathinputextrapreamble
}{
	\endsaveenv\pythonimmediatecallhandler{""" + add_extra_preamble_identifier + r"""}
}
""").execute()

@newcommand
def typstmathinputenable()->None:
	s: str=get_arg_str()
	s=check_valid_delimiter(s)
	if s in enabled:
		raise RuntimeError(f"'{s}' is already enabled!")
	enabled.add(s)

	if s=="$" or default_engine.is_unicode:
		if s=="$" and catcode[s]!=Catcode.math_toggle:
			raise RuntimeError("It seems that '$' has an unusual catcode?")
		catcode[s]=Catcode.active
		TokenList([r"\def", Catcode.active(s),
			 r"{\pythonimmediatecallhandler{"+handle_formula_identifier+r"}", Catcode.active(s), "}"]).execute()
	else:
		T[("_typstmathinput_backup_"+s).encode('u8')].set_eq(T[("u8:"+s).encode('u8')])
		TokenList([r"\def", T[("u8:"+s).encode('u8')],
			 r"{\pythonimmediatecallhandler{"+handle_formula_identifier+r"}{",
			 *map(Catcode.active, s.encode('u8')),
			 "}}"]).execute()


@newcommand
def typstmathinputdisable()->None:
	r"""
	>>> _end_to_end_test(r'\typstmathinputenable{\$}${integral x² dif x #1 \#}$\typstmathinputdisable{\$}$integral x² dif x$')
	'{∫ 𝑥2 d𝑥1#}𝑖𝑛𝑡𝑒𝑔𝑟𝑎𝑙𝑥2 𝑑𝑖𝑓𝑥'
	"""
	s: str=get_arg_str()
	s=check_valid_delimiter(s)
	if s not in enabled:
		raise RuntimeError(f"'{s}' is already disabled!")
	enabled.remove(s)

	if s=="$":
		catcode["$"]=Catcode.math_toggle

	if s=="$" or default_engine.is_unicode:
		catcode[s]=Catcode.math_toggle if s=="$" else Catcode.other
	else:
		T[("u8:"+s).encode('u8')].set_eq(T[("_typstmathinput_backup_"+s).encode('u8')])


T.typstmathinputtext.set_eq(T.text)
r"""
Alias ``\text{...}`` → ``\typstmathinputtext{...}``. User can redefine this function to customize the behavior.
"""



def in_preamble()->bool:
	# https://tex.stackexchange.com/questions/16295/how-does-one-detect-whether-one-is-in-the-preamble-or-not
	return not T["@onlypreamble"].meaning_eq(T["@notprerr"])

@newcommand
def typstmathinputrewrite()->str:
	r"""
	Will gobble the whole body, rewrite it, then scan the result.

	This is obviously faster than using raw ``\typstmathinputenable``.

	Not recommended because it will likely lose line number information and SyncTeX capacity.
	Consider using :func:`typstmathinputprepare` instead.

		>>> _end_to_end_test(r'\typstmathinputrewrite{\$}' + '\n' + r'${integral x² dif x #1 \#}$')
		'{∫ 𝑥2 d𝑥1#}'
	"""
	assert not in_preamble(), "Should not rewrite in preamble, will conflict with fastrecompile"
	s: str=get_arg_str()
	s=check_valid_delimiter(s)
	assert s not in enabled
	#execute(r'''
	#\AddToHook{begindocument/before} [typstmathinput] {
	#	\AddToHook{begindocument/end} [typstmathinput] {
	#		\_typstmathinput_rewrite_at_begin
	#	}
	#}
	#''')
	#@newcommand
	#def _typstmathinput_rewrite_at_begin()->None:
	lineno: int=T.inputlineno.int()
	path: str=T.currfileabspath.str()
	assert path, "Currently you must have --recorder flag and [abspath]currfile package"
	text=Path(path).read_text(encoding='u8')
	a=text.splitlines()
	assert r'\typstmathinputrewrite' in a[lineno-1]
	result=(
			"\n"*(lineno) +
			rewrite_body('\n'.join(a[lineno:]), s)
			+ r'\end{document}'  # just in case
	  )
	#Path("/tmp/c.tex").write_text(f"{result}")
	return result

@newcommand
def typstmathinputprepare()->Optional[str]:
	r"""
	Will gobble the whole body, extract the formulas, then on actual formulas look up the prepared result.

	Should be on a separate line.

	Use starred version to still use old Python-side ``$...$`` handling, use non-starred version to use TeX version (faster)

	>>> _end_to_end_test(r'''
	... \typstmathinputenable{\$}
	... \typstmathinputprepare{\$}
	... ${integral x² dif x #1 \#
	...
	... }$
	... ''')
	'{∫ 𝑥2 d𝑥1#}'
	>>> _end_to_end_test(r'''
	... \typstmathinputenable{\$}
	... \typstmathinputprepare*{\$}
	... ${integral x² dif x #1 \#
	...
	... }$
	... ''')
	'{∫ 𝑥2 d𝑥1#}'
	>>> _end_to_end_test(r'''
	... \typstmathinputenable{\$}
	... \typstmathinputprepare{\$}
	... \iffalse $error$ \fi
	... ''')
	Traceback (most recent call last):
		...
	RuntimeError: ...

	>>> _end_to_end_test(r'''
	... \typstmathinputenable{\$}
	... \typstmathinputprepare{\$}
	... \typstmathinputdisable{\$}
	... $error$
	... \typstmathinputenable{\$}
	... $integral x dif x$
	... ''')
	'𝑒𝑟𝑟𝑜𝑟 ∫ 𝑥 d𝑥'

	There's an optional argument, which can be used to write the TeX commands to define the formulas to a file.
	Put it after the ``*`` (if any) and before the mandatory argument (delimiter).
	"""
	assert not in_preamble(), "Should not prepare in preamble, will conflict with fastrecompile"
	starred: bool=peek_next_char()=="*"
	if starred: get_next_char()
	output_file: Optional[str]=get_optional_arg_estr()
	delimiter: str=get_arg_str()
	delimiter=check_valid_delimiter(delimiter)
	assert delimiter in enabled
	lineno: int=T.inputlineno.int()
	path: str=T.currfileabspath.str()
	assert path
	text=Path(path).read_text(encoding='u8')
	a=text.splitlines()
	assert r'\typstmathinputprepare' in a[lineno-1]
	body='\n'.join(a[lineno:])
	if starred:
		rewrite_body(body, delimiter)  # just populate the cache, discard the result
	else:
		formulas=sorted(set(get_formulas_in_body_before_preprocess(body, delimiter)))
		formulas_converted=typst_formulas_to_tex_tolerant_use_cache(formulas, extra_preamble)
		if formulas_converted is None:
			return r"\textbf{??}"

		# redefine $...$ to use TeX
		if delimiter=="$" or default_engine.is_unicode:
			delimiter_set_command=r'\catcode`' + '\\' + delimiter + r'\active\xdef' + delimiter
		else:
			delimiter_set_command=r'\expandafter\xdef\csname u8:\detokenize{' + delimiter + r'}\endcsname'
		delimiter_set_command+=r'{\csname _typstmathinput_handle_formula\endcsname}'
		content=(
			delimiter_set_command +
			textwrap.dedent((#TeX
			r"""
			\ExplSyntaxOn
			\providecommand\typstmathinputtext{\text}
			\providecommand\typstmathinputenable[1]{
				\catcode `#1 \active
			}
			\providecommand\typstmathinputdisable[1] {
				\catcode `#1 = """) + str((Catcode.math_toggle if delimiter=="$" else Catcode.other).value) +
					(#TeX
					r""" \relax
			}
			\protected\gdef \__handle_formula {
				\__handle_formula_a \empty
			}
			\protected\gdef \__set_handle_formula_delimiter #1 {
				\protected\long\gdef \__handle_formula_a ##1 #1 {
					\begingroup\expandafter\endgroup\csname __prepared)\detokenize\expandafter{##1}\endcsname
				}
			}
			\ExplSyntaxOff
			""").replace('__', '_typstmathinput_')) +
			r'\csname _typstmathinput_set_handle_formula_delimiter\endcsname{' + delimiter + '}' +
			r'\begingroup\long\def\\#1{\expandafter\gdef\csname _typstmathinput_prepared)\detokenize{#1}\endcsname}' + '\n' +
			"".join(
				r'\\{' + f + '}{' + fc + '}\n' for f, fc in zip(formulas, formulas_converted)
				)
			+ r'\endgroup'
			)

		if output_file:
			Path(output_file).write_text(content, encoding='u8')

		execute(content)

	return None


# handle_formula is first called to insert the \empty token
# handle_formula_a is called after it to grab the argument
# use \begingroup\expandafter\endgroup to raise an error if the formula is unexpected

#execute(r'\AtBeginDocument{\typstmathinputenable{◇}}')
