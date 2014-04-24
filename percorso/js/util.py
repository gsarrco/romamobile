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

from prnt import prnt
from __pyjamas__ import JS
from pyjamas import DOM
from pyjamas.ui.Calendar import Calendar, DateField
from pyjamas.ui.RootPanel import RootPanel
from pyjamas.ui.VerticalPanel import VerticalPanel
from pyjamas.ui.HorizontalPanel import HorizontalPanel
from pyjamas.ui.SimplePanel import SimplePanel
from pyjamas.ui.ScrollPanel import ScrollPanel
from pyjamas.ui.FocusPanel import FocusPanel
from pyjamas.ui.DisclosurePanel import DisclosurePanel
from pyjamas.ui.DialogBox import DialogBox
from pyjamas.ui.TabPanel import TabPanel
from pyjamas.ui.Grid import Grid
from pyjamas.ui.Frame import Frame
from pyjamas.ui.TextBox import TextBox
from pyjamas.ui.TextArea import TextArea
from pyjamas.ui.HTML import HTML
from pyjamas.ui.FlowPanel import FlowPanel
from pyjamas.ui.FlexTable import FlexTable
from pyjamas.ui.Anchor import Anchor
from pyjamas.ui.FlexCellFormatter import FlexCellFormatter
from pyjamas.ui.Label import Label
from pyjamas.ui.CheckBox import CheckBox
from pyjamas.ui.ListBox import ListBox
from pyjamas.ui.Button import Button
from pyjamas.ui.ToggleButton import ToggleButton
from pyjamas.ui.PopupPanel import PopupPanel
from pyjamas.ui.KeyboardListener import KeyboardHandler
from pyjamas.ui.FocusListener import FocusHandler
from pyjamas.ui.Tree import Tree, TreeItem
from pyjamas.ui.Image import Image
from pyjamas.ui import HasAlignment, HorizontalSplitPanel, FocusListener
from pyjamas.ui.MenuBar import MenuBar
from pyjamas.ui.MenuItem import MenuItem
from pyjamas.ui.Widget import Widget
from pyjamas.ui.Hyperlink import Hyperlink
from pyjamas import Window, History
from pyjamas.Timer import Timer
from datetime import date, time, datetime, timedelta
from DissolvingPopup import DissolvingPopup
from pyjamas.ui.HTMLPanel import HTMLPanel
from messages import messages
from globals import get_user, get_control, old_android


class JsonHandler():
	def __init__(self, callback, callback_error=None, data=None):
		self.callback = callback
		self.callback_error = callback_error
		self.data = data
	
	def onRemoteResponse(self, res):
		if self.callback is not None:
			if isinstance(self.callback, str):
				DissolvingPopup(self.callback)
			elif self.data is None:
				self.callback(res)
			else:
				self.callback(res, self.data)

	def onRemoteError(self, text, code):
		wait_stop()
		if self.callback_error is not None:
			if self.data is None:
				self.callback_error(text, code)
			else:
				self.callback(text, code, self.data)
		else:
			prnt(text)
			prnt(code)
			
class MyKeyboardHandler(KeyboardHandler):
	def __init__(self, callback):
		self.callback = callback
	
	def onKeyDown(self, res):
		self.callback()

def redirect(url):
	JS("""$wnd.location.replace(url);""")
	
def date2mysql(d):
	return d.strftime("%Y-%m-%d")

def mysql2date(s):
	return date(year=int(s[0:4]), month=int(s[5:7]), day=int(s[8:10]))

def date2italian(d):
	return d.strftime("%d/%m/%Y")

def italian2date(s):
	return date(year=int(s[6:10]), month=int(s[3:5]), day=int(s[0:2]))

def datetime2mysql(dt):
	return dt.strftime("%Y-%m-%d %H:%M:%S")


def mysql2datetime(s):
	return datetime(
		year=int(s[0:4]),
		month=int(s[5:7]),
		day=int(s[8:10]),
		hour=int(s[9:11]),
		minute=int(s[12:14]),
		second=int(s[15:17]),
	)

def validateMandatory(tbs):
	"""
	Verifica che tutte le textbox siano state riempite ed evidenzia le textbox non riempite
	
	tbs: lista ti textbox
	return: True sse tutte sono state riempite
	"""
	error = False
	for tb in tbs:
		if tb.getText() == '':
			tb.addStyleName('validation-error')
			error = True
	return not error

def validateInteger(tbs):
	"""
	Verifica che tutte le textbox contengano numeri interi ed evidenzia le textbox non riempite
	
	tbs: lista ti textbox
	return: True sse tutte contengono numeri interi
	"""
	error = False
	for tb in tbs:
		if not tb.getText().isdigit():
			tb.addStyleName('validation-error')
			error = True
	return not error


class ValidatingFieldsChangeListener():
	def onChange(self, widget):
		widget.removeStyleName('validation-error')
		
	def onKeyDown(self, sender, keycode, modifiers):
		sender.removeStyleName('validation-error')
		
	def onKeyUp(self, sender, keycode, modifiers):
		pass
		 
	def onKeyPress(self, sender, keycode, modifiers):
		pass 
		
vfcl = ValidatingFieldsChangeListener()

def setValidatingFields(fields):
	"""
	Add a listener to fields, such that validation-error style is removed
	when user changes field content
	"""	
	for f in fields:
		f.addChangeListener(vfcl)
		f.addKeyboardListener(vfcl)
		
def emptyFields(fields):
	"""
	Clear content of textboxes
	"""
	for f in fields:
		f.setText('')

