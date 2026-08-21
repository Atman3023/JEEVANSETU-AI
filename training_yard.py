class HourReading:
    hour_label: str      # e.g. "05:30"
    temp_c: float
    humidity_pct: float
    wind_kmh: float

class test1:
    def __init__(self, hour_label: str, temp_c: float, humidity_pct: float, wind_kmh: float):
        self.hour_label = hour_label
        self.temp_c = temp_c
        self.humidity_pct = humidity_pct
        self.wind_kmh = wind_kmh

    def __repr__(self):
        return f"HourReading(hour_label={self.hour_label}, temp_c={self.temp_c}, humidity_pct={self.humidity_pct}, wind_kmh={self.wind_kmh})"

obj1 = test1("05:30", 30.0, 50.0, 10.0)
obj2 = test1("06:30", 32.0, 55.0, 12.0)

obj_list = [obj1, obj2]
obj_list.sort(key=lambda x: x.hour_label)
print(obj_list)