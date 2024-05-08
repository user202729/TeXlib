from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass

from pythonimmediate.simple import newcommand, parse_keyval, default_get_catcode
from pythonimmediate import*

def main()->None:
	if T.__umi_register_deunicode.is_defined():
		return

	@lru_cache(maxsize=None)
	def unicode_char_meaning(c: str)->BalancedTokenList:
		assert len(c)==1
		if default_engine.name=="pdftex":
			t=T["u8:"+c]
			if "macro:->" in t.meaning_str():
				return BalancedTokenList([T["u8:"+c]]).expand_o()
			else:
				raise ValueError(f"Character {c!r} has unexpected meaning {t.meaning_str()!r}")
		else:
			raise ValueError(f"Engine {default_engine.name!r} is not supported")

	def expand_next_until_callback()->None:
		with group:
			T.__umi_callback.set_eq(T.pythonimmediatecontinuenoarg)
			continue_until_passed_back()

	def expand_until_callback(t: BalancedTokenList, prefix: BalancedTokenList=BalancedTokenList())->BalancedTokenList:
		try:
			egroup.put_next()
			t.put_next()
			expand_next_until_callback()
			prefix.put_next()
			bgroup.put_next()
			return BalancedTokenList.get_next()
		except:
			raise RuntimeError(f"Error expanding {t}")

	@functools.lru_cache(maxsize=None)
	def process_char(c: str)->Any:
		s=unicode_char_meaning(c)
		if s[0]==T["mode_if_math:TF"]:
			l=1
			r=2
			while not TokenList(s)[l:r].is_balanced():
				r+=1
			s=s[l:r]
			if isinstance(s[0], CharacterToken) and s[0].catcode==C.begin_group and TokenList(s)[1:-1].is_balanced():
				s=s[1:-1]

		if s[0]==T["__umi_require_math"]:
			s=s[1:]

		while s and isinstance(s[0], ControlSequenceToken) and s[0].csname.startswith(("umiMath", "__umi_")):
			if s and s[0] in (T["__umi_superscript"], T["__umi_subscript"]):
				return (s[0], s[1:])
			s=expand_until_callback(s)

		return (BalancedTokenList, s)

	def process(input_content: str)->str:
		result=[]
		for c in input_content:
			if ord(c)>=0x80:
				result.append(process_char(c))
			else:
				result.append((str, c))

		import itertools
		result1=[]
		for kind, group in itertools.groupby(result, lambda x: x[0]):
			if kind==str:
				result1.append("".join(x[1] for x in group))
			elif kind==BalancedTokenList:
				result1.append("".join(x[1].simple_detokenize(default_get_catcode) for x in group))
			elif kind in (T["__umi_superscript"], T["__umi_subscript"]):
				content_inside=BalancedTokenList([t for x in group for t in x[1]])
				if T.umiPrime in content_inside or T.umiBackprime in content_inside:
					try: i=content_inside.index(T.umiPrime)
					except ValueError: i=content_inside.index(T.umiBackprime)
					content_inside=expand_until_callback(content_inside[i:], prefix=content_inside[:i])
				content_inside_str="".join(x.simple_detokenize(default_get_catcode) for x in content_inside)
				if len(content_inside_str)>1:
					content_inside_str="{"+content_inside_str+"}"
				result1.append(("^" if kind==T["__umi_superscript"] else "_")+content_inside_str)
			else:
				raise ValueError(f"Unknown kind {kind}")

		for i in range(1, len(result1)):
			if result1[i-1].endswith(" ") and result1[i].startswith(" "):
				result1[i]=result1[i].lstrip(" ")
		return "".join(result1)

	@dataclass
	class RegisteredItem:
		input_file: Path
		input_content: str
		output_file: Path
	registered_items: list[RegisteredItem]=[]

	def register_deunicode()->None:
		d={
				BalancedTokenList(k).expand_estr(): (v.expand_estr() if v is not None else None)
				for k, v in BalancedTokenList.get_next().parse_keyval().items()}
		try: input_file=d["input"]
		except KeyError: raise ValueError("Input not specified")
		try: output_file=d["output"]
		except KeyError: raise ValueError("Output not specified")

		if input_file is None:
			raise ValueError("Input not specified")
		if output_file is None:
			raise ValueError("Output not specified")

		try: input_content=Path(input_file).read_text()
		except FileNotFoundError: raise ValueError(f"Input file {input_file} not found")

		registered_items.append(RegisteredItem(input_file=Path(input_file), input_content=input_content, output_file=Path(output_file)))

	T.__umi_register_deunicode.set_func(register_deunicode, global_=True)

	BalancedTokenList(r'\AtBeginDocument{\__umi_run_deunicode}').execute()

	def run_deunicode()->None:
		for item in registered_items:
			if item.input_content!=item.input_file.read_text():
				raise ValueError(f"Input file {item.input_file} has been modified")
			item.output_file.write_text(process(item.input_content))

	T.__umi_run_deunicode.set_func(run_deunicode, global_=True)

main()
