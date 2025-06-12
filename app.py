
from googleapiclient.errors import HttpError
from flask import Flask, request, jsonify
import base64
import os
from datetime import datetime, timedelta
import threading
import time
from pyngrok import ngrok
import os
from dotenv import load_dotenv
from agent2 import agent_executor,get_gmail_service

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

load_dotenv()

app = Flask(__name__)

ngrok.set_auth_token(os.getenv("NGROK_KEY"))

def get_public_url():
    """Establish ngrok tunnel and return public URL"""
    try:
        # Kill existing tunnels if any
        ngrok.kill()
        # Start new HTTPS tunnel
        public_url = ngrok.connect(5000, bind_tls=True).public_url
        print(f" * Ngrok tunnel running at: {public_url}")
        return public_url
    except Exception as e:
        print(f"Error creating ngrok tunnel: {e}")
        return None


@app.route('/gmail_push', methods=['POST'])
def gmail_push_notification():
    """Handle incoming push notifications"""
    try:
        data = request.get_json()
        print(f"Received notification: {data}")
        
        # Process the notification with your agent
        response = agent_executor.invoke({"input": "Fetch and summarize the emails"})
        print(response["output"])
        
        # Always return a valid Flask response
        return jsonify({
            "success": True,
            "message": "Notification processed",
            "agent_output": response["output"]
        })
        
    except Exception as e:
        print(f"Error handling notification: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

def setup_push_notifications(public_url):
    """Configure Gmail watch with Pub/Sub"""
    try:
        service = get_gmail_service()
        
        watch_request = {
            'labelIds': ['INBOX'],
            'topicName': 'projects/emailassisstant/topics/gmail_push_notifications',
            'labelFilterAction': 'include'
        }
        
        response = service.users().watch(
            userId='me',
            body=watch_request
        ).execute()
        
        print(f"Push notifications configured. History ID: {response['historyId']}")
        return True
    except HttpError as e:
        print(f"Error setting up push notifications: {e}")
        return False

def start_flask_app():
    """Run Flask server"""
    app.run(port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Start ngrok tunnel
    public_url = get_public_url()
    if not public_url:
        print("Failed to establish ngrok tunnel")
        exit(1)
    
    # Start Flask in background
    flask_thread = threading.Thread(target=start_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Configure push notifications
    if setup_push_notifications(public_url):
        print("📡 Email watcher active. Push notifications enabled.")
        print(f"Endpoint: {public_url}/gmail_push")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
            ngrok.kill()
    else:
        print("Failed to configure push notifications")