class DataButton(Button):
	"""
	Button holding some associated data
	"""
	def __init__(self, html, callback, data):
		"""
		callback is a function, not a class
		"""
		Button.__init__(self, html, getattr(self, "onButton"))
		self.data = data
		self.callback = callback
	
	def onButton(self):
		self.callback(self, self.data)

class QuestionDialogBox(DialogBox):
	def __init__(self, title, question, answers):
		"""
		Init a dialog box with predefined answers
		
		Each answer has an associated callback function; it can be None if
		no other action than closing the dialog box is required
		
		title, question: strings
		answers: list of 3-ples with the form (answer_string, callback, data)
		"""
		DialogBox.__init__(self, glass=True)
		contents = VerticalPanel(StyleName="Contents", Spacing=4)
		contents.add(HTML(question))
		buttons = HorizontalPanel()
		contents.add(buttons)
		contents.setCellWidth(buttons, '100%')
		contents.setCellHorizontalAlignment(buttons, HasAlignment.ALIGN_RIGHT)
		buttons.setWidth('100%')
		perc = "%d%" % int(100 / len(answers))
		for a in answers:
			db = DataButton(a[0], self.onButton, (a[1], a[2]))
			db.setWidth('100%')
			buttons.add(db)
			buttons.setCellWidth(db, perc)
		self.setHTML('<b>%s</b>' % title)
		self.setWidget(contents)
		left = (Window.getClientWidth() - 200) / 2 + Window.getScrollLeft()
		top = (Window.getClientHeight() - 100) / 2 + Window.getScrollTop()
		self.setPopupPosition(left, top)
		
	def onButton(self, button, data):
		self.hide()
		callback = data[0]
		if callback is not None:
			callback(data[1])

class HourListBox(ListBox):	
	def __init__(self):
		ListBox.__init__(self)
		for h in range(0, 24):
			ora = "%02d" % h
			self.addItem(ora, ora)
		
	def selectValue(self, v):
		v = "%02d" % int(v)
		return ListBox.selectValue(self, v)

class MinuteListBox(ListBox):
	def __init__(self):
		ListBox.__init__(self)
		for m in range(0, 60, 5):
			minuto = "%02d" % m
			self.addItem(minuto, minuto)

	def selectValue(self, v):
		v = "%02d" % int(v)
		return ListBox.selectValue(self, v)
		
		
class MyAnchor(Anchor):
	def __init__(self, max_parita=2, *args, **kwargs):
		Anchor.__init__(self, *args, **kwargs)
		self.my_parita = 0
		self.max_parita = max_parita
		
	def set_numero_eventi(self, n):
		self.max_parita = n
		
	def addClickListener(self, listener):
		self.my_original_listener = listener
		Anchor.addClickListener(self, self.myClickListener)
		
	def myClickListener(self, source):
		self.my_parita += 1
		if self.my_parita >= self.max_parita:
			self.my_parita = 0
			self.my_original_listener(source)
		
				
class HelpButton(HorizontalPanel):
	def __init__(self, text, align_right=False):
		HorizontalPanel.__init__(self)
		self.img = Image("question.png")
		self.add(self.img)
		if align_right:
			self.setWidth('100%')
			self.setCellHorizontalAlignment(self.img, HasAlignment.ALIGN_RIGHT)
		self.text = text
		self.img.addClickListener(self.showPopup)
		self.img.addStyleName('help-image')

	def showPopup(self, event):
		contents = HTML(self.text)
		contents.addClickListener(getattr(self, "onClick"))

		self._popup = PopupPanel(autoHide=True)
		self._popup.add(contents)
		self._popup.setStyleName("help-popup")
		pw = Window.getClientWidth()
		x = self.img.getAbsoluteLeft()
		y = self.img.getAbsoluteTop()
		left = x + 10 if pw - x > 300 else x - 300
		top = y + 10
		self._popup.setPopupPosition(left, top)
		self._popup.show()

	def onClick(self, sender=None):
		self._popup.hide()

		
class StyledFlexTable(FlexTable):
	def __init__(self, *args, **kwargs):
		FlexTable.__init__(self, *args, **kwargs)
		self.formatter = FlexCellFormatter(self)
		self.setCellFormatter(self.formatter)		
		self.row = 0
		self.column = 0
		
	def newRow(self):
		self.row += 1
		self.column = 0
		
	def getRow(self):
		return self.row
		
	def addStyledWidget(self, w, style=None, center=False, expand=False):
		self.setWidget(self.row, self.column, w)
		if style is not None:
			self.formatter.addStyleName(self.row, self.column, style)
		if type(center) == bool:
			if center:
				self.formatter.setHorizontalAlignment(self.row, self.column, HasAlignment.ALIGN_CENTER)
		else:
			self.formatter.setHorizontalAlignment(self.row, self.column, center)
		if expand:
			self.formatter.setWidth(self.row, self.column, '100%')
			w.setWidth('100%')
		self.column += 1
		
class StyledFixedColumnFlexTable(StyledFlexTable):
	def __init__(self, *args, **kwargs):
		self.column_count = kwargs['column_count']
		del kwargs['column_count']
		StyledFlexTable.__init__(self, *args, **kwargs)
		
	def addStyledWidget(self, w, style=None, center=False, expand=False):
		StyledFlexTable.addStyledWidget(self, w, style, center, expand)
		if self.column == self.column_count:
			self.newRow()
			
	def add(self, w, center=True, expand=False):
		self.addStyledWidget(w, center=center, expand=expand)

		
		
