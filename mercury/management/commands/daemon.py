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


from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
import settings
import os, subprocess, signal
from datetime import date, time, datetime, timedelta
from servizi.utils import datetime2time
from django.db.models import Q
from mercury.models import *

config = {
	'allow_public_attrs': True,
}

class Command(BaseCommand):
	args = "[-f] nome_demone1 nome_demone2..."
	help = """
		Orchestra i demoni passati come parametro.
		E' responsabilita' del demone impostare ready a True sulla propria istanza per permettere
		la presecuzione della procedura di restart.
		
		-f: riavvia anche i server con flag ready==False
	"""
	option_list = BaseCommand.option_list + (
		make_option(
			'-f',
			action='store_true',
			dest='forza_riavvio',
			default=False,
			help='riavvia anche i server con flag ready==False',
		),
	)
	

	def handle(self, *args, **options):
		
		n = datetime.now()
		t = datetime2time(n)
		
		for nome in args:		
			print "Orchestro demone ", nome
			sc = DaemonControl.objects.get(name=nome)
			ss_istanziati = sc.daemon_set.all()
			if options['forza_riavvio']:
				print "Forzo riavvio"
				ss_pronti = ss_istanziati
			else:
				ss_pronti = ss_istanziati.filter(ready=True)			
			
			if sc.action == 'R':
				for s in ss_istanziati:
					s.action = 'R'
					s.save()
				sc.action = 'N'
				sc.save()
				
			if sc.action == 'S':
				for s in ss_istanziati:
					print "Chiudo il processo ", sc.name, s.pid
					try:
						os.kill(s.pid, signal.SIGTERM)
					except Exception:
						pass
					s.delete()					
				sc.action = 'F'
				sc.save()
			
			if sc.action != 'F':
				# Chiudo un eventuale server obsoleto
				server_chiusi = 0			
				if len(ss_pronti) == len(ss_istanziati):
					ss_scaduti = ss_istanziati.filter(Q(active_since__lt=n - timedelta(minutes=sc.restart_timeout)) | Q(action='R')).exclude(action='F')
					if len(ss_scaduti) > 0:
						s = ss_scaduti[0]
						if s.action == 'R' or sc.restart_from <= t <= sc.restart_to:
							print "Chiudo il processo ", sc.name, s.pid
							try:
								os.kill(s.pid, signal.SIGTERM)
							except Exception:
								pass
							s.delete()
							server_chiusi = 1
									
				# Istanzio i server richiesti, fino a raggiungere il numero previsto
				for i in range(max(0, sc.instances - len(ss_istanziati) + server_chiusi)):
					print "Lancio: ", sc.command
					p = subprocess.Popen(sc.command.split())
					Daemon(
						control=sc,
						active_since=n,
						pid=p.pid,
					).save()

			