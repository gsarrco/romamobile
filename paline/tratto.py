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

from datetime import date, time, datetime, timedelta
from servizi.utils import RPyCAllowRead, modifica_url_con_storia
from django.utils.safestring import mark_safe
from servizi.utils import ricapitalizza
from geomath import gbfe_to_wgs84
from django.utils.translation import ugettext as _
from django.template.defaultfilters import date as datefilter
from pprint import pprint
import cPickle as pickle

class Tratto(RPyCAllowRead):
	def __init__(self, parent, tempo):
		RPyCAllowRead.__init__(self)
		self.sub = []
		self.tempo_attesa = 0
		self.tempo_percorrenza = 0
		self.distanza = 0
		self.poly = []
		self.parent = parent
		self.tempo = tempo
		if parent is not None:
			parent.sub.append(self)
			
	def __getstate__(self):
		state = self.__dict__.copy()
		del state['parent']
		return state
		
	def __setstate__(self, state):
		self.__dict__.update(state)
		for s in self.sub:
			s.__dict__['parent'] = self
		if not 'parent' in self.__dict__:
			self.__dict__['parent'] = None
		
	def get_funzione_ric(self, fun_get, val_init=0, fun_comb=lambda s, v, e: v + e):
		"""
		Estrae ricorsivamente dai figli e combina i risultati
		
		val_init: valore di default
		fun_get(self): estrae i dati dalle foglie (self)
		fun_comb(self, val, ext): estende l'oggetto che contiene i risultati (val) con i nuovi risultati (ext)
		"""
		if len(self.sub) == 0:
			return fun_get(self)
		v = val_init
		for s in self.sub:
			v = fun_comb(self, v, s.get_funzione_ric(fun_get, val_init, fun_comb))
		return v
		
	def get_poly(self):
		return self.get_funzione_ric(
			lambda s: s.poly,
			[],
			lambda s, v, e: v + e,
		)
		
	def get_poly_wgs84(self):
		return [gbfe_to_wgs84(p[0], p[1]) for p in self.get_poly()]
	
	def get_punto(self):
		p = self.get_poly()
		if len(p) > 0:
			return p[0]
		return None
	
	def get_punto_wgs_84(self):
		p = self.get_punto()
		if p is None:
			return None
		return gbfe_to_wgs84(p[0], p[1])
	
	def get_punto_fine(self):
		p = self.get_poly()
		if len(p) > 0:
			return p[-1]
		return None
	
	def get_punto_fine_wgs_84(self):
		p = self.get_punto_fine()
		if p is None:
			return None
		return gbfe_to_wgs84(p[0], p[1])	
		
	def get_tempo_attesa(self):
		return self.get_funzione_ric(lambda s: s.tempo_attesa)
		
	def get_tempo_percorrenza(self):
		return self.get_funzione_ric(lambda s: s.tempo_percorrenza)

	def get_distanza(self):
		return self.get_funzione_ric(lambda s: s.distanza)
	
	def get_tempo_totale(self):
		#print "Tempo attesa:", self.get_tempo_attesa()
		#print "Tempo percorrenza:", self.get_tempo_percorrenza()
		return self.get_tempo_attesa() + self.get_tempo_percorrenza()
	
	def stampa(self, indent=0):
		spazi = "  " * indent
		print spazi + "Tipo: ", type(self)
		print spazi + "Partenza alle: ", self.tempo
		print spazi + "Tempo attesa: ", self.tempo_attesa
		print spazi + "Tempo percorrenza: ", self.tempo_percorrenza
		print spazi + "Tempo attesa ric.:", self.get_tempo_attesa()
		print spazi + "Tempo percorrenza ric.:", self.get_tempo_percorrenza()
		print spazi + "Tempo totale ric.:", self.get_tempo_totale()
		print spazi + "Arrivo alle: ", self.tempo + timedelta(seconds=self.get_tempo_totale())
		print
		for s in self.sub:
			s.stampa(indent + 1)
			
	def ricalcola_tempi(self, rete, grafo, opz):
		pass
			
	def attualizza(self, tempo, rete, grafo, opz):
		self.tempo = tempo
		for s in self.sub:
			s.attualizza(tempo, rete, grafo, opz)
			tempo += timedelta(seconds=s.get_tempo_totale())
		self.ricalcola_tempi(rete, grafo, opz)


class TrattoRoot(Tratto):
	def __init__(self, tempo):
		Tratto.__init__(self, None, tempo)
		self.partenza = None
		self.arrivo = None

