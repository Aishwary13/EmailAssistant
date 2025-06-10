import os.path
import base64
import email
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
SEEN_EMAIL_IDS = set()

def fetch_emails():
    """Fetch and print emails from the last 8 hours that haven't been seen before."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)
        now = datetime.utcnow()
        past = now - timedelta(hours=8)
        after_timestamp = int(past.timestamp())
        query = f"in:inbox after:{after_timestamp}"

        resp = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
        msgs = resp.get('messages', [])
        formatEmail = []

        for m in msgs:
            if m['id'] in SEEN_EMAIL_IDS:
                continue

            SEEN_EMAIL_IDS.add(m['id'])

            msg = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            cc = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
            
            parts = msg['payload'].get('parts', [])
            body = ""
            for part in parts:
                if part['mimeType'] == 'text/plain' and part['body'].get('data'):
                    data = part['body']['data']
                    body += base64.urlsafe_b64decode(data.encode()).decode()

            if not body and msg['payload']['body'].get('data'):
                body = base64.urlsafe_b64decode(msg['payload']['body']['data'].encode()).decode()

            # print("📩 New Email:")
            # print("Subject:", subject)
            # print("From:", sender)
            # print("CC", cc)
            # print("Body:", body[:200], "...\n")  # Print 1st 200 chars

            temp = f"From: {sender} | CC: {cc} | Subject: {subject} | Body: {body}."
            formatEmail.append(temp)
        
        return formatEmail

    except HttpError as e:
        print(f'An error occurred: {e}')
        return "email fetching Error occured"


# 🔁 Schedule email fetching every 1 minute
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_emails, 'interval', minutes=1)
    scheduler.start()
    print("📡 Email fetcher started. Press Ctrl+C to stop.")

    try:
        # Keep the script running
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("🛑 Scheduler stopped.")
