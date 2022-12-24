#!/bin/python3
"""
======== Py-to-TeX half ========

receive things that should be passed to TeX from TeX-to-Py half,
then pass to TeX.

the things that are sent should already be newline-terminated if necessary.

user code are not executed here.
"""

import sys
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)  # when the other half terminates this one will terminates "gracefully"

#debug_file=open(Path(tempfile.gettempdir())/"pythonimmediate_debug_pytotex.txt", "w", encoding='u8', buffering=2)
#debug=functools.partial(print, file=debug_file, flush=True)
debug=lambda *args, **kwargs: None

import argparse
parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("mode", choices=["multiprocessing-network", "unnamed-pipe"])
args=parser.parse_args()


# ======== setup communication method. Just an infinite loop print whatever being sent.

if args.mode=="multiprocessing-network":
	from multiprocessing.connection import Listener

	address=("localhost", 7348)
	#address="./pythonimmediate.socket"
	with Listener(address) as listener:
		print("listener-setup-done", flush=True)
		with listener.accept() as connection:
			debug("accepted a connection")
			while True:
				try:
					data=connection.recv_bytes()
					debug(" data=", data)
					sys.__stdout__.buffer.write(data)  # will go to TeX
					sys.__stdout__.buffer.flush()
				except EOFError: break

elif args.mode=="unnamed-pipe":
	import os
	sys.stdout.write("pytotex_pid=" + str(os.getpid()) + "\n")
	sys.stdout.flush()
	for line in sys.stdin:
		sys.stdout.write(line)
		sys.stdout.flush()

else:
	assert False

# ========
