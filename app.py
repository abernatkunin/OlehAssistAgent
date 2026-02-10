import streamlit as st
from typing import Dict, Any, List
from google.cloud import bigquery
from google.cloud import discoveryengine_v1 as discoveryengine
from google import genai
from google.genai import types
from google.oauth2 import service_account

# --- PAGE SETUP ---
st.set_page_config(page_title="OlehAssist", page_icon="🇮🇱", layout="wide")

st.title("🤖 OlehAssist")
st.markdown("Your personal guide to navigating bureaucracy in Israel.")

# --- CONFIGURATION ---
PROJECT_ID = "avibernat-kunin"
LOCATION = "global"
DATA_STORE_LOCATION = "global"
APP_ID = "olehassistapp_1768923251166"
DATASET_ID = "new_immigrant"
Ministry_of_aliyah_branch_table = f"{PROJECT_ID}.{DATASET_ID}.ministry_of_aliyah_branch_info"
MODEL_ID = "gemini-2.5-flash"

# --- CONNECT TO GOOGLE CLOUD ---
@st.cache_resource
def get_clients():
    """Connects using secrets for both local and cloud deployment"""
    
    if "gcp_service_account" in st.secrets:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/generative-language"
            ]
        )
    else:
        st.error("⚠️ Google Cloud credentials not found. Please add them to secrets.")
        st.stop()
    
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        credentials=credentials
    )
    
    bq_client = bigquery.Client(
        project=PROJECT_ID,
        credentials=credentials
    )
    
    return client, bq_client

try:
    client, bq_client = get_clients()
except Exception as e:
    st.error(f"❌ Could not connect to Google Cloud: {e}")
    st.info("💡 Make sure you've added your service account credentials to Streamlit secrets.")
    st.stop()

# --- TOOLS ---
def search_aliyah_information(query: str) -> str:
    """Searches the ministry of Aliyah's knowledge base."""
    with st.status(f"Searching knowledge base for: '{query}'...", expanded=False) as status:
        try:
            client_options = {"api_endpoint": f"{DATA_STORE_LOCATION}-discoveryengine.googleapis.com"}
            de_client = discoveryengine.SearchServiceClient(client_options=client_options)

            serving_config = f"projects/{PROJECT_ID}/locations/{DATA_STORE_LOCATION}/collections/default_collection/engines/{APP_ID}/servingConfigs/default_search"

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=10,
                content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                    extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                        max_extractive_segment_count=1
                    ),
                    snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                        return_snippet=True
                    )
                )
            )

            response = de_client.search(request)
            results_text = ""
            has_documents = False
            
            for result in response.results:
                has_documents = True
                if hasattr(result.document, 'derived_struct_data'):
                    data = result.document.derived_struct_data
                    link = data.get('link', '')
                    extractive_segments = data.get('extractive_segments', [])
                    
                    if extractive_segments:
                        for segment in extractive_segments:
                            content = segment.get('content', '').strip()
                            if content:
                                results_text += f"- {content}"
                                if link: results_text += f" (Source: {link})"
                                results_text += "\\n"
                    else:
                        snippets = data.get('snippets', [])
                        for snippet_item in snippets:
                            snippet = snippet_item.get('snippet', '').strip()
                            if snippet:
                                results_text += f"- {snippet}"
                                if link: results_text += f" (Source: {link})"
                                results_text += "\\n"

            status.update(label="✅ Search complete!", state="complete")
            
            if not results_text:
                if has_documents: return "I found documents but no specific answer. Try being more specific."
                return "No information found."
            return results_text

        except Exception as e:
            status.update(label="❌ Search failed", state="error")
            return f"Error: {str(e)}"

def find_ministry_of_aliyah_branch(query: str) -> List[Dict[str, Any]]:
    """Executes SQL query against BigQuery."""
    with st.status("Checking Database...", expanded=False) as status:
        try:
            query_job = bq_client.query(query)
            results = [dict(row.items()) for row in query_job.result()]
            status.update(label="✅ Database query complete!", state="complete")
            return results
        except Exception as e:
            status.update(label="❌ Query failed", state="error")
            return [{"error": str(e)}]

# --- FETCH SCHEMA ---
try:
    schema_query = f"""
    SELECT field_path AS column_name, data_type, description
    FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
    WHERE table_name = 'ministry_of_aliyah_branch_info'
    """
    job = bq_client.query(schema_query)
    branch_schema = [dict(row.items()) for row in job.result()]
