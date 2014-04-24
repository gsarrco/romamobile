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
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP, DeferrablePanel, ScrollAdaptivePanel, \
	PreferitiImage
from util import get_checked_radio, HidingPanel, ValidationErrorRemover, MyAnchor, LoadingButton
from util import FavSearchBox, wait_start, wait_stop, getdefault, _, get_lang
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel, Marker, get_location
from globals import base_url, make_absolute


from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect


client = JSONProxy(base_url + '/json/', [
	'paline_smart_search',
	'urldecode',
	'paline_percorso_fermate',
	'paline_orari',
	'servizi_autocompleta_indirizzo',
	'paline_previsioni',
	'paline_preferiti',
])

INTERVALLO_TIMER = 30000

class PalinaPanel(HorizontalPanel):
	def __init__(self, owner, p, img='/paline/s/img/palina.png'):
		HorizontalPanel.__init__(self)
		self.addStyleName('palina')
		self.owner = owner
		i = Image(make_absolute(img))
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
				linea.add(Image(make_absolute('/paline/s/img/bus.png')))
				linea.addAnchor(l['id_linea'], owner.onLineaFactory(l['id_linea']))
				linea.addHtml(_("&nbsp;Direz. %s") % l['direzione'])
				vp.add(linea)
		if 'linee_extra' in p and len(p['linee_extra']) > 0:
			altre = HTMLFlowPanel()
			altre.add(Image(make_absolute('/paline/s/img/bus.png')))
			vp.add(altre)
			altre.addHtml(_('Altre linee:&nbsp;'))
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
		self.add(Image(make_absolute('/paline/s/img/bus.png')))
		if 'arrivo' in p:
			p['direzione'] = p['arrivo']
		if p['descrizione'] is not None and p['descrizione'] != '':
			self.addAnchor(p['descrizione'], owner.onPercorsoFactory(p['id_percorso']))
		else:
			self.addAnchor(_('%s %s Direz. %s') % (p['id_linea'], p['carteggio_dec'], p['direzione']), owner.onPercorsoFactory(p['id_percorso']))

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
			client.paline_orari(self.id_percorso, self.giorno, get_lang(), JsonHandler(self.onOrarioDone))
			
	def onOrarioDone(self, res):
		self.orari = VerticalPanel()
		trovato = False
		for h in res['orari_partenza']:
			m = h['minuti']
			if len(m) > 0:
				self.orari.add(HTML(_('<b>%s:</b> %s') % (
					h['ora'],
					' '.join(m),
				)))
				trovato = True
		if not trovato:
			if res['no_orari']:
				self.orari.add(HTML(_('Siamo spiacenti, non sono disponibili gli orari di partenza dal capolinea per il percorso selezionato.')))
			else:
				self.orari.add(HTML(_('Nella giornata selezionata il percorso non &egrave; attivo.')))
		self.add(self.orari)

