import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ADMIN_PASSWORD = 'collins77.'

app.secret_key = os.environ.get('SECRET_KEY', 'comrade_hub_super_secret_session_key')

# --- 1. CLOUDINARY ENGINE CONFIGURATION ---
cloudinary.config( 
  cloud_name = os.environ.get('CLOUD_NAME', 'YOUR_CLOUD_NAME'), 
  api_key = os.environ.get('API_KEY', 'YOUR_API_KEY'), 
  api_secret = os.environ.get('API_SECRET', 'YOUR_API_SECRET'),
  secure = True
)

# --- 2. PERMANENT DATABASE ROUTINE WITH SYNTAX STRING FIX ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("⚠️ DATABASE_URL variable missing from environment settings.")
        return None
        
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://", 1)
        
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"❌ DATABASE CONNECTIVITY REJECTED: {str(e)}")
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
        print("✅ DATABASE INITIALIZED: Connected to permanent cloud tables layout smoothly.")
    else:
        print("⚠️ FALLBACK WARNING: Web service running on temporary server memory.")

try:
    init_db()
except Exception as e:
    print(f"Database initialization step crashed: {str(e)}")

LOCAL_FALLBACK = {"total_visits": 105, "file_views": {}, "cloudinary_urls": {}}
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt', 'rtf', 'odt', 'ppt', 'pptx', 'pps', 'key', 'xls', 'xlsx', 'csv', 'zip', 'rar', '7z', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    is_admin = session.get('logged_in') == True
    session['is_admin'] = is_admin 
    total_visits = 100
    file_views = {}
    cloudinary_urls = {}

    conn = get_db_connection()
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT value FROM analytics WHERE key = 'total_visits';")
            res = cur.fetchone()
            if res: total_visits = res['value']

            cur.execute("SELECT filename, cloudinary_url, views FROM repo_files;")
            rows = cur.fetchall()
            for row in rows:
                cloudinary_urls[row['filename']] = row['cloudinary_url']
                file_views[row['filename']] = row['views']
        
        if 'has_visited' not in session:
            with conn.cursor() as cur:
                cur.execute("UPDATE analytics SET value = value + 1 WHERE key = 'total_visits';")
            conn.commit()
            total_visits += 1
            session['has_visited'] = True
        conn.close()
    else:
        total_visits = LOCAL_FALLBACK["total_visits"]
        file_views = LOCAL_FALLBACK["file_views"]
        cloudinary_urls = LOCAL_FALLBACK["cloudinary_urls"]

    files = list(cloudinary_urls.keys())
    return render_template('index.html', files=files, is_admin=is_admin, total_visits=total_visits, file_views=file_views)
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'paper_file' not in request.files:
        return redirect('/')
        
    file = request.files['paper_file']
    unit = request.form['unit_code'].strip().upper().replace(' ', '_')
    year = request.form['year'].strip() 
    
    if file and file.filename != '' and allowed_file(file.filename):
        filename_str = file.filename
        
        # 🎯 BUG FIX CONFIRMED: Correct extraction using exact index list positions
        if '.' in filename_str:
            parts = filename_str.rsplit('.', 1)
            name_part = str(parts[0])
            ext = str(parts[1]).lower()
            original_title = name_part.replace(" ", "_").replace(".", "_")
        else:
            original_title = filename_str.replace(" ", "_")
            ext = "pdf"
            
        clean_filename = f"{unit}_{year}_{original_title}.{ext}"
        cloudinary_public_id = f"{unit}_{year}_{original_title}"
        
        try:
            upload_result = cloudinary.uploader.upload(
                file,
                public_id = cloudinary_public_id,
                resource_type = "auto"
            )
            secure_url = upload_result.get('secure_url')
            
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO repo_files (filename, cloudinary_url, views) VALUES (%s, %s, 0) ON CONFLICT (filename) DO UPDATE SET cloudinary_url = EXCLUDED.cloudinary_url;",
                        (clean_filename, secure_url)
                    )
                conn.commit()
                conn.close()
            else:
                LOCAL_FALLBACK["cloudinary_urls"][clean_filename] = secure_url
                LOCAL_FALLBACK["file_views"][clean_filename] = 0
            
            session['download_credit'] = True
            flash(f"🤝 Thank you for contributing! Material for {unit} ({year}) uploaded. Access Unlocked! 🎉") 
        except Exception as e:
            flash(f"❌ Cloud storage engine upload error occurred: {str(e)}")
            
    return redirect('/')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        typed_password = request.form.get('password')
        if typed_password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['is_admin'] = True
            flash("Welcome back, Admin! Controls unlocked. 🔒")
            return redirect('/')
        else:
            flash("Incorrect admin password. Access Denied.")
            return redirect('/admin-login')
    return render_template('login.html')

