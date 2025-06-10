from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from langchain_openai.chat_models import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain import hub
from langchain_core.tools import Tool, StructuredTool
from langchain.memory import ConversationBufferMemory
from typing import List, Dict
from pydantic import BaseModel
import json 
from dotenv import load_dotenv
import os

load_dotenv()

OpenAIchat = AzureChatOpenAI(
    azure_endpoint="https://aishtestopenaichat.openai.azure.com/",
    api_key= os.getenv("AZURE_CHAT_API_KEY"),
    model = "gpt-4o-mini",
    api_version= "2024-12-01-preview",
    temperature=0.7
)

###############################################
# Define tools
###############################################

def getemails() -> Dict[str, List[str]]:
    """Mock function to fetch emails."""

    emails = [
        "From: alice@company.com | To: bob@company.com | Subject: Team Sync Meeting Tomorrow | Body: Hi Bob, just a reminder that we have a team sync scheduled for tomorrow at 3 PM in the main conference room. Please be prepared to discuss progress on your current tasks and blockers.",
        
        "From: accounts@billing.com | To: finance@company.com | Subject: Invoice #123 for April 2025 | Body: Hello, please find attached invoice #123 for the services provided in April 2025. Kindly ensure payment is processed by June 15th. Let us know if you need any clarifications.",
        
        "From: noreply@monitoring.com | To: it@company.com | Subject: Urgent: Server Downtime in Region A | Body: Monitoring system has detected an outage in Region A starting at 02:45 AM UTC. Initial diagnostics suggest a network failure. Engineering team is investigating. Updates will follow shortly.",
        
        "From: hr@company.com | To: all@company.com | Subject: Company Offsite Announcement | Body: We're excited to announce a company offsite on July 12th! This will be a full-day event with team-building activities, workshops, and fun. Attendance is optional, but encouraged!",
        
        "From: marketing@company.com | To: clients@company.com | Subject: New Product Launch: AI Assistant Pro | Body: We’re thrilled to introduce AI Assistant Pro, our most advanced productivity tool yet! Explore the features, benefits, and introductory pricing. Click here to learn more and book a demo.",
        
        "From: security@company.com | To: all@company.com | Subject: System Maintenance Scheduled This Weekend | Body: Please note that scheduled maintenance will occur on Saturday from 10 PM to Sunday 4 AM. Access to internal tools may be temporarily restricted during this time. No action is required from your end."
    ]

    return {"emails": emails}


from pydantic import BaseModel
from typing import List, Optional


# def getemails() -> Dict:
#     emails = [
#         "From: alice@company.com | To: bob@company.com | Subject: Team Sync Meeting Tomorrow | Body: Hi Bob, just a reminder...",
#         # all the other mock emails...
#     ]
#     return {
#         "items": {
#             "items": emails,
#             "title": "Mocked Inbox"
#         },
#         "type": "Mock",
#         "title": "Email Summary"
#     }

class EmailListInput(BaseModel):
    emails: List[str]


# def summaryEmail(emails: List[str]) -> str:
#     """Summarizes a list of email texts."""
#     summary_prompt = ChatPromptTemplate.from_messages([
#         ("system", "Summarize the following list of emails briefly."),
#         ("human", "{input}"),
#     ])

#     email_text = "\n\n".join(emails)
#     chain = summary_prompt | OpenAIchat
#     response = chain.invoke({"input": email_text})

#     return response.content  # Return only text, not full response dict

def summarize_and_rank_emails(input: EmailListInput) -> List[Dict]:
    """Tags, summarizes, and prioritizes a list of formatted email strings."""

    system_prompt = """
        You are an email assistant. You will be given a list of email strings. Each email is separated and follows this format:
        "From: <sender> | To: <receiver> | Subject: <subject> | Body: <body>"

        Your task is to:
        1. Parse each email properly.
        2. Categorize each email into one of the following:
            - Reply not mandatory:
                1. Announcements
                2. Feedback
                3. Non-compliance
                8. System Generated Mails
                9. Others
            - Action is required:
                4. Events
                5. Meetings
            - Reply is mandatory:
                6. Updates
                7. Marketing
        3. Generate a short summary (1-2 sentences) for each email.
        4. Prioritize emails that need attention first. Rank from highest to lowest priority.
        5. Return a list of dictionaries in descending priority order, where each dictionary contains:
            {
                "summary": "<short summary>",
                "actual_body": "<full body>",
                "category": "<category name>",
                "from": "<sender>",
                "subject": "<subject>"
            }

        Output must be a valid JSON list of dictionaries. Do not include any other explanation.
        """

    email_text = "\n\n".join(input)

    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt.strip()),
        ("human", "{input}")
    ])

    chain = summary_prompt | OpenAIchat
    response = chain.invoke({"input": email_text})

    try:
        parsed_output = json.loads(response.content)
    except json.JSONDecodeError:
        raise ValueError("LLM response was not valid JSON:\n" + response.content)

    return parsed_output

###############################################
# Setup tools
###############################################

tools = [
    StructuredTool.from_function(
        name="FetchEmails",
        func=getemails,
        description="Use this tool to fetch recent emails from the Gmail inbox.",
    ),
    StructuredTool.from_function(
        name="SummarizeAndRankEmails",
        func=summarize_and_rank_emails,
        description="Summarize and categorize a list of plain-text formatted email strings. Input should be a list of email strings.",
        args_schema=EmailListInput
        
    ),
]

###############################################
# Setup agent
###############################################

# React-style prompt from LangChain Hub
prompt = hub.pull("hwchase17/structured-chat-agent")

from langchain.prompts import ChatPromptTemplate

# prompt_str = """
# You are an AI assistant with access to the following tools:

# {tools}

# Available tools: {tool_names}

# You must always respond ONLY with a single JSON blob specifying one action.

# The JSON blob must have the keys:
# - "action": the tool name or "Final Answer"
# - "action_input": the input for the tool or the final answer string

# ---

# Tool Input Formats:

# 1. FetchEmails  
# Input: {{}}  
# Example:  
# {{  
#   "action": "FetchEmails",  
#   "action_input": {{}}  
# }}

# 2. SummarizeAndRankEmails  
# Input: A JSON object matching this Pydantic model:  

# {{
#   "items": {{
#     "items": [string],        # List of email strings in the format:  
#                              # "From: <sender> | To: <receiver> | Subject: <subject> | Body: <body>"
#     "title": "optional title"
#   }},
#   "type": "optional string",
#   "title": "optional string"
# }}

# Example:

# {{
#   "action": "SummarizeAndRankEmails",
#   "action_input": {{
#     "items": {{
#       "items": [
#         "From: alice@company.com | To: bob@company.com | Subject: Meeting | Body: Let's meet tomorrow.",
#         "From: hr@company.com | To: all@company.com | Subject: Announcement | Body: Company offsite on July 12th."
#       ],
#       "title": "Recent Emails"
#     }},
#     "type": "email_list",
#     "title": "Inbox"
#   }}
# }}

# ---

# Format:

# Question: {input}

# Thought: {agent_scratchpad}

# Action:
# ```json
# {{your JSON action here}}
# """
# prompt = ChatPromptTemplate.from_template(prompt_str)

# Create the agent
agent = create_structured_chat_agent(
    llm=OpenAIchat,
    tools=tools,
    prompt=prompt
)

agent_executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True
)

###############################################
# Main Chat Loop
###############################################

if __name__ == "__main__":
    while True:
        query = input("you: ")
        if query.strip().lower() in ["exit", "quit"]:
            break

        response = agent_executor.invoke({"input": query})
        print("AI:", response["output"])