class TrattoBus(Tratto):
	def __init__(self, parent, tempo, rete_fermata_s, tempo_attesa, tipo_attesa, attesa_salita):
		Tratto.__init__(self, parent, tempo)
		fermata = rete_fermata_s
		palina = fermata.rete_palina
		self.id_percorso = fermata.rete_percorso.id_percorso
		self.descrizione_percorso = ricapitalizza(fermata.rete_percorso.descrizione)
		self.id_linea = fermata.rete_percorso.id_linea
		self.destinazione = ricapitalizza(fermata.rete_percorso.tratti_percorso[-1].t.rete_palina.nome)		
		self.id_palina_s = palina.id_palina
		self.nome_palina_s = ricapitalizza(palina.nome)
		self.coordinate_palina_s = (palina.x, palina.y)
		self.id_palina_t = None
		self.nome_palina_t = None
		self.coordinate_palina_t = None
		TrattoBusSalita(self, tempo, attesa_salita)
		self.tratto_attesa = TrattoBusAttesa(self, tempo + timedelta(seconds=attesa_salita), tempo_attesa, tipo_attesa)
		
	def imposta_fermata_t(self, f):
		p = f.rete_palina
		self.id_palina_t = p.id_palina
		self.nome_palina_t = ricapitalizza(p.nome)
		self.coordinate_palina_t = (p.x, p.y)
				
class TrattoBusSalita(Tratto):
	def __init__(self, parent, tempo, tempo_salita):
		Tratto.__init__(self, parent, tempo)		
		self.tempo_percorrenza = tempo_salita
		
		
class TrattoBusDiscesa(Tratto):
	def __init__(self, parent, tempo, rete_fermata, tempo_discesa):
		Tratto.__init__(self, parent, tempo)
		parent.imposta_fermata_t(rete_fermata)
		self.tempo_percorrenza = tempo_discesa

class TrattoBusAttesa(Tratto):
	def __init__(self, parent, tempo, tempo_attesa, tipo_attesa="P"):
		"""
		Inizializzatore
		
		tipo_attesa può assumere i seguenti valori:
			'P': prevista da InfoTP
			'S': dedotta dalle statistiche
			'O': dedotta dall'orario
		"""
		Tratto.__init__(self, parent, tempo)		
		self.tempo_attesa = tempo_attesa
		self.tipo_attesa = tipo_attesa
		
	def ricalcola_tempi(self, rete, grafo, opz):
		fermata = rete.fermate_da_palina[(self.parent.id_palina_s, self.parent.id_percorso)]
		a = grafo.archi[(3, fermata.id_fermata)]
		self.tempo_attesa, self.tipo_attesa = a.get_tempo_vero(self.tempo, opz)
			
		
class TrattoBusArcoPercorso(Tratto):
	"""
	Inizializzatore
	
	tipo_percorrenza può assumere i seguenti valori:
		'P': prevista da InfoTP
		'S': dedotta dalle statistiche
		'D': dedotta in base alla distanza
	"""	
	def __init__(self, parent, tempo, rete_tratto_percorso, tempo_percorrenza, tipo_percorrenza, poly):
		Tratto.__init__(self, parent, tempo)
		palina = rete_tratto_percorso.s.rete_palina
		self.id_palina_s = palina.id_palina
		self.nome_palina_s = ricapitalizza(palina.nome)
		self.coordinate_palina_s = (palina.x, palina.y)
		palina = rete_tratto_percorso.t.rete_palina
		self.id_palina_t = palina.id_palina
		self.nome_palina_t = ricapitalizza(palina.nome)
		self.coordinate_palina_t = (palina.x, palina.y)
		self.tempo_percorrenza = tempo_percorrenza
		self.tipo_percorrenza = tipo_percorrenza
		self.poly = poly
		self.distanza = rete_tratto_percorso.rete_tratto_percorsi.distanza()
		
	def ricalcola_tempi(self, rete, grafo, opz):
		fermata_s = rete.fermate_da_palina[(self.id_palina_s, self.parent.id_percorso)]
		fermata_t = rete.fermate_da_palina[(self.id_palina_t, self.parent.id_percorso)]
		a = grafo.archi[(5, fermata_s.id_fermata, fermata_t.id_fermata)]
		self.tempo_percorrenza, self.tipo_percorrenza = a.get_tempo_vero(self.tempo, opz)
					
		
class TrattoMetro(TrattoBus):
	def __init__(self, parent, tempo, rete_fermata_s, tempo_attesa, tipo_attesa, attesa_salita, interscambio=False):
		Tratto.__init__(self, parent, tempo)
		fermata = rete_fermata_s
		palina = fermata.rete_palina
		self.interscambio = interscambio
		self.destinazione = ricapitalizza(fermata.rete_percorso.tratti_percorso[-1].t.rete_palina.nome)
		self.id_percorso = fermata.rete_percorso.id_percorso
		self.descrizione_percorso = ricapitalizza(fermata.rete_percorso.descrizione)
		self.id_linea = fermata.rete_percorso.id_linea		
		self.id_palina_s = palina.id_palina
		self.nome_palina_s = ricapitalizza(palina.nome)
		self.coordinate_palina_s = (palina.x, palina.y)
		self.id_palina_t = None
		self.nome_palina_t = None
		self.coordinate_palina_t = None
		if interscambio:
			TrattoMetroInterscambio(self, tempo, attesa_salita)
		else:
			TrattoMetroSalita(self, tempo, attesa_salita)
		self.tratto_attesa = TrattoMetroAttesa(self, tempo + timedelta(seconds=attesa_salita), tempo_attesa, tipo_attesa)

