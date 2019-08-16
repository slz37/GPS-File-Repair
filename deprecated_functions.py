'''
Random non-functional snippets of code that may come in handy in the future.
Completely useless for the current version.
'''

def total_time():
    '''
    Grabs the total time of the good segment of the file and combines it with the
    bad total time.
    '''
    
    #Total good time is a little more complicated...
    #First grab velocity change between each pair of 2 points
    del_velocity = []
    for i in range(len(good_lat)-1):
        d = distance([good_lat[i], good_lat[i + 1]], [good_long[i], good_long[i + 1]])
        t = good_time[i + 1] - good_time[i]
        del_velocity.append(d / t)

    #Now check threshold for velocity to prevent counting time while watch paused
    good_time_tot = 0
    for i in range(1, len(good_time)):
        prev_time = good_time[i - 1]
        
        if del_velocity[i - 1] > 1.5:
            good_time_tot += good_time[i] - prev_time

    #Final total time of the run
    tot_time = (bad_time_tot + good_time_tot) * TO_MINUTES

def total_distance():
    '''
    Calculates the total distance of the entire run by combining
    the distance of the good segment and the new route.
    '''
    
    good_distance = 0
    for i in range(len(good_lat) - 1):
        good_distance += distance([good_lat[i], good_lat[i+1]], [good_long[i], good_long[i+1]]) * TO_MILES
    tot_distance = route_distance + good_distance

def elevation():
    '''
    Uses nationalmap to get elevation for lat/long
    coordinates. Faster to just download data and
    use that instead of causing unwanted traffic.
    '''

    def get_elevation(lat, long):
        #Query nationalmap.gov
        query = (r"https://nationalmap.gov/epqs/pqs.php?x={}&y={}&units=Meters&output=xml".format(long, lat))
        r = requests.get(query)

        #Search xml for elevation
        pattern = "(?<=Elevation>)(\d+\.\d+)|(\d+)(?=</Elevation>)"
        elevation = re.search(pattern, r.content.decode("utf-8")).group(0)
        
        return elevation
    
    #Now grab elevation of each point from nationalmap
    elevation = []
    for i in range(len(final_lat)):
        print("Elevation step {} of {}".format(i + 1, len(final_lat)))
        ele = get_elevation(final_lat[i], final_long[i])
        elevation.append(ele)

        #Wait for crawl-delay
        if i != len(final_lat) - 1:
            time.sleep(10)