class AutofitHorizontalPanel(HorizontalPanel):
	def __init__(self, owner):
		HorizontalPanel.__init__(self)
		self.owner = owner
		self.setWidth('100%')
		self.owner.add(self)
		self.owner.setCellWidth(self, '100%')
		#self.owner.setCellVerticalAlignment(self, HasAlignment.ALIGN_MIDDLE)
		
class AutofitVerticalPanel(VerticalPanel):
	def __init__(self, owner):
		VerticalPanel.__init__(self)
		self.owner = owner
		self.setHeight('100%')
		self.owner.add(self)
		self.owner.setCellHeight(self, '100%')
		#self.owner.setCellHorizontalAlignment(self, HasAlignment.ALIGN_CENTER)
		
class Autofit(object):
	def __init__(self, owner):
		object.__init__(self)
		self.owner = owner
		self.owner.add(self)
		self.setSize('100%', '100%')
		self.owner.setCellWidth(self, '100%')
		self.owner.setCellHeight(self, '100%')
		
class HTMLFlowPanel(FlowPanel):
	"""
	Requires the following CSS class to be defined:
	.inl {
		display: inline-block;
		vertical-align: middle;
	}
	.inl-ie6 {
		display: inline;
		vertical-align: middle;
	}
	"""
	def setInl(self, w):
		w.addStyleName('inl')
	
	def add(self, w):
		self.setInl(w)
		FlowPanel.add(self, w)
		
	def addHtml(self, html):
		self.add(HTML(html))
		
	def addBr(self):
		FlowPanel.add(self, HTML(''))
		
	def addAnchor(self, text, callback):
		a = MyAnchor()
		h = HTML(text)
		self.setInl(h)
		a.setWidget(h)
		a.addClickListener(callback)
		self.add(a)


class HidingPanel(HorizontalPanel):
	def __init__(self, open=True):
		HorizontalPanel.__init__(self)
		self.content_panel = SimplePanel()
		self.content_panel.setSize('300px', '100%')
		HorizontalPanel.add(self, self.content_panel)	
		
		hp = HorizontalPanel()
		hp.setSize('5px', '100%')
		hp.addStyleName('hiding-splitter')
		HorizontalPanel.add(self, hp)
		self.setCellWidth(hp, '5px')		
		
		self.hider_panel = MyAnchor()
		hp.add(self.hider_panel)
		self.hider_panel.addClickListener(self.onHider)
		self.hider_panel.setSize('5px', '100%')
		hp.setCellWidth(self.hider_panel, '5px')
		self.hider_panel.addStyleName('hidePanel')
		self.setCellWidth(self.content_panel, '100%')
		self.hider_panel.set_numero_eventi(1)
		
		self.open_label = MyAnchor()
		#self.html_open_label = HTML("&nbsp;&laquo;&nbsp;")
		self.html_open_label = Image('toolbar/grip.png', Width='24px', Height='48px')
		self.open_label.setWidget(self.html_open_label)
		self.html_open_label.addStyleName('hiding-label-html')
		hp.add(self.open_label)
		# hp.setCellWidth(self.open_label, 0)
		self.open_label.addStyleName('hiding-label')
		self.open_label.addClickListener(self.onHider)

		self.hide_listener = None
		self.is_open = open
		self.update()

	def addHideListener(self, listener):
		self.hide_listener = listener
		
	def add(self, widget):
		#self.content_panel.remove(self.w)
		self.w = widget
		self.content_panel.add(widget)
		
	def update(self):
		self.content_panel.setVisible(self.is_open)
		"""
		if self.is_open:
			self.html_open_label.setHTML("&nbsp;&laquo;&nbsp;")
		else:
			self.html_open_label.setHTML("&nbsp;&raquo;&nbsp;")
		"""
		if self.hide_listener is not None:
			self.hide_listener(self)		
		
	def onHider(self):
		self.is_open = not self.is_open
		self.update()
		
	def hide(self, hide=True):
		if self.is_open != (not hide):
			self.is_open = not hide
			self.update()


class AutoLayout:
	def __init__(self, owner, sub=[], add_to_owner=False, **kwargs):
		self.owner = owner
		self.sub = []
		self.dict = {}
		reserved_args = ['class', 'name', 'args', 'style', 'enabled', 'checked', 'click_listener', 'client_data'] + self.getReservedArgs()
		for l in sub:
			klass = l['class']
			res = dict([(x, l[x]) for x in l if x not in reserved_args and x[:5] != 'call_'])
			call = dict([(x[5:], l[x]) for x in l if x[:5] == 'call_'])
			args = []
			if issubclass(klass, AutoLayout):
				args.append(self)
			if 'args' in l:
				args.extend(l['args'])
			el = klass(*args, **res)
			if 'style' in l:
				el.addStyleName(l['style'])
			if 'enabled' in l:
				el.setEnabled(l['enabled'])
			if 'checked' in l:
				el.setChecked(l['checked'])
			if 'click_listener' in l:
				el.addClickListener(l['click_listener'])
			if 'client_data' in l:
				l.client_data = l['client_data']
			for f in call:
				getattr(el, f)(*(call[f][0]), **(call[f][1]))
			self.onCreate(el, l)
			self.sub.append(el)
			if 'name' in l:
				self.dict[l['name']] = el
			
		if owner is not None and add_to_owner:
			owner.add(self)
	
	def onCreate(self, el, kwargs):
		el.setSize('100%', '100%')
		self.add(el)
	
	def getReservedArgs(self):
		return []
	
	def by_name(self, name):
		if name in self.dict:
			return self.dict[name]
		for s in self.sub:
			if isinstance(s, AutoLayout):
				el = s.by_name(name)
				if el is not None:
					return el
		return None
	
	def __getitem__(self, name):
		return self.by_name(name)
		
	
	