class TrattoMetroAttesa(TrattoBusAttesa):
	pass

class TrattoMetroSalita(TrattoBusSalita):
	pass

class TrattoMetroDiscesa(TrattoBusDiscesa):
	pass

class TrattoMetroInterscambio(TrattoMetroSalita):
	pass

class TrattoMetroArcoPercorso(TrattoBusArcoPercorso):
	pass

# begin teletrasporto

class TrattoTeletrasporto(TrattoMetro):
	pass

class TrattoTeletrasportoSalita(TrattoBusSalita):
	pass

class TrattoTeletrasportoDiscesa(TrattoBusDiscesa):
	pass

class TrattoTeletrasportoArcoPercorso(Tratto):
	"""
	Inizializzatore
	
	tipo_percorrenza può assumere i seguenti valori:
		'P': prevista da InfoTP
		'S': dedotta dalle statistiche
		'D': dedotta in base alla distanza
	"""	
	def __init__(self, parent, tempo, palina_s, palina_t, tempo_percorrenza):
		Tratto.__init__(self, parent, tempo)
		palina = palina_s
		self.id_palina_s = palina.id_palina
		self.nome_palina_s = ricapitalizza(palina.nome)
		self.coordinate_palina_s = (palina.x, palina.y)
		palina = palina_t
		self.id_palina_t = palina.id_palina
		self.nome_palina_t = ricapitalizza(palina.nome)
		self.coordinate_palina_t = (palina.x, palina.y)
		self.tempo_percorrenza = tempo_percorrenza
		self.tipo_percorrenza = ''
		self.poly = [self.coordinate_palina_s, self.coordinate_palina_t]
		self.distanza = 0

# end teletrasporto

class TrattoFC(TrattoMetro):
	pass

class TrattoFCAttesa(TrattoMetroAttesa):
	pass

class TrattoFCSalita(TrattoMetroSalita):
	pass

class TrattoFCDiscesa(TrattoMetroDiscesa):
	pass

class TrattoFCInterscambio(TrattoMetroInterscambio):
	pass

class TrattoFCArcoPercorso(TrattoMetroArcoPercorso):
	pass

class TrattoTreno(TrattoMetro):
	pass

class TrattoTrenoAttesa(TrattoMetroAttesa):
	pass

class TrattoTrenoSalita(TrattoMetroSalita):
	pass

class TrattoTrenoDiscesa(TrattoMetroDiscesa):
	pass

class TrattoTrenoInterscambio(TrattoMetroInterscambio):
	pass

class TrattoTrenoArcoPercorso(TrattoMetroArcoPercorso):
	pass


class TrattoPiedi(Tratto):
	pass

class TrattoPiediArco(Tratto):
	def __init__(self, parent, tempo, arco, tempo_percorrenza):
		Tratto.__init__(self, parent, tempo)
		self.nome_arco = arco.get_nome()
		self.distanza = arco.w
		self.tempo_percorrenza = tempo_percorrenza
		self.id = arco.id
		self.id_arco = "%d-%d" % (arco.id[1], arco.id[2])
		self.tipo = arco.id[0]
		self.poly = arco.get_coordinate()

class TrattoPiediArcoDistanzaPaline(Tratto):
	def __init__(self, parent, tempo, distanza, tempo_percorrenza):
		Tratto.__init__(self, parent, tempo)
		self.nome_arco = ""
		self.distanza = distanza
		self.tempo_percorrenza = tempo_percorrenza
			
class TrattoBici(Tratto):
	pass

class TrattoBiciArco(TrattoPiediArco):
	pass

class TrattoBiciArcoDistanzaPaline(TrattoPiediArcoDistanzaPaline):
	pass

class TrattoAuto(Tratto):
	def __init__(self, parent, tempo, carsharing=False):
		Tratto.__init__(self, parent, tempo)
		self.carsharing = carsharing

class TrattoAutoArco(TrattoPiediArco):
	pass

class TrattoCarPooling(Tratto):
	def __init__(self, parent, tempo, offset):
		Tratto.__init__(self, parent, tempo)
		self.offset = offset

class TrattoCarPoolingArco(TrattoPiediArco):
	pass

class TrattoCarPoolingAttesa(Tratto):
	def __init__(self, parent, tempo, tempo_attesa):
		Tratto.__init__(self, parent, tempo)
		self.tempo_attesa = tempo_attesa
		
