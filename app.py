from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
import mysql.connector
import random
import string
import uuid 
from aptsmandals import Andhrapradesh, Telangana 

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ------------------ DATABASE CONNECTION ------------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="FILL_YOUR_SQL_PASSWORD",
    database="carpool_db"
)

cursor = db.cursor(dictionary=True, buffered=True)
# ------------------ GOOGLE OAUTH ------------------
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    access_token_url="https://oauth2.googleapis.com/token",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    api_base_url="https://www.googleapis.com/oauth2/v2/",
    client_kwargs={"scope": "openid email profile"},
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
)

# ------------------ ROUTES ------------------

@app.route("/")
def index():
    return render_template("navbar.html", user=session.get("user"))

@app.route("/dashboard")
def dashboard():
    return render_template("navbar.html", user=session.get("user"))

@app.route("/login")
def show_login():
    return render_template("login.html")

@app.route("/login/google")
def login_with_google():
    redirect_uri = url_for("google_auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def google_auth_callback():
    token = google.authorize_access_token()
    resp = google.get("userinfo")
    user_info = resp.json()

    email = user_info["email"]

    session["user"] = {
        "google_id": user_info["id"],
        "name": user_info["name"],
        "email": email,
        "picture": user_info["picture"]
    }

    cursor.execute(
        "SELECT * FROM userdb WHERE Gmail=%s",
        (email,)
    )
    existing_user = cursor.fetchone()

    if existing_user:
        session["UID"] = existing_user["UID"]
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("userinfo"))

        # API - DRIVER STATUS 
@app.route("/api/driver_status")
def api_driver_status():
    if "UID" not in session:
        return jsonify({"status": "no"})

    uid = session["UID"]
    cursor.execute(
        "SELECT driver_status FROM userdb WHERE UID = %s",
        (uid,)
    )
    result = cursor.fetchone()
    status = result['driver_status'] if result else "no"
    return jsonify({"status": status})


# ------------------ USER INFO ------------------
@app.route("/userinfo")
def userinfo():
    if "user" not in session:
        return redirect(url_for("show_login"))
    return render_template("userinfo.html", user=session["user"])

# ------------------ DRIVER INFO ------------------
@app.route("/driverinfo")
def driverinfo():
    if "user" not in session:
        return redirect(url_for("show_login"))

    email = session["user"]["email"]

    cursor.execute("""
        SELECT UID, Name, Gmail AS Email, Phone,
               Address AS District, State, driver_status
        FROM userdb
        WHERE Gmail = %s
    """, (email,))
    driver = cursor.fetchone()

    if not driver:
        return "User profile not completed. Please complete registration first.", 400

    # ALREADY REGISTERED DRIVER
    if driver["driver_status"] == "yes":
        cursor.execute("SELECT * FROM driverdb WHERE UID=%s", (driver["UID"],))
        driverdb = cursor.fetchone()

        return render_template(
            "driverinfo.html",
            already_driver=True,
            driverdb=driverdb,
            user=session.get("user")
        )

    # NOT REGISTERED DRIVER
    return render_template(
        "driverinfo.html",
        already_driver=False,
        driver=driver,
        user=session.get("user")
    )