class HP(HorizontalPanel, AutoLayout):

	def __init__(self, owner, sub=[], **kwargs):
		HorizontalPanel.__init__(self)
		AutoLayout.__init__(self, owner, sub, **kwargs)
		self.setHeight('100%')
		
	def onCreate(self, el, kwargs):
		#el.setSize('100%', '100%')
		self.add(el)
		if not 'width' in kwargs:
			el.setWidth('100%')
		if 'width' in kwargs:
			if kwargs['width'] is not None:
				el.setWidth('100%')
				self.setCellWidth(el, kwargs['width'])
		if not 'height' in kwargs:
			self.setCellHeight(el, '100%')
		elif kwargs['height'] is not None:
			self.setCellHeight(el, kwargs['height'])
		if 'vertical_alignment' in kwargs:
			self.setCellVerticalAlignment(el, kwargs['vertical_alignment'])
		if 'horizontal_alignment' in kwargs:
			self.setCellHorizontalAlignment(el, kwargs['horizontal_alignment'])
			
	def getReservedArgs(self):
		return ['width', 'height', 'vertical_alignment', 'horizontal_alignment']

			
class VP(VerticalPanel, AutoLayout):
	def __init__(self, owner, sub=[], **kwargs):
		VerticalPanel.__init__(self)
		AutoLayout.__init__(self, owner, sub, **kwargs)
		self.setWidth('100%')
		
	def onCreate(self, el, kwargs):
		if not 'width' in kwargs:
			el.setWidth('100%')
		elif kwargs['width'] is not None:
			el.setWidth(kwargs['width'])
		self.add(el)
		if 'height' in kwargs:
			if kwargs['height'] is not None:
				self.setCellHeight(el, kwargs['height'])
				el.setHeight('100%')
		else:
			self.setCellHeight(el, '100%')
			el.setHeight('100%')			
		self.setCellWidth(el, '100%')
		if 'horizontal_alignment' in kwargs:
			self.setCellHorizontalAlignment(el, kwargs['horizontal_alignment'])

			
	def getReservedArgs(self):
		return ['height', 'width', 'horizontal_alignment']
	
class DP(DisclosurePanel, AutoLayout):
	def __init__(self, owner, sub=[], **kwargs):
		DisclosurePanel.__init__(self, kwargs['title'])
		AutoLayout.__init__(self, owner, sub, **kwargs)
		self.setWidth('100%')
		self.setOpen(True)
		
	def getReservedArgs(self):
		return ['height']
	
class SP(SimplePanel, AutoLayout):
	def __init__(self, owner, sub=[], **kwargs):
		SimplePanel.__init__(self)
		AutoLayout.__init__(self, owner, sub, **kwargs)
		self.setWidth('100%')
		
	def getReservedArgs(self):
		return ['height']
	
class GP(StyledFixedColumnFlexTable, AutoLayout):
	def __init__(self, owner, sub=[], **kwargs):
		StyledFixedColumnFlexTable.__init__(self, column_count=kwargs['column_count']	)
		AutoLayout.__init__(self, owner, sub, **kwargs)
		self.setWidth('100%')
		
	def onCreate(self, el, kwargs):
		expand = True
		if 'expand' in kwargs:
			expand = kwargs['expand']
		self.addStyledWidget(el, expand=expand)
		
	def getReservedArgs(self):
		return ['expand']
	
def get_checked_radio(base, name, values):
	for v in values:
		if base.by_name("%s_%s" % (name, str(v))).isChecked():
			return v
	return None


class ValidationErrorRemover(KeyboardHandler):
	def __init__(self, widget):
		self.widget = widget

	def onKeyDown(self, sender, keycode, modifiers):
		self.widget.removeStyleName('validation-error')
		
	def remove(self):
		self.widget.removeStyleName('validation-error')
		
class LoadingButton(Button):
	def __init__(self, *args, **kwargs):
		Button.__init__(self, *args, **kwargs)
		self.backup_html = None
		
	def start(self):
		if self.backup_html is None:
			self.setEnabled(False)
			self.backup_html = self.getHTML()
			# self.setHTML('<img src="loading.gif" />')
			wait_start()
			
	def stop(self):
		if self.backup_html is not None:
			# self.setHTML(self.backup_html)
			self.backup_html = None
			self.setEnabled(True)
			wait_stop()
		
class MenuCmd:
	def __init__(self, handler):
	  self.handler = handler
	def execute(self):
	  self.handler()
	  
# ToggleImage
class ToggleImage(Image):
	def __init__(self, filename, style_inactive, style_active, callback=None, data=None, can_turn_off=True):
		Image.__init__(self, filename)
		self.style_inactive = style_inactive
		self.style_active = style_active
		self.callback = callback
		self.active = False
		self.setActive(False)
		self.addClickListener(self.onClick)
		self.data = data
		self.can_turn_off = can_turn_off

	def setTooltip(self, s):
		self.getElement().setAttribute('title', s)
		
	def setActive(self, active=None):
		if active is None:
			active = not self.active
		self.active = active
		if not active:
			self.removeStyleName(self.style_active)
			self.addStyleName(self.style_inactive)
		else:
			self.removeStyleName(self.style_inactive)
			self.addStyleName(self.style_active)
			
	def isActive(self):
		return self.active
	
	def onClick(self):
		if self.can_turn_off:
			self.setActive()
		elif not self.active:
			self.setActive(True)
		if self.callback is not None:
			self.callback(self)


