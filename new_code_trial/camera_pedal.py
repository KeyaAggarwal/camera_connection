import hid
import subprocess
import time
import os
import shutil
import threading
from datetime import datetime
import dropbox
from dropbox.exceptions import AuthError
from dropbox.files import WriteMode

# Import our Dropbox OAuth module
import dropbox_oauth

# HID device identifiers for the foot pedal
VENDOR_ID = 0x04b4
PRODUCT_ID = 0x5555

# Camera capture command that works 
CAMERA_COMMAND = ["sudo", "gphoto2", "--camera=Canon EOS 700D", "--capture-image-and-download"]

# Set up a directory to save the photos
PHOTO_DIR = "pedal_triggered_photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

# Keep track of the last pedal state
last_state = None
DEBOUNCE_TIME = 0.5  # seconds
last_trigger_time = 0

# Camera connection maintenance
CAMERA_CHECK_INTERVAL = 300  # Check camera connection every 5 minutes
last_camera_check = time.time()
camera_connected = True

# Timelapse parameters
TIMELAPSE_INTERVAL = 180  # Take a photo every 3 minutes
timelapse_active = False
timelapse_thread = None
timelapse_stop_event = threading.Event()

# Pedal press counting for timelapse mode
pedal_presses = []
TIMELAPSE_TRIGGER_COUNT = 5
TIMELAPSE_TRIGGER_WINDOW = 20  # seconds

def upload_to_dropbox(local_file_path, dropbox_folder_path):
    """Upload a file to Dropbox and return success status."""
    try:
        # Get a valid access token using our OAuth module
        access_token = dropbox_oauth.get_valid_access_token()
        if not access_token:
            print("❌ Could not get valid Dropbox access token")
            return False
            
        # Initialize Dropbox client with the valid token
        dbx = dropbox.Dropbox(access_token)
        
        # Check if the token is valid
        try:
            dbx.users_get_current_account()
        except AuthError as e:
            print(f"❌ Dropbox auth error: {e}")
            return False
        
        # Open the local file
        with open(local_file_path, 'rb') as f:
            file_name = os.path.basename(local_file_path)
            dropbox_path = f"{dropbox_folder_path}/{file_name}"
            
            # Upload the file
            print(f"📤 Uploading {file_name} to Dropbox folder {dropbox_folder_path}...")
            dbx.files_upload(f.read(), dropbox_path, mode=WriteMode('overwrite'))
            
            print(f"✅ Successfully uploaded to Dropbox as {dropbox_path}")
            return True
    
    except Exception as e:
        print(f"❌ Dropbox upload error: {e}")
        return False

