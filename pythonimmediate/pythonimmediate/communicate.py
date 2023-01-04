"""
Classes to facilitate communication between this process and the pytotex half.
"""

from abc import ABC, abstractmethod
import typing
import sys
from typing import List, Any, Optional


class Communicator(ABC):
	character = typing.cast(str, None)

	def send(self, data: bytes)->None:
		raise NotImplementedError

	@staticmethod
	@abstractmethod
	def forward()->None:
		"""
		initially the process will print one line to TeX, and then
		TeX will forward that line to the other process to determine the communication method used.

		another process should initialize a Communicator object with that line,
		call .send() to send data to this process.
		this process will get all the data and print them to stdout.
		"""
		raise NotImplementedError


class MultiprocessingNetworkCommunicator(Communicator):
	character = 'm'

	def __init__(self, s: str)->None:
		self.address=("localhost", int(s))
		from multiprocessing.connection import Client
		self.connection=Client(self.address)

	def send(self, data: bytes)->None:
		self.connection.send_bytes(data)

	@staticmethod
	def forward()->None:
		from multiprocessing.connection import Listener

		# pick address randomly and create listener with it until it succeeds
		import socket
		import random
		while True:
			try:
				port = random.randint(1024, 65535)
				address=("localhost", port)
				listener=Listener(address)
				break
			except socket.error:
				pass

		sys.__stdout__.write(f"{MultiprocessingNetworkCommunicator.character}{port}\n")
		sys.__stdout__.flush()

		with listener:
			with listener.accept() as connection:
				while True:
					try:
						data=connection.recv_bytes()
						sys.__stdout__.buffer.write(data)  # will go to TeX
						sys.__stdout__.buffer.flush()
					except EOFError: break


class UnnamedPipeCommunicator(Communicator):
	character = 'u'
	
	def __init__(self, s: str)->None:
		self.connection=open("/proc/" + str(s) + "/fd/0", "wb")

	def send(self, data: bytes)->None:
		self.connection.write(data)
		self.connection.flush()  # just in case

	@staticmethod
	def forward()->None:
		import os
		sys.stdout.write(f"{UnnamedPipeCommunicator.character}{os.getpid()}\n")
		sys.stdout.flush()
		for line in sys.stdin:
			sys.stdout.write(line)
			sys.stdout.flush()



communicator_classes: List[Any] = [MultiprocessingNetworkCommunicator, UnnamedPipeCommunicator]
first_char_to_communicator = {c.character: c for c in communicator_classes}
assert len(first_char_to_communicator) == len(communicator_classes)
assert all(len(c)==1 for c in first_char_to_communicator)


def create_communicator(s: str)->Communicator:
	return first_char_to_communicator[s[0]](s[1:])