class TrattoRisorsa(Tratto):
	def __init__(self, parent, tempo, ct_ris, id_ris, icon, icon_size, nome, descrizione, poly):
		Tratto.__init__(self, parent, tempo)
		self.id_ris = id_ris
		self.ct_ris = ct_ris
		self.icon = icon
		self.icon_size=icon_size
		self.nome_luogo=nome
		self.descrizione=descrizione
		self.poly = poly

# Formattatori
tipi_formattatore = {}

def to_min(sec, hide_zero=False):
	m = round(sec / 60.0)
	if m == 1:
		return _("1 minuto")
	if m == 0:
		if hide_zero:
			return ""
		else:
			return _("meno di 1 minuto")
	if m < 60:
		return _("%(tempo)d minuti") % {'tempo': m}
	h = int(m / 60)
	if h > 1:
		ore_pl = _("ore")
	else:
		ore_pl = _("ora")
	return _("%(ore)d %(ore_pl)s %(minuti)s") % {
		'ore': h,
		'ore_pl': ore_pl,
		'minuti': to_min((m % 60) * 60, True)
	}


def formattatore(tipo, tratti, post=False):
	def decoratore(k):
		for t in tratti:
			tipi_formattatore[(tipo, t.__name__, post)] = k
		return k
	return decoratore

def arrotonda_distanza(n, step=50):
	k = round(n / float(step)) * step
	if k == 0:
		return _("meno di %(dist).0f metri") % {'dist': step}
	if k > 1000:
		return _("%(dist).1f km") % {'dist': (k / 1000.0)}
	return _("%(dist).0f metri") % {'dist': k}

def arrotonda_tempo(t):
	if t.second > 30:
		t += timedelta(minutes=1)
	return datefilter(t, _("H:i"))

def formatta_percorso(tratto, tipo, ft, opzioni):
	try:
		nome = tratto.clsname
	except Exception:
		nome = tratto.__class__.__name__
	if (tipo, nome, False) in tipi_formattatore:
		ft = tipi_formattatore[(tipo, nome, False)](tratto, ft, opzioni)
	for s in tratto.sub:
		formatta_percorso(s, tipo, ft, opzioni)
	if (tipo, nome, True) in tipi_formattatore:
		ft = tipi_formattatore[(tipo, nome, True)](tratto, ft, opzioni)		
	return ft

class PercorsoIndicazioni(object):
	def __init__(self):
		object.__init__(self)
		self.indicazioni = []
	
	def aggiungi(self, tempo, desc, id=None, dettagli=None, punto=None):
		self.indicazioni.append({
			'tempo': arrotonda_tempo(tempo),
			'desc': desc,
			'id': id,
			'dettagli': dettagli,
			'punto': {'x': "%f" % punto[0], 'y': "%f" % punto[1]}
		})
		
class PercorsoIndicazioniIcona(object):
	def __init__(self):
		object.__init__(self)
		self.indicazioni = []
		self.ricevi_nodo = True
		self.numero_nodi = 0
		self.numero_archi = 0
		
	def aggiungi_nodo(self, t, nome, id, tipo, punto, url='', icona='nodo.png', overwrite=False, info_exp=''):
		"""
		Tipi:
			F: fermata
			I: indirizzo
			L: luogo
		"""
		if self.ricevi_nodo or overwrite:
			nodo = {'nodo': {
				't': arrotonda_tempo(t),
				'nome': nome,
				'id': id,
				'tipo': tipo,
				'punto': {'x': "%f" % punto[0], 'y': "%f" % punto[1]} if punto is not None else '',
				'url': url,
				'icona': icona,
				'numero': self.numero_nodi,
				'info_exp': info_exp,
			}}
			if self.ricevi_nodo:
				self.indicazioni.append(nodo)
				self.numero_nodi += 1
			else:
				nodo['nodo']['numero'] -= 1
				self.indicazioni[-1] = nodo
		self.ricevi_nodo = False
	
	
	def aggiungi_tratto(self, mezzo, linea, id_linea, dest, url='', id='', tipo_attesa='', tempo_attesa='', info_tratto='', info_tratto_exp='', icona=''):
		"""
		Mezzi:
			P: piedi
			B: bus/tram
			M: metro
			T: treno
			
		Tipo attesa:
			O: da orario (tempo_attesa è la stringa dell'orario)
			S: stimata
			P: prevista
		"""
		self.indicazioni.append({'tratto': {
			'mezzo': mezzo,
			'linea': linea,
			'id_linea': id_linea,
			'dest': dest,
			'url': url,
			'id': id,
			'tipo_attesa': tipo_attesa,
			'tempo_attesa': tempo_attesa,
			'info_tratto': info_tratto,
			'info_tratto_exp': info_tratto_exp,
			'icona': icona,
			'numero': self.numero_archi,
		}})
		self.numero_archi += 1
		self.ricevi_nodo = True
		
	def mark_safe(self):
		for i in self.indicazioni:
			if 'tratto' in i:
				a = i['tratto']
				a['info_tratto_exp'] = mark_safe(a['info_tratto_exp'])


