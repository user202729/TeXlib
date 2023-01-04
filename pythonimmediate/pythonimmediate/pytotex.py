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

from .communicate import MultiprocessingNetworkCommunicator, UnnamedPipeCommunicator

communicator_by_name={
		"multiprocessing-network": MultiprocessingNetworkCommunicator,
		"unnamed-pipe": UnnamedPipeCommunicator,
		}

import argparse
parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("mode", choices=list(communicator_by_name.keys()), help="the mode of communication")
args=parser.parse_args()


communicator_by_name[args.mode].forward()
