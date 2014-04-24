# coding: utf-8

#
#    Copyright 2013-2014 Roma servizi per la mobilità srl
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

from django.core.management.base import BaseCommand, CommandError
import settings
from mercury.models import *
from datetime import date, time, datetime, timedelta
from paline.trovalinea import TrovalineaFactory

config = {
	'allow_public_attrs': True,
}

class Command(BaseCommand):
	args = ""
	help = 'Nuovo trovalinea'

	def handle(self, *args, **options):
		commands = ['mini', 'cpd', 'tr', 'shell', 'special', 'download']
		dt = None
		for k in args:
			if not k in commands:
				dt = k.replace('T', ' ')

		name = settings.MERCURY_CPD
		if 'tr' in args:
			name = settings.MERCURY_GIANO
		
		giano = PeerType.objects.get(name=name)
		giano_daemon = Daemon.get_process_daemon(name)
		Trovalinea = TrovalineaFactory('mini' in args, 'cpd' in args, 'tr' in args, 'shell' in args, 'special' in args, dt, 'download' in args, daemon=giano_daemon)

		m = Mercury(giano, Trovalinea, daemon=giano_daemon, watchdog_daemon=giano_daemon)
		if not 'tr' in args:
			try:
				print "Richiedo serializzazione"
				c = Mercury.rpyc_connect_any_static(settings.MERCURY_CPD)
				Trovalinea.rete.deserializza_dinamico(pickle.loads(c.root.serializza_dinamico()))
				print "Serializzazione richiesta effettuata"
			except Exception, e:
				print "Serializzazione richiesta fallita"
		
		giano_daemon.set_ready()