class PercorsoStat(object):
	def __init__(self):
		self.distanza_totale = 0.0
		self.distanza_piedi = 0.0
		self.tempo_totale = 0.0
		
	def finalizza(self):
		self.distanza_totale_format = arrotonda_distanza(self.distanza_totale)
		self.distanza_piedi_format = arrotonda_distanza(self.distanza_piedi)
		self.tempo_totale_format = to_min(self.tempo_totale)
		


# Formattatori indicazioni testuali nuovo tipo
def fermate_intermedie(tratto):
	fermate = []
	old = None
	for s in tratto.sub:
		if isinstance(s, TrattoBusArcoPercorso):
			old = s
			fermate.append((arrotonda_tempo(s.tempo), s.nome_palina_s, s.id_palina_s, s.tipo_percorrenza))
	if old is not None:
		s = old
		fermate.append((arrotonda_tempo((s.tempo + timedelta(seconds = s.tempo_percorrenza))), s.nome_palina_t, s.id_palina_t, s.tipo_percorrenza))	
	return fermate

@formattatore('indicazioni_icona', [TrattoRoot])
def format_indicazioni_icona_root(tratto, ft, opz):
	if 'address' in tratto.partenza:
		ft.aggiungi_nodo(
			tratto.tempo,
			tratto.partenza['address'],
			'',
			'I',
			punto=tratto.get_punto_wgs_84()
		)
	
	elif 'id_palina' in tratto.partenza:
		id_palina = tratto.partenza['id_palina']
		ft.aggiungi_nodo(
			t=tratto.tempo,
			nome="%s (%s)" % (ricapitalizza(tratto.partenza['nome_palina']), id_palina),
			tipo='F',
			id=id_palina,
			punto=tratto.get_punto_wgs_84(),
		)		
	return ft


@formattatore('indicazioni_icona', [TrattoRoot], True)
def format_indicazioni_icona_root_post(tratto, ft, opz):
	if 'address' in tratto.arrivo:
		ft.aggiungi_nodo(
			tratto.tempo + timedelta(seconds=tratto.get_tempo_totale()),
			tratto.arrivo['address'],
			'',
			'I',
			punto=tratto.get_punto_fine_wgs_84()
		)
	
	elif 'id_palina' in tratto.arrivo:
		id_palina = tratto.arrivo['id_palina']
		ft.aggiungi_nodo(
			t=tratto.tempo,
			nome="%s (%s)" % (ricapitalizza(tratto.arrivo['nome_palina']), id_palina),
			tipo='F',
			id=id_palina,
			punto=tratto.get_punto_fine_wgs_84(),
		)		
	return ft

@formattatore('indicazioni_icona', [TrattoBus, TrattoMetro, TrattoTreno, TrattoFC, TrattoTeletrasporto])
def format_indicazioni_icona_tratto_bus(tratto, ft, opz):
	numero_fermate = len([x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)])
	fermate = _("fermata") if numero_fermate==1 else _("fermate")
	id_veicolo = None
	url = ''
	nome_fermata_s = tratto.nome_palina_s
	nome_fermata_t = tratto.nome_palina_t
	tempo_attesa = to_min(tratto.get_tempo_attesa())
	tempo_s = tratto.tempo
	tempo_t = tratto.tempo + timedelta(seconds=tratto.get_tempo_totale())
	if isinstance(tratto, TrattoFC):
		mezzo = 'T'
		icona = 'treno'
		tipo = 'S'
	elif isinstance(tratto, TrattoTreno):
		mezzo = 'T'
		icona = 'treno'
		tipo = 'O'
		tratti_intermedi = [x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)]
		tempo_attesa = arrotonda_tempo(tratti_intermedi[0].tempo)
	elif isinstance(tratto, TrattoTeletrasporto):
		mezzo = 'Z'
		icona = 'teletrasporto'
		tipo = 'S'			
	elif isinstance(tratto, TrattoMetro):
		mezzo = 'M'
		icona = 'metro'
		tipo = 'S'		
	elif isinstance(tratto, TrattoBus):
		mezzo = 'B'
		icona = 'bus'
		tipo = tratto.tratto_attesa.tipo_attesa
		nome_fermata_s += " (%s)" % tratto.id_palina_s
		nome_fermata_t += " (%s)" % tratto.id_palina_t
		if tipo == 'O':
			tipo = 'S'
		url = '/paline/percorso/%s?id_palina=%s' % (tratto.id_percorso, tratto.id_palina_s)
		if tipo[0] == 'P':
			if len(tipo) > 1:
				id_veicolo = tipo[1:]
				url = '/paline/percorso/%s?id_veicolo=%s&amp;id_palina=%s' % (tratto.id_percorso, id_veicolo, tratto.id_palina_s)
			else:
				url = '/paline/percorso/%s?id_palina=%s' % (tratto.id_percorso, tratto.id_palina_s)
			tipo = 'P'		

	id = "T-%s-%s" % (tratto.id_palina_s, tratto.id_percorso)
	dettagli = u''
	if 'espandi_tutto' in opz or ('espandi' in opz and opz['espandi']) == id:
		dettagli = u"<br />".join([u"&nbsp;%s %s" % (x[0], x[1]) for x in fermate_intermedie(tratto)])
			
	ft.aggiungi_nodo(
		t=tempo_s,
		nome=nome_fermata_s,
		tipo='F',
		id=tratto.id_palina_s,
		punto=tratto.get_punto_wgs_84(),
		url=('/paline/palina/%s' % tratto.id_palina_s) if mezzo == 'B' else '',
		overwrite=True,
	)
	ft.aggiungi_tratto(
		mezzo=mezzo,
		linea=tratto.descrizione_percorso,
		id_linea=tratto.id_linea,
		dest=tratto.destinazione,
		url=url,
		id=id,
		tipo_attesa=tipo,
		tempo_attesa=tempo_attesa,
		info_tratto=_("Per %(numero)d %(fermate)s (%(tempo)s)") % {
			'numero': numero_fermate,
			'fermate': fermate,
			'tempo': to_min(tratto.get_tempo_percorrenza()),
		},
		info_tratto_exp=dettagli,
		icona=icona + '.png'
	)
	ft.aggiungi_nodo(
		t=tempo_t,
		nome=nome_fermata_t,
		tipo='F',
		id=tratto.id_palina_t,
		punto=tratto.get_punto_fine_wgs_84(),
		url=('/paline/palina/%s' % tratto.id_palina_t) if mezzo == 'B' else '',
	)	
	return ft


