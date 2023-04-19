import tempfile
from pathlib import Path
import itertools
import subprocess
import shutil
import hashlib
import re
import typing
from typing import Dict, Union
from pythonimmediate import*
from pythonimmediate.engine import default_engine
import shelve
import atexit

tmpdir=Path(tempfile.gettempdir())/".typstmathinput-tmp"
tmpdir.mkdir(exist_ok=True)
template_file=Path(__file__).parent/"typstmathinput-template.typ"
shutil.copy(template_file, tmpdir)
template_hash=hashlib.sha256((tmpdir/template_file.name).read_bytes()).digest()

cache=shelve.open(str(tmpdir/"cache"))
template_hash_cache_key="_template_hash_"
if cache.get(template_hash_cache_key)!=template_hash:
	cache.clear()
	cache[template_hash_cache_key]=template_hash


@dataclass(frozen=True)
class Input:
	s: str  # the formula. Must not start or end with "$", but the return value will be wrapped in \(...\) or similar
	extra_preamble: str
	def hash(self)->str:
		return hashlib.sha256((str(len(self.s)) + "|" + self.s + self.extra_preamble).encode('u8')).hexdigest()

def typst_formulas_to_tex(l: list[str], extra_preamble: str)->list[str]:
	# no caching, preamble must be the same
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
			try: errortext=process.stderr.decode('u8')
			except UnicodeDecodeError: errorcontext=repr(process.stderr)
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


if not T.typstmathinputextrapreamble.defined():
	T.typstmathinputextrapreamble.assign_value(BalancedTokenList([]))


formula_counter: int=0
pending_formulas: list[Input]=[]

def process_pending_formulas()->None:
	# group pending_formulas by preamble
	key=lambda f: f.extra_preamble
	for k, g_ in itertools.groupby(sorted(pending_formulas, key=key), key=key):
		g=list(g_)
		result=typst_formulas_to_tex([x.s for x in g], k)
		for f, r in zip(pending_formulas, result):
			cache[f.hash()]=r

atexit.register(process_pending_formulas)

def handle_formula(engine: "Engine")->None:
	with group:  # we use the group to set the catcode temporarily
		catcode[" "]=catcode["\\"]=catcode["{"]=catcode["}"]=catcode["&"]=catcode["^"]=Catcode.other
		delimiter: BalancedTokenList=BalancedTokenList.get_next()
		s: str=BalancedTokenList([
				(Catcode.space(' ') if t==T.par else t)
				for t in BalancedTokenList.get_until(delimiter, remove_braces=False)
				]).detokenize()

	# preprocess it before passing to Typst
	superscript: Dict[str, Union[str, int, None]] = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-="))
	subscript: Dict[str, Union[str, int, None]] = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-="))
	s = re.sub('[' + "".join(superscript) + ']+', lambda x: "^(" + x[0].translate(str.maketrans(superscript)) + ")" , s)
	s = re.sub('[' + "".join(subscript) + ']+', lambda x: "_(" + x[0].translate(str.maketrans(subscript)) + ")" , s)
	s = re.sub(r'√\s*\(', ' sqrt(', s)
	s = re.sub(r'√\s*(\d+|\w+)', r' sqrt(\1)', s)

	input_=Input(s, var["typstmathinputextrapreamble"])
	input_hash=input_.hash()
	tmp=cache.get(input_hash)
	if tmp is not None:
		execute(tmp+"%")
	else:
		global formula_counter
		formula_counter+=1
		if formula_counter>=5:
			TokenList(r"\textbf{??}").execute()
			pending_formulas.append(input_)
		else:
			tmp_: str=typst_formulas_to_tex([s], input_.extra_preamble)[0]
			cache[input_hash]=tmp_
			execute(tmp_+"%")

	finish_listen()
handle_formula_identifier = add_handler(handle_formula)

enabled: set[str]=set()

def check_valid_delimiter(s: str)->None:
	if not (len(s)==1 and (s=="$" or ord(s)>=0x80)):
		raise RuntimeError(f"'{s}' is not supported!")

@newcommand
def typstmathinputenable()->None:
	s: str=get_arg_str()
	check_valid_delimiter(s)
	if s in enabled:
		raise RuntimeError(f"'{s}' is already enabled!")

	if s=="$" or default_engine.is_unicode:
		if s=="$" and catcode[s]!=Catcode.math_toggle:
			raise RuntimeError("It seems that '$' has an unusual catcode?")
		catcode[s]=Catcode.active
		TokenList([r"\def", Catcode.active(s),
			 r"{\pythonimmediatecallhandler{"+handle_formula_identifier+r"}\pythonimmediatelisten", Catcode.active(s), "}"]).execute()
	else:
		T[("_typstmathinput_backup_"+s).encode('u8')].assign_equal(T[("u8:"+s).encode('u8')])
		TokenList([r"\def", T[("u8:"+s).encode('u8')],
			 r"{\pythonimmediatecallhandler{"+handle_formula_identifier+r"}\pythonimmediatelisten{",
			 *map(Catcode.active, s.encode('u8')),
			 "}}"]).execute()


@newcommand
def typstmathinputdisable()->None:
	s: str=get_arg_str()
	check_valid_delimiter(s)
	if s not in enabled:
		raise RuntimeError(f"'{s}' is already disabled!")

	if s=="$":
		catcode["$"]=Catcode.math_toggle

	if s=="$" or default_engine.is_unicode:
		catcode[s]=Catcode.math_toggle if s=="$" else Catcode.other
	else:
		T[("u8:"+s).encode('u8')].assign_equal(T[("_typstmathinput_backup_"+s).encode('u8')])


@newcommand
def typstmathinputnormcat()->None:
	"""
	Internal function.

	To be used inside a math environment. Avoid fancyvrb or csquotes causing trouble with active characters.
	"""
	catcode["|"]=catcode['"']=Catcode.other


execute(r'\AtBeginDocument{\typstmathinputenable{◇}}')