@app.route('/vehicleinfo', methods=['GET', 'POST'])
def vehicleinfo():
    if "user" not in session:
        return redirect(url_for("show_login"))

    if request.method == 'POST':
        UID = session.get("UID")                  
        VUID = str(uuid.uuid4())                   

        Oname = request.form.get('OwnerName', '').upper()
        Vnum = request.form.get('VehicleNumber', '').upper()
        Vname = request.form.get('VehicleName', '').upper()
        Vtype = request.form.get('VehicleType')
        Ftype = request.form.get('FuelType')
        Rstate = request.form.get('Registerdstate')

        # Vehicle Color
        Vcolor = request.form.get('VehicleColor')
        OtherColor = request.form.get('OtherColor')
        if Vcolor == "Other" and OtherColor:
            Vcolor = OtherColor.upper()  

        Scapty = request.form.get('SeatingCapacity')
        Bspace = request.form.get('BootSpace')
        Transmission = request.form.get('Transmission')
        FuelEff = request.form.get('FuelEfficiency')

        # Convert numeric values
        FuelEff = float(FuelEff) if FuelEff else None

        query = """
        INSERT INTO vehicleinfo
        (UID, VUID, OwnerName, VehicleNumber, VehicleColor,
         VehicleType, VehicleName, SeatingCapacity, BootSpace,
         FuelType, RegisteredState, Transmission, FuelEfficiency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            UID, VUID, Oname, Vnum, Vcolor,
            Vtype, Vname, Scapty, Bspace,
            Ftype, Rstate, Transmission, FuelEff
        )

        cursor.execute(query, values)
        db.commit()

        return redirect(url_for('vehicleinfo'))

    return render_template('vehicleinfo.html', user=session.get("user"))

@app.route('/bookings')
def bookings():
    uid = session.get('UID')
    return f"SESSION UID = {uid}"

# ------------------ Registration aam admi ------------------
@app.route("/register", methods=["POST"])
def register():
    if "user" not in session:
        return redirect(url_for("show_login"))

    user = session["user"]

    UID = request.form["UID"]
    phone = request.form["Phone"]
    district = request.form["Dist"]
    state = request.form["state"]
    pincode = request.form["Pincode"]

    if not phone.isdigit() or len(phone) != 10:
        return "Phone number must be exactly 10 digits", 400

    allowed_districts = ["Kurnool", "Prakasam", "Nandyal"]
    if district not in allowed_districts:
        return "Service available only in Kurnool, Prakasam, Nandyal", 400

    sql = """
        INSERT INTO userdb
        (UID, Name, Gmail, LoginType, Phone, Address, State, driver_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'no')
    """

    values = (
        UID,
        user["name"],
        user["email"],
        "Google",
        phone,
        district,
        state
    )

    cursor.execute(sql, values)
    db.commit()

    session["UID"] = UID

    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))



@app.route("/ticketinfo")
def ticketinfo():
    return redirect(url_for("ticket_status"))

# ------------------ DRIVER REGISTER ------------------
@app.route("/driver_register", methods=["POST","GET"])
def driver_register():
    if "user" not in session:
        return redirect(url_for("show_login"))

    # Get error fix kiya,form waas asking get for post request
    if request.method == "GET":
        return redirect(url_for("driverinfo"))

    UID = request.form["UID"]

    #  Prevent duplicate registration
    cursor.execute("SELECT driver_status FROM userdb WHERE UID=%s", (UID,))
    status = cursor.fetchone()

    if status and status["driver_status"] == "yes":
        return redirect(url_for("driverinfo"))

    sql = """
        INSERT INTO driverdb
        (UID, Name, AGE, VerifnType, Last_4Digi,
         Email, Phone, Address, STATE, expirydt)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """

    values = (
        request.form["UID"],
        request.form["Name"],
        request.form["AGE"],
        request.form["VerifnType"],
        request.form["Last_4Digi"],
        request.form["Email"],
        request.form["Phone"],
        request.form["Address"],
        request.form["STATE"],
        request.form["expirydt"]
    )

    cursor.execute(sql, values)

    # Update driver status
    cursor.execute(
        "UPDATE userdb SET driver_status='yes' WHERE UID=%s",
        (UID,)
    )

    db.commit()
    return redirect(url_for("dashboard"))

# ------------------ CAPTCHA ------------------
def generate_captcha():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

# ------------------ ADD RIDE ------------------
@app.route('/add-ride', methods=['GET','POST'])
def add_ride():
    if "user" not in session:
        return redirect(url_for("show_login"))

    #  BACKEND PROTECTION
    cursor.execute(
        "SELECT driver_status FROM userdb WHERE UID=%s",
        (session['UID'],)
    )
    status = cursor.fetchone()

    if not status or status["driver_status"] != "yes":
        return redirect(url_for("driverinfo"))

    if request.method == 'POST':
        driver_uid = request.form.get("UID")
        vehicle_id = request.form.get("vehicle_no")
        source = request.form.get("source")
        destination = request.form.get("destination")
        travel_date = request.form.get("ride_date")
        seats = int(request.form.get("seats"))

        cursor.execute(
            "SELECT FuelEfficiency FROM vehicleinfo WHERE VUID=%s",
            (vehicle_id,)
        )
        vehicle = cursor.fetchone()

        if not vehicle:
            return "Selected vehicle does not exist", 400

        fuel_eff = vehicle['FuelEfficiency']
        distance = 100
        fuel_price = 100
        total_fuel_cost = (distance / fuel_eff) * fuel_price
        passenger_fare = round(total_fuel_cost / seats, 2)

        cursor.execute("""
            INSERT INTO rides
            (vehicle_id, UID, Source, Destination, TravelDate,
             SeatsAvailable, Fare)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            vehicle_id, driver_uid, source,
            destination, travel_date, seats, passenger_fare
        ))

        db.commit()
        return redirect(url_for("driverinfo"))

    cursor.execute(
        "SELECT VUID, VehicleName FROM vehicleinfo WHERE UID=%s",
        (session['UID'],)
    )
    vehicles = cursor.fetchall()

    return render_template("upload_ride.html", vehicles=vehicles)


