# coding: utf-8

#
#    Copyright 2013-2016 Roma servizi per la mobilità srl
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

from bt import AVLTree as Avl
import pyximport; pyximport.install()
from models import *
from paline import cities
from datetime import datetime, timedelta, time, date
import Queue
from threading import Thread, Lock
from grafo import Arco, Nodo, Grafo, DijkstraPool
import shapefile
import math
from copy import copy
from time import sleep
import logging
import traceback
import geomath
import osm
import geocoder
from django.contrib.gis.geos import Point
from django.db import transaction as djangotransaction
from servizi.utils import datetime2compact, datetime2time, transaction, date2datetime
from servizi.utils import datetime2date, dateandtime2datetime, ricapitalizza
from servizi.utils import model2contenttype, contenttype2model, batch_qs, datetime2mysql
from servizi.models import Festivita
from parcheggi import models as parcheggi
import os, os.path
import settings
import tratto
from django import db
from django.db.models import Avg, Max, Min, Count, F
import os, os.path
from floatingvehicle import FVPath
from constance import config
import cPickle as pickle
from mercury.models import Mercury
from risorse import models as risorse
from ztl.views import Orari, orari_per_ztl
from ztl import models as ztl
import xmlrpclib
import tomtom
from collections import defaultdict
from pprint import pprint
from urllib_transport import UrllibTransport
from random import Random
# import gtfs_rt


LINEE_MINI = ['90', '542', '61', 'MEB', 'MEB1', '998', 'MEA', 'FR1']
#LINEE_MINI = ['012', '063', '90', '999', 'MEB', 'MEB1']
VALIDITA_TEMPO_ARCHI = timedelta(minutes=60)
# Per ogni ciclo di aggiornamento tempi archi, massimo numero di tentativi per ciascun arcoprint
MAX_PERIODO_PERCORSO_ATTIVO = timedelta(minutes=58)

MIN_PESO_VELOCITA = 0.1

TIMEOUT_VALIDITA_VEICOLO = timedelta(minutes=3)
AVANZAMENTO_INTERPOLATO = False

TIMEOUT_AGGIORNAMENTO_RETE = timedelta(seconds=90)
MAX_TENTATIVI_INFOTP = 5


class RetePalina(object):
	def __init__(self, id_palina, nome, soppressa=False):
		object.__init__(self)
		self.id_palina = id_palina
		self.nome = nome
		self.nome_ricapitalizzato = ricapitalizza(nome)
		self.arrivi = {}
		self.ultimo_aggiornamento = None
		self.x = -1
		self.y = -1
		self.fermate = {}
		self.tratti_percorsi_precedenti = []
		self.tratti_percorsi_successivi = []
		self.soppressa = soppressa
		self.ferroviaria = False
		# Nota: le paline soppresse esistono, ed esistono anche le corrispondenti fermate.
		#       Nel grafo, però, esistono solo i nodi relativi alle fermate, NON quelli relativi alle paline.
		#       In questo modo sarà possibile transitare per le fermate ma non salire/scendere dal mezzo.

	def serializza_dinamico(self):
		return {
			'type': 'RetePalina',
			'id': self.id_palina,
			'arrivi': self.arrivi,
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
		}

	def deserializza_dinamico(self, rete, res):
		self.arrivi = res['arrivi']
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']

	def serializza(self):
		return {
			'id': self.id_palina,
			'x': self.x,
			'y': self.y,
		}

	def deserializza(self, res):
		self.x = res['x']
		self.y = res['y']

	def log_arrivi(self):
		if settings.CPD_LOG_PER_STATISTICHE:
			for k in self.fermate:
				f = self.fermate[k]

				if f.tratto_percorso_successivo is None:
					#print "Capolinea percorso " + k
					f.log_arrivi()

	def propaga_arrivi_indietro(self):
		for k in self.fermate:
			f = self.fermate[k]
			if f.aggiornabile_infotp() and f.is_capolinea():
				p = f.rete_percorso
				p.begin_aggiorna_veicoli()
				f.propaga_arrivi_indietro()
				p.end_aggiorna_veicoli()

	def distanza(self, p):
		if self.x == -1 or p.x == -1:
			return None
		a = self.x - p.x
		b = self.y - p.y
		return math.sqrt(a * a + b * b)

	def aggiornabile_infotp(self):
		"""
		E' il capolinea per almeno una fermata di cui interessa interrogare InfoTP
		"""
		for k in self.fermate:
			f = self.fermate[k]
			if f.aggiornabile_infotp():
				return True
		return False


class RetePercorso(object):
	def __init__(self, id_percorso, id_linea, tipo, descrizione, soppresso, gestore):
		object.__init__(self)
		self.id_percorso = id_percorso
		self.id_linea = id_linea
		self.tipo = tipo
		self.descrizione = descrizione if descrizione is not None else id_linea
		self.soppresso = soppresso and tipo != 'FR'
		self.gestore = gestore
		self.fv = FVPath()
		# Tratti del percorso, in ordine
		self.tratti_percorso = []
		self.frequenza = []
		self.tempo_stat_orari = []
		# Mapping tra gli indici delle fermate non soppresse (0-based) e i tratti di percorso che iniziano con tali fermate
		# L'indice del capolinea finale non è mappato, perché esso non dà origine a un tratto di percorso
		self.map_fermate_tratti = []
		self.dist = 0
		self.veicoli = {}
		self.veicoli_problematici = {}
		self.ultimo_aggiornamento = None
		self.orario_inizio_aggiornamento_veicoli = None
		self.segmenti = None
		for i in range(0, 7):
			self.frequenza.append([(0.0, -1, -1) for j in range(0, 24)])

	def __repr__(self):
		return "Percorso %s (linea %s)" % (self.id_percorso, self.id_linea)

	def serializza(self):
		return {
			'id': self.id_percorso,
			'frequenza': self.frequenza,
			'tempo_stat_orari': self.tempo_stat_orari,
		}

	def deserializza(self, res):
		self.frequenza = res['frequenza']
		self.tempo_stat_orari = res['tempo_stat_orari']

	def init_mapping_fermate_non_soppresse(self):
		n_tratto = 0
		for tp in self.tratti_percorso:
			f = tp.s
			if not f.rete_palina.soppressa:
				self.map_fermate_tratti.append(n_tratto)
			n_tratto += 1

	def get_tratto_e_distanza_da_fermata(self, n_fermata, dist_fermata):
		"""
		Restituisce l'indice del tratto, il tratto e la distanza a partire dalla posizione linearizzata in fermate

		Il metodo converte la posizione linearizzata, espressa in termini di fermate "non soppresse" e distanza
		dall'ultima fermata, in una nuova posizione linearizzata espressa in termini di tratti di percorso:
		restituisce una terna (indice_tratto_percorso, tratto_percorso, distanza_da_inizio_tratto_percorso)
		"""
		n_tratto = self.map_fermate_tratti[n_fermata]
		tp = self.tratti_percorso[n_tratto]
		dist = tp.rete_tratto_percorsi.dist
		if dist < dist_fermata:
			dist_fermata -= dist
			tp = tp.t.tratto_percorso_successivo
			n_tratto += 1
		return (n_tratto, tp, dist_fermata)

	def begin_aggiorna_veicoli(self):
		self.orario_inizio_aggiornamento_veicoli = datetime.now()

	def end_aggiorna_veicoli(self):
		da_cancellare = []
		for id_veicolo in self.veicoli:
			v = self.veicoli[id_veicolo]
			if v.ultimo_aggiornamento < self.orario_inizio_aggiornamento_veicoli:
				da_cancellare.append(id_veicolo)
		for id_veicolo in da_cancellare:
			del self.veicoli[id_veicolo]
		self.orario_inizio_aggiornamento_veicoli = None

	def serializza_dinamico(self):
		return {
			'type': 'RetePercorso',
			'id': self.id_percorso,
			'veicoli': [id_veicolo for id_veicolo in self.veicoli],
		}

	def deserializza_dinamico(self, rete, res):
		self.veicoli = {}
		for id_veicolo in res['veicoli']:
			if not id_veicolo in rete.veicoli:
				rete.veicoli[id_veicolo] = ReteVeicolo(id_veicolo)
			self.veicoli[id_veicolo] = rete.veicoli[id_veicolo]

	def iter_punti(self):
		"""
		Restituisce un iteratore sui punti della polilinea, dall'ultimo al primo
		"""
		tp = self.tratti_percorso[0]
		while tp is not None:
			punti = tp.rete_tratto_percorsi.punti
			n = len(punti)
			for i in range(n):
				yield punti[i]
			tp = tp.t.tratto_percorso_successivo

	def iter_punti_rev(self):
		"""
		Restituisce un iteratore sui punti della polilinea, dall'ultimo al primo
		"""
		tp = self.tratti_percorso[-1]
		while tp is not None:
			punti = tp.rete_tratto_percorsi.punti
			n = len(punti)
			for i in range(n-1, -1, -1):
				yield punti[i]
			tp = tp.s.tratto_percorso_precedente

	def set_punti(self):
		self.segmenti = geocoder.SegmentGeocoder()
		punti = list(self.iter_punti())
		for i in range(1, len(punti)):
			self.segmenti.add_segment(punti[i-1], punti[i], i)
		self.segmenti.freeze()

	def linearizza(self, p):
		"""
		Trasforma il punto p (coppia x, y) nella posizione linearizzata

		Restituisce un dizionario con le seguenti chiavi:
		- distanza_capolinea: distanza dal capolinea iniziale
		- tratto_percorso: tratto_percorso a cui appartiene il punto
		- distanza_inizio_tratto: distanza dall'inizio del tratto
		- distanza_2d: distanza 2D del punto dal segmento
		- progressiva: progressivo del tratto di percorso (partendo da 1 per il primo tratto)
		"""
		i, dist_tratto, dist_inizio = self.segmenti.project(p)

		residua = dist_inizio
		tp = self.tratti_percorso[0]
		i = 0

		while True:
			dist = tp.rete_tratto_percorsi.dist
			tratto_successivo = tp.t.tratto_percorso_successivo
			i += 1
			if residua < dist or tratto_successivo is None:
				return {
					'distanza_capolinea': dist_inizio,
					'tratto_percorso': tp,
					'distanza_inizio_tratto': residua,
					'distanza_2d': dist_tratto,
					'progressiva': i,
				}
			residua -= dist
			tp = tratto_successivo

	def linear_to_coord(self, distanza_capolinea):
		"""
		A partire dalla posizione linearizzata, calcola coordinate e direzione del veicolo

		Restituisce una terna (lng, lat, azimuth)
		"""
		op = None
		mp = None
		d = distanza_capolinea
		for p in self.iter_punti_rev():
			if op is not None:
				dp = geomath.distance(p, op)
				if d < dp:
					frac = d / dp
					#print "frac = ", frac
					mp = (op[0] + frac * (p[0] - op[0]), op[1] + frac * (p[1] - op[1]))
					#print "Posizione: ", mp
					break
				d -= dp
			op = p
			#print "Fine ciclo, distanza residua", d2
		if mp is None:
			return None
		# p:  nuovo punto
		# op: vecchio punto
		# mp: posizione interpolata
		mpw = gbfe_to_wgs84(*mp)
		return (mpw[0], mpw[1], geomath.azimuth_deg(p, op))

	def campioni_fvd(self, orario_min):
		ss = self.fv.speed
		out = []
		for s in reversed(ss):
			t, p, s, id = s
			if orario_min is not None and t < orario_min:
				break
			res = self.linear_to_coord(p)
			if res is None:
				print "Errore nella posizione del veicolo"
				continue
			lng, lat, azimuth = res
			out.append({
				'id_veicolo': id,
				'data_acquisizione': datetime2mysql(t),
				'lon': lng,
				'lat': lat,
				'direzione': int(azimuth),
				'velocita': int(s * 3.6),
				'stato': 1,
				'quality': 3,
				'classe_veicolo': 'B',
				'id_sistema': 'A',
				'distanza': int(self.dist - p),
			})
		return out

	def log_tempo_attesa(self, data=None, ora=None):
		arrivi = self.tratti_percorso[-1].t.arrivi
		if len(arrivi) > 0:
			tempo = arrivi[0]['tempo']
			if tempo > -1:
				if data is None:
					t = datetime.now()
					ora = datetime2time(t)
					data = datetime2date(t)
				LogTempoAttesaPercorso(
					id_percorso=self.id_percorso,
					data=data,
					ora=ora,
					tempo=tempo
				).save()


	def stampa_tempi(self):
		print " *** Tempi percorso %s (linea %s) ***" % (self.id_percorso, self.id_linea)
		i = 0
		for tp in self.tratti_percorso:
			i += 1
			t = tp.rete_tratto_percorsi
			s = str(t.tempo_percorrenza)
			#else:
			#	s = str(t.tempo_percorrenza_interpolato) + " (I)"
			print "%d - %s" % (i, s)

	def calcola_distanze(self):
		self.tratti_percorso[0].s.distanza_da_partenza = 0
		d = 0
		for tp in self.tratti_percorso:
			d += tp.rete_tratto_percorsi.dist
			tp.t.distanza_da_partenza = d

	def get_destinazione(self):
		return self.tratti_percorso[-1].t.rete_palina.nome_ricapitalizzato


	def calcola_percorrenze(self):
		dist_rem = self.dist
		n = datetime.now()
		for t in self.tratti_percorso:
			dist = t.rete_tratto_percorsi.dist
			if dist is None:
				logging.error("Distanza non disponibile per percorso %s (linea %s)" % (self.id_percorso, self.id_linea))
				return
			nd = dist_rem - dist
			v, w = self.fv.compute_speed(n, dist_rem, nd)
			#print "SPEED: ", v, t.weight_tempo_percorrenza
			if v >= 0 and w >= 0:
				t.tempo_percorrenza = dist / v
				t.weight_tempo_percorrenza = w
			else:
				t.weight_tempo_percorrenza = -1
				#print "Non disponibile"
			dist_rem = nd
		#print "Distanza finale: ", dist_rem

	def get_fermate(self):
		fs = []
		for tp in self.tratti_percorso:
			fs.append(tp.s)
		fs.append(tp.t)
		return fs

	def get_paline(self):
		return [f.rete_palina for f in self.get_fermate()]

	def is_circolare(self):
		return self.tratti_percorso[0].s.rete_palina == self.tratti_percorso[-1].t.rete_palina

	def aggiorna_posizione_veicoli(self):
		if AVANZAMENTO_INTERPOLATO:
			veicoli_spostati = {}
			veicoli_propaganti = {}
			n = datetime.now()
			for tpo in self.tratti_percorso:
				fermata = tpo.t
				fermata.reset_arrivi()
				for id_veicolo in tpo.veicoli:
					v = tpo.veicoli[id_veicolo]
					if v.is_valido():
						veicoli_spostati[id_veicolo] = (v, v.distanza_successiva, (n - v.ultima_interpolazione).seconds)
				tpi = tpo.rete_tratto_percorsi
				dist = tpi.dist
				velocita = tpi.get_velocita()
				da_eliminare = []
				for id_veicolo in veicoli_spostati:
					v, s, t = veicoli_spostati[id_veicolo]
					if s == 0:
						s = dist
					if velocita < 0:
						da_eliminare.append(id_veicolo)
						veicoli_propaganti[id_veicolo] = (v, -1, None, 1)
					else:
						ds = velocita * t
						if ds < s:
							da_eliminare.append(id_veicolo)
							veicoli_propaganti[id_veicolo] = (v, s - ds, 0, 1)
							v.aggiorna_posizione_interpolata(tpo, ds, n)
						else:
							veicoli_spostati[id_veicolo] = (v, 0, t - (s / velocita))
				for id_veicolo in da_eliminare:
					del veicoli_spostati[id_veicolo]
				for id_veicolo in veicoli_propaganti:
					v, s, t, ferm = veicoli_propaganti[id_veicolo]
					if s < 0 or velocita < 0:
						fermata.add_arrivo(v, None, ferm)
						veicoli_propaganti[id_veicolo] = (v, -1, -1, ferm + 1)
					else:
						ds = dist - s
						dt = ds / velocita
						fermata.add_arrivo(v, n + timedelta(seconds=t + dt), ferm)
						veicoli_propaganti[id_veicolo] = (v, 0, t + dt, ferm + 1)
		# else:
			# Elimino veicoli vecchi
			# for tpo in self.tratti_percorso:
			# 	da_cancellare = []
			# 	arrivi = tpo.t.arrivi
			# 	for a in arrivi:
			# 		id_veicolo = a['id_veicolo']
			# 		if id_veicolo in self.veicoli:
			# 			v = self.veicoli[id_veicolo]
			# 			if not v.is_valido():
			# 				da_cancellare.append(a)
			# 		else:
			# 			da_cancellare.append(a)
			# 	for a in da_cancellare:
			# 		arrivi.remove(a)


	def stato(self):
		"""
		Restituisce informazioni sullo stato del percorso: fermate, tratti di percorso ecc.
		"""
		out = {
			'fermate': [],
		}
		s = self.tratti_percorso[0].s.rete_palina
		out['fermate'].append({
			'id_palina': s.id_palina,
			'nome': s.nome,
			'soppressa': s.soppressa,
			'nome_ricapitalizzato': s.nome_ricapitalizzato,
			'stato_traffico': 0,
		})
		n = datetime.now()
		for t in self.tratti_percorso:
			stato = -1
			tp = t.rete_tratto_percorsi
			v = -1
			if tp.ultimo_aggiornamento is not None and n - tp.ultimo_aggiornamento < VALIDITA_TEMPO_ARCHI:
				v = 3.6 * tp.dist / tp.tempo_percorrenza
				if v <= 5:
					stato = 1
				elif 5 < v <= 10:
					stato = 2
				elif 10 < v <= 15:
					stato = 3
				else:
					stato = 4
			t = t.t.rete_palina
			out['fermate'].append({
				'id_palina': t.id_palina,
				'nome': t.nome,
				'soppressa': t.soppressa,
				'nome_ricapitalizzato': t.nome_ricapitalizzato,
				'stato_traffico': stato,
			})
		return out

	def get_frequenza(self, dt=None):
		if dt is None:
			dt = datetime.now()
		d = Festivita.get_weekday(dt, compatta_feriali=True)
		t_prog, da, a = self.frequenza[d][dt.hour]
		# print "Frequenza percorso:", t_prog, da, a
		if not (da <= dt.minute <= a):
			return None
		else:
			return round(t_prog / 60.0)

	def statistiche(self):
		now = datetime.now()
		attesa_totale = 0
		attesa_max = None
		cnt = 0
		tempo_totale = 0
		distanza_totale = 0

		for t in self.tratti_percorso:
			f = t.t
			tempo = f.get_primo_arrivo(now)
			if tempo is not None:
				tempo = tempo[0]
				attesa_totale += tempo
				attesa_max = max(tempo, attesa_max)
				cnt += 1
			tp = t.rete_tratto_percorsi
			if tp.tempo_percorrenza > 0:
				tempo_totale += tp.tempo_percorrenza
				distanza_totale += tp.dist

		vic = 0
		vac = 0

		for id_veicolo in self.veicoli:
			v = self.veicoli[id_veicolo]
			if v.a_capolinea:
				vac += 1
			else:
				vic += 1

		freq = self.get_frequenza(now)
		indice_attesa = None
		if freq is not None and attesa_max is not None:
			indice_attesa = attesa_max / (freq * 60.0)

		return {
			'attesa_media': None if cnt == 0 else int(round(attesa_totale / (60.0 * cnt))),
			'attesa_max': None if attesa_max is None else int(round(attesa_max / 60.0)),
			'veicoli_in_corsa': vic,
			'veicoli_capolinea': vac,
			'velocita_media': None if distanza_totale == 0 else (3.6 * distanza_totale / tempo_totale),
			'frequenza_programmata': None if freq is None else int(freq),
			'indice_attesa': indice_attesa,
		}

	def destinazione(self):
		return self.tratti_percorso[-1].t.rete_palina.nome_ricapitalizzato

	def esporta_come_shape(self, path, gbfe=False):
		"""
		Esporta il percorso come coppia di shapefile, uno per il percorso e uno per le fermate

		path: cartella nella quale creare gli shapefile
		Il nome degli shapefile ha lo schema seguente:
		LINEA_PERCORSO_percorso.shp/dbf/...
		LINEA_PERCORSO_fermate.shp/dbf/...
		"""
		base_file_name = "{}_{}_".format(self.id_linea, self.id_percorso)
		with geomath.zipped_shapefile(shapefile.POLYLINE, path, base_file_name + "percorso", gbfe) as shp_p:
			with geomath.zipped_shapefile(shapefile.POINT, path, base_file_name + "fermate", gbfe) as shp_f:
				shp_p.autoBalance = 1
				shp_f.autoBalance = 1
				shp_f.field('ID_PAL', 'C', '10')
				shp_f.field('NOME_PAL', 'C', '40')
				shp_f.field('PROGR', 'N', '10')
				shp_p.field('ID_LINEA', 'C', '10')
				shp_p.field('ID_PERC', 'C', '10')
				shp_p.field('ID_PAL_S', 'C', '10')
				shp_p.field('NOME_PAL_S', 'C', '40')
				shp_p.field('PROGR', 'N', '10')
				shp_p.field('ID_PAL_T', 'C', '10')
				shp_p.field('NOME_PAL_T', 'C', '40')
				f = self.tratti_percorso[0].s
				i = 0
				palina_old = None
				while f is not None:
					pl = f.rete_palina
					if gbfe:
						lon, lat = pl.x, pl.y
					else:
						lon, lat = gbfe_to_wgs84(pl.x, pl.y)
					shp_f.point(lon, lat)
					shp_f.record(
						ID_PAL=pl.id_palina,
						NOME_PAL=pl.nome,
						PROGR=i,
					)
					if palina_old is not None:
						line = []
						punti = f.tratto_percorso_precedente.rete_tratto_percorsi.punti
						for pt in punti:
							if gbfe:
								ptw = pt
							else:
								ptw = gbfe_to_wgs84(*pt)
							line.append(ptw)
						shp_p.line(parts=[line])
						shp_p.record(
							ID_LINEA=self.id_linea,
							ID_PERC=self.id_percorso,
							ID_PAL_S=palina_old.id_palina,
							NOME_PAL_S=palina_old.nome,
							ID_PAL_T=pl.id_palina,
							NOME_PAL_T=pl.nome,
							PROGR=i,
						)
					palina_old = pl
					i += 1
					f = f.tratto_percorso_successivo.t if f.tratto_percorso_successivo is not None else None