# SearchBox

class SearchPopup(PopupPanel, KeyboardHandler):
	def __init__(self, els, callback, textbox=None):
		PopupPanel.__init__(self, False, modal=False)
		self.sp = ScrollPanel()
		self.sp.setSize('100%', '400px')
		self.add(self.sp)
		self.callback = callback
		self.list = MenuPanel(None, [], None)
		self.sp.addStyleName('big-list')
		self.els = els
		self.names = {}
		for el in els:
			pk, name = el
			self.list.addItem(pk, name, self.onList)
			self.names[pk] = name
		self.sp.add(self.list)
		self.textbox = textbox
		self.addStyleName('search-popup')

	def update(self, els):
		self.list.clear()
		self.names = {}
		for el in els:
			pk, name = el
			self.list.addItem(pk, name, self.onList)
			self.names[pk] = name
	
	def onList(self, mpi):
		self.callback(mpi.id, mpi.text)
		
	def setFocus(self, focus=True):
		self.list.setFocus(focus)

	def onKeyDown(self, sender, keycode, modifiers):
		return
		if keycode == 38 and self.textbox is not None and self.list.getSelectedIndex() == 0:
			self.list.setValueSelection([])
			self.textbox.setFocus(True)

	def onKeyUp(self, sender, keycode, modifiers):
		return
		if keycode == 13:
			pk = self.list.getValue(self.list.getSelectedIndex())
			self.callback(pk, self.names[pk])
		if keycode == 27:
			self.hide()

			
	def getSingleElement(self):
		"""
		Return (pk, name) if a single element is present; None otherwise
		"""
		if len(self.names) == 1:
			return self.names.items()[0]
		return None


class SearchBox(TextBox, KeyboardHandler, FocusListener):
	def __init__(self, method, callback=None, min_len=3, delay=100, mandatory=True):
		"""
		method: json-rpc method. It expects a search string, a returns a list of pairs (pk, name)
		"""
		TextBox.__init__(self)
		self.method = method
		self.addKeyboardListener(self)
		self.addFocusListener(self)
		self.pk = -1
		self.popup = None
		self.callback = callback
		self.delay = delay
		self.min_len = min_len
		self.timer = Timer(notify=self.onTimer)
		self.timer_enabled = False
		self.mandatory = mandatory
		el = self.getElement()
		self.schedule_popup_close = False
		JS("""
			el.oninput = function(e) {
				self.onInput();
			};
		""")

	def closePopup(self):
		self.stop_timer()
		if self.popup is not None:
			self.popup.hide()

	def onTimer(self):
		if self.schedule_popup_close:
			self.schedule_popup_close = False
			self.timer_enabled = False
			self.popup.hide()
		elif self.timer_enabled:
			search = self.getText()
			if len(search) >= self.min_len:
				self.method(search, JsonHandler(self.onMethodDone))

	def start_timer(self, delay=None):
		self.timer_enabled = True
		delay = self.delay if delay is None else delay
		self.timer.schedule(delay)

	def stop_timer(self):
		self.timer_enabled = False
		self.timer.cancel()
		
	def onMethodDone(self, res):
		if self.timer_enabled and res['cerca'] == self.getText() and len(res['risultati']) > 0:
			res = res['risultati']
			if self.popup is not None:
				self.popup.update(res)
			else:
				self.popup = SearchPopup(res, self.onSearchPopupSelected, self)
			self.popup.setPopupPosition(self.getAbsoluteLeft(), self.getAbsoluteTop() + self.getClientHeight())
			self.popup.show()
		elif self.popup is not None:
			self.popup.hide()

	def manualPopup(self, elems):
		"""
		Manually open a popup panel.

		elems is a list of pairs (pk, value)
		"""
		self.stop_timer()
		self.setFocus()
		if self.popup is not None:
			self.popup.update(elems)
		else:
			self.popup = SearchPopup(elems, self.onSearchPopupSelected, self)
		self.popup.setPopupPosition(self.getAbsoluteLeft(), self.getAbsoluteTop() + self.getClientHeight())
		self.popup.show()

	def onFocus(self):
		self.selectAll()
			
	def onLostFocus(self):
		self.stop_timer()
		if self.mandatory and self.popup is not None:
			el = self.popup.getSingleElement()
			if el is not None:
				pk, name = el
				self.onSearchPopupSelected(pk, name)
		if self.popup is not None:
			# Process pending evens, i.e., an eventual click on a menu item, before closing popup
			self.schedule_popup_close = True
			self.start_timer(delay=150)

	def onInput(self):
		self.pk = -1
		self.start_timer()

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode in [9, 13, 27]: # TAB, Enter, ESC
			self.stop_timer()
			self.closePopup()

	def onKeyUp(self, sender, keycode, modifiers):
		self.removeStyleName('validation-error')
		if keycode == 40 and self.popup is not None: # Down
			self.popup.setFocus()
			self.stop_timer()
		elif self.mandatory and keycode == 13 and self.popup is not None:
			self.stop_timer()
			el = self.popup.getSingleElement()
			if el is not None:
				pk, name = el
				self.onSearchPopupSelected(pk, name)

	def setValidationError(self):
		self.addStyleName('validation-error')

	def setText(self, text):
		TextBox.setText(self, text)
		self.pk = -1

	def getStatus(self):
		return (self.pk, TextBox.getText(self))

	def setStatus(self, pk, text):
		self.pk = pk
		TextBox.setText(self, text)
		
	def onSearchPopupSelected(self, pk, name):
		self.closePopup()
		TextBox.setText(self, name)
		self.setFocus(True)
		self.setCursorPos(len(name))
		self.pk = pk
		if self.callback is not None:
			self.callback()

