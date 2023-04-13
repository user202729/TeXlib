#!/bin/python3
"""
temporary file
"""

import sys
import re
def replace_8bit(match_: re.Match) -> str:
	return chr(ord(match_.group(1))^0x40)
if __name__ == '__main__':
	for line in sys.stdin:
		sys.stdout.write(re.sub(r"\^\^(.)", replace_8bit, line))
