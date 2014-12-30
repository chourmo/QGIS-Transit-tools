##[Network]=group
##GTFS_folder=folder
##Use_Reference_shapes=boolean Yes
##Reference_shapes=vector
##Mode=field Reference_shapes
##Reference_Buffer=number 50
##Use_Roads_for_Bus=boolean No
##Roads=vector
##Road_cost=field Roads
##Minimum_road_distance=number 1000
##Use_Rails=boolean No
##Rails=vector
##Rail_cost=field Rails
##Road_and_rail_buffer=number 100
##Results=output vector



import csv, codecs, cStringIO
import os

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import *
from operator import itemgetter
from qgis.networkanalysis import *
from math import sqrt 




# class to import text as unicode
class UTF8Recoder:
    """
    Iterator that reads an encoded stream and reencodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)
 
    def __iter__(self):
        return self
 
    def next(self):
        return self.reader.next().encode("utf-8")
 
class UnicodeDictReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """
 
    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)
        self.header = self.reader.next()
 
    def next(self):
        row = self.reader.next()
        vals = [unicode(s, "utf-8") for s in row]
        return dict((self.header[x], vals[x]) for x in range(len(self.header)))
 
    def __iter__(self):
        return self


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([unicode(s).encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class UnicodeDictWriter(csv.DictWriter, object):
    def __init__(self, f, fieldnames, restval="", extrasaction="raise",
                 dialect="excel", *args, **kwds):
        super(UnicodeDictWriter, self).__init__(f, fieldnames, restval="",
        										extrasaction="raise",
        										dialect="excel", *args, **kwds)
        self.writer = UnicodeWriter(f, dialect, **kwds)


def indexLine(index, i, line):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPolyline(line))
	return index.insertFeature(f)




def rectBuff(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)




def mergeLines(lines):

	''' merge list of list of points in the right order'''
	
	res = []
	
	if len(lines) == 0: return None
	elif len(lines) == 1: return lines[0]
	else:
		# shortest distance from end point of first segment to next
		end = min(lines[0][-1].sqrDist(lines[1][0]), lines[0][-1].sqrDist(lines[1][-1]))

		# shortest distance from first point of first segment to next		
		first = min(lines[0][0].sqrDist(lines[1][0]), lines[0][0].sqrDist(lines[1][-1]))
	
		if end > first: res = [x for x in lines[0][::-1]]
		else: res = [x for x in lines[0]]
		
		for l in lines[1:]:
			if res[-1].sqrDist(l[0]) < res[-1].sqrDist(l[-1]):
				res.extend([x for x in l[1:][:]])
			else:
				res.extend([x for x in l[::-1][1:]])
		return res




def cutLine(line, p1, p2 = None):
	''' lines: list of points
		p1, p2: points on line, p2 is optional		
		return tuple of lists of QgsPoint in the same direction than p1-p2'''	
	
	# test if pt1 > pt2 is in the same direction than line
	if p2 != None and p1.sqrDist(line[0]) > p2.sqrDist(line[0]): line = line[::-1]

	
	geom = QgsGeometry().fromPolyline(line)

	# insert fist point
	dist, pt, v1 = geom.closestSegmentWithContext(p1)
	
	if v1 != 0: geom.insertVertex(pt.x(), pt.y(), v1)


	if p2 == None:		
		path = geom.asPolyline()
		return (path[:v1], path[v1:])


	# insert second point	
	dist, pt, v2 = geom.closestSegmentWithContext(p2)
	geom.insertVertex(pt.x(), pt.y(), v2)
	path = geom.asPolyline()	
	
	return (path[:v1], path[v1: v2], path[v2:])



def distPathPt(path, pt):
	
	geoPath = QgsGeometry().fromPolyline(path)
	geoPt = QgsGeometry().fromPoint(pt)
	return geoPath.distance(geoPt)
	
	
	
def pathLength(path):
	if len(path) == 0: return 0
	else: return QgsGeometry().fromPolyline(path).length()



def arcsOnGraph(G, st, end):
		
	(tree, cost) = QgsGraphAnalyzer.dijkstra(G, st, 0)
			
	if tree[end] == -1: return None
	else:
		path = []
		
		while end != st:						
			path.append(tree[end])
			end = G.arc(tree[end]).outVertex()
		return path[::-1]



def arcsInBuff(pt, buf, ix, arcs):
	
	near = ix.intersects(rectBuff(pt, buf))
		
	if len(near) == 0: return None
	else:
		prox = [(distPathPt(arcs[x]['path'], pt), x) for x in near]
		prox.sort(key=itemgetter(0))
		prox = [x[1] for x in prox if x[0] <= buf]
		if len(prox) == 0: return None
		else: return prox[:]



def addFeat(path, tid, mid, txt):

	feat = QgsFeature()
	feat.setAttributes([str(tid), mid, txt])
	feat.setGeometry(QgsGeometry().fromPolyline(path))
	Fwriter.addFeature(feat)






# ------- Start of algorithm

sDist = Minimum_road_distance * Minimum_road_distance
sBuf = Reference_Buffer * Reference_Buffer
buffer = Road_and_rail_buffer
debug = False
connect = False


# chek if required files exist in folder and no shapes files
dir = os.listdir(GTFS_folder)
if 'stops.txt' not in dir or 'trips.txt' not in dir or 'stop_times.txt' not in dir:
	progress.setText("{0} is not a valid GTFS folder".format(d))


progress.setText("Parse stops...")
progress.setPercentage(20)

# parse stop file for coordinates

stops = {}

with open(GTFS_folder + '/stops.txt', 'rb') as csvfile:

	for row in csv.DictReader(csvfile):
		x = float(row['stop_lon'].replace(',', '.'))
		y = float(row['stop_lat'].replace(',', '.'))						
		stops[row['stop_id']] = QgsPoint(x, y)


# parse stop_times, append stop_time (order, pt) in trip      

progress.setText("Parse stop times...")

progress.setPercentage(40)

trips = {}

with open(GTFS_folder + '/stop_times.txt', 'rb') as csvfile:

	for row in csv.DictReader(csvfile):
		trips.setdefault(row['trip_id'], [])
		trips[row['trip_id']].append((int(row['stop_sequence']), row['stop_id']))


# order trips seq of stops in place by sequence number, skip it and store as tuple

keys = trips.keys()

for i in range(len(keys)):	
	trips[keys[i]] = tuple([x[1] for x in sorted(trips[keys[i]], key=itemgetter(0))])



# find route type

progress.setText("Parse routes...")
progress.setPercentage(60)

with open(GTFS_folder + '/routes.txt', 'rb') as csvfile:

	routes = {row["route_id"]: [int(row["route_type"]), row["route_short_name"]]
			  for row in csv.DictReader(csvfile)}




# parse trips, find duplicates (same route_id and stops sequence) and create shapes dict
# replace trips value by shape key

progress.setText("Parse trips...")
progress.setPercentage(80)


with open(GTFS_folder + '/trips.txt', 'rb') as csvfile:

	reader = csv.DictReader(csvfile)
	tripHeader = reader.fieldnames

	uniqTrips = {(r['route_id'], trips[r['trip_id']]):r['trip_id'] for r in reader}

progress.setPercentage(100)



shpLayer = processing.getObject(Reference_shapes)


# make coordinate transform objects from and to the shapes CRS

crs_out = shpLayer.dataProvider().crs()
xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(4326), crs_out)
xinv = QgsCoordinateTransform(crs_out, QgsCoordinateReferenceSystem(4326))


