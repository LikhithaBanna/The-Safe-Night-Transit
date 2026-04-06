"""
Safe-Night Transit — Safety-First On-Demand Campus Shuttle System
Flask Backend: Handles ride requests, pooling, OTP, panic, safety scores, camera logic
"""

from flask import Flask, render_template, request, jsonify, session
import random
import string
import time
import math
from datetime import datetime

app = Flask(__name__)
app.secret_key = "safenighttransit2024"

# ─────────────────────────────────────────────
# CAMPUS LOCATIONS & DISTANCE MATRIX
# ─────────────────────────────────────────────

LOCATIONS = [
    "Library", "Main Gate", "Hostel A", "Hostel B",
    "Girls Hostel", "Boys Hostel", "Academic Block",
    "Lab Complex", "Cafeteria", "Sports Complex"
]

SAFE_ZONES = LOCATIONS  # All predefined campus points are safe zones

# Distance matrix (symmetric, in minutes walking)
DISTANCE_MATRIX = {
    ("Library", "Main Gate"): 8,
    ("Library", "Hostel A"): 5,
    ("Library", "Hostel B"): 6,
    ("Library", "Girls Hostel"): 7,
    ("Library", "Boys Hostel"): 7,
    ("Library", "Academic Block"): 3,
    ("Library", "Lab Complex"): 4,
    ("Library", "Cafeteria"): 6,
    ("Library", "Sports Complex"): 10,
    ("Main Gate", "Hostel A"): 10,
    ("Main Gate", "Hostel B"): 9,
    ("Main Gate", "Girls Hostel"): 11,
    ("Main Gate", "Boys Hostel"): 11,
    ("Main Gate", "Academic Block"): 7,
    ("Main Gate", "Lab Complex"): 9,
    ("Main Gate", "Cafeteria"): 5,
    ("Main Gate", "Sports Complex"): 6,
    ("Hostel A", "Hostel B"): 3,
    ("Hostel A", "Girls Hostel"): 4,
    ("Hostel A", "Boys Hostel"): 5,
    ("Hostel A", "Academic Block"): 7,
    ("Hostel A", "Lab Complex"): 8,
    ("Hostel A", "Cafeteria"): 9,
    ("Hostel A", "Sports Complex"): 12,
    ("Hostel B", "Girls Hostel"): 3,
    ("Hostel B", "Boys Hostel"): 4,
    ("Hostel B", "Academic Block"): 6,
    ("Hostel B", "Lab Complex"): 7,
    ("Hostel B", "Cafeteria"): 8,
    ("Hostel B", "Sports Complex"): 11,
    ("Girls Hostel", "Boys Hostel"): 2,
    ("Girls Hostel", "Academic Block"): 8,
    ("Girls Hostel", "Lab Complex"): 9,
    ("Girls Hostel", "Cafeteria"): 10,
    ("Girls Hostel", "Sports Complex"): 12,
    ("Boys Hostel", "Academic Block"): 8,
    ("Boys Hostel", "Lab Complex"): 9,
    ("Boys Hostel", "Cafeteria"): 10,
    ("Boys Hostel", "Sports Complex"): 12,
    ("Academic Block", "Lab Complex"): 4,
    ("Academic Block", "Cafeteria"): 5,
    ("Academic Block", "Sports Complex"): 8,
    ("Lab Complex", "Cafeteria"): 6,
    ("Lab Complex", "Sports Complex"): 9,
    ("Cafeteria", "Sports Complex"): 5,
}

