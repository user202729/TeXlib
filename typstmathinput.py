import joblib  # type: ignore
import tempfile
from pathlib import Path
import subprocess
import shutil
import hashlib

tmpdir=Path(tempfile.gettempdir())/".typstmathinput-tmp"
tmpdir.mkdir(exist_ok=True)
template_file=Path(__file__).parent/"typstmathinput-template.typ"
shutil.copy(template_file, tmpdir)

@joblib.Memory(location=tmpdir/"cache", bytes_limit=2**20, verbose=0).cache
def typstmathinput_typst_formula_to_tex(s: str, template_hash: bytes)->str:
	# s must not start or end with "$", but the return value will be wrapped in $...$ or similar
	# template_hash is not directly used but this is needed to invalidate joblib cache
	with tempfile.NamedTemporaryFile(dir=tmpdir, prefix="", suffix=".typ", delete=False, mode="w") as f:
		n=Path(f.name)
		f.write(r"""
#import "typstmathinput-template.typ": equation_to_latex
#raw(equation_to_latex($""" + s + r"""$))
""")
	try: subprocess.run(["typst", n, n.with_suffix(".pdf")], cwd=tmpdir, check=True)
	finally: n.unlink(missing_ok=True)
	try: subprocess.run(["pdftotext", n.with_suffix(".pdf")], cwd=tmpdir, check=True)
	finally: n.with_suffix(".pdf").unlink(missing_ok=True)
	try: result: str=n.with_suffix(".txt").read_text().replace("\n", "").replace("\x0c", "")
	finally: n.with_suffix(".txt").unlink(missing_ok=True)
	return result

def typstmathinput_printdollar_py()->str:
	from pythonimmediate import get_arg_str, print_TeX
	s = get_arg_str()
	print_TeX(typstmathinput_typst_formula_to_tex(
		s,
		hashlib.sha256(template_file.read_bytes()).digest()
		), end="")

user_scope["typstmathinput_printdollar_py"]=typstmathinput_printdollar_py