class ReteTrattoPercorsi(object):
	"""
	Rappresenta un tratto fra due paline, condiviso fra uno o più percorsi
	"""
	def __init__(self, s, t, rete):
		object.__init__(self)
		self.s = s
		self.t = t
		s.tratti_percorsi_successivi.append(self)
		t.tratti_percorsi_precedenti.append(self)
		self.percorsi = {}
		self.tempo_percorrenza = -1
		self.ultimo_aggiornamento = None
		self.tempo_percorrenza_stat_orari = []
		self.punti = []
		self.dist = None
		self.rete = rete
		self.segmenti = None #geocoder.SegmentGeocoder()

		self.infotp = False
		self.tratti_percorso = []


	def get_id(self):
		return (self.s.id_palina, self.t.id_palina)

	def serializza_dinamico(self):
		return {
			'type': 'ReteTrattoPercorsi',
			'id': self.get_id(),
			'tempo_percorrenza': self.tempo_percorrenza,
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
		}

	def deserializza_dinamico(self, rete, res):
		self.tempo_percorrenza = res['tempo_percorrenza']
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']


	def serializza(self):
		return {
			'id': self.get_id(),
			'punti': self.punti,
			'dist': self.dist,
			'tempo_percorrenza_stat_orari': self.tempo_percorrenza_stat_orari,
		}

	def deserializza(self, res):
		self.set_punti(res['punti'])
		self.set_dist(res['dist'])
		self.tempo_percorrenza_stat_orari = res['tempo_percorrenza_stat_orari']

	def aggiungi_tratto_percorso(self, tp):
		self.percorsi[tp.rete_percorso.id_percorso] = tp
		if tp.rete_percorso.tipo in TIPI_LINEA_INFOTP:
			self.infotp = True

	def add_tratto_percorso(self, tp):
		self.tratti_percorso.append(tp)

	def media_tempi_percorrenza(self, logging=False):
		tot = 0
		cnt = 0
		for t in self.tratti_percorso:
			#print "TRATTO, weight=", t.weight_tempo_percorrenza, t.tempo_percorrenza
			if t.weight_tempo_percorrenza > 0:
				if t.tempo_percorrenza < 0:
					print "VELOCITA ARCO SINGOLO NEGATIVA", t.tempo_percorrenza, t.weight_tempo_percorrenza
				if self.dist < 0:
					print "DISTANZA NEGATIVA"
				cnt += t.weight_tempo_percorrenza
				tot += t.weight_tempo_percorrenza * (self.dist / t.tempo_percorrenza)
				#print "Considero la velocità: ", (self.dist / t.tempo_percorrenza)
		if cnt > MIN_PESO_VELOCITA:
			velocita = tot / cnt
			#print "La velocità media: ", velocita
			self.tempo_percorrenza = self.dist / velocita
			if self.tempo_percorrenza < 0:
				print "TEMPO RISULTANTE < 0", self.tempo_percorrenza
			n = datetime.now()
			self.ultimo_aggiornamento = n
			if logging and settings.CPD_LOG_PER_STATISTICHE:
				LogTempoArco(
					id_palina_s=self.s.id_palina,
					id_palina_t=self.t.id_palina,
					data=datetime2date(n),
					ora=datetime2time(n),
					tempo=velocita,
					peso=cnt,
				).save()
		#print "Calcolato tempo percorrenza:", cnt, self.tempo_percorrenza

	def get_velocita(self):
		if self.ultimo_aggiornamento is None or datetime.now() - self.ultimo_aggiornamento > VALIDITA_TEMPO_ARCHI:
			return -1
		if self.tempo_percorrenza == -1 or self.dist is None:
			return -1
		return self.dist / self.tempo_percorrenza


	def distanza(self):
		return self.dist
		#return self.s.distanza(self.t)

	def linearizza(self, p):
		"""
		Restituisce la distanza lineare della proiezione di p sul tratto dall'inizio del tratto
		"""
		i, dist_tratto, dist_inizio = self.segmenti.project(p)
		return dist_inizio

	def set_dist(self, dist):
		if dist is not None:
			delta = 0
			if self.dist is not None:
				delta = -self.dist
			self.dist = dist
			delta += dist

			for k in self.percorsi:
				self.percorsi[k].rete_percorso.dist += delta

	def set_punti(self, punti):
		self.segmenti = geocoder.SegmentGeocoder()
		self.punti = punti
		for i in range(1, len(punti)):
			self.segmenti.add_segment(punti[i-1], punti[i], i)
		self.segmenti.freeze()

	def sposta_paline_su_percorso(self):
		self.s.x, self.s.y = self.punti[0][0], self.punti[0][1]
		self.t.x, self.t.y = self.punti[-1][0], self.punti[-1][1]


class ReteFermata(object):
	"""
	Rappresenta una fermata di un percorso presso una palina
	"""
	def __init__(self, id_fermata, rete_palina, rete_percorso, rete):
		self.id_fermata = id_fermata
		self.rete_palina = rete_palina
		self.rete_percorso = rete_percorso
		self.rete = rete
		# Gli arrivi qui sono ordinati per tempo di attesa, e ricalcolati di frequente
		# a partire dagli arrivi al capolinea di destinazione (vecchio metodo)
		# oppure direttamente a partire dalla posizione dei veicoli (nuovo metodo)
		self.arrivi = []
		self.arrivi_temp = []
		self.ultimo_aggiornamento = None
		rete_palina.fermate[rete_percorso.id_percorso] = self
		if rete_percorso.tipo in TIPI_LINEA_FERRO:
			rete_palina.ferroviaria = True
		self.tratto_percorso_precedente = None
		self.tratto_percorso_successivo = None
		self.distanza_da_partenza = -1

	def is_valida(self):
		return self.ultimo_aggiornamento is not None and datetime.now() - self.ultimo_aggiornamento <= TIMEOUT_VALIDITA_VEICOLO

	def serializza_dinamico(self):
		arr = []
		for el in self.arrivi:
			el2 = copy(el)
			if 'tratto_percorso' in el2:
				el2['tratto_percorso'] = el2['tratto_percorso'].get_id()
			arr.append(el2)
		return {
			'type': 'ReteFermata',
			'id': self.id_fermata,
			'arrivi': arr,
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
		}

	def deserializza_dinamico(self, rete, res):
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']
		arr = res['arrivi']
		for a in arr:
			if 'tratto_percorso' in a:
				a['tratto_percorso'] = rete.tratti_percorso[a['tratto_percorso']]
		self.arrivi = arr

	def aggiornabile_infotp(self):
		return self.rete_percorso.gestore in GESTORI_INFOTP and self.rete_percorso.tipo in TIPI_LINEA_INFOTP


	def propaga_arrivi_indietro(self):
		tratto = self.tratto_percorso_precedente
		if tratto is not None:
			t = tratto.rete_tratto_percorsi.tempo_percorrenza
			dist = tratto.rete_tratto_percorsi.dist
			if dist is None:
				logging.error("Distanza NONE su percorso %s (%s)" % (self.rete_percorso.id_percorso, self.rete_percorso.id_linea))
				return
			fermata = tratto.s
			fermata.reset_arrivi_temp()
			for el in self.arrivi_temp:
				#print "Veicolo: %s - Fermate: %d, distanza: %f" % (el['id_veicolo'], el['fermate'], el['distanza'])
				if el['fermate'] > 0:
					el = copy(el)
					el['tempo'] -= t
					el['fermate'] -= 1
					if el['distanza'] > 0:
						el['distanza'] -= dist
					fermata.arrivi_temp.append(el)
					if el['a_capolinea']:
						pass
						#print "Ho propagato indietro bus a capolinea, distanza: %d" % el['fermate']
					#TODO: aggiornare o ELIMINARE distanza, ecc.
			fermata.propaga_arrivi_indietro()
		else:
			self.reset_arrivi()
			#print "Arrivato al capolinea di partenza, ora propago in avanti"
			#print "Questi sono i veicoli attuali"
			#print self.arrivi_temp
			self.propaga_arrivi_avanti()

	def is_capolinea(self):
		if self.rete_percorso.is_circolare():
			t = self.tratto_percorso_successivo
			if t is None:
				return False
			return t.t.tratto_percorso_successivo is None
		else:
			return self.tratto_percorso_successivo is None

	def is_capolinea_partenza(self):
		return self.tratto_percorso_precedente is None

	def propaga_arrivi_avanti(self):
		tratto = self.tratto_percorso_successivo
		#self.ultimo_aggiornamento = datetime.now()
		if tratto is not None:
			rtp = tratto.rete_tratto_percorsi
			if rtp.ultimo_aggiornamento is not None and datetime.now() - rtp.ultimo_aggiornamento < VALIDITA_TEMPO_ARCHI:
				t = tratto.rete_tratto_percorsi.tempo_percorrenza
			else:
				t = -1
			dist = tratto.rete_tratto_percorsi.dist
			punti = [x for x in reversed(tratto.rete_tratto_percorsi.punti)]
			fermata = tratto.t
			fermata.reset_arrivi()
			for el in self.arrivi_temp:
				if el['fermate'] == 0:
					#print "Tratto: ", tratto.rete_tratto_percorsi.s.id_palina, tratto.rete_tratto_percorsi.t.id_palina
					el = copy(el)
					el['fermate'] = 1
					el['tratto_percorso'] = tratto
					if not el['a_capolinea']:
						d2 = el['distanza']
						if d2 == -1 or d2 == -2:
							d2 = dist / 2
						else:
							d2 += dist
						if d2 >= 0 and d2 <= dist:
							el['tempo'] = t * d2 / dist
							el['distanza_primo_tratto'] = d2
							op = None
							mp = None
							for p in punti:
								if op is not None:
									dp = geomath.distance(p, op)
									if d2 < dp:
										frac = d2 / dp
										#print "frac = ", frac
										mp = (op[0] + frac * (p[0] - op[0]), op[1] + frac * (p[1] - op[1]))
										#print "Posizione: ", mp
										break
									d2 -= dp
								op = p
								#print "Fine ciclo, distanza residua", d2
							if mp is None:
								mp = op
						elif d2 < 0:
							mp = punti[0]
							el['distanza_primo_tratto'] = 0
							el['tempo'] = 0
						else:
							mp = punti[-1]
							el['distanza_primo_tratto'] = dist
							el['tempo'] = t
						el['in_arrivo'] = True
					else:
						# A capolinea
						el['tempo'] = max(el['tempo'], t)
						el['distanza_primo_tratto'] = dist
						mp = punti[-1]
					if t == -1:
						el['tempo'] = -1
					fermata.arrivi.append(el)
					dotazioni = {
						'pedana': el['pedana'],
						'aria': el['aria'],
						'moby': el['moby'],
						'meb': el['meb'],
					}
					self.rete.aggiorna_posizione_bus(el['id_veicolo'], el['distanza_capolinea'], el['distanza_primo_tratto'], tratto, el['a_capolinea'], mp, dotazioni=dotazioni, propaga=False)
			for el in self.arrivi:
				el = copy(el)
				if el['tempo'] >= 0 and t >= 0:
					el['tempo'] += t
				else:
					el['tempo'] = -1
				el['fermate'] += 1
				el['distanza'] += dist
				el['in_arrivo'] = False
				fermata.arrivi.append(el)
			fermata.propaga_arrivi_avanti()

	def log_arrivi(self):
		logged = set()
		for a in self.arrivi_temp:
			idp = a['id_percorso']
			t = a['tempo']
			if t > -1 and not idp in logged:
				logged.add(idp)
				LogTempoAttesaPercorso(
					id_percorso=idp,
					data=date.today(),
					ora=datetime2time(datetime.now()),
					tempo=t,
				).save()

	def get_primo_arrivo(self, t, rev=False):
		"""
		Restituisce il primo arrivo del bus a partire dal tempo t (secondi), None se non disponibile

		Restituisce una coppia (t, el), dove el è il dizionario con le info sull'arrivo del veicolo
		"""
		#TODO: rendere la funzione efficiente con un'opportuna struttura dati!
		if self.ultimo_aggiornamento is None:
			return None
		diff = (t - self.ultimo_aggiornamento).seconds
		old = None
		for a in self.arrivi:
			if a['tempo'] - diff >= 0 and not a['a_capolinea']:
				if not rev:
					return (a['tempo'] - diff, a)
				else:
					if old is not None:
						return (diff - old['tempo'], old)
					return None
			old = a
		return None

	def reset_arrivi(self):
		self.arrivi = []
		self.ultimo_aggiornamento = datetime.now()

	def reset_arrivi_temp(self):
		self.arrivi_temp = []

	def aggiungi_arrivo_temp(self, arrivo):
		a = copy(arrivo)
		self.arrivi_temp.append(a)

	def ordina_arrivi_temp(self, aggiorna_fv):
		n = datetime.now()
		for d in self.arrivi_temp:
			if aggiorna_fv and d['distanza'] > 0:
				self.rete_percorso.fv.add(d['id_veicolo'], n, d['distanza'])
		self.arrivi_temp.sort(key=lambda x: x['tempo'])

	def add_arrivo(self, veicolo, orario_arrivo, dist_fermate):
		"""
		Nuovo metodo per aggiungere gli arrivi
		"""
		n = datetime.now()
		self.ultimo_aggiornamento = n
		secondi = -1
		if orario_arrivo is not None:
			if orario_arrivo > n:
				secondi = (orario_arrivo - n).seconds
			else:
				secondi = 0
		if secondi > (10 + 4 * dist_fermate) * 60:
			secondi = -1
		percorso = veicolo.tratto_percorso.rete_percorso
		secondi_attesa = secondi
		self.arrivi.append({
			'tempo': secondi_attesa,
			'id_percorso': percorso.id_percorso,
			'id_veicolo': veicolo.id_veicolo,
			'id_linea': percorso.id_linea,
			'destinazione': percorso.get_destinazione(),
			#'annuncio_infotp': '', # Composto su richiesta da getVeicoliCaching
			#'posizione': -1, # Non prevista nel servizio web
			'fermate': dist_fermate,
			#'distanza': -1, # Non prevista nel servizio web
			'pedana': veicolo.dotazioni['pedana'],
			'aria': veicolo.dotazioni['aria'],
			'moby': veicolo.dotazioni['moby'],
			'meb': veicolo.dotazioni['meb'],
			'a_capolinea': veicolo.a_capolinea,
			'in_arrivo': secondi_attesa < INTERVALLO_IN_ARRIVO,
		})
		self.arrivi.sort(key=lambda x: x['tempo'])


	def elimina_veicolo(self, veicolo):
		"""
		Elimina le previsioni di arrivo per il veicolo passato; restituisce True se erano presenti.
		"""
		id_veicolo = veicolo.id_veicolo
		for a in self.arrivi:
			if a['id_veicolo'] == id_veicolo:
				self.arrivi.remove(a)
				return True
		return False

