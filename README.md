Orion - Your AI Calendar Assistant
Overview
Orion is an AI-powered personal calendar assistant designed to automate your schedule management. It aims to understand your requests in natural language and seamlessly integrate with your existing calendars to create, modify, and manage your events. This project is being built step-by-step, with a focus on learning and understanding each component.

Current Status
As of this point, the project is in its early stages. The following functionalities and components are under development or have been explored:

Google Calendar Integration: We have experimented with using the Google Calendar API to programmatically create events on a connected calendar.
Gemini AI Integration: We have explored using the Google Gemini Generative API to understand natural language prompts and extract necessary information for scheduling events. This includes defining function calls to structure Gemini's responses for event creation.
Basic Backend Setup (Conceptual): We have begun to outline the structure of a FastAPI backend to handle requests for scheduling events. This includes defining a Pydantic model for event data and creating a basic endpoint to receive POST requests.
Planned Architecture
Orion is envisioned as a microservices architecture, with the following key components:

Event Management Service: Responsible for the core logic of creating, reading, updating, and deleting calendar events, and interacting with calendar APIs.
Natural Language Processing (NLP) Service: Utilizes AI models (like Gemini) to understand user commands and extract event details.
Reminders and Notifications Service: Manages event reminders and sends notifications through various channels.
User Interface (UI) Service: Provides a user-friendly interface (web and mobile) for interacting with Orion.
User Management Service: Handles user authentication and profile management.
Email Integration Service: Extracts event information from emails.
Database: MongoDB is planned for storing application-specific data and potentially caching calendar information for efficiency.
Getting Started (Developer Notes)
As this project is currently under development, there are no public releases or user-facing setup instructions yet. However, if you are following along with the development:

Set up a Python environment: Ensure you have Python 3.x installed.
Install dependencies: Use pip install -r requirements.txt (once this file is created with the necessary libraries like fastapi, uvicorn, google-generativeai, google-api-python-client, pymongo, and python-dotenv).
Configure API Keys: You will need API keys for Google Gemini and potentially other services. Store these securely, for example, in a .env file.
Google Calendar Credentials: Set up and download your Google Calendar API credentials JSON file.
Next Steps
The immediate next steps in the development process include:

Implementing the connection to the Google Calendar API within the FastAPI backend.
Building the logic within the FastAPI endpoint to take validated event data and create an event using the Google Calendar API.
Potentially defining the schema for storing event data in MongoDB.
Further refining the Gemini integration for more robust natural language understanding.
Contributing
As this is currently a personal learning project, contributions are not yet being actively solicited. However, feedback and suggestions are always welcome.

License
This project is currently unlicensed.

Contact
[genereux.alahassa@gmail.com]
