import subprocess
import tempfile

import pytest

import pythonimmediate
import pythonimmediate.textopy
from pythonimmediate.engine import ChildProcessEngine, default_engine, engine_names
from pythonimmediate import TokenList, ControlSequenceToken
from pythonimmediate import Catcode as C

T=ControlSequenceToken.make

class Test:
	@pytest.mark.parametrize("engine_name", engine_names)
	def test_child_process_engine(self, engine_name: str)->None:
		for engine_name in ["pdflatex", "xelatex", "lualatex"]:
			engine=ChildProcessEngine(engine_name)

			with default_engine.set_engine(engine):
				TokenList([T["def"], T.testa, TokenList.doc("123")]).execute()
				assert TokenList([T.testa]).expand_x().str() == "123"

			assert default_engine.engine is None

			with pytest.raises(RuntimeError):
				TokenList([T["def"], T.testa, TokenList.doc("789")]).execute()

			with ChildProcessEngine("pdflatex") as new_engine:
				TokenList([T["def"], T.testa, TokenList.doc("456")]).execute(engine=new_engine)
				assert TokenList([T.testa]).expand_x(engine=engine).str() == "123"
				assert TokenList([T.testa]).expand_x(engine=new_engine).str() == "456"


	@pytest.mark.parametrize("engine_name", engine_names)
	@pytest.mark.parametrize("communication_method", ["unnamed-pipe", "multiprocessing-network"])
	def test_subprocess(self, engine_name: str, communication_method: str)->None:
		from pathlib import Path
		for name in ["test_pythonimmediate.tex", "test_pythonimmediate_file.py"]:
			a=Path("/tmp")/name
			a.unlink(missing_ok=True)
			a.symlink_to(Path(__file__).parent.parent.parent/name)

		subprocess.run(
				[engine_name, "-shell-escape", "-8bit", r"\def\specifymode{"+communication_method+r"}\input{/tmp/test_pythonimmediate.tex}"],
				check=True,
				cwd=tempfile.gettempdir(),
				)