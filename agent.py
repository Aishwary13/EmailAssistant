from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from langchain_openai.chat_models import AzureChatOpenAI
from langgraph.graph import StateGraph, START, MessagesState, END
from langchain.tools import tool
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

@tool
def getemails() -> dict:
    """
    Fetches recent emails from an inbox (mock implementation).
    Returns a dictionary with a list of emails.
    """

    emails = [
        "Subject: Meeting | Body: Let's meet tomorrow at 3 PM.",
        "Subject: Invoice | Body: Please find attached invoice #123.",
        "Subject: Urgent | Body: Server downtime reported in region A.",
    ]
    return {"emails": emails}

summaryAgent = create_react_agent(
    model = OpenAIchat,
    name = "summaryAgent",
    prompt = "Summarize each email in a concise bullet point.",
    tools = []
)

rankAgent = create_react_agent(
    model = OpenAIchat,
    name = "rankingAgent",
    prompt = "Rank emails from most to least important based on their content.",
    tools = []
)

emailAgent = create_react_agent(
    model = OpenAIchat,
    name = "EmailAgent",
    prompt = "Fetch recent emails using the get_emails tool.",
    tools=[getemails]
)

supervisor = create_supervisor(
    agents=[summaryAgent,rankAgent,emailAgent],
    model = OpenAIchat,
    prompt="""
        You are a smart supervisor agent.
        - If the user asks about emails (e.g., to fetch, summarize, or prioritize), route to the EmailAgent.
        - Otherwise, just respond directly like a helpful assistant.
        """
).compile()

def supervisor_router(state: MessagesState) -> str:
    last_message = state["messages"][-1].content.lower()

    if "email" in last_message:
        return "EmailAgent"
    else:
        return END  # normal chat, no agent needed

# Graph setup
graph = StateGraph(MessagesState)
graph.add_node("supervisor", supervisor)
graph.add_node("EmailAgent", emailAgent)
graph.add_node("SummaryAgent", summaryAgent)
graph.add_node("RankAgent", rankAgent)
# graph.add_node("SuperRouter",supervisor_router)

# Edges (Flow)
graph.set_entry_point("supervisor")

#add conditional edge
graph.add_conditional_edges("supervisor", supervisor_router)

# graph.add_edge("SuperRouter","supervisor")
# graph.add_edge("SuperRouter","EmailAgent")
graph.add_edge("EmailAgent", "SummaryAgent")
graph.add_edge("SummaryAgent", "RankAgent")
graph.add_edge("RankAgent", END)

def visualizeGraph(graph, file_name="graph.png"):
    from langchain_core.runnables.graph import MermaidDrawMethod

    # Get the image data
    img_data = graph.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)

    # Save to file
    with open(file_name, "wb") as f:
        f.write(img_data)

    print(f"Graph saved to {file_name}. Open it to view.")

if __name__ == "__main__":
    app = graph.compile(debug=False)

    # visualizeGraph(app)
    
    while True:
        query = input("Human message: ")

        if query.strip().lower() == "exit":
            break

        # Wrap the input as a user message
        output = app.invoke({"messages": [{"role": "user", "content": query}]})

        # print(len(output))
        ai_messages = [msg.content for msg in output['messages'] if msg.__class__.__name__ == "AIMessage"]
        if ai_messages:
            print("AI:", ai_messages[-1])

        # print(output)