class CercaLineaPanel(ScrollAdaptivePanel, KeyboardHandler, FocusHandler, DeferrablePanel):
	def __init__(self, owner):
		ScrollAdaptivePanel.__init__(self)
		DeferrablePanel.__init__(self)
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
							'args': [_('Fermata, linea o indirizzo')],
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
												'class': FavSearchBox,
												'name': 'query',
												'call_addKeyboardListener': ([self], {}),
												'args': [client.servizi_autocompleta_indirizzo, None, 0, 100, False],
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
													'style': 'close-button',
												}
											]
										},
									],
								},
								{
									'class': LoadingButton,
									'args': [_('Cerca'), self.onCerca],
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
		self.modo_realtime = None
		self.pannelli_real_time = None
		self.id_veicolo_selezionato = None
		self.id_percorso = None
		self.id_palina = None
		self.timer = Timer(notify=self.onTimer)
		
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
			self.owner.setTabMappaLinea()
			q = self.base.by_name('query').getText()
			if q is not None:
				self.cercaLinea(q, set_tab=True)
		if param == 'id_percorso':
			self.cercaPercorso(value, True)	
		
	def ripristinaWidgets(self):
		for x, x_list, x_holder in [self.getWidgets()]:
			x.removeStyleName('validation-error')
			if not x.getVisible():
				x.setText(x_list.getSelectedItemText()[0])
				x_holder.setVisible(False)
				x.setVisible(True)
		
	def onChange(self, el):
		el.removeStyleName('validation-error')

	def setMap(self, map):
		self.map = map
		self.map.addRightClickOption(_("Fermate vicine"), self.onRightClick)
		
	def onRightClick(self, lat, lng):
		query = self.base.by_name('query')
		query.setText('punto:(%0.4f,%0.4f)' % (lat, lng))
		self.owner.setTabMappaLinea()
		self.createClLayer()
		def add_marker():
			m = Marker(
				self.cl_layer,
				(lng, lat),
				make_absolute('/paline/s/img/arrivo_percorso.png'),
				anchor=(16, 32),
				icon_size=(32, 32),
			)
		self.owner.map_tab.do_or_defer(add_marker)
		self.onCerca()

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()
			
	def onPercorsoFactory(self, id_percorso, id_veicolo=None):
		def onPercorso(source):
			self.id_veicolo_selezionato = id_veicolo
			self.cercaPercorso(id_percorso, reset_palina=False)
		return onPercorso
	
	def onLineaFactory(self, id_linea):
		def onLinea(source):
			self.cercaLinea(id_linea)
		return onLinea
	
	def onPalinaFactory(self, id_palina):
		def onPalina(source):
			self.dettaglioPalina(id_palina)
		return onPalina

	def onMostraTuttePaline(self):
		for p in self.paline_nascoste:
			p.mostra()
		self.mostra_tutto.setVisible(False)
	
	def createClLayer(self):
		# self.owner.setTabMappaLinea()
		if self.cl_layer is not None:
			self.cl_layer.destroy()
		self.map.hideAllLayers()
		self.cl_layer = Layer('cp_layer', _('Fermate trovate'), self.map)
		
	def dettaglioPalina(self, id_palina):
		wait_start()
		self.resetPannelliRealtime()
		self.modo_realtime = 'palina'
		self.id_palina = id_palina
		# self.owner.setTabMappa()
		def load_layer():
			self.map.loadNewLayer(id_palina, 'palina-singola', id_palina)
		self.owner.map_tab.do_or_defer(load_layer)
		client.paline_previsioni(id_palina, get_lang(), JsonHandler(self.onDettaglioPalinaDone))


	def _converti_dotazioni_bordo(self, x, dotaz):
		if x[dotaz]:
			x[dotaz + 'alt'] = dotaz[0].upper()
			x[dotaz] = dotaz
		else:
			x[dotaz + 'alt'] = ' '
			x[dotaz] = 'blank'

	def onDettaglioPalinaDone(self, res):
		self.aggiornaArrivi(res)
		wait_stop()
		self.startTimer()

	def aggiornaArrivi(self, res):
		wait_stop()
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
					'height': None,
					'sub': [
						{
							'class': HP,
							'sub': [
								{
									'class': PreferitiImage,
									'args': ['P', self.id_palina, '%s (%s)' % (res['nome'], self.id_palina), res['esiste_preferito'], client.paline_preferiti],
									'width': '25px',
								},
								{
									'class': Label,
									'args': ['%s (%s)' % (res['nome'], self.id_palina)],
									'style': 'indicazioni-h1',
									'height': None,
								},
								{
									'class': Image,
									'args': ['reload.png'],
									'width': '18px',
									'call_addClickListener': ([self.onReload], {}),
									'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
								},
							]
						},
						{
							'class': HTML,
							'args': [_("Linee della fermata")],
							'style': 'indicazioni-h2',
							'height': None,
						},
						{
							'class': GP,
							'column_count': 2,
							'name': 'linee',
							'sub': [],
						},
						{
							'class': HTML,
							'args': [_("Tutti gli arrivi")],
							'style': 'indicazioni-h2',
							'height': None,
							'name': 'arrivi_label'
						},
						{
							'class': VP,
							'name': 'arrivi',
							'sub': [],
						},
					]
				}
			],
			title=_('Risultati'),
			style='indicazioni'
		)

		risultati_holder.add(self.risultati)
		# Primi arrivi
		gp = self.risultati.by_name('linee')
		primi = res['primi_per_palina'][0]['arrivi']
		for l in primi:
			msg = l['linea']
			carteggi = getdefault(l, 'carteggi', '')
			if carteggi != '':
				msg += " (%s)" % carteggi
			a = MyAnchor()
			h = HTML("<b>" + msg + "</b>")
			a.setWidget(h)
			if 'id_percorso' in l:
				a.addClickListener(self.onPercorsoFactory(l['id_percorso'], l['id_veicolo']))
			else:
				a.addClickListener(self.onLineaFactory(l['linea']))
			gp.add(a, center=HasAlignment.ALIGN_RIGHT)
			if getdefault(l, 'disabilitata', False):
				msg = _("Non disponibile")
			elif getdefault(l, 'non_monitorata', False):
				msg = _("Non monitorata")
			elif getdefault(l, 'nessun_autobus', False):
				msg = _("Nessun autobus")
			else:
				msg = l['annuncio']
				partenza = getdefault(l, 'partenza', '')
				if partenza != '':
					msg += _(" (partenza %s)") % partenza
			gp.add(HTML(": " + msg), center=HasAlignment.ALIGN_LEFT)

		# Tutti gli arrivi
		tutti = res['arrivi']
		self.risultati.by_name('arrivi_label').setVisible(len(tutti) > 0)
		arrivi = self.risultati.by_name('arrivi')
		banda = 0
		for l in tutti:
			vp = VerticalPanel()
			vp.setWidth('100%')
			vp.addStyleName('banda%d' % banda)
			banda = (banda % 2) + 1
			hp1 = HorizontalPanel()
			msg = l['linea']
			carteggi = getdefault(l, 'carteggi', '')
			if carteggi != '':
				msg += " (%s)" % carteggi
			a = MyAnchor()
			h = HTML("<b>" + msg + "</b>")
			a.setWidget(h)
			a.addClickListener(self.onPercorsoFactory(l['id_percorso'], l['id_veicolo']))
			hp1.add(a)
			msg = ': ' + l['annuncio']
			partenza = getdefault(l, 'partenza', '')
			if partenza != '':
				msg += _(" (partenza %s)") % partenza
			hp1.add(HTML(msg))
			vp.add(hp1)
			hp2 = HorizontalPanel()
			vp.add(hp2)
			for dotaz in ['pedana', 'meb', 'aria', 'moby']:
				self._converti_dotazioni_bordo(l, dotaz)
				hp2.add(Image(make_absolute('/paline/s/img/%s.gif' % l[dotaz])))

			arrivi.add(vp)
			arrivi.setCellWidth(vp, '100%')


	def cercaLinea(self, query, set_input=False, set_tab=False, from_map=False):
		self.owner.setDirty()
		if set_tab:
			self.owner.setTabLineaMappa()
		if set_input:
			self.base.by_name('query').setText(query)
		self.base.by_name('button').start()
		wait_start()
		if from_map:
			callback = self.onCercaDoneFromMap
		else:
			callback = self.onCercaDone
		client.paline_smart_search(query, get_lang(), JsonHandler(callback))
			
	def onCerca(self):
		self.ripristinaWidgets()
		self.cercaLinea(self.base.by_name('query').getText())
		
	def cercaPercorso(self, id_percorso, set_tab=False, su_mappa=False, reset_palina=True):
		wait_start()
		if reset_palina:
			self.id_palina = None
			self.id_veicolo_selezionato = None
		if su_mappa:
			self.owner.hide(False)
		else:
			self.owner.setTabLineaMappa()
		client.paline_percorso_fermate(id_percorso, self.id_veicolo_selezionato, get_lang(), JsonHandler(self.onCercaPercorsoDone))
		def load_layer():
			self.map.loadNewLayer(id_percorso, 'percorso', id_percorso)
		self.owner.map_tab.do_or_defer(load_layer)
		
	def onCercaPercorsoDone(self, res):
		wait_stop()
		self.resetPannelliRealtime()
		self.modo_realtime = 'percorso'
		risultati_holder = self.base.by_name('risultati_holder')
		if self.risultati is not None:
			risultati_holder.remove(self.risultati)

		p = res['percorso']
		if p['descrizione'] is not None and p['descrizione'] != '':
			desc = p['descrizione']
		else:
			desc = _('%(id_linea)s %(carteggio_dec)s direz. %(arrivo)s') % p
		
		self.risultati = DP(
			None,
			[ 
				{
					'class': VP,
					'style': 'indicazioni',
					'name': 'dettaglio',
					'sub': [
						{
							'class': HP,
							'sub': [
								{
									'class': Label,
									'args': [desc],
									'style': 'indicazioni-h1',
									'height': None,
								},
								{
									'class': Image,
									'args': ['reload.png'],
									'width': '20px',
									'call_addClickListener': ([self.onReload], {}),
									'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
								},
							]
						},
						{
							'class': Label,
							'args': [_('Partenze da capolinea')],
							'style': 'indicazioni-h2',
							'height': None,
						},
						{
							'class': VP,
							'name': 'orari',
							'sub': [],
						},								
						{
							'class': Label,
							'args': [_('Fermate')],
							'style': 'indicazioni-h2',
							'height': None,
						},
						{
							'class': HTML,
							'args': [_("<b>Veicolo: </b>Seleziona un bus")],
							'style': 'indicazioni',
							'height': None,
							'name': 'veicolo_selezionato',
						},
						{
							'class': GP,
							'column_count': 4,
							# Traffico, Icona Fermata/Bus, Tempo di arrivo, Nome fermata
							'name': 'paline',
							'sub': [],
						},
						{
							'class': Label,
							'name': 'altri_label',
							'args': [_('Altri percorsi della linea')],
							'style': 'indicazioni-h2',
							'height': None,
						},
						{
							'class': VP,
							'args': [],
							'name': 'altri',
							'height': None,
						},
						{
							'class': Label,
							'args': [_('Gestore')],
							'style': 'indicazioni-h2',
							'height': None,
						},
						{
							'class': HTML,
							'name': 'gestore',
							'args': [""],
							'height': None,
						},
					]
				}		
			],
			title=_('Risultati'),
			style='indicazioni'
		)
		risultati_holder.add(self.risultati)

		if self.id_veicolo_selezionato is not None:
			self.selezionaVeicolo(self.id_veicolo_selezionato)

		orari = self.risultati.by_name('orari')
		for o in res['giorni']:
			orari.add(OrarioPanel(self, o, res['id_percorso']))
		
		paline = self.risultati.by_name('paline')
		n = len(res['fermate'])

		self.pannelli_real_time = []
		self.id_percorso = res['id_percorso']

		for p in res['fermate']:
			if not p['soppressa']:
				st = p['stato_traffico']
				stp = SimplePanel()
				stp.setHeight('100%')
				stp.add(HTML('&nbsp;'))
				paline.add(stp)
				imgp = SimplePanel()
				paline.add(imgp)
				tap = SimplePanel()
				paline.add(tap)
				self.pannelli_real_time.append((stp, imgp, tap))
				a = MyAnchor()
				h = HTML(p['nome_ricapitalizzato'])
				if self.id_palina == p['id_palina']:
					a.addStyleName('hl')
				a.setWidget(h)
				a.addClickListener(self.onPalinaFactory(p['id_palina']))
				paline.add(a, center=HasAlignment.ALIGN_LEFT)


		self.risultati.by_name('gestore').setHTML(_('La linea %s &egrave; gestita da %s.') % (
			res['percorso']['id_linea'],
			res['percorso']['gestore'],
		))

		altri = self.risultati.by_name('altri')
		self.risultati.by_name('altri_label').setVisible(len(res['percorsi']) > 1)
		for p in res['percorsi']:
			if p['id_percorso'] != self.id_percorso:
				percorso = PercorsoPanel(self, p)
				altri.add(percorso)

		self.onInfoRealtime(res)
		self.startTimer()

	def selezionaVeicolo(self, id_veicolo):
		self.id_veicolo_selezionato = id_veicolo
		self.risultati.by_name('veicolo_selezionato').setHTML('<b>Veicolo:</b> %s' % id_veicolo)

	def onInfoRealtime(self, res):
		wait_stop()
		i = 0
		n = len(res['fermate'])
		for p in res['fermate']:
			if not p['soppressa']:
				stp, imgp, tap = self.pannelli_real_time[i]
				if i > 0:
					stp.setStyleName('stato%s' % p['stato_traffico'])
				if 'veicolo' in p:
					id_veicolo = p['veicolo']['id_veicolo']
					if id_veicolo == self.id_veicolo_selezionato:
						img = Image(make_absolute('/paline/s/img/bus_hl.png'))
					else:
						img = Image(make_absolute('/paline/s/img/bus.png'))
						img.addStyleName('clickable')
						def onVeicolo(id_veicolo):
							def f():
								self.selezionaVeicolo(id_veicolo)
								client.paline_percorso_fermate(self.id_percorso, id_veicolo, get_lang(), JsonHandler(self.onInfoRealtime))
							return f
						img.addClickListener(onVeicolo(id_veicolo))
				else:
					img = Image(make_absolute('/paline/s/img/%s_arrow.gif' % ('down' if i < n - 1 else 'stop')))
				imgp.setWidget(img)
				ta = ''
				if 'orario_arrivo' in p:
					ta = p['orario_arrivo']
				tap.setWidget(HTML(ta))
				i += 1


				
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

	def resetPannelliRealtime(self):
		self.modo_realtime = None
		self.timer.cancel()

	def onReload(self):
		wait_start()
		self.onTimer()

	def onTimer(self):
		if self.modo_realtime is not None:
			if self.modo_realtime == 'percorso':
				client.paline_percorso_fermate(self.id_percorso, self.id_veicolo_selezionato, get_lang(), JsonHandler(self.onInfoRealtime))
			elif self.modo_realtime == 'palina':
				client.paline_previsioni(self.id_palina, get_lang(), JsonHandler(self.aggiornaArrivi))
			else:
				wait_stop()
			self.timer.schedule(INTERVALLO_TIMER)

	def startTimer(self):
		self.timer.schedule(INTERVALLO_TIMER)

	def onCercaDoneFromMap(self, res):
		self.onCercaDone(res, True)
		
	def onCercaDone(self, res, from_map=False):
		self.resetPannelliRealtime()
		self.base.by_name('button').stop()
		wait_stop()
		risultati_holder = self.base.by_name('risultati_holder')
		if self.risultati is not None:
			risultati_holder.remove(self.risultati)
			
		if res['errore']:
			self.onCercaErrore(res)
			return
		
		tipo = res['tipo']
		if tipo == 'Palina':
			if from_map:
				self.owner.setTabMappaLinea()
			else:
				self.owner.setTabCercaLinea()
			self.dettaglioPalina(res['id_palina'])
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
			title=_('Risultati'),
			style='indicazioni'
		)
		self.map.hideAllLayers()
		self.risultati.setOpen(True)
		dettaglio = self.risultati.by_name('dettaglio')
		risultati_holder.add(self.risultati)
		
		self.paline_nascoste = []

		if len(res['paline_extra']) > 0 or len(res['paline_semplice']) > 0:
			h = HTML(_('Fermate trovate'))
			h.addStyleName('indicazioni-h1')
			dettaglio.add(h)

		for p in res['paline_semplice']:
			palina = PalinaPanel(self, p)
			dettaglio.add(palina)
			if palina.nascosta:
				self.paline_nascoste.append(palina)

			
		if len(res['paline_extra']) > 0 or 'lng' in res:
			self.createClLayer()
			
		for p in res['paline_extra']:
			palina = PalinaPanel(self, p)
			dettaglio.add(palina)
			if palina.nascosta:
				self.paline_nascoste.append(palina)
			else:
				if 'lng' in p:
					def add_marker():
						m = Marker(
							self.cl_layer,
							(p['lng'], p['lat']),
							make_absolute('/paline/s/img/partenza.png'),
							icon_size=(16, 16),
							anchor=(8, 8),
							name=('palina', (p['id_palina'], '')),
							label=p['nome'],
							infobox=p['nome'],
						)
					self.owner.map_tab.do_or_defer(add_marker)

		if len(res['percorsi']) > 0:
			if from_map:
				self.owner.setTabCercaLinea()
			h = HTML(_('Linee trovate'))
			h.addStyleName('indicazioni-h1')
			dettaglio.add(h)
		elif len(res['paline_semplice']) > 0 and from_map:
			self.owner.setTabCercaLinea()
			
		for p in res['percorsi']:
			percorso = PercorsoPanel(self, p)
			dettaglio.add(percorso)
			
		if len(self.paline_nascoste) > 0:
			self.mostra_tutto = HTMLFlowPanel()
			dettaglio.add(self.mostra_tutto)
			self.mostra_tutto.addHtml(_("Alcune fermate sono state nascoste perch&eacute; non vi transitano altre linee bus.&nbsp"))
			self.mostra_tutto.addAnchor(_("Mostra tutte le fermate"), self.onMostraTuttePaline)

		if 'lng' in res:
			def on_cpda():
				self.owner.cercaPercorsoDa(res['ricerca'])

			def on_cpa():
				self.owner.cercaPercorsoA(res['ricerca'])

			def on_cl():
				self.owner.setTabCercaLinea()

			def on_cr():
				self.owner.cercaLuogo(res['ricerca'])

			infobox=_("""
				<b>%(ricerca)s</b><br /><br />
				<a id="link-cpa" href="#">Cerca percorso fino a qui</a>
				<a id="link-cpda" href="#">Cerca percorso da qui</a>
				<a id="link-cl" href="#">Cerca fermate vicine</a>
				<a id="link-cr" href="#">Cerca luoghi vicini</a>
			""") % {'ricerca': res['ricerca']}

			def on_infobox(marker):
				marker.openBubble(infobox)
				DOM.getElementById('link-cpda').onclick = on_cpda
				DOM.getElementById('link-cpa').onclick = on_cpa
				DOM.getElementById('link-cl').onclick = on_cl
				DOM.getElementById('link-cr').onclick = on_cr

			def add_marker():
				m = Marker(
					self.cl_layer,
					(res['lng'], res['lat']),
					make_absolute('/paline/s/img/partenza_percorso.png'),
					icon_size=(32, 32),
					anchor=(16, 32),
					drop_callback=self.onRightClick,
					infobox=infobox,
					infobox_listener=on_infobox
				)
				if from_map:
					on_infobox(m)

			self.owner.map_tab.do_or_defer(add_marker)


		if len(res['paline_extra']) > 0 or 'lng' in res:
			self.owner.center_and_zoom(self.cl_layer)


