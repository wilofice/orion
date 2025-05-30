from google import genai
from google.genai import types
import json

user_prompt = "Schedule a meeting from 4PM to 6PM on 8th Mai 2025 ending. The meeting is about Presenting Calendar AI. The meeting will be held in Paris."

def get_ai_response(prompt):
    schedule_meeting_function = {
        "name": "schedule_event",
        "description": "Schedules a meeting with specified attendees at a given time and date.",
        "parameters": {
            "type": "object",
            "properties": {
                "startDate": {
                    "type": "string",
                    "description": "Start Date of the meeting (e.g., '2024-07-29')",
                },
                "startTime": {
                    "type": "string",
                    "description": "Start Time of the meeting (e.g., '15:00:00')",
                },
                "endDate": {
                    "type": "string",
                    "description": "End Date of the meeting (e.g., '2024-07-29')",
                },
                "endTime": {
                    "type": "string",
                    "description": "End Time of the meeting (e.g., '15:00:00')",
                },
                "topic": {
                    "type": "string",
                    "description": "The subject or topic of the meeting.",
                },
                "description": {
                    "type": "string",
                    "description": "The subject or topic of the meeting.",
                },
                "timeZone": {
                    "type": "string",
                    "description": "The timezone of the meeting. (e.g. 'America/New_York'), (e.g. 'Europe/Paris').",
                },
            },
            "required": ["startDate", "startTime", "endDate", "endTime", "topic", "timeZone"],
        },
    }
    # Configure le client pour l'api générative de Gemini et les outils
    with open('config.json') as config_file:
        config = json.load(config_file)
        api_key = config['api_key']
    client = genai.Client(api_key=api_key)
    tools = types.Tool(function_declarations=[schedule_meeting_function])
    config = types.GenerateContentConfig(tools=[tools])
    # Executer le model avec le prompt
    ai_response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=config,
    )

    return ai_response

# Définir les fonctions que l'intelligence artificielle peut appeler

def parse_ai_response(ai_response):
    if ai_response.candidates[0].content.parts[0].function_call:
        function_call = ai_response.candidates[0].content.parts[0].function_call
        print(f"Function to call: {function_call}")
        print(f"Parameters: {function_call.args}")

        # Dynamically call the method specified in function_call
        method_name = function_call.name
        method_to_call = globals().get(method_name)
        if method_to_call:
            return True
            #return method_to_call(**function_call.args)
        else:
            print(f"Error: Method '{method_name}' not found.")
            return False
    else:
        print("No function call found in the response.")
        print(f"Response: {ai_response.text}")
        return False


# Verifier la réponse de l'IA et appeler la fonction correspondante avec les paramètres
#ai_response = get_ai_response(user_prompt)
#result = parse_ai_response(ai_response)
#print(result)
