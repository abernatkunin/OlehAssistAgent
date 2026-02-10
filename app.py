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

# --- AUTHENTICATION ---
@st.cache_resource
def get_clients():
    """Initialize Google Cloud clients with credentials from secrets"""
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
    
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION, credentials=credentials)
    bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
    return client, bq_client

try:
    client, bq_client = get_clients()
except Exception as e:
    st.error(f"❌ Could not connect to Google Cloud: {e}")
    st.stop()

# --- TOOLS ---
def search_aliyah_information(query: str) -> str:
    """
    Searches the ministry of Aliyah's knowledge base (Data Store) for information to aid new immigrants to Israel in navigating bureaucracy.
    Use this for any informational questions.

    Args:
        query: The search query (e.g., "How do I sign up for health insurance?", "How do I get a passport?").
    """
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
                                if link:
                                    results_text += f" (Source: {link})"
                                results_text += "\n"
                    else:
                        snippets = data.get('snippets', [])
                        for snippet_item in snippets:
                            snippet_content = snippet_item.get('snippet', '').strip()
                            if snippet_content and snippet_content != "No snippet is available for this page.":
                                results_text += f"- {snippet_content}"
                                if link:
                                    results_text += f" (Source: {link})"
                                results_text += "\n"

            status.update(label="✅ Search complete!", state="complete")

            if not results_text:
                if has_documents:
                    return "I could not find an answer to your question. Try rephrasing your question or being more specific."
                else:
                    return "No specific information found regarding your question."
            else:
                return results_text

        except Exception as e:
            status.update(label="❌ Search failed", state="error")
            return f"Error searching knowledge base: {str(e)}"

def find_ministry_of_aliyah_branch(query: str) -> List[Dict[str, Any]]:
    """
    Executes a SQL query against BigQuery and returns the results as a list of dictionaries.
    Args:
        query: The SQL query string to execute.
    """
    with st.status("Executing BigQuery SQL...", expanded=False) as status:
        try:
            query_job = bq_client.query(query)
            results = []
            for row in query_job.result():
                results.append(dict(row.items()))
            status.update(label="✅ Query complete!", state="complete")
            return results
        except Exception as e:
            status.update(label="❌ Query failed", state="error")
            return [{"error": str(e)}]

# --- GET SCHEMA ---
schema_query = f"""
SELECT field_path AS column_name, data_type, description
FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE table_name = 'ministry_of_aliyah_branch_info'
"""
try:
    branch_schema = find_ministry_of_aliyah_branch(schema_query)
except:
    branch_schema = "Schema unavailable"

# --- SYSTEM INSTRUCTIONS (UNCHANGED FROM ORIGINAL) ---
CORE_PERSONA = """
You are 'OlehAssist', a professional and empathetic AI assistant for New Immigrants (Olim) in Israel.
Your mission is to guide users through the complex Aliyah bureaucracy with clarity and patience.

LANGUAGE HANDLING (FIRST PRIORITY):
- Your first message must be: "Hello! I am your personal Aliyah assistant. Before we begin, what is your preferred language?"
- Do NOT provide advice until the user selects a language.
- Once selected, respond in that language and maintain it throughout the session.
"""

INTENT_SELECTION = """
INTENT SELECTION (SECOND PRIORITY):
Once the language is set, present these options EXACTLY as formatted below.
You MUST use a double line break (\\n\\n) between each title and its description:

A) GENERAL INFORMATION:
(Providing details on rights, benefits, Sal Klita, and health care)

B) DOCUMENT UNDERSTANDING:
(Explaining confusing forms, bills, letters, etc.)

C) FIRST STEPS & APPOINTMENTS:
(Guiding you through the essential first steps in Israel, such as setting up a phone, bank account, and making important appointments)

Instruction: Use capital letters for the titles and wrap the descriptions in parentheses on a new line.
"""

ROUTING_LOGIC = """
ROUTING LOGIC:
1. Route based on intent:
   - "appointments," "bank," or "phone" -> FIRST STEPS PATH.
   - "benefits," "rights," or "how things work" -> GENERAL INFO PATH.
   - Letters, bills, or forms -> DOCUMENT_UNDERSTANDING_PATH.

2. MANDATORY UI INSTRUCTION:
   - When the user chooses Option B or asks about a document, you MUST explicitly say:
     "To select a photo from your local computer files, please type the word 'upload' in the chat."
   - DO NOT tell them to look for icons or "attach" buttons.
   - DO NOT provide the analysis summary (Identify, Extract, etc.) until AFTER they have uploaded the file.
"""

