import streamlit as st
from app.gemini_function import  get_ai_response, parse_ai_response

# Initialize session state for chat history and events
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "events" not in st.session_state:
    st.session_state.events = []

# Function to handle user input and AI response
def handle_user_input(user_input):
    # Simulate AI response (replace with actual AI integration)
    # ai_response = f"AI: I can help you schedule an event or suggest activities for '{user_input}'."
    ai_response = get_ai_response(user_input)
    # Parse AI response to check if it includes a function call
    result = parse_ai_response(ai_response)
    if result is not None:

        st.session_state.chat_history.append({"user": user_input, "ai": "Event scheduled successfully!"})
    else:
        st.session_state.chat_history.append({"user": user_input, "ai": "AI: I couldn't process your request."})

# Function to add a new event
def add_event(event_name):
    st.session_state.events.append({"name": event_name})

# Function to delete an event
def delete_event(index):
    st.session_state.events.pop(index)

# Main Chat Interface
st.title("Event Planner AI")
st.write("Interact with the AI to plan and organize your events.")

# Chat Area
with st.container():
    user_input = st.text_input("Enter your query:", key="user_input")
    if st.button("Send"):
        if user_input.strip():
            handle_user_input(user_input)
            st.session_state.user_input = ""  # Clear input field

    # Display chat history
    for chat in st.session_state.chat_history:
        st.markdown(f"**You**: {chat['user']}")
        st.markdown(f"**AI**: {chat['ai']}")

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