# import and index reference shapes
if Use_Reference_shapes:

	progress.setText("Index shapes...")

	# shape indexes, one per mode

	shpIX = {i:None for i in range(7)}			# key : route type in GTFS
	shapepts = {}

	step = max(1, shpLayer.dataProvider().featureCount() / 100)
	l = 0

	for feat in processing.features(shpLayer):
		if l % step == 0: progress.setPercentage(l/step)
		l+=1
	
		if shpIX[feat[Mode]] == None: shpIX[feat[Mode]] = QgsSpatialIndex()
		shpIX[feat[Mode]].insertFeature(feat)
	
		shapepts[feat.id()] = feat.geometry().asPolyline()


# key: GTFS mode, 2 for rail, 3 for buses
G = {2:QgsGraph(), 3:QgsGraph()}
iX = {2: QgsSpatialIndex(), 3:QgsSpatialIndex()}
Arcs = {2:{}, 3:{}}

gparam = [{'bool': Use_Rails, 'ix':2,'txt':"Build rail graph...",
		  'layer': Rails, 'cost': Rail_cost},
		  {'bool': Use_Roads_for_Bus, 'ix':3, 'txt':"Build road graph...",
		  'layer': Roads,'cost': Road_cost}]


for p in [x for x in gparam if x['bool']]:
	progress.setText(p['txt'])

	layer = processing.getObject(p['layer'])
	step = max(1, layer.dataProvider().featureCount() / 100)

	Nodes = {}
	revNode = {}
	arcl = []
	l = 0

	for feat in processing.features(layer):
		if l % step == 0: progress.setPercentage(l/step)
		l+=1
	
		if feat["dir"] != 0:
			n_beg, n_end = feat["from"], feat["to"]
			geom = feat.geometry()

			Nodes[n_beg] = geom.vertexAt(0)        
			if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
			Nodes[n_end] = geom.vertexAt(len(geom.asPolyline())-1)
		
			arcl.append((n_beg, n_end, [feat[p['cost']]], geom.asPolyline(), feat["dir"], str(feat['id_AGAM'])))


	# Create graph vertex and arcs, only index arcs in one direction

	for k in Nodes:
		Nodes[k] = G[p['ix']].addVertex(Nodes[k])
		revNode[Nodes[k]] = k
		
	for (beg, end, c, pts, dir, name) in arcl:	
		if dir == 1 or dir == 2:
			n = G[p['ix']].addArc(Nodes[beg], Nodes[end], c)
			Arcs[p['ix']][n] = {'path':pts[:], 'n':name+' fwd', 'l':pathLength(pts)}
			indexLine(iX[p['ix']], n, pts)			
			
		if dir == -1 or dir == 2:
			n = G[p['ix']].addArc(Nodes[end], Nodes[beg], c)
			Arcs[p['ix']][n] = {'path':pts[::-1], 'n':name+' back', 'l':pathLength(pts)}
			if dir == -1: indexLine(iX[p['ix']], n, pts[::-1])
		