STYLE_AND_FLOW = """
STYLE:
- Simple, professional, and scannable (use bullet points).
- Don't overwhelm: provide the 2-3 most important points first.
- Use strategic emojis to improve clarity:
  * 📋 For document lists/checklists
  * ✅ For completed steps or requirements met
  * ⚠️ For important warnings or deadlines
  * 📞 For contact information
  * 🏛️ For government offices/ministries
  * 💰 For payment/financial information
  * 📍 For locations/addresses
- Keep emojis professional: 1-2 per response, only where they add clarity.
- End responses naturally based on context:
  * If explaining a multi-step process: "Would you like details on [specific next step]?"
  * If listing options: "Which of these applies to your situation?"
  * If providing general info: End without a forced question - let the user guide the conversation.
"""

GENERAL_INFO_PATH = """
1) GENERAL INFORMATION PATH:
   - Use the 'search_aliyah_information' tool to provide accurate data for new immigrants in Israel on:
Rights/benefits (Sal Klita, Ulpan), Procedures (Teudat Zehut, health care),  Timelines, etc.
   - Summarize clearly and practically, step by step.
   - If vague, ask a clarifying question before using tools.
"""

DOCUMENT_EXPLAINER_PATH = """
2) DOCUMENT UNDERSTANDING PATH (Visual Analysis):
- User can upload documents and you will analyze them to help them understand and handle them
- Initial Response: Ask the user to type 'upload' to upload a file from their local computer
(if they don't type 'upload' exactly, check first that the input is not simply a mispelling of 'upload'. If it appears as a mispelling of the word 'upload',
tell them, respectfully, to try typing 'upload' again but in the exact spelling.)
- After they type 'upload', and you have received the document (bill, government letter, contract, etc.):
- IDENTIFY: State clearly what the document is (e.g., "This is an Arnona/Property Tax bill from the Jerusalem Municipality").
- KEY INFO: Extract the most relevant info (ex. 'Total Amount Due', 'Due Date', 'Consumer ID')
- EXPLAIN: Summarize the purpose of the letter in 1-2 simple sentences.
- ACTION STEPS: Tell the user exactly what to do.
    * Example: "Go to the website listed at the bottom to pay," or "Take this to the bank to set up a Hora'at Keva (standing order)."
- RISK WARNING: If the document appears legally binding, urgent, or
high-risk (e.g., court notice, legal demand, enforcement letter, fine, or debt collection),
clearly warn the user and recommend contacting the issuing authority or a qualified professional before taking action.
"""

FIRST_TASKS_PATH = f"""
3) FIRST STEPS PATH:
Your goal is to guide the user through the three essential bureaucracy steps in strict order.
Do not jump to Step 3 until you have verified that the user has completed Steps 1 and 2.

STEP 1: ISRAELI PHONE PLAN
- Ask: "Have you already signed up for an Israeli phone plan?"
- If no: Explain that a local number is required for almost every other registration (including banking and government appointments). Advise them to visit a nearby phone provider to acquire a SIM card.
- If yes: Proceed to Step 2.

STEP 2: ISRAELI BANK ACCOUNT
- Ask: "Have you opened an Israeli bank account yet?"
- If no: Inform the user that they must visit a physical bank branch of their choice.
- Provide this mandatory Document Checklist:
  * Teudat Zehut
  * Passport (from country of origin)
  * NIS cash or check (for the initial deposit to activate the account)
  * US Citizens: Must provide their Social Security Number (SSN) for FATCA compliance forms.
- If yes: Proceed to Step 3.

STEP 3: MINISTRY OF ALIYAH (MISRAD HAKLITA) APPOINTMENT
- Explain Purpose: This appointment is essential to "activate your benefits," receive your initial Sal Klita (Absorption Basket) payment, and be assigned a personal Aliyah mentor.
- Document Checklist for appointment:
  * Teudat Zehut
  * All passports (original and Israeli)
  * Bank account details (from Step 2)
  * Passport pictures
  * Proof of living abroad (if applicable)
- Action A: Refer them to book an appointment online via 'myvisit.com'. Also, tell them that if they don't succeed in booking online for any reason,
you can help them locate their locate branch and will provide them the necessary details to book an appointment by phone/email.
- Action B: If the user states they cannot successfully book an appointment online, say:
  '"I will help you find the phone, email, and address for your local branch so you can contact them directly. Which city or town do you live in?"

- TOOL LOGIC (Text-to-SQL):
  * IMPORTANT: The database 'serving' column contains city names in ENGLISH (e.g., 'Tel Aviv', 'Jerusalem').
  * SPELLING CORRECTION (BEFORE TRANSLATION): Correct typos and alternative spellings
    in ANY language first, then translate to English. Meaning, if the city name is in a
    non-English language (HEBREW, Russian, French, Spanish, etc.), you must first check for typos and then translate
    it to ENGLISH before generating the SQL.
  * ONLY after the user provides a city or town name, call the `find_ministry_of_aliyah_branch` tool.
  * Table Schema to use: {branch_schema}
  * SQL Generation Rule: Generate a valid BigQuery SQL query to find the contact info for that city.
  * Fuzzy Matching: Always use `LOWER(serving) LIKE '%city_name_in_english%'` to ensure you catch the city.
  * Query Template: `SELECT branch, address, email, contact FROM {Ministry_of_aliyah_branch_table} WHERE LOWER(serving) LIKE '%city_name_in_english%'`

- Fallback: If the tool returns no results, or if you cannot find a specific branch, provide the following link:
  "I could not find a specific branch for your location in my database.
  Please refer to this official list to find your closest branch: https://www.gov.il/en/government-service-branches"
"""

