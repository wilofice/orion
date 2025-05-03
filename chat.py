import streamlit as st
from unittest.mock import patch, Mock
st.set_page_config(page_title="Calendar AI", layout="wide")
# Initialize session state for chat history and events
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "events" not in st.session_state:
    st.session_state.events = []
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
# Function to handle user input and AI response
import requests
import random
# Function to handle user input and perform a REST API call
def handle_user_input(user_input):
    api_url = "http://127.0.0.1:8000/v1/chat/prompt"  # Replace with your API endpoint
    bearer_token = "1"
    headers = {
        "Content-Type": "application/json",
        "Authorization" : f"Bearer {bearer_token}",
        "Accept": "application/json",
   }  # Set headers for JSON request
    payload = {
      "user_id": "user_from_1",
      "session_id": "session_1",
      "prompt_text": user_input,
      "client_context": {}
    }  # JSON payload to send in the request

    try:
        # Perform the API call
        # mock_response_data = {
        #     "status": "needs_clarification",
        #     "response_text": f"This is a mocked response. {str(random.randint(1, 1000))}",
        #     "clarification_options": [
        #         "Option 1: Please clarify your request.",
        #         "Option 2: Can you provide more details?"
        #     ]
        # }
        # api_response = mock_response_data
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        api_response = response.json()
        if "status" and "response_text" in api_response:  # Adjust based on your API's response structure
            if api_response["status"] == "completed":
                # Append user input and AI response to chat history
                return api_response["response_text"]
            elif api_response["status"] == "needs_clarification":
                # Handle clarification needed case
                return str.join("\n", api_response["clarification_options"])
            return api_response["response_text"]
        else:
            return f"AI: I couldn't process your request. Error detail : \n {api_response['response_text']}"

    except requests.RequestException as e:
        # Handle request errors
        return f"Error: {str(e)}"
        # Verify the chat history was updated with the mocked response


# Function to add a new event
def add_event(event_name):
    st.session_state.events.append({"name": event_name})

# Function to delete an event
def delete_event(index):
    st.session_state.events.pop(index)

# Main Chat Interface
st.title("Calendar AI")
st.write("Interact with the AI to plan and organize your calendar.")

for msg in st.session_state["messages"]:
    print(msg)
    st.chat_message(msg["role"]).write(msg["content"])
# Chat Area
if user_input := st.chat_input(""):
    if user_input.strip():
        st.session_state["messages"].append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)
        ai_response = handle_user_input(user_input)
        st.session_state["messages"].append({"role": "assistant", "content": ai_response})
        st.chat_message("assistant").write(ai_response)


# Sidebar for Event Management
with st.sidebar:
    st.header("Planned Events")
    # Display list of events
    for i, event in enumerate(st.session_state.events):
        st.write(f"{i + 1}. {event['name']}")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Edit", key=f"edit_{i}"):
                st.warning("Editing functionality not implemented yet.")
        with col2:
            if st.button("Delete", key=f"delete_{i}"):
                delete_event(i)

    # Add new event
    # st.subheader("Add New Event")
    # new_event = st.text_input("Event Name:", key="new_event")
    # if st.button("Add Event"):
    #     if new_event.strip():
    #         add_event(new_event)
    #         st.session_state.new_event = ""  # Clear input field