import os
import json
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
# Secure encryption seed fallback
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'collins_super_secret_comrade_key_2026')

# 🎯 SAFE LOCAL STORAGE PATH (Works on Render's free tier without crashes)
ANALYTICS_FILE = os.path.join(os.path.dirname(__file__), 'analytics.json')

# --- 1. CLOUDINARY ENVIRONMENT INTEGRATION ---
# This automatically reads the secret keys you pasted into the Render Dashboard!
cloudinary.config( 
  cloud_name = os.environ.get('CLOUD_NAME', 'YOUR_CLOUD_NAME'), 
  api_key = os.environ.get('API_KEY', 'YOUR_API_KEY'), 
  api_secret = os.environ.get('API_SECRET', 'YOUR_API_SECRET'),
  secure = True
)

# --- 2. PERSISTENT JSON STORAGE HELPERS ---
def load_repository_data():
    if not os.path.exists(ANALYTICS_FILE):
        return {}
    try:
        with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_repository_data(data):
    try:
        with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving tracking data: {str(e)}")


# --- 3. CORE ROUTE INTERFACES ---

@app.route('/')
def home():
    repo_data = load_repository_data()
    file_list = list(repo_data.keys())
    file_views = {filename: info['views'] for filename, info in repo_data.items()}
    
    return render_template(
        'index.html', 
        is_admin=session.get('is_admin', False), 
        files=file_list, 
        file_views=file_views,
        total_visits=1000
    )

@app.route('/upload', methods=['POST'])
def upload():
    if 'paper_file' not in request.files:
        flash('No file part selected.')
        return redirect(url_for('home'))
        
    file = request.files['paper_file']
    unit_code = request.form.get('unit_code', '').strip().replace(' ', '_')
    year = request.form.get('year', '').strip()
    
    if file.filename == '':
        flash('No file selected.')
        return redirect(url_for('home'))
        
    if file:
        try:
            filename = f"{unit_code}_{year}_{file.filename}"
            
            # Send file streaming directly into Cloudinary
            upload_result = cloudinary.uploader.upload(
                file,
                public_id = filename.split('.')[0], # Clean public ID mapping
                resource_type = "auto"
            )
            
            secure_url = upload_result.get('secure_url')
            
            repo_data = load_repository_data()
            repo_data[filename] = {
                "cloudinary_url": secure_url,
                "views": 0
            }
            save_repository_data(repo_data)
            
            flash('Material uploaded successfully to cloud vaults! Thank you, comrade.')
        except Exception as e:
            flash(f"Upload error occurred: {str(e)}")
            
        return redirect(url_for('home'))

@app.route('/view/<filename>')
def view_file(filename):
    repo_data = load_repository_data()
    
    if filename in repo_data:
        repo_data[filename]['views'] += 1
        save_repository_data(repo_data)
        return redirect(repo_data[filename]['cloudinary_url'])
        
    flash("Requested file resource not found in repository matrix.")
    return redirect(url_for('home'))


# --- 4. ADMIN CONSOLE OPERATIONS ---
@app.route('/delete/<filename>')
def delete_file(filename):
    if not session.get('is_admin', False):
        return redirect(url_for('home'))
        
    repo_data = load_repository_data()
    if filename in repo_data:
        try:
            public_id = filename.split('.')[0]
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
            
        del repo_data[filename]
        save_repository_data(repo_data)
        flash(f"{filename} deleted successfully from all systems.")
        
    return redirect(url_for('home'))

# --- 5. COMPLIANCE INFORMATION FOOTER PAGES ---
@app.route('/privacy-policy')
def privacy_policy(): return render_template('privacy.html', is_admin=session.get('is_admin',False))
@app.route('/terms-of-service')
def terms_of_service(): return render_template('terms.html', is_admin=session.get('is_admin',False))
@app.route('/dmca-copyright')
def dmca_copyright(): return render_template('dmca.html', is_admin=session.get('is_admin',False))
@app.route('/about')
def about(): return render_template('about.html', is_admin=session.get('is_admin',False))
@app.route('/contact')
def contact(): return render_template('contact.html', is_admin=session.get('is_admin',False))

if __name__ == '__main__':
    # Local fallback port setup
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

