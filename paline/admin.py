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

from django.contrib import admin
from models import *

admin.site.register(PalinaPreferita)
admin.site.register(GruppoPalinePreferite)
admin.site.register(StatPeriodoAggregazione)
admin.site.register(Disservizio)
admin.site.register(DisservizioPalinaElettronica)
admin.site.register(LineaSospesa)
admin.site.register(ArcoRimosso)
admin.site.register(LogAvm)

