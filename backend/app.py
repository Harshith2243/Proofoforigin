from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import hashlib, json, os, re, io, random, string, time
from datetime import datetime
from dotenv import load_dotenv
from web3 import Web3
 
 
 

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["*"], supports_credentials=True)

@app.route("/")
def home():
    return "Backend Running ✅"
 

 

# ── Blockchain ─────────────────────────────────────────────
w3               = Web3(Web3.HTTPProvider(os.getenv("SEPOLIA_RPC_URL")))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
PRIVATE_KEY      = os.getenv("PRIVATE_KEY")
ACCOUNT          = w3.eth.account.from_key(PRIVATE_KEY)

with open(os.path.join(os.path.dirname(__file__), "abi.json")) as f:
    abi = json.load(f)

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=abi)

# ── Users DB (JSON file) ───────────────────────────────────
USERS_FILE = "users.json"
import os
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# Auto-create if missing
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ── OTP store (in-memory) ──────────────────────────────────
otp_store = {}   # { email: { otp, expires } }

# ── Helpers ────────────────────────────────────────────────
def generate_hash(b): return hashlib.sha256(b).hexdigest()

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def generate_phash(file_bytes, filename):
    """
    Perceptual Hash — detects visually similar images.
    Two images that LOOK the same (even after filter/crop/resize)
    will have very similar pHash values.
    Returns: phash string, or None if not an image
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if ext not in ['jpg','jpeg','png','gif','bmp','webp','tiff','heic','heif']:
        return None
    try:
        import imagehash
        from PIL import Image
        img   = Image.open(io.BytesIO(file_bytes)).convert('RGB')
        phash = str(imagehash.phash(img))      # perceptual hash
        dhash = str(imagehash.dhash(img))      # difference hash
        return {"phash": phash, "dhash": dhash}
    except ImportError:
        return None
    except Exception:
        return None

def phash_similarity(hash1, hash2):
    """
    Compare two perceptual hashes.
    Returns similarity percentage (0-100).
    100 = identical, >85 = very similar (same image modified)
    """
    try:
        import imagehash
        h1   = imagehash.hex_to_hash(hash1)
        h2   = imagehash.hex_to_hash(hash2)
        diff = h1 - h2          # hamming distance (0 = identical)
        # phash is 64 bits — max distance is 64
        similarity = round((1 - diff / 64) * 100, 1)
        return similarity
    except:
        return 0

def load_phash_db():
    """Load perceptual hash database"""
    if not os.path.exists('phash_db.json'):
        return []
    with open('phash_db.json') as f:
        return json.load(f)

def save_phash_db(db):
    with open('phash_db.json', 'w') as f:
        json.dump(db, f, indent=2)

def find_similar_image(phash_val, dhash_val, threshold=85):
    """
    Check if a visually similar image is already registered.
    Returns the matching entry if found, else None.
    """
    db = load_phash_db()
    for entry in db:
        # Check phash similarity
        sim_p = phash_similarity(phash_val, entry.get('phash',''))
        sim_d = phash_similarity(dhash_val, entry.get('dhash',''))
        avg_sim = (sim_p + sim_d) / 2
        if avg_sim >= threshold:
            return {**entry, "similarity": avg_sim}
    return None

def send_otp_email(to_email, otp, name="User"):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    gmail_user = os.getenv("GMAIL_ADDRESS")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"ProofOfOrigin — Your OTP: {otp}"
    msg["From"]    = f"ProofOfOrigin <{gmail_user}>"
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#0d1218;color:#fff;border-radius:16px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#137fec,#1d4ed8);padding:32px;text-align:center;">
        <h1 style="margin:0;font-size:24px;">🔐 ProofOfOrigin</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:13px;">Blockchain Content Authentication</p>
      </div>
      <div style="padding:32px;">
        <p style="color:#94a3b8;font-size:14px;">Hello <strong style="color:#fff;">{name}</strong>,</p>
        <p style="color:#94a3b8;font-size:14px;">Your One-Time Password is:</p>
        <div style="background:#1e293b;border:2px solid #137fec;border-radius:12px;padding:24px;text-align:center;margin:20px 0;">
          <span style="font-size:40px;font-weight:900;letter-spacing:12px;color:#137fec;">{otp}</span>
        </div>
        <p style="color:#64748b;font-size:12px;">⏱ This OTP expires in <strong style="color:#f59e0b;">5 minutes</strong>.</p>
        <p style="color:#64748b;font-size:12px;">If you didn't request this, ignore this email.</p>
      </div>
      <div style="background:#0a0f16;padding:16px;text-align:center;">
        <p style="color:#334155;font-size:11px;margin:0;">BCT Alpha · Batch 19 · ProofOfOrigin v2.0</p>
      </div>
    </div>"""

    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_email, msg.as_string())

