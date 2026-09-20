import os
import shelve
import threading 
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ADMIN_PASSWORD = 'collins77.'

app.secret_key = os.environ.get('SECRET_KEY', 'comrade_hub_super_secret_session_key')

# --- 1. CLOUDINARY CONFIGURATION ---
cloudinary.config( 
  cloud_name = os.environ.get('CLOUD_NAME', 'YOUR_CLOUD_NAME'), 
  api_key = os.environ.get('API_KEY', 'YOUR_API_KEY'), 
  api_secret = os.environ.get('API_SECRET', 'YOUR_API_SECRET'),
  secure = True
)

# --- 2. PERMANENT DISK STORAGE LEDGER (SHELVE ENGINE) ---
DB_FILE = os.path.join(os.path.dirname(__file__), 'comrade_vault')
db_lock = threading.Lock()

def init_db():
    with db_lock:
        with shelve.open(DB_FILE, writeback=True) as db:
            if 'total_visits' not in db:
                db['total_visits'] = 100
            if 'file_views' not in db:
                db['file_views'] = {}
            if 'cloudinary_urls' not in db:
                db['cloudinary_urls'] = {}

# Run database initializer instantly on startup
init_db()

# --- 3. CORE ROUTE INTERFACES ---

@app.route('/')
def home():
    is_admin = session.get('logged_in') == True
    session['is_admin'] = is_admin 

    with db_lock:
        with shelve.open(DB_FILE) as db:
            total_visits = db.get('total_visits', 100)
            file_views = dict(db.get('file_views', {}))
            cloudinary_urls = dict(db.get('cloudinary_urls', {}))
            files = list(cloudinary_urls.keys())

    if 'has_visited' not in session:
        with db_lock:
            with shelve.open(DB_FILE, writeback=True) as db:
                db['total_visits'] = db.get('total_visits', 100) + 1
                total_visits = db['total_visits']
        session['has_visited'] = True

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
        
        # 🎯 FIX VERIFIED: Correctly grabs item indexes from the split list arrays
        if '.' in filename_str:
            parts = filename_str.rsplit('.', 1)
            original_title = parts[0].replace(" ", "_").replace(".", "_")
            ext = parts[1].lower()
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
            
            with db_lock:
                with shelve.open(DB_FILE, writeback=True) as db:
                    db['cloudinary_urls'][clean_filename] = secure_url
                    db['file_views'][clean_filename] = 0
            
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
            flash("Welcome back, Admin! Management controls unlocked. 🔒")
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
        flash("📚 Help a Comrade, Unlock the Vault! Upload/Drop just 1 past paper, assignment summary, or lecture snapshot above to instantly unlock unlimited downloads for your revision session. 🤝")
        return redirect('/')
    
    with db_lock:
        with shelve.open(DB_FILE, writeback=True) as db:
            urls = db.get('cloudinary_urls', {})
            if filename not in urls:
                flash("Error: Requested file resource not found in repository cloud matrix.")
                return redirect('/')
            
            views = db.get('file_views', {})
            if filename not in views:
                views[filename] = 0
            views[filename] += 1
            
            target_url = urls[filename]
            
    return redirect(target_url)

@app.route('/delete/<filename>')
def delete_file(filename):
    if not session.get('logged_in'):
        flash("Unauthorized access! Only the Admin can delete past papers")
        return redirect('/')

    with db_lock:
        with shelve.open(DB_FILE, writeback=True) as db:
            urls = db.get('cloudinary_urls', {})
            views = db.get('file_views', {})
            
            if filename in urls:
                try:
                    parts = filename.rsplit('.', 1)
                    public_id = parts[0]
                    cloudinary.uploader.destroy(public_id)
                except Exception:
                    pass
                    
                del urls[filename]
                if filename in views:
                    del views[filename]
                flash(f"File '{filename}' was successfully removed from cloud repository vaults!")
            else:
                flash("Error: File could not be found.")
                
    return redirect('/')
  
@app.route('/search', methods=['GET'])
def serch_materials():
    query = request.args.get('query', '').strip().lower()
    is_admin = session.get('logged_in') == True        
    
    with db_lock:
        with shelve.open(DB_FILE) as db:
            total_visits = db.get('total_visits', 100)
            file_views = dict(db.get('file_views', {}))
            cloudinary_urls = dict(db.get('cloudinary_urls', {}))
            all_files = list(cloudinary_urls.keys())
            
    if not query:
        return redirect('/')
    
    filtered_files = [file for file in all_files if query in file.lower()]

    if not filtered_files:
        flash(f"🔍 No repository materials found matching '{query}'. Be the first to upload it below! 📁")
        return render_template('index.html', files=[], is_admin=is_admin, total_visits=total_visits, file_views=file_views)

    return render_template('index.html', files=filtered_files, is_admin=is_admin, total_visits=total_visits, file_views=file_views)           

@app.errorhandler(413)
def file_too_large(error):
    flash("❌ Upload Denied: That file is way too big! The maximum size allowed is 16MB.")
    return redirect('/')

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt', 'rtf', 'odt', 'ppt', 'pptx', 'pps', 'key', 'xls', 'xlsx', 'csv', 'zip', 'rar', '7z', 'webp'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS

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