def analizza_percorso(pe):
	for tp in pe.tratti_percorso:
		print "Percorrenza arco: " + str(tp.rete_tratto_percorsi.tempo_percorrenza)
		f = tp.t
		p = f.rete_palina
		for a in f.arrivi:
			idv = a['id_veicolo']
			if idv in p.arrivi:
				print "%s fermata %d: Differenza %s" % (str(idv), a['fermate'], str(a['tempo'] - p.arrivi[idv]['tempo']))
			else:
				print "%s fermata %d: Bus non presente in palina" % (str(idv), a['fermate'])

class ReteTrattoPercorso(object):
	"""
	Rappresenta un tratto di percorso fra due fermate
	"""
	def __init__(self, rete_percorso, rete_tratto_percorsi, rete_fermata_s, rete_fermata_t):
		self.rete_percorso = rete_percorso
		self.rete_tratto_percorsi = rete_tratto_percorsi
		rete_tratto_percorsi.add_tratto_percorso(self)
		self.s = rete_fermata_s
		self.t = rete_fermata_t
		self.s.tratto_percorso_successivo = self
		self.t.tratto_percorso_precedente = self
		rete_tratto_percorsi.aggiungi_tratto_percorso(self)
		rete_percorso.tratti_percorso.append(self)
		self.tempo_percorrenza = 0
		self.weight_tempo_percorrenza = 0
		self.veicoli = {}

	def get_id(self):
		return (self.s.id_fermata, self.t.id_fermata)

	def serializza_dinamico(self):
		return {
			'type': 'ReteTrattoPercorso',
			'id': self.get_id(),
			'tempo_percorrenza': self.tempo_percorrenza,
			'weight_tempo_percorrenza': self.weight_tempo_percorrenza,
			'veicoli': [id_veicolo for id_veicolo in self.veicoli],
		}

	def deserializza_dinamico(self, rete, res):
		self.tempo_percorrenza = res['tempo_percorrenza']
		self.weight_tempo_percorrenza = res['weight_tempo_percorrenza']
		self.veicoli = {}
		for id_veicolo in res['veicoli']:
			if not id_veicolo in rete.veicoli:
				rete.veicoli[id_veicolo] = ReteVeicolo(id_veicolo)
			self.veicoli[id_veicolo] = rete.veicoli[id_veicolo]

	def linearizza(self, p):
		"""
		Restituisce la distanza lineare dal capolinea iniziale della proiezione di p sul tratto
		"""
		dist_tratto = self.rete_tratto_percorsi.linearizza(p)
		return {
			'da_fermata': dist_tratto,
			'da_capolinea': dist_tratto + self.s.distanza_da_partenza,
		}

	def elimina_veicolo(self, v):
		id_veicolo = v.id_veicolo
		if id_veicolo in self.veicoli:
			del self.veicoli[id_veicolo]

	def distanza_a_capolinea(self, dist_succ):
		"""
		Restituisce la distanza fino al capolinea finale

		:param dist_succ: distanza alla fine del tratto
		:return: distanza al capolinea finale
		"""
		return self.rete_percorso.dist - self.s.distanza_da_partenza - self.rete_tratto_percorsi.dist + dist_succ


class ReteCorsa(object):
	def __init__(self, percorso, veicolo=None):
		super(ReteCorsa).__init__()
		self.veicolo = veicolo
		self.percorso = percorso
		self.n = len(percorso.tratti_percoroso) + 1
		self.orari = [None for x in range(self.n)]
		if veicolo is not None:
			pass

	def aggiorna(self):
		"""
		Aggiorna la posizione e i tempi del veicolo, se il veicolo sta continuando la corsa, e restituisce True.

		Se il veicolo ha iniziato un'altra corsa, restituisce False
		"""


class ReteVeicolo(object):
	def __init__(self, id_veicolo, dotazioni=None):
		object.__init__(self)
		self.id_veicolo = id_veicolo
		self.distanza_capolinea = None
		self.distanza_successiva = None
		self.tratto_percorso = None
		self.ultimo_aggiornamento = None
		self.ultima_interpolazione = None
		self.a_capolinea = None
		self.punto = None
		if dotazioni is None:
			self.dotazioni = {
				'pedana': False,
				'aria': False,
				'moby': False,
				'meb': False,
			}
		else:
			self.dotazioni = dotazioni
		# Diagnostica problemi veicoli problematici
		self.problematico = False
		self.tratto_percorso_problematico = None
		self.fuori_percorso = False
		self.lontano_1d = False
		self.distanza_1d = None
		self.lontano_2d = False
		self.distanza_2d = None
		self.progressiva_atac = None
		self.progressiva_ric = None


	def serializza_dinamico(self):
		return {
			'type': 'ReteVeicolo',
			'id': self.id_veicolo,
			'distanza_capolinea': self.distanza_capolinea,
			'distanza_successiva': self.distanza_successiva,
			'tratto_percorso': None if not self.is_valido() else self.tratto_percorso.get_id(),
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
			'ultima_interpolazione': self.ultima_interpolazione,
			'a_capolinea': self.a_capolinea,
			'dotazioni': self.dotazioni,
			'punto': self.punto,
		}

	def log_su_db(self):
		lon, lat = gbfe_to_wgs84(*self.punto)

		LogPosizioneVeicolo(
			id_veicolo=self.id_veicolo,
			id_percorso=self.tratto_percorso.rete_percorso.id_percorso,
			orario=self.ultimo_aggiornamento,
			distanza_capolinea=self.distanza_capolinea,
			lon=lon,
			lat=lat,
			sistema=settings.MERCURY_GIANO,
		).save()


	def deserializza_dinamico(self, rete, res):
		self.distanza_capolinea = res['distanza_capolinea']
		self.distanza_successiva = res['distanza_successiva']
		self.tratto_percorso = rete.tratti_percorso[res['tratto_percorso']]
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']
		self.ultima_interpolazione = res['ultima_interpolazione']
		self.a_capolinea = res['a_capolinea']
		self.dotazioni = res['dotazioni']
		self.punto = res['punto']

	def aggiorna_posizione(self, distanza_capolinea, distanza_successiva, tratto_percorso, a_capolinea, punto, propaga=True, ultimo_aggiornamento=None):
		"""
		Aggiorna la posizione del veicolo.

		Se punto=None, calcola le coordinate in base alla posizione linearizzata
		"""
		self.problematico = False
		percorso = tratto_percorso.rete_percorso
		if self.tratto_percorso is not None:
			old_percorso = self.tratto_percorso.rete_percorso
			if percorso != old_percorso:
				self.elimina_da_percorso()

		percorso.veicoli[self.id_veicolo] = self
		old_tratto = None
		if self.tratto_percorso is not None:
			old_tratto = self.tratto_percorso
			if tratto_percorso != old_tratto and self.id_veicolo in old_tratto.veicoli:
				del old_tratto.veicoli[self.id_veicolo]
		if old_tratto != tratto_percorso:
			tratto_percorso.veicoli[self.id_veicolo] = self

		self.distanza_capolinea = distanza_capolinea
		self.distanza_successiva = distanza_successiva
		self.tratto_percorso = tratto_percorso
		self.ultimo_aggiornamento = datetime.now() if ultimo_aggiornamento is None else ultimo_aggiornamento
		self.ultima_interpolazione = self.ultimo_aggiornamento
		self.a_capolinea = a_capolinea
		if punto is None:
			self.calcola_punto()
		else:
			self.punto = punto
		if propaga:
			self.propaga_su_fermate()

	def aggiorna_posizione_interpolata(self, tratto_percorso, distanza_precedente, ultima_interpolazione):
		tpi = tratto_percorso.rete_tratto_percorsi
		self.distanza_successiva = tpi.dist - distanza_precedente
		percorso = tratto_percorso.rete_percorso
		self.distanza_capolinea = percorso.dist - tratto_percorso.s.distanza_da_partenza + distanza_precedente
		if self.tratto_percorso != tratto_percorso:
			del self.tratto_percorso.veicoli[self.id_veicolo]
			self.tratto_percorso.veicoli[self.id_veicolo] = self
		self.ultima_interpolazione = ultima_interpolazione
		self.calcola_punto()

	def get_punto(self):
		"""
		A partire dalla posizione linearizzata, calcola le coordinate occupate dal veicolo
		"""
		tpi = self.tratto_percorso.rete_tratto_percorsi
		d = tpi.dist - self.distanza_successiva
		op = None
		mp = None
		for p in tpi.punti:
			if op is not None:
				dp = geomath.distance(p, op)
				if d < dp:
					frac = d / dp
					#print "frac = ", frac
					mp = (op[0] + frac * (p[0] - op[0]), op[1] + frac * (p[1] - op[1]))
					#print "Posizione: ", mp
					break
				d -= dp
			op = p
			#print "Fine ciclo, distanza residua", d2
		if mp is None:
			mp = op
		return mp

	def calcola_punto(self):
		self.punto = self.get_punto()

	def reset_fermate(self, a_fermata=None):
		"""
		Cancella gli arrivi del veicolo corrente dal capolinea di partenza fino alla fermata indicata, inclusa.

		Se non è indicata una fermata, cancella su tutto il percorso.
		"""
		if a_fermata is None:
			a_fermata = self.tratto_percorso.rete_percorso.tratti_percorso[-1].t
		while a_fermata is not None:
			a_fermata.elimina_veicolo(self)
			tp = a_fermata.tratto_percorso_precedente
			if tp is not None:
				tp.elimina_veicolo(self)
				a_fermata = tp.s
			else:
				a_fermata = None

	def elimina_da_percorso(self):
		if self.tratto_percorso is not None:
			old_percorso = self.tratto_percorso.rete_percorso
			self.reset_fermate()
			if self.id_veicolo in old_percorso.veicoli:
				del old_percorso.veicoli[self.id_veicolo]
			self.tratto_percorso = None

	def propaga_su_fermate(self):
		tpo = self.tratto_percorso
		self.reset_fermate(tpo.s)
		numero = 0
		tempo = datetime.now()
		while tpo is not None:
			numero += 1
			fermata = tpo.t
			fermata.elimina_veicolo(self)
			tpi = tpo.rete_tratto_percorsi
			dist = tpi.dist
			velocita = tpi.get_velocita()
			if tempo is not None and velocita > 0:
				if numero == 1:
					d = self.distanza_successiva
					if d < 0:
						d = dist / 2
					tempo = tempo + timedelta(seconds=(d / velocita))
				else:
					tempo = tempo + timedelta(seconds=(dist / velocita))
			else:
				tempo = None
			fermata.add_arrivo(self, tempo, numero)
			tpo = fermata.tratto_percorso_successivo


	def is_valido(self):
		if self.tratto_percorso is None:
			return False
		if self.ultimo_aggiornamento is None or datetime.now() - self.ultimo_aggiornamento > TIMEOUT_VALIDITA_VEICOLO:
			return False
		return True

	def set_problematico(
		self,
		fuori_percorso=False,
		lontano_2d=False,
		distanza_2d=None,
		lontano_1d=False,
		distanza_1d=None,
		progressiva_atac=None,
		progressiva_ric=None,
	):
		self.problematico = True
		self.fuori_percorso = fuori_percorso
		self.lontano_2d = lontano_2d
		self.distanza_1d = distanza_1d
		self.distanza_2d = distanza_2d
		self.lontano_1d = lontano_1d
		self.tratto_percorso_problematico = self.tratto_percorso
		self.progressiva_atac = progressiva_atac
		self.progressiva_ric = progressiva_ric
		self.elimina_da_percorso()

	def get_arrivi(self):
		"""
		Restituisce gli arrivi alle fermate successive
		"""
		if self.a_capolinea:
			return {}
		t = self.tratto_percorso
		d = self.distanza_successiva
		n = datetime.now()
		dt = (n - self.ultimo_aggiornamento).seconds
		# Scalo
		while t is not None and dt > 0:
			v = t.rete_tratto_percorsi.get_velocita()
			if v < 0:
				return {}
			tempo = d / v
			if tempo < dt:
				dt -= tempo
				t = t.t.tratto_percorso_successivo
				if t is not None:
					d = t.rete_tratto_percorsi.dist
			else:
				d -= v * dt
				dt = 0
		# Determino posizioni
		out = {}
		i = 1
		tempo = 0
		while t is not None:
			v = t.rete_tratto_percorsi.get_velocita()
			if v < 0:
				t = None
				break
			tempo += d / v
			# Protezione da malfunzionamenti algoritmo previsione causati da dati di input errati:
			# in caso di tempi anomali, rendi tempo non disponibile
			if tempo > (10 + 4 * i) * 60:
				t = None
				break
			f = t.t
			out[f.rete_palina.id_palina] = n + timedelta(seconds=tempo)
			t = f.tratto_percorso_successivo
			i += 1
			if t is not None:
				d = t.rete_tratto_percorsi.dist
		return out

	def get_info(self, get_arrivi=True, get_distanza=False):
		out = {
			'id_veicolo': self.id_veicolo,
			'id_prossima_palina': self.tratto_percorso.t.rete_palina.id_palina if not self.a_capolinea else self.tratto_percorso.s.rete_palina.id_palina,
			'self.a_capolinea': self.a_capolinea,
			'x': self.punto[0],
			'y': self.punto[1],
		}
		if get_distanza:
			out['distanza_capolinea'] = self.distanza_capolinea
		if get_arrivi:
			out['arrivi'] = self.get_arrivi()
		return out

def get_parametri_costo_pedonale(a0, a1, exp):
	c0 = a0
	c1 = (a1 - c0) / math.pow(1000, exp)
	return (c0, c1, exp)

class ReteZtl(object):
	def __init__(self, codice, nome, orari):
		self.id_ztl = codice
		self.nome = nome
		# Orari è una lista di tuple (orario_inizio, orario_fine), che rappresentano
		# gli orari in cui la ZTL è attiva nei prossimi n giorni
		self.orari = orari

	def attesa(self, t, rev=False):
		"""
		Restituisce None se la ztl non è attiva, oppure il tempo di attesa in secondi
		"""
		for o in self.orari:
			if t >= o[0] and t < o[1]:
				if not rev:
					return (o[1] - t).seconds
				else:
					return (t - o[0]).seconds
		return None


