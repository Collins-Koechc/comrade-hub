import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
# STORAGE SECURITY GATE: Hard limit uploads to 5MB max to prevent storage abuse
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'collins77.')

app.secret_key = os.environ.get('SECRET_KEY', 'comrade_hub_super_secret_session_key')

# --- 1. CLOUDINARY ENGINE CONFIGURATION ---
cloudinary.config(
    cloud_name=os.environ.get('CLOUD_NAME', 'YOUR_CLOUD_NAME'),
    api_key=os.environ.get('API_KEY', 'YOUR_API_KEY'),
    api_secret=os.environ.get('API_SECRET', 'YOUR_API_SECRET'),
    secure=True
)

# --- 2. DATABASE ROUTINE ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("⚠️ DATABASE_URL variable missing.")
        return None
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://", 1)
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    key TEXT PRIMARY KEY,
                    value INT DEFAULT 100
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS repo_files (
                    filename TEXT PRIMARY KEY,
                    cloudinary_url TEXT NOT NULL,
                    views INT DEFAULT 0
                );
            """)
            cur.execute("INSERT INTO analytics (key, value) VALUES ('total_visits', 100) ON CONFLICT DO NOTHING;")
        conn.commit()
        conn.close()
        print("✅ DATABASE INITIALIZED: Connected successfully.")
    else:
        print("❌ DATABASE INITIALIZATION FAILED: Check your Render Environment variables!")

try:
    init_db()
except Exception as e:
    print(f"Database init crashed: {str(e)}")

ALLOWED_EXTENSIONS = {'pdf','png','jpg','jpeg','doc','docx','txt','rtf','odt','ppt','pptx','pps','key','xls','xlsx','csv','zip','rar','7z','webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS
@app.route('/')
def home():
    is_admin = session.get('logged_in') == True
    session['is_admin'] = is_admin
    total_visits = 100
    file_views = {}
    cloudinary_urls = {}
    
    # 🧭 Secure Pagination Query Param Handling
    try:
        page = int(request.args.get('page', 1))
        if page < 1: page = 1
    except ValueError:
        page = 1
        
    per_page = 20
    offset = (page - 1) * per_page

    conn = get_db_connection()
    if not conn:
        flash("⚠️ System Warning: Database disconnected. Please contact admin.")
        return render_template('index.html', files=[], is_admin=is_admin, total_visits=100, file_views={}, page=page, has_next=False)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Fetch Total Visit Count Metrics
        cur.execute("SELECT value FROM analytics WHERE key = 'total_visits';")
        res = cur.fetchone()
        if res:
            total_visits = res['value']
            
        # ⚡ Fast Batch Loading: Limit resource payload to 20 elements per render block
        cur.execute("SELECT filename, cloudinary_url, views FROM repo_files ORDER BY filename ASC LIMIT %s OFFSET %s;", (per_page, offset))
        rows = cur.fetchall()
        for row in rows:
            cloudinary_urls[row['filename']] = row['cloudinary_url']
            file_views[row['filename']] = row['views']
            
        # Dynamic Counter to calculate matrix bounds
        cur.execute("SELECT COUNT(*) FROM repo_files;")
        total_files = cur.fetchone()['count']
        has_next = (offset + per_page) < total_files
            
        if 'has_visited' not in session:
            with conn.cursor() as cur:
                cur.execute("UPDATE analytics SET value = value + 1 WHERE key = 'total_visits';")
            conn.commit()
            total_visits += 1
            session['has_visited'] = True
    conn.close()
    
    files = list(cloudinary_urls.keys())
    return render_template('index.html', files=files, is_admin=is_admin, total_visits=total_visits, file_views=file_views, page=page, has_next=has_next)
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'paper_file' not in request.files:
        return redirect('/')
    file = request.files['paper_file']
    unit = request.form['unit_code'].strip().upper().replace(' ', '_')
    year = request.form['year'].strip()
    
    if file and file.filename != '' and allowed_file(file.filename):
        filename_str = file.filename
        if '.' in filename_str:
            parts = filename_str.rsplit('.', 1)
            name_part = parts[0]
            ext = parts[1].lower()
            original_title = name_part.replace(" ", "_").replace(".", "_")
        else:
            original_title = filename_str.replace(" ", "_")
            ext = "pdf"
        clean_filename = f"{unit}_{year}_{original_title}.{ext}"
        cloudinary_public_id = f"{unit}_{year}_{original_title}"
        
        try:
            conn = get_db_connection()
            if not conn:
                flash("❌ Upload failed: Could not establish secure cloud database connection.")
                return redirect('/')

            upload_result = cloudinary.uploader.upload(
                file, 
                public_id=cloudinary_public_id, 
                resource_type="auto"
            )
            secure_url = upload_result.get('secure_url')
            
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO repo_files (filename, cloudinary_url, views) VALUES (%s, %s, 0) ON CONFLICT (filename) DO UPDATE SET cloudinary_url = EXCLUDED.cloudinary_url;",
                    (clean_filename, secure_url)
                )
            conn.commit()
            conn.close()
            
            session['download_credit'] = True
            flash(f"🤝 Thank you! Material for {unit} ({year}) uploaded permanently.")
        except Exception as e:
            flash(f"❌ Upload system error: {str(e)}")
    return redirect('/')

@app.route('/admin-login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        typed_password = request.form.get('password')
        if typed_password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['is_admin'] = True
            flash("Welcome back, Admin!")
            return redirect('/')
        else:
            flash("Incorrect password.")
            return redirect('/admin-login')
    return render_template('login.html')

@app.route('/admin-logout')
def admin_logout():
    session.pop('logged_in', None)
    session.pop('is_admin', None)
    flash("Logged out.")
    return redirect('/')

@app.route('/view/<filename>')
def view_file(filename):
    is_admin = session.get('logged_in') == True
    if not is_admin and not session.get('download_credit'):
        flash("📚 Upload one file to unlock downloads.")
        return redirect('/')
    
    cloudinary_url = None
    conn = get_db_connection()
    if not conn:
        flash("❌ Database error: Could not fetch file resource links.")
        return redirect('/')
        
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT cloudinary_url FROM repo_files WHERE filename = %s;", (filename,))
        res = cur.fetchone()
        if res:
            cloudinary_url = res['cloudinary_url']
        cur.execute("UPDATE repo_files SET views = views + 1 WHERE filename = %s;", (filename,))
    conn.commit()
    conn.close()

    if not cloudinary_url:
        flash("Error: File not found in registry database.")
        return redirect('/')
        
    file_extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    download_url = cloudinary_url.replace("/upload/", "/upload/fl_attachment/") if "/upload/" in cloudinary_url else cloudinary_url
    return render_template('view.html', filename=filename, extension=file_extension, cloudinary_url=cloudinary_url, download_url=download_url, text_content="")

@app.route('/delete/<filename>')
def delete_file(filename):
    if not session.get('logged_in'):
        flash("Unauthorized! Admin only.")
        return redirect('/')
    
    conn = get_db_connection()
    if not conn:
        flash("❌ Error: Could not connect to database to perform delete action.")
        return redirect('/')
        
    with conn.cursor() as cur:
        cur.execute("DELETE FROM repo_files WHERE filename = %s;", (filename,))
    conn.commit()
    conn.close()
    return redirect('/')
@app.route('/search')
def search_materials():
    is_admin = session.get('logged_in') == True
    session['is_admin'] = is_admin
    
    # 🔍 Extract the search term entered by the student
    query = request.args.get('query', '').strip()
    
    if not query:
        return redirect('/')
        
    file_views = {}
    cloudinary_urls = {}
    
    conn = get_db_connection()
    if not conn:
        flash("⚠️ Search Error: Database connection lost.")
        return redirect('/')
        
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ⚡ Smart case-insensitive search matching institution, code, or name parameters
        search_pattern = f"%{query}%"
        cur.execute(
            "SELECT filename, cloudinary_url, views FROM repo_files WHERE filename ILIKE %s ORDER BY filename ASC LIMIT 40;", 
            (search_pattern,)
        )
        rows = cur.fetchall()
        for row in rows:
            cloudinary_urls[row['filename']] = row['cloudinary_url']
            file_views[row['filename']] = row['views']
    conn.close()
    
    matching_files = list(cloudinary_urls.keys())
    
    # Reuses your home layout to display search matches instantly on screen!
    return render_template(
        'index.html', 
        files=matching_files, 
        is_admin=is_admin, 
        total_visits=100, 
        file_views=file_views, 
        page=1, 
        has_next=False
    )

# ─── FINAL SERVER EXECUTION MATRIX GATEWAY ───
if __name__ == '__main__':
    app.run(debug=False)
