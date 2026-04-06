# 🛡️ Safe-Night Transit
### Safety-First On-Demand Campus Shuttle System

---

## 📂 Project Structure

```
safe-night-transit/
├── app.py                  # Flask backend — all logic
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html          # Landing page
│   ├── student.html        # Student portal
│   ├── driver.html         # Driver portal
│   └── admin.html          # Admin dashboard
└── static/
    ├── style.css           # Night-theme shared CSS
    └── script.js           # Shared JS utilities
```

---

## 🚀 How to Run

```bash
# 1. Clone / enter the project folder
cd safe-night-transit

# 2. Install dependencies
pip install flask

# 3. Start the server
python app.py

# 4. Open browser at:
#    http://localhost:5000          (Landing page)
#    http://localhost:5000/student  (Student portal)
#    http://localhost:5000/driver   (Driver portal)
#    http://localhost:5000/admin    (Admin dashboard)
```

---

## 🎮 Demo Walkthrough

### Step 1: Admin — Check Dashboard
- Open `/admin` — see 2 pre-seeded students (Ananya, Karthik) in Van Alpha
- Van Alpha is `EN_ROUTE`, Van Beta is `AVAILABLE`
- Safety score: 100/100 — Safe

### Step 2: Driver — Start Shift & Verify
- Open `/driver`
- Select **Van Alpha**
- Click **Start Shift**
- Enter Ride ID `R0001` and OTP `7391` → click **Verify & Board**
- Mark Ride `R0001` as dropped

### Step 3: Student — Request Ride
- Open `/student`
- Fill form: Name, pickup (Lab Complex), drop (Girls Hostel)
- Click **Request Safe Ride**
- Note your **Ride ID** and **OTP**

### Step 4: Test Panic Button
- In the student portal (after ride is assigned)
- Click the red **PANIC — EMERGENCY ALERT** button
- Admin dashboard will show active panic, camera activated

### Step 5: Route Deviation (Driver)
- In driver portal, update van location to a spot NOT in the planned route
- Admin dashboard shows deviation alert, camera auto-activates

### Step 6: Safe Arrival
- In student portal, once marked as dropped, click **I Am Safe — Confirm Arrival**
- Rate the ride and submit feedback

---

## 🔧 Key Backend Logic

| Feature | Implementation |
|---|---|
| Ride pooling | Nearest-neighbor heuristic assigns students to closest van with seats |
| ETA | Distance matrix with van speed (~3× walk speed) |
| OTP verification | Random 4-digit code, matched server-side |
| Panic handling | Alert stored, camera activated, score recalculated |
| Safety score | 100 − (20×panics) − (15×deviation), clamped 0–100 |
| Camera control | Activated ONLY for: panic / route deviation / manual admin |
| Waitlist | Students queued when no van available, auto-assigned on shift start |
| Safe arrival | Student confirms; if no confirm after drop → admin alert logic |

---

## 🛡️ Safety Features

- **BEFORE ride**: Safe zone validation, OTP generation, emergency contact registration
- **DURING ride**: Route deviation detection, panic button, live safety score, camera activation
- **AFTER ride**: Mandatory safe arrival confirmation, feedback → driver trust score

---

## 💡 Future Improvements

1. WebSocket for true real-time updates (vs polling)
2. SMS integration for emergency contact alerts (Twilio)
3. Real map with campus GeoJSON overlay
4. Machine learning for anomaly detection in routes
5. Mobile-responsive PWA
6. Admin multi-factor authentication
7. Persistent database (PostgreSQL/SQLite)
8. QR code boarding (vs OTP)
