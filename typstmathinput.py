import joblib  # type: ignore
import tempfile
from pathlib import Path
import subprocess
import shutil
import hashlib
import re
from typing import Dict, Union

tmpdir=Path(tempfile.gettempdir())/".typstmathinput-tmp"
tmpdir.mkdir(exist_ok=True)
template_file=Path(__file__).parent/"typstmathinput-template.typ"
shutil.copy(template_file, tmpdir)
template_hash=hashlib.sha256((tmpdir/template_file.name).read_bytes()).digest()

@joblib.Memory(location=tmpdir/"cache", bytes_limit=2**20, verbose=0).cache
def typstmathinput_typst_formula_to_tex(s: str, extra_preamble: str, template_hash: bytes)->str:
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

def typstmathinput_printdollar_py()->None:
	from pythonimmediate import get_arg_str, print_TeX, var
	s = get_arg_str()

	# preprocess it before passing to Typst
	superscript: Dict[str, Union[str, int, None]] = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-="))
	subscript: Dict[str, Union[str, int, None]] = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-="))
	s = re.sub('[' + "".join(superscript) + ']+', lambda x: "^(" + x[0].translate(str.maketrans(superscript)) + ")" , s)
	s = re.sub('[' + "".join(subscript) + ']+', lambda x: "_(" + x[0].translate(str.maketrans(subscript)) + ")" , s)
	s = re.sub(r'√\s*\(', 'sqrt(', s)
	s = re.sub(r'√\s*(\d+|\w+)', r'sqrt(\1)', s)

	print_TeX(typstmathinput_typst_formula_to_tex(
		s,
		var["typstmathinputextrapreamble"],
		template_hash,
		), end="")

user_scope["typstmathinput_printdollar_py"]=typstmathinput_printdollar_py  # type: ignore