@formattatore('indicazioni_icona', [TrattoPiedi, TrattoBici, TrattoAuto])
def format_indicazioni_icona_tratto_piedi(tratto, ft, opz):
	sub = [s for s in tratto.sub if isinstance(s, TrattoPiediArco)]
	if len(sub) > 0:
		distanza = arrotonda_distanza(tratto.get_distanza()).capitalize()
		id = "O-%s" % sub[0].id_arco
		dettagli = u''
		if 'espandi_tutto' in opz or ('espandi' in opz and opz['espandi']) == id:
			nome_corr = None
			for s in sub:
				if s.nome_arco != "" and s.nome_arco != nome_corr:
					dettagli += u"&nbsp;%s<br />" % s.nome_arco
					nome_corr = s.nome_arco
			dettagli += u"<br />".join([u"&nbsp;%s %s" % (x[0], x[1]) for x in fermate_intermedie(tratto)])
		bici = isinstance(tratto, TrattoBici)
		auto = isinstance(tratto, TrattoAuto)
		if bici:
			mezzo = 'C'
			icona = 'bici.png'
		elif auto:
			if tratto.carsharing:
				mezzo = 'CS'
				icona = 'carsharing.png'
			else:
				mezzo = 'A'
				icona = 'auto.png'
		else:
			mezzo = 'P'
			icona = 'piedi.png'
		ft.aggiungi_tratto(
			mezzo=mezzo,
			linea='',
			id_linea='',
			dest='',
			url='',
			id=id,
			tipo_attesa='',
			tempo_attesa='',
			info_tratto=_("%(distanza)s (%(tempo)s)" % {
				'distanza': distanza,
				'tempo': to_min(tratto.get_tempo_percorrenza()),
			}),
			info_tratto_exp=dettagli,
			icona=icona,
		)
	return ft

@formattatore('indicazioni_icona', [TrattoCarPooling])
def format_indicazioni_icona_tratto_car_pooling(tratto, ft, opz):
	sub = [s for s in tratto.sub if isinstance(s, TrattoCarPoolingArco)]
	nome_primo_arco = None
	if len(sub) > 0:
		distanza = arrotonda_distanza(tratto.get_distanza()).capitalize()
		id = "O-%s" % sub[0].id_arco
		dettagli = u''
		nome_corr = None
		for s in sub:
			if s.nome_arco != "" and s.nome_arco != nome_corr:
				dettagli += u"&nbsp;%s<br />" % s.nome_arco
				nome_corr = s.nome_arco
				if nome_primo_arco is None:
					nome_primo_arco = nome_corr
		dettagli += u"<br />".join([u"&nbsp;%s %s" % (x[0], x[1]) for x in fermate_intermedie(tratto)])
		ta = tratto.get_tempo_attesa()
		tp = tratto.get_tempo_percorrenza()
		tempo_attesa = to_min(ta)
		nome_ultimo_arco = nome_corr		
		ft.aggiungi_nodo(
			tratto.tempo,
			nome_primo_arco,
			'',
			'I',
			punto=tratto.get_punto_wgs_84()
		)
		ft.aggiungi_tratto(
			mezzo='CP',
			linea='',
			id_linea='',
			dest='',
			url='',
			id=id,
			tipo_attesa='E',
			tempo_attesa=tempo_attesa,
			info_tratto=_("%(distanza)s (%(tempo)s)" % {
				'distanza': distanza,
				'tempo': to_min(tp),
			}),
			info_tratto_exp=dettagli if 'espandi_tutto' in opz or ('espandi' in opz and opz['espandi']) == id else '',
			icona='carpooling.png',
		)
		ft.aggiungi_nodo(
			tratto.tempo + timedelta(seconds=ta + tp),
			nome_ultimo_arco,
			'',
			'I',
			punto=tratto.get_punto_fine_wgs_84()
		)			
	return ft