class Rete(object):
	def __init__(self):
		object.__init__(self)
		self.paline = {}
		self.tratti_percorsi = {}
		self.tratti_percorso = {}
		self.percorsi = {}
		# Capilinea: dizionario {id_palina: [percorsi]}
		self.capilinea = {}
		self.fermate = {}
		self.fermate_da_palina = {}
		self.veicoli = {}
		self.ztl = {}
		# Dizionario che associa le pk degli oggetti di tipo StatPeriodiAggregazione agli indici degli elementi
		# che contengono il tempo
		self.indice_stat_periodi_aggregazione = {}
		self.velocita_medie = []
		self.percorrenze_calcolate = False
		# Dizionario avente per chiave una linea, e elementi la lista delle linee ad essa equivalenti
		# ai fini dell'esclusione dal calcola percorso
		self.linee_equivalenti = {}
		self.ultimo_aggiornamento = None
		self.geocoder = None
		self.random = Random()
		self.qualita_atac = QualitaAtac()
		# [Workaround] Dizionario che associa ogni id_veicolo Atac all'id_percorso "ufficiale" che sta compiendo, ottenuto interrogando
		# ciclicamente i capilinea. Usato per la validazione dei percorsi restituiti da CITIES
		self.percorsi_veicoli_atac = {}

	def serializza_dinamico_interno(self):
		return {
			'type': 'Rete',
			'id': '',
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
			'qualita_atac': self.qualita_atac.serializza_dinamico()
		}

	def deserializza_dinamico_interno(self, res):
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']
		self.qualita_atac.deserializza_dinamico(res['qualita_atac'])

	def serializza_dinamico(self):
		out = []
		for id in self.paline:
			out.append(self.paline[id].serializza_dinamico())
		for id in self.tratti_percorsi:
			out.append(self.tratti_percorsi[id].serializza_dinamico())
		for id in self.fermate:
			out.append(self.fermate[id].serializza_dinamico())
		for id in self.veicoli:
			out.append(self.veicoli[id].serializza_dinamico())
		for id in self.percorsi:
			out.append(self.percorsi[id].serializza_dinamico())
		for id in self.tratti_percorso:
			out.append(self.tratti_percorso[id].serializza_dinamico())
		out.append(self.serializza_dinamico_interno())
		return out

	def serializza_dinamico_veicoli(self, percorrenze=True, veicoli=True, percorsi_veicoli_atac=False):
		out = []
		if percorrenze:
			for id in self.tratti_percorsi:
				out.append(self.tratti_percorsi[id].serializza_dinamico())
		if percorsi_veicoli_atac:
			out.append({
				'type': 'PercorsiVeicoliAtac',
				'id': '',
				'ultimo_aggiornamento': self.ultimo_aggiornamento,
				'percorsi_veicoli_atac': self.percorsi_veicoli_atac
			})
		if veicoli:
			for id in self.veicoli:
				v = self.veicoli[id]
				out.append(v.serializza_dinamico())
			out.append(self.serializza_dinamico_interno())
		return out

	def deserializza_dinamico(self, res):
		for r in res:
			try:
				t = r['type']
				id = r['id']
				if t == 'RetePalina':
					self.paline[id].deserializza_dinamico(self, r)
				elif t == 'ReteTrattoPercorsi':
					self.tratti_percorsi[id].deserializza_dinamico(self, r)
				elif t == 'ReteFermata':
					self.fermate[id].deserializza_dinamico(self, r)
				elif t == 'ReteTrattoPercorso':
					self.tratti_percorso[id].deserializza_dinamico(self, r)
				elif t == 'ReteVeicolo':
					if not id in self.veicoli:
						self.veicoli[id] = ReteVeicolo(id)
					self.veicoli[id].deserializza_dinamico(self, r)
				elif t == 'RetePercorso':
					self.percorsi[id].deserializza_dinamico(self, r)
				elif t == 'Rete':
					self.deserializza_dinamico_interno(r)
				else:
					print "Tipo %s non riconosciuto" % t
			except Exception, e:
				print e

	def deserializza_dinamico_veicoli(self, res):
		for r in res:
			try:
				t = r['type']
				id = r['id']
				if t == 'ReteTrattoPercorsi':
					self.tratti_percorsi[id].deserializza_dinamico(self, r)
				elif t == 'PercorsiVeicoliAtac':
					self.percorsi_veicoli_atac = r['percorsi_veicoli_atac']
				elif t == 'ReteVeicolo':
					try:
						id_tratto = r['tratto_percorso']
						if id_tratto is None:
							self.invalida_bus(r['id'])
						else:
							self.aggiorna_posizione_bus(
								r['id'],
								r['distanza_capolinea'],
								r['distanza_successiva'],
								self.tratti_percorso[id_tratto],
								r['a_capolinea'],
								r['punto'],
								r['dotazioni'],
								ultimo_aggiornamento=r['ultimo_aggiornamento'],
							)
					except:
						logging.error('Errore aggiornamento posizione veicolo: %s' % traceback.format_exc())
				elif t == 'Rete':
					self.deserializza_dinamico_interno(r)
			except Exception, e:
				print e

		self.invalida_bus_obsoleti()

	def get_veicoli_tutti_percorsi(self, get_arrivi, get_distanza=False):
		ret = []
		for id_percorso in self.percorsi:
			vs = self.get_veicoli_percorso(id_percorso)
			out = []
			for v in vs:
				out.append(v.get_info(get_arrivi, get_distanza))
			ret.append({
				'id_percorso': id_percorso,
				'arrivi': out,
				'ultimo_aggiornamento': self.percorsi[id_percorso].tratti_percorso[-1].t.ultimo_aggiornamento
			})
		db.reset_queries()
		return ret

	def genera_gtfs_rt(self):
		arrivi = {
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
			'percorsi': self.get_veicoli_tutti_percorsi(True, True),
		}
		return None # gtfs_rt.generate_gtfs_rt(self, arrivi)

	def add_palina(self, id_palina, nome, soppressa=False):
		p = RetePalina(id_palina, nome, soppressa)
		self.paline[id_palina] = p
		return p

	def add_percorso(self, id_percorso, id_linea, tipo, descrizione, soppresso, gestore):
		p = RetePercorso(id_percorso, id_linea, tipo, descrizione, soppresso, gestore)
		self.percorsi[id_percorso] = p
		return p

	def add_fermata(self, id_fermata, id_palina, id_percorso):
		f = ReteFermata(id_fermata, self.paline[id_palina], self.percorsi[id_percorso], self)
		if id_fermata in self.fermate:
			print "FERMATA DUPLICATA", id_fermata
		self.fermate[id_fermata] = f
		self.fermate_da_palina[(id_palina,id_percorso)] = f
		return f

	def add_tratto_percorso(self, id_percorso, id_fermata_s, id_fermata_t):
		s = self.fermate[id_fermata_s]
		t = self.fermate[id_fermata_t]
		ps = s.rete_palina
		pt = t.rete_palina
		p = self.percorsi[id_percorso]
		c = (ps.id_palina, pt.id_palina)

		if c in self.tratti_percorsi:
			a = self.tratti_percorsi[c]
		else:
			a = ReteTrattoPercorsi(ps, pt, self)
			self.tratti_percorsi[c] = a
		tp = ReteTrattoPercorso(p, a, s, t)
		self.tratti_percorso[(id_fermata_s, id_fermata_t)] = tp
		return tp

	def add_capolinea(self, id_percorso, id_palina):
		if id_palina in self.capilinea:
			self.capilinea[id_palina].append(id_percorso)
		else:
			self.capilinea[id_palina] = [id_percorso]

	def add_ztl(self, codice, nome, orari):
		self.ztl[codice] = ReteZtl(codice, nome, orari)

	def log_tempi_attesa_percorsi(self):
		t = datetime.now()
		ora = datetime2time(t)
		data = datetime2date(t)
		if settings.CPD_LOG_PER_STATISTICHE:
			for id_percorso in self.percorsi:
				self.percorsi[id_percorso].log_tempo_attesa(data, ora)

	def aggiorna_arrivi(self, calcola_percorrenze=False, logging=False, aggiorna_arrivi=True, timeout=TIMEOUT_AGGIORNAMENTO_RETE):
		if aggiorna_arrivi:
			print "Aggiornamento arrivi"
			self.qualita_atac.start_ciclo()
			self.qualita_atac.percorso_ok()
			self.qualita_atac.risposta_ok()
			self.dati_da_avm_atac()
			self.qualita_atac.stop_ciclo()
			print "Aggiornamento arrivi completato"
		if calcola_percorrenze:
			print "Calcolo percorrenze archi"
			for k in self.percorsi:
				#print "Processo percorso %s" % self.percorsi[k].id_percorso
				self.percorsi[k].fv.process_data()
				self.percorsi[k].calcola_percorrenze()
			for k in self.tratti_percorsi:
				self.tratti_percorsi[k].media_tempi_percorrenza(logging)
			self.percorrenze_calcolate = True
			print "Calcolo percorrenze completato"
			# Sincronizzazione periodica statistiche CITIES su DB
			# percorsi_cities_sincronizza()
		print "Log posizione veicoli"
		plpvs = PercorsiLogPosizioneVeicolo.objects.all()
		for plpv in plpvs:
			id_percorso = plpv.id_percorso
			if id_percorso in self.percorsi:
				p = self.percorsi[id_percorso]
				for id_veicolo in p.veicoli:
					p.veicoli[id_veicolo].log_su_db()
		print "Log posizione veicoli completato"
		if logging:
			print "Log tempi di attesa percorsi"
			self.log_tempi_attesa_percorsi()
			print "Log tempi attesa percorsi completato"
		self.ultimo_aggiornamento = datetime.now()

	def invalida_bus_obsoleti(self):
		for id_veicolo in self.veicoli:
			v = self.veicoli[id_veicolo]
			if not v.is_valido():
				v.elimina_da_percorso()

	def invalida_bus(self, id_veicolo):
		if id_veicolo in self.veicoli:
			self.veicoli[id_veicolo].elimina_da_percorso()

	def aggiorna_posizione_bus(self, id_veicolo, distanza_capolinea, distanza_successiva, tratto, a_capolinea, punto, dotazioni=None, propaga=True, ultimo_aggiornamento=None):
		if not id_veicolo in self.veicoli:
			self.veicoli[id_veicolo] = ReteVeicolo(id_veicolo, dotazioni=dotazioni)
		self.veicoli[id_veicolo].aggiorna_posizione(distanza_capolinea, distanza_successiva, tratto, a_capolinea, punto, propaga, ultimo_aggiornamento=ultimo_aggiornamento)
		return self.veicoli[id_veicolo]

	def elimina_veicolo_da_percorso(self, id_veicolo):
		if id_veicolo in self.veicoli:
			self.veicoli[id_veicolo].elimina_da_percorso()


	def dati_da_avm_romatpl(self, dati):
		# Determino distanza linearizzata
		id_percorso = dati['id_percorso']
		id_veicolo = dati['id_veicolo']
		a_capolinea = False # TODO
		percorso = self.percorsi[id_percorso]
		if dati['progressiva'] - 1 >= len(percorso.tratti_percorso):
			self.elimina_veicolo_da_percorso(id_veicolo)
		else:
			tpo = percorso.tratti_percorso[dati['progressiva'] - 1]
			tpi = tpo.rete_tratto_percorsi

			punto = geomath.wgs84_to_gbfe(dati['lon'], dati['lat'])
			linear = tpo.linearizza(punto)

			# Aggiungo campione
			distanza_capolinea_finale = percorso.dist - linear['da_capolinea']
			percorso.fv.add(id_veicolo, dati['timestamp'], distanza_capolinea_finale)

			dotazioni = {
				'meb': True,
				'aria': True,
				'moby': True,
				'pedana': True,
			}

			if id_veicolo.startswith("51") or id_veicolo.startswith("52"):
				dotazioni['pedana'] = False

			self.aggiorna_posizione_bus(id_veicolo, distanza_capolinea_finale, tpi.dist - linear['da_fermata'], tpo, a_capolinea, punto, dotazioni=dotazioni)

	@djangotransaction.commit_on_success(using='gis')
	def dati_da_avm_atac(self):
		log_cities = config.LOG_ATAC_CITIES
		log_cities_tr = config.LOG_ATAC_CITIES_TR
		max_distanza = config.GIANO_CITIES_MAX_DISTANZA
		try:
			veicoli = cities.get_cities()
			LogChiamataCities(orario=datetime.now(), successo=True).save()
		except:
			LogChiamataCities(orario=datetime.now(), successo=False, errore=traceback.format_exc(2047)).save()
			return
		percosi_cities_init()
		in_percorso = 0
		fuori_percorso = 0
		altro_percorso = 0
		filtrati = 0
		per_tipo = defaultdict(list)
		for v in veicoli:
			v_fuori = False
			v_filtrato = False
			v_filtrato_2d = False
			try:
				id_veicolo = v['id_veicolo']
				if log_cities_tr:
					LogCitiesTr.objects.filter(num_soc=id_veicolo).update(recency=F('recency') + 1)
					LogCitiesTr.objects.filter(num_soc=id_veicolo, recency__gte=50).delete()
				id_percorso = v['id_percorso']
				id_percorso_atac = id_percorso
				if id_veicolo in self.percorsi_veicoli_atac:
					id_percorso_vero = self.percorsi_veicoli_atac[id_veicolo]['id_percorso']
					if id_percorso_vero != id_percorso:
						altro_percorso += 1
					else:
						# print "Ok, il veicolo %s è in percorso %s" % (id_veicolo, id_percorso)
						in_percorso += 1
				else:
					# print "Veicolo %s NON in percorso %s" % (id_veicolo, id_percorso)
					fuori_percorso += 1
					v_fuori = True
				linea = v['id_linea']
				if id_percorso in associazione_percorsi_cities:
					id_percorso = associazione_percorsi_cities[id_percorso]
				log_percorso_cities(id_percorso, linea, id_percorso in self.percorsi)
				progressiva = v['progressiva']
				distanza_precedente = v['dist_prec']
				a_capolinea = (progressiva == 0 and distanza_precedente == 0)
				percorso = self.percorsi[id_percorso]
				n_tratto, tpo, dist_precedente_tratto = percorso.get_tratto_e_distanza_da_fermata(progressiva, distanza_precedente)
				distanza_successiva = tpo.rete_tratto_percorsi.dist - dist_precedente_tratto
				distanza_capolinea_finale = tpo.distanza_a_capolinea(distanza_successiva)
				x, y = v['x'], v['y']
				if x is not None:
					punto = Point(x, y, srid=3004)
				else:
					punto = None

				dotazioni = {
					'meb': False,
					'aria': False,
					'moby': False,
					'pedana': False,
				}

				veicolo = self.aggiorna_posizione_bus(id_veicolo, distanza_capolinea_finale, distanza_successiva, tpo, a_capolinea, punto, dotazioni=dotazioni)

				cx, cy = veicolo.get_punto()
				punto_ric = Point(cx, cy, srid=3004)

				if punto is None:
					dist = None
				else:
					dist = geomath.distance((x, y), (cx, cy))

				dist_2d = None
				progressiva_ric=None

				if dist is not None and dist <= max_distanza:
					# Aggiungo campione
					percorso.fv.add(id_veicolo, v['timestamp'], distanza_capolinea_finale)
				else:
					# print "** Veicolo %s troppo distante, %f" % (id_veicolo, dist)
					filtrati += 1
					v_filtrato = True
					linear = percorso.linearizza((x, y))
					dist_2d = linear['distanza_2d']
					if dist_2d <= max_distanza:
						distanza_capolinea_finale = percorso.dist - linear['distanza_capolinea']
						tratto_percorso = linear['tratto_percorso']
						distanza_successiva = tratto_percorso.rete_tratto_percorsi.dist - linear['distanza_inizio_tratto']
						veicolo = self.aggiorna_posizione_bus(id_veicolo, distanza_capolinea_finale, distanza_successiva, tpo, a_capolinea, punto, dotazioni=dotazioni)
						progressiva_ric = linear['progressiva'] - 1
					else:
						v_filtrato_2d = True

				if v_fuori or v_filtrato:
					veicolo.set_problematico(
						fuori_percorso=v_fuori,
						lontano_1d=v_filtrato,
						distanza_1d=dist,
						lontano_2d=v_filtrato_2d,
						distanza_2d=dist_2d,
						progressiva_atac=progressiva,
						progressiva_ric=progressiva_ric,
					)

				per_tipo[(v_fuori, v_filtrato)].append({'veicolo': v, 'distanza': dist})

				# Log
				if log_cities:
					LogCities(
						data_ora_ric=v['timestamp'],
						num_soc=id_veicolo,
						geom=punto,
						linea=linea,
						dest=v['dest'],
						cod_perc=v['id_percorso'],
						cod_perc_alt=v['cod_perc_alt'],
						prog_ferm=progressiva,
						dist_da_ferm=distanza_precedente,
						ferm_da_arr=v['ferm_da_arr'],
						cod_corsa=v['cod_corsa'],
						geom_ric=punto_ric,
						dist_ric=dist,
						id_percorso_dec=id_percorso,
					).save()
				if log_cities_tr:
					LogCitiesTr(
						data_ora_ric=v['timestamp'],
						num_soc=id_veicolo,
						geom=punto,
						linea=linea,
						dest=v['dest'],
						cod_perc=v['id_percorso'],
						cod_perc_alt=v['cod_perc_alt'],
						prog_ferm=progressiva,
						dist_da_ferm=distanza_precedente,
						ferm_da_arr=v['ferm_da_arr'],
						cod_corsa=v['cod_corsa'],
						geom_ric=punto_ric,
						dist_ric=dist,
						id_percorso_dec=id_percorso,
					).save()
			except:
				logging.error('Errore aggiornamento posizione veicolo: %s' % traceback.format_exc())
				if log_cities or log_cities_tr:
					try:
						x, y = v['x'], v['y']
						if x is not None:
							punto = Point(x, y, srid=3004)
						else:
							punto = None
						if log_cities:
							LogCities(
								data_ora_ric=v['timestamp'],
								num_soc=v['id_veicolo'],
								geom=punto,
								linea=v['id_linea'],
								dest=v['dest'],
								cod_perc=v['id_percorso'],
								cod_perc_alt=v['cod_perc_alt'],
								prog_ferm=v['progressiva'],
								dist_da_ferm=distanza_precedente,
								ferm_da_arr=v['ferm_da_arr'],
								cod_corsa=v['cod_corsa'],
								geom_ric=None,
								dist_ric=None,
								id_percorso_dec=None,
							).save()
						if log_cities_tr:
							LogCitiesTr(
								data_ora_ric=v['timestamp'],
								num_soc=v['id_veicolo'],
								geom=punto,
								linea=v['id_linea'],
								dest=v['dest'],
								cod_perc=v['id_percorso'],
								cod_perc_alt=v['cod_perc_alt'],
								prog_ferm=v['progressiva'],
								dist_da_ferm=distanza_precedente,
								ferm_da_arr=v['ferm_da_arr'],
								cod_corsa=v['cod_corsa'],
								geom_ric=None,
								dist_ric=None,
								id_percorso_dec=None,
							).save()
					except:
						logging.error('Errore logging veicolo errato: %s' % traceback.format_exc())

		print "Interrogazione CITIES completata. %d in percorso, %d fuori percorso, %d altro percorso, %d filtrati" % (in_percorso, fuori_percorso, altro_percorso, filtrati)

		# pprint(per_tipo[(False, True)])

		print "%d ok, %d fuori percorso, %d filtrati, %d fuori e filtrati" % (
			len(per_tipo[(False, False)]),
			len(per_tipo[(True, False)]),
			len(per_tipo[(False, True)]),
			len(per_tipo[(True, True)]),
		)

	def costruisci_percorso_intersezione(self, id_percorso_1, id_percorso_2, id_percorso, id_linea, tipo, descrizione):
		try:
			p1 = self.percorsi[id_percorso_1]
			p2 = self.percorsi[id_percorso_2]
			pal1 = p1.get_paline()
			paline1 = set(pal1)
			paline2 = set(p2.get_paline())
			paline = paline1.intersection(paline2)
			p = self.add_percorso(id_percorso, id_linea, tipo, descrizione, False, p1.gestore)
			n = 0
			old_f = None
			for pa in pal1:
				if pa in paline:
					n += 1
					f = str(id_percorso) + str(n)
					self.add_fermata(f, pa.id_palina, id_percorso)
					if old_f is not None:
						self.add_tratto_percorso(id_percorso, old_f, f)
					old_f = f
			self.add_capolinea(id_percorso, pa.id_palina)
			# Frequenze
			for giorno_settimana in range(0, 7):
				for ora_inizio in range(0, 24):
					f1, oi1, of1 = p1.frequenza[giorno_settimana][ora_inizio]
					f2, oi2, of2 = p2.frequenza[giorno_settimana][ora_inizio]
					if f1 <= 0:
						f = f2
					elif f2 <= 0:
						f = f1
					else:
						f = (1 / (1 / f1 + 1 / f2))
					if oi1 == -1:
						oi = oi2
					elif oi2 == -1:
						oi = oi1
					else:
						oi = min(oi1, oi2)
					if of1 == -1:
						of = of2
					elif of2 == -1:
						of = of1
					else:
						of = max(of1, of2)
					p.frequenza[giorno_settimana][ora_inizio] = (f, oi, of)
			linee = [id_linea, p1.id_linea, p2.id_linea]
			for l in linee:
				self.linee_equivalenti[l] = linee
		except:
			m = "Errore nella costruzione del percorso intersezione: %s" % traceback.format_exc()
			logging.error(m)
			print m


	def costruisci_indice_periodi_aggregazione(self):
		# Inizializzazione indice
		ispa = self.indice_stat_periodi_aggregazione
		spas = StatPeriodoAggregazione.objects.all()
		# Costruzione indice
		n = 0
		for spa in spas:
			ispa[spa.pk] = n
			n += 1


	def carica(self, retina=False, versione=None, rete_base=None):
		"""
		Genera e restituisce una rete a partire dal database

		bool retina: se True, carica una versione ridotta della rete a scopo di test
		datetime versione: se definita, timestamp dell'inizio di validità della versione
		Rete rete_base: se definita, rete (precedente) da cui copiare la geometria degli oggetti non modificati nella nuova rete
		"""
		if versione is None:
			inizio_validita = datetime2compact(VersionePaline.attuale().inizio_validita)
		else:
			inizio_validita = datetime2compact(versione)
		path_rete = os.path.join(settings.TROVALINEA_PATH_RETE, inizio_validita)
		rete_serializzata_file = os.path.join(path_rete, 'rete%s.v3.dat' % ('_mini' if retina else ''))

		try:
			f = open(rete_serializzata_file, 'rb')
			res = pickle.loads(f.read())
			print "Carico rete serializzata"
			for tipo, param in res['add']:
				getattr(self, 'add_%s' % tipo)(*param)
			for p in res['paline']:
				self.paline[p['id']].deserializza(p)
			for p in res['percorsi']:
				self.percorsi[p['id']].deserializza(p)
			for p in res['tratti_percorsi']:
				self.tratti_percorsi[p['id']].deserializza(p)
			for id_percorso in self.percorsi:
				self.percorsi[id_percorso].set_punti()
			self.velocita_medie = res['velocita_medie']
			self.indice_stat_periodi_aggregazione = res['indice_stat_periodi_aggregazione']
			f.close()

		except IOError:
			print "Costruisco rete da database"
			r = self
			ser = []
			print "Carico paline"
			if retina:
				ps = Palina.objects.by_date(versione).filter(fermata__percorso__linea__id_linea__in=LINEE_MINI)
			else:
				ps = Palina.objects.by_date(versione).all()
			for p in ps:
				r.add_palina(p.id_palina, p.nome, p.soppressa)
				ser.append(('palina', (p.id_palina, p.nome, p.soppressa)))
			print "Carico percorsi"
			ps = Percorso.objects.by_date(versione).all()
			if retina:
				ps = Percorso.objects.by_date(versione).filter(linea__id_linea__in=LINEE_MINI)
			for p in ps:
				percorso_rete = r.add_percorso(p.id_percorso, p.linea.id_linea, p.linea.tipo, p.descrizione, p.soppresso, p.linea.gestore.nome)
				ser.append(('percorso', (p.id_percorso, p.linea.id_linea, p.linea.tipo, p.descrizione, p.soppresso, p.linea.gestore.nome)))
				# Fermate
				old_f = None
				fs = Fermata.objects.by_date(versione).filter(percorso=p).order_by('progressiva')
				for f in fs:
					id_fermata = "%s|%d" % (p.id_percorso, f.progressiva)
					r.add_fermata(id_fermata, f.palina.id_palina, p.id_percorso)
					ser.append(('fermata', (id_fermata, f.palina.id_palina, p.id_percorso)))
					if old_f is not None:
						r.add_tratto_percorso(p.id_percorso, old_id_fermata, id_fermata)
						ser.append(('tratto_percorso', (p.id_percorso, old_id_fermata, id_fermata)))
					old_f = f
					old_id_fermata = id_fermata
				if not percorso_rete.is_circolare():
					r.add_capolinea(p.id_percorso, old_f.palina.id_palina)
					ser.append(('capolinea', (p.id_percorso, old_f.palina.id_palina)))
				else:
					r.add_capolinea(p.id_percorso, percorso_rete.tratti_percorso[-1].s.rete_palina.id_palina)
					ser.append(('capolinea', (p.id_percorso, percorso_rete.tratti_percorso[-1].s.rete_palina.id_palina)))
				# Frequenze
				fs = FrequenzaPercorso.objects.filter(id_percorso=p.id_percorso)
				for f in fs:
					percorso_rete.frequenza[f.giorno_settimana][f.ora_inizio] = (f.frequenza, f.da_minuto, f.a_minuto)
			print "Carico coordinate paline"
			if rete_base is not None:
				print "Trasferimento da vecchia rete"
				for id_palina in rete_base.paline:
					try:
						pold = rete_base.paline[id_palina]
						pnew = r.paline[id_palina]
						pnew.x, pnew.y = pold.x, pold.y
					except:
						print "Trasferimento non possibile per palina ", id_palina
				for id_tratto in rete_base.tratti_percorsi:
					try:
						told = rete_base.tratti_percorsi[id_tratto]
						tnew = r.tratti_percorsi[id_tratto]
						tnew.set_punti(told.punti)
						tnew.set_dist(told.dist)
						tnew.sposta_paline_su_percorso()
					except:
						print "Trasferimento non possibile per tratto ", id_tratto
						traceback.print_exc()
				print "Nuove coordinate"
			path_shp = os.path.join(path_rete, 'shp')
			sf = shapefile.Reader(os.path.join(path_shp, 'Fermate_Percorsi.shp'))
			rs = sf.shapeRecords()
			for el in rs:
				try:
					id_palina = el.record[3]
					p = r.paline[id_palina]
					p.x = el.shape.points[0][0]
					p.y = el.shape.points[0][1]
				except Exception:
					pass
					#print id_palina
			print "Carico coordinate percorsi"
			sf = shapefile.Reader(os.path.join(path_shp, 'Archi/Archi.shp'))
			rs = sf.shapeRecords()
			for el in rs:
				try:
					id_palina_s = el.record[4]
					id_palina_t = el.record[5]
					p = r.tratti_percorsi[(id_palina_s, id_palina_t)]
					p.set_punti(el.shape.points)
					p.set_dist(el.record[6])
					p.sposta_paline_su_percorso()
				except Exception:
					pass
					#print id_palina
			for id_percorso in self.percorsi:
				self.percorsi[id_percorso].set_punti()
			print "Carico statistiche"
			self.costruisci_indice_periodi_aggregazione()
			self.carica_stat_percorrenze_archi()
			self.carica_stat_attese_bus()
			print "Serializzo rete"
			f = open(rete_serializzata_file, 'wb')
			f.write(pickle.dumps({
				'add': ser,
				'paline': [self.paline[id].serializza() for id in self.paline],
				'percorsi': [self.percorsi[id].serializza() for id in self.percorsi],
				'tratti_percorsi': [self.tratti_percorsi[id].serializza() for id in self.tratti_percorsi],
				'velocita_medie': self.velocita_medie,
				'indice_stat_periodi_aggregazione': self.indice_stat_periodi_aggregazione,
			}, 2))
			f.close()
		print "Elaboro mapping fermate soppresse"
		for id_percorso in self.percorsi:
			self.percorsi[id_percorso].init_mapping_fermate_non_soppresse()
		print "Carico ZTL"
		today = date.today()
		zs = orari_per_ztl(today, today + timedelta(days=settings.CPD_GIORNI_LOOKAHEAD))
		for ztl_id in zs:
			z = zs[ztl_id]
			self.add_ztl(ztl_id, z['toponimo'], z['fasce'])
		print "Calcolo distanze"
		for id_percorso in self.percorsi:
			self.percorsi[id_percorso].calcola_distanze()
		db.reset_queries()



	def valida_distanze(self):
		"""
		Verifica che sia definita la distanza su tutti i tratti di percorsi
		"""
		out = ""
		for id in self.tratti_percorsi:
			t = self.tratti_percorsi[id]
			if t.dist is None:
				out += "%s - %s" % (t.s.id_palina, t.t.id_palina)
				out += " (percorsi: %s)\n" % ", ".join([x.rete_percorso.id_percorso for x in t.tratti_percorso])
		if out != "":
			return "Distanza non definita negli shapefile per i seguenti archi tra paline:\n" + out
		return ""

	def carica_stat_percorrenze_archi(self):
		print "Carico statistiche tempi di percorrenza archi"
		spas = StatPeriodoAggregazione.objects.all()
		n = len(self.indice_stat_periodi_aggregazione)
		spazio = [0.0 for x in range(n)]
		tempo = [0.0 for x in range(n)]
		self.velocita_medie = [-1 for x in range(n)]
		for k in self.tratti_percorsi:
			self.tratti_percorsi[k].tempo_percorrenza_stat_orari = [-1 for x in range(n)]
		stas = StatTempoArco.objects.all().order_by('id_palina_s', 'id_palina_t', '-periodo_aggregazione__livello')
		ips, ipt = None, None
		for sta in stas:
			ips2, ipt2 = sta.id_palina_s, sta.id_palina_t
			if (ips2, ipt2) != (ips, ipt):
				ips, ipt = ips2, ipt2
				try:
					tp = self.tratti_percorsi[(ips, ipt)]
					distanza = tp.dist
					if distanza is None:
						tp = None
				except:
					tp = None
			if tp is not None and distanza is not None:
				indice = self.indice_stat_periodi_aggregazione[sta.periodo_aggregazione.pk]
				tempo_vero = distanza / sta.tempo # sta.tempo è una velocità
				tp.tempo_percorrenza_stat_orari[indice] = tempo_vero
				spazio[indice] += distanza
				tempo[indice] += tempo_vero
		for i in range(n):
			#print i, spazio[i], tempo[i]
			if tempo[i] > 0:
				#print i, spazio[i] / tempo[i]
				self.velocita_medie[i] = spazio[i] / tempo[i]

	def carica_stat_attese_bus(self):
		print "Carico statistiche tempi di attesa bus"
		spas = StatPeriodoAggregazione.objects.all()
		n = len(self.indice_stat_periodi_aggregazione)
		for k in self.percorsi:
			self.percorsi[k].tempo_stat_orari = [-1 for x in range(n)]
		staps = StatTempoAttesaPercorso.objects.all().order_by('id_percorso', '-periodo_aggregazione__livello')
		idp = None
		for stap in staps:
			idp2 = stap.id_percorso
			if idp2 != idp:
				idp = idp2
				try:
					p = self.percorsi[idp]
				except:
					p = None
			if p is not None:
				indice = self.indice_stat_periodi_aggregazione[stap.periodo_aggregazione.pk]
				p.tempo_stat_orari[indice] = stap.tempo

	def get_veicoli_percorso(self, id_percorso):
		percorso = self.percorsi[id_percorso]
		percorso.aggiorna_posizione_veicoli()
		veicoli = []
		for id_veicolo in percorso.veicoli:
			v = percorso.veicoli[id_veicolo]
			if v.is_valido():
				veicoli.append(v)
		return veicoli
		#capolinea = self.percorsi[id_percorso].tratti_percorso[-1].t
		#return [self.veicoli[x['id_veicolo']] for x in capolinea.arrivi]

	def get_indici_periodi_attivi(self, dt):
		"""
		Restituisce una array con gli indici dei periodi di aggregazione attivi nell'orario dt.

		Gli indici sono ordinati in ordine decrescente di granularità.
		"""
		wd = Festivita.get_weekday(dt)
		wdd = {'wd%d' % wd: True}
		spas = StatPeriodoAggregazione.objects.filter(
			ora_inizio__lte=dt,
			ora_fine__gt=dt,
			**wdd
		).order_by('livello')
		return [self.indice_stat_periodi_aggregazione[spa.pk] for spa in spas]

	def get_opzioni_calcola_percorso(
		self,
		metro,
		bus,
		fc,
		fr,
		piedi,
		dt=None,
		primo_tratto_bici=False,
		linee_escluse=None,
		auto=False,
		carpooling=False,
		carpooling_vincoli=None,
		teletrasporto=False,
		carsharing=False,
		ztl=None,
		tpl=False,
		bici_sul_tpl=False,
	):
		"""
		Restituisce le opzioni di calcolo del percorso

		metro, bus, fc, fr: boolean
		piedi: 0 (lento), 1 (medio) o 2 (veloce)
		dt: data e ora di calcolo
		"""
		if dt is None:
			dt = datetime.now()
		if linee_escluse is None:
			linee_escluse = set([])
		c0, c1, exp = get_parametri_costo_pedonale(
			[config.CPD_PENAL_PEDONALE_0_0, config.CPD_PENAL_PEDONALE_0_1, config.CPD_PENAL_PEDONALE_0_2][piedi],
			[config.CPD_PENAL_PEDONALE_1_0, config.CPD_PENAL_PEDONALE_1_1, config.CPD_PENAL_PEDONALE_1_2][piedi],
			[config.CPD_PENAL_PEDONALE_EXP_0, config.CPD_PENAL_PEDONALE_EXP_1, config.CPD_PENAL_PEDONALE_EXP_2][piedi],
		)

		if teletrasporto:
			heuristic_speed = 99999999
		elif carpooling or auto:
			heuristic_speed = 33.3
		else:
			heuristic_speed = 16.0

		opt = {
			'metro': metro and not auto,
			'bus': bus and not auto,
			'fc': fc and not auto,
			'fr': fr and not auto,
			'v_piedi': [config.CPD_PIEDI_0, config.CPD_PIEDI_1, config.CPD_PIEDI_2][piedi],
			'v_bici': [config.CPD_BICI_0, config.CPD_BICI_1, config.CPD_BICI_2][piedi],
			't_sal_bus': config.CPD_T_SAL_BUS,
			't_disc_bus': config.CPD_T_DISC_BUS,
			't_sal_metro': config.CPD_T_SAL_METRO,
			't_disc_metro': config.CPD_T_DISC_METRO,
			't_sal_treno': config.CPD_T_SAL_TRENO,
			't_disc_treno': config.CPD_T_DISC_TRENO,
			't_sal_fc': config.CPD_T_SAL_FC,
			't_disc_fc': config.CPD_T_DISC_FC,
			't_disc_bici': config.CPD_T_DISC_BICI,
			't_interscambio': config.CPD_T_INTERSCAMBIO,
			'indici_stat': self.get_indici_periodi_attivi(dt),
			'giorno': dt.day,
			'wd_giorno': Festivita.get_weekday(dt, compatta_feriali=True),
			'wd_giorno_succ': Festivita.get_weekday(dt, True, True),
			'penalizzazione_auto': config.CPD_PENALIZZAZIONE_AUTO if not carsharing else config.CPD_PENALIZZAZIONE_CAR_SHARING,
			'penalizzazione_bus': config.CPD_PENALIZZAZIONE_BUS,
			'penalizzazione_metro': config.CPD_PENALIZZAZIONE_METRO,
			'penalizzazione_fc': config.CPD_PENALIZZAZIONE_FC,
			'penalizzazione_treno': config.CPD_PENALIZZAZIONE_TRENO,
			'incentivo_capolinea': config.CPD_INCENTIVO_CAPOLINEA,
			#'coeff_penal_pedonale': [config.CPD_COEFF_PENAL_PEDONALE_0, config.CPD_COEFF_PENAL_PEDONALE_1, config.CPD_COEFF_PENAL_PEDONALE_2][piedi],
			'penal_pedonale_0': c0,
			'penal_pedonale_1': c1,
			'penal_pedonale_exp': exp,
			'primo_tratto_bici': primo_tratto_bici,
			't_bici_cambio_strada': config.CPD_BICI_CAMBIO_STRADA,
			'linee_escluse': linee_escluse,
			'auto': auto,
			'car_pooling': (not auto) and carpooling,
			'carpooling_vincoli': carpooling_vincoli,
			'carsharing': carsharing,
			'teletrasporto': teletrasporto,
			'rete': self,
			'ztl': set() if ztl is None else ztl,
			'tpl': tpl,
			'bici_sul_tpl': bici_sul_tpl,
			'rev': False,
			'heuristic_speed': heuristic_speed,
		}
		return opt



