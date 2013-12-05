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


client = JSONProxy('/json/', ['risorse_lista_tipi'])


class CercaLuogoPanel(SimplePanel, KeyboardHandler, FocusHandler):
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
							'args': ['Indirizzo'],
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
												},										
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
						{
							'class': ListBox,
							'name': 'risorse',
							'call_setVisibleItemCount': ([6], {}),
							'call_setMultipleSelect': ([True], {}),
						},
						{
							'class': MyAnchor,
							'name': 'risorse_percorso',
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
		
		self.risultati_holder = self.base.by_name('risultati_holder')
		self.risultati = None
		self.cl_layer = None
		self.cr_lista_tipi = []
		self.cr_a = None
		rp = self.base.by_name('risorse_percorso')
		rp.setWidget(HTML('Cerca luogo lungo un percorso'))
		rp.addClickListener(self.onRisorsePercorso)
		client.risorse_lista_tipi([], JsonHandler(self.onRisorsaListaTipiDone))
		
	def availableParams(self):
		return [
			'cr_da',
			'cr_a',
			'cr_lista_tipi',
			'cr',
		]
		
	def setParam(self, param, value):
		if param == 'cr_da':
			self.base.by_name('query').setText(value)
		if param == 'cr_a':
			self.cr_a = value
		if param == 'cr_lista_tipi':
			self.cr_lista_tipi = value.split(',')
			client.risorse_lista_tipi(self.cr_lista_tipi, JsonHandler(self.onRisorsaListaTipiDone))
		if param == 'cr':
			if self.cr_a is None:
				self.ripristinaWidgets()
				self.cercaLuogo(self.base.by_name('query').getText(), self.cr_lista_tipi)
			else:
				self.owner.cercaPercorsoRisorse(
					self.base.by_name('query').getText(),
					self.cr_lista_tipi,
					self.cr_a,
				)
		
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
		self.map.addRightClickOption("Luoghi vicini", self.onRightClick)
		
	def onRightClick(self, lat, lng):
		query = self.base.by_name('query')
		query.setText('punto:(%s,%s)' % (lat, lng))
		self.owner.setTabCercaLuogo()
		self.onCerca()

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()

		
	def onCerca(self):
		self.ripristinaWidgets()
		self.cercaLuogo(self.base.by_name('query').getText())
		
	def cercaLuogo(self, query, tipi=None):
		query = query.strip()
		if query == '':
			self.onCercaErrore({'stato': 'Error'})
			return
		if self.risultati is not None:
			self.risultati_holder.remove(self.risultati)
		self.risultati = DP(
			None,
			[ 
				{
					'class': VP,
					'style': 'indicazioni',
					'sub': [
						{
							'class': Label,
							'args': ['Risultati'],
							'style': 'indicazioni-h1',
							'height': None,
						},									
						{
							'class': VerticalPanel,
							'name': 'risultati_list',
							'args': [],
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
			title='Luoghi trovati',
		)
		self.risultati.setOpen(True)
		self.risultati_holder.add(self.risultati)
		risultati_list = self.risultati.by_name('risultati_list')
		if tipi is None:
			tipi = self.base.by_name('risorse').getSelectedValues()
		self.map.loadNewLayer('cerca_risorsa', 'risorsa', (query, tipi, 2000), reload=True, info_panel=risultati_list, on_error=self.onCercaErrore)
		
		

	def onRisorsaListaTipiDone(self, res):
		trs = set(self.cr_lista_tipi)
		risorse = self.base.by_name('risorse')
		risorse.clear()
		i = 0
		for r in res:
			risorse.addItem(r['nome'], r['id'])		
			risorse.setItemSelected(i, r['id'] in trs)
			i += 1


				
	def onCercaErrore(self, el):
		x, x_list, x_holder = self.getWidgets()
		if el['stato'] == 'Ambiguous':
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
		
		
	def onRisorsePercorso(self):
		self.owner.cercaPercorsoRisorse(
			self.base.by_name('query').getText(),
			self.base.by_name('risorse').getSelectedValues(),
		)