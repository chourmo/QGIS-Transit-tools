##[Network]=group
##GTFS_folder=folder
##Day=string 20/01/2014
##Zones=vector
##Buffer=number 300
##Hour_details=boolean False
##Step_in_minutes=number 30
##Results=output vector 

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
import datetime as dt
import csv
import os.path as os
from operator import itemgetter



def buffRect(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x-b, y-b, x+b, y+b)

def HMS(t):
	# returns time of day in minutes
	d = [int(x) for x in t.split(":")]
	if len(d) == 2: return(d[0]*60 + d[1])
	elif len(d) == 3: return(d[0]*60 + d[1] + d[2]/60.0)
	else: return 0



d_list=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
Day = [int(x) for x in Day.split("/")]
J = Day[2] * 10000 + Day[1] * 100 + Day[0]
num_j = dt.date(Day[2], Day[1], Day[0]).weekday()+1

progress.setText("Day: {0:%A}".format(dt.date(Day[2], Day[1], Day[0])))

if Hour_details: step = Step_in_minutes
else: step = 60
nillist = [0] * (24 * 60 / stepMin)


zonelayer = processing.getObject(Zones)
zoneprovider = zonelayer.dataProvider()


xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(4326), zoneprovider.crs())



Stops_file = GTFS_folder+'/stops.txt'
Trips_file = GTFS_folder+'/trips.txt'
Route_file = GTFS_folder+'/routes.txt'
Stop_times_file = GTFS_folder+'/stop_times.txt'
Cal_dates_file = GTFS_folder+'/calendar_dates.txt'
Cal_liste_file = GTFS_folder+'/calendar.txt'
Freq_file = GTFS_folder+'/frequencies.txt' 

cal_dates_exists = os.exists(Cal_dates_file)
calendar_exists = os.exists(Cal_liste_file)
freq_exists = os.exists(Freq_file)


#Calendars_list import

calendar_val = set()  #Set of valid calendars
calendar_excl = set() #Set of non valid calendars

if cal_dates_exists:
	with open(Cal_dates_file, 'rb') as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			if int(row['exception_type'])==1 and int(row['date']) == J:
				calendar_val.add(row['service_id'])
			elif row['exception_type']==2 and int(row['date'])==J:
				calendar_excl.add(row['service_id'])


#Calendars import

if calendar_exists:
	with open(Cal_liste_file, 'rb') as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			if (J == 0 or (J >= int(row['start_date'])
				and J <= int(row['end_date'])
				and int(row[d_list[num_j]]) == 1
				and (row['service_id'] not in calendar_excl))):
		   
				calendar_val.add(row['service_id'])

if len(calendar_val) == 0:
	progress.setText("No valid calendar in folder at date {0}".format(Day))