def check_camera_connection():
    """Check if camera is still connected and reconnect if needed."""
    global camera_connected
    
    try:
        # Run a simple gphoto2 command to check camera connection
        check_cmd = ["gphoto2", "--camera=Canon EOS 700D", "--auto-detect"]
        result = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Check if our camera model is in the output
        if "Canon EOS 700D" in result.stdout:
            if not camera_connected:
                print("✅ Camera reconnected successfully")
            camera_connected = True
            return True
        else:
            print("❌ Camera not detected, attempting to reconnect...")
            camera_connected = False
            
            # Try to reset USB connections
            reset_cmd = ["gphoto2",  "--camera=Canon EOS 700D", "--reset"]
            subprocess.run(reset_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # Give camera time to initialize
            
            # Check again after reset
            result = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "Canon EOS 700D" in result.stdout:
                print("✅ Camera reconnected after reset")
                camera_connected = True
                return True
            else:
                print("⚠️ Could not reconnect camera")
                return False
    
    except Exception as e:
        print(f"⚠️ Error checking camera connection: {e}")
        camera_connected = False
        return False

def take_photo(timelapse_mode=False):
    """Take a photo with the camera and save it to the appropriate folder."""
    global camera_connected
    
    current_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # Add timelapse info to timestamp if in timelapse mode
    if timelapse_mode:
        print("in timelapse mode")
        timestamp = f"timelapse_{timestamp}"
    
    # Create local date folder if needed
    date_folder = os.path.join(PHOTO_DIR, today_date)
    os.makedirs(date_folder, exist_ok=True)
    
    # Only proceed if camera is connected or we can reconnect it
    if not camera_connected:
        if not check_camera_connection():
            print("⚠️ Camera disconnected - cannot take photo")
            return False
    
    # Run the camera capture command
    try:
        result = subprocess.run(
            CAMERA_COMMAND, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            timeout=30  # Add timeout to prevent hanging
        )
        
        if result.returncode == 0:
            print("✅ Photo captured successfully!")
            
            # Find the captured image file and move it to the date folder
            uploaded_files = []
            for file in os.listdir("."):
                if file.endswith(".jpg") or file.endswith(".cr2"):
                    if os.path.isfile(file) and os.path.getmtime(file) > current_time - 5:
                        new_name = f"{timestamp}_{file}"
                        local_path = os.path.join(date_folder, new_name)
                        shutil.move(file, local_path)
                        print(f"📸 Saved locally as: {local_path}")
                        
                        # Get the current user's Dropbox folder from webinterface
                        from webinterface import get_user_config
                        user_config = get_user_config()
                        user_folder = user_config.get("dropbox_folder", "/Camera_Pedal_Photos/shared")
                        
                        # Create the Dropbox path with user folder and date
                        dropbox_folder = f"{user_folder}/{today_date}"
                        
                        # Upload to Dropbox
                        upload_success = upload_to_dropbox(local_path, dropbox_folder)
                        if upload_success:
                            uploaded_files.append(new_name)
            
            if uploaded_files:
                print(f"📂 All files uploaded to Dropbox folder: {dropbox_folder}")
                return True
            else:
                print("⚠️ No files were found to upload")
                return False
        else:
            print("❌ Error capturing photo:")
            print(result.stderr)
            
            # Check if error indicates disconnection
            if "Could not claim the USB device" in result.stderr or "No camera found" in result.stderr:
                camera_connected = False
                check_camera_connection()
            
            return False
    
    except subprocess.TimeoutExpired:
        print("⚠️ Camera command timed out - possible camera sleep or disconnection")
        camera_connected = False
        check_camera_connection()
        return False
    except Exception as camera_error:
        print(f"❌ Camera error: {camera_error}")
        return False

def timelapse_worker():
    """Worker function for timelapse thread."""
    print("🕒 Starting timelapse mode - taking photos every 3 minutes")
    
    # Take an initial photo immediately when starting timelapse
    take_photo(timelapse_mode=True)
    
    while not timelapse_stop_event.is_set():
        # Sleep for the interval, but check stop_event frequently
        for i in range(TIMELAPSE_INTERVAL):
            if timelapse_stop_event.is_set():
                break
            if i % 60 == 0:  # Log every minute
                print(f"Waited {i} seconds so far...")
            time.sleep(1)
        
        if not timelapse_stop_event.is_set():
            # Check camera connection before taking timelapse photo
            if not camera_connected:
                check_camera_connection()
            
            # Take timelapse photo
            print("🕒 Taking scheduled timelapse photo...")
            take_photo(timelapse_mode=True)
    
    print("🕒 Timelapse mode stopped")

def toggle_timelapse_mode():
    """Toggle timelapse mode on/off."""
    global timelapse_active, timelapse_thread, timelapse_stop_event
    
    if timelapse_active:
        # Stop timelapse
        print("🕒 Stopping timelapse mode...")
        timelapse_stop_event.set()
        if timelapse_thread:
            timelapse_thread.join()
        timelapse_active = False
        print("🕒 Timelapse mode deactivated")
    else:
        # Start timelapse
        print("🕒 Activating timelapse mode...")
        timelapse_stop_event.clear()
        timelapse_thread = threading.Thread(target=timelapse_worker)
        timelapse_thread.daemon = True
        timelapse_thread.start()
        timelapse_active = True
        print("🕒 Timelapse mode activated - photos will be taken every 5 minutes")

def check_rapid_presses():
    """Check if there were 5 presses within 10 seconds."""
    global pedal_presses
    
    # Remove presses older than 10 seconds
    current_time = time.time()
    old_count = len(pedal_presses)
    pedal_presses = [t for t in pedal_presses if current_time - t <= TIMELAPSE_TRIGGER_WINDOW]
    if old_count != len(pedal_presses):
        print(f"Removed {old_count - len(pedal_presses)} old presses, {len(pedal_presses)} remain in window")
    
    # Add current press
    pedal_presses.append(current_time)
    print(f"👣 Pedal press #{len(pedal_presses)} within {TIMELAPSE_TRIGGER_WINDOW} second window")
    
    # Check if we have 5 or more presses within the window
    if len(pedal_presses) >= TIMELAPSE_TRIGGER_COUNT:
        print(f"⚡ Detected {TIMELAPSE_TRIGGER_COUNT} rapid presses within {TIMELAPSE_TRIGGER_WINDOW} seconds!")
        pedal_presses = []  # Reset the counter
        toggle_timelapse_mode()
        return True
    
    return False

# Main function
def main():
    # First, ensure we have a valid Dropbox token
    print("🔐 Checking Dropbox authentication...")
    access_token = dropbox_oauth.get_valid_access_token()
    if not access_token:
        print("❌ Failed to authenticate with Dropbox. Exiting.")
        return
    
    print("✅ Dropbox authentication successful.")
    
    try:
        # Connect to the foot pedal
        pedal = hid.device()
        pedal.open(VENDOR_ID, PRODUCT_ID)
        print("Connected to foot pedal. Waiting for press...")
        print("Press Ctrl+C to exit")
        print(f"Press pedal {TIMELAPSE_TRIGGER_COUNT} times within {TIMELAPSE_TRIGGER_WINDOW} seconds to toggle timelapse mode")
        
        # Initial camera check
        check_camera_connection()
        
        while True:
            # Periodically check camera connection
            current_time = time.time()
            if current_time - last_camera_check > CAMERA_CHECK_INTERVAL:
                print("🔄 Performing routine camera connection check...")
                check_camera_connection()
                last_camera_check = current_time
            
            # Read data from the pedal
            data = pedal.read(64, timeout_ms=100)  # Short timeout for responsiveness
            
            # Only process if we got data
            if data:
                current_state = data
                print(f"Pedal Data: {data}")
                
                if (last_state is None or last_state[4] == 0) and data[4] == 3:
                    current_time = time.time()
                    print(f"Detected pedal press at {datetime.now().strftime('%H:%M:%S.%f')}")
                    
                    # Check for rapid presses (timelapse toggle)
                    rapid_press_detected = check_rapid_presses()
                    
                    # If not handling a timelapse toggle and enough time has passed (debounce)
                    if not rapid_press_detected and current_time - last_trigger_time > DEBOUNCE_TIME and not timelapse_active:
                        print("\n🔴 TRIGGERING CAMERA...")
                        take_photo()
                        last_trigger_time = current_time
                
                # Update the last state
                last_state = current_state
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nExiting program")
        # Make sure to stop timelapse if active
        if timelapse_active:
            timelapse_stop_event.set()
            if timelapse_thread:
                timelapse_thread.join(timeout=1)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up
        try:
            pedal.close()
        except:
            pass
        print("Disconnected from foot pedal")

if __name__ == "__main__":
    main()