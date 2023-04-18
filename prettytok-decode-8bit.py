#!/bin/python3
"""
A hack to allow decoding for example ^^[ to the proper escape sequence.
"""

import sys
import re
def replace_8bit(match_: re.Match) -> str:
	return chr(ord(match_.group(1))^0x40)
if __name__ == '__main__':
	for line in sys.stdin:
		sys.stdout.write(re.sub(r"\^\^(.)", replace_8bit, line))
