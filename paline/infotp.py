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

import logging
import urllib2
from BeautifulSoup import BeautifulSoup as Soup
import re
import time
import csv
from servizi.utils import datetime2mysql
from datetime import date, time, datetime, timedelta
from threading import Lock

delta = 30 # seconds
TIMEOUT = 3 # seconds

# disable proxy in 3 steps
# 1: define a proxy handler which does not use a proxy (empty dict)
h = urllib2.ProxyHandler({})
# 2: construct an opener
opener = urllib2.build_opener(h)
# 3: register the opener globally
urllib2.install_opener(opener)

LOG_INFOTP = False

infotp_log_file = [None, None]
lock = Lock()

def log_infotp(id_palina, s):
	if LOG_INFOTP:
		lock.acquire()
		try:
			if infotp_log_file[0] is None:
				f = open('infotp.log', 'a')
				infotp_log_file[0] = f
				infotp_log_file[1] = csv.writer(f)
			c = infotp_log_file[1]
			c.writerow([datetime2mysql(datetime.now()), id_palina, s.replace('\n', '')])
		except Exception, e:
			pass
		lock.release()

def call_infotp(id_palina):
	u = urllib2.urlopen('http://localhost/Xml_PrevNodo.php?IdFermata=%s' % id_palina)
	response = u.read().strip()
	u.close()
	logging.debug(response)
	if response.upper().find('ERROR') >= 0 or not response.endswith('</palina>'):
		raise Exception('Errore nella risposta di InfoTP')
	soup = Soup(response)
	log_infotp(id_palina, str(soup))
	return soup

def call_infotp_raw(id_palina):
	u = urllib2.urlopen('http://localhost/Xml_PrevNodo.php?IdFermata=%s' % id_palina)
	response = u.read()
	u.close()
	return response
	

def get_arriving_buses(id_palina, id_percorsi):
	"""
	id_percorsi: set
	"""
	out = {}
	soup = call_infotp(id_palina)
	bs = soup.findAll('linea')
	for b in bs:
		attrs = dict(b.attrs)
		if attrs['id_percorso'] in id_percorsi:
			out[attrs['id_veicolo']] = attrs
	return out

def catch_first_bus(id_palina, id_percorsi):
	"""
	Return the bus id of the first vehicle arriving
	
	id_percorsi: set of routes to wait for
	"""
	arriving_buses = {}
	percorsi = set()
	percorsi_capolinea = {}
	for id in id_percorsi:
		p = Percorsi.objects.get(pk=id)
		if p.partenza.pk == id_palina:
			percorsi_capolinea[(
				p.arrivo.pk,
				id
			)] = {}
		else:
			percorsi.add(id)
	# Per le partenze da capolinea, considero tutti i bus sul percorso.
	# Quando ne appare uno nuovo, significa che un nuovo bus e' partito
	# dal capolinea
	# Oppure quando un bus precedentemente 'A Capolinea' non e' piu' 
	# 'A Capolinea'
	for k in percorsi_capolinea:
		percorsi_capolinea[k] = get_arriving_buses(k[0], set([k[1]]))
	while True:
		a = get_arriving_buses(id_palina, percorsi)
		for k in arriving_buses:
			if k not in a:
				return arriving_buses[k]
		arriving_buses.update(a)
		logging.debug(arriving_buses)
		for k in percorsi_capolinea:
			bus_noti = percorsi_capolinea[k]
			bs = get_arriving_buses(k[0], set([k[1]]))
			for b in bus_noti:
				if bus_noti[b]['a_capolinea'] == 'S' and (b not in bs or bs[b]['a_capolinea'] != 'S'):
					return bs[b]
			for b in bs:
				if b not in bus_noti:
					if bs[b]['a_capolinea'] == 'S':
						percorsi_capolinea[k][bs[b]['id_veicolo']] = b
					return bs[b]
			logging.debug(bs)
		time.sleep(delta)
		
def wait_for_vehicle(id_palina, veicolo):
	"""
	Wait until bus passes through bus stop id_palina
	"""
	id_percorso = veicolo['id_percorso']
	id_veicolo = veicolo['id_veicolo']
	bs = get_arriving_buses(id_palina, set([id_percorso]))
	while id_veicolo in bs:
		time.sleep(delta)
		bs = get_arriving_buses(id_palina, set([id_percorso]))
		
		