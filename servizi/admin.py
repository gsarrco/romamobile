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

from django.contrib import admin
from models import *

admin.site.register(Servizio)
admin.site.register(FasciaServizio)
admin.site.register(Versione)
admin.site.register(ServizioFrontEnd)
admin.site.register(Lingua)
admin.site.register(ServizioLingua)
admin.site.register(GruppoServizio)
admin.site.register(GiornoSettimana)
admin.site.register(LinguaPreferita)
admin.site.register(LogoPersonalizzato)
admin.site.register(Festivita)

class RicercaErrataAdmin(admin.ModelAdmin):
    list_display = ('ricerca', 'conteggio', 'conversione')
    search_fields = ('ricerca', 'conversione')

admin.site.register(RicercaErrata, RicercaErrataAdmin)