class FavSearchBox(SearchBox):
	"""
	SearchBox con sostituzione dei preferiti, per Muoversi a Roma
	"""
	def getText(self):
		if self.pk != -1 and not str(self.pk).startswith('A'):
			s = 'fav:' + self.pk
		else:
			s = SearchBox.getText(self)
		return s
		
# Input mapper

class InputMapper(KeyboardHandler):
	def __init__(self, pk, desc, load_method, save_method, save_button, save_callback=None, load_callback=None, close_button=None, close_callback=None):
		"""
		pk: pk of object, or -1 if not created yet
		desc: list of dictionaries: {
			'name': field name,
			'type': 'free' | 'single' | 'multi' | 'address' | 'foreign' | 'custom',
			'input': input widget, or callback for custom type
		}
		load_method, save_methos: jsonrpc methods
		"""
		self.pk = pk
		self.desc = desc
		self.load_method = load_method
		self.save_method = save_method
		self.desc = {}
		for el in desc:
			self.desc[el['name']] = el
			if el['type'] in ['free', 'single', 'multi']:
				el['input'].addChangeListener(self.onChange)
				if el['type'] == 'free':
					el['input'].addKeyboardListener(self)
		self.load()
		self.save_button = save_button
		if save_button is not None:
			save_button.addClickListener(self.onSaveButton)
		self.save_callback = save_callback
		self.load_callback = load_callback
		self.modified = False
		self.close_button = close_button
		self.close_callback = close_callback
		if self.close_button is not None:
			self.close_button.addClickListener(self.onCloseButton)
		
	def setModified(self, modified=True):
		if modified and not self.modified:
			self.modified = True
			if self.close_button is not None:
				self.close_button.setText('Annulla')
		elif not modified and self.modified:
			self.modified = False
			if self.close_button is not None:
				self.close_button.setText('Chiudi')
		
	def onChange(self, sender):
		sender.removeStyleName('validation-error')
		self.setModified()
			
	def onKeyUp(self, sender, keycode, modifiers):
		sender.removeStyleName('validation-error')
		self.setModified()
		
	def onSaveDone(self, res):
		if res['status'] == 'OK':
			self.pk = res['pk']
		else:
			DissolvingPopup(res['msg'], error=True)
			for f in res['fields']:
				d = self.desc[f]
				if d['type'] in ['free', 'multi', 'single']:
					d['input'].addStyleName('validation-error')
				elif d['type'] in ['address', 'foreign']:
					d['input'].setValidationError()
		if self.save_button is not None:
			self.save_button.setEnabled(True)
		self.setModified(False)
		if self.save_callback is not None:
			self.save_callback(res)
		
	def save(self, callback):
		out = {}
		for name in self.desc:
			d = self.desc[name]
			t = d['type']
			input = d['input']
			if t == 'free':
				out[name] = input.getText()
			elif t == 'single':
				out[name] = input.getValue(input.getSelectedIndex())
			elif t == 'multi':
				#TODO
				out[name] = ''
			elif t == 'foreign':
				out[name] = input.pk if input.pk > -1 else None
			elif t == 'custom':
				out[name] = input()
			elif t == 'address':
				out[name] = input.getAddress()
		self.callback = callback
		self.save_method(self.pk, out, JsonHandler(self.onSaveDone))
		
	def onSaveButton(self):
		self.save_button.setEnabled(False)
		self.save()
		
	def onCloseButton(self):
		self.confirmClose(self.close_callback)
		
	def confirmClose(self, callback_yes, callback_no=None):
		if not self.modified:
			if callback_yes is not None:
				callback_yes()
		else:
			QuestionDialogBox("Conferma", "Ci sono modifiche non salvate. Confermi la chiusura?", [("S&igrave;", callback_yes, None), ("No", callback_no, None)]).show()
		
	def onLoadDone(self, res):
		for name in res:
			el = res[name]
			d = self.desc[name]
			input = d['input']
			type = d['type']
			if type == 'free':
				input.setText(el)
			elif type == 'single':
				input.clear()
				pk = el[0]
				i = 0
				for item in el[1]:
					ipk, iname = item
					input.addItem(iname, ipk)
					if ipk == pk:
						input.setSelectedIndex(i)
					i += 1
			elif type == 'multi':
				#TODO
				pass
			elif type == 'foreign':
				pk, text = el
				input.setText(text)
				input.pk = pk
			elif type == 'custom':
				pass
			elif type == 'address':
				text, lng, lat = el
				input.setAddress(text, lng, lat)
		if self.load_callback is not None:
			self.load_callback(res)
		
	def load(self):
		self.load_method(self.pk, JsonHandler(self.onLoadDone))


