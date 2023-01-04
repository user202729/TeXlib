"""
Abstract engine class.
"""

from typing import Optional, Literal, Iterable, List, Dict, Tuple
from abc import ABC, abstractmethod
import sys
import subprocess
from dataclasses import dataclass


class Engine(ABC):
	_is_unicode: bool
	def __init__(self):
		self.action_done=False
		self.exited=False  # once the engine exit, it can't be used anymore.

	# some helper functions for the communication protocol.
	def check_not_finished(self)->None:
		if self.action_done:
			raise RuntimeError("can only do one action per block!")

	@property
	def is_unicode(self)->bool: 
		return self._is_unicode

	def check_not_exited(self, message: str)->None:
		if self.exited:
			raise RuntimeError(message)

	def check_not_exited_before(self)->None:
		self.check_not_exited("TeX error already happened, cannot continue")

	def check_not_exited_after(self)->None:
		self.check_not_exited("TeX error!")

	def read(self)->bytes:
		"""
		Read one line from the engine.

		It must not be EOF otherwise there's an error.
		"""
		self.check_not_exited_before()
		result=self._read()
		self.check_not_exited_after()
		return result

	def write(self, s: bytes)->None:
		self.check_not_exited_before()
		self._write(s)
		self.check_not_exited_after()

	@abstractmethod
	def _read(self)->bytes:
		"""
		Read one line from the engine.

		Should return b"⟨line⟩\n" or b"" (if EOF) on each call.
		"""
		...

	@abstractmethod
	def _write(self, s: bytes)->None:
		"""
		Write data to the engine.

		Because TeX can only read whole lines s should be newline-terminated.
		"""
		...


class ParentProcessEngine(Engine):
	"""
	Represent the engine if this process is started by the TeX's pythonimmediate library.

	This should not be used directly. Only pythonimmediate.main module should use this.
	"""
	def __init__(self)->None:
		super().__init__()
		line=self.read().decode('u8')
		assert line.endswith("\n")

		self._is_unicode={"a": False, "u": True}[line[0]]
		line=line[1:]

		from . import communicate
		self.communicator=communicate.create_communicator(line[:-1])

		sys.stdin=None  # type: ignore
		# avoid user mistakenly read

	def _read(self)->bytes:
		line=sys.__stdin__.buffer.readline()
		if not line: self.exited=True
		return line

	def _write(self, s: bytes)->None:
		self.communicator.send(s)


EngineName=Literal["pdflatex", "xelatex", "lualatex"]
engine_names: Tuple[str, ...]=EngineName.__args__  # type: ignore
engine_is_unicode: Dict[EngineName, bool]={
		"pdflatex": False,
		"xelatex": True,
		"lualatex": True,
		}
assert len(engine_is_unicode)==len(engine_names)
assert set(engine_is_unicode)==set(engine_names)


@dataclass
class SetDefaultEngineContextManager:
	"""
	Context manager, used in conjunction with default_engine.set_engine(...) to revert to the original engine.
	"""
	old_engine: Optional[Engine]

	def __enter__(self)->None:
		pass

	def __exit__(self, exc_type, exc_val, exc_tb)->None:
		default_engine.set_engine(self.old_engine)


class DefaultEngine(Engine):
	def __init__(self)->None:
		super().__init__()
		self.engine: Optional[Engine]=None

	def set_engine(self, engine: Optional[Engine])->SetDefaultEngineContextManager:
		"""
		set to another engine. Can also be used as a context manager to revert to the original engine.
		Example:

		with default_engine.set_engine(...):
			pass  # do something
		# now the original engine is restored
		"""
		result=SetDefaultEngineContextManager(self.engine)
		self.engine=engine
		return result

	def get_engine(self)->Engine:
		"""
		Convenience helper function, return the engine.

		All the other functions that use this one (those that make use of the engine) will raise RuntimeError
		if the engine is None.
		"""
		if self.engine is None:
			raise RuntimeError("Default engine not set!")
		return self.engine

	@property
	def is_unicode(self)->bool:
		return self.get_engine().is_unicode

	def _read(self)->bytes:
		return self.get_engine().read()

	def _write(self, s: bytes)->None:
		self.get_engine().write(s)


default_engine=DefaultEngine()


from . import textopy


@dataclass
class ChildProcessEngine(Engine):
	"""
	An object that represents an engine that runs as a subprocess of this process.

	Can be used as a context manager to automatically close the subprocess when the context is exited.

	Example:

	with ChildProcessEngine(...) as engine:
		# do something
	# the subprocess is closed here
	"""

	def __init__(self, engine_name: EngineName, args: Iterable[str]=())->None:
		super().__init__()
		self.engine_name=engine_name
		self._is_unicode=engine_is_unicode[engine_name]

		# old method, tried, does not work, see details in sty file

		# create a sym link from /dev/stderr to /tmp/.tex-stderr
		# because TeX can only write to files that contain a period
		#from pathlib import Path
		import tempfile
		#target=Path(tempfile.gettempdir())/"symlink-to-stderr.txt"
		#try:
		#	target.symlink_to(Path("/dev/stderr"))
		#except FileExistsError:
		#	# we assume nothing maliciously create a file named `.symlink-to-stderr` that is not a symlink to stderr...
		#	pass

		self.process: Optional[subprocess.Popen]=subprocess.Popen(
				[
					engine_name, "-shell-escape",
						*args, r"\RequirePackage[mode=child-process]{pythonimmediate}\pythonimmediatechildprocessmainloop\stop"],
				stdin=subprocess.PIPE,
				#stdout=subprocess.PIPE,  # we don't need the stdout
				stdout=subprocess.DEVNULL,
				stderr=subprocess.PIPE,
				cwd=tempfile.gettempdir(),
				)

		from .textopy import surround_delimiter, send_raw, substitute_private
		send_raw(surround_delimiter(substitute_private(
			textopy.bootstrap_code + 
			r"""
			\cs_new_eq:NN \pythonimmediatechildprocessmainloop \__read_do_one_command:
			"""
			)), engine=self)

	def get_process(self)->subprocess.Popen:
		if self.process is None:
			raise RuntimeError("process is already closed!")
		return self.process

	def _read(self)->bytes:
		process=self.get_process()
		assert process.stderr is not None
		#print("waiting to read")
		line=process.stderr.readline()
		#print("reading", line)
		return line

	def _write(self, s: bytes)->None:
		process=self.get_process()
		assert process.stdin is not None
		#print("writing", s)
		process.stdin.write(s)
		process.stdin.flush()

	def close(self)->None:
		"""
		sent a "r" to the process so TeX exits gracefully.

		this might be called from __del__ so do not import anything here.
		"""
		process=self.get_process()
		textopy.run_none_finish(engine=self)
		process.wait()
		assert process.stdin is not None
		assert process.stderr is not None
		process.stdin.close()
		process.stderr.close()
		self.process=None

	def __del__(self)->None:
		if self.process is not None:
			self.close()

	def __enter__(self)->Engine:
		return self

	def __exit__(self, exc_type, exc_val, exc_tb)->None:
		self.close()


