# coding: utf-8
#cython: cdivision=True

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


from libc.math cimport sqrt, abs
from tomtom import NodoTomTom, ArcoTomTom
import cython
from django.contrib.gis.geos import Point, GEOSGeometry, LineString
from paline.models import StradaTomtom
import gis.models as gis
from pprint import pprint
import traceback

cdef extern from "stdlib.h":
	void free(void* ptr)
	void* malloc(size_t size)
	void* realloc(void* ptr, size_t size)

#
# Geocoder
#


cdef double dot(double Ax, double Ay, double Bx, double By, double Cx, double Cy) nogil:
	cdef double ABx = Bx - Ax
	cdef double ABy = By - Ay
	cdef double BCx = Cx - Bx
	cdef double BCy = Cy - By
	cdef double dot = ABx * BCx + ABy * BCy
	return dot

cdef double cross(double Ax, double Ay, double Bx, double By, double Cx, double Cy) nogil:
	cdef double ABx = Bx - Ax
	cdef double ABy = By - Ay
	cdef double ACx = Cx - Ax
	cdef double ACy = Cy - Ay
	cdef double cross = ABx * ACy - ABy * ACx
	return cross

cdef double distance(double Ax, double Ay, double Bx, double By) nogil:
	cdef double d1 = Ax - Bx
	cdef double d2 = Ay - By
	return sqrt(d1*d1+d2*d2)

cdef double segment_point_dist(double Ax, double Ay, double Bx, double By, double Cx, double Cy) nogil:
	cdef double d = distance(Ax, Ay, Bx, By)
	cdef double dist, dot1, dot2
	if d > 0:
		dist = cross(Ax, Ay, Bx, By, Cx, Cy) / d
		dot1 = dot(Ax, Ay, Bx, By, Cx, Cy);
		if dot1 > 0:
			return distance(Bx, By, Cx, Cy)
		dot2 = dot(Bx, By, Ax, Ay, Cx, Cy)
		if dot2 > 0:
			return distance(Ax, Ay, Cx, Cy)
		return dist if dist > 0 else -dist
	else:
		return distance(Ax, Ay, Cx, Cy)
	
cpdef piede_perpendicolare(double Ax, double Ay, double Bx, double By, double Px, double Py):
	# Retta parallela all'asse x
	if Ax == Bx:
		return Ax, Py
	# Retta parallela all'asse y
	if Ay == By:
		return Px, By
	# Altri casi
	m = (By - Ay) / (Bx - Ax) # Coeff. angolare retta
	q = (Ax * By - Ay * Bx) / (Ax - Bx) 
	mp = -1 / m # Coeff. angolare perpendicolare
	norm = sqrt(1 + m * m)
	d = abs(m * Px - Py + q) / norm # Distanza punto-retta
	# Posizione di P rispetto alla retta: se k e m sono concordi, P sta "a sinistra" della retta
	# e quindi mi avvicino alla retta seguendo il versore; altrimenti devo andare
	# in verso opposto
	k = m * Px - Py + q
	kv = -1 if k * m > 0 else 1 
	# versore = (1, mp) / normp, restituisco P + d * versore:
	normp = sqrt(1 + mp * mp)
	q = (Px + kv * d / normp, Py + kv * mp * d / normp)
	return q
	
	
	
cpdef double length(points):
	pold = None
	cdef double l = 0
	for p in points:
		if pold is not None:
			l += distance(pold[0], pold[1], p[0], p[1])
		pold = p
	return l

class ArcoGeocoder(ArcoTomTom):
	id_count = 0
	tipo_archi = 16
		
	def __init__(self,
			s,
			t,
			nome,
			auto,
			velocita,
			lunghezza,
			punti,
			tipo,
			ztl,
			da_strada,
			id=None,
		):
			if id is None:
				id = ArcoGeocoder.id_count
				ArcoGeocoder.id_count += 1
			else:
				ArcoGeocoder.id_count = max(ArcoGeocoder.id_count, id) + 1				
			ArcoTomTom.__init__(
				self,
				id,
				0,
				s,
				t,
				nome,
				auto,
				velocita,
				lunghezza,
				punti,
				tipo,
				ztl,
				special_type_id=16,
			)
			self.da_strada = da_strada
			
	def serialize(self):
		res = ArcoTomTom.serialize(self)
		res['da_strada'] = self.da_strada
		return res
		
	@classmethod
	def deserialize(cls, grafo, res):
		e = ArcoGeocoder(
			grafo.nodi[res['sid']],
			grafo.nodi[res['tid']],
			res['nome'],
			res['auto'],
			res['velocita'],
			res['lunghezza'],
			res['punti'],
			res['tipo'],
			res['ztl'],
			res['da_strada'],
			id=res['id'][1],
		)
		grafo.add_arco(e)
			
	def aggiorna_contesto(self, opt, rev=False):
		if self.da_strada and opt['primo_tratto_bici']:
			if rev:
				context = self.t.get_context(opt)
			else:
				context = self.s.get_context(opt)
			if context['primo_tratto_bici']:
				context = self.duplica_contesto(opt, rev)
				context['primo_tratto_bici'] = False
			