@formattatore('indicazioni_icona', [TrattoRisorsa])
def format_indicazioni_icona_tratto_risorsa(tratto, ft, opz):
	ft.aggiungi_nodo(
		tratto.tempo,
		tratto.nome_luogo,
		"RIS-%s-%s" % (tratto.ct_ris, tratto.id_ris),
		'L',
		punto=tratto.get_punto_wgs_84(),
		icona=tratto.icon,
		info_exp=tratto.descrizione,
	)
	return ft

	
# Formattatori indicazioni su mappa
@formattatore('mappa', [TrattoBus])
def format_mappa_tratto_bus(tratto, ft, opz):
	numero_fermate = len([x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)])
	fermate = _("fermata") if numero_fermate==1 else _("fermate")
	out = '[%s] ' % arrotonda_tempo(tratto.tempo)
	out += _("Alla fermata %(palina)s (%(id)s), prendi il %(linea)s per %(numero)d %(fermate)s") % {
		'palina': tratto.nome_palina_s,
		'id': tratto.id_palina_s,
		'linea': tratto.id_linea,
		'numero': numero_fermate, 
		'fermate': fermate,
	}	
	ft.add_polyline(tratto.get_poly_wgs84(), 0.7, '#7F0000', 5)
	ft.add_marker(gbfe_to_wgs84(*tratto.coordinate_palina_s), '/paline/s/img/partenza.png', icon_size=(16, 16), infobox=out, anchor=(8, 8))
	tratti_intermedi = [x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)]
	for s in tratti_intermedi[:-1]:
		infobox = '[%s] %s' % (arrotonda_tempo(s.tempo), s.nome_palina_t)
		ft.add_marker(gbfe_to_wgs84(*s.coordinate_palina_t), '/paline/s/img/fermata.png', icon_size=(16, 16), infobox=infobox, anchor=(8, 8))
	out = '[%s] ' % arrotonda_tempo(tratto.tempo + timedelta(seconds=tratto.get_tempo_totale()))
	out += _("Scendi alla fermata %(palina)s (%(id)s)") % {
		'palina': tratto.nome_palina_t,
		'id': tratto.id_palina_t,
	}
	ft.add_marker(gbfe_to_wgs84(*tratto.coordinate_palina_t), '/paline/s/img/arrivo.png', icon_size=(16, 16), infobox=out, anchor=(8, 8))
	return ft


@formattatore('mappa', [TrattoMetro, TrattoFC, TrattoTreno])
def format_mappa_tratto_metro(tratto, ft, opz):
	numero_fermate = len([x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)])
	fermate = _("fermata") if numero_fermate==1 else _("fermate")
	out = '[%s] ' % arrotonda_tempo(tratto.tempo)
	if tratto.interscambio:
		out += _("Scendi a %(palina)s e cambia con la %(desc)s per %(numero)d %(fermate)s") % {
			'palina': tratto.nome_palina_s,
			'desc': tratto.descrizione_percorso,
			'numero': numero_fermate,
			'fermate': fermate,
		}
	else:
		out += _("A %(palina)s, prendi la %(desc)s per %(numero)d %(fermate)s") %  {
			'palina': tratto.nome_palina_s,
			'desc': tratto.descrizione_percorso,
			'numero': numero_fermate,
			'fermate': fermate,
		}	
	color = '#000000'
	icona = 'treno'
	if tratto.id_linea == 'MEA':
		icona = 'metro'
		color = '#FF0000'
	if tratto.id_linea[:3] == 'MEB':
		icona = 'metro'
		color = '#0000FF'
	ft.add_polyline(tratto.get_poly_wgs84(), 0.7, color, 5)
	ft.add_marker(gbfe_to_wgs84(*tratto.coordinate_palina_s), '/paline/s/img/%s.png' % icona, icon_size=(16, 16), infobox=out)
	tratti_intermedi = [x for x in tratto.sub if isinstance(x, TrattoBusArcoPercorso)]
	for s in tratti_intermedi[:-1]:
		infobox = '[%s] %s' % (arrotonda_tempo(s.tempo), s.nome_palina_t)
		ft.add_marker(gbfe_to_wgs84(*s.coordinate_palina_t), '/paline/s/img/%s_fermata.png' % icona, icon_size=(16, 16), infobox=infobox, anchor=(8, 8))	
	out = '[%s] ' % arrotonda_tempo(tratto.tempo + timedelta(seconds=tratto.get_tempo_totale()))
	out += _("Scendi a %(palina)s") % {'palina': tratto.nome_palina_t}
	ft.add_marker(gbfe_to_wgs84(*tratto.coordinate_palina_t), '/paline/s/img/%s.png' % icona, icon_size=(16, 16), infobox=out, anchor=(8, 8))
	return ft