except:
    branch_schema = "Schema unavailable"

# --- SYSTEM INSTRUCTIONS ---
SYSTEM_INSTRUCTIONS = f"""
You are 'OlehAssist', a professional and empathetic AI assistant for New Immigrants (Olim) in Israel.

LANGUAGE HANDLING:
- First message: "Hello! I am your personal Aliyah assistant. Before we begin, what is your preferred language?"
- Once selected, respond in that language throughout the session.

INTENT SELECTION:
Present these options:

A) GENERAL INFORMATION:
(Details on rights, benefits, Sal Klita, health care)

B) DOCUMENT UNDERSTANDING:
(Explaining forms, bills, letters, etc.)

C) FIRST STEPS & APPOINTMENTS:
(Setting up phone, bank account, appointments)

DOCUMENT PATH:
- Ask user to attach document using chat input, then type 'upload'
- After upload: IDENTIFY, KEY INFO, EXPLAIN, ACTION STEPS, RISK WARNING

FIRST STEPS PATH:
- Guide through: Phone plan → Bank account → Ministry appointment
- For branch lookup, use find_ministry_of_aliyah_branch tool
- Table: {Ministry_of_aliyah_branch_table}
- Schema: {branch_schema}

Use tools: search_aliyah_information, find_ministry_of_aliyah_branch
"""

config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTIONS,
    tools=[search_aliyah_information, find_ministry_of_aliyah_branch],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="AUTO")
    )
)

# --- CHAT INTERFACE ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = client.chats.create(model=MODEL_ID, config=config)
    st.session_state.messages = []
    greeting = "Hello! I am your personal Aliyah assistant. Before we begin, what is your preferred language?"
    st.session_state.messages.append({"role": "assistant", "content": greeting})

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
prompt = st.chat_input("Type your message (or attach a document)...")

if prompt:
    # Handle both old string format and new dict/object format
    if isinstance(prompt, dict):
        user_text = prompt.get("text", "")
        files = prompt.get("files", [])
    elif isinstance(prompt, str):
        user_text = prompt
        files = []
    else:
        user_text = getattr(prompt, 'text', str(prompt))
        files = getattr(prompt, 'files', [])
    
    # Display user message
    st.chat_message("user").markdown(user_text)
    st.session_state.messages.append({"role": "user", "content": user_text})

    # Prepare message
    message_parts = [user_text]
    
    # Handle upload command
    if user_text.strip().lower() == "upload":
        if files and len(files) > 0:
            st.toast("📎 Attaching file...", icon="📎")
            image_bytes = files[0].getvalue()
            mime = files[0].type
            message_parts = [
                "Please explain this document for me.",
                types.Part.from_bytes(data=image_bytes, mime_type=mime)
            ]
        else:
            with st.chat_message("assistant"):
                warning_msg = "⚠️ Please attach your document first, then type 'upload' and send."
                st.warning(warning_msg)
                st.session_state.messages.append({"role": "assistant", "content": warning_msg})
            st.stop()

    # Get response
    try:
        with st.chat_message("assistant"):
            response = st.session_state.chat_session.send_message(message_parts)

            # Tool calling loop with safety limit
            max_iterations = 5
            iteration = 0
            
            while iteration < max_iterations:
                has_function_call = False
                function_call_part = None
                
                if response.candidates and len(response.candidates) > 0:
                    parts = response.candidates[0].content.parts
                    for part in parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            has_function_call = True
                            function_call_part = part
                            break
                
                if not has_function_call:
                    break
                
                fc = function_call_part.function_call
                tool_name = fc.name
                
                # Execute tool
                if tool_name == "search_aliyah_information":
                    tool_output = search_aliyah_information(**fc.args)
                elif tool_name == "find_ministry_of_aliyah_branch":
                    tool_output = find_ministry_of_aliyah_branch(**fc.args)
                else:
                    tool_output = "Unknown tool."

                # Send result back
                response = st.session_state.chat_session.send_message(
                    types.Part.from_function_response(name=tool_name, response={"content": tool_output})
                )
                
                iteration += 1
            
            if iteration >= max_iterations:
                st.warning("⚠️ Maximum tool iterations reached.")

            # Display final response
            text = response.text if response.text else "..."
            st.markdown(text)
            st.session_state.messages.append({"role": "assistant", "content": text})

    except Exception as e:
        error_msg = f"❌ Error: {e}"
        st.error(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
