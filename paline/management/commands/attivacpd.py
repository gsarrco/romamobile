# coding: utf-8

#
#    Copyright 2013 Roma servizi per la mobilità srl
#    Developed by Luca Allulli and Damiano Morosi
#
#    This file is part of Muoversi a Roma for Developers.
#
#    Muoversi a Roma for Developers is free software: you can redistribute it
#    and/or modify it under the terms of the GNU General Public License as
#    published by the Free Software Foundation, version 2.
#
#    Muoversi a Roma for Developers is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
#    for more details.
#
#    You should have received a copy of the GNU General Public License along with
#    Muoversi a Roma for Developers. If not, see http://www.gnu.org/licenses/.
#

from paline import tpl
from rpyc.utils.server import ThreadedServer
from django.core.management.base import BaseCommand, CommandError
import settings
import socket
import os
import time

config = {
	'allow_public_attrs': True,
}

class Command(BaseCommand):
	args = """Nessun argomento"""
	help = 'Aggiorna il timestamp dei file Cython per triggerare la ricompilazione'

	def handle(self, *args, **options):
		fs = [
			'paline/geocoder.pyx',
			'paline/grafo.pyx',
		]
		for f in fs:
			os.utime(f, None)
	
