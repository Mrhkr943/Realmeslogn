import os
import base64
import json
from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from flask_session import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import functools

app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
Session(app)

# Google OAuth Configuration
CLIENT_ID = "733557611631-tvn1a5fovr1u990glo6jbvjnkr67c2sn.apps.googleusercontent.com"
CLIENT_SECRET = "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"
PROJECT_ID = "newporoject-c6f66"

# Get the base URL
BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
REDIRECT_URI = f"{BASE_URL}/callback"

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/gmail.readonly'
]

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'credentials' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_flow():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "project_id": PROJECT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI]
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)

@app.route('/')
def index():
    return render_template('google.html')

@app.route('/login')
def login():
    try:
        flow = get_flow()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        session['state'] = state
        return redirect(authorization_url)
    except Exception as e:
        return f"Login error: {str(e)}", 500

@app.route('/callback')
def callback():
    try:
        flow = get_flow()
        flow.fetch_token(authorization_response=request.url)
        
        if session.get('state') != request.args.get('state'):
            return 'State mismatch error', 400
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Get user info
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        session['email'] = user_info['email']
        session['name'] = user_info.get('name', 'User')
        session['picture'] = user_info.get('picture', '')
        
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        return f"Callback error: {str(e)}", 400

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', 
                         email=session.get('email'),
                         name=session.get('name'),
                         picture=session.get('picture'))

@app.route('/api/get_emails')
@login_required
def get_emails():
    try:
        creds_dict = session['credentials']
        credentials = Credentials(
            token=creds_dict['token'],
            refresh_token=creds_dict.get('refresh_token'),
            token_uri=creds_dict['token_uri'],
            client_id=creds_dict['client_id'],
            client_secret=creds_dict['client_secret'],
            scopes=creds_dict['scopes']
        )
        
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            session['credentials']['token'] = credentials.token
        
        service = build('gmail', 'v1', credentials=credentials)
        results = service.users().messages().list(userId='me', maxResults=20).execute()
        messages = results.get('messages', [])
        
        emails = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id'], format='metadata').execute()
            headers = msg['payload']['headers']
            
            emails.append({
                'id': message['id'],
                'subject': next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject'),
                'from': next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown'),
                'date': next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown'),
                'snippet': msg['snippet'],
            })
        
        return jsonify(emails)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