progress.setText("Analysing trips and saving shapes...")


feat = QgsFeature()
resL = [QgsField("tripid", QVariant.String),
		QgsField("mode", QVariant.Int)]

if debug: resL.append(QgsField("creation", QVariant.String))

Fwriter = VectorWriter(Results, None, resL, QGis.WKBLineString, crs_out) 

shpHeader = ['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence',
			 'shape_dist_traveled']
			 
writer = UnicodeDictWriter(open(GTFS_folder + '/shapes.txt', 'wb'), shpHeader)
writer.writeheader()

row = {x:'' for x in shpHeader}




step = max(1, len(uniqTrips.keys()) / 100)
l = 0

for k,tid in uniqTrips.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1

	rid, seq = k[0], list(k[1])
	mid = routes[rid][0]
		
	# default value of shape is the point sequence, in result CRS
	shape = []
	
	# find all shape in Reference_Buffer of each stop if spatial index of mode exists	
	if Use_Reference_shapes and shpIX[mid] != None:
				
		buff_shp = []
				
		for p in seq:
			xy = xform.transform(stops[p])
			temp = []			
			near = shpIX[mid].intersects(rectBuff(xy, Reference_Buffer * 1.2))
			
			for g in near:
				geom = QgsGeometry().fromPolyline(shapepts[g])
								
				if geom.closestSegmentWithContext(xy)[0] < sDist: temp.append(g)
			
			buff_shp.append(set(temp))
		
		if sum([sum(list(x)) for x in buff_shp]) > 0:
		
			# make list of common shapes, in the sequence order [(start ix, end ix, shape),...]
		
			commons = [[0, 1, buff_shp[0]]]
		
			for i in range(1, len(buff_shp)):
					
				if len(buff_shp[i] & commons[-1][2]) > 0:
					commons[-1][1] = i
					commons[-1][2] = buff_shp[i] & commons[-1][2]
			
				elif len(buff_shp[i] & buff_shp[i-1]) > 0:
					commons.append([i-1, i, buff_shp[i] & buff_shp[i-1]])
			
				else: commons.append([i, i, buff_shp[i]])
		
		if len(commons) == 1 and len(list(commons[0][2])) > 0:  	# one shape found
			shape = shapepts[list(commons[0][2])[0]]
			if debug: addFeat(shapepts[list(commons[0][2])[0]], tid, mid, 'reference shape')
			
	
	
	# try to find a path on graph

	if len(shape) == 0 and ((Use_Roads_for_Bus and mid == 3) or (Use_Rails and mid == 2)):
				
		p0 = seq[0]
		xy0 = xform.transform(stops[p0])
		
		shape.append(xy0)
				
		for p in seq[1:]:
			
			xy = xform.transform(stops[p])
						
			if mid == 3 and xy0.sqrDist(xy) < sDist:
				shape.append(xy)
				if debug: addFeat(shape[-2:], tid, mid, '{0}: short arc'.format(seq.index(p)))
			
			else:
			
				stix = arcsInBuff(xy0, buffer, iX[mid], Arcs[mid])
				endix = arcsInBuff(xy, buffer, iX[mid], Arcs[mid])
								
				if stix == None or endix == None:
					shape.append(xy)
					if debug and not connect: addFeat(shape[-2:], tid, mid, '{0}: no arc in buffer'.format(seq.index(p)))
				

				# one common arc
				elif len(set(stix) & set(endix)) == 1:
					
					a = Arcs[mid][list(set(stix) & set(endix))[0]]					
					(a0, a1, a2) = cutLine(a['path'], xy0, xy)
					
					if len(a1) == 1:
						shape.append(xy)
						if debug and not connect: addFeat(shape[-2:], tid, mid, '{0}: same shape arc {1} st=end'.format(seq.index(p), a['n']))
					else:						
						shape.extend(a1)
						if debug and not connect: addFeat(a1, tid, mid, '{0}: same shape arc {1}'.format(seq.index(p), a['n']))
							
										
				else:
				
					# only keep closest arc in stix and endix
					stix = stix[0]
					endix = endix[0]
				
					# create new nodes and arcs around start point			
					stArc = Arcs[mid][stix]
					
					# cut start and end arc
					(a0, a1) = cutLine(stArc['path'], xy0)				
											
					# start xy close of start or end of path
					if xy0.sqrDist(stArc['path'][0]) < sBuf or len(a0) < 2:
						start = G[mid].arc(stix).outVertex()
						sttype = ' start : debut {0}'.format(stArc['n'])
						
					elif xy0.sqrDist(stArc['path'][-1]) < sBuf or len(a1) < 2:
						start = G[mid].arc(stix).inVertex()
						sttype = ' start: fin {0}'.format(stArc['n'])
											
					# else create new node and arcs
					else:						
						sttype = ' new start {0}'.format(stArc['n'])
						start = G[mid].addVertex(xy0)
						
						c = G[mid].arc(stix).property(0) / stArc['l']
						c0 = c * pathLength(a0)
						c1 = c * pathLength(a1)
			
						n = G[mid].addArc(start, G[mid].arc(stix).outVertex(), [c0])
						Arcs[mid][n] = {'path':a0[::-1], 'n':'n'}
						
						n = G[mid].addArc(start, G[mid].arc(stix).inVertex(), [c1])
						Arcs[mid][n] = {'path':a1[:], 'n':'n'}

						if connect: addFeat(a0[::-1], tid, mid, '{0}: start > deb {1}'.format(seq.index(p), revNode[G[mid].arc(stix).outVertex()]))
						if connect: addFeat(a1, tid, mid, '{0}: start > fin {1}'.format(seq.index(p), revNode[G[mid].arc(stix).inVertex()]))
				

					endArc = Arcs[mid][endix]
					(a0, a1) = cutLine(endArc['path'], xy)

					if xy.sqrDist(endArc['path'][0]) < sBuf or len(a0) < 2:
						end = G[mid].arc(endix).outVertex()
						endtype = ' - end : debut {0}'.format(endArc['n'])
						
					elif xy.sqrDist(endArc['path'][-1]) < sBuf or len(a1) < 2:
						end = G[mid].arc(endix).inVertex()
						endtype = ' - end : fin {0}'.format(endArc['n'])
					
					# else create new node and arcs
					else:
						
						endtype = ' - new end {0}'.format(endArc['n'])	
					
						end = G[mid].addVertex(xy)

						c = G[mid].arc(endix).property(0) / endArc['l']
						c0 = c * pathLength(a0)
						c1 = c * pathLength(a1)
					
						n = G[mid].addArc(G[mid].arc(endix).outVertex(), end, [c0])
						Arcs[mid][n] = {'path':a0[:], 'n':'n'}

						n = G[mid].addArc(G[mid].arc(endix).inVertex(), end, [c1])
						Arcs[mid][n] = {'path':a1[::-1], 'n':'n'}
						
						if connect: addFeat(a0[:], tid, mid, '{0}: deb {1} > end'.format(seq.index(p), revNode[G[mid].arc(endix).outVertex()]))
						if connect: addFeat(a1[::-1], tid, mid, '{0}: fin {1} > end'.format(seq.index(p), revNode[G[mid].arc(endix).inVertex()]))
					
					
					path = arcsOnGraph(G[mid], start, end)
										
					if path == None:
						shape.append(xy)  				  	  # path not found
						if debug and not connect: addFeat(shape[-2:], tid, mid, 'shape on graph not found' + sttype + endtype)
					else:
						shape.extend(mergeLines([Arcs[mid][x]['path'] for x in path]))
						if debug and not connect:
							if len(mergeLines([Arcs[mid][x]['path'] for x in path])) < 2:
								addFeat(shape[-2:], tid, mid, '{0}: shape on graph - one point'.format(seq.index(p)) + sttype + endtype)
							else:
								addFeat(mergeLines([Arcs[mid][x]['path'] for x in path]), tid, mid, '{0}: shape on graph'.format(seq.index(p)) + sttype + '-'.join([Arcs[mid][x]['n'] for x in path]) + endtype)
						
			p0, xy0 = p, xy
				


	# if no shape found before, use point sequence, in final CRS
	if len(shape) < 2:
		shape = [xform.transform(stops[x]) for x in seq]
		if debug: addFeat([xform.transform(stops[x]) for x in seq], tid, mid, 'shape < 2')
	
	# save in shape.txt and result shapefile	
	for i in range(len(shape)):
		
		pt = xinv.transform(shape[i])
		row['shape_id'] = l
		row['shape_pt_lon'] = pt.x()
		row['shape_pt_lat'] = pt.y()
		row['shape_pt_sequence'] = i
		
		writer.writerow(row)
	
	if not debug:
		feat.setAttributes([str(tid), mid])
		feat.setGeometry(QgsGeometry().fromPolyline(shape))
		Fwriter.addFeature(feat)


	# replace tid value by the shape index
	uniqTrips[k] = l


del Fwriter




progress.setText("Update trips.txt file...")


writer = UnicodeDictWriter(open(GTFS_folder + '/trips2.txt', 'wb'), tripHeader)
writer.writeheader()

with open(GTFS_folder + '/trips.txt') as csvfile:
	for row in UnicodeDictReader(csvfile):
		
		row['shape_id'] = uniqTrips[(row["route_id"], trips[row["trip_id"]])]
		writer.writerow(row)

os.rename(GTFS_folder + '/trips2.txt', GTFS_folder + '/trips.txt')
		
del writer