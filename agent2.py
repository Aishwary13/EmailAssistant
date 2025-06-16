from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_openai.chat_models import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_structured_chat_agent, create_react_agent
from langchain import hub
from langchain_core.tools import Tool, StructuredTool
from langchain.memory import ConversationBufferMemory
from typing import List, Dict
from pydantic import BaseModel, Field
import json 
from dotenv import load_dotenv
import os
import sqlite3

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import base64

load_dotenv()
SEEN_EMAIL_IDS = set()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.modify']

conn = sqlite3.connect('emails.db')
cursor = conn.cursor()

######################################################################################################
def get_gmail_service():
    """Get authenticated Gmail service"""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)

def process_email(msg):
    """Extract and format email content"""
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

    timestamp_ms = int(msg.get('internalDate'))  
    timestamp = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

    temp = f"ID: {msg["id"]} | From: {sender} | CC: {cc} | Subject: {subject} | Body: {body} | receivedtime: {timestamp}."
    # formatEmail.append(temp)
    return temp

def fetch_new_emails(): 
    """Fetch and process unseen emails"""
    try:
        service = get_gmail_service()

        ##### get the last time email was fetched
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute("SELECT receivedtime FROM emails ORDER BY receivedtime DESC LIMIT 1")
        last_time_result = cursor.fetchone()
        
        # Set query time window (default: last 5 minutes if no records exist)
        if last_time_result:
            last_time = datetime.strptime(last_time_result[0], "%Y-%m-%d %H:%M:%S")
            query_time = last_time
        else:
            query_time = datetime.utcnow() - timedelta(minutes=5)
        
        # Convert to Gmail query format
        query_timestamp = int(query_time.timestamp())

        query = f"in:inbox after:{query_timestamp}"
        
        messages = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=10
        ).execute().get('messages', [])
        
        new_emails = []
        for msg in messages:
            if msg['id'] not in SEEN_EMAIL_IDS:
                SEEN_EMAIL_IDS.add(msg['id'])
                email_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                new_emails.append(process_email(email_data))
        
        return new_emails
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []


###################################################################################################


# Connect to SQLite DB (will create it if not exists)
# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS emails (
    ID TEXT PRIMARY KEY,
    sender TEXT,
    subject TEXT,
    body TEXT,
    summary TEXT,
    category TEXT,
    score TEXT,
    action TEXT,
    receivedtime text
)
""")

conn.commit()



def insert_emails_to_db(email_data):
    with sqlite3.connect('emails.db') as conn:
        cursor = conn.cursor()
        for email in email_data:
            cursor.execute("""
            INSERT OR IGNORE INTO emails (ID, sender, subject ,body, summary, category, score, action, receivedtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email.get("ID"),
                email.get("from"),
                email.get("subject"),
                email.get("body"),
                email.get("summary"),
                email.get("category"),
                email.get("score"),
                email.get("action"),
                email.get("receivedtime")
            ))
        conn.commit()


CATEGORIES = [
    "Announcements", "Feedback", "Non-complaince", "System Generated Mails",
    "Others", "Events", "Meetings", "Updates", "Marketing"
]