class Aggiornatore(Thread):
	"""
	Aggiornatore dinamico della rete Atac..
	"""
	def __init__(self, rete, intervallo, cicli_calcolo_percorrenze=4, cicli_logging=24, aggiorna_arrivi=True, gtfs_rt_handler=None):
		Thread.__init__(self)
		self.rete = rete
		self.intervallo = intervallo
		self.ultimo_aggiornamento = None
		self.stopped = False
		self.cicli_calcolo_percorrenze = cicli_calcolo_percorrenze
		self.ciclo_calcolo_percorrenze = 0
		self.cicli_logging = cicli_logging
		self.ciclo_logging = 0
		self.aggiorna_arrivi = aggiorna_arrivi
		self.gtfs_rt_handler = gtfs_rt_handler
		self.mercury = Mercury(settings.MERCURY_GIANO)

	def stop(self):
		self.stopped = True

	def run(self):
		while not self.stopped:
			if self.ultimo_aggiornamento is not None:
				t1 = self.ultimo_aggiornamento + self.intervallo
				t2 = datetime.now()
				if t1 > t2:
					diff = (t1 - t2).seconds
					sleep(diff)
			self.ultimo_aggiornamento = datetime.now()
			try:
				print "Inizio aggiornamento arrivi"
				self.ciclo_calcolo_percorrenze = (self.ciclo_calcolo_percorrenze + 1) % self.cicli_calcolo_percorrenze
				self.ciclo_logging = (self.ciclo_logging + 1) % self.cicli_logging
				aggiorna_percorrenze = self.ciclo_calcolo_percorrenze == 0
				self.rete.aggiorna_arrivi(self.ciclo_calcolo_percorrenze == 0, self.ciclo_logging == 0, aggiorna_arrivi=self.aggiorna_arrivi)
				print "Fine aggiornamento arrivi, serializzazione"
				self.mercury.async_all_stored('deserializza_dinamico_veicoli_stored', self.rete.serializza_dinamico_veicoli(aggiorna_percorrenze))
				print "Serializzazione completata"
				if self.gtfs_rt_handler is not None:
					print "Generazione GTFS Real Time"
					g = self.rete.genera_gtfs_rt()
					print "Attivazione GTFS Real Time"
					self.gtfs_rt_handler(g)
					print "GTFS Real Time generato e attivato"
			except Exception, e:
				logging.error(traceback.format_exc())
		print "Stoppato"