#-----cancel karo bhai------#
@app.route("/cancel_ticket", methods=["GET", "POST"])
def cancel_ticket():
    error = None

    if "user" not in session:
        return redirect(url_for("show_login"))

    #  GENERATE CAPTCHA ON PAGE LOAD
    if request.method == "GET":
        captcha = generate_captcha()
        session["captcha"] = captcha
        return render_template("cancel_ticket.html", captcha=captcha, error=None)

    #  FORM SUBMIT (POST)
    ticket_no = request.form.get("ticket_no")
    captcha_input = request.form.get("captcha")
    stored_captcha = session.get("captcha")

    if captcha_input != stored_captcha:
        error = "Invalid captcha"
    else:
        cursor.execute(
            "SELECT * FROM bookings WHERE ticketnum=%s",
            (ticket_no,)
        )
        ticket = cursor.fetchone()

        if ticket:
            return render_template("ticketinfomain.html", ticket=ticket)
        else:
            error = "Ticket number not found"

    #  regenerate captcha after failure
    captcha = generate_captcha()
    session["captcha"] = captcha

    return render_template("cancel_ticket.html", captcha=captcha, error=error)


# ------------------ Usser name checkk karo bhai------------------
@app.route("/check-username")
def check_username():
    username = request.args.get("username")

    if not username:
        return jsonify({"exists": False})

    cursor.execute(
        "SELECT 1 FROM userdb WHERE UID=%s",
        (username,)
    )
    user = cursor.fetchone()

    return jsonify({"exists": bool(user)})

# ------------------ Pincode check karlo bhai ------------------
@app.route("/check-pincode")
def check_pincode():
    district = request.args.get("district")
    pincode = request.args.get("pincode")

    if not pincode or not pincode.isdigit():
        return jsonify({"valid": False})

    pin = int(pincode)

    ranges = {
        "Visakhapatnam": [(530001, 530049)],
        "Guntur": [(522001, 522034)],
        "Krishna": [(521001, 521333)],
        "Kurnool": [(518001, 518599)],
        "Nellore": [(524001, 524408)],
        "Hyderabad": [(500001, 500096)],
        "Rangareddy": [(500018, 501512)],
        "Warangal": [(506001, 506013)],
        "Karimnagar": [(505001, 505532)],
        "Nizamabad": [(503001, 503230)]
    }

    if district not in ranges:
        return jsonify({"valid": False})

    for start, end in ranges[district]:
        if start <= pin <= end:
            return jsonify({"valid": True})

    return jsonify({"valid": False})

