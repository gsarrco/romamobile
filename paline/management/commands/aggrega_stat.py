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
from autenticazione.models import LogAutenticazioneServizi
from log_servizi.models import Invocazione
from stats.models import *
from paline.models import Disservizio, DisservizioPalinaElettronica as DPE
from datetime import datetime, timedelta, date
from django.db import connections, transaction
from servizi.utils import mysql2date, datetime2date, date2mysql

class Command(BaseCommand):
	args = '[<data>] [deleteonly]'
	help = 'Aggrega i dati statistici per ora'
	
	
	def handle(self, *args, **options):
		if len(args) == 0:
			data = datetime2date(datetime.now() - timedelta(days=1))
		else:
			data = mysql2date(args[0])
				
		print data
				
		connection = connections['default']
		cursor = connection.cursor()
		if not 'deleteonly' in args:
			print "Elaboro statistiche"
			cursor.execute('''
				insert into paline_logtempoarcoaggr(id_palina_s, id_palina_t, data, ora, tempo, peso)
				select id_palina_s, id_palina_t, data, hour(ora) as ora, sum(peso*tempo)/sum(peso) as tempo, sum(peso) as peso
				from paline_logtempoarco
				where data = %s
				group by hour(ora), id_palina_s, id_palina_t;	
			''', (data, )
			)
			transaction.commit_unless_managed() 
		for i in range(24):
			print "Elimino vecchi dati, ore %d" % i
			sql = '''
				delete from paline_logtempoarco
				where data = '%s'
				and hour(ora) = %d
			''' % (date2mysql(data), i)
			print sql
			cursor.execute(sql)
			transaction.commit_unless_managed() 
	