@app.route('/admin-logout')
def admin_logout():
    session.pop('logged_in', None)
    session.pop('is_admin', None)
    flash("Logged out from admin panel.")
    return redirect('/')                

@app.route('/view/<filename>')
def view_file(filename):
    is_admin = session.get('logged_in') == True
    if not is_admin and not session.get('download_credit'):
        flash("📚 Help a Comrade, Unlock the Vault! Upload just 1 paper above to unlock unlimited downloads. 🤝")
        return redirect('/')
    
    cloudinary_url = None
    conn = get_db_connection()
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT cloudinary_url FROM repo_files WHERE filename = %s;", (filename,))
            res = cur.fetchone()
            if res:
                cloudinary_url = res['cloudinary_url']
                cur.execute("UPDATE repo_files SET views = views + 1 WHERE filename = %s;", (filename,))
        conn.commit()
        conn.close()
    else:
        cloudinary_url = LOCAL_FALLBACK["cloudinary_urls"].get(filename)
        if filename in LOCAL_FALLBACK["file_views"]:
            LOCAL_FALLBACK["file_views"][filename] += 1
    
    if not cloudinary_url:
        flash("Error: Requested file resource not found.")
        return redirect('/')
        
    file_extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    download_url = cloudinary_url.replace("/upload/", "/upload/fl_attachment/") if "/upload/" in cloudinary_url else cloudinary_url
    
    return render_template('view.html', filename=filename, extension=file_extension, cloudinary_url=cloudinary_url, download_url=download_url, text_content="")

@app.route('/delete/<filename>')
def delete_file(filename):
    if not session.get('logged_in'):
        flash("Unauthorized access!")
        return redirect('/')
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM repo_files WHERE filename = %s;", (filename,))
        conn.commit()
        conn.close()
        try:
            public_id = filename.rsplit('.', 1)[0] if '.' in filename else filename
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
        flash(f"File '{filename}' was successfully removed.")
    return redirect('/')
  
@app.route('/search', methods=['GET'])
def search_materials():
    query = request.args.get('query', '').strip().lower()
    total_visits = 100
    file_views = {}
    cloudinary_urls = {}
    is_admin = session.get('logged_in') == True        

    conn = get_db_connection()
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT value FROM analytics WHERE key = 'total_visits';")
            res = cur.fetchone()
            if res: total_visits = res['value']
            cur.execute("SELECT filename, cloudinary_url, views FROM repo_files;")
            rows = cur.fetchall()
            for row in rows:
                cloudinary_urls[row['filename']] = row['cloudinary_url']
                file_views[row['filename']] = row['views']
        conn.close()
    else:
        total_visits = LOCAL_FALLBACK["total_visits"]
        file_views = LOCAL_FALLBACK["file_views"]
        cloudinary_urls = LOCAL_FALLBACK["cloudinary_urls"]
    
    if not query:
        return redirect('/')
    all_files = list(cloudinary_urls.keys())
    filtered_files = [file for file in all_files if query in file.lower()]

    if not filtered_files:
        flash(f"🔍 No materials found matching '{query}'. Be the first to upload it below!")
        return render_template('index.html', files=[], is_admin=is_admin, total_visits=total_visits, file_views=file_views)
    return render_template('index.html', files=filtered_files, is_admin=is_admin, total_visits=total_visits, file_views=file_views)           

@app.errorhandler(413)
def file_too_large(error):
    flash("❌ File too big! Maximum size is 16MB.")
    return redirect('/')

@app.route('/privacy-policy')
def privacy_policy(): return render_template('privacy.html', is_admin=session.get('logged_in', False))
@app.route('/terms-of-service')
def terms_of_service(): return render_template('terms.html', is_admin=session.get('logged_in', False))
@app.route('/dmca-copyright')
def dmca_copyright(): return render_template('dmca.html', is_admin=session.get('logged_in', False))
@app.route('/about')
def about(): return render_template('about.html', is_admin=session.get('logged_in', False))
@app.route('/contact')
def contact(): return render_template('contact.html', is_admin=session.get('logged_in', False))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