# ══════════════════════════════════════════════════════════
#   AUTH ROUTES
# ══════════════════════════════════════════════════════════

@app.route("/signup", methods=["POST"])
def signup():
    data     = request.json
    username = data.get("username","").strip().lower()
    name     = data.get("name","").strip()
    email    = data.get("email","").strip().lower()
    password = data.get("password","").strip()

    if not all([username, name, email, password]):
        return jsonify({"success": False, "message": "All fields required!"})

    users = load_users()
    if username in users:
        return jsonify({"success": False, "message": "Username already taken!"})
    if any(u["email"] == email for u in users.values()):
        return jsonify({"success": False, "message": "Email already registered!"})

    # Generate & send OTP
    otp = "".join(random.choices(string.digits, k=6))
    otp_store[email] = {"otp": otp, "expires": time.time() + 300,
                        "pending": {"username": username, "name": name,
                                    "email": email, "password": hash_password(password)}}
    try:
        send_otp_email(email, otp, name)
        return jsonify({"success": True, "message": f"OTP sent to {email}!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Email error: {str(e)}"})


@app.route("/verify-signup-otp", methods=["POST"])
def verify_signup_otp():
    data  = request.json
    email = data.get("email","").strip().lower()
    otp   = data.get("otp","").strip()

    entry = otp_store.get(email)
    if not entry:
        return jsonify({"success": False, "message": "OTP expired or not found!"})
    if time.time() > entry["expires"]:
        del otp_store[email]
        return jsonify({"success": False, "message": "OTP expired! Request a new one."})
    if entry["otp"] != otp:
        return jsonify({"success": False, "message": "Wrong OTP! Try again."})

    # Save user
    users = load_users()
    pending = entry["pending"]
    users[pending["username"]] = {
        "name"    : pending["name"],
        "email"   : pending["email"],
        "password": pending["password"],
        "joined"  : datetime.now().strftime("%d %b %Y"),
        "registered_files": []
    }
    save_users(users)
    del otp_store[email]
    return jsonify({"success": True, "message": "Account created! Please login."})


@app.route("/login", methods=["POST"])
def login():
    data     = request.json
    username = data.get("username","").strip().lower()
    password = data.get("password","").strip()

    users = load_users()
    user  = users.get(username)

    if not user or user["password"] != hash_password(password):
        return jsonify({"success": False, "message": "Invalid username or password!"})

    # Direct login — no OTP needed
    return jsonify({
        "success" : True,
        "message" : "Login successful!",
        "name"    : user["name"],
        "username": username,
        "email"   : user["email"],
        "joined"  : user.get("joined", "—")
    })

@app.route("/verify-login-otp", methods=["POST"])
def verify_login_otp():
    data  = request.json
    email = data.get("email","").strip().lower()
    otp   = data.get("otp","").strip()

    entry = otp_store.get(email)
    if not entry:
        return jsonify({"success": False, "message": "OTP expired!"})
    if time.time() > entry["expires"]:
        del otp_store[email]
        return jsonify({"success": False, "message": "OTP expired! Login again."})
    if entry["otp"] != otp:
        return jsonify({"success": False, "message": "Wrong OTP!"})

    del otp_store[email]

    # Find user by email
    users = load_users()
    for username, user in users.items():
        if user["email"] == email:
            return jsonify({"success": True, "username": username,
                            "name": user["name"], "email": email,
                            "joined": user["joined"]})

    return jsonify({"success": False, "message": "User not found!"})