SYSTEM_INSTRUCTIONS = f"""
{CORE_PERSONA}
{INTENT_SELECTION}
{ROUTING_LOGIC}
{STYLE_AND_FLOW}

--- SPECIFIC PATHS ---
{GENERAL_INFO_PATH}
{DOCUMENT_EXPLAINER_PATH}
{FIRST_TASKS_PATH}
"""

# --- CONFIGURATION ---
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTIONS,
    tools=[search_aliyah_information, find_ministry_of_aliyah_branch],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="AUTO")
    )
)

# --- STREAMLIT CHAT INTERFACE ---
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
# Sidebar for file uploads
with st.sidebar:
    st.header("📄 Document Upload")
    st.info("When ready, type 'upload' in the chat")
    uploaded_file = st.file_uploader("Select a file", type=['png', 'jpg', 'jpeg', 'pdf'], key="doc_upload")

# Chat input (simple version without file attachment)
prompt = st.chat_input("Type your message...")


if prompt:
    user_text = prompt
    files = []

    
    # Display user message
    st.chat_message("user").markdown(user_text)
    st.session_state.messages.append({"role": "user", "content": user_text})

    # Prepare message
    message_parts = [user_text]
    
    # Handle upload command
    if user_text.lower() == "upload":
        if uploaded_file is not None:
            st.toast("📎 Uploading file...", icon="📎")
            image_bytes = uploaded_file.getvalue()
            mime = uploaded_file.type
            message_parts = [
                "Please explain this document for me.",
                types.Part.from_bytes(data=image_bytes, mime_type=mime)
            ]
        else:
            with st.chat_message("assistant"):
                warning_msg = "📁 No file attached. Please attach a file using the chat input, then type 'upload' again."
                st.warning(warning_msg)
                st.session_state.messages.append({"role": "assistant", "content": warning_msg})
            st.stop()

    # Get response
    try:
        with st.chat_message("assistant"):
            response = st.session_state.chat_session.send_message(message_parts)

            # Tool calling loop
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
                
                if tool_name == "search_aliyah_information":
                    tool_output = search_aliyah_information(**fc.args)
                elif tool_name == "find_ministry_of_aliyah_branch":
                    tool_output = find_ministry_of_aliyah_branch(**fc.args)
                else:
                    tool_output = "Unknown tool."

                response = st.session_state.chat_session.send_message(
                    types.Part.from_function_response(name=tool_name, response={"content": tool_output})
                )
                
                iteration += 1
            
            if iteration >= max_iterations:
                st.warning("⚠️ Maximum tool iterations reached.")

            # Get response text
            text = response.text if response.text else ""
            
            # Menu formatting
            menu_keywords = ["GENERAL INFORMATION", "DOCUMENT UNDERSTANDING", "FIRST STEPS"]
            
            if text and all(key in text.upper() for key in menu_keywords):
                text = (
                    "I can help you with a few things. Please choose one of the following options:\n\n"
                    "**A) GENERAL INFORMATION:**\n(rights, benefits, Sal Klita, health care, etc.)\n\n"
                    "**B) DOCUMENT UNDERSTANDING:**\n(confusing forms, bills, letters, etc.)\n\n"
                    "**C) FIRST STEPS & APPOINTMENTS:**\n(Guiding for essential first steps in Israel, such as setting up a phone, bank account, and making your Ministry of Aliyah Appointment)"
                )
            
            if text:
                st.markdown(text)
                st.session_state.messages.append({"role": "assistant", "content": text})
            else:
                fallback = "I'm sorry, I didn't catch that. Could you please repeat?"
                st.markdown(fallback)
                st.session_state.messages.append({"role": "assistant", "content": fallback})

    except Exception as e:
        error_msg = f"❌ Error: {e}"
        st.error(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
