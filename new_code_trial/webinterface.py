# web_interface.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import time
from datetime import datetime
from camera_pedal import take_photo, check_camera_connection, toggle_timelapse_mode, timelapse_active

# Configuration
USERS_DIR = "lab_users"
ACTIVE_USER_FILE = "active_user.txt"
DEFAULT_USER = "shared"
APP_PORT = 8080  # Web server port

# Initialize Flask app
app = Flask(__name__)

# Ensure user directories exist
def setup_user_system():
    """Set up the user system directories and files if they don't exist"""
    # Create users directory if it doesn't exist
    os.makedirs(USERS_DIR, exist_ok=True)
    
    # Create default user profile if it doesn't exist
    default_user_file = os.path.join(USERS_DIR, f"{DEFAULT_USER}.json")
    if not os.path.exists(default_user_file):
        default_user = {
            "name": "Shared Lab Account",
            "dropbox_folder": "/Camera_Pedal_Photos/shared",
            "local_folder": "pedal_triggered_photos/shared"
        }
        with open(default_user_file, 'w') as f:
            json.dump(default_user, f, indent=4)
    
    # Create or check active user file
    if not os.path.exists(ACTIVE_USER_FILE):
        with open(ACTIVE_USER_FILE, 'w') as f:
            f.write(DEFAULT_USER)

# User management functions
def get_all_users():
    """Get a list of all configured users"""
    users = []
    for filename in os.listdir(USERS_DIR):
        if filename.endswith('.json'):
            username = filename[:-5]  # Remove .json extension
            with open(os.path.join(USERS_DIR, filename), 'r') as f:
                user_data = json.load(f)
                users.append({
                    "username": username,
                    "display_name": user_data.get("name", username)
                })
    return sorted(users, key=lambda x: x["display_name"])

def get_active_user():
    """Get the currently active user"""
    if not os.path.exists(ACTIVE_USER_FILE):
        return DEFAULT_USER
    
    with open(ACTIVE_USER_FILE, 'r') as f:
        return f.read().strip()

def set_active_user(username):
    """Set the active user"""
    with open(ACTIVE_USER_FILE, 'w') as f:
        f.write(username)
    print(f"✅ Active user set to: {username}")
    return True

def get_user_config(username=None):
    """Get the configuration for the specified user or active user"""
    if username is None:
        username = get_active_user()
    
    user_file = os.path.join(USERS_DIR, f"{username}.json")
    if not os.path.exists(user_file):
        print(f"⚠️ User '{username}' not found, using default user")
        username = DEFAULT_USER
        user_file = os.path.join(USERS_DIR, f"{username}.json")
    
    with open(user_file, 'r') as f:
        return json.load(f)

def create_or_update_user(username, display_name, dropbox_folder=None):
    """Create a new user or update an existing one"""
    if not username.isalnum() and not all(c.isalnum() or c == '_' for c in username):
        return False, "Username should contain only letters, numbers, or underscores"
    
    # Set default paths if not provided
    if dropbox_folder is None:
        dropbox_folder = f"/Camera_Pedal_Photos/{username}"
    
    # Create user data
    user_data = {
        "name": display_name,
        "dropbox_folder": dropbox_folder,
        "local_folder": f"pedal_triggered_photos/{username}"
    }
    
    # Save user file
    user_file = os.path.join(USERS_DIR, f"{username}.json")
    file_existed = os.path.exists(user_file)
    
    with open(user_file, 'w') as f:
        json.dump(user_data, f, indent=4)
    
    # Make sure the local folder exists
    os.makedirs(user_data["local_folder"], exist_ok=True)
    
    return True, f"User '{username}' {'updated' if file_existed else 'created'}"

# Camera control functions
def take_photo_for_user():
    """Take a photo using the current user's configuration"""
    user_config = get_user_config()
    # Set the photo directory for the current user
    os.environ['PHOTO_DIR'] = user_config['local_folder']
    return take_photo()

def check_camera_status():
    """Check if the camera is connected and working"""
    return check_camera_connection()

# Flask routes
@app.route('/')
def index():
    """Main page - user selection and camera control"""
    users = get_all_users()
    active_user = get_active_user()
    camera_status = check_camera_status()
    active_user_data = get_user_config(active_user)
    
    return render_template('index.html', 
                         users=users, 
                         active_user=active_user,
                         active_user_data=active_user_data,
                         camera_status=camera_status,
                         timelapse_active=timelapse_active)

@app.route('/set_user', methods=['POST'])
def set_user():
    """Set the active user"""
    username = request.form['username']
    success = set_active_user(username)
    
    if success:
        return redirect(url_for('index'))
    else:
        return "Error setting user", 400

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user"""
    username = request.form['username']
    display_name = request.form['display_name']
    dropbox_folder = request.form.get('dropbox_folder', '')
    
    if not dropbox_folder:
        dropbox_folder = None
    
    success, message = create_or_update_user(username, display_name, dropbox_folder)
    
    if request.form.get('set_active', 'off') == 'on':
        set_active_user(username)
    
    return redirect(url_for('index'))

@app.route('/take_photo', methods=['POST'])
def trigger_photo():
    """Trigger a photo capture for the current user"""
    try:
        success = take_photo_for_user()
        return jsonify({'success': success, 'message': 'Photo captured successfully' if success else 'Failed to capture photo'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error capturing photo: {str(e)}'})

@app.route('/check_camera', methods=['GET'])
def check_camera():
    """Check camera connection status"""
    try:
        connected = check_camera_status()
        return jsonify({'connected': connected})
    except Exception as e:
        return jsonify({'connected': False, 'error': str(e)})

@app.route('/toggle_timelapse', methods=['POST'])
def toggle_timelapse():
    """Toggle timelapse mode on/off"""
    try:
        toggle_timelapse_mode()
        return jsonify({'success': True, 'timelapse_active': timelapse_active})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error toggling timelapse: {str(e)}'})

@app.route('/api/current_user', methods=['GET'])
def api_current_user():
    """API endpoint to get current user - for the camera script to query"""
    active_user = get_active_user()
    user_config = get_user_config(active_user)
    
    return jsonify({
        "username": active_user,
        "display_name": user_config.get("name", active_user),
        "dropbox_folder": user_config.get("dropbox_folder"),
        "local_folder": user_config.get("local_folder")
    })

# Start the web server
def run_webserver():
    """Run the Flask web server"""
    # Determine IP address for easier access from other devices
    import socket
    hostname = socket.gethostname()
    try:
        ip_address = socket.gethostbyname(hostname)
    except:
        ip_address = "0.0.0.0"
    
    print(f"✨ Web interface starting at http://{ip_address}:{APP_PORT}")
    print(f"Access from other devices at http://{ip_address}:{APP_PORT}")
    app.run(host='0.0.0.0', port=APP_PORT)

if __name__ == "__main__":
    setup_user_system()
    run_webserver()