class AggiornatorePercorsiAtac(Thread):
	"""
	Aggiornatore dinamico dei percorsi Atac. Calcola i dati interrogando i capilinea.
	"""

	def __init__(self, rete, intervallo=timedelta(seconds=60)):
		Thread.__init__(self)
		self.rete = rete
		self.intervallo = intervallo
		self.ultimo_aggiornamento = None
		self.stopped = False
		self.mercury = Mercury(settings.MERCURY_GIANO_PERCORSI)

	def stop(self):
		self.stopped = True

	def run(self):
		while not self.stopped:
			if self.ultimo_aggiornamento is not None:
				t1 = self.ultimo_aggiornamento + self.intervallo
				t2 = datetime.now()
				if t1 > t2:
					diff = (t1 - t2).seconds
					sleep(diff)
			self.ultimo_aggiornamento = datetime.now()
			try:
				cities.percorsi_veicoli_multithread(self.rete)
				ser = self.rete.serializza_dinamico_veicoli(percorrenze=False, veicoli=False, percorsi_veicoli_atac=True)
				self.mercury.async_all('deserializza_dinamico_veicoli', ser)

			except Exception, e:
				print "Errore nell'aggiornamento percorsi Atac:"
				traceback.print_exc()
		print "Stoppato"


class AggiornatoreDownload(Thread):
	"""
	Aggiornatore dinamico della rete. Scarica periodicamente la rete serializzata.
	"""
	def __init__(self, rete, intervallo):
		Thread.__init__(self)
		self.rete = rete
		self.intervallo = intervallo
		self.stopped = False

	def stop(self):
		self.stopped = True

	def run(self):
		sa = xmlrpclib.Server('%s/ws/xml/autenticazione/1' % settings.WS_BASE_URL)
		sp = xmlrpclib.Server('%s/ws/xml/paline/7' % settings.WS_BASE_URL)
		token = sa.autenticazione.Accedi(settings.DEVELOPER_KEY, '')
		ultimo_aggiornamento = None
		while not self.stopped:
			print "Verifico ora ultimo aggiornamento rete dinamica"
			res = sp.paline.GetOrarioUltimoAggiornamentoArrivi(token)
			ua = res['risposta']['ultimo_aggiornamento']
			if ultimo_aggiornamento is None or ua > ultimo_aggiornamento:
				print "Scarico ultimo aggiornamento"
				res = sp.paline.GetStatoRete(token)['risposta']
				ultimo_aggiornamento = res['ultimo_aggiornamento']
				print "Deserializzo ultimo aggiornamento"
				#pprint(res['stato_rete'])
				self.rete.deserializza_dinamico(pickle.loads(res['stato_rete'].data))
				print "Rete dinamica aggiornata"
			sleep(self.intervallo.seconds)



def differenza_datetime_secondi(t1, t2):
	if t1 > t2:
		return (t1 - t2).seconds
	return -((t2 - t1).seconds)


# Rete su grafo
class NodoRisorsa(Nodo):
	def __init__(self, ris):
		ct_ris = model2contenttype(ris)
		id_ris = ris.pk
		Nodo.__init__(self, (6, ct_ris, id_ris))
		self.ct_ris = ct_ris
		self.tipo_id = ris.tipo.pk
		self.tipo_ris = ris.tipo.nome
		self.id_ris = id_ris
		self.x, self.y = ris.geom

	def get_coordinate(self):
		return [(self.x, self.y)]

	def get_risorsa(self):
		m = contenttype2model(self.ct_ris)
		return m.objects.get(pk=self.id_ris)

	def risultati_vicini(self, opz):
		return (
			opz['cerca_vicini'] == 'risorse'
			and self.tipo_id in opz['tipi_ris']
			and not ('RIS-%s-%s' % (self.ct_ris, self.id_ris) in opz['linee_escluse'])
		)

	def aggiorna_risultati_vicini(self, risultati, opz):
		if opz['cerca_vicini'] == 'risorse' and self.tipo_id in opz['tipi_ris']:
			dist = self.get_vars(opz).get_distanza()
			risultati.aggiungi_risorsa(self, dist)

	def costruisci_percorso(self, t, opzioni):
		vars = self.get_vars(opzioni)
		ris = self.get_risorsa()
		return tratto.TrattoRisorsa(
			t.parent,
			vars.time,
			self.ct_ris,
			self.id_ris,
			ris.icon,
			ris.icon_size,
			ris.nome_luogo,
			ris.descrizione(),
			self.get_coordinate(),
		)


class NodoPuntoArrivo(geocoder.NodoGeocoder):
	"""
	Nodo usato per le ricerche di percorso single-source, multiple-destination, o per la ricerca di luoghi vicini
	tra un insieme di nodi (NodoPuntoArrivo) passati come parametro
	"""
	def __init__(self, *args, **kwargs):
		super(NodoPuntoArrivo, self).__init__(*args, **kwargs)
		self.nome = ''

	def aggiorna_risultati_vicini(self, risultati, opz):
		if opz['cerca_vicini'] == 'punti' and self in risultati.nodi:
			dist = self.get_vars(opz).get_distanza()
			tempo = self.get_vars(opz).time
			risultati.aggiungi_punto(self, dist, tempo)


class NodoPalinaAttesa(Nodo):
	def __init__(self, rete_palina):
		Nodo.__init__(self, (1, rete_palina.id_palina))
		self.rete_palina = rete_palina

	def get_coordinate(self):
		return [(self.rete_palina.x, self.rete_palina.y)]

	def aggiorna_risultati_vicini(self, risultati, opz):
		if opz['cerca_vicini'] == 'paline':
			p = self.rete_palina
			linee = {}
			dist = self.get_vars(opz).get_distanza()
			for k in p.fermate:
				perc = p.fermate[k].rete_percorso
				if perc.tipo in TIPI_LINEA_INFOTP:
					linee[perc.id_linea] = (p.id_palina, dist, p.x, p.y)
			if len(linee) > 0:
				risultati.aggiungi_palina(p.id_palina, dist, p.x, p.y)
				risultati.aggiungi_linee(linee)


class NodoFermata(Nodo):
	def __init__(self, rete_fermata):
		Nodo.__init__(self, (2, rete_fermata.id_fermata))
		self.rete_fermata = rete_fermata

	def get_coordinate(self):
		return [(self.rete_fermata.rete_palina.x, self.rete_fermata.rete_palina.y)]


class NodoInterscambio(Nodo):
	def __init__(self, nome):
		Nodo.__init__(self, (8, nome))
		self.nome = nome


class ArcoAttesaBus(Arco):
	def __init__(self, nodo_palina, nodo_fermata):
		Arco.__init__(self, nodo_palina, nodo_fermata, (3, nodo_fermata.rete_fermata.id_fermata))

	def get_tempo_vero(self, t, opz):
		d = get_weekday_caching(t, opz)
		f = self.t.rete_fermata
		p = f.rete_percorso
		if p.id_linea in opz['linee_escluse']:
			return (-1, 'Z')
		t_prog, da, a = p.frequenza[d][t.hour]
		if not (da <= t.minute <= a):
			return (-1, 'Z')
		t_arr = f.get_primo_arrivo(t, opz['rev'])
		if t_arr is not None:
			id_veicolo = ""
			if 'id_veicolo' in t_arr[1]:
				id_veicolo = str(t_arr[1]['id_veicolo'])
			return (t_arr[0], 'P' + id_veicolo)
		for i in opz['indici_stat']:
			try:
				ts = p.tempo_stat_orari[i]
				if ts != -1:
					return (ts * 2 / 1.4, 'S')
			except Exception:
				pass
		return (t_prog / 1.4, 'O')


	def get_tempo(self, t, opz):
		if opz['bus'] == False:
			return (-1, -1)
		tempo = self.get_tempo_vero(t + timedelta(seconds=opz['t_sal_bus']), opz)[0]
		if tempo == -1:
			return (-1, -1)
		if self.t.rete_fermata.is_capolinea_partenza():
			tpen = max(0, tempo + opz['penalizzazione_bus'] - opz['incentivo_capolinea'])
		else:
			tpen = tempo + opz['penalizzazione_bus']
		return (tpen, tempo)

	def get_coordinate(self):
		return [(self.s.rete_palina.x, self.s.rete_palina.y)]

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoBus(t.parent, vars.time, self.t.rete_fermata, ta - opzioni['t_sal_bus'], tt, opzioni['t_sal_bus'])

def tratto_piedi_o_bici(parent, time, arco, opzioni):
	if arco.s.get_context(opzioni)['primo_tratto_bici']:
		return tratto.TrattoBici(parent, time)
	else:
		return tratto.TrattoPiedi(parent, time)

class ArcoDiscesaBus(Arco):
	def __init__(self, nodo_fermata, nodo_palina):
		Arco.__init__(self, nodo_fermata, nodo_palina, (4, nodo_fermata.rete_fermata.id_fermata))

	def get_coordinate(self):
		return [(self.t.rete_palina.x, self.t.rete_palina.y)]

	def get_tempo(self, t, opz):
		tempo = opz['t_disc_bus']
		return (tempo, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		tratto.TrattoBusDiscesa(t, vars.time, self.s.rete_fermata, opzioni['t_disc_bus'])
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)



class ArcoPercorrenzaBus(Arco):
	def __init__(self, rete_tratto_percorso, nodo_fermata_s, nodo_fermata_t):
		self.rete_tratto_percorso = rete_tratto_percorso
		Arco.__init__(self, nodo_fermata_s, nodo_fermata_t, (5, nodo_fermata_s.rete_fermata.id_fermata, nodo_fermata_t.rete_fermata.id_fermata))

	def get_tempo_vero(self, t, opz):
		rtp = self.rete_tratto_percorso.rete_tratto_percorsi
		tp = rtp.tempo_percorrenza
		ua = rtp.ultimo_aggiornamento
		if ua is not None and abs(t - ua) < VALIDITA_TEMPO_ARCHI:
			if tp > 0:
				return (tp, 'P')
			#if rtp.tempo_percorrenza_interpolato > 0:
			#	return (rtp.tempo_percorrenza_interpolato, 'I')
		for i in opz['indici_stat']:
			t = rtp.tempo_percorrenza_stat_orari[i]
			if t != -1:
				return (t, 'S')
		if rtp.dist > 0:
			velocita = 19.0 * 5.0 / 18.0
			for i in opz['indici_stat']:
				if rtp.rete.velocita_medie[i] > 0:
					velocita = rtp.rete.velocita_medie[i]
					break
			return (rtp.dist / velocita, 'D')
		return (60, 'DD')

	def get_tempo(self, t, opz):
		tempo = self.get_tempo_vero(t, opz)[0]
		return (tempo, tempo)

	def get_distanza(self):
		return self.rete_tratto_percorso.rete_tratto_percorsi.dist

	def get_coordinate(self):
		return self.rete_tratto_percorso.rete_tratto_percorsi.punti

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		tratto.TrattoBusArcoPercorso(t, vars.time, self.rete_tratto_percorso, ta, tt, self.rete_tratto_percorso.rete_tratto_percorsi.punti)
		return t



class ArcoAttesaMetro(ArcoAttesaBus):
	def get_tempo_vero(self, t, opz):
		d = get_weekday_caching(t, opz)
		p = self.t.rete_fermata.rete_percorso
		if p.id_linea in opz['linee_escluse']:
			return (-1, 'Z')
		f = p.frequenza[d][t.hour]
		t_arr, da, a = f
		if da <= t.minute <= a:
			return (t_arr / 1.5, False)
		return (-1, False)

	def get_tempo(self, t, opz):
		if opz['metro'] == False:
			return (-1, -1)
		tm = self.get_tempo_vero(t, opz)[0]
		if tm < 0:
			return (-1, -1)
		tempo = tm + opz['t_sal_metro']
		if self.t.rete_fermata.is_capolinea_partenza():
			tpen = max(0, tempo + opz['penalizzazione_metro'] - opz['incentivo_capolinea'])
		else:
			tpen = tempo + opz['penalizzazione_metro']
		return (tpen, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoMetro(t.parent, vars.time, self.t.rete_fermata, ta, tt, opzioni['t_sal_metro'])


class ArcoDiscesaMetro(ArcoDiscesaBus):
	def get_tempo(self, t, opz):
		tempo = opz['t_disc_metro']
		return (tempo, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		tratto.TrattoMetroDiscesa(t, vars.time, self.s.rete_fermata, opzioni['t_disc_metro'])
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)




class ArcoDiscesaMetroInterscambio(Arco):
	def __init__(self, nodo_fermata, nodo_interscambio):
		Arco.__init__(self, nodo_fermata, nodo_interscambio, (9, nodo_fermata.rete_fermata.id_fermata))

	def get_tempo(self, t, opz):
		return (0, 0)

	def get_coordinate(self):
		return [(self.s.rete_fermata.rete_palina.x, self.s.rete_fermata.rete_palina.y)]
	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		tratto.TrattoMetroDiscesa(t, vars.time, self.s.rete_fermata, 0)
		return t.parent



class ArcoAttesaMetroInterscambio(Arco):
	def __init__(self, nodo_interscambio, nodo_fermata):
		Arco.__init__(self, nodo_interscambio, nodo_fermata,(20, nodo_fermata.rete_fermata.id_fermata))

	def get_tempo_vero(self, t, opz):
		d = get_weekday_caching(t, opz)
		p = self.t.rete_fermata.rete_percorso
		if p.id_linea in opz['linee_escluse']:
			return (-1, 'Z')
		f = p.frequenza[d][t.hour]
		t_arr, da, a = f
		if da <= t.minute <= a:
			return (t_arr / 1.5, False)
		return (-1, False)

	def get_tempo(self, t, opz):
		tv = self.get_tempo_vero(t, opz)[0]
		if tv <= 0:
			return (-1, -1)
		return (opz['t_sal_metro'] + tv, tv)


	def get_coordinate(self):
		return [(self.t.rete_fermata.rete_palina.x, self.t.rete_fermata.rete_palina.y)]

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoMetro(t, vars.time, self.t.rete_fermata, ta, tt, opzioni['t_sal_metro'], True)

class ArcoAttesaInterscambio(Arco):
	def __init__(self, nodo_palina, nodo_interscambio):
		Arco.__init__(self, nodo_palina, nodo_interscambio, (21, nodo_palina.rete_palina.id_palina, nodo_interscambio.nome))

	def get_tempo(self, t, opz):
		if opz['auto']:
			return (-1, -1)
		return (opz['t_interscambio'], opz['t_interscambio'])

	def get_coordinate(self):
		return []

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		return tratto.TrattoInterscambio(t.parent, vars.time, self.s.rete_palina, opzioni['t_interscambio'])

class ArcoDiscesaInterscambio(Arco):
	def __init__(self, nodo_interscambio, nodo_palina):
		Arco.__init__(self, nodo_interscambio, nodo_palina, (22, nodo_interscambio.nome, nodo_palina.rete_palina.id_palina))

	def get_tempo(self, t, opz):
		return (0, 0)

	def get_coordinate(self):
		return []

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		t.set_palina_t(self.t.rete_palina)
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)


class ArcoPercorrenzaMetro(ArcoPercorrenzaBus):
	def get_tempo(self, t, opz):
		if self.rete_tratto_percorso.rete_percorso.id_linea == 'MEC':
			return (106, 106)
		return (90, 90)

	def get_tempo_vero(self, t, opz=None):
		if self.rete_tratto_percorso.rete_percorso.id_linea == 'MEC':
			return (106, 'D')
		return (90, 'D')

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time)
		tratto.TrattoMetroArcoPercorso(t, vars.time, self.rete_tratto_percorso, ta, tt, self.rete_tratto_percorso.rete_tratto_percorsi.punti)
		return t


# begin teletrasporto
class ArcoAttesaTeletrasporto(ArcoAttesaBus):
	def __init__(self, nodo_palina, nodo_fermata):
		Arco.__init__(self, nodo_palina, nodo_fermata, (97, nodo_fermata.rete_fermata.id_fermata))

	def get_tempo_vero(self, t, opz):
		return (0, False)

	def get_tempo(self, t, opz):
		if not opz['teletrasporto']:
			return (-1, -1)
		return (0, 0)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoTeletrasporto(t.parent, vars.time, self.t.rete_fermata, ta, tt, 0)