else :


	#Stops import

	stops = {}
	with open(Stops_file, 'rb') as csvfile:

		reader = csv.DictReader(csvfile)
		for row in reader:
			x = float(row['stop_lon'].replace(',', '.'))
			y = float(row['stop_lat'].replace(',', '.'))						
			stops[row['stop_id']] = xform.transform(QgsPoint(x, y))


	#Trips import

	trips = {}
	with open(Trips_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)
		for row in reader:
			if row['service_id'] in calendar_val: trips[row['trip_id']] = row['route_id']




	# If frequencies.txt exists, add a time table in minutes of the route for the whole day
	if freq_exists:

		routefq = {}
	
		with open(Freq_file, 'rb') as csvfile:
	
			for row in csv.DictReader(csvfile):
				# Calendar in date range
				if row['trip_id'] in calendar_val:  
			
					st = HMS(row["start_time"])
					end = HMS(row["end_time"])
					secs = int(row["headway_secs"]) / 60.0
					rid = trips[row['trip_id']]
				
					routefq.setdefault(rid, {'table':[], 'nodes':[]})
			
					li = range(int((end - st) / secs))
				
					routefq[rid]['table'].extend([st + secs * l for l in li])


	# Build nodes for each route

	nodes = {}       # key tuple of stop_id and route_id

	l = 0

	with open(Stop_times_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)
		for row in reader:
	
			if row['trip_id'] in trips:
		
				l += 1
			
				# create entry in dict if not exists
				rid = trips[row['trip_id']]
				dep = row['departure_time']
				key = (row['stop_id'], rid)
				nodes.setdefault(key, list(nillist))
			
				# if not frequencies based : add 1 in hour range
			
				if not freq_exists or rid not in routefq:
					H = HMS(dep)
					if H >= 1440: H = H - 1440        # H after 24:00:00				
					nodes[key][int(H / stepMin)] += 1
			
				else: routefq[rid]['nodes'].append((key, row['stop_sequence'], HMS(dep)))


	if freq_exists:
	
		for r in routefq.values():
			nlist = sorted(r['nodes'], key=itemgetter(2))
			st = nlist[0][2]
		
			for i in zip(nlist, r['table']):
				H = int((i[1] + i[0][2] - st))
				if H >= 1440: H = H - 1440       # H after 24:00:00
				nodes[i[0][0]][int(H/stepMin)] += 1


	# Index nodes

	nodes_ix = {}
	index = QgsSpatialIndex()
	featindex = QgsFeature()
	l = 0

	for n in nodes.keys():
		nodes_ix[l] = n
		featindex.setGeometry(QgsGeometry.fromPoint(stops[n[0]]))
		featindex.setFeatureId(l)
		index.insertFeature(featindex)
		l+=1

	progress.setText("{0} nodes".format(len(nodes)))
	


	step = max(1, zonelayer.featureCount() / 100
	l = 0
	fields = zoneprovider.fields()


	fields.append(QgsField("routes", QVariant.Int))
	fields.append(QgsField("freq", QVariant.Int))

	if Hour_details:
		fields.append(QgsField("start", QVariant.String))
		fields.append(QgsField("end", QVariant.String))

	else:
		fields.append(QgsField("amplitude", QVariant.String))
		fields.append(QgsField("freq_max", QVariant.Int))


	writer = VectorWriter(Results, None, fields, QGis.WKBPolygon, zoneprovider.crs())


	for feat in processing.features(zonelayer):
		if l % step == 0: progress.setPercentage(l/step)
		l+=1
	
		attrs = feat.attributes()
		geom = feat.geometry()
	
		if Buffer == 0:			# no buffer, take object only, else buffer around centroid
			near = [x for x in index.intersects(geom.boundingBox())
					if geom.contains(stops[nodes_ix[x][0]])]
		else:
			near = index.intersects(buffRect(geom.centroid().asPoint(), Buffer))
	
		if len(near) > 0:
			routeset = set()
			v_routes = v_freq = nillist[:]		
		
			for i in [nodes_ix[x] for x in near]:
				if i[1] not in routeset:
					routeset.add(i[1])
					v_freq = [x + y for x, y in zip(v_freq, nodes[i])]
					v_routes = [min(1, x) + y for x, y in zip(v_routes, nodes[i])]
		
		
			if Hour_details:
			
				# loop on index with at least 1 transit stop in range
				for i in [x for x in range(len(v_freq)) if v_freq[x] != 0]:
				
					t = i * stepMin
					attrs.append(v_routes[i])
					attrs.append(v_freq[i])
				
					attrs.append(str(dt.datetime(Day[2], Day[1], Day[0], t/60, t%60)))
				
					t1 = t + stepMin
					if t1 >= 1440: t1 = t1 - 1440
					attrs.append(str(dt.datetime(Day[2], Day[1], Day[0], t1/60, t1%60)))
				
					feat.setAttributes(attrs)
					writer.addFeature(feat)
				
			else:
				amplfr = [x for x in v_freq if x > 0]
				attrs.append(sum(v_routes))
				attrs.append(sum(v_freq))
				attrs.append(len(amplfr))
				attrs.append(max(amplfr))
			
				feat.setAttributes(attrs)
				writer.addFeature(feat)

	del writer