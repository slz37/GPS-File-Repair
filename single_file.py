import fitparse, gpxpy                        #Parsing files
from math import sin, cos, atan2, sqrt, pi    #Calculating haversine distance
from numpy import random                      #Add noise to pace
from osgeo import gdal                        #Parse elevation profiles
import matplotlib.pyplot as plt               #Plotting
from datetime import datetime                 #Timing
import sys

'''
Repairing a single file with damaged GPS segments.
'''

def convert_time(t):
    '''
    Converts the given time to the appropriate format
    to write to .gpx files.
    '''

    #Convert seconds to full time
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    microsecs = int(((t % 60) - seconds) * 1E6)

    #Different dates for hours > 24
    if hours >= 24:
        hours = hours % 24
        temp_date = DATE[:-1] + str(int(DATE[-1]) + 1)
        
        full_time = temp_date + " {:02d}:{:02d}:{:02d}.{:06d}".format(hours, minutes, seconds, microsecs)
    else:
        full_time = DATE + " {:02d}:{:02d}:{:02d}.{:06d}".format(hours, minutes, seconds, microsecs)

    #Convert to datetime
    dt = datetime.strptime(full_time, "%Y-%m-%d %H:%M:%S.%f")

    return dt

def semi_to_degree(pos):
    '''
    Converts longitude/latitude in semicircles
    to units of degrees.
    '''

    return pos * 180 / 2**31