@app.route("/profile/<username>", methods=["GET"])
def get_profile(username):
    users = load_users()
    user  = users.get(username.lower())
    if not user:
        return jsonify({"success": False, "message": "User not found!"})

    # Use users.json registered_files — accurate filenames!
    my_files = user.get("registered_files", [])
    total    = len(my_files)

    # Build recent with filename
    recent = []
    for f in reversed(my_files[-5:]):
        recent.append({
            "hash"    : f.get("hash", "")[:16] + "...",
            "type"    : f.get("type", "—"),
            "filename": f.get("filename", f.get("file", "Unknown File")),
            "date"    : f.get("date", "—")
        })

    return jsonify({"success": True, "name": user["name"],
                    "email": user["email"], "joined": user.get("joined","—"),
                    "total_registered": total, "recent": recent})


# ══════════════════════════════════════════════════════════
#   QR CODE
# ══════════════════════════════════════════════════════════

@app.route("/qr/<file_hash>", methods=["GET"])
def get_qr(file_hash):
    try:
        import qrcode
        from PIL import Image as PILImage

        # Use RGB tuples — hex colors not supported by qrcode library
        qr = qrcode.QRCode(
            box_size      = 10,
            border        = 4,
            error_correction = qrcode.constants.ERROR_CORRECT_H
        )
        qr.add_data(f"ProofOfOrigin:\n{file_hash}")
        qr.make(fit=True)

        # Blue on dark background using RGB
        img = qr.make_image(
            fill_color  = (19, 127, 236),   # #137fec in RGB
            back_color  = (13, 18, 24)      # #0d1218 in RGB
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        from flask import Response
        return Response(buf.getvalue(), mimetype="image/png",
                        headers={"Cache-Control": "no-cache",
                                 "Access-Control-Allow-Origin": "*"})
    except ImportError:
        return jsonify({"error": "Run: pip install qrcode[pil] pillow"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════
#   PDF CERTIFICATE
# ══════════════════════════════════════════════════════════

@app.route("/certificate", methods=["POST"])
def get_certificate():
    data     = request.json
    filename = data.get("filename", "Unknown File")
    creator  = data.get("creator",  "Unknown")
    ctype    = data.get("type",     "human")
    tx       = data.get("tx",       "")
    fhash    = data.get("hash",     "")
    reg_date = data.get("date",     datetime.now().strftime("%d %B %Y"))

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib          import colors
        from reportlab.lib.units    import cm
        from reportlab.pdfgen       import canvas as rl_canvas

        buf = io.BytesIO()
        W, H = A4
        c    = rl_canvas.Canvas(buf, pagesize=A4)

        # Background
        c.setFillColor(colors.HexColor("#0d1218"))
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Top gradient bar
        c.setFillColor(colors.HexColor("#137fec"))
        c.rect(0, H-3*cm, W, 3*cm, fill=1, stroke=0)

        # Title
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(W/2, H-1.6*cm, "ProofOfOrigin")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#93c5fd"))
        c.drawCentredString(W/2, H-2.3*cm, "Blockchain Content Authentication Certificate")

        # Certificate box
        c.setStrokeColor(colors.HexColor("#137fec"))
        c.setFillColor(colors.HexColor("#111827"))
        c.setLineWidth(1.5)
        c.roundRect(2*cm, H-16*cm, W-4*cm, 12*cm, 12, fill=1, stroke=1)

        # Certificate heading
        c.setFillColor(colors.HexColor("#137fec"))
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(W/2, H-4.5*cm, "CERTIFICATE OF REGISTRATION")

        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 9)
        c.drawCentredString(W/2, H-5.1*cm, "This certifies that the following content has been permanently")
        c.drawCentredString(W/2, H-5.5*cm, "registered on the Ethereum Sepolia blockchain.")

        # Divider
        c.setStrokeColor(colors.HexColor("#1e3a5f"))
        c.setLineWidth(1)
        c.line(3*cm, H-6*cm, W-3*cm, H-6*cm)

        # Details
        def row(label, value, y, val_color="#ffffff"):
            c.setFillColor(colors.HexColor("#64748b"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(3*cm, y, label.upper())
            c.setFillColor(colors.HexColor(val_color))
            c.setFont("Helvetica", 10)
            c.drawString(7.5*cm, y, str(value))

        row("File Name",   filename,  H-7*cm)
        row("Creator",     creator,   H-8*cm)
        row("Content Type", ("🤖 AI Generated" if ctype=="AI" else "👤 Human Created"),
            H-9*cm, "#a78bfa" if ctype=="AI" else "#4ade80")
        row("Date",        reg_date,  H-10*cm)

        # Hash
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(3*cm, H-11.2*cm, "SHA-256 HASH")
        c.setFillColor(colors.HexColor("#137fec"))
        c.setFont("Courier", 8)
        c.drawString(3*cm, H-11.8*cm, fhash)

        if tx:
            c.setFillColor(colors.HexColor("#64748b"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(3*cm, H-12.8*cm, "TRANSACTION")
            c.setFillColor(colors.HexColor("#60a5fa"))
            c.setFont("Courier", 7.5)
            c.drawString(3*cm, H-13.4*cm, f"https://sepolia.etherscan.io/tx/{tx}")

        # Verified badge
        c.setFillColor(colors.HexColor("#052e16"))
        c.setStrokeColor(colors.HexColor("#16a34a"))
        c.setLineWidth(1.5)
        c.roundRect(W/2-3*cm, H-17*cm, 6*cm, 1.2*cm, 8, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#4ade80"))
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(W/2, H-16.4*cm, "✓  VERIFIED ON BLOCKCHAIN")

        # Footer
        c.setFillColor(colors.HexColor("#1e293b"))
        c.rect(0, 0, W, 1.8*cm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#475569"))
        c.setFont("Helvetica", 8)
        c.drawCentredString(W/2, 0.9*cm,
            "BCT Alpha · Batch 19 · ProofOfOrigin v2.0 · Ethereum Sepolia Testnet")

        c.save()
        buf.seek(0)
        pdf_bytes = buf.getvalue()

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype    = "application/pdf",
            headers     = {
                "Content-Disposition": f"attachment; filename=certificate_{fhash[:8]}.pdf",
                "Content-Length"     : str(len(pdf_bytes)),
                "Access-Control-Allow-Origin"      : "*",
                "Access-Control-Expose-Headers"    : "Content-Disposition",
            }
        )
    except ImportError:
        return jsonify({"error": "Run: pip install reportlab"}), 500
    except Exception as e:
        print("PDF error:", str(e))
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════
#   DETECTION ENGINE
# ══════════════════════════════════════════════════════════

def detect_ai_image(file_bytes, filename):
    try:
        from PIL import Image
        img      = Image.open(io.BytesIO(file_bytes))
        info_str = str(img.info).lower()
        ai_tools = {
            "Midjourney"       : ["midjourney","mj v","imagine"],
            "DALL-E"           : ["dall-e","openai","dalle"],
            "Stable Diffusion" : ["stable diffusion","dreamstudio","automatic1111","comfyui"],
            "Adobe Firefly"    : ["adobe firefly","firefly"],
            "Canva AI"         : ["canva"],
            "Bing Copilot"     : ["bing","copilot"],
            "Leonardo AI"      : ["leonardo"],
        }
        for tool, kws in ai_tools.items():
            for kw in kws:
                if kw in info_str:
                    return {"type":"AI","confidence":99,"method":"image_metadata",
                            "reason":f"AI tool signature found: {tool}"}
        if img.format == "PNG":
            params = str(img.info.get("parameters","")).lower()
            if any(k in params for k in ["steps","sampler","cfg scale","seed","model"]):
                return {"type":"AI","confidence":98,"method":"image_metadata",
                        "reason":"Stable Diffusion prompt parameters in PNG"}
        exif_data = None
        try: exif_data = img._getexif()
        except: pass
        if exif_data:
            make = str(exif_data.get(271,"")).lower()
            model= str(exif_data.get(272,"")).lower()
            sw   = str(exif_data.get(305,"")).lower()
            for s in ["midjourney","dall-e","stable diffusion","firefly","canva"]:
                if s in sw or s in make:
                    return {"type":"AI","confidence":97,"method":"image_exif",
                            "reason":f"AI software in EXIF: {sw or make}"}
            if make or model:
                return {"type":"human","confidence":92,"method":"image_exif",
                        "reason":f"Real camera: {(make+' '+model).strip().title()}"}
        ext = filename.lower().rsplit(".",1)[-1]
        if ext in ["jpg","jpeg"] and not exif_data:
            return {"type":"AI","confidence":72,"method":"image_exif",
                    "reason":"No EXIF — real photos always contain camera EXIF"}
        if ext == "png" and not img.info:
            return {"type":"AI","confidence":65,"method":"image_metadata",
                    "reason":"Empty metadata — common in AI-generated images"}
        return {"type":"human","confidence":70,"method":"image_metadata",
                "reason":"No AI signatures found"}
    except ImportError:
        return {"type":"human","confidence":50,"method":"unavailable",
                "reason":"Run: pip install Pillow"}
    except Exception as e:
        return {"type":"human","confidence":50,"method":"error","reason":str(e)}


def detect_ai_text(text):
    import re as _re
    score=0; reasons=[]; tl=text.lower()

    # Strong AI phrases — very reliable signals
    strong_ai=["as an ai","i am an ai","as a language model",
               "i cannot provide","i'm unable to","i don't have personal opinions"]
    sa=sum(1 for p in strong_ai if p in tl)
    if sa>=1: score+=50; reasons.append(f"Strong AI phrase detected")

    # Moderate AI phrases
    mod_ai=["it's important to note","it is worth noting",
            "in conclusion,","to summarize,","in summary,",
            "furthermore,","moreover,","additionally,",
            "it is essential to","on the other hand,",
            "there are several","the following"]
    ma=sum(1 for p in mod_ai if p in tl)
    if ma>=4: score+=40; reasons.append(f"{ma} AI transition phrases")
    elif ma>=2: score+=20; reasons.append(f"{ma} AI transition phrases")

    # Sentence uniformity — AI is very consistent
    sents=[s.strip() for s in _re.split(r'[.!?]+',text) if len(s.strip())>10]
    if len(sents)>=5:
        ls=[len(s) for s in sents]; avg=sum(ls)/len(ls)
        var=sum((l-avg)**2 for l in ls)/len(ls)
        if var<150: score+=30; reasons.append("Highly uniform sentence structure")
        elif var<300: score+=10; reasons.append("Somewhat uniform sentences")

    # Human signals — strong negative score
    strong_human=["tbh","lol","btw","omg","gonna","wanna","idk","smh",
                  "ngl","imo","fyi","asap","brb","wtf","lmao"]
    sh=sum(1 for s in strong_human if s in tl)
    if sh>=1: score-=50; reasons.append(f"Casual slang detected")

    # Contractions — humans use them naturally
    contractions=["i'm","i've","i'll","i'd","don't","can't","won't",
                  "isn't","aren't","wasn't","weren't","haven't","couldn't"]
    ch=sum(1 for s in contractions if s in tl)
    if ch>=3: score-=30; reasons.append(f"{ch} contractions (human pattern)")
    elif ch>=1: score-=15; reasons.append(f"{ch} contraction found")

    # Spelling/grammar errors = human
    common_errors=["recieve","occured","seperate","definately",
                   "untill","beleive","wierd","freind"]
    er=sum(1 for e in common_errors if e in tl)
    if er>=1: score-=40; reasons.append("Spelling errors — human writing")

    # First person casual = human
    casual_first=["i think","i feel","i believe","i guess","i mean",
                  "in my opinion","personally","honestly","actually"]
    cf=sum(1 for s in casual_first if s in tl)
    if cf>=2: score-=20; reasons.append("Personal opinion language")

    # Very structured paragraphs with headers = AI
    paras=[p.strip() for p in text.split('\n\n') if len(p.strip())>50]
    if len(paras)>=5: score+=20; reasons.append("Highly structured format")

    # Determine with higher threshold — needs strong evidence to call AI
    is_ai = score >= 45   # raised from 25 to 45
    conf  = min(95, max(60, abs(score) + 55)) if score != 0 else 65

    return {"type": "AI" if is_ai else "human",
            "confidence": conf,
            "method": "text_heuristic",
            "reason": ", ".join(reasons) if reasons else
                      ("AI writing patterns detected" if is_ai else "Human writing patterns detected")}


def detect_origin(file_bytes, filename):
    ext = filename.lower().rsplit(".",1)[-1] if "." in filename else ""
    if ext in ["jpg","jpeg","png","gif","bmp","webp","tiff"]:
        return detect_ai_image(file_bytes, filename)
    text=None
    for enc in ["utf-8","latin-1","ascii"]:
        try: text=file_bytes.decode(enc); break
        except: continue
    if not text or len(text.strip())<20:
        return {"type":"human","confidence":60,"method":"binary",
                "reason":"Binary file — assumed human-created"}
    return detect_ai_text(text.strip())


# ══════════════════════════════════════════════════════════
#   BLOCKCHAIN ROUTES
# ══════════════════════════════════════════════════════════

@app.route("/hash", methods=["POST"])
def hash_only():
    file       = request.files["file"]
    file_bytes = file.read()
    sha256     = generate_hash(file_bytes)
    detection  = detect_origin(file_bytes, file.filename)

    # Check perceptual similarity for images
    phash_info = generate_phash(file_bytes, file.filename)
    similar    = None
    if phash_info:
        similar = find_similar_image(phash_info['phash'], phash_info['dhash'])

    result = {"hash": sha256, **detection}
    if similar:
        result["similar_found"]    = True
        result["similar_creator"]  = similar.get("creator","Unknown")
        result["similar_date"]     = similar.get("date","Unknown")
        result["similar_filename"] = similar.get("filename","Unknown")
        result["similarity"]       = similar.get("similarity", 0)
        result["original_hash"]    = similar.get("sha256","")
    else:
        result["similar_found"] = False

    return jsonify(result)

@app.route("/register", methods=["POST"])
def register():
    file         = request.files["file"]
    creator      = request.form.get("creator", "Unknown")
    content_type = request.form.get("type", "human")
    username     = request.form.get("username", "").strip().lower()
    file_bytes   = file.read()
    file_hash    = generate_hash(file_bytes)
    _,_,_,exists=contract.functions.verifyContent(file_hash).call()
    if exists:
        # Get original owner details from blockchain
        result  = contract.functions.verifyContent(file_hash).call()
        orig_creator   = result[0]
        orig_timestamp = result[1]
        orig_type      = result[2]
        from datetime import datetime as dt
        reg_date = dt.fromtimestamp(orig_timestamp).strftime("%d %b %Y, %I:%M %p") if orig_timestamp else "Unknown"
        return jsonify({
            "message"       : "Already registered!",
            "hash"          : file_hash,
            "already"       : True,
            "orig_creator"  : orig_creator,
            "orig_type"     : orig_type,
            "orig_date"     : reg_date,
            "orig_timestamp": orig_timestamp
        })
    txn=contract.functions.registerContent(file_hash,creator,content_type).build_transaction(
        {"from":ACCOUNT.address,"nonce":w3.eth.get_transaction_count(ACCOUNT.address),"gas":200000})
    signed=w3.eth.account.sign_transaction(txn,PRIVATE_KEY)
    tx_hash=w3.eth.send_raw_transaction(signed.raw_transaction)
    # Save to user profile using username as exact key
    users = load_users()
    if username and username in users:
        users[username].setdefault("registered_files", []).append({
            "file"    : file.filename,
            "type"    : content_type,
            "hash"    : file_hash,          # store FULL hash for accuracy
            "filename": file.filename,
            "date"    : datetime.now().strftime("%d %b %Y")
        })
        save_users(users)
    # Save perceptual hash to local DB for similarity detection
    phash_info = generate_phash(file_bytes, file.filename)
    if phash_info:
        phash_db = load_phash_db()
        phash_db.append({
            "sha256"  : file_hash,
            "phash"   : phash_info["phash"],
            "dhash"   : phash_info["dhash"],
            "creator" : creator,
            "username": username,
            "filename": file.filename,
            "date"    : datetime.now().strftime("%d %b %Y, %I:%M %p")
        })
        save_phash_db(phash_db)

    return jsonify({"message":"Registered on Blockchain! ✅","hash":file_hash,
                    "tx":tx_hash.hex(),"creator":creator,"type":content_type})

@app.route("/verify", methods=["POST"])
def verify():
    file       = request.files["file"]
    file_bytes = file.read()
    file_hash  = generate_hash(file_bytes)
    result     = contract.functions.verifyContent(file_hash).call()
    creator, timestamp, ctype, exists = result[0], result[1], result[2], result[3]
    if exists:
        return jsonify({"verified": True, "creator": creator, "type": ctype,
                        "timestamp": timestamp, "hash": file_hash})
    return jsonify({"verified": False, "hash": file_hash})


@app.route("/verify-hash", methods=["POST"])
def verify_hash():
    """Verify directly by SHA-256 hash string — no file needed"""
    data      = request.json
    file_hash = data.get("hash", "").strip().lower()
    if not file_hash or len(file_hash) != 64:
        return jsonify({"verified": False, "hash": file_hash,
                        "message": "Invalid hash — must be 64-character SHA-256"})
    try:
        result = contract.functions.verifyContent(file_hash).call()
        creator, timestamp, ctype, exists = result[0], result[1], result[2], result[3]
        if exists:
            return jsonify({"verified": True, "creator": creator, "type": ctype,
                            "timestamp": timestamp, "hash": file_hash})
        return jsonify({"verified": False, "hash": file_hash})
    except Exception as e:
        return jsonify({"verified": False, "hash": file_hash, "error": str(e)})

@app.route("/stats", methods=["GET"])
def get_stats():
    """Global stats — total blockchain counts (for admin/global view)"""
    try:
        events = contract.events.ContentRegistered.create_filter(from_block=0).get_all_entries()
        human  = sum(1 for e in events if e['args'].get('contentType','') == 'human')
        users  = load_users()
        return jsonify({"human": human, "ai": len(events)-human,
                        "total": len(events), "users": len(users)})
    except Exception as e:
        return jsonify({"human":0,"ai":0,"total":0,"users":0,"error":str(e)})


@app.route("/stats/<username>", methods=["GET"])
def get_user_stats(username):
    """Personal stats — uses users.json as exact source of truth"""
    try:
        users = load_users()
        user  = users.get(username.lower())
        if not user:
            return jsonify({"human":0,"ai":0,"total":0,"recent":[]})

        # Use registered_files from users.json — 100% accurate per user
        my_files = user.get("registered_files", [])

        human  = sum(1 for f in my_files if f.get("type","") == "human")
        ai     = sum(1 for f in my_files if f.get("type","") == "AI")
        total  = len(my_files)

        # Recent 5 files
        recent = []
        for f in reversed(my_files[-5:]):
            recent.append({
                "hash"     : f.get("hash","")[:16] + "...",
                "type"     : f.get("type",""),
                "filename" : f.get("filename", f.get("file","")),
                "date"     : f.get("date","—")
            })

        return jsonify({
            "human"  : human,
            "ai"     : ai,
            "total"  : total,
            "recent" : recent,
            "name"   : user["name"],
            "joined" : user.get("joined","—")
        })
    except Exception as e:
        print("User stats error:", str(e))
        return jsonify({"human":0,"ai":0,"total":0,"recent":[],"error":str(e)})

# ══════════════════════════════════════════════════════════
#   ADMIN ROUTES
# ══════════════════════════════════════════════════════════

@app.route("/admin/users", methods=["GET"])
def admin_get_users():
    """Return all users with their registration data"""
    try:
        users = load_users()
        users_list = []
        for username, user in users.items():
            users_list.append({
                "username"        : username,
                "name"            : user.get("name",""),
                "email"           : user.get("email",""),
                "joined"          : user.get("joined",""),
                "blocked"         : user.get("blocked", False),
                "registered_files": user.get("registered_files",[])
            })
        return jsonify({"success": True, "users": users_list, "total": len(users_list)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "users": []})


@app.route("/admin/blockchain", methods=["GET"])
def admin_get_blockchain():
    """Return all blockchain records"""
    try:
        events  = contract.events.ContentRegistered.create_filter(from_block=0).get_all_entries()
        records = []
        for e in events:
            ts = e['args'].get('time', 0)
            records.append({
                "hash"   : e['args'].get('contentHash',''),
                "creator": e['args'].get('creator',''),
                "type"   : e['args'].get('contentType',''),
                "date"   : datetime.fromtimestamp(ts).strftime("%d %b %Y, %I:%M %p") if ts else "—",
                "tx"     : e.transactionHash.hex() if hasattr(e,'transactionHash') else ""
            })
        return jsonify({"success": True, "records": records, "total": len(records)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "records": []})


@app.route("/admin/alerts", methods=["GET"])
def admin_get_alerts():
    """Detect suspicious activity — high AI uploads, duplicates"""
    try:
        users   = load_users()
        alerts  = []

        for username, user in users.items():
            files = user.get("registered_files", [])
            total = len(files)
            if total == 0:
                continue

            # Alert: More than 80% AI content
            ai_count = sum(1 for f in files if f.get("type","") == "AI")
            if total >= 3 and ai_count / total >= 0.8:
                alerts.append({
                    "type"    : "High AI Content",
                    "message" : f"{user.get('name')} has {ai_count}/{total} files flagged as AI-generated.",
                    "user"    : user.get("email",""),
                    "date"    : files[-1].get("date","—") if files else "—",
                    "severity": "HIGH"
                })

            # Alert: Rapid uploads (more than 10 files)
            if total > 10:
                alerts.append({
                    "type"    : "Excessive Uploads",
                    "message" : f"{user.get('name')} has uploaded {total} files.",
                    "user"    : user.get("email",""),
                    "date"    : files[-1].get("date","—") if files else "—",
                    "severity": "MEDIUM"
                })

        # Alert: pHash similarity attempts
        phash_db = load_phash_db()
        if len(phash_db) > 0:
            creators = [e.get("creator","") for e in phash_db]
            from collections import Counter
            counts = Counter(creators)
            for creator, count in counts.items():
                if count > 5:
                    alerts.append({
                        "type"    : "Similar Image Pattern",
                        "message" : f"{creator} has {count} visually similar images in the system.",
                        "user"    : creator,
                        "date"    : "—",
                        "severity": "LOW"
                    })

        return jsonify({"success": True, "alerts": alerts, "total": len(alerts)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "alerts": []})


@app.route("/admin/block-user", methods=["POST"])
def admin_block_user():
    """Block or unblock a user"""
    try:
        data     = request.json
        username = data.get("username","").strip().lower()
        action   = data.get("action","block")
        users    = load_users()
        if username not in users:
            return jsonify({"success": False, "message": "User not found"})
        users[username]["blocked"] = (action == "block")
        save_users(users)
        return jsonify({"success": True, "message": f"User {action}ed successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    app.run(debug=True)