class NodoGeocoder(NodoTomTom):
	id_count = 0
	tipo_nodi = 17
	
	def __init__(self, point, id=None):
		if id is None:
			NodoTomTom.__init__(self, NodoGeocoder.id_count, point[0], point[1], special_type_id=17)
			NodoGeocoder.id_count += 1
		else:
			NodoTomTom.__init__(self, id, point[0], point[1], special_type_id=17)
			NodoGeocoder.id_count = max(id, NodoGeocoder.id_count) + 1
		
		
	@classmethod
	def deserialize(cls, grafo, res):
		n = NodoGeocoder(
				res['x'],
				res['y'],
				id=res['id'][1],
			)
		grafo.add_nodo(n)
			

cdef struct Segment:
	double Ax, Ay, Bx, By
	long long eid1, eid2, eid3
	

cdef class SegmentRepo(object):
	cdef Segment* r
	cdef list s
	cdef long n

	def __init__(self):
		object.__init__(self)
		#self.proj = pyproj.Proj("+proj=utm +zone=33 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
		self.s = []
		
	def add_segment(self, p1, p2, ref):
		self.s.append((p1, p2, ref))
		
	def freeze(self):
		n = len(self.s)
		self.n = n
		self.r = <Segment*> malloc(n * sizeof(Segment))
		for i in range(0, n):
			s = self.s[i]
			self.r[i].Ax = s[0][0]
			self.r[i].Ay = s[0][1]
			self.r[i].Bx = s[1][0]
			self.r[i].By = s[1][1]
			if isinstance(s[2], int):
				self.r[i].eid1 = s[2]
				self.r[i].eid2 = 0
				self.r[i].eid3 = 0
			else:
				self.r[i].eid1 = s[2][0].id[1]
				self.r[i].eid2 = s[2][0].id[2]
				self.r[i].eid3 = s[2][1]
		self.s = None
			
	cpdef find_nearest_segment(self, double x, double y):
		#p = self.proj(x, y)
		cdef double min
		cdef Segment* minpoint
		cdef long i
		cdef double d
		with nogil:
			min = -1
			minpoint = NULL
			for i in range(0, self.n):
				d = segment_point_dist(
					self.r[i].Ax, self.r[i].Ay,
					self.r[i].Bx, self.r[i].By,
					x, y
				)
				if min == -1 or d < min:
					minpoint = &(self.r[i])
					min = d
		return (minpoint.eid1, minpoint.eid2, minpoint.eid3)
	
	cpdef find_nearest_segment_and_endpoints(self, double x, double y):
		#p = self.proj(x, y)
		cdef double min = -1
		cdef Segment* minpoint = NULL
		cdef long i
		cdef double d
		for i in range(0, self.n):
			d = segment_point_dist(
				self.r[i].Ax, self.r[i].Ay,
				self.r[i].Bx, self.r[i].By,
				x, y
			)
			if min == -1 or d < min:
				minpoint = &(self.r[i])
				min = d
		return (minpoint.Ax, minpoint.Ay, minpoint.Bx, minpoint.By, minpoint.eid1)
		
	

class SegmentGeocoder(object):
	def __init__(self):
		self.repo = SegmentRepo()
		self.length = []
		self.total_length = 0
		
	def add_segment(self, a, b, i):
		self.repo.add_segment(a, b, i)
		self.length.append(self.total_length)
		self.total_length += distance(a[0], a[1], b[0], b[1])
		
	def project(self, p):
		Ax, Ay, Bx, By, i = self.repo.find_nearest_segment_and_endpoints(p[0], p[1])
		p_perp = piede_perpendicolare(Ax, Ay, Bx, By, p[0], p[1])
		dist = distance(Ax, Ay, p_perp[0], p_perp[1])
		return (i, dist, dist + self.length[i])
	
	def freeze(self):
		self.repo.freeze()
		

	
