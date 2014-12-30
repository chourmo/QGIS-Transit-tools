##[Network]=group
##GTFS_folder=folder
##Day=string 20/01/2014
##Step_in_minutes=number 5
##Projection=number 3944
##Results=output vector 

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
import datetime as dt
import csv
import os.path as os
from operator import itemgetter
from math import sqrt



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


def pathLength(path):
	return QgsGeometry().fromPolyline(path).length()


def distOnLine(line, p):
	'''return (distance of point from start point on the shape as a list of points
	'''
	geom = QgsGeometry().fromPolyline(line)
	d, pt, v = geom.closestSegmentWithContext(p)		# square distance, pt on segment, next vertex
	
	geom = QgsGeometry().fromPolyline(line[:v+1])
	
	if v == 0: return 0.0
	else: return geom.length() - sqrt(pt.sqrDist(line[v]))




d_list=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
Day = [int(x) for x in Day.split("/")]
J = Day[2] * 10000 + Day[1] * 100 + Day[0]
num_j = dt.date(Day[2], Day[1], Day[0]).weekday()+1

progress.setText("{1} Day: {0:%A}".format(dt.date(Day[2], Day[1], Day[0]), Day))

timesteps = range(0, 1440, Step_in_minutes)


modes = {0: 'Tram',
		 1: 'Metro',
		 2: 'Train',
		 3: 'Bus',
		 4: 'Boat',
		 5: 'Cable-Car',
		 6: 'Telepherique',
		 7: 'Funicular'}

crs_out = QgsCoordinateReferenceSystem(Projection)
xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(4326), crs_out)


Agency_file = GTFS_folder+'/agency.txt'
Stops_file = GTFS_folder+'/stops.txt'
Trips_file = GTFS_folder+'/trips.txt'
Route_file = GTFS_folder+'/routes.txt'
Stop_times_file = GTFS_folder+'/stop_times.txt'
Cal_dates_file = GTFS_folder+'/calendar_dates.txt'
Cal_liste_file = GTFS_folder+'/calendar.txt'
Freq_file = GTFS_folder+'/frequencies.txt'
Shape_file = GTFS_folder+'/shapes.txt'

cal_dates_exists = os.exists(Cal_dates_file)
calendar_exists = os.exists(Cal_liste_file)
freq_exists = os.exists(Freq_file)


progress.setText("Parse calendars...")
progress.setPercentage(20)


#Calendars_list import

c_valid = set()  #Set of valid calendars
c_excl = set() #Set of non valid calendars

if cal_dates_exists:
	with open(Cal_dates_file, 'rb') as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			if int(row['exception_type'])==1 and int(row['date']) == J:
				c_valid.add(row['service_id'])
			elif row['exception_type']==2 and int(row['date'])==J:
				c_excl.add(row['service_id'])


#Calendars import

if calendar_exists:
	with open(Cal_liste_file, 'rb') as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			if (J == 0 or (J >= int(row['start_date'])
				and J <= int(row['end_date'])
				and int(row[d_list[num_j]]) == 1
				and (row['service_id'] not in c_excl))):
		   
				c_valid.add(row['service_id'])

if len(c_valid) == 0:
	progress.setText("No valid calendar in folder at date {0}".format(Day))