class DeferrableTabPanel(TabPanel):
	def __init__(self, owner):
		super(DeferrableTabPanel, self).__init__()
		History.addHistoryListener(self)
		self.owner = owner
		self.selected = None

	def onHistoryChanged(self, token):
		if token.startswith('htm-'):
			index = int(token[4:])
			super(DeferrableTabPanel, self).selectTab(index)


	def onTabSelected(self, sender, tabIndex):
		res = super(DeferrableTabPanel, self).onTabSelected(sender, tabIndex)
		self.selected = self.getWidget(tabIndex)
		History.newItem("htm-%d" % tabIndex)
		self.selected.perform_deferred()
		self.selected.onTabSelected()
		return res

	def add(self, widget, *args, **kwargs):
		widget.dtp = self
		return TabPanel.add(self, widget, *args, **kwargs)

	def star_tab(self, index):
		tab_bar = self.getTabBar()
		# h = tab_bar.getTabHTML(index)
		w = tab_bar.getTabWidget(index)
		w.addStyleName('tab-evidenziata')
		def remove_star():
			w.removeStyleName('tab-evidenziata')
		self.getWidget(index).do_or_defer(remove_star)


class DeferrablePanel(object):
	def __init__(self, deferrable_tab_panel, deferred_interval=None):
		object.__init__(self)
		self.op = []
		self.dtp = deferrable_tab_panel
		self.deferred_timer = Timer(notify=self.onTimer)
		self.deferred_interval = deferred_interval

	def onTimer(self):
		self.perform_deferred_actions()

	def perform_deferred_actions(self):
		self.deferred_timer.cancel()
		op = self.op
		self.op = []
		for el in op:
			o, args, kwargs = el
			o(*args, **kwargs)

	def do_or_defer(self, o, *args, **kwargs):
		self.op.append([o, args, kwargs])
		if self == self.dtp.selected:
			self.perform_deferred_actions()

	def perform_deferred(self):
		if self.deferred_interval is not None:
			self.deferred_timer.schedule(self.deferred_interval)
		else:
			self.perform_deferred_actions()


	def onTabSelected(self):
		pass


if old_android():
	class ScrollAdaptivePanel(VerticalPanel):
		def __init__(self):
			VerticalPanel.__init__(self)

		def relayout(self):
			pass

else:
	class ScrollAdaptivePanel(ScrollPanel):
		def __init__(self):
			ScrollPanel.__init__(self)

		def relayout(self):
			w = self.getWidget()
			self.remove(w)
			self.setHeight('100%')
			height = self.getClientHeight()
			self.setHeight(height)
			self.setWidget(w)

waiting = [None]

def wait_init(owner):
	waiting[0] = Waiting(owner)
	return waiting[0]

def wait_start():
	waiting[0].start()

def wait_stop():
	waiting[0].stop()

class Waiting(VerticalPanel):
	def __init__(self, owner):
		super(Waiting, self).__init__(Width='48px', Height='48px')
		self.wait = Image('wait.gif', Width='31px', Height='31px')
		self.menu = Image('toolbar/menu.png', Width='48px', Height='48px')
		self.add(self.menu)
		self.owner = owner
		self.owner.add(self)
		self.addStyleName('waiting')
		self.setVerticalAlignment(HasAlignment.ALIGN_MIDDLE)
		self.setHorizontalAlignment(HasAlignment.ALIGN_CENTER)

	def start(self):
		self.remove(self.menu)
		self.add(self.wait)

	def stop(self):
		self.remove(self.wait)
		self.add(self.menu)

	def setGeneralMenuPanel(self, menu_panel):
		self.menu.addClickListener(menu_panel.display_menu)

def getdefault(d, key, default):
	if key in d:
		return d[key]
	return default

# [default_lang, current_lang]
langs = ['', '']

def set_lang(default_lang, current_lang):
	langs[0] = default_lang
	langs[1] = current_lang

def get_lang():
	return langs[1]

def _(x):
	if langs[0] == langs[1]:
		return x
	try:
		return messages[langs[1]][x]
	except:
		return x


class MenuPanelItem(HorizontalPanel):
	def __init__(self, owner, id, text, listener=None, icon=None, width=None, height=None, action_icon=None, action_listener=None):
		HorizontalPanel.__init__(self)
		self.setWidth('100%')
		self.setVerticalAlignment(HasAlignment.ALIGN_MIDDLE)
		self.owner = owner
		self.id = id
		self.text = text
		self.addStyleName('menu-item')
		self.fp = FocusPanel()
		self.fp.setSize('100%', '100%')
		self.add(self.fp)
		self.setCellWidth(self.fp, '100%')
		self.hp = HorizontalPanel()
		self.fp.add(self.hp)
		self.hp.setHeight('100%')
		self.hp.setVerticalAlignment(HasAlignment.ALIGN_MIDDLE)
		if icon is not None:
			self.icon = Image(icon)
			if width is None:
				width = '72px'
			self.icon.setWidth(width)
			if height is None:
				height = '48px'
			self.icon.setHeight(height)
		else:
			self.icon = SimplePanel()
		self.icon.addStyleName('menu-item-icon')
		self.hp.add(self.icon)
		self.html = HTML(text)
		self.hp.add(self.html)
		self.action_listener = action_listener
		if action_icon is not None:
			self.action_icon = Image(action_icon)
			self.action_icon.addStyleName('menu-item-action-icon')
			self.add(self.action_icon)
			self.action_icon.addClickListener(self.onActionClick)
		self.listener = listener
		self.fp.addClickListener(self.onClick)

	def onClick(self):
		self.owner.hide()
		if self.listener is not None:
			self.listener(self)

	def onActionClick(self):
		if self.action_listener is not None:
			self.action_listener(self)

	def setText(self, t):
		self.html.setHTML(t)

	def setListener(self, listener):
		self.listener = listener