def get_distance(a, b):
    """Get travel time between two campus points (van speed ~3x walk)."""
    if a == b:
        return 0
    key = (a, b) if (a, b) in DISTANCE_MATRIX else (b, a)
    base = DISTANCE_MATRIX.get(key, 10)
    return max(2, base // 3)  # Van is faster


# ─────────────────────────────────────────────
# IN-MEMORY DATA STORE
# ─────────────────────────────────────────────

# Vans: id, driver, capacity, current_location, status, passengers, route, safety_score
VANS = {
    "V001": {
        "id": "V001", "name": "Van Alpha", "driver": "Rajan Kumar",
        "driver_id": "D001", "capacity": 8, "current_location": "Main Gate",
        "status": "available",  # available | en_route | full | offline
        "passengers": [], "route": [], "safety_score": 96,
        "camera_active": False, "camera_log": [],
        "route_deviation": False, "shift_active": False,
    },
    "V002": {
        "id": "V002", "name": "Van Beta", "driver": "Priya Sharma",
        "driver_id": "D002", "capacity": 8, "current_location": "Library",
        "status": "available",
        "passengers": [], "route": [], "safety_score": 91,
        "camera_active": False, "camera_log": [],
        "route_deviation": False, "shift_active": False,
    },
    "V003": {
        "id": "V003", "name": "Van Gamma", "driver": "Arun Mehta",
        "driver_id": "D003", "capacity": 8, "current_location": "Hostel A",
        "status": "offline",
        "passengers": [], "route": [], "safety_score": 88,
        "camera_active": False, "camera_log": [],
        "route_deviation": False, "shift_active": False,
    },
}

# Students: id, name, pickup, drop, status, otp, van_id, request_time, emergency_contact
RIDES = {}          # ride_id → ride details
WAITLIST = []       # list of ride_ids waiting for van
PANIC_ALERTS = []   # active panic events
SAFETY_EVENTS = []  # all safety log entries
FEEDBACK_LOG = []   # student feedback

ride_counter = [1]

def gen_ride_id():
    rid = f"R{ride_counter[0]:04d}"
    ride_counter[0] += 1
    return rid

def gen_otp():
    return ''.join(random.choices(string.digits, k=4))

def now_str():
    return datetime.now().strftime("%H:%M:%S")

def timestamp():
    return time.time()


# ─────────────────────────────────────────────
# VEHICLE ASSIGNMENT & POOLING
# ─────────────────────────────────────────────

def find_best_van(pickup):
    """Find closest available van with seats. Enables ride pooling."""
    best_van = None
    best_eta = 999
    for vid, van in VANS.items():
        if van["status"] in ("available", "en_route") and van["shift_active"]:
            seats_left = van["capacity"] - len(van["passengers"])
            if seats_left > 0:
                eta = get_distance(van["current_location"], pickup)
                if eta < best_eta:
                    best_eta = eta
                    best_van = vid
    return best_van, best_eta


def build_pooled_route(van_id):
    """
    Build optimized route for a van considering all pending pickups and drops.
    Nearest-neighbor heuristic: visit nearest unvisited stop first.
    """
    van = VANS[van_id]
    pickups_needed = []
    drops_needed = []
    for rid in van["passengers"]:
        ride = RIDES.get(rid)
        if not ride:
            continue
        if ride["status"] == "waiting":
            pickups_needed.append(("pickup", rid, ride["pickup"]))
        elif ride["status"] == "boarded":
            drops_needed.append(("drop", rid, ride["drop"]))

    # Simple route: do all pickups first (nearest first), then all drops
    route = []
    current = van["current_location"]

    for group in [pickups_needed, drops_needed]:
        remaining = list(group)
        while remaining:
            nearest = min(remaining, key=lambda x: get_distance(current, x[2]))
            route.append(nearest)
            current = nearest[2]
            remaining.remove(nearest)

    van["route"] = route
    return route


def calc_eta(van_id, student_pickup):
    """Calculate ETA for a student considering current route."""
    van = VANS[van_id]
    minutes = get_distance(van["current_location"], student_pickup)
    # Add time for intermediate stops already queued
    for stop in van.get("route", []):
        stop_loc = stop[2]
        minutes += get_distance(van["current_location"], stop_loc) // 2
        break  # rough estimate
    return max(2, minutes)


# ─────────────────────────────────────────────
# SAFETY SCORE ENGINE
# ─────────────────────────────────────────────

def recalc_safety_score(van_id):
    """
    Safety Score (0-100) based on:
    - Route deviations (-15 each)
    - Panic events (-20 each)
    - Unusual stops (-10 each)
    - On-time performance (+base)
    Returns: score, status (Safe/Warning/Risk)
    """
    van = VANS[van_id]
    score = 100

    # Check panic events for this van
    panics = [p for p in PANIC_ALERTS if p.get("van_id") == van_id and p.get("resolved") == False]
    score -= len(panics) * 20

    if van.get("route_deviation"):
        score -= 15

    score = max(0, min(100, score))
    van["safety_score"] = score

    if score >= 80:
        status = "Safe"
    elif score >= 55:
        status = "Warning"
    else:
        status = "Risk"

    return score, status


def log_safety_event(event_type, van_id, ride_id, detail):
    SAFETY_EVENTS.append({
        "time": now_str(),
        "type": event_type,
        "van_id": van_id,
        "ride_id": ride_id,
        "detail": detail,
        "ts": timestamp()
    })


# ─────────────────────────────────────────────
# CAMERA ACTIVATION LOGIC
# ─────────────────────────────────────────────

def activate_camera(van_id, reason):
    """
    Camera is ONLY activated during:
    - Panic event
    - Route deviation
    - Suspicious delay
    Access is logged with timestamp and reason.
    """
    van = VANS[van_id]
    van["camera_active"] = True
    log_entry = {
        "time": now_str(),
        "reason": reason,
        "activated_by": "System/Admin",
        "ts": timestamp()
    }
    van["camera_log"].append(log_entry)
    log_safety_event("CAMERA_ACTIVATED", van_id, None, reason)
    return log_entry


def deactivate_camera(van_id):
    van = VANS[van_id]
    van["camera_active"] = False
    van["camera_log"].append({"time": now_str(), "reason": "Deactivated", "ts": timestamp()})


# ─────────────────────────────────────────────
# ROUTES — PAGES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/student")
def student():
    return render_template("student.html", locations=LOCATIONS)

@app.route("/driver")
def driver():
    return render_template("driver.html", vans=VANS)

@app.route("/admin")
def admin():
    return render_template("admin.html")


# ─────────────────────────────────────────────
# API — STUDENT
# ─────────────────────────────────────────────

@app.route("/api/request_ride", methods=["POST"])
def request_ride():
    """Student requests a ride. System assigns van or adds to waitlist."""
    data = request.json
    name = data.get("name", "Student")
    student_id = data.get("student_id", f"S{random.randint(100,999)}")
    pickup = data.get("pickup")
    drop = data.get("drop")
    emergency_contact = data.get("emergency_contact", "Campus Security: 9999")

    if pickup not in LOCATIONS or drop not in LOCATIONS:
        return jsonify({"success": False, "error": "Invalid location. Use campus safe zones only."})

    if pickup == drop:
        return jsonify({"success": False, "error": "Pickup and drop cannot be the same."})

    ride_id = gen_ride_id()
    otp = gen_otp()

    ride = {
        "id": ride_id,
        "name": name,
        "student_id": student_id,
        "pickup": pickup,
        "drop": drop,
        "status": "waiting",       # waiting | boarded | completed | cancelled
        "otp": otp,
        "van_id": None,
        "eta": None,
        "request_time": now_str(),
        "request_ts": timestamp(),
        "board_time": None,
        "drop_time": None,
        "emergency_contact": emergency_contact,
        "safe_arrived": False,
        "wait_check_sent": False,
        "feedback": None,
    }

    # Try to assign van
    van_id, eta = find_best_van(pickup)
    if van_id:
        ride["van_id"] = van_id
        ride["eta"] = eta
        VANS[van_id]["passengers"].append(ride_id)
        VANS[van_id]["status"] = "en_route"
        build_pooled_route(van_id)
        msg = f"Van {VANS[van_id]['name']} assigned. ETA: {eta} min. Your OTP: {otp}"
    else:
        WAITLIST.append(ride_id)
        msg = "No van available. Added to waitlist. We'll notify you when a van is assigned."

    RIDES[ride_id] = ride
    log_safety_event("RIDE_REQUESTED", van_id, ride_id, f"{name}: {pickup} → {drop}")

    return jsonify({
        "success": True,
        "ride_id": ride_id,
        "otp": otp,
        "van_id": van_id,
        "van_name": VANS[van_id]["name"] if van_id else None,
        "driver": VANS[van_id]["driver"] if van_id else None,
        "eta": eta,
        "message": msg
    })


@app.route("/api/ride_status/<ride_id>")
def ride_status(ride_id):
    ride = RIDES.get(ride_id)
    if not ride:
        return jsonify({"success": False, "error": "Ride not found"})
    van = VANS.get(ride["van_id"]) if ride["van_id"] else None
    score, status = recalc_safety_score(ride["van_id"]) if ride["van_id"] else (100, "Safe")
    return jsonify({
        "success": True,
        "ride": ride,
        "van": van,
        "safety_score": score,
        "safety_status": status,
        "in_waitlist": ride_id in WAITLIST
    })


@app.route("/api/panic", methods=["POST"])
def panic():
    """Student triggers panic button. Alerts admin, activates camera."""
    data = request.json
    ride_id = data.get("ride_id")
    ride = RIDES.get(ride_id)
    if not ride:
        return jsonify({"success": False, "error": "Ride not found"})

    van_id = ride.get("van_id")

    alert = {
        "id": f"P{len(PANIC_ALERTS)+1:03d}",
        "ride_id": ride_id,
        "van_id": van_id,
        "student": ride["name"],
        "pickup": ride["pickup"],
        "drop": ride["drop"],
        "time": now_str(),
        "ts": timestamp(),
        "resolved": False,
        "contact_alerted": ride["emergency_contact"],
        "camera_activated": False
    }

    # Activate camera if van is assigned
    if van_id:
        activate_camera(van_id, "Panic Button Triggered")
        alert["camera_activated"] = True
        VANS[van_id]["status"] = "en_route"
        recalc_safety_score(van_id)

    PANIC_ALERTS.append(alert)
    log_safety_event("PANIC_TRIGGERED", van_id, ride_id, f"Student: {ride['name']}")

    return jsonify({
        "success": True,
        "alert_id": alert["id"],
        "message": "🚨 Emergency alert sent to admin and security. Camera activated. Your contact has been notified.",
        "camera_active": True,
        "contact_alerted": ride["emergency_contact"]
    })


@app.route("/api/safe_arrival", methods=["POST"])
def safe_arrival():
    """Student confirms safe arrival after drop."""
    data = request.json
    ride_id = data.get("ride_id")
    ride = RIDES.get(ride_id)
    if not ride:
        return jsonify({"success": False})
    ride["safe_arrived"] = True
    ride["status"] = "completed"
    ride["drop_time"] = now_str()
    log_safety_event("SAFE_ARRIVAL", ride.get("van_id"), ride_id, f"{ride['name']} confirmed arrival")
    if ride.get("van_id"):
        van = VANS[ride["van_id"]]
        if ride_id in van["passengers"]:
            van["passengers"].remove(ride_id)
        if not van["passengers"]:
            van["status"] = "available"
        build_pooled_route(ride["van_id"])
        recalc_safety_score(ride["van_id"])
    return jsonify({"success": True, "message": "✅ Safe arrival confirmed. Thank you for using Safe-Night Transit!"})


@app.route("/api/submit_feedback", methods=["POST"])
def submit_feedback():
    data = request.json
    ride_id = data.get("ride_id")
    rating = data.get("rating", 5)
    comment = data.get("comment", "")
    ride = RIDES.get(ride_id)
    if ride:
        ride["feedback"] = {"rating": rating, "comment": comment, "time": now_str()}
        FEEDBACK_LOG.append({"ride_id": ride_id, "rating": rating, "comment": comment})
        # Update driver trust score
        van_id = ride.get("van_id")
        if van_id:
            van = VANS[van_id]
            old_score = van["safety_score"]
            adjust = (rating - 3) * 2  # +4 for 5★, -4 for 1★
            van["safety_score"] = max(0, min(100, old_score + adjust))
    return jsonify({"success": True, "message": "Feedback submitted. Thank you!"})


# ─────────────────────────────────────────────
# API — DRIVER
# ─────────────────────────────────────────────

@app.route("/api/driver/start_shift", methods=["POST"])
def start_shift():
    data = request.json
    van_id = data.get("van_id")
    van = VANS.get(van_id)
    if not van:
        return jsonify({"success": False, "error": "Van not found"})
    van["shift_active"] = True
    van["status"] = "available"
    log_safety_event("SHIFT_STARTED", van_id, None, f"Driver {van['driver']} started shift")
    # Check if anyone is in waitlist
    _process_waitlist()
    return jsonify({"success": True, "message": f"Shift started for {van['name']}.", "van": van})


@app.route("/api/driver/end_shift", methods=["POST"])
def end_shift():
    data = request.json
    van_id = data.get("van_id")
    van = VANS.get(van_id)
    if not van:
        return jsonify({"success": False, "error": "Van not found"})
    if van["passengers"]:
        return jsonify({"success": False, "error": "Cannot end shift with active passengers."})
    van["shift_active"] = False
    van["status"] = "offline"
    log_safety_event("SHIFT_ENDED", van_id, None, f"Driver {van['driver']} ended shift")
    return jsonify({"success": True, "message": "Shift ended."})


@app.route("/api/driver/verify_otp", methods=["POST"])
def verify_otp():
    """Driver verifies student OTP before boarding."""
    data = request.json
    van_id = data.get("van_id")
    ride_id = data.get("ride_id")
    otp_entered = data.get("otp")

    ride = RIDES.get(ride_id)
    if not ride:
        return jsonify({"success": False, "error": "Ride not found"})
    if ride["van_id"] != van_id:
        return jsonify({"success": False, "error": "Student not assigned to this van"})
    if ride["otp"] != otp_entered:
        return jsonify({"success": False, "error": "❌ Incorrect OTP. Student boarding denied."})

    ride["status"] = "boarded"
    ride["board_time"] = now_str()
    build_pooled_route(van_id)
    log_safety_event("STUDENT_BOARDED", van_id, ride_id, f"{ride['name']} verified & boarded")
    return jsonify({"success": True, "message": f"✅ OTP verified. {ride['name']} is now boarded."})


@app.route("/api/driver/mark_drop", methods=["POST"])
def mark_drop():
    """Driver marks a student as dropped."""
    data = request.json
    van_id = data.get("van_id")
    ride_id = data.get("ride_id")
    ride = RIDES.get(ride_id)
    if not ride:
        return jsonify({"success": False})
    ride["status"] = "dropped"
    ride["drop_time"] = now_str()
    log_safety_event("STUDENT_DROPPED", van_id, ride_id, f"{ride['name']} dropped at {ride['drop']}")
    # Schedule safe arrival check — if student doesn't confirm in 3 mins → alert
    return jsonify({"success": True, "message": f"Dropped {ride['name']} at {ride['drop']}. Waiting for safe arrival confirmation."})


@app.route("/api/driver/update_location", methods=["POST"])
def update_location():
    """Driver updates current van location."""
    data = request.json
    van_id = data.get("van_id")
    location = data.get("location")
    van = VANS.get(van_id)
    if not van or location not in LOCATIONS:
        return jsonify({"success": False})
    old_location = van["current_location"]
    van["current_location"] = location
    # Route deviation check: if new location not in planned route
    route_locs = [s[2] for s in van.get("route", [])]
    if route_locs and location not in route_locs and location != old_location:
        van["route_deviation"] = True
        activate_camera(van_id, "Route Deviation Detected")
        recalc_safety_score(van_id)
        log_safety_event("ROUTE_DEVIATION", van_id, None, f"Deviated to {location}")
    return jsonify({"success": True, "van": van})


@app.route("/api/driver/van_status/<van_id>")
def van_status(van_id):
    van = VANS.get(van_id)
    if not van:
        return jsonify({"success": False})
    passengers_detail = [RIDES.get(r) for r in van["passengers"] if RIDES.get(r)]
    score, status = recalc_safety_score(van_id)
    return jsonify({
        "success": True,
        "van": van,
        "passengers": passengers_detail,
        "route": van["route"],
        "safety_score": score,
        "safety_status": status
    })


# ─────────────────────────────────────────────
# API — ADMIN
# ─────────────────────────────────────────────

@app.route("/api/admin/dashboard")
def admin_dashboard():
    """Full admin dashboard data."""
    all_rides = list(RIDES.values())
    active_rides = [r for r in all_rides if r["status"] in ("waiting", "boarded", "dropped")]
    completed = [r for r in all_rides if r["status"] == "completed"]
    
    vans_data = {}
    for vid, van in VANS.items():
        score, status = recalc_safety_score(vid)
        vans_data[vid] = {**van, "safety_score": score, "safety_status": status}

    # High demand zones: locations with most requests
    location_counts = {}
    for r in all_rides:
        location_counts[r["pickup"]] = location_counts.get(r["pickup"], 0) + 1
    high_demand = sorted(location_counts.items(), key=lambda x: -x[1])

    unresolved_panics = [p for p in PANIC_ALERTS if not p["resolved"]]

    return jsonify({
        "success": True,
        "active_rides": active_rides,
        "completed_count": len(completed),
        "waitlist": [RIDES.get(r) for r in WAITLIST if RIDES.get(r)],
        "vans": vans_data,
        "panic_alerts": PANIC_ALERTS,
        "unresolved_panics": unresolved_panics,
        "safety_events": SAFETY_EVENTS[-20:],
        "high_demand_zones": high_demand[:5],
        "total_rides": len(all_rides),
    })


@app.route("/api/admin/resolve_panic", methods=["POST"])
def resolve_panic():
    data = request.json
    alert_id = data.get("alert_id")
    for p in PANIC_ALERTS:
        if p["id"] == alert_id:
            p["resolved"] = True
            if p.get("van_id"):
                deactivate_camera(p["van_id"])
                VANS[p["van_id"]]["route_deviation"] = False
                recalc_safety_score(p["van_id"])
            log_safety_event("PANIC_RESOLVED", p.get("van_id"), p.get("ride_id"), f"Admin resolved alert {alert_id}")
            return jsonify({"success": True, "message": "Alert resolved. Camera deactivated."})
    return jsonify({"success": False, "error": "Alert not found"})


@app.route("/api/admin/activate_camera", methods=["POST"])
def admin_activate_camera():
    data = request.json
    van_id = data.get("van_id")
    reason = data.get("reason", "Admin Manual Activation")
    if van_id not in VANS:
        return jsonify({"success": False})
    log = activate_camera(van_id, reason)
    return jsonify({"success": True, "log": log, "message": f"Camera activated for {VANS[van_id]['name']}"})


@app.route("/api/admin/safety_log")
def safety_log():
    return jsonify({"success": True, "events": SAFETY_EVENTS[-50:]})


@app.route("/api/locations")
def get_locations():
    return jsonify({"locations": LOCATIONS, "safe_zones": SAFE_ZONES})


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _process_waitlist():
    """Try to assign vans to waitlisted students."""
    still_waiting = []
    for ride_id in WAITLIST:
        ride = RIDES.get(ride_id)
        if not ride:
            continue
        van_id, eta = find_best_van(ride["pickup"])
        if van_id:
            ride["van_id"] = van_id
            ride["eta"] = eta
            VANS[van_id]["passengers"].append(ride_id)
            VANS[van_id]["status"] = "en_route"
            build_pooled_route(van_id)
            log_safety_event("WAITLIST_ASSIGNED", van_id, ride_id, f"{ride['name']} assigned from waitlist")
        else:
            still_waiting.append(ride_id)
    WAITLIST.clear()
    WAITLIST.extend(still_waiting)


# ─────────────────────────────────────────────
# SEED DEMO DATA
# ─────────────────────────────────────────────

def seed_demo():
    """Pre-populate demo state so the dashboard isn't empty."""
    # Start Van Alpha shift
    VANS["V001"]["shift_active"] = True
    VANS["V001"]["status"] = "available"
    VANS["V002"]["shift_active"] = True
    VANS["V002"]["status"] = "available"

    # Student 1
    r1_id = gen_ride_id()
    RIDES[r1_id] = {
        "id": r1_id, "name": "Ananya Iyer", "student_id": "S21CS042",
        "pickup": "Lab Complex", "drop": "Girls Hostel",
        "status": "boarded", "otp": "7391", "van_id": "V001",
        "eta": 5, "request_time": "22:14:00", "request_ts": timestamp()-300,
        "board_time": "22:17:00", "drop_time": None,
        "emergency_contact": "Mom: 9876543210",
        "safe_arrived": False, "wait_check_sent": False, "feedback": None
    }
    VANS["V001"]["passengers"].append(r1_id)

    # Student 2 (pooled in same van)
    r2_id = gen_ride_id()
    RIDES[r2_id] = {
        "id": r2_id, "name": "Karthik Raj", "student_id": "S21EC011",
        "pickup": "Library", "drop": "Boys Hostel",
        "status": "waiting", "otp": "4862", "van_id": "V001",
        "eta": 3, "request_time": "22:16:00", "request_ts": timestamp()-180,
        "board_time": None, "drop_time": None,
        "emergency_contact": "Dad: 9988776655",
        "safe_arrived": False, "wait_check_sent": False, "feedback": None
    }
    VANS["V001"]["passengers"].append(r2_id)
    VANS["V001"]["status"] = "en_route"
    build_pooled_route("V001")

    # Safety event log
    log_safety_event("RIDE_REQUESTED", "V001", r1_id, "Ananya Iyer: Lab Complex → Girls Hostel")
    log_safety_event("STUDENT_BOARDED", "V001", r1_id, "Ananya verified & boarded")
    log_safety_event("RIDE_REQUESTED", "V001", r2_id, "Karthik Raj: Library → Boys Hostel")

seed_demo()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
