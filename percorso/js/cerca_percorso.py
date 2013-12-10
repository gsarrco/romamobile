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
from pyjamas.ui.Tooltip import TooltipListener
from pyjamas.JSONService import JSONProxy
from pyjamas import History
from pyjamas import DOM
from prnt import prnt
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP
from util import get_checked_radio, HidingPanel, ValidationErrorRemover, MyAnchor
from util import ToggleImage
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel, Marker

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect


client = JSONProxy('/json/', ['percorso_cerca', 'urldecode', 'risorse_lista_tipi'])

class LineaLabel(HorizontalPanel):
	def __init__(self, id_linea):
		HorizontalPanel.__init__(self)
		self.id_linea = id_linea
		self.addStyleName('inl')
		self.addStyleName('linea-label')
		self.linea = MyAnchor()
		self.linea.setWidget(HTML(id_linea))
		self.linea.addStyleName('linea-label-sx')
		self.add(self.linea)
		self.x = MyAnchor()
		self.x.setWidget(Image('x.png'))
		self.x.addStyleName('linea-label-dx')
		self.add(self.x)
		self.setCellHorizontalAlignment(self.x, HasAlignment.ALIGN_CENTER)
		self.setCellVerticalAlignment(self.x, HasAlignment.ALIGN_MIDDLE)
		self.chiudi_listener = None
		self.x.addClickListener(self.onClose)
		
	def addCloseListener(self, l):
		self.chiudi_listener = l
		
	def addLineaListener(self, l):	
		self.linea.addClickListener(l)
		
	def onClose(self):
		if self.chiudi_listener is not None:
			self.x.setVisible(False)
			self.linea.addStyleName('linea-chiusa')
			chiudi = self.chiudi_listener
			self.chiudi_listener = None
			chiudi()