else :

	progress.setText("Parse stops, agencies...")
	progress.setPercentage(40)


	#Stops import

	stops = {}
	with open(Stops_file, 'rb') as csvfile:

		reader = csv.DictReader(csvfile)
		for row in reader:
			x = float(row['stop_lon'].replace(',', '.'))
			y = float(row['stop_lat'].replace(',', '.'))						
			
			P = QgsPoint(x, y)
			if Projection != 4326: P = xform.transform(P)

			stops[row['stop_id']] = P


	#Agency import

	with open(Agency_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)
		Agency = {r['agency_id']:r['agency_name'] for r in reader}


	progress.setText("Parse shapes...")
	progress.setPercentage(60)

	#Shapes import
	
	shapes = {}

	with open(Shape_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)

		for row in reader:
			shapes.setdefault(int(row['shape_id']), [])
			pt =  xform.transform(QgsPoint(float(row['shape_pt_lon']),
										   float(row['shape_pt_lat'])))
			shapes[int(row['shape_id'])].append((int(row['shape_pt_sequence']), pt))


	
	# Sort Shapes by pt sequence and only keep points
	
	for k in shapes.keys():
		shapes[k].sort(key=itemgetter(0))
		shapes[k] = [y for x,y in shapes[k]]


	progress.setText("Parse trips and routes...")
	progress.setPercentage(80)
	

	#Trips import

	with open(Trips_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)
		trips = {int(r['trip_id']):{'rid':int(r['route_id']), 'shape':int(r['shape_id'])}
				 for r in reader if r['service_id'] in c_valid}


	
	# Routes import
	with open(Route_file, 'rb') as csvfile:
	
		reader = csv.DictReader(csvfile)
		
		routes = {}
		
		for r in reader:
			rid = int(r['route_id'])
			routes[rid] = {'agency':Agency[r['agency_id']], 'type':r['route_type']}
			if r['route_short_name'] == '': routes[rid]['name'] = r['route_short_name']
			else: routes[rid]['name'] = r['route_long_name']
		
	


	# If frequencies.txt exists, add a time table in minutes of the route for the whole day
	'''if freq_exists:

		routefq = {}
	
		with open(Freq_file, 'rb') as csvfile:
	
			for row in csv.DictReader(csvfile):
				# Calendar in date range
				if row['trip_id'] in c_valid:  
			
					st = HMS(row["start_time"])
					end = HMS(row["end_time"])
					secs = int(row["headway_secs"]) / 60.0
					rid = trips[row['trip_id']]
				
					routefq.setdefault(rid, {'table':[], 'nodes':[]})
			
					li = range(int((end - st) / secs))
				
					routefq[rid]['table'].extend([st + secs * l for l in li])'''


	progress.setText("Done...")
	progress.setPercentage(0)



	# prepare results file

	fields = [QgsField("agency", QVariant.String),
			  QgsField("route", QVariant.String),
			  QgsField("type", QVariant.String),
			  QgsField("time", QVariant.String)]
	
	writer = VectorWriter(Results, None, fields, QGis.WKBPoint, crs_out)
	feat = QgsFeature()

	tripset = set(trips.keys())
	ctrips = set()
	step = max(1, len(trips.keys()) / 100)
	neg = savpts = 0

	with open(Stop_times_file, 'rb') as csvfile:
	
		prevstop = (None, None)
	
		for r in csv.DictReader(csvfile):
			
			l = len(ctrips)
			if l % step == 0: progress.setPercentage(l/step)
			
			tid = int(r['trip_id'])
			ctrips.add(tid)
			
			if tid in tripset:
				rid = trips[tid]['rid']
				shp = shapes[trips[tid]['shape']]
				sid = r['stop_id']
				arr = HMS(r['arrival_time'])
			
				geom = QgsGeometry.fromPolyline(shp)
				shplength = pathLength(shp)

			
			
				if prevstop == (tid, int(r['stop_sequence']) - 1):
				
					dist = distOnLine(shp, stops[sid])
				
					if (arr - prevtime) == 0: slope = 0
					else: slope = (dist - prevdist) / (arr - prevtime)
								
					for t in [x for x in timesteps if prevtime <= x < arr]:
					
						attrs = [routes[rid]['agency'],
								 routes[rid]['name'],
								 modes[int(routes[rid]['type'])],
								 str(dt.datetime(Day[2], Day[1], Day[0], t / 60, t % 60))]
						
						feat.setAttributes(attrs)

						pDist = prevdist + (t - prevtime) * slope
						
						if pDist < 0:
							neg += 1
							progress.setText('distance negative')
						
						geom2 = geom.interpolate(pDist)
						if geom2 == None: progress.setText('geom none')
						elif geom2.isMultipart(): progress.setText('geom multipart')
						
						feat.setGeometry(geom2)
						writer.addFeature(feat)
						
						savpts += 1


				prevstop = (tid, int(r['stop_sequence']))
				prevpt = sid
				prevtime = HMS(r['departure_time'])
				prevdist = distOnLine(shp, stops[sid])

	progress.setText('{0} negative nodes, not saved'.format(nef/(neg+savpts)))

	'''if freq_exists:
	
		for r in routefq.values():
			nlist = sorted(r['nodes'], key=itemgetter(2))
			st = nlist[0][2]
		
			for i in zip(nlist, r['table']):
				H = int((i[1] + i[0][2] - st))
				if H >= 1440: H = H - 1440       # H after 24:00:00
				nodes[i[0][0]][int(H/stepMin)] += 1'''


	del writer