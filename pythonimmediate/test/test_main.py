import pytest

import pythonimmediate
import pythonimmediate.textopy
from pythonimmediate.engine import ChildProcessEngine, default_engine
from pythonimmediate import TokenList, ControlSequenceToken
from pythonimmediate import Catcode as C

T=ControlSequenceToken.make

engine=ChildProcessEngine("lualatex")

default_engine.set_engine(engine)

class Test:
	def test_something(self)->None:
		TokenList([T["def"], T.testa, TokenList.doc("123")]).execute()
		assert TokenList([T.testa]).expand_x().str() == "123"

	def test_separate_engine(self)->None:
		with default_engine.set_engine(None):

			with pytest.raises(RuntimeError):
				TokenList([T["def"], T.testa, TokenList.doc("123")]).execute()

			TokenList([T["def"], T.testa, TokenList.doc("123")]).execute(engine=engine)

			with ChildProcessEngine("pdflatex") as new_engine:

				TokenList([T["def"], T.testa, TokenList.doc("456")]).execute(engine=new_engine)

				assert TokenList([T.testa]).expand_x(engine=engine).str() == "123"
				assert TokenList([T.testa]).expand_x(engine=new_engine).str() == "456"


