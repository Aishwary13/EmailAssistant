# import os.path
# import base64
# import email
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
 
# SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
 
# def fetch_emails(max_results=10, only_unread=True):
#     """Fetches latest emails from Gmail. Returns list of dicts: {id, subject, sender, body}."""
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open('token.json', 'w') as token:
#             token.write(creds.to_json())
 
#     try:
#         service = build('gmail', 'v1', credentials=creds)
#         query = 'in:inbox' + (' is:unread' if only_unread else '')
#         resp = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
#         msgs = resp.get('messages', [])
#         result = []
 
#         for m in msgs:
#             msg = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
#             headers = msg['payload']['headers']
#             subject = next((h['value'] for h in headers if h['name']=='Subject'), '')
#             sender = next((h['value'] for h in headers if h['name']=='From'), '')
           
#             parts = msg['payload'].get('parts', [])
#             body = ""
#             for part in parts:
#                 if part['mimeType']=='text/plain' and part['body'].get('data'):
#                     data = part['body']['data']
#                     body += base64.urlsafe_b64decode(data.encode()).decode()
           
#             if not body and msg['payload']['body'].get('data'):
#                 body = base64.urlsafe_b64decode(msg['payload']['body']['data'].encode()).decode()
 
#             result.append({'id': m['id'], 'subject': subject, 'from': sender, 'body': body})
 
#         return result
 
#     except HttpError as e:
#         print(f'An error occurred: {e}')
#         return []

# emails = fetch_emails(max_results=15,only_unread=True)
# for i in emails:
#     print("subject",i["subject"])
#     print("body",i["body"])
#     print("from",i["from"])
#     print(i)
#     break






# import os.path
# import base64
# import email
# from datetime import datetime, timedelta
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# def fetch_emails(max_results=10):
#     """Fetches emails from the last 8 hours. Returns list of dicts: {id, subject, sender, body}."""
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open('token.json', 'w') as token:
#             token.write(creds.to_json())

#     try:
#         service = build('gmail', 'v1', credentials=creds)

#         # Calculate 8 hours ago as a Unix timestamp
#         now = datetime.utcnow()
#         past = now - timedelta(hours=8)
#         after_timestamp = int(past.timestamp())
#         query = f"in:inbox after:{after_timestamp}"

#         # Fetch messages
#         resp = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
#         msgs = resp.get('messages', [])
#         result = []
        
#         for m in msgs:
#             msg = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
#             headers = msg['payload']['headers']
            
#             subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
#             sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
#             cc = next((h['value'] for h in headers if h['name'] == 'cc'), '')
            
#             parts = msg['payload'].get('parts', [])
#             body = ""
#             for part in parts:
#                 if part['mimeType'] == 'text/plain' and part['body'].get('data'):
#                     data = part['body']['data']
#                     body += base64.urlsafe_b64decode(data.encode()).decode()

#             if not body and msg['payload']['body'].get('data'):
#                 body = base64.urlsafe_b64decode(msg['payload']['body']['data'].encode()).decode()

#             result.append({'id': m['id'], 'from': sender,'cc':cc, 'body': body, 'subject': subject})

#         return result

#     except HttpError as e:
#         print(f'An error occurred: {e}')
#         return []

# # Test the function

# emails = fetch_emails(max_results=15)
# for i in emails:
#     print("subject:", i["subject"])
#     print("body:", i["body"])
#     print("from:", i["from"])
#     print(i)
#     break





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

            print("📩 New Email:")
            print("Subject:", subject)
            print("From:", sender)
            print("CC", cc)
            print("Body:", body[:200], "...\n")  # Print 1st 200 chars

    except HttpError as e:
        print(f'An error occurred: {e}')


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