def get_emails_by_category(category):
    with sqlite3.connect('emails.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ID, sender, subject, body FROM emails WHERE category = ?", (category,))
        return cursor.fetchall()

def get_email_by_id(email_id):
    with sqlite3.connect('emails.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE ID = ?", (email_id,))
        return cursor.fetchone()

############################################################

# Initialize LLM
OpenAIchat = AzureChatOpenAI(
    azure_endpoint="https://azureopenai-practice.openai.azure.com/",
    api_key=os.getenv("AZURE_CHAT_API_KEY2"),
    model="gpt-4o",  # or "gpt-35-turbo" depending on what you have access to
    api_version="2024-12-01-preview",  # Updated to a more recent stable version
    temperature=0.7
)

# llm_with_structure = OpenAIchat.with_structured_output()

###############################################
# Define tools (improved versions)
###############################################

def get_emails() -> Dict[str, List[str]]:
    """Fetch emails"""
    emails = fetch_new_emails()

    return {"emails": emails}


class EmailListInput(BaseModel):
    emails: List[str] = Field(description="List of email strings to process")


def summarize_and_rank_emails(emails_input) -> List[Dict]:
    """Final working version with complete error handling"""
    # Input handling
    if isinstance(emails_input, str):
        try:
            parsed = json.loads(emails_input)
            emails = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            emails = [emails_input]
    else:
        emails = emails_input if isinstance(emails_input, list) else [emails_input]

    system_prompt = """
        You are an expert email assistant. For each email, extract and return a JSON object with the following fields:

        - ID: ID of that mail
        - from: Email sender's address
        - subject: Subject line of the email
        - body: Body of the Mail
        - summary: A brief 3 to 4 sentence summary of the email content
        - category: One of the following — "Announcements", "Feedback", "Non-compliance", "System Generated Mails", "Others", "Events", "Meetings", "Updates", "Marketing"
        - score: A string float between "0.00000" and "1.00000" (e.g., "0.342"). t reflects how important the email is. 
                Score must reflect the real importance based on content, not just presence of a subject or urgency tone. Use this logic:
                - "0.9 to 1.0": Very urgent/critical action needed (e.g., compliance issue, escalation)
                - "0.7 to 0.89": Important but not urgent (e.g., pending approval, customer complaint)
                - "0.4 to 0.69": Medium importance (e.g., team updates, meeting summaries)
                - "0.1 to 0.39": Low importance (e.g., announcements, non-urgent feedback)
                - "0.0 to 0.09": Very low importance or noise (e.g., ads, system auto-mails)
                The score must match the mail's true urgency and relevance.
                Internally assess the content's urgency, relevance, and required action to determine the score. Do not default to high scores.
                Avoid assigning scores close to 1 unless the mail clearly demands urgent and high-priority action.

        - action: A suggested action to take based on the email content
        -receivedtime: timestamp

        Return the output as a JSON array. 

        Example output:
        ```json
        [
            {
                "ID": "ID of that mail",
                "from": "sender@example.com",
                "subject": "Subject",
                "body" : "Body of the mail"
                "summary": "Brief summary of the email content in 3 to 4 sentences.",
                "category": "Meetings",
                "score": "0.2315",
                "action": "Schedule a meeting based on the proposed time."
                "receivedtime": timestamp
            }
        ]
"""

    email_text = "\n---\n".join(emails)
    #print(email_text)
    
    try:
        # Create prompt with explicit JSON formatting instructions
        messages = [
            ("system", system_prompt),
            ("human", f"Process these emails:\n{email_text}\n\nReturn ONLY valid JSON:")
        ]
        
        response = OpenAIchat.invoke(messages)
        
        # Extract JSON from response
        json_str = response.content.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:-3]  # Remove markdown code block
        
        # print("#############################")
        # print(json_str)
        emails_data_db = json.loads(json_str)
        insert_emails_to_db(emails_data_db)

        return emails_data_db
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}\nResponse was: {response.content}")
        return []
    except Exception as e:
        print(f"Error processing emails: {str(e)}")
        return []

###############################################
# Setup tools
###############################################


tools = [
    StructuredTool.from_function(
        name="FetchEmails",
        func=get_emails,
        description="Fetches the latest emails from the inbox. Returns a dictionary with an 'emails' key containing a list of email strings."
    ),
    StructuredTool.from_function(
        name="ProcessEmails",
        func=summarize_and_rank_emails,
        description="Processes a list of email strings. For each email, extracts key info, categorizes, prioritizes, and suggests actions. Input must be a list of email strings.",
        # args_schema=EmailListInput
    )
]

###############################################
# Setup agent with memory
###############################################

prompt = hub.pull("hwchase17/react")

# Create agent
agent = create_react_agent(
    llm=OpenAIchat,
    tools=tools,
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors="Check your output and make sure it conforms to the expected format!",
    max_iterations=5  
)

###############################################
#main chat loop
###############################################

if __name__ == "__main__":
    print("Email Assistant initialized. Type 'exit' to quit.")
    while True:
        try:
            query = input("\nYou: ").strip()
            if query.lower() in ["exit", "quit"]:
                break
                
            if not query:
                continue
                
            response = agent_executor.invoke({"input": query})
            print("\nAssistant:", response["output"])
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An error occurred: {str(e)}")