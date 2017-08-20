# coding: utf-8

#
#    Copyright 2015-2016 Roma servizi per la mobilità srl
#    Developed by Luca Allulli
#
#    This file is part of Roma mobile.
#
#    Roma mobile is free software: you can redistribute it
#    and/or modify it under the terms of the GNU General Public License as
#    published by the Free Software Foundation, version 2.
#
#    Roma mobile is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
#    for more details.
#
#    You should have received a copy of the GNU General Public License along with
#    Roma mobile. If not, see http://www.gnu.org/licenses/.
#

from stats.models import get_data_limite
from servizi.models import RicercaRecente
from paline.models import LogTempoArco, LogTempoAttesaPercorso, LogPercorsoCities, LogChiamataCities, ArcoRimosso
from paline.models import LogCities, LogCitiesLineaPreservata
from paline import tpl
from datetime import datetime, date, time, timedelta
from django.db import connections, transaction
from django.db.models import Min, Sum
from servizi.utils import datetime2date, date2datetime, mysql2datetime, date2mysql, dateandtime2datetime
from servizi.utils import transaction_commit_manually, template_to_mail
from autenticazione.models import LogAutenticazioneServizi
from log_servizi.models import Invocazione
from paline.caricamento_rete.caricamento_rete import carica_rete_auto
import os, os.path, shutil
import settings

MAIL_REPORT_CITIES = [
]

@transaction_commit_manually
def _aggrega_stat_data(job=None, data=None):
	"""
	Metodo interno invocato da aggrega_stat
	"""
	connection = connections['default']
	cursor = connection.cursor()
	print "Elaboro statistiche"
	cursor.execute('''
		insert ignore into paline_logtempoarcoaggr(id_palina_s, id_palina_t, data, ora, tempo, peso)
		select id_palina_s, id_palina_t, data, hour(ora) as ora, sum(peso*tempo)/sum(peso) as tempo, sum(peso) as peso
		from paline_logtempoarco
		where data = %s
		group by hour(ora), id_palina_s, id_palina_t;
	''', (data, ))
	transaction.commit()



def aggrega_stat(job=None, data_limite=None):
	"""
	Aggrega i log_tempo_arco per fascia oraria

	Non cancella i log dal db, calcola solo le statistiche.
	Pertanto usa la data annotata nel job come data di partenza per le statistiche
	"""
	assert job is not None, "Il job non puo' essere None"

	d = job.last_element_ts
	while not esci:
		d = d + timedelta(days=1)
		if d <= data_limite:
			_aggrega_stat_data(job, d)
			job.last_element_ts = d
			job.keep_alive()
		else:
			esci = True


def calcola_frequenze(job):
	tpl.calcola_frequenze()
	return (0, 'OK')


def carica_rete(job=None):
	"""
	Carica la rete del TPL e invia una mail di conferma
	"""
	carica_rete_auto()
	return (0, 'OK')


def elimina_file_rete_obsoleti(job=None):
	"""
	Elimina i file della rete più vecchi di un mese.

	Mantiene comunque le ultime 20 reti
	"""
	RETI_DA_MANTENERE = 20
	GIORNI_DA_MANTENERE = 30

	path = settings.TROVALINEA_PATH_RETE
	fs = os.listdir(path)
	fs = [f for f in fs if f.startswith('20')]
	fs.sort()
	print fs
	fs = fs[:-RETI_DA_MANTENERE]
	data_limite = (datetime.now() - timedelta(days=GIORNI_DA_MANTENERE)).strftime('%Y%m%d')
	print "Cancello fino alla data limite: %s" % data_limite
	for f in fs:
		if f < data_limite:
			print "Deleting %s" % f
			shutil.rmtree(os.path.join(path, f))

	return (0, 'OK')


@transaction_commit_manually()
def _elimina_log_cities_obsoleti_data(job=None, data=None):
	"""
	Metodo interno invocato da aggrega_stat
	"""
	print data
	lps = LogCitiesLineaPreservata.objects.all()
	lps = [lp.id_linea for lp in lps]
	LogCities.objects.filter(data_ora_ric__lt=data).exclude(linea__in=lps).delete()
	transaction.commit()
	if job is not None:
		job.last_element_ts = data + timedelta(days=1)
		job.keep_alive()


# Elimina log CITIES obsoleti, eccetto i percorsi di interesse
def elimina_log_cities_obsoleti(job=None, data_limite=None):
	"""
	Storicizza i log_tempo_attesa_percorso
	"""
	if data_limite is None:
		data_limite = get_data_limite(3)

	esci = False
	while not esci:
		if job.last_element_ts is not None:
			d = datetime2date(job.last_element_ts)
		else:
			d = datetime2date(LogCities.objects.all().aggregate(Min('data_ora_ric'))['data_ora_ric__min'])
		if d <= data_limite:
			_elimina_log_cities_obsoleti_data(job, d)
		else:
			esci = True
	return (0, 'OK')
