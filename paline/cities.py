# coding: utf-8

#
#    Copyright 2015-2016 Roma servizi per la mobilità srl
#    Developed by Luca Allulli
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

import logging
import requests
import re
import csv
from datetime import date, time, datetime, timedelta
from paline.geomath import wgs84_to_gbfe
from servizi.utils import mysql2datetime, datetime2mysql
import traceback
import bz2
import Queue
from lxml import etree
from lxml.etree import fromstring
import io
from threading import Thread

CITIES_URL = ''
CITIES_URL_CAPOLINEA = ''
TIMEOUT = 10

_parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
# Definisco una trasformazione XSLT che rimuove i namespace dal documento XML
_xslt='''<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
	<xsl:output method="xml" indent="no"/>

	<xsl:template match="/|comment()|processing-instruction()">
			<xsl:copy>
				<xsl:apply-templates/>
			</xsl:copy>
	</xsl:template>

	<xsl:template match="*">
			<xsl:element name="{local-name()}">
				<xsl:apply-templates select="@*|node()"/>
			</xsl:element>
	</xsl:template>

	<xsl:template match="@*">
			<xsl:attribute name="{local-name()}">
				<xsl:value-of select="."/>
			</xsl:attribute>
	</xsl:template>
	</xsl:stylesheet>
'''
_xslt_doc=etree.parse(io.BytesIO(_xslt))
_transform=etree.XSLT(_xslt_doc)


def _parse_xml(s):
	return _transform(fromstring(s.encode('utf-8'), parser=_parser)).getroot()


def get_cities(document=None):
	"""
	Connect to CITIES server and parse data
	"""
	max_retries = 5
	if document is None:
		print "Downloading from CITIES"
		# Exclude http proxy
		session = requests.session()
		session.trust_env = False
		i = 0
		document = None
		while document is None and i < max_retries:
			try:
				document = session.get(CITIES_URL, timeout=TIMEOUT, proxies={}).text
			except Exception as e:
				traceback.print_exc()
				i += 1
				if i == max_retries:
					print "Giving up"
					raise e
	# with bz2.BZ2File('/data/log/cities/%s.xml.bz2' % datetime2mysql(datetime.now()), 'w') as f:
	# 	f.write(document)
	print "Parsing XML"
	soup = _parse_xml(document)
	print "Building output"
	out = []
	buses = soup.getchildren()
	for bus in buses:
		if len(bus.find('Lat').attrib) > 0: #'xsi:nil' in bus.find('Lat').attrib:
			x, y = None, None
		else:
			lat = float(bus.find('Lat').text)
			lon = float(bus.find('Long').text)
			x, y = wgs84_to_gbfe(lon, lat)
		dt = mysql2datetime("%s %s" % (bus.find('DataRic').text, bus.find('OraRic').text))
		el = {
			'id_veicolo': bus.find('NumSoc').text,
			'x': x,
			'y': y,
			'progressiva': int(bus.find('ProgFerm').text),
			'dist_prec': int(bus.find('DistDaFerm').text),
			'id_percorso': bus.find('CodPerc').text, # Oppure CodPercAlt?
			'timestamp': dt,
			'id_linea': bus.find('Linea').text,
			'dest': bus.find('Dest').text,
			'cod_perc_alt': bus.find('CodPercAlt').text,
			'ferm_da_arr': int(bus.find('FermDaArr').text),
			'cod_corsa': bus.find('CodCorsa').text,
		}
		out.append(el)
	return out

def str2bool(s):
	return True if s == 'true' else False

def interroga_capolinea(id_palina):
	# Exclude http proxy
	session = requests.session()
	session.trust_env = False
	document = session.get(CITIES_URL_CAPOLINEA, timeout=2, params={'CodiceFermata': id_palina}).text
	# print "Parsing XML"
	soup = _parse_xml(document)
	# print "Building output"
	out = []
	buses = soup.getchildren()
	for bus in buses:
		el = {
			'id_veicolo': bus.find('NumeroSociale').text,
			'id_percorso': bus.find('CodicePercorso').text, # Oppure CodPercAlt?
			'id_linea': bus.find('Linea').text,
			'dest': bus.find('Destinazione').text,
			'teorica': str2bool(bus.find('Teorica').text),
			'previsione_partenza': bus.find('PrevisionePartenza').text,
			'ora_arrivo': bus.find('OraArrivo').text,
			'previsione_arrivo': bus.find('PrevisioneArrivo').text,
			'descrizione_percorso': bus.find('DescrizionePercorso').text,
			'codice_barrata': bus.find('CodiceBarrata').text,
			'cod_perc_alt': bus.find('CodicePercorsoAlternativo').text,
			'ferm_da_arr': int(bus.find('FermateDaArrivo').text),
			'cod_corsa': bus.find('CodiceCorsa').text,
			'a_capolinea': str2bool(bus.find('ACapolinea').text),
			'in_arrivo': str2bool(bus.find('InArrivo').text),
		}
		out.append(el)
	return out


