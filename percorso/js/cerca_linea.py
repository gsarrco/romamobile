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

from pyjamas.ui.RootPanel import RootPanel
from pyjamas.ui.VerticalPanel import VerticalPanel
from pyjamas.ui.HorizontalPanel import HorizontalPanel
from pyjamas.ui.VerticalSplitPanel import VerticalSplitPanel
from pyjamas.ui.SimplePanel import SimplePanel
from pyjamas.ui.FlowPanel import FlowPanel
from pyjamas.ui.DisclosurePanel import DisclosurePanel
from pyjamas.ui.TabPanel import TabPanel
from pyjamas.ui.Grid import Grid
from pyjamas.ui.Frame import Frame
from pyjamas.ui.TextBox import TextBox
from pyjamas.ui.TextArea import TextArea
from pyjamas.ui.HTML import HTML
from pyjamas.ui.HTMLPanel import HTMLPanel
from pyjamas.ui.Anchor import Anchor
from pyjamas.ui.Label import Label
from pyjamas.ui.CheckBox import CheckBox
from pyjamas.ui.ListBox import ListBox
from pyjamas.ui.Button import Button
from pyjamas.ui.RadioButton import RadioButton
from pyjamas.ui.PopupPanel import PopupPanel
from pyjamas.ui.KeyboardListener import KeyboardHandler
from pyjamas.ui.FocusListener import FocusHandler
from pyjamas.ui.Tree import Tree, TreeItem
from pyjamas.ui.Image import Image
from pyjamas.ui import HasAlignment
from pyjamas.ui.MenuBar import MenuBar
from pyjamas.ui.MenuItem import MenuItem
from pyjamas.ui.Widget import Widget
from pyjamas.ui.Hyperlink import Hyperlink
from pyjamas import Window
from pyjamas.Timer import Timer
from pyjamas.JSONService import JSONProxy
from pyjamas import History
from pyjamas import DOM
from prnt import prnt
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP
from util import get_checked_radio, HidingPanel, ValidationErrorRemover, MyAnchor, LoadingButton
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel, Marker

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect


client = JSONProxy('/json/', ['paline_smart_search', 'urldecode', 'paline_percorso_fermate', 'paline_orari'])

class PalinaPanel(HorizontalPanel):
	def __init__(self, owner, p, img='/paline/s/img/palina.png'):
		HorizontalPanel.__init__(self)
		self.addStyleName('palina')
		self.owner = owner
		i = Image(img)
		i.addStyleName('palina-img')
		self.add(i)
		vp = VerticalPanel()
		self.add(vp)
		titolo = HTMLFlowPanel()
		vp.add(titolo)
		if 'nascosta' in p and p['nascosta']:
			self.nascosta = True
			self.setVisible(False)
		else:
			self.nascosta = False
		titolo.addAnchor("%s (%s)" % (p['nome'], p['id_palina']), owner.onPalinaFactory(p['id_palina']))
		titolo.addStyleName('h2')
		if 'distanza_arrotondata' in p and p['distanza_arrotondata'] != '':
			titolo.addHtml("&nbsp;(%s)" % p['distanza_arrotondata'])
		if 'linee_info' in p:
			for l in p['linee_info']:
				linea = HTMLFlowPanel()
				linea.add(Image('/paline/s/img/bus.png'))
				linea.addAnchor(l['id_linea'], owner.onLineaFactory(l['id_linea']))
				linea.addHtml("&nbsp;Direz. %s" % l['direzione'])
				vp.add(linea)
		if 'linee_extra' in p and len(p['linee_extra']) > 0:
			altre = HTMLFlowPanel()
			altre.add(Image('/paline/s/img/bus.png'))
			vp.add(altre)
			altre.addHtml('Altre linee:&nbsp;')
			for l in p['linee_extra']:
				altre.addAnchor(l, owner.onLineaFactory(l))
				altre.addHtml("&nbsp;")
				
	def mostra(self):
		self.setVisible(True)
				
				
class PalinaSmallPanel(HTMLFlowPanel):
	def __init__(self, owner, p, img='/paline/s/img/down_arrow.png'):
		HTMLFlowPanel.__init__(self)
		self.owner = owner
		i = Image(img)
		self.add(i)
		self.addAnchor("%s (%s)" % (p['nome'], p['id_palina']), owner.onPalinaFactory(p['id_palina']))
				
class PercorsoPanel(HTMLFlowPanel):
	def __init__(self, owner, p):
		HTMLFlowPanel.__init__(self)
		self.owner = owner
		self.add(Image('/paline/s/img/bus.png'))
		self.addAnchor('%s %s Direz. %s' % (p['id_linea'], p['carteggio_dec'], p['direzione']), owner.onPercorsoFactory(p['id_percorso']))