class ArcoPercorrenzaTeletrasporto(ArcoPercorrenzaBus):
	def __init__(self, nodo_fermata_s, nodo_fermata_t):
		Arco.__init__(self, nodo_fermata_s, nodo_fermata_t, (99, nodo_fermata_s.rete_fermata.id_fermata, nodo_fermata_t.rete_fermata.id_fermata))

	def get_coordinate(self):
		return self.s.get_coordinate() + self.t.get_coordinate()


	def get_tempo(self, t, opz):
		if not opz['teletrasporto']:
			return (-1, -1)
		return (1, 1)

	def get_tempo_vero(self, t, opz=None):
		return (1, 'D')

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time)
		tratto.TrattoTeletrasportoArcoPercorso(t, vars.time, self.s.rete_fermata.rete_palina, self.t.rete_fermata.rete_palina, ta)
		return t

class ArcoDiscesaTeletrasporto(ArcoDiscesaBus):
	def __init__(self, nodo_fermata, nodo_palina):
		Arco.__init__(self, nodo_fermata, nodo_palina, (98, nodo_fermata.rete_fermata.id_fermata))

	def get_tempo(self, t, opz):
		if not opz['teletrasporto']:
			return (-1, -1)
		tempo = 0
		return (tempo, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		tratto.TrattoTeletrasportoDiscesa(t, vars.time, self.s.rete_fermata, 0)
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)
# end teletrasporto