@formattatore('mappa', [TrattoTeletrasporto])
def format_mappa_teletrasporto(tratto, ft, opz):
	ft.add_marker(tratto.get_punto_wgs_84(), '/paline/s/img/teletrasporto.png', icon_size=(16, 16), infobox='Smaterializzazione Teletrasporto', anchor=(8, 8))
	color = '#B200FF'
	ft.add_polyline([tratto.get_punto_wgs_84(), tratto.get_punto_fine_wgs_84()], 1, color, 0.5)
	ft.add_marker(tratto.get_punto_fine_wgs_84(), '/paline/s/img/teletrasporto.png', icon_size=(16, 16), infobox='Rimaterializzazione Teletrasporto', anchor=(8, 8))
	return ft

@formattatore('mappa', [TrattoPiedi])
def format_mappa_piedi(tratto, ft, opz):
	color = '#000000'
	"""
	if int(tratto.tipo) != 12:
		color = '#00FF00'
	"""
	ft.add_polyline(tratto.get_poly_wgs84(), 1, color, 2.5)
	return ft

@formattatore('mappa', [TrattoBici])
def format_mappa_bici(tratto, ft, opz):
	ft.add_polyline(tratto.get_poly_wgs84(), 1, '#267F00', 3.5)
	return ft

@formattatore('mappa', [TrattoAuto, TrattoCarPooling])
def format_mappa_auto(tratto, ft, opz):
	ft.add_polyline(tratto.get_poly_wgs84(), 1, '#F600FF', 3.5)
	return ft


@formattatore('mappa', [TrattoRisorsa])
def format_mappa_luogo(tratto, ft, opz):
	ft.add_marker(
		tratto.get_punto_wgs_84(),
		icon=tratto.icon,
		icon_size=tratto.icon_size,
		infobox=tratto.nome_luogo,
		desc=tratto.descrizione,
	)
	return ft


@formattatore('mappa', [TrattoRoot])
def format_mappa_root(tratto, ft, opz):
	out = '[%s] ' % arrotonda_tempo(tratto.tempo)
	if tratto.partenza is None or 'address' not in tratto.partenza:
		out += _("Parti")
	else:
		out += _("Parti da %(luogo)s") % {'luogo': tratto.partenza['address']}	
	p = tratto.get_poly_wgs84()
	if len(p) > 0:
		ft.add_marker(p[0], '/paline/s/img/partenza_percorso.png', icon_size=(32, 32), infobox=out, drop_callback='drop_start')		
	return ft

@formattatore('mappa', [TrattoRoot], True)
def format_mappa_root_post(tratto, ft, opz):
	out = '[%s] ' % arrotonda_tempo(tratto.tempo + timedelta(seconds=tratto.get_tempo_totale()))
	if tratto.arrivo is None or 'address' not in tratto.arrivo:
		out += _("Sei arrivato")
	else:
		out += _("Sei arrivato a %s") % tratto.arrivo['address']
	p = tratto.get_poly_wgs84()
	if len(p) > 0:
		ft.add_marker(p[-1], '/paline/s/img/arrivo_percorso.png', icon_size=(32, 32), infobox=out, drop_callback='drop_stop')		
	return ft

# Formattatori per statistiche percorso
@formattatore('stat', [TrattoRoot])
def format_stat_root(tratto, ft, opz):
	ft.distanza_totale = tratto.get_distanza()
	ft.tempo_totale = tratto.get_tempo_totale()
	return ft
	
@formattatore('stat', [TrattoPiedi])
def format_stat_piedi(tratto, ft, opz):
	ft.distanza_piedi += tratto.get_distanza()
	return ft
	
@formattatore('stat', [TrattoRoot], True)
def format_stat_mappa_root_post(tratto, ft, opz):
	ft.finalizza()
	return ft

# Formattatore percorso auto salvato
@formattatore('auto_salvato', [TrattoAutoArco])
def format_auto_salvato_tratto_auto_arco(tratto, ft, opz):
	eid = tratto.id
	e = ft.grafo.archi[eid]
	ft.add_arco(
		t=tratto.tempo, 
		eid=eid,
		sid=e.s.id,
		tid=e.t.id,
		tp=tratto.tempo_percorrenza,
	)
	return ft