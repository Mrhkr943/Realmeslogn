import os
import base64
from flask import Flask, redirect, session, render_template, request, jsonify
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import functools

app = Flask(__name__, template_folder='.')
app.secret_key = "my-super-secret-key-12345-change-this"  # Change this in production

# Google Credentials
CLIENT_ID = "733557611631-tvn1a5fovr1u990glo6jbvjnkr67c2sn.apps.googleusercontent.com"
CLIENT_SECRET = "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"
PROJECT_ID = "newporoject-c6f66"

# URL Configuration
BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://gmailx.onrender.com')
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
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('google.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/login')
def login():
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": PROJECT_ID,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": [REDIRECT_URI]
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )
        
        session['state'] = state
        return redirect(auth_url)
        
    except Exception as e:
        return f"Login Error: {str(e)}", 500

@app.route('/callback')
def callback():
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "project_id": PROJECT_ID,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": [REDIRECT_URI]
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        flow.fetch_token(authorization_response=request.url)
        
        if session.get('state') != request.args.get('state'):
            return "State mismatch error", 400
        
        creds = flow.credentials
        session['credentials'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        
        # Get user info
        service = build('oauth2', 'v2', credentials=creds)
        user = service.userinfo().get().execute()
        session['email'] = user['email']
        
        return redirect('/dashboard')
        
    except Exception as e:
        return f"Callback Error: {str(e)}", 400

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', email=session.get('email'))

@app.route('/api/emails')
@login_required
def get_emails():
    try:
        creds_dict = session['credentials']
        creds = Credentials(
            token=creds_dict['token'],
            refresh_token=creds_dict.get('refresh_token'),
            token_uri=creds_dict['token_uri'],
            client_id=creds_dict['client_id'],
            client_secret=creds_dict['client_secret'],
            scopes=creds_dict['scopes']
        )
        
        if creds.expired:
            creds.refresh(Request())
            session['credentials']['token'] = creds.token
        
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', maxResults=20).execute()
        
        emails = []
        for msg in results.get('messages', []):
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            
            emails.append({
                'subject': subject,
                'from': from_email,
                'date': date,
                'snippet': msg_data['snippet']
            })
        
        return jsonify(emails)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