class ArcoAttesaFC(ArcoAttesaBus):
	def get_tempo_vero(self, t, opz):
		d = get_weekday_caching(t, opz)
		p = self.t.rete_fermata.rete_percorso
		if p.id_linea in opz['linee_escluse']:
			return (-1, 'Z')
		f = p.frequenza[d][t.hour]
		t_arr, da, a = f
		if da <= t.minute <= a:
			return (t_arr / 1.4, False)
		return (-1, False)

	def get_tempo(self, t, opz):
		if opz['fc'] == False:
			return (-1, -1)
		tm = self.get_tempo_vero(t, opz)[0]
		if tm < 0:
			return (-1, -1)
		tempo = tm + opz['t_sal_fc']
		if self.t.rete_fermata.is_capolinea_partenza():
			tpen = max(0, tempo + opz['penalizzazione_fc'] - opz['incentivo_capolinea'])
		else:
			tpen = tempo + opz['penalizzazione_fc']
		return (tpen, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		#print "Salgo sul FC"
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoFC(t.parent, vars.time, self.t.rete_fermata, ta, tt, opzioni['t_sal_fc'])


class ArcoDiscesaFC(ArcoDiscesaBus):
	def get_tempo(self, t, opz):
		tempo = opz['t_disc_fc']
		return (tempo, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		#print "Scendo dalla FC"
		tratto.TrattoFCDiscesa(t, vars.time, self.s.rete_fermata, opzioni['t_disc_fc'])
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)

class ArcoPercorrenzaFC(ArcoPercorrenzaBus):
	def get_tempo(self, t, opz):
		p = self.rete_tratto_percorso.rete_percorso
		idl = p.id_linea
		n = len(p.tratti_percorso)
		tempo = {
			'FC1': 103,
			'FC2': 185,
			'FC3': 94,
		}[idl] * n * self.rete_tratto_percorso.rete_tratto_percorsi.dist / p.dist
		return (tempo, tempo)

	def get_tempo_vero(self, t, opz):
		p = self.rete_tratto_percorso.rete_percorso
		idl = p.id_linea
		n = len(p.tratti_percorso)
		return ({
			'FC1': 103,
			'FC2': 185,
			'FC3': 94,
		}[idl] * n * self.rete_tratto_percorso.rete_tratto_percorsi.dist / p.dist), 'D'

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		tratto.TrattoFCArcoPercorso(t, vars.time, self.rete_tratto_percorso, ta, tt, self.rete_tratto_percorso.rete_tratto_percorsi.punti)
		return t


class ArcoAttesaTreno(ArcoAttesaBus):
	def __init__(self, nodo_palina, nodo_fermata):
		ArcoAttesaBus.__init__(self, nodo_palina, nodo_fermata)
		self.partenze = [Avl() for i in range(7)]
		self.ha_partenze = False

	def aggiungi_partenza(self, dt, day=None):
		"""
		Aggiunge un orario di partenza

		L'orario di partenza può essere un time o un datetime.
		Se è un datetime bisogna passare day=None. Se è un time, day deve valere
		0 (festivo), 5 (sabato) o 6 (domenica)
		"""
		self.ha_partenze = True
		if day is None:
			d = dt.weekday()
			t = datetime2time(dt)
		else:
			d = day % 7
			t = dt
		if d < 5:
			d = 0
		self.partenze[d].insert(t, None)

	def prossima_partenza(self, t, opz):
		if not self.ha_partenze:
			return None
		ora = datetime2time(t)
		data = datetime2date(t)
		n = None
		giorni = 0
		while n is None:
			if giorni <= 1:
				d = get_weekday_caching(data, opz)
			else:
				d = Festivita.get_weekday(data, compatta_feriali=True)
			n = self.partenze[d].gt_key(ora)
			if n is None:
				ora = time(0, 0)
				data += timedelta(days=1)
				giorni += 1
		return dateandtime2datetime(data, n[0])

	def get_tempo_vero(self, t, opz):
		if not self.ha_partenze:
			return (-1, False)
		p = self.t.rete_fermata.rete_percorso
		if p.id_linea in opz['linee_escluse']:
			return (-1, 'Z')
		t1 = t + timedelta(seconds=opz['t_sal_treno'])
		dt = self.prossima_partenza(t1, opz)
		diff = dt - t
		tempo = diff.days * 86400 + diff.seconds
		return (tempo, 'O')

	def get_tempo(self, t, opz):
		if not opz['fr']:
			return (-1, -1)
		tempo, b = self.get_tempo_vero(t, opz)
		if tempo == -1:
			return (-1, -1)
		if self.t.rete_fermata.is_capolinea_partenza():
			tpen = max(0, tempo + opz['penalizzazione_treno'] - opz['incentivo_capolinea'])
		else:
			tpen = tempo + opz['penalizzazione_treno']
		return (tpen, tempo)

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, tt = self.get_tempo_vero(vars.time, opzioni)
		return tratto.TrattoTreno(t.parent, vars.time, self.t.rete_fermata, ta - opzioni['t_sal_treno'], tt, opzioni['t_sal_treno'])



class ArcoDiscesaTreno(ArcoDiscesaBus):
	def get_tempo(self, t, opz):
		return (opz['t_disc_treno'], opz['t_disc_treno'])

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		tratto.TrattoTrenoDiscesa(t, vars.time, self.s.rete_fermata, opzioni['t_disc_treno'])
		return tratto_piedi_o_bici(t.parent, vars.time, self, opzioni)



class ArcoPercorrenzaTreno(ArcoPercorrenzaBus):
	def __init__(self, rete_tratto_percorso, nodo_fermata_s, nodo_fermata_t):
		ArcoPercorrenzaBus.__init__(self, rete_tratto_percorso, nodo_fermata_s, nodo_fermata_t)
		self.partenze = [Avl() for i in range(7)]
		self.ha_partenze = False

	def aggiungi_partenza(self, dt, perc, day=None):
		"""
		Aggiunge un orario di partenza e lo associa a un tempo di percorrenza, in secondi

		L'orario di partenza può essere un time o un datetime.
		Se è un datetime bisogna passare day=None. Se è un time, day deve valere
		0 (festivo), 5 (sabato) o 6 (domenica)
		"""
		self.ha_partenze = True
		if day is None:
			d = dt.weekday()
			t = datetime2time(dt)
		else:
			d = day % 7
			t = dt
		if d < 5:
			d = 0
		self.partenze[d].insert(t, perc)

	def prossima_partenza(self, t, opz):
		if not self.ha_partenze:
			return None
		ora = datetime2time(t)
		data = datetime2date(t)
		n = None
		giorni = 0
		while n is None:
			if giorni <= 1:
				d = get_weekday_caching(data, opz)
			else:
				d = Festivita.get_weekday(data, compatta_feriali=True)
			n = self.partenze[d].gt_key(ora)
			if n is None:
				ora = time(0, 0)
				data += timedelta(days=1)
				giorni += 1
		return (dateandtime2datetime(data, n[0]), n[1])


	def get_tempo(self, t, opz):
		el = self.prossima_partenza(t, opz)
		if el is None:
			return (-1, -1)
		dt, tempo = el
		return (tempo, tempo)

	def get_tempo_vero(self, t, opz=None):
		pass
		#return (90, 'D')

	def costruisci_percorso(self, t, opzioni):
		vars = self.s.get_vars(opzioni)
		ta, x = self.get_tempo(vars.time, opzioni)
		tt = 'O'
		tratto.TrattoTrenoArcoPercorso(t, vars.time, self.rete_tratto_percorso, ta, tt, self.rete_tratto_percorso.rete_tratto_percorsi.punti)
		return t

def registra_classi_grafo(g):
	classi_nodi = [tomtom.NodoTomTom, geocoder.NodoGeocoder]
	classi_archi = [tomtom.ArcoTomTom, geocoder.ArcoGeocoder]
	for cn in classi_nodi:
		g.registra_tipo_nodi(cn)
	for ca in classi_archi:
		g.registra_tipo_archi(ca)

def carica_rete_su_grafo(r, g, retina=False, versione=None):
	"""
	Carica la rete del TPL all'interno del grafo g e aggiorna i link inversi
	"""
	print "Carico rete su grafo"

	registra_classi_grafo(g)

	# Paline
	for k in r.paline:
		p = r.paline[k]
		if not p.soppressa:
			n = NodoPalinaAttesa(p)
			p.nodo_palina = n
			g.add_nodo(n)
	interscambio = {'TERMINI': None, 'BOLOGNA': None}
	nodi_scambio = {
		'PIRAMIDE': ['90151', '91151', 'BP8', 'BD15', '90221', '91221'],
		'EUR MAGLIANA': ['90153', '91153', 'BP4', 'BD19'],
		'SAN PAOLO': ['90152', '91152', 'BP6', 'BD17'],
		# 'TEST': ['BP8', 'BD15', 'AP7', 'AD21'] # Ostiense <-> Porta Furba
	}
	for k in interscambio:
		n = NodoInterscambio(k)
		interscambio[k] = n
		g.add_nodo(n)
	for k in nodi_scambio:
		n = NodoInterscambio(k)
		g.add_nodo(n)
		for id_palina in nodi_scambio[k]:
			try:
				np = g.nodi[(1, id_palina)]
				a = ArcoAttesaInterscambio(np, n)
				g.add_arco(a)
				a = ArcoDiscesaInterscambio(n, np)
				g.add_arco(a)
			except:
				traceback.print_exc()
				print "Nodo scambio: palina %s non trovata" % id_palina
	# Fermate
	fermata_teletrasporto = None
	for k in r.fermate:
		f = r.fermate[k]
		if not f.rete_percorso.soppresso:
			# Aggiungo fermata
			n = NodoFermata(f)
			f.nodo_fermata = n
			g.add_nodo(n)
			# Aggiungo arco di attesa e arco di discesa, se la palina non è soppressa
			if (1, f.rete_palina.id_palina) in g.nodi:
				np = g.nodi[(1, f.rete_palina.id_palina)]
				tipo = f.rete_percorso.tipo
				Attesa, Discesa = {
					'BU': (ArcoAttesaBus, ArcoDiscesaBus),
					'TR': (ArcoAttesaBus, ArcoDiscesaBus),
					'ME': (ArcoAttesaMetro, ArcoDiscesaMetro),
					'FR': (ArcoAttesaTreno, ArcoDiscesaTreno),
					'FC': (ArcoAttesaFC, ArcoDiscesaFC),
				}[tipo]
				a = Attesa(np, n)
				f.arco_attesa_bus = a
				g.add_arco(a)
				a = Discesa(n, np)
				f.arco_discesa_bus = a
				g.add_arco(a)
				# begin teletrasporto
				if tipo != 'BU' and tipo != 'TR':
					Attesa = ArcoAttesaTeletrasporto
					Discesa = ArcoDiscesaTeletrasporto
					a = Attesa(np, n)
					f.arco_attesa_bus = a
					g.add_arco(a)
					a = Discesa(n, np)
					f.arco_discesa_bus = a
					g.add_arco(a)
					if fermata_teletrasporto is not None:
						g.add_arco(ArcoPercorrenzaTeletrasporto(fermata_teletrasporto, n))
						g.add_arco(ArcoPercorrenzaTeletrasporto(n, fermata_teletrasporto))
					else:
						fermata_teletrasporto = n
				# end teletrasporto
				nome = f.rete_palina.nome
				if tipo == 'ME' and nome in interscambio:
					ni = interscambio[nome]
					a = ArcoAttesaMetroInterscambio(ni, n)
					g.add_arco(a)
					a = ArcoDiscesaMetroInterscambio(n, ni)
					g.add_arco(a)
	# Tratti di percorso
	for k in r.tratti_percorso:
		tp = r.tratti_percorso[k]
		if not tp.rete_percorso.soppresso:
			tipo = tp.rete_percorso.tipo
			Percorrenza = {
				'BU': ArcoPercorrenzaBus,
				'TR': ArcoPercorrenzaBus,
				'ME': ArcoPercorrenzaMetro,
				'FR': ArcoPercorrenzaTreno,
				'FC': ArcoPercorrenzaFC,
			}[tipo]
			a = Percorrenza(tp, tp.s.nodo_fermata, tp.t.nodo_fermata)
			tp.arco_tratto_percorso = a
			g.add_arco(a)
			# begin teletrasporto
			"""
			if tipo == 'ME':
				a = ArcoPercorrenzaTeletrasporto(tp, tp.s.nodo_fermata, tp.t.nodo_fermata)
				tp.arco_tratto_percorso = a
				g.add_arco(a)
			"""
			# end teletrasporto
	# Archi di distanza fra paline e grafo pedonale (osm)
	print "Collego la rete del TPL alla rete stradale"
	if versione is None:
		inizio_validita = datetime2compact(VersionePaline.attuale().inizio_validita)
	else:
		inizio_validita = datetime2compact(versione)
	path_rete = os.path.join(settings.TROVALINEA_PATH_RETE, inizio_validita)
	geocoding_file = os.path.join(path_rete, 'archi_geocoding%s.v3.dat' % ('_mini' if retina else ''))
	r.geocoder = geocoder.Geocoder(g, 12, caching_id='mini' if retina else 'full') # 12 e' il tipo degli archi stradali
	gc = r.geocoder
	try:
		g.deserialize(geocoding_file)
	except IOError:
		print "Necessario ricalcolo"
		ps = [r.paline[k] for k in r.paline if not r.paline[k].soppressa]
		dp = DijkstraPool(g, 1)
		with dp.get_dijkstra() as dj:
			for i in range(0, len(ps)):
				pi = ps[i]
				ni = g.nodi[(1, pi.id_palina)]
				if pi.ferroviaria :
					archi_conn = gc.connect_to_node_multi(ni, dj)
					if len(archi_conn) == 0:
						archi_conn = gc.connect_to_node(ni)
				else:
					archi_conn = gc.connect_to_node(ni)
				for a in archi_conn:
					g.add_arco(a)
		g.serialize(geocoding_file, [geocoder.ArcoGeocoder], [geocoder.NodoGeocoder])

	if True: #not retina:
		# Nodi luogo e connessione
		print "Aggiungo e collego nodi luogo"
		for risorsa in risorse.modelli_risorse:
			print risorsa.__name__
			for a in risorsa.objects.all():
				if a.geom is None:
					print "No luogo: " + a.nome_luogo
				else:
					n = NodoRisorsa(a)
					g.add_nodo(n)
					archi_conn = gc.connect_to_node(n)
					for a in archi_conn:
						g.add_arco(a)

		# Elimino archi rimossi da database
		print "Elimino archi rimossi da database"
		ars = ArcoRimosso.objects.filter(rimozione_attiva=True)
		for a in ars:
			try:
				print a, a.eid
				g.rm_arco(g.archi[a.eid])
			except Exception, e:
				logging.error(u'Arco rimosso %s non trovato', a.descrizione)

	# Orari Ferrovie del Lazio
	fn = os.path.join(path_rete, 'rete', 'fr.txt')
	carica_orari_fr_da_file(r, g, fn)

	gc.serialize_cache()
	db.reset_queries()



def carica_rete_e_grafo(retina=False, versione=None, rete_base=None):
	rete = Rete()
	rete.carica(retina, versione, rete_base=rete_base)
	g = Grafo()
	registra_classi_grafo(g)
	g.deserialize(os.path.join(settings.TROVALINEA_PATH_RETE, '%s%s.v3.dat' % (settings.GRAPH, '_mini' if retina else '')))
	#tomtom.load_from_shp(g, 'C:\\Users\\allulll\\Desktop\\grafo\\cpd\\RM_nw%s'  % ('_mini' if retina else ''))
	carica_rete_su_grafo(rete, g, retina, versione)
	return (rete, g)

# Frequenza bus
def calcola_frequenze_giorno(giorno, giorno_settimana, percorsi_da_rete=True):
	with transaction():
		FrequenzaPercorso.objects.filter(giorno_settimana=giorno_settimana).delete()
		giorno_succ = giorno + timedelta(days=1)
		if percorsi_da_rete:
			ps = Percorso.objects.by_date(date2datetime(giorno) + timedelta(hours=7)).all()
			id_percorsi = [p.id_percorso for p in ps]
		else:
			pcs = PartenzeCapilinea.objects.filter(orario_partenza__gte=giorno, orario_partenza__lt=giorno_succ).distinct('id_percorso')
			id_percorsi = [p.id_percorso for p in pcs]
		for id_percorso in id_percorsi:
			#print percorso.id_percorso
			pcs = PartenzeCapilinea.objects.filter(id_percorso=id_percorso, orario_partenza__gte=giorno, orario_partenza__lt=giorno_succ)
			sum = [0.0 for i in range(24)]
			cnt = [0 for i in range(24)]
			da = [0 for i in range(24)]
			a = [59 for i in range(24)]
			old = None
			pcs = [x for x in pcs] + [None]
			for p in pcs:
				sx = False
				dx = False
				if p is None:
					dx = True
					op = date2datetime(giorno_succ)
				else:
					op = p.orario_partenza
				if old is None:
					sx = True
					old = date2datetime(giorno)
				diff = op - old
				if sx or dx:
					diff = 2 * diff
				h1 = old.hour
				m1 = old.minute
				h2 = op.hour
				m2 = op.minute
				if dx and sx:
					# Percorso non attivo per tutto il giorno
					da = [-1 for i in range(24)]
					a = [-1 for i in range(24)]
					break
				if diff <= MAX_PERIODO_PERCORSO_ATTIVO:
					if dx:
						h2 = 23
					"""
					if id_percorso == '51035':
						print "%d - %d" % (h1, h2)
					"""
					for i in range(h1, h2 + 1):
						sum[i] += diff.seconds
						cnt[i] += 1
				else:
					if m1 > 0:
						a[h1] = m1
					else:
						da[h1] = -1
						a[h1] = -1
					if dx:
						h2 = 24
					for i in range(h1 + 1, h2):
						da[i] = -1
						a[i] = -1
					if not dx:
						da[h2] = m2
				old = op
			"""
			if id_percorso == '51035':
				print cnt
				print sum
			"""
			for h in range(24):
				if cnt[h] > 0:
					f = sum[h] / cnt[h]
				else:
					f = -1
				fp = FrequenzaPercorso(
					id_percorso=id_percorso,
					ora_inizio=h,
					giorno_settimana=giorno_settimana,
					frequenza=f,
					da_minuto=da[h],
					a_minuto=a[h],
				)
				#print fp.ora_inizio
				fp.save()


def calcola_frequenze(percorsi_da_rete=True):
	def cerca_giorno(i):
		if i < 0 or i > 6:
			raise Exception("Il giorno deve variare tra 0 (lunedi') e 6 (domenica)")
		d = date.today()
		while True:
			if Festivita.get_weekday(d, compatta_feriali=True) == i:
				return d
			d += timedelta(days=1)

	giorni = set([0, 5, 6])
	for gi in giorni:
		g = cerca_giorno(gi)
		print g
		calcola_frequenze_giorno(g, gi, percorsi_da_rete)


def elabora_statistiche(data_inizio, data_fine, min_weight=5):
	with transaction():
		StatTempoArcoNew.objects.all().delete()
		StatTempoAttesaPercorsoNew.objects.all().delete()
		for s in StatPeriodoAggregazione.objects.all():
			print s
			wds = [getattr(s, "wd%d" % wd) for wd in range(0, 7)]
			print wds
			ltas = LogTempoArco.objects.filter(data__gte=data_inizio, data__lte=data_fine, ora__gte=s.ora_inizio, ora__lt=s.ora_fine).order_by('id_palina_s', 'id_palina_t')
			cnt = 0.0
			tot = 0.0
			ids, idt = None, None
			for lta in batch_qs(ltas):
				ids2, idt2 = lta.id_palina_s, lta.id_palina_t
				if (ids2, idt2) != (ids, idt):
					print cnt, ids
					if ids != None and cnt >= min_weight:
						print "Salvo", ids, idt, tot/cnt, s
						sta = StatTempoArcoNew(
							id_palina_s=ids,
							id_palina_t=idt,
							tempo=tot / cnt,
							numero_campioni=cnt,
							periodo_aggregazione=s,
						)
						sta.save()
					cnt = 0.0
					tot = 0.0
					ids, idt = ids2, idt2
				wd = lta.data.weekday()
				if wds[wd]:
					tot += lta.peso * lta.tempo
					cnt += lta.peso
			if ids != None and cnt >= min_weight:
				sta = StatTempoArcoNew(
					id_palina_s=ids,
					id_palina_t=idt,
					tempo=tot / cnt,
					numero_campioni=cnt,
					periodo_aggregazione=s,
				)
				sta.save()
			lta = None
			ltaps = LogTempoAttesaPercorso.objects.filter(data__gte=data_inizio, data__lte=data_fine, ora__gte=s.ora_inizio, ora__lt=s.ora_fine).order_by('id_percorso')
			cnt = 0
			tot = 0.0
			idp = None
			for ltap in batch_qs(ltaps):
				idp2 = ltap.id_percorso
				if idp != idp2:
					if idp != None and cnt >= min_weight:
						StatTempoAttesaPercorsoNew(
							id_percorso=idp,
							tempo=tot / cnt,
							numero_campioni=cnt,
							periodo_aggregazione=s,
						).save()
					cnt = 0
					tot = 0.0
					idp = idp2
				wd = ltap.data.weekday()
				if wds[wd]:
					tot += ltap.tempo
					cnt +=1
			if idp != None and cnt >= min_weight:
				StatTempoAttesaPercorsoNew(
					id_percorso=idp,
					tempo=tot / cnt,
					numero_campioni=cnt,
					periodo_aggregazione=s,
				).save()


# Analisi
class Avg(object):
	def __init__(self):
		object.__init__(self)
		self.cnt = 0
		self.tot = 0
		self.min = None
		self.max = None

	def aggiungi(self, k):
		self.cnt +=1
		self.tot += k

	def aggiungi_percentuale(self, a1, a2):
		print a1, a2
		diff = float(abs(a1 - a2))
		self.aggiungi(diff / max((a1, a2)))
		if self.min is None or diff < self.min:
			self.min = diff
		if self.max is None or diff > self.max:
			self.max = diff

	def media(self):
		print self.tot, self.cnt
		return float(self.tot) / float(self.cnt)

	def media_percentuale(self):
		return self.media() * 100

	def get_statistiche(self):
		return "min: %.0f, max: %.0f, media: %.0f%%" % (self.min, self.max, self.media_percentuale())

def organizza_arrivi_ricalcolati(palina):
	a = {}
	for k in palina.fermate:
		arr = palina.fermate[k].arrivi
		for el in arr:
			a[el['id_veicolo']] = el
	return a

def confronta_arrivi(paline):
	tot = 0
	trov = 0
	errore_numero = Avg()
	errore_tempo = Avg()
	for palina in paline:
		ar = organizza_arrivi_ricalcolati(palina)
		palina.aggiorna_arrivi()
		for id_veicolo in palina.arrivi:
			tot += 1
			if id_veicolo in ar:
				trov += 1
				a1 = palina.arrivi[id_veicolo]
				a2 = ar[id_veicolo]
				f1 = a1['fermate']
				f2 = a2['fermate']
				errore_numero.aggiungi_percentuale(f1, f2)
				t1 = a1['tempo']
				t2 = a2['tempo']
				if t1 != -1 and t2 != -1:
					errore_tempo.aggiungi_percentuale(t1, t2)
	print "Trovate: %d su %d" % (trov, tot)
	print "Errore numero femate: %s" % errore_numero.get_statistiche()
	print "Errore tempi attesa: %s" % errore_tempo.get_statistiche()

def carica_orari_fr_da_file(r, g, filename):
	def converti_ora_giorno(s, d):
		h, m = s.split(':')
		today = date.today()
		h = int(h)
		while h > 23:
			d += 1
			h -= 24
			today += timedelta(days=1)
		t = time(h, int(m))
		return t, d, dateandtime2datetime(today, t)

	print "Carico orari FL"
	f = open(filename, 'r')
	for l in f:
		a = l.split("\t")
		if len(a) > 4 and (a[4].startswith('LE') or a[4].startswith('FL')):
			id_percorso = a[5]
			validita = a[0]
			day = None
			if validita.find('FESTIVO') != -1:
				day = 6
			elif validita.find('FERIALE') != -1:
				day = 0
			elif validita.find('SABATO') != -1:
				day = 5
			if day is not None and id_percorso in r.percorsi:
				p = r.percorsi[id_percorso]
				i = 14
				for tp in p.tratti_percorso:
					t1, d1, dt1 = converti_ora_giorno(a[i], day)
					t2, d2, dt2 = converti_ora_giorno(a[i + 3], day)
					f1 = tp.s.id_fermata
					f2 = tp.t.id_fermata
					perc = (dt2 - dt1).seconds
					#print f1, f2, perc
					aat = g.archi[(3, f1)]
					apt = g.archi[(5, f1, f2)]
					aat.aggiungi_partenza(t1, d1)
					apt.aggiungi_partenza(t1, perc, d2)
					i += 3

def test_ferrovia(r, g):
	for id_percorso in ['51305', '51306']:
		perc = r.percorsi[id_percorso]
		for t in perc.tratti_percorso:
			f = t.s
			aat = g.archi[(3, f.id_fermata)]
			apt = g.archi[(5, f.id_fermata, t.t.id_fermata)]
			print f.id_fermata
			tod = date2datetime(date.today())
			tom = tod + timedelta(days=1)
			while tod < tom:
				#print tod
				aat.aggiungi_partenza(tod)
				apt.aggiungi_partenza(tod, 55)
				tod += timedelta(minutes=1)


def get_weekday_caching(t, opz):
	if t.day == opz['giorno']:
		return opz['wd_giorno']
	return opz['wd_giorno_succ']


def salva_archi_tomtom_su_db(grafo, num=1, den=1):
	n = len(grafo.archi)
	dim = n / den
	start = (num - 1) * dim
	stop = num * dim
	i = 0
	with transaction():
		for eid in grafo.archi:
			i += 1
			if i % 100 == 0:
				print "%d%%" % int(100 * float(i) / n)
			if start <= i-1 and i-1 < stop and eid[0] == 12:
				a = grafo.archi[eid]
				s = a.to_model()
				s.save()

def analisi_velocita_archi(r, g, opz=None):
	if opz is None:
		opz = r.get_opzioni_calcola_percorso(True, True, True, True, 1)
	# dijkstra = DijkstraPool(g, 1)
	# opz['dijkstra'] = dijkstra
	n = datetime.now()
	d = defaultdict(int)
	for eid in g.archi:
		tipo = eid[0]
		if tipo not in [12, 16, 97, 98, 99]:
			e = g.archi[eid]
			cs = e.s.get_coordinate()
			ct = e.t.get_coordinate()
			if cs is not None and ct is not None:
				ip, tv = e.get_tempo(n, opz)
				dist = geomath.distance(cs[0], ct[0])
				if ip > 0:
					v = dist / tv
					if v > d[tipo]:
						d[tipo] = v
					if v > 18:
						print v, eid, e, e.s.rete_fermata.rete_palina.nome
	return d


class Qualita(object):
	def __init__(self, id=''):
		super(Qualita, self).__init__()
		self.id = id
		self.ultimo_aggiornamento = None
		self.ultimo_aggiornamento_completo = None
		self.durata_ultimo_ciclo = None
		self.percorsi_ok = None
		self.percorsi_totali = None
		self.risposte_ok = None
		self.risposte_totali = None

	def _get_qualita_derivata(self):
		now = datetime.now()
		return {
			'ritardo_ultimo_aggiornamento_parziale': (
				now + self.durata_ultimo_ciclo - self.ultimo_aggiornamento
			) if self.ultimo_aggiornamento is not None else None,
			'ritardo_ultimo_aggiornamento_completo': (
				now + self.durata_ultimo_ciclo - self.ultimo_aggiornamento_completo
			) if self.ultimo_aggiornamento_completo is not None else None,
			'tasso_errore': (
				(self.risposte_totali - self.risposte_ok) / float(self.risposte_totali)
			) if self.risposte_totali is not None else None,
		}

	def _get_qualita_base(self):
		return {
			'ultimo_aggiornamento': self.ultimo_aggiornamento,
			'ultimo_aggiornamento_completo': self.ultimo_aggiornamento_completo,
			'durata_ultimo_ciclo': self.durata_ultimo_ciclo,
			'percorsi_ok': self.percorsi_ok,
			'percorsi_totali': self.percorsi_totali,
			'risposte_ok': self.risposte_ok,
			'risposte_totali': self.risposte_totali,
		}

	def get_qualita(self):
		q = self._get_qualita_base()
		q.update(self._get_qualita_derivata())
		return q

	def serializza_dinamico(self):
		q = self._get_qualita_base()
		q.update({
			'type': 'Qualita',
			'id': self.id,
		})
		return q

	def deserializza_dinamico(self, res):
		self.ultimo_aggiornamento = res['ultimo_aggiornamento']
		self.ultimo_aggiornamento_completo = res['ultimo_aggiornamento_completo']
		self.durata_ultimo_ciclo = res['durata_ultimo_ciclo']
		self.percorsi_ok = res['percorsi_ok']
		self.percorsi_totali = res['percorsi_totali']
		self.risposte_ok = res['risposte_ok']
		self.risposte_totali = res['risposte_totali']


class QualitaAtac(Qualita):
	def start_ciclo(self):
		self.qnew = Qualita()
		self.qnew.percorsi_totali = 0
		self.qnew.percorsi_ok = 0
		self.qnew.risposte_ok = 0
		self.qnew.risposte_totali = 0
		self.qnew.ultimo_aggiornamento = datetime.now()

	def stop_ciclo(self):
		self.risposte_ok = self.qnew.risposte_ok
		self.risposte_totali = self.qnew.risposte_totali
		self.percorsi_ok = self.qnew.percorsi_ok
		self.percorsi_totali = self.qnew.percorsi_totali
		now = datetime.now()
		self.durata_ultimo_ciclo = now - self.qnew.ultimo_aggiornamento
		if self.percorsi_ok > 0:
			self.ultimo_aggiornamento = now
		if self.percorsi_ok == self.percorsi_totali:
			self.ultimo_aggiornamento_completo = now

	def percorso_ok(self):
		self.qnew.percorsi_ok += 1
		self.qnew.percorsi_totali += 1
	
	def percorso_ko(self):
		self.qnew.percorsi_totali += 1

	def risposta_ok(self):
		self.qnew.risposte_ok += 1
		self.qnew.risposte_totali += 1

	def risposta_ko(self):
		self.qnew.risposte_totali += 1

def analizza_consistenza_rete(rete, correggi=False):
	for id_fermata in rete.fermate:
		f = rete.fermate[id_fermata]
		id_palina = f.rete_palina.id_palina
		id_percorso = f.rete_percorso.id_percorso
		elimina = []
		out = []
		for a in f.arrivi:
			try:
				id_veicolo = a['id_veicolo']
				v = rete.veicoli[id_veicolo]
			except:
				print id_palina, id_percorso, id_veicolo, 'Veicolo non riconosciuto'
				out.append((id_palina, id_percorso, id_veicolo, 'Veicolo non riconosciuto'))
				elimina.append(a)
				break
			if v.tratto_percorso.rete_percorso.id_percorso != id_percorso:
				print id_palina, id_percorso, id_veicolo, 'Veicolo sul percorso %s' % v.tratto_percorso.rete_percorso.id_percorso
				out.append((id_palina, id_percorso, id_veicolo, 'Veicolo sul percorso %s' % v.tratto_percorso.rete_percorso.id_percorso))
				elimina.append(a)
		if correggi:
			for a in elimina:
				f.arrivi.remove(a)
	return out

associazione_percorsi_cities = {}

def percosi_cities_init():
	if percorsi_cities_data[0] is None or percorsi_cities_data[0] != date.today():
		percorsi_cities_data[0] = date.today()
		percorsi_cities.clear()
		pcs = LogPercorsoCities.objects.filter(data=date.today())
		for pc in pcs:
			percorsi_cities[pc.id_percorso] = [pc.riconosciuto, pc.conteggio]
	pas = PercorsoAtac.objects.all()
	for pa in pas:
		associazione_percorsi_cities[pa.id_percorso_atac] = pa.percorso.id_percorso

def log_percorso_cities(id_percorso, id_linea, riconosciuto):
	if not id_percorso in percorsi_cities:
		percorsi_cities[id_percorso] = [riconosciuto, 1]
		LogPercorsoCities(
			data=percorsi_cities_data[0],
			id_percorso=id_percorso,
			id_linea=id_linea,
			riconosciuto=riconosciuto,
			conteggio=1,
		).save()
	else:
		percorsi_cities[id_percorso][1] += 1

def percorsi_cities_sincronizza():
	for id_percorso in percorsi_cities:
		riconosciuto, conteggio = percorsi_cities[id_percorso]
		ps = LogPercorsoCities.objects.filter(data=percorsi_cities_data[0], id_percorso=id_percorso)
		if len(ps) > 0:
			for p in ps[1:]:
				p.delete()
			p = p[0]
			p.conteggio = conteggio
			p.save()


def grafo2shape(g, path, filename):
	"""
	Esporta il grafo g come shapefile

	path: cartella nella quale creare gli shapefile
	Il nome degli shapefile ha lo schema seguente:
	LINEA_PERCORSO_percorso.shp/dbf/...
	LINEA_PERCORSO_fermate.shp/dbf/...
	"""
	base_file_name = "grafo"
	with geomath.zipped_shapefile(shapefile.POLYLINE, path, filename, gbfe=True) as shp_p:
		shp_p.autoBalance = 1
		shp_p.field('EID', 'C', '80')
		shp_p.field('ID_S', 'C', '80')
		shp_p.field('ID_T', 'C', '80')
		shp_p.field('DESC', 'C', '80')
		for eid in g.archi:
			e = g.archi[eid]
			if e.id[0] == 12:
				line = e.get_coordinate()
				desc = ""
				if e.id[0] != 12:
					print eid, line
				else:
					desc = e.get_nome().encode('iso-8859-1')
				shp_p.line(parts=[line])
				shp_p.record(
					EID=str(e.id),
					ID_S=str(e.s.id),
					ID_T=str(e.t.id),
					DESC=desc,
				)