class MenuPanel(FocusPanel):
	"""
	Menu panel

	Definition is a list of dictionaries, with the following items:
	 * id: id of the item
	 * icon: url of the item icon, or None (optional)
	 * text: text of menu item
	 * listener: item listener
	 * action_icon: url of the action icon for the item, or None (optional)
	 * action_listener: action listener for the item (optional)
	"""
	def __init__(self, general_menu_panel, definition, title='Menu', icon=None):
		FocusPanel.__init__(self)
		self.vp = VerticalPanel(self)
		self.add(self.vp)
		self.gmp = general_menu_panel
		#self.setSize('100%', '100%')
		self.setWidth('100%')
		self.addStyleName('menu')
		self.vp.setWidth('100%')
		self.items = []
		self.itemdict = {}
		if title is not None:
			self.header = MenuPanelItem(
				self,
				id='header',
				text=title,
				listener=None,
				icon=icon,
			)
			self.header.addStyleName('menu-header')
			self.vp.add(self.header)
		for d in definition:
			mip = MenuPanelItem(
				self,
				id=d['id'],
				text=d['text'],
				listener=d['listener'],
				icon=getdefault(d, 'icon', None),
				action_icon=getdefault(d, 'action_icon', None),
				action_listener=getdefault(d, 'action_listener', None),
			)
			self.items.append(mip)
			self.itemdict[d['id']] = mip
			self.vp.add(mip)
		# self.addClickListener(self.onClick)

	def addItem(self, id, text, listener, icon=None, width=None, height=None):
		mip = MenuPanelItem(
			self,
			id=id,
			text=text,
			listener=listener,
			icon=icon,
			width=width,
			height=height,
		)
		self.items.append(mip)
		self.itemdict[id] = mip
		self.vp.add(mip)

	def clear(self):
		self.vp.clear()
		self.items = []
		self.itemdict = {}

	def by_id(self, id):
		return self.itemdict[id]

	def hide(self):
		if self.gmp is not None:
			self.gmp.display_menu(False)

	def onClick(self):
		self.hide()


class GeneralMenuPanel(SimplePanel):
	def __init__(self):
		SimplePanel.__init__(self)
		self.setSize('100%', '100%')
		self.active_menu = None

	def setMainPanel(self, main_panel):
		self.main_panel = main_panel
		self.add(main_panel)

	def setMenuPanel(self, menu_panel):
		self.menu_panel = menu_panel

	def display_menu(self, display=True, alternative_menu=None):
		if display:
			self.active_menu = alternative_menu if alternative_menu is not None else self.menu_panel
			self.remove(self.main_panel)
			self.add(self.active_menu)
		else:
			self.remove(self.active_menu)
			self.add(self.main_panel)
			self.active_menu = None


def setAttribute(widget, name, value):
	widget.getElement().setAttribute(name, value)

class PreferitiImage(Image):
	def __init__(self, tipo, nome, descrizione, esiste, client):
		self.esiste = esiste
		self.prepareUrl()
		Image.__init__(self, self.url)
		self.tipo = tipo
		self.nome = nome
		self.descrizione = descrizione
		self.client = client
		self.addClickListener(self.onClick)

	def onClick(self):
		u = get_user()
		if u is None:
			ask_login()
		else:
			self.esiste = not self.esiste
			self.prepareUrl()
			self.setUrl(self.url)
			self.client(self.tipo, self.nome, self.descrizione, self.esiste, JsonHandler(self.onClientDone))

	def prepareUrl(self):
		if self.esiste:
			self.url = 'preferiti.png'
		else:
			self.url = 'preferiti-off.png'

	def onClientDone(self, res):
		get_control().setPreferiti(res['fav'])

def ask_login():
	QuestionDialogBox(
		_('Accesso richiesto'),
		_("Per continuare devi effettuare l'accesso."),
		[
			(_('Accedi o registrati'), get_control().onLogin, None),
			(_('Annulla'), None, None),
		]
	).show()

def storage_get(key, default_value=None):
	JS("""
		if(localStorage && localStorage[key]) {
			ret = localStorage[key];
		} else {
			ret = default_value;
		}
	""")
	return ret

def storage_set(key, value):
	JS("""localStorage[key] = value;""")

def enforce_login(f):
	def g(*args, **kwargs):
		u = get_user()
		if u is None:
			ask_login()
		else:
			return f(*args, **kwargs)
	return g

# class PausableTimer(Timer):
# 	timers = []
#
# 	def __init__(self, delayMillis=0, notify=None):
# 		self.delayMillis = delayMillis
# 		self.notify = notify
# 		Timer.__init__(self, delayMillis, notify)
# 		PausableTimer.timers.append(self)
# 		if delayMillis == 0:
# 			self.modo = 0
# 		else:
# 			self.modo = 1
# 		self.paused = None
#
# 	def call(self):
# 		if self.notify is not None:
# 			self.notify()
# 		else:
# 			self.run()
#
# 	def schedule(self, delayMillis):
# 		self.modo = 1
# 		self.delayMillis = delayMillis
# 		Timer.schedule(self, delayMillis)
#
# 	def cancel(self):
# 		self.modo = 0
# 		Timer.cancel(self)
#
# 	def scheduleRepeating(self, periodMillis):
# 		self.modo = 2
# 		self.delayMillis = periodMillis
# 		Timer.scheduleRepeating(self, periodMillis)
#
# 	def pause(self):
# 		if self.paused is None:
# 			self.paused = datetime.now()
# 			Timer.cancel(self)
#
# 	def resume(self):
# 		if self.paused is not None:
# 			elapsed = (datetime.now() - self.paused).total_seconds() * 1000
# 			self.paused = None
# 			if elapsed <
