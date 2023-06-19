import tempfile
from pathlib import Path
import itertools
import subprocess
import shutil
import hashlib
import re
import typing
from typing import Dict, Union, Optional, MutableMapping
from pythonimmediate import*
from pythonimmediate import simple
from pythonimmediate.engine import default_engine
import atexit
from functools import lru_cache
import traceback

P=ControlSequenceTokenMaker("_typstmathinput_")

debug_=lambda *args, **kwargs: None

execute(r"""
\RequirePackage{l3keys2e}
\keys_define:nn{typstmathinput}{
	cache-location.tl_set:N=\_typstmathinput_cache_location,
	cache-location.initial:n={},

	cache-format.choices:nn={ shelve,json }{
		\str_set:Nx \_typstmathinput_cache_format {\l_keys_choice_tl}
	},
	cache-format.initial:n = { shelve },

	rewrite-at-begin.tl_set:N=\_typstmathinput_rewrite_at_begin,
	rewrite-at-begin.initial:n={},

	watch-template-change.bool_set:N=\_typstmathinput_watch_template_change,
}
\ProcessKeysOptions{typstmathinput}
""")
cache_location=P.cache_location.val().expand_estr()
cache_format=P.cache_format.val().expand_estr()
watch_template_change=P.watch_template_change.e3bool()
rewrite_at_begin=P.rewrite_at_begin.val().expand_estr()

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
				try: self.data=json.loads(Path(cache_location).read_text())
				except FileNotFoundError: pass
			def save(self)->None:
				self.data={k: self.data[k] for k in sorted(self.data.keys())}
				Path(cache_location).write_text(json.dumps(self.data, indent=0))
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

def typst_formulas_to_tex(l: list[str], extra_preamble: str)->list[str]:
	# no caching, preamble must be the same
	initialize_template()
	tmpdir=initialize_tmpdir()
	delimiter = "XXXtypstmathinput-delimiterXXX"
	with tempfile.NamedTemporaryFile(dir=tmpdir, prefix="", suffix=".typ", delete=False, mode="w") as f:
		n=Path(f.name)
		f.write(r"""
#import "typstmathinput-template.typ": equation_to_latex
""" + extra_preamble + r"""
#set page(width: 100cm)
""" +

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

	try: result=n.with_suffix(".txt").read_text().replace("\n", "").replace("\x0c", "")
	finally: n.with_suffix(".txt").unlink(missing_ok=True)

	result_=result.split(delimiter)
	assert len(result_)==len(l)
	return result_


formula_counter: int=0
total_formula_counter: int=0
pending_formulas: list[Input]=[]
pending_formulas_set: set[Input]=set()

def typst_formulas_to_tex_tolerant_cached(l: list[str], extra_preamble: str)->bool:  # return whether it's successful
	debug_(f"+ process {len(l)} [{pending_formulas.index(Input(l[0], extra_preamble))} - {pending_formulas.index(Input(l[-1], extra_preamble))}]")
	result: Optional[List[str]]=None
	try:
		result=typst_formulas_to_tex(l, extra_preamble)
	except:
		# "binary search" for the first error location
		if len(l)==1:
			debug_(" ↑ fail ×")
			traceback.print_exc()
			return False

	if result is None:  # we don't do this in except block to avoid making the traceback long
		if not typst_formulas_to_tex_tolerant_cached(l[:len(l)//2], extra_preamble): return False
		return typst_formulas_to_tex_tolerant_cached(l[len(l)//2:], extra_preamble)

	cache=initialize_cache()
	assert len(l)==len(result)
	for f, r in zip(l, result):
		cache[Input(f, extra_preamble).hash()]=r
	debug_(" ↑ success")
	return True

def process_pending_formulas()->None:
	# group pending_formulas by preamble
	key=lambda f: f.extra_preamble
	if pending_formulas:
		print("Typstmathinput has pending formulas. Rerun.")  # log reader will miss this unfortunately
	for k, g_ in itertools.groupby(sorted(pending_formulas, key=key), key=key):
		g=list(g_)
		debug_(f":: process {len(g)}")
		typst_formulas_to_tex_tolerant_cached([x.s for x in g], k)

atexit.register(process_pending_formulas)

def handle_formula(engine: "Engine")->None:
	global total_formula_counter
	total_formula_counter += 1

	with group:  # we use the group to set the catcode temporarily
		# if catcode is already fixed, the function still works, although a bit more limited
		# (most frequent issue is probably that the braces inside must be balanced --
		# although this can be fixed by escaping the braces with minimal harm)
		catcode[" "]=catcode["\\"]=catcode["{"]=catcode["}"]=catcode["&"]=catcode["^"]=Catcode.other
		delimiter: BalancedTokenList=BalancedTokenList.get_next()
		s: str=BalancedTokenList.get_until(delimiter, remove_braces=False).detokenize()
		# really bad hack here ><

	# preprocess it before passing to Typst
	superscript: Dict[str, Union[str, int, None]] = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-="))
	subscript: Dict[str, Union[str, int, None]] = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-="))
	s = re.sub('[' + "".join(superscript) + ']+', lambda x: "^(" + x[0].translate(str.maketrans(superscript)) + ")" , s)
	s = re.sub('[' + "".join(subscript) + ']+', lambda x: "_(" + x[0].translate(str.maketrans(subscript)) + ")" , s)
	s = re.sub(r'√\s*\(', ' sqrt(', s)
	s = re.sub(r'√\s*(\d+|\w+)', r' sqrt(\1)', s)

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

extra_preamble: str=""
def set_extra_preamble(engine: "Engine")->None:
	global extra_preamble
	extra_preamble=T.typstmathinputextrapreamble.val_str()


set_extra_preamble_identifier = add_handler(set_extra_preamble)
BalancedTokenList(r"""
\NewDocumentEnvironment{typstmathinputsetextrapreamble}{}{
	\saveenv\typstmathinputextrapreamble
}{
	\endsaveenv\pythonimmediatecallhandler{""" + set_extra_preamble_identifier + r"""}
}
""").execute()

enabled: set[str]=set()

def check_valid_delimiter(s: str)->str:
	if len(s)==2 and s[0]=="\\": s=s[1]
	if not (len(s)==1 and (s=="$" or ord(s)>=0x80)):
		raise RuntimeError(f"'{s}' is not supported!")
	return s

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


BalancedTokenList(r"""
				  \def\typstmathinputnormcat{\catcode `\| 12 \catcode `" 12 \relax}
""").execute()

#@newcommand
def typstmathinputnormcat()->None:
	"""
	Internal function.

	To be used inside a math environment. Avoid fancyvrb or csquotes causing trouble with active characters.
	"""
	#catcode["|"]=catcode['"']=Catcode.other
	pass

T.typstmathinputtext.set_eq(T.text)
r"""
Alias ``\text{...}`` → ``\typstmathinputtext{...}``. User can redefine this function to customize the behavior.
"""

if rewrite_at_begin:
	execute(r'''
	\AddToHook{begindocument/before} [typstmathinput] {
		\AddToHook{begindocument/end} [typstmathinput] {
			\_typstmathinput_rewrite_at_begin
		}
	}
	''')
	@newcommand
	def _typstmathinput_rewrite_at_begin()->None:
		T.inputlineno.int()
		text=Path(T.currfileabspath.val_str()).read_text()
		parts=text.split('\n\\begin{document}\n', maxsplit=1)
		assert len(parts)==2
		execute("\n"*(parts[0].count('\n')+2) +
		  rewrite_body(parts[1]))

else:
	execute(r'\AtBeginDocument{\typstmathinputenable{◇}}')