def distance(lat, long):
    '''
    Calculates the distance between two pairs of
    long/lat points using the Haversine formula.
    '''

    #Formula variables
    psi1 = lat[0] * TO_RADIANS
    psi2 = lat[1] * TO_RADIANS
    del_psi = (lat[1] - lat[0]) * TO_RADIANS
    del_lamb = (long[1] - long[0]) * TO_RADIANS

    a = sin(del_psi / 2)**2 + cos(psi1) * cos(psi2) * sin(del_lamb / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

def load_elevation(final_lat, final_long):
    '''
    Calculates the elevation at a given lat/long
    point using 3DEP data.
    '''

    #Open 3DEP data downloaded from https://www.usgs.gov/core-science-systems/ngp/3dep
    file_convention = "ned19_n40x00_w075x25_pa_northeast_2010"

    #Grab elevation data
    geo_ele = gdal.Open("data\\" + file_convention + "\\" + file_convention + "_thumb.jpg")
    arr_ele = geo_ele.ReadAsArray() + 44 #Offset by about 44 for some reason

    #Grab correspond lat, long data
    geo_coords = gdal.Open("data\\" + file_convention + "\\" + file_convention + ".img")
    arr_coords = geo_coords.ReadAsArray()

    #Calculate extent to scale image
    nrows, ncols = arr_coords.shape
    x0, dx, dxdy, y0, dydx, dy = geo_coords.GetGeoTransform()
    x1 = x0 + dx * ncols
    y1 = y0 + dy * nrows

    #Grab elevation for the new route
    elevation = []
    for i in range(len(final_long)):
        long = final_long[i]
        lat = final_lat[i]

        #Since resolution is not 1 pixel, len(arr_ele) < len(long)
        #So, scale indices of long/lat to fit size of arr_ele
        long_index = (long - x0) / ((x1 - x0) / 300)
        lat_index = (y0 - lat) / ((y0 - y1) / 385)
        ele = arr_ele[int(lat_index)][int(long_index)]

        elevation.append(ele)

    #Plot elevation profile
    if PLOT:
        plt.imshow(arr_ele, cmap = "inferno", extent = [x0, x1, y1, y0])
        plt.plot(final_long, final_lat, c = "m")
        plt.scatter(good_long, good_lat, c = "b")
        plt.scatter(route_long, route_lat, c = "tab:olive")
        plt.scatter(bad_long, bad_lat, c = "r")
        plt.legend(["Final Route", "Good Segment", "Fixed Segment", "Bad Segment"])
        plt.tick_params(
            axis = "both",
            which = "both",
            bottom = False,
            top = False,
            right = False,
            left = False,
            labelleft = False,
            labelbottom = False)
        plt.show()

    return elevation

def parse_fit(file):
    '''
    Parses the data from a fitparse.FitFile for the
    longitude, latitude, and time between polls.
    '''

    lat = []
    long = []
    time = []
    vel = []
    anom_time = []

    #Each time data is polled by watch, it is stored as a record.
    #Grab the longitude, latitude, and time for each record.
    for record in file.get_messages("record"):
        #Skip weird GPS issues
        if record.get_value("position_lat"):
            #Units of semicircles for lat and long
            lat.append(semi_to_degree(record.get_value("position_lat")))
            long.append(semi_to_degree(record.get_value("position_long")))

            #Current velocity
            vel.append(record.get_value("enhanced_speed"))
        
            #(year, month, day, hour, min, sec)
            current_time = record.get_value("timestamp")
            time_in_sec = current_time.hour * 3600 + current_time.minute * 60 + current_time.second

            #Prevent loop-around at 24:00 mark
            if time:
                if time_in_sec - time[-1] < 0:
                    time_in_sec += 24 * 3600
            
            time.append(time_in_sec)
        else:
            #Anomalous time where no lat/long coords
            current_time = record.get_value("timestamp")
            anom_time.append(current_time.hour * 3600 + current_time.minute * 60 + current_time.second)

    if anom_time:
        return lat, long, [time, anom_time], vel
    else:
        return lat, long, time, vel

def parse_gpx(file):
    '''
    Parses the data from a gpxpy.gpx for the
    longitude and latitude between polls.
    '''

    lat = []
    long = []
    gpx_route = file.routes[0]

    #Grab lat, long
    for point in gpx_route.points:
        lat.append(point.latitude)
        long.append(point.longitude)    

    return lat, long

#Constants
R = 6371E3
TO_RADIANS = pi / 180
TO_MILES = 1 / 1609.34
TO_MINUTES = 1 / 60
PLOT = False

#Interval in seconds containing bad segment
#0 for start of file, -1 for end of file
start_bad = 1922
end_bad = -1

#Load our .fit files
file = fitparse.FitFile("3954847400.FIT")    #GPS File
route = gpxpy.parse(open("route_2.gpx", "r"))  #Actual route - made on gmap-pedometer

#Get date
for record in file.get_messages("record"):
    d = record.get_value("timestamp")
    DATE = "{}-{:02d}-{:02d}".format(d.year, d.month, d.day)
    break

#Parse
lat, long, time, vel = parse_fit(file)
route_lat, route_long = parse_gpx(route)

#Remove duplicate points in route
indices = []
for i in range(len(route_lat) - 1):
    if (route_lat[i] == route_lat[i + 1]) and (route_long[i] == route_long[i + 1]):
        indices.append(i)
for i in indices:
    del route_lat[i]
    del route_long[i]

#Find starting and ending indices if not 0 and -1
if start_bad != 0:
    start_bad = time.index(time[0] + start_bad) - 1
if end_bad != -1:
    end_bad = time.index(time[0] + end_bad)

#Split into good and bad segments
if start_bad == 0:
    #Bad segment is at start of run
    good_lat = lat[end_bad:]
    good_long = long[end_bad:]
    good_time = time[end_bad:]
    good_vel = vel[end_bad:]

    bad_lat = lat[start_bad:end_bad]
    bad_long = long[start_bad:end_bad]
    bad_time = time[start_bad:end_bad]
    bad_vel = vel[start_bad:end_bad]

    #Set ending point of route to starting point of good file
    route_lat[-1] = good_lat[0]
    route_long[-1] = good_long[0]
elif end_bad == -1:
    #Bad segment is at end of run
    good_lat = lat[0:start_bad]
    good_long = long[0:start_bad]
    good_time = time[0:start_bad]
    good_vel = vel[0:start_bad]

    bad_lat = lat[start_bad:]
    bad_long = long[start_bad:]
    bad_time = time[start_bad:]
    bad_vel = vel[start_bad:]

    #Set starting point of route to ending point of good file
    #route_lat[0] = good_lat[-1]
    #route_long[0] = good_long[-1]
else:
    #Bad segment splits run in half
    good_lat = lat[0:start_bad] + lat[end_bad:]
    good_long = long[0:start_bad] + long[end_bad:]
    good_time = time[0:start_bad] + time[end_bad:]
    good_vel = vel[0:start_bad] + vel[end_bad:]

    bad_lat = lat[start_bad:end_bad]
    bad_long = long[start_bad:end_bad]
    bad_time = time[start_bad:end_bad]
    bad_vel = vel[start_bad:end_bad]

    #Set starting/ending point of route to ending/starting point of good file
    route_lat[0] = lat[start_bad - 1]
    route_long[0] = long[start_bad - 1]
    route_lat[-1] = lat[end_bad]
    route_long[-1] = long[end_bad]

#Calculate the total bad time - still inaccurate
'''
del_velocity = []
for i in range(len(bad_lat)-1):
    d = distance([bad_lat[i], bad_lat[i + 1]], [bad_long[i], bad_long[i + 1]])
    t = bad_time[i + 1] - bad_time[i]
    del_velocity.append(d / t)
'''

bad_time_tot = 0
for i in range(1, len(bad_time)):
    prev_time = bad_time[i - 1]

    if bad_vel[i - 1] > 3.13:
        bad_time_tot += bad_time[i] - prev_time
#print(bad_time_tot // 60, (bad_time_tot / 60) % (bad_time_tot // 60) * 60)

#Now calculate the real total distance of the route
route_distance = 0
for i in range(1, len(route_lat) - 1):
    #Calculate angle of points
    x0 = route_long[i]
    x1 = route_long[i + 1]
    y0 = route_lat[i]
    y1 = route_lat[i + 1]
    theta = atan2(y1 - y0, x1 - x0)

    #Convert to [0, 2pi] and scale to [0, pi/2]
    if theta < 0:
        theta += 2 * pi
    theta = theta % (pi / 2)
    percent = theta / (pi / 2)
    
    '''
    Add noise to coordinates - add noise mostly in direction normal to velocity vector
    Don't want to add noise to start/end points
    Mess around with amplitude of noise - not sure what best value is
    '''
    route_lat[i] = route_lat[i] + random.normal(0, 2E-5) * (1 - percent)
    route_long[i] = route_long[i] + random.normal(0, 2E-5) * percent
    
    route_distance += distance([route_lat[i], route_lat[i+1]],
                               [route_long[i], route_long[i+1]]) * TO_MILES

#Calculate the average pace of the new route
tot_pace = (bad_time_tot * TO_MINUTES) / route_distance

#Calculate route times to match avg pace with some noise
route_time = [bad_time[0]]
for i in range(len(route_lat) - 1):
    current_pace = tot_pace + random.normal(0, 0.2)
    current_distance = distance([route_lat[i], route_lat[i + 1]],
                                [route_long[i], route_long[i + 1]]) * TO_MILES
    route_time.append(route_time[-1] + current_pace * current_distance / TO_MINUTES)

#Now add fake point to account for time stopped during new portion of run 
route_lat.append(route_lat[-1])
route_long.append(route_long[-1])
missing_time = bad_time[-1] - bad_time[0] - bad_time_tot
route_time.append(route_time[-1] + missing_time)

#Create final arrays and get elevation data
if start_bad == 0:
    final_lat = route_lat + good_lat
    final_long = route_long + good_long
    final_time = route_time + good_time
elif end_bad == -1:
    final_lat = good_lat + route_lat
    final_long = good_long + route_long 
    final_time = good_time + route_time
else:
    final_lat = good_lat[:start_bad] + route_lat + good_lat[end_bad:]
    final_long = good_long[:start_bad] + route_long + good_long[end_bad:]
    final_time = good_time[:start_bad] + route_time + good_time[end_bad:]
elevation = load_elevation(final_lat, final_long)

#Finally write to new .gpx file
new_gpx = gpxpy.gpx.GPX()

#Add track
gpx_track = gpxpy.gpx.GPXTrack()
new_gpx.tracks.append(gpx_track)

#Add segment
gpx_segment = gpxpy.gpx.GPXTrackSegment()
gpx_track.segments.append(gpx_segment)

#Add points
for i in range(len(final_long)):
    #Convert time datetime object
    t = convert_time(final_time[i])
    
    gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(final_lat[i],
                                                      final_long[i],
                                                      elevation[i],
                                                      t))

#Done
f = open("new_route.gpx", "w")
f.write(new_gpx.to_xml())
f.close()
