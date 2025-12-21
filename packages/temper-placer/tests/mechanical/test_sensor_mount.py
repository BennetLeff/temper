
import pytest
import math

def calculate_spring_force(k, compression_mm):
    return k * (compression_mm / 1000.0)

def calculate_thermal_resistance(thickness_mm, conductivity, area_mm2):
    area_m2 = area_mm2 * 1e-6
    thickness_m = thickness_mm * 1e-3
    return thickness_m / (conductivity * area_m2)

def test_sensor_mount_contact_force():
    """Verify contact force meets 2N requirement."""
    k = 500 # N/m
    min_compression = 5.0 # mm (travel range spec)
    
    force = calculate_spring_force(k, min_compression)
    assert force >= 2.0 # N

def test_sensor_mount_thermal_resistance():
    """Verify thermal resistance meets 0.5 K/W requirement."""
    thickness = 3.0 # mm
    conductivity = 205 # W/mK (Aluminum)
    radius = 7.5 # mm (15mm diameter)
    area = math.pi * (radius**2)
    
    r_cond = calculate_thermal_resistance(thickness, conductivity, area)
    
    # Interface resistance (conservative estimate)
    r_int = 0.2
    
    r_total = r_cond + r_int
    assert r_total < 0.5 # K/W

def test_response_time_estimate():
    """Estimate time to 90% step response."""
    # Thermal mass C = mass * specific_heat
    # mass = area * thickness * density
    radius = 7.5e-3 # m
    thickness = 3e-3 # m
    area = math.pi * (radius**2)
    vol = area * thickness
    density = 2700 # kg/m3 (Al)
    mass = vol * density
    
    cp = 900 # J/kgK (Al)
    c_th = mass * cp
    
    # R_th from previous test
    r_total = 0.28
    
    # Time constant tau = R * C
    tau = r_total * c_th
    
    # 90% response time = 2.3 * tau
    t_90 = 2.3 * tau
    
    print(f"Estimated 90% response time: {t_90:.2f} s")
    # Target < 2s for responsive control
    assert t_90 < 2.0