class OrarioPanel(VerticalPanel):
	def __init__(self, owner, o, id_percorso):
		HorizontalPanel.__init__(self)
		self.owner = owner
		self.giorno = o['giorno']
		self.orari = None
		self.id_percorso = id_percorso
		a = MyAnchor()
		a.setWidget(HTML(o['nome']))
		a.addClickListener(self.onOrario)
		self.add(a)

	def onOrario(self):
		if self.orari is not None:
			self.remove(self.orari)
			self.orari = None
		else:
			client.paline_orari(self.id_percorso, self.giorno, JsonHandler(self.onOrarioDone))
			
	def onOrarioDone(self, res):
		self.orari = VerticalPanel()
		trovato = False
		for h in res['orari_partenza']:
			m = h['minuti']
			if len(m) > 0:
				self.orari.add(HTML('<b>%s:</b> %s' % (
					h['ora'],
					' '.join(m),
				)))
				trovato = True
		if not trovato:
			if res['no_orari']:
				self.orari.add(HTML('Siamo spiacenti, non sono disponibili gli orari di partenza dal capolinea per il percorso selezionato.'))
			else:
				self.orari.add(HTML('Nella giornata selezionata il percorso non &egrave; attivo.'))
		self.add(self.orari)

class CercaLineaPanel(SimplePanel, KeyboardHandler, FocusHandler):
	def __init__(self, owner):
		SimplePanel.__init__(self)
		KeyboardHandler.__init__(self)
		self.owner = owner
		self.map = None
		self.base = VP(
			self,
			[
				{
					'class': VP,
					'style': 'indicazioni',
					'sub': [
	
						{
							'class': Label,
							'args': ['Fermata, linea o indirizzo'],
							'style': 'indicazioni-h1',
							'height': None,
						},			
						{
							'class': HP,
							'sub': [
								{
									'class': HP,
									'width': '70%',
									'sub': [							
										{
											'class': TextBox,
											'name': 'query',
											'call_addKeyboardListener': ([self], {}),
											'call_addFocusListener': ([self], {}),
										},
										{
											'class': HP,
											'call_setVisible': ([False], {}),
											'name': 'query_list_holder',
											'sub': [
												{
													'class': ListBox,
													'name': 'query_list',
													'width': '100%',
												},
												{
													'class': Button,
													'args': ['X', self.onChiudiQuery],
													'width': '40px',
												}														
											]
										},
									],
								},
								{
									'class': LoadingButton,
									'args': ['Cerca', self.onCerca],
									'width': '30%',
									'name': 'button',
								},									
							]
						},								
		
					]
				},

		
						
				{
					'class': SP,
					'name': 'risultati_holder',
					'sub': [],
				},
			],
			add_to_owner=True,						
		)
		
		self.risultati = None
		self.cl_layer = None
		
	def availableParams(self):
		return [
			'query',
			'id_percorso',			
			'cl',
		]
		
	def setParam(self, param, value):
		if param == 'query':
			self.base.by_name('query').setText(value)	
		if param == 'cl':
			self.onCerca()
		if param == 'id_percorso':
			self.cercaPercorso(value)	
		
	def ripristinaWidgets(self):
		for x, x_list, x_holder in [self.getWidgets()]:
			x.removeStyleName('validation-error')
			if not x.getVisible():
				x.setText(x_list.getSelectedItemText()[0])
				x_holder.setVisible(False)
				x.setVisible(True)
		
	def onChange(self, el):
		el.removeStyleName('validation-error')
		
	def onFocus(self, text):
		text.selectAll()
				
	def setMap(self, map):
		self.map = map
		self.map.addRightClickOption("Fermate vicine", self.onRightClick)
		
	def onRightClick(self, lat, lng):
		query = self.base.by_name('query')
		query.setText('punto:(%s,%s)' % (lat, lng))
		self.owner.setTabCercaLinea()
		self.createClLayer()
		m = Marker(
			self.cl_layer,
			(lng, lat),
			'/paline/s/img/arrivo_percorso.png',
			icon_size=(32, 32),
		)	
		self.onCerca()

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()
			
	def onPercorsoFactory(self, id_percorso):
		def onPercorso(source):
			self.cercaPercorso(id_percorso)
		return onPercorso
	
	def onLineaFactory(self, id_linea):
		def onLinea(source):
			self.cercaLinea(id_linea)
		return onLinea
	
	def onPalinaFactory(self, id_palina):
		def onPalina(source):
			self.palinaSuMappa(id_palina)
		return onPalina
	
	def onMostraTuttePaline(self):
		for p in self.paline_nascoste:
			p.mostra()
		self.mostra_tutto.setVisible(False)
	
	def createClLayer(self):
		self.owner.setTabCercaLinea()
		if self.cl_layer is not None:
			self.cl_layer.destroy()
		self.map.hideAllLayers()
		self.cl_layer = Layer('cp_layer', 'Fermate trovate', self.map)	
		
	def palinaSuMappa(self, id_palina):
		self.map.loadNewLayer(id_palina, 'palina-singola', id_palina)
			
	def cercaLinea(self, query):
		self.base.by_name('button').start()
		client.paline_smart_search(query, JsonHandler(self.onCercaDone))
			
	def onCerca(self):
		self.ripristinaWidgets()
		self.cercaLinea(self.base.by_name('query').getText())
		
	def cercaPercorso(self, id_percorso):
		client.paline_percorso_fermate(id_percorso, JsonHandler(self.onCercaPercorsoDone))
		self.map.loadNewLayer(id_percorso, 'percorso', id_percorso)
		
	def onCercaPercorsoDone(self, res):
		risultati_holder = self.base.by_name('risultati_holder')
		if self.risultati is not None:
			risultati_holder.remove(self.risultati)
		
		self.risultati = DP(
			None,
			[ 
				{
					'class': VP,
					'style': 'indicazioni',
					'name': 'dettaglio',
					'sub': [
						{
							'class': Label,
							'args': ['Partenze da capolinea'],
							'style': 'indicazioni-h1',
							'height': None,
						},
						{
							'class': VP,
							'name': 'orari',
							'sub': [],
						},								
						{
							'class': Label,
							'args': ['Fermate'],
							'style': 'indicazioni-h1',
							'height': None,
						},
						{
							'class': VP,
							'name': 'paline',
							'sub': [],
						},
					]
				}		
			],
			title='Risultati',
			style='indicazioni'
		)
		risultati_holder.add(self.risultati)
		
		orari = self.risultati.by_name('orari')
		for o in res['giorni']:
			orari.add(OrarioPanel(self, o, res['id_percorso']))
		
		paline = self.risultati.by_name('paline')
		n = len(res['paline'])
		i = 0
		
		for p in res['paline']:
			i += 1
			img = '/paline/s/img/%s_arrow.gif' % ('down' if i < n else 'stop') 
			paline.add(PalinaSmallPanel(self, p, img))
		
				
	def onCercaErrore(self, el):
		x, x_list, x_holder = self.getWidgets()
		if el['tipo'] == 'Indirizzo ambiguo':
			x.setVisible(False)
			x_holder.setVisible(True)
			x_list.addStyleName('validation-error')
			x_list.clear()
			for i in el['indirizzi']:
				x_list.addItem(i)
		else:
			x.addStyleName('validation-error')
			
	def getWidgets(self):
		x = self.base.by_name('query')
		x_list = self.base.by_name('query_list')
		x_holder = self.base.by_name('query_list_holder')
		return x, x_list, x_holder			
			
	def onChiudiQuery(self):
		x, x_list, x_holder = self.getWidgets()
		x_holder.setVisible(False)
		x.setVisible(True)			
		
	def onCercaDone(self, res):
		self.base.by_name('button').stop()
		risultati_holder = self.base.by_name('risultati_holder')
		if self.risultati is not None:
			risultati_holder.remove(self.risultati)
			
		if res['errore']:
			self.onCercaErrore(res)
			return
		
		tipo = res['tipo']
		if tipo == 'Palina':
			self.palinaSuMappa(res['id_palina'])
			return
		
		elif tipo == 'Indirizzo ambiguo':
			self.onCercaErrore(res)
		
		self.risultati = DP(
			None,
			[ 
				{
					'class': VP,
					'style': 'indicazioni',
					'name': 'dettaglio',
					'sub': [			
					]
				}		
			],
			title='Risultati',
			style='indicazioni'
		)
		self.map.hideAllLayers()
		self.risultati.setOpen(True)
		dettaglio = self.risultati.by_name('dettaglio')
		risultati_holder.add(self.risultati)
		
		self.paline_nascoste = []
		
		if len(res['paline_extra']) > 0 or len(res['paline_semplice']) > 0:
			h = HTML('Fermate trovate')
			h.addStyleName('indicazioni-h1')
			dettaglio.add(h)

		for p in res['paline_semplice']:
			prnt(p)
			palina = PalinaPanel(self, p)
			dettaglio.add(palina)
			if palina.nascosta:
				self.paline_nascoste.append(palina)

			
		if len(res['paline_extra']) > 0:
			self.createClLayer()
			
		for p in res['paline_extra']:
			palina = PalinaPanel(self, p)
			dettaglio.add(palina)
			if palina.nascosta:
				self.paline_nascoste.append(palina)
			else:
				if 'lng' in p:
					m = Marker(
						self.cl_layer,
						(p['lng'], p['lat']),
						'/paline/s/img/partenza.png',
						icon_size=(16, 16),
						anchor=(8, 8),
						name=('palina', (p['id_palina'], '')),
						label=p['nome'],
						infobox=p['nome'],
					)
			self.cl_layer.centerOnMap()
				
		if len(res['percorsi']) > 0:
			h = HTML('Linee trovate')
			h.addStyleName('indicazioni-h1')
			dettaglio.add(h)				
			
		for p in res['percorsi']:
			percorso = PercorsoPanel(self, p)
			dettaglio.add(percorso)
			
		if len(self.paline_nascoste) > 0:
			self.mostra_tutto = HTMLFlowPanel()
			dettaglio.add(self.mostra_tutto)
			self.mostra_tutto.addHtml("Alcune fermate sono state nascoste perch&eacute; non vi transitano altre linee bus.&nbsp")
			self.mostra_tutto.addAnchor("Mostra tutte le fermate", self.onMostraTuttePaline)
			
		if 'lng' in res:
			m = Marker(
				self.cl_layer,
				(res['lng'], res['lat']),
				'/paline/s/img/partenza_percorso.png',
				icon_size=(32, 32),
				drop_callback=self.onRightClick,
			)