# ------------------ CHECK PHONE ------------------
@app.route("/check-phone")
def check_phone():
    phone = request.args.get("phone")
    if not phone:
        return jsonify({"exists": False})

    cursor.execute(
        "SELECT * FROM userdb WHERE Phone=%s",
        (phone,)
    )
    result = cursor.fetchone()

    return jsonify({"exists": bool(result)})

#------ticket status idhar hai bsdk-----#
@app.route("/ticket_status", methods=["GET", "POST"])
def ticket_status():
    if "user" not in session:
        return redirect(url_for("show_login"))

    error = None
    if request.method == "GET":
        captcha = generate_captcha()
        session["captcha"] = captcha
        return render_template(
            "ticketinfo.html",
            captcha=captcha,
            error=None,
            user=session["user"]
        )

    ticket_no = request.form.get("ticket_no")
    captcha_input = request.form.get("captcha")
    stored_captcha = session.get("captcha")

    # Captcha validation
    if not captcha_input or captcha_input != stored_captcha:
        error = "Invalid captcha"
    else:
        cursor.execute(
            """
            SELECT *
            FROM bookings
            WHERE ticketnum = %s
            
            """,
            (ticket_no,)
        )
        ticket = cursor.fetchone()

        if ticket:
            return render_template(
                "ticketinfomain.html",
                ticket=ticket
            )
        else:
            error = "Ticket not found for this user"

    
    # captcha on errr
    captcha = generate_captcha()
    session["captcha"] = captcha

    return render_template(
        "ticketinfo.html",
        captcha=captcha,
        error=error
    )


@app.route('/vehicles')
def vehicles_page():
    if "user" not in session:
        return redirect(url_for("show_login"))

    # Fetch all vehicles with driver info
    cursor.execute("""
        SELECT v.VehicleName AS name, v.VehicleType AS type,
               v.VUID AS vid, v.FuelEfficiency AS fuel_eff,
               u.Name AS driver, u.UID AS driver_uid,
               v.RegisteredState AS source, '' AS dest,
               v.VehicleNumber AS number, v.VehicleColor AS color
        FROM vehicleinfo v
        JOIN userdb u ON v.UID = u.UID
    """)
    vehicles = cursor.fetchall()

    return render_template(
        'bookingsinfo.html',
        vehicles=vehicles,
        user=session.get('user')
    )


@app.route('/mybookings')
def mybookings():
    if 'UID' not in session:  
        return redirect('/login')
    
    uid = session['UID']  
    
    
    cursor.execute("""
        SELECT b.*, d.Name as driver_name, d.rating
        FROM bookings b 
        LEFT JOIN driverdb d ON b.coj = d.UID
        WHERE b.UID = %s
        ORDER BY b.DateofJourney DESC
    """, (uid,))
    
    bookings = cursor.fetchall()
    
    
    for booking in bookings:
        if booking.get('DateofJourney'):
            booking['DateofJourney'] = booking['DateofJourney'].strftime('%d/%m/%Y')
    
    
    print(f"🔍 Found {len(bookings)} bookings for UID: {uid}")
    for b in bookings[:2]:  
        print(f"  - {b.get('ticketnum')} | {b.get('STATUS')}")
    
    return render_template('bookingsinfo.html', bookings=bookings, user=session.get('user'))

@app.route("/locations")
def get_locations():
    all_locations = []
    
   
    for district, mandals in Andhrapradesh.items():
        all_locations.append(district.strip())
        for mandal in mandals:
            all_locations.append(mandal.strip())
    
    
    for district, mandals in Telangana.items():
        all_locations.append(district.strip())
        for mandal in mandals:
            all_locations.append(mandal.strip())
    
   
    seen = set()
    unique_locations = []
    for loc in all_locations:
        clean_loc = loc.strip()
        if clean_loc and clean_loc not in seen:
            seen.add(clean_loc)
            unique_locations.append(clean_loc)
    
    return jsonify(unique_locations)  




# ------------------ RUN MAIN WALA ------------------
if __name__ == "__main__":
    app.run(debug=True)
