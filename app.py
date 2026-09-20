import os
import json
import threading 
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

# --- 2. CLOUD ENVIRONMENT PERSISTENCE LEDGER ---
GLOBAL_LEDGER = {"total_visits": 100, "file_views": {}, "cloudinary_urls": {}}

def load_starts():
    return GLOBAL_LEDGER

def save_status(starts):
    global GLOBAL_LEDGER
    GLOBAL_LEDGER = starts

# =======================================================
# 🌐 FILE VALIDATION FILTER MECHANICS
# =======================================================
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt', 'rtf', 'odt', 'ppt', 'pptx', 'pps', 'key', 'xls', 'xlsx', 'csv', 'zip', 'rar', '7z', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS

# =======================================================
# 🌐 WEBPAGE ENDPOINTS ROUTING MATRIX
# =======================================================

@app.route('/')
def home():
    starts = load_starts()
    files = list(starts.get('cloudinary_urls', {}).keys())
    
    # ✅ DUAL COMPATIBILITY FIXED: Sets both variables so your dashboard works no matter which one your HTML checks for!
    is_admin = session.get('logged_in') == True
    session['is_admin'] = is_admin 

    if 'has_visited' not in session:
        starts['total_visits'] += 1
        save_status(starts)
        session['has_visited'] = True

    return render_template('index.html', files=files, is_admin=is_admin, total_visits=starts['total_visits'], file_views=starts['file_views'])

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'paper_file' not in request.files:
        return redirect('/')
        
    file = request.files['paper_file']
    unit = request.form['unit_code'].strip().upper().replace(' ', '_')
    year = request.form['year'].strip() 
    
    if file and file.filename != '' and allowed_file(file.filename):
        parts = file.filename.rsplit('.', 1)
        ext = parts[-1].lower()
        original_title = parts[0].replace(" ", "_").replace(".", "_")
        
        clean_filename = f"{unit}_{year}_{original_title}.{ext}"
        cloudinary_public_id = f"{unit}_{year}_{original_title}"
        
        try:
            upload_result = cloudinary.uploader.upload(
                file,
                public_id = cloudinary_public_id,
                resource_type = "auto"
            )
            
            secure_url = upload_result.get('secure_url')
            
            starts = load_starts()
            starts['cloudinary_urls'][clean_filename] = secure_url
            starts['file_views'][clean_filename] = 0
            save_status(starts)
            
            session['download_credit'] = True
            flash(f"🤝 Thank you for contributing! Material for {unit} ({year}) uploaded. Access Unlocked! 🎉") 
        except Exception as e:
            flash(f"❌ Cloud storage engine upload error occurred: {str(e)}")
            
    return redirect('/')

# ✅ ADMIN LOGIN SYSTEM FIXED
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
    
    starts = load_starts()
    
    if filename not in starts.get('cloudinary_urls', {}):
        flash("Error: Requested file resource not found in repository cloud matrix.")
        return redirect('/')
        
    if filename not in starts['file_views']:
        starts['file_views'][filename] = 0
        
    starts['file_views'][filename] += 1
    save_status(starts)    
    
    return redirect(starts['cloudinary_urls'][filename])

@app.route('/delete/<filename>')
def delete_file(filename):
    if not session.get('logged_in'):
        flash("Unauthorized access! Only the Admin can delete past papers")
        return redirect('/')

    starts = load_starts()
    
    if filename in starts.get('cloudinary_urls', {}):
        try:
            parts = filename.rsplit('.', 1)
            public_id = parts[0]
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
            
        del starts['cloudinary_urls'][filename]
        if filename in starts.get('file_views', {}):
            del starts['file_views'][filename]
        save_status(starts)
        
        flash(f"File '{filename}' was successfully removed from cloud repository vaults!")
    else:
        flash("Error: File could not be found.")
        
    return redirect('/')
  
@app.route('/search', methods=['GET'])
def serch_materials():
    query = request.args.get('query', '').strip().lower()
    starts = load_starts()
    is_admin = session.get('logged_in') == True        
    
    if not query:
        return redirect('/')
    
    all_files = list(starts.get('cloudinary_urls', {}).keys())
    filtered_files = [file for file in all_files if query in file.lower()]

    if not filtered_files:
        flash(f"🔍 No repository materials found matching '{query}'. Be the first to upload it below! 📁")
        return render_template('index.html', files=[], is_admin=is_admin, total_visits=starts['total_visits'], file_views=starts['file_views'])

    return render_template('index.html', files=filtered_files, is_admin=is_admin, total_visits=starts['total_visits'], file_views=starts['file_views'])           

@app.errorhandler(413)
def file_too_large(error):
    flash("❌ Upload Denied: That file is way too big! The maximum size allowed is 16MB.")
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