class CercaPercorsoPanel(SimplePanel, KeyboardHandler, FocusHandler):
	def __init__(self, owner):
		SimplePanel.__init__(self)
		KeyboardHandler.__init__(self)
		self.owner = owner
		self.map = None
		self.carpooling = 0
		self.tipi_risorse_init = None
		self.base = VP(
			self,
			[	
				{
					'class': VP,
					'style': 'indicazioni',
					'sub': [
						{
							'class': Label,
							'args': ['Dove'],
							'style': 'indicazioni-h1',
							'height': None,
						},
						{
							'class': GP,
							'column_count': 2,
							#'style': 'indicazioni',
							'sub': [
								{
									'class': Label,
									'args': ["Da: "],
									'expand': False,
								},
								{
									'class': HP,
									'sub': [
											{
												'class': TextBox,
												'name': 'da',
												'call_addKeyboardListener': ([self], {}),
												'call_addFocusListener': ([self], {}),
											},
											{
												'class': HP,
												'call_setVisible': ([False], {}),
												'name': 'da_list_holder',
												'sub': [
													{
														'class': ListBox,
														'name': 'da_list',
														'width': '100%',
													},
													{
														'class': Button,
														'args': ['X', self.onChiudiDa],
														'width': '40px',
													}														
												]
										},
									]
								},
								{
									'class': Label,
									'args': ["A: "],
									'expand': False,
								}, 
								{
									'class': HP,
									'sub': [
											{
												'class': TextBox,
												'name': 'a',
												'call_addKeyboardListener': ([self], {}),
												'call_addFocusListener': ([self], {}),
											},
											{
												'class': HP,
												'call_setVisible': ([False], {}),
												'name': 'a_list_holder',
												'sub': [
													{
														'class': ListBox,
														'name': 'a_list',
														'width': '100%',
													},
													{
														'class': Button,
														'args': ['X', self.onChiudiA],
														'width': '40px',
													}														
												]
										},
									]
								},
							]
						},
						{
							'class': HP,
							'sub': [
								{
									'class': Button,
									'args': ["Cerca", self.onCerca],
									'name': 'cerca',
									'width': '50%',
								}, {
									'class': Button,
									'args': ["Ritorno", self.onScambia],
									'name': 'scambia',
									'width': '50%',
								}
							]
						},
						{
							'class': Label,
							'args': ['Come: Trasporto pubblico'],
							'style': 'indicazioni-h1',
							'name': 'come_header',
							'height': None,
						},
						{
							'class': GP,
							'column_count': 3,
							'sub': [
								{
									'class': ToggleImage,
									'args': ['modo_tpl.png', 'modo-inactive', 'modo-active', self.onModo, 1, False],
									'name': 'modo_tpl',
									'expand': False,
									'call_addMouseListener': ([TooltipListener("Trasporto pubblico", 350)], {}),
								},
								{
									'class': ToggleImage,
									'args': ['modo_bnr.png', 'modo-inactive', 'modo-active', self.onModo, 3, False],
									'name': 'modo_bnr',
									'expand': False,
									'call_addMouseListener': ([TooltipListener("Bike and ride", 350)], {}),
								},
								{
									'class': ToggleImage,
									'args': ['modo_carsharing.png', 'modo-inactive', 'modo-active', self.onModo, 4, False],
									'name': 'modo_carsharing',
									'expand': False,
									'call_addMouseListener': ([TooltipListener("Car sharing", 350)], {}),
								},
								{
									'class': ToggleImage,
									'args': ['modo_auto.png', 'modo-inactive', 'modo-active', self.onModo, 0, False],
									'name': 'modo_auto',
									'expand': False,
									'call_addMouseListener': ([TooltipListener("Trasporto privato", 350)], {}),
								},
								{
									'class': ToggleImage,
									'args': ['modo_pnr.png', 'modo-inactive', 'modo-active', self.onModo, 2, False],
									'name': 'modo_pnr',
									'expand': False,
									'call_addMouseListener': ([TooltipListener("Park and ride", 350)], {}),
								},							
							],
						},								
					],
				},
				{
					'class': DP,
					'name': 'opzioni_avanzate',
					'title': 'Opzioni avanzate',
					'sub': [{
						'class': VP,
						'style': 'indicazioni',
						'sub': [
							{
								'class': Label,
								'args': ['Opzioni'],
								'style': 'indicazioni-h1',
								'height': None,
							},
							{
								'class': CheckBox,
								'args': ['Cerca un luogo lungo il percorso', True],
								'name': 'luogo',
								'click_listener': self.onCercaLuogo,
							},
							{
								'class': ListBox,
								'name': 'risorse',
								'call_setVisibleItemCount': ([6], {}),
								'call_setMultipleSelect': ([True], {}),
								'call_setVisible': ([False], {}),
							},
							{
								'class': VP,
								'name': 'opzioni_tpl',
								'sub': [
									{
										'class': Label,
										'args': ['Propensione spostamenti a piedi'],
										'style': 'indicazioni-h2',
									},									
									{
										'class': RadioButton,
										'args': ['piedi', 'Bassa (camminatore lento)'],
										'name': 'piedi_0',	
									},
									{
										'class': RadioButton,
										'args': ['piedi', 'Media'],
										'name': 'piedi_1',
										'checked': True,
									},
									{
										'class': RadioButton,
										'args': ['piedi', 'Alta (camminatore veloce)'],
										'name': 'piedi_2',
									},
									{
										'class': Label,
										'args': ['Mezzi pubblici da utilizzare'],
										'style': 'indicazioni-h2',
									},									
									{
										'class': CheckBox,
										'args': ['Autobus e tram', True],
										'name': 'bus',
										'checked': True,						
									},
									{
										'class': CheckBox,
										'args': ['Metropolitana', True],
										'name': 'metro',
										'checked': True,						
									},
									{
										'class': CheckBox,
										'args': ['Ferrovie urbane', True],
										'name': 'ferro',
										'checked': True,						
									},
									{
										'class': CheckBox,
										'args': ['Teletrasporto', True],
										'name': 'teletrasporto',
										'checked': False,
										'call_setVisible': ([False], {}),	
									},
								],
							},
									
							{
								'class': HP,
								'name': 'opzioni_bnr',
								'call_setVisible': ([False], {}),
								'sub': [
									{
										'class': HTML,
										'args': ['Max distanza in bici:&nbsp;'],
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},
									{
										'class': TextBox,
										'name': 'max_distanza_bici',
										'call_setVisibleLength': ([3], {}),
										'call_setText': (['5'], {}),
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},
									{
										'class': HTML,
										'args': ['&nbsp;km'],
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},		
								],
							},
							{
								'class': VP,
								'name': 'opzioni_pnr',
								'call_setVisible': ([False], {}),
								'sub': [
									{
										'class': Label,
										'args': ['Parcheggi Park and Ride'],
										'style': 'indicazioni-h2',
									},									
									{
										'class': CheckBox,
										'args': ['Parcheggi di scambio', True],
										'name': 'parcheggi_scambio',
										'checked': True,					
									},
									{
										'class': CheckBox,
										'args': ['Autorimesse private', True],
										'name': 'parcheggi_autorimesse',
										'checked': False,	
									},
								],
							},
							{
								'class': Label,
								'args': ['Quando'],
								'style': 'indicazioni-h1',
								'height': None,
							},
							{
								'class': RadioButton,
								'args': ['quando', 'Adesso'],
								'name': 'quando_0',
								'checked': True,
								'click_listener': self.onQuando01,					
							},
							{
								'class': RadioButton,
								'args': ['quando', 'Fra 5 minuti'],
								'name': 'quando_1',
								'click_listener': self.onQuando01,						
							},
							{
								'class': HP,
								'width': None,
								'sub': [
									{
										'class': RadioButton,
										'args': ['quando', 'Parti alle:&nbsp;', True],
										'name': 'quando_2',
										'click_listener': self.onQuando23,
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,					
									},											
									{
										'class': RadioButton,
										'args': ['quando', 'Arriva alle:&nbsp;', True],
										'name': 'quando_3',
										'click_listener': self.onQuando23,
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,					
									},											
								]
							},
							{
								'class': HP,
								'width': None,
								'sub': [										
									{
										'class': DateField,
										'args': ['%d/%m/%Y'],
										'name': 'data',
										'enabled': False,
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},
									{
										'class': HTML,
										'args': ['&nbsp;&nbsp;Ore:&nbsp;'],
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},											
									{
										'class': TextBox,
										'name': 'ora',
										'enabled': False,
										'call_setVisibleLength': ([5], {}),
										'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
									},											
								]
							},												

						]
					}],
				},
				{
					'class': SP,
					'name': 'risultati_holder',
					'sub': [],
				},
			],
			add_to_owner=True,				
		)
		
		self.base.by_name('modo_tpl').setActive(True)
		self.modo = 1
		
		self.risultati = None
		n = datetime.now()
		
		if n.day == 1 and n.month == 4:
			self.base.by_name('teletrasporto').setVisible(True)
		
		self.base.by_name('data').getTextBox().setText(n.strftime('%d/%m/%Y'))
		self.base.by_name('ora').setText(n.strftime('%H:%M'))
		self.cp_layer = None
		self.linee_escluse = None
		self.percorsi_realtime = []
		
		self.realtime = Button("Tempo reale off", self.onRealtime)
		self.realtime.addStyleName('realtime')
		self.realtime.setVisible(False)
		self.realtime_status = False
		self.owner.owner.add(self.realtime)
		self.cercaLuogoInit = False
		
	def cambiaModo(self, modo):
		modi = ['modo_auto', 'modo_tpl', 'modo_pnr', 'modo_bnr', 'modo_carsharing']
		come = ['Trasporto privato', 'Trasporto pubblico', 'Park and Ride', 'Bike and Ride', 'Car Sharing']
		self.base.by_name(modi[self.modo]).setActive(False)
		self.modo = modo
		self.base.by_name(modi[self.modo]).setActive(True)
		tpl = False
		pnr = False
		bnr = False
		luoghi = True
		if self.modo == 1:
			tpl = True
		elif self.modo == 2:
			tpl = True
			pnr = True
			luoghi = False
		elif self.modo == 3:
			tpl = True
			bnr = True
		elif self.modo == 4:
			tpl = True
			luoghi = False			
		self.base.by_name('opzioni_tpl').setVisible(tpl)
		self.base.by_name('opzioni_bnr').setVisible(bnr)
		self.base.by_name('opzioni_pnr').setVisible(pnr)
		if not luoghi:
			self.base.by_name('luogo').setChecked(False)
			self.base.by_name('risorse').setVisible(False)
		self.base.by_name('luogo').setVisible(luoghi)
		self.base.by_name('come_header').setText("Come: %s" % come[self.modo])

	
	def onModo(self, sender):
		self.cambiaModo(sender.data)
		if self.base.by_name('da') != "" and self.base.by_name('a') != "":
			self.cercaPercorso()
			
	def onRisorsaListaTipiDone(self, res):
		risorse = self.base.by_name('risorse')
		if self.tipi_risorse_init is not None:
			trs = set(self.tipi_risorse_init)
		else:
			trs = set()
		i = 0
		for r in res:
			risorse.addItem(r['nome'], r['id'])		
			risorse.setItemSelected(i, r['id'] in trs)
			i += 1
			
	def selectRisorse(self, tipi):
		trs = set(tipi)
		risorse = self.base.by_name('risorse')
		n = risorse.getItemCount()
		for i in range(n):
			risorse.setItemSelected(i, risorse.getItemText(i) in trs)

		
	def onCercaLuogo(self):
		v = self.base.by_name('luogo').isChecked()
		self.base.by_name('opzioni_avanzate').setOpen(True)
		self.base.by_name('risorse').setVisible(v)
		q3 = self.base.by_name('quando_3')
		q3.setEnabled(not v)
		if v and q3.isChecked():
			self.base.by_name('quando_0').setChecked(True)
		if not self.cercaLuogoInit:
			self.cercaLuogoInit = True
			if self.tipi_risorse_init is None:
				self.tipi_risorse_init = []
			client.risorse_lista_tipi(self.tipi_risorse_init, JsonHandler(self.onRisorsaListaTipiDone))
		

	def availableParams(self):
		return [
			'da',
			'a',
			'bus',
			'metro',
			'ferro',
			'mezzo',
			'piedi',
			'quando',
			'max_distanza_bici',
			'dt',
			'linee_escluse',
			'carpooling',
			'tipi_ris',
			'cp', # cp deve essere l'ultimo parametro
		]
		
	def setParam(self, param, value):
		if param == 'carpooling':
			self.carpooling = carpooling
		if param == 'da':
			self.base.by_name('da').setText(value)	
		if param == 'a':
			self.base.by_name('a').setText(value)						
		if param == 'bus':
			self.base.by_name('bus').setChecked(value==1)
		if param == 'metro':
			self.base.by_name('metro').setChecked(value==1)
		if param == 'ferro':
			self.base.by_name('ferro').setChecked(value==1)
		if param == 'quando':
			self.base.by_name('quando_%d' % value).setChecked(True)
			if int(value) == 2 or int(value) == 3:
				self.base.by_name('data').setEnabled(True)
				self.base.by_name('ora').setEnabled(True)			
		if param == 'mezzo':
			self.cambiaModo(int(value))
		if param == 'piedi':
			self.base.by_name('piedi_%d' % value).setChecked(True)			
		if param == 'max_distanza_bici':
			self.base.by_name('max_distanza_bici').setText(value)			
		if param == 'dt':
			self.base.by_name('data').getTextBox().setText('%s/%s/%s' % (value[8:10], value[5:7], value[:4]))
			self.base.by_name('ora').setText('%s:%s' % (value[11:13], value[14:16]))
		if param == 'linee_escluse':
			self.linee_escluse = {}
			if value != '-':
				le = value.split(',')
				for l in le:
					i = l.find(':')
					self.linee_escluse[l[:i]] = l[i + 1:]
		if param == 'tipi_ris' and self.modo == 2:
			tipi_ris = value.split(",")
			self.base.by_name('parcheggi_scambio').setChecked('Parcheggi di scambio' in tipi_ris)
			self.base.by_name('parcheggi_autorimesse').setChecked('Autorimesse' in tipi_ris)
		if param == 'cp':
			self.cercaPercorso()
	
		
	def onChange(self, el):
		el.removeStyleName('validation-error')
		
	def onFocus(self, text):
		text.selectAll()
				
	def setMap(self, map):
		self.map = map
		self.map.addRightClickOption("Cerca percorso da qui", self.onRightClickDa)
		self.map.addRightClickOption("Cerca percorso fino a qui", self.onRightClickA)
		
	def onRealtime(self):
		self.realtime_status = not self.realtime_status
		self.realtime.setText("Tempo reale %s" % ("on" if self.realtime_status else "off"))
		for id_percorso in self.percorsi_realtime:
			self.map.loadNewLayer("%s*" % id_percorso, 'percorso_tiny', id_percorso, toggle=self.realtime_status)

		
	def onRightClickDa(self, lat, lng):
		da = self.base.by_name('da')
		da.setText('punto:(%s,%s)' % (lat, lng))
		a = self.base.by_name('a')
		if a.getText() != '':
			self.onCerca()
		else:
			self.createCpLayer()
		if self.cp_layer is not None:
			m = Marker(
				self.cp_layer,
				(lng, lat),
				'/paline/s/img/partenza_percorso.png',
				icon_size=(32, 32),
			)
			
			
	def onRightClickA(self, lat, lng):
		a = self.base.by_name('a')
		a.setText('punto:(%s,%s)' % (lat, lng))
		da = self.base.by_name('da')
		if da.getText() != '':
			self.onCerca()				
		else:
			self.createCpLayer()
		if self.cp_layer is not None:
			m = Marker(
				self.cp_layer,
				(lng, lat),
				'/paline/s/img/arrivo_percorso.png',
				icon_size=(32, 32),
			)			
		

	def onQuando01(self):
		self.base.by_name('data').setEnabled(False)
		self.base.by_name('ora').setEnabled(False)
		
	def onQuando23(self):
		self.base.by_name('data').setEnabled(True)
		self.base.by_name('ora').setEnabled(True)
		
	def ripristinaWidgets(self):
		for x, x_list, x_holder in [self.getWidgets(t) for t in (False, True)]:
			x.removeStyleName('validation-error')
			if not x.getVisible():
				x.setText(x_list.getSelectedItemText()[0])
				x_holder.setVisible(False)
				x.setVisible(True)


	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()
			
	def onCerca(self):
		self.linee_escluse = None
		self.cercaPercorso()
		
	def createCpLayer(self):
		self.owner.setTabMappaPercorso()
		if self.cp_layer is not None:
			self.cp_layer.destroy()
		self.map.hideAllLayers()
		self.cp_layer = Layer('cp_layer', 'Percorso trovato', self.map)

		
	def cercaPercorso(self, tipi_risorse=None):
		cerca = self.base.by_name('cerca')
		n = datetime.now().strftime('%d/%m/%Y %H:%M')
		quando = get_checked_radio(self.base, 'quando', range(4))
		offset = 0
		if quando == 1:
			offset = 5 * 60
		elif quando == 2 or quando == 3:
			data = self.base.by_name('data').getTextBox()
			ora = self.base.by_name('ora')
			data.removeStyleName('validation-error')
			ora.removeStyleName('validation-error')
			n = '%s %s' % (data.getText(), ora.getText())
		try:
			mdb = self.base.by_name('max_distanza_bici')
			max_distanza_bici = float(mdb.getText()) * 1000
			mdb.removeStyleName('validation-error')
		except Exception:
			mdb.addStyleName('validation-error')
			return
		tipi_ris = []
		if self.base.by_name('luogo').isChecked():
			if tipi_risorse is not None:
				tipi_ris = tipi_risorse
			else:
				tipi_ris = self.base.by_name('risorse').getSelectedValues()
		da_in = self.getIndirizzo(False)
		a_in = self.getIndirizzo(True)
		
		if da_in != '' and a_in != '' and cerca.isEnabled():
			cerca.setEnabled(False)
			cerca.setHTML('<img width="16" height="16" src="loading.gif" />')
			self.ripristinaWidgets()
			opzioni = {
				'mezzo': 1 if self.modo == 3 else self.modo,
				'piedi': get_checked_radio(self.base, 'piedi', range(3)),
				'bus': self.base.by_name('bus').isChecked(),
				'metro': self.base.by_name('metro').isChecked(),
				'fc': self.base.by_name('ferro').isChecked(),
				'fr': self.base.by_name('ferro').isChecked(),
				'bici': self.modo == 3,
				'max_distanza_bici': max_distanza_bici,
				'teletrasporto': self.base.by_name('teletrasporto').isChecked(),
				'carpooling': self.carpooling,
				'rev': quando == 3,
				'tipi_ris': tipi_ris,
				'parcheggi_scambio': self.base.by_name('parcheggi_scambio').isChecked(),
				'parcheggi_autorimesse': self.base.by_name('parcheggi_autorimesse').isChecked(),
			}
			if self.linee_escluse is not None:
				opzioni['linee_escluse'] = self.linee_escluse
			client.percorso_cerca(
				da_in,
				a_in,
				opzioni,				
				n,
				'it',
				offset,
				JsonHandler(self.onCercaDone, self.onCercaErroreRemoto)
			)
			
		
	def onEscludiFactory(self, id_linea, linea):
		def onEscludi():
			if self.linee_escluse is None:
				self.linee_escluse = {}
			self.linee_escluse[id_linea] = linea
			self.cercaPercorso()
		return onEscludi
	
	def onIncludiFactory(self, id_linea):
		def onIncludi():
			if id_linea in self.linee_escluse:
				del self.linee_escluse[id_linea]
			self.cercaPercorso()
		return onIncludi
	
	def onLineaFactory(self, id_percorso):
		def onLinea(source):
			self.map.loadNewLayer(id_percorso, 'percorso', id_percorso)
		return onLinea
	
	def onPalinaFactory(self, id_palina):
		def onPalina(source):
			self.map.loadNewLayer(id_palina, 'palina-singola', id_palina)
		return onPalina	
	
	def onInfoEsteseFactory(self, panel, info_ext):
		panel.w = None
		def onInfoEstese(self):
			if panel.w is not None:
				panel.remove(panel.w)
				panel.w = None
			else:
				h = HTML(info_ext)
				panel.add(h)
				panel.w = h
		return onInfoEstese
	
	def cercaPercorsoRisorse(self, da, tipi, a=None):
		self.base.by_name('da').setText(da)
		if self.cercaLuogoInit:
			self.selectRisorse(tipi)
		else:
			self.tipi_risorse_init = tipi
		self.base.by_name('luogo').setChecked(True)
		self.onCercaLuogo()
		if a is not None:
			self.base.by_name('a').setText(a)
			self.cercaPercorso(self.tipi_risorse_init)
	
	def getWidgets(self, arrivo):
		if arrivo:
			x = self.base.by_name('a')
			x_list = self.base.by_name('a_list')
			x_holder = self.base.by_name('a_list_holder')
		else:
			x = self.base.by_name('da')
			x_list = self.base.by_name('da_list')
			x_holder = self.base.by_name('da_list_holder')
		return x, x_list, x_holder
	
	def onChiudiDa(self):
		x, x_list, x_holder = self.getWidgets(False)
		x_holder.setVisible(False)
		x.setVisible(True)
		
	def onChiudiA(self):
		x, x_list, x_holder = self.getWidgets(True)
		x_holder.setVisible(False)
		x.setVisible(True)		

	def getIndirizzo(self, arrivo):
		x, x_list, x_holder = self.getWidgets(arrivo)
		if x.getVisible():
			return x.getText()
		return x_list.getSelectedItemText()[0]
	
	def abilitaCerca(self):
		cerca = self.base.by_name('cerca')
		cerca.setEnabled(True)
		cerca.setText('Cerca') 
	
	def onCercaErroreRemoto(self, text, code):
		self.abilitaCerca()
		prnt(code)
		prnt(text)
				
	def onCercaErrore(self, el, arrivo):
		x, x_list, x_holder = self.getWidgets(arrivo)
		if el['stato'] == 'Ambiguous':
			x.setVisible(False)
			x_holder.setVisible(True)
			x_list.addStyleName('validation-error')
			x_list.clear()
			for i in el['indirizzi']:
				x_list.addItem(i)
		else:
			x.addStyleName('validation-error')
		
		
	def onCercaDone(self, res):
		self.abilitaCerca()
		
		# Errori
		if 'errore-partenza' in res or 'errore-arrivo' in res:
			if 'errore-partenza' in res:
				self.onCercaErrore(res['errore-partenza'], False)
			if 'errore-arrivo' in res:
				self.onCercaErrore(res['errore-arrivo'], True)
			return
		
		if 'errore-data' in res:
			self.base.by_name('data').getTextBox().addStyleName('validation-error')
			self.base.by_name('ora').addStyleName('validation-error')
			return
		
		# OK
		self.createCpLayer()
		self.percorsi_realtime = []
		self.base.by_name('opzioni_avanzate').setOpen(False)
		risultati_holder = self.base.by_name('risultati_holder')
		if self.risultati is not None:
			risultati_holder.remove(self.risultati)
		
		self.risultati = DP(
			None,
			[ 
				{
					'class': VP,
					'style': 'indicazioni',
					'sub': [
						{
							'class': Label,
							'args': ['Riepilogo'],
							'style': 'indicazioni-h1',
							'height': None,
						},									
						{
							'class': FlowPanel,
							'name': 'riepilogo',
							'args': [],
							'style': 'riepilogo',
						},
						{
							'class': Label,
							'args': ['Esclusioni'],
							'style': 'indicazioni-h1',
							'height': None,
							'name': 'esclusioni-header'
						},											
						{
							'class': HTMLFlowPanel,
							'name': 'esclusioni',
							'args': [],
						},
						{
							'class': Label,
							'args': ['Indicazioni'],
							'style': 'indicazioni-h1',
							'height': None,
						},									
						{
							'class': GP,
							'column_count': 2,
							'name': 'indicazioni',
							'sub': [],
						},									
						{
							'class': HTML,
							'args': ["""&copy; %d
								<a class="inl" href="http://www.agenziamobilita.roma.it">Roma servizi per la mobilit&agrave; s.r.l.</a>""" % datetime.now().year
							],
						},									
					]
				}		
			],
			title='Percorso trovato',
		)
		self.risultati.setOpen(True)
		indicazioni = self.risultati.by_name('indicazioni')
		count = 0
		numero_indicazioni = len(res['indicazioni'])
		
		# Riepilogo
		stat = res['stat']
		riepilogo = self.risultati.by_name('riepilogo')
		riepilogo.add(HTML("<b>Durata spostamento:</b> %s" % stat['tempo_totale_format']))
		riepilogo.add(HTML("<b>Distanza percorsa:</b> %s<br />" % stat['distanza_totale_format']))
		riepilogo.add(HTML("<b>Di cui a piedi:</b> %s" % stat['distanza_piedi_format']))
		
		# Esclusioni
		if len(res['linee_escluse']) > 0:
			self.linee_escluse = {}
			esclusioni = self.risultati.by_name('esclusioni')
			for el in res['linee_escluse']:
				id_linea, nome_linea = el['id_linea'], el['nome']
				ll = LineaLabel(nome_linea)
				ll.addCloseListener(self.onIncludiFactory(id_linea))
				esclusioni.add(ll)
				esclusioni.addHtml('&nbsp;')
				self.linee_escluse[id_linea] = nome_linea
		else:
			self.risultati.by_name('esclusioni-header').setVisible(False)
		# Indicazioni
		for i in res['indicazioni']:
			count += 1
			
			# Tratto
			if 'tratto' in i:
				out = HTMLFlowPanel()
				t = i['tratto']
				indicazioni.addStyledWidget(Image("/percorso/s/img/%s" % t['icona']), expand=False, center=True, style="tratto")
				mezzo = t['mezzo']
				if mezzo == 'Z':
					out.addHtml('Teletrasporto')
				else:
					if mezzo in ['P', 'C', 'CP', 'A', 'CS']:
						if mezzo =='P':
							out.addHtml('A piedi')
						elif mezzo == 'C':
							out.addHtml('In bici')
						elif mezzo == 'CP':
							out.addHtml('Car pooling')
						elif mezzo == 'A':
							out.addHtml('In automobile')
						elif mezzo == 'CS':
							out.addHtml('Car sharing')
					else:
						if mezzo == 'B':
							out.addHtml('Linea&nbsp;')
						linea = t['linea']
						id_linea = t['id_linea']
						ll = LineaLabel(linea)
						out.add(ll)
						out.addHtml("&nbsp;direz. " + t['dest'])
						out.addBr()
						ll.addCloseListener(self.onEscludiFactory(id_linea, linea))
						id_percorso = t['id'].split('-')[-1]
						ll.addLineaListener(self.onLineaFactory(id_percorso))
						if mezzo == 'B':
							self.percorsi_realtime.append(id_percorso)
						tipo_attesa = t['tipo_attesa']
						if tipo_attesa == 'O':
							out.addHtml('Partenza ore&nbsp;')
						elif tipo_attesa == 'S':
							out.addHtml('Attesa circa&nbsp;')
						elif tipo_attesa == 'P' and t['numero'] == 0:
							out.addHtml('In arrivo fra&nbsp;')
						elif tipo_attesa == 'P' and t['numero'] > 0:
							out.addHtml('In arrivo dopo&nbsp;')
						out.addHtml(" %s" % t['tempo_attesa'])
					out.addBr()
					sp = SimplePanel()
					out.addAnchor(t['info_tratto'], self.onInfoEsteseFactory(sp, t['info_tratto_exp']))
					out.addBr()
					out.add(sp)
				indicazioni.addStyledWidget(out)
				
			# Nodo
			else:
				out = HTMLFlowPanel()
				
				n = i['nodo']
				partenza = False
				arrivo = False
				if count == 1:
					icona = 'partenza.png'
					partenza = True
				elif count == numero_indicazioni:
					icona = 'arrivo.png'
					arrivo = True
				else:
					icona = 'icon.png'				
				vp = VP(
					indicazioni,
					[
						{
							'class': Image,
							'args': ["/percorso/s/img/%s" % icona],
							'width': '24px',
							'height': '24px',
							'horizontal_alignment': HasAlignment.ALIGN_CENTER,
						},
						{
							'class': HTML,
							'args': [n['t']],
							'horizontal_alignment': HasAlignment.ALIGN_CENTER,
							'style': 'indicazioni-orario',
						}
					],
					add_to_owner=False,
					expand=False,
					center=True
				)
				indicazioni.addStyledWidget(vp, expand=False, center=True, style="nodo")
				tipo = n['tipo']
				if tipo == 'F':
					out.addHtml("Fermata&nbsp;")
				if tipo == 'L':
					ll = LineaLabel(n['nome'])
					out.add(ll)
					ll.addCloseListener(self.onEscludiFactory(n['id'], n['nome']))
					out.addHtml(n['info_exp'])
				elif n['url'] != '':
					out.addAnchor(n['nome'], self.onPalinaFactory(n['id']))
				else:
					out.addHtml(n['nome'])
				# todo: parti in bici/a piedi	
				
				indicazioni.addStyledWidget(out)
				
		risultati_holder.add(self.risultati)
		
		self.cp_layer.deserialize(res['mappa'], callbacks={
			'drop_start': self.onRightClickDa,
			'drop_stop': self.onRightClickA,
		})
		self.cp_layer.centerOnMap()
		
		if len(self.percorsi_realtime) > 0:
			self.realtime_status = False
			self.realtime.setVisible(True)
			self.realtime.setText("Tempo reale off")
		
	def onScambia(self):
		da, a = self.base.by_name('da').getText(), self.base.by_name('a').getText()
		self.base.by_name('da').setText(a)
		self.base.by_name('a').setText(da)
