import joblib  # type: ignore
import tempfile
from pathlib import Path
import subprocess
import shutil
import hashlib
import re
from typing import Dict, Union
from pythonimmediate import*
from pythonimmediate.engine import default_engine

tmpdir=Path(tempfile.gettempdir())/".typstmathinput-tmp"
tmpdir.mkdir(exist_ok=True)
template_file=Path(__file__).parent/"typstmathinput-template.typ"
shutil.copy(template_file, tmpdir)
template_hash=hashlib.sha256((tmpdir/template_file.name).read_bytes()).digest()

@joblib.Memory(location=tmpdir/"cache", bytes_limit=2**20, verbose=0).cache
def typst_formula_to_tex(s: str, extra_preamble: str, template_hash: bytes)->str:
	# s must not start or end with "$", but the return value will be wrapped in $...$ or similar
	# template_hash is not directly used but this is needed to invalidate joblib cache
	with tempfile.NamedTemporaryFile(dir=tmpdir, prefix="", suffix=".typ", delete=False, mode="w") as f:
		n=Path(f.name)
		f.write(r"""
#import "typstmathinput-template.typ": equation_to_latex
""" + extra_preamble + r"""
#set page(width: 100cm)
#raw(equation_to_latex($""" + s + r"""$))
""")
		# .replace(" ", "<SP>")
	try:
		process=subprocess.run(["typst", "compile", n, n.with_suffix(".pdf")], cwd=tmpdir, stderr=subprocess.PIPE)
		if process.returncode!=0:
			try: errortext=process.stderr.decode('u8')
			except UnicodeDecodeError: errorcontext=repr(process.stderr)
			raise RuntimeError(f"Formula ${s}$ is invalid: {errortext}")
	finally: n.unlink(missing_ok=True)
	if not n.with_suffix(".pdf").is_file():
		raise ValueError(f"Formula ${s}$ is invalid -- Typst finishes but does not provide PDF")
	try: subprocess.run(["pdftotext", n.with_suffix(".pdf")], cwd=tmpdir, check=True)
	finally: n.with_suffix(".pdf").unlink(missing_ok=True)
	try: result: str=n.with_suffix(".txt").read_text().replace("\n", "").replace("\x0c", "")
	finally: n.with_suffix(".txt").unlink(missing_ok=True)
	return result


if not T.typstmathinputextrapreamble.defined():
	T.typstmathinputextrapreamble.assign_value(BalancedTokenList([]))


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

	execute(typst_formula_to_tex(
		s,
		var["typstmathinputextrapreamble"],
		template_hash,
		)+"%")

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
