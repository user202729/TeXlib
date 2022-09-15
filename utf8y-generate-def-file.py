#!/bin/python3
from pathlib import Path
import re

f=Path(".").glob("uni-*.def")

f=sorted([
		(int(m[1]), n)
		for n in f
		for m in [re.fullmatch(r"uni-(\d+)\.def", n.name)]
		if m
		])

Path("/tmp/all.def").write_text(
		"\n".join(y.read_text() for x, y in f)
		)
