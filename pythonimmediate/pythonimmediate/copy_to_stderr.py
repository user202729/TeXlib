"""
module to copy everything from stdin to stderr.

needed to allow TeX to write to stderr.
"""

import sys
if __name__ == '__main__':
	for line in sys.stdin.buffer:
		sys.stderr.buffer.write(line)
		sys.stderr.buffer.flush()
