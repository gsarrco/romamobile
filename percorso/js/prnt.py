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

from pyjamas.ui.HTML import HTML
from pyjamas.ui.RootPanel import RootPanel
from __pyjamas__ import JS

main_panel = None

def prnt(s, title=""):
	#main_panel.aggiungi_errore(HTML(s), title)
	s = str(s)
	print s
	#JS("""alert(s);""")
	return
	s.replace('\n', '<br />')
	RootPanel().add(HTML(s))

