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

from emailcode import fetch_emails

load_dotenv()

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

    # emails = [
    #     "From: alice@company.com | To: bob@company.com | Subject: Team Sync Meeting Tomorrow | Body: Hi Bob, just a reminder that we have a team sync scheduled for tomorrow at 3 PM in the main conference room. Please be prepared to discuss progress on your current tasks and blockers.",
    #     "From: accounts@billing.com | To: finance@company.com | Subject: Invoice #123 for April 2025 | Body: Hello, please find attached invoice #123 for the services provided in April 2025. Kindly ensure payment is processed by June 15th. Let us know if you need any clarifications.",
    #     "From: noreply@monitoring.com | To: it@company.com | Subject: Urgent: Server Downtime in Region A | Body: Monitoring system has detected an outage in Region A starting at 02:45 AM UTC. Initial diagnostics suggest a network failure. Engineering team is investigating. Updates will follow shortly.",
    #     "From: hr@company.com | To: all@company.com | Subject: Company Offsite Announcement | Body: We're excited to announce a company offsite on July 12th! This will be a full-day event with team-building activities, workshops, and fun. Attendance is optional, but encouraged!",
    #     "From: marketing@company.com | To: clients@company.com | Subject: New Product Launch: AI Assistant Pro | Body: We're thrilled to introduce AI Assistant Pro, our most advanced productivity tool yet! Explore the features, benefits, and introductory pricing. Click here to learn more and book a demo.",
    #     "From: security@company.com | To: all@company.com | Subject: System Maintenance Scheduled This Weekend | Body: Please note that scheduled maintenance will occur on Saturday from 10 PM to Sunday 4 AM. Access to internal tools may be temporarily restricted during this time. No action is required from your end."
    # ]

    emails = fetch_emails()

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

    system_prompt = """You are an expert email assistant. For each email, return JSON with:
    - from: sender
    - to: recipient  
    - subject
    - summary: 1-sentence
    - category: Critical/High/Medium/Low
    - action: suggested action
    
    Example output:
    ```json
    [
        {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Subject",
            "summary": "Brief summary",
            "category": "High", 
            "action": "Suggested action"
        }
    ]
    ```"""

    email_text = "\n---\n".join(emails)
    
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
        
        return json.loads(json_str)
        
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

# Custom prompt for better email handling
prompt_template = """You are a professional email assistant AI. Your job is to help manage emails efficiently.

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Previous conversation history:
{history}

Question: {input}
Thought:{agent_scratchpad}"""

# prompt = ChatPromptTemplate.from_template(prompt_template)

# Add memory
# memory = ConversationBufferMemory(memory_key="history")

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
    max_iterations=5  # Prevent infinite loops
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