def percorsi_veicoli(r):
	"""
	Restituisce i percorsi su cui sono attivi i veicoli
	"""
	veicoli = {}
	for id_palina in r.capilinea:
		print id_palina
		try:
			res = interroga_capolinea(id_palina)
			for el in res:
				veicoli[el['id_veicolo']] = el['id_percorso']
		except:
			traceback.print_exc()
	return veicoli



class AggiornatorePercorsi(Thread):
	def __init__(self, rete, queue, veicoli):
		Thread.__init__(self)
		self.rete = rete
		self.queue = queue
		self.quit_request = False
		self.veicoli = veicoli


	def run(self):
		# print "Aggiornatore percorsi, inizio thread", str(self)
		try:
			while not self.quit_request:
				p, tentativi_rimasti = self.queue.get_nowait()
				try:
					res = interroga_capolinea(p.id_palina)
					for el in res:
						if el['ferm_da_arr'] != -1:
							id_veicolo = el['id_veicolo']
							if id_veicolo in self.veicoli:
								old = self.veicoli[id_veicolo]
								if old['id_percorso'] == el['id_percorso']:
									# print "Veicolo %s duplicato, era su %s (%d fermate), ora su %s (%d fermate)" % (id_veicolo, old['id_percorso'], old['ferm_da_arr'], el['id_percorso'], el['ferm_da_arr'])
									# Il percorso è lo stesso, il capolinea ha la distanza massima in fermate
									if el['previsione_arrivo'] > old['previsione_arrivo']:
										el['tutti'] = old['tutti']
										self.veicoli[id_veicolo] = el
								else:
									# Il percorso è diverso, considero il percorso con la minima distanza in fermate
									if el['previsione_arrivo'] < old['previsione_arrivo']:
										el['tutti'] = old['tutti']
										self.veicoli[id_veicolo] = el
							else:
								self.veicoli[id_veicolo] = el
								self.veicoli[id_veicolo]['tutti'] = []
							self.veicoli[id_veicolo]['tutti'].append(el)
				except Exception, e:
					# traceback.print_exc()
					# print "** Timeout, %d tentativi rimasti" % tentativi_rimasti
					if tentativi_rimasti > 1:
						self.queue.put((p, tentativi_rimasti - 1))
					else:
						self.veicoli['-1'] += 1
		except Queue.Empty:
			pass
		except Exception, e:
			logging.error(traceback.format_exc())
		# print "Aggiornatore percorsi, fine thread", str(self)

	def quit(self):
		self.quit_request = True


def percorsi_veicoli_multithread(r, num_thread=6, timeout=timedelta(minutes=3), max_tentativi=5):
	veicoli = {'-1': 0}
	s = r.capilinea
	l = []
	for p in s:
		p = r.paline[p]
		if p.aggiornabile_infotp():
			l.append(p)
	r.random.shuffle(l)
	q = Queue.Queue()
	for p in l:
		q.put((p, max_tentativi))
	print "Aggiorno percorsi"
	threads = []
	for i in range(0, num_thread):
		t = AggiornatorePercorsi(r, q, veicoli)
		t.start()
		threads.append(t)
	tstop = datetime.now() + timeout
	j = num_thread
	for t in threads:
		n = datetime.now()
		if tstop > n:
			remaining = (tstop - n).seconds
			# print "\nREMAINING: %d seconds, %d threads" % (remaining, j)
			j -= 1
			t.join(remaining)
	for t in threads:
		t.quit()
	print "Aggiornamento percorsi completato, %d percorsi non aggiornati, %d veicoli" % (veicoli['-1'], len(veicoli) - 1)
	r.percorsi_veicoli_atac = veicoli


# Parametri:
# Timeout 2 secondi
# num_thread = 10
# max_tentativi = 5
# --> Wall time: 41 s