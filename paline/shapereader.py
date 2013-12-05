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

import shapefile

class ShapeReader(object):
	def __init__(self, filename):
		self.sf = shapefile.Reader(filename)
		self.records = self.sf.shapeRecords()
		"""
		fs = self.fs.fields
		self.fields = {}
		for i in range(1, len(fs)):
			self.fields[fs[i][0]] = i
		"""
		
	def __iter__(self):
		fs = self.sf.fields
		for r in self.records:
			fields = {}
			for i in range(1, len(fs)):
				fields[fs[i][0]] = r.record[i - 1]
			yield((r.shape.points, fields))
