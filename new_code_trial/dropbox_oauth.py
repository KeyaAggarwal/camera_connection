import os
import json
import time
import webbrowser
import threading
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# Dropbox OAuth Configuration
DROPBOX_APP_KEY = "008yigu3hd08tcf"  # Replace with your Dropbox App Key
DROPBOX_APP_SECRET = "ra4d1fx6onlttbz"  # Replace with your Dropbox App Secret
DROPBOX_REDIRECT_URI = "http://localhost:8081/auth/callback"
DROPBOX_TOKEN_FILE = "dropbox_tokens.json"

# OAuth server response flag
oauth_response_received = threading.Event()
auth_code = None

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        
        if 'code' in query_components:
            auth_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization Successful!</h1><p>You can close this window now.</p></body></html>")
            oauth_response_received.set()
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization Failed</h1><p>No authorization code received.</p></body></html>")
    
    # Suppress server logs
    def log_message(self, format, *args):
        return

def load_dropbox_tokens():
    """Load Dropbox tokens from file."""
    if os.path.exists(DROPBOX_TOKEN_FILE):
        with open(DROPBOX_TOKEN_FILE, 'r') as f:
            return json.load(f)
    return None

def save_dropbox_tokens(tokens):
    """Save Dropbox tokens to file."""
    with open(DROPBOX_TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)
    print("✅ Dropbox tokens saved")

def get_dropbox_auth_url():
    """Generate the authorization URL for Dropbox OAuth."""
    auth_url = "https://www.dropbox.com/oauth2/authorize"
    params = {
        "client_id": DROPBOX_APP_KEY,
        "response_type": "code",
        "redirect_uri": DROPBOX_REDIRECT_URI,
        "token_access_type": "offline"  # This will give us a refresh token
    }
    return f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"

def get_tokens_from_auth_code(code):
    """Exchange authorization code for access and refresh tokens."""
    token_url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": DROPBOX_APP_KEY,
        "client_secret": DROPBOX_APP_SECRET,
        "redirect_uri": DROPBOX_REDIRECT_URI
    }
    
    response = requests.post(token_url, data=data)
    if response.status_code == 200:
        token_data = response.json()
        # Add expiration time (usually 4 hours for Dropbox)
        token_data["expires_at"] = time.time() + token_data["expires_in"]
        return token_data
    else:
        print(f"❌ Error getting tokens: {response.text}")
        return None

def refresh_access_token(refresh_token):
    """Refresh the access token using the refresh token."""
    token_url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "client_id": DROPBOX_APP_KEY,
        "client_secret": DROPBOX_APP_SECRET
    }
    
    response = requests.post(token_url, data=data)
    if response.status_code == 200:
        token_data = response.json()
        # Add expiration time
        token_data["expires_at"] = time.time() + token_data["expires_in"]
        return token_data
    else:
        print(f"❌ Error refreshing token: {response.text}")
        return None

def start_oauth_server():
    """Start a local server to handle the OAuth callback."""
    server = HTTPServer(('localhost', 8081), OAuthCallbackHandler)
    
    # Start server in a new thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    return server

def start_oauth_flow():
    """Start the OAuth flow to get Dropbox tokens."""
    global auth_code, oauth_response_received
    
    # Reset state
    auth_code = None
    oauth_response_received.clear()
    
    # Start the callback server
    server = start_oauth_server()
    
    # Generate and open the authorization URL
    auth_url = get_dropbox_auth_url()
    print(f"🔐 Please visit this URL to authorize the app: {auth_url}")
    
    try:
        # Try to open the browser automatically
        webbrowser.open(auth_url)
    except:
        print("⚠️ Could not open browser automatically. Please copy and paste the URL into your browser.")
    
    # Wait for the callback (with a timeout)
    oauth_response_received.wait(timeout=300)
    
    # Shutdown the server
    server.shutdown()
    
    if auth_code:
        # Exchange authorization code for tokens
        tokens = get_tokens_from_auth_code(auth_code)
        if tokens:
            save_dropbox_tokens(tokens)
            print("✅ Authorization successful!")
            return True
    
    print("❌ Authorization failed or timed out")
    return False

def get_valid_access_token():
    """Get a valid access token, refreshing if necessary."""
    tokens = load_dropbox_tokens()
    
    if not tokens:
        print("❌ No tokens found. Starting OAuth flow...")
        start_oauth_flow()
        tokens = load_dropbox_tokens()
        if not tokens:
            print("❌ OAuth flow failed")
            return None
    
    # Check if token is expired (or will expire in the next 5 minutes)
    is_expired = tokens.get("expires_at", 0) <= time.time() + 300
    
    if is_expired and "refresh_token" in tokens:
        print("⏳ Access token expired, refreshing...")
        new_tokens = refresh_access_token(tokens["refresh_token"])
        
        if new_tokens:
            # Preserve the refresh token if not returned in the response
            if "refresh_token" not in new_tokens:
                new_tokens["refresh_token"] = tokens["refresh_token"]
                
            save_dropbox_tokens(new_tokens)
            return new_tokens["access_token"]
        else:
            print("❌ Token refresh failed. Starting new OAuth flow...")
            start_oauth_flow()
            tokens = load_dropbox_tokens()
            if tokens:
                return tokens["access_token"]
    
    return tokens.get("access_token")

# For testing the OAuth module directly
if __name__ == "__main__":
    print("Testing Dropbox OAuth module...")
    token = get_valid_access_token()
    if token:
        print(f"✅ Successfully obtained access token: {token[:10]}...")
    else:
        print("❌ Failed to obtain access token")
