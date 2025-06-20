import os
import threading
import asyncio
import time
import ssl
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from pyngrok import ngrok
from dotenv import load_dotenv

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import AzureChatOpenAI

from agent2 import get_emails_by_category, get_email_by_id, CATEGORIES, get_gmail_service
from googleapiclient.errors import HttpError

# Allow unverified HTTPS (for dev only)
ssl._create_default_https_context = ssl._create_unverified_context

load_dotenv()

app = Flask(__name__)

# Set ngrok auth token
ngrok.set_auth_token(os.getenv("NGROK_KEY"))

# MCP client setup pointing to your MCP server
client = MultiServerMCPClient({
    "email": {
        "url": "http://localhost:8000/mcp/",  # Your MCP server URL
        "transport": "streamable_http"
    }
})

# Azure OpenAI LLM setup
llm = AzureChatOpenAI(
    azure_endpoint="https://azureopenai-practice.openai.azure.com/",
    api_key=os.getenv("AZURE_CHAT_API_KEY2"),
    model="gpt-4o",
    api_version="2024-12-01-preview",
    temperature=0.7
)

agent = None  # Will hold your react agent

# Async init agent with MCP tools
async def init_agent():
    global agent
    tools = await client.get_tools()
    agent = create_react_agent(llm, tools)

asyncio.run(init_agent())


def setup_push_notifications(public_url):
    """Configure Gmail watch with Pub/Sub"""
    try:
        service = get_gmail_service()
        watch_request = {
            'labelIds': ['INBOX'],
            'topicName': 'projects/emailassisstant/topics/gmail_push_notifications',  # Use your exact Pub/Sub topic
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


@app.route('/')
def index():
    selected_category = request.args.get('category', CATEGORIES[0])
    selected_email_id = request.args.get('email_id')

    emails = get_emails_by_category(selected_category)
    email_detail = get_email_by_id(selected_email_id) if selected_email_id else None

    return render_template('index.html',
                           categories=CATEGORIES,
                           selected_category=selected_category,
                           emails=emails,
                           selected_email=email_detail)


@app.route('/gmail_push', methods=['POST'])
def gmail_push_notification():
    try:
        data = request.get_json()
        print(f"Received notification: {data}")

        result = asyncio.run(agent.ainvoke({"messages": "Fetch and summarize the emails"}))
        print("MCP Agent Response:", result)

        # Extract readable message content from all message objects
        messages = result.get("messages", [])
        agent_output_text = [getattr(m, "content", str(m)) for m in messages]

        return jsonify({
            "success": True,
            "message": "Notification processed",
            "agent_output": agent_output_text
        })
    except Exception as e:
        print("Error in /gmail_push:", str(e))
        return jsonify({"success": False, "error": str(e)}), 500



def get_public_url():
    """Start ngrok tunnel and return the public HTTPS URL"""
    try:
        ngrok.kill()  # Kill any existing tunnels
        public_url = ngrok.connect(5000, bind_tls=True).public_url
        print(f" * Ngrok tunnel running at: {public_url}")
        return public_url
    except Exception as e:
        print(f"Error creating ngrok tunnel: {e}")
        return None


def start_flask_app():
    app.run(port=5000, debug=True, use_reloader=False)


if __name__ == '__main__':
    public_url = get_public_url()
    if not public_url:
        print("❌ Could not start ngrok tunnel")
        exit(1)

    # Start Flask server in a background thread
    flask_thread = threading.Thread(target=start_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    # Setup Gmail push notifications with the ngrok public URL
    if setup_push_notifications(public_url):
        print("📡 Email watcher active. Push notifications enabled.")
        print(f"Push notification endpoint: {public_url}/gmail_push")
        print("Press Ctrl+C to stop")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
            ngrok.kill()
    else:
        print("Failed to configure push notifications")