class Geocoder(object):
	def __init__(self, graph, edge_type_id=12):
		object.__init__(self)
		self.edge_type_id = edge_type_id
		self.graph = graph
		self.repo = SegmentRepo()
		for eid in graph.archi:
			if edge_type_id is None or edge_type_id == eid[0]:
				e = graph.archi[eid]
				if e.auto:
					pold = e.punti[0]
					if pold != e.s.get_coordinate()[0]:
						print "s errato"
					for i in range(1, len(e.punti)):
						p = e.punti[i]
						self.repo.add_segment(pold, p, (e, i - 1))
						pold = p
					if pold != e.t.get_coordinate()[0]:
						print "t errato"				
		self.repo.freeze()
			
	def _find_nearest_edge(self, point):
		#print "Cerco"
		eid1, eid2, i = self.repo.find_nearest_segment(point[0], point[1])
		#print eid1, eid2, i
		e = self.graph.archi[(self.edge_type_id, eid1, eid2)]
		#print "Trovato arco"
		return e, i
	
	def find_nearest_edge(self, point):
		return self._find_nearest_edge(point)[0]
		
	def find_nearest_edge_and_node(self, point):
		e, i = self._find_nearest_edge(point)
		s = e.s.get_coordinate()[0]
		t = e.t.get_coordinate()[0]
		ds = distance(point[0], point[1], s[0], s[1])
		dt = distance(point[0], point[1], t[0], t[1])
		return (e, e.s) if ds < dt else (e, e.t)
	
	def connect_to_node_nogis(self, node):
		p = node.get_coordinate()[0]
		e, i = self._find_nearest_edge(p)
		#print "i=", i
		punti1 = e.punti[:i + 1]
		punti2 = e.punti[i + 1:]
		#print punti1, punti2
		if len(punti1) == 0:
			#print "Solo punti2"
			a, b = punti2[:2]
		elif len(punti2) == 0:
			#print "Solo punti1"
			a, b = punti1[-2:]
		else:
			#print "Tutto"
			a = punti1[-1]
			b = punti2[0]
		if a == b:
			print "NOOOO! Sono uguali!!!" 
		#print "Calcolo piede perpendicolare"
		p_perp = piede_perpendicolare(a[0], a[1], b[0], b[1], p[0], p[1])
		#print "Ok", p_perp
		punti1 += [p_perp, p]
		punti2 = [p, p_perp] + punti2 # [p, p_perp] +
		nome = e.get_nome()
		a1 = ArcoGeocoder(e.s, node, nome, e.auto, e.velocita, length(punti1), punti1, e.tipo, e.ztl, True)
		a1r = ArcoGeocoder(node, e.s, nome, False, e.velocita, length(punti1), list(reversed(punti1)), e.tipo, e.ztl, False)
		a2 = ArcoGeocoder(node, e.t, nome, e.auto, e.velocita, length(punti2), punti2, e.tipo, e.ztl, False)
		a2r = ArcoGeocoder(e.t, node, nome, False, e.velocita, length(punti2), list(reversed(punti2)), e.tipo, e.ztl, True)
		return (a1, a2, a1r, a2r)
	
	def connect_to_node_gis(self, node):
		try:
			p = node.get_coordinate()[0]
			point = Point(p[0], p[1], srid=3004)
			res = gis.geocode(point, StradaTomtom)
			pprint(res)
			stt = res['elem']
			
			e = self.graph.archi[(self.edge_type_id, stt.eid, stt.count)]
			parts = res['parts']
			print "%d parti" % len(parts)
			print parts
			print "Foot:", res['foot']
			parts = res['parts']
			p_perp = list(res['foot'])
			if len(parts) > 1:
				punti1 = list(parts[0])
				punti2 = list(parts[1])
			else:
				punti = list(parts[0])
				p1 = punti[0]
				p2 = punti[-1]
				if distance(p_perp[0], p_perp[1], p1[0], p1[1]) < distance(p_perp[0], p_perp[1], p2[0], p2[1]):
					punti1 = []
					punti2 = punti
				else:
					punti1 = punti
					punti2 = []
			
			punti1 += [p_perp, p]
			punti2 = [p, p_perp] + punti2 # [p, p_perp] +
			nome = e.get_nome()
			a1 = ArcoGeocoder(e.s, node, nome, e.auto, e.velocita, length(punti1), punti1, e.tipo, e.ztl, True)
			a1r = ArcoGeocoder(node, e.s, nome, False, e.velocita, length(punti1), list(reversed(punti1)), e.tipo, e.ztl, False)
			a2 = ArcoGeocoder(node, e.t, nome, e.auto, e.velocita, length(punti2), punti2, e.tipo, e.ztl, False)
			a2r = ArcoGeocoder(e.t, node, nome, False, e.velocita, length(punti2), list(reversed(punti2)), e.tipo, e.ztl, True)
			return (a1, a2, a1r, a2r)
		except Exception:
			traceback.print_exc()
			
	def connect_to_node(self, node):
		return self.connect_to_node_nogis(node)
	
		
	def connect_to_point(self, point):
		#print "Creo nodo"
		node = NodoGeocoder(point)
		#print "Connetto"
		archi = self.connect_to_node(node)
		#print "Fatto"
		return (node, archi)
		

