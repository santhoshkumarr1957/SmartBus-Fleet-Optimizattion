import urllib.request
import json
import time
import math

def haversine_meters(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2)**2
    return 6371000.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def main():
    url = "http://127.0.0.1:8000/api/buses/live"
    print("--- LIVE BUS TELEMETRY SNAPSHOT 1 ---")
    req1 = urllib.request.urlopen(url)
    data1 = json.loads(req1.read().decode())
    time1 = time.time()
    for b in data1:
        print(f"Bus {b['bus_number']} (Route {b['route_number']}): Lat={b['latitude']:.6f}, Lon={b['longitude']:.6f}, Speed={b['speed']} km/h, Pax={b['passenger_count']}/{b['capacity']}, LF={b['load_factor']}")

    delay_sec = 4.0
    print(f"\nWaiting {delay_sec} seconds...")
    time.sleep(delay_sec)

    print("\n--- LIVE BUS TELEMETRY SNAPSHOT 2 ---")
    req2 = urllib.request.urlopen(url)
    data2 = json.loads(req2.read().decode())
    time2 = time.time()
    elapsed = time2 - time1

    map1 = {b['bus_id']: b for b in data1}
    print(f"\n--- DISPLACEMENT COMPARISON (Elapsed: {elapsed:.2f}s) ---")
    for b2 in data2:
        b1 = map1.get(b2['bus_id'])
        if b1 and b1['latitude'] and b2['latitude']:
            dist = haversine_meters(b1['latitude'], b1['longitude'], b2['latitude'], b2['longitude'])
            avg_speed_est = (dist / elapsed) * 3.6
            print(f"Bus {b2['bus_number']} (Route {b2['route_number']}): Distance covered = {dist:.2f} m | Telemetry Speed = {b2['speed']} km/h | Implied Speed = {avg_speed_est:.1f} km/h")

if __name__ == "__main__":
    main()
