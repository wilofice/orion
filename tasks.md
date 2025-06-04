Tasks

1) In conversations_router.py, when retrieving user conversations, we should only return user messages and the AI messages. It means ConversationRole should be either USER or AI.
2) in auth_router.py, when retrieving user access and refresh tokens and authenticating the user, we are generating a GUID for the user ID each time. We should only a new GUID only if the user is connecting the first time. That means we need to check if the user already exists in the database and only generate a new GUID if they do not. We should also ensure that the user ID is consistent across sessions. This will help us maintain a consistent user identity and avoid creating multiple user records for the same user. This will also help us avoid issues with user sessions and ensure that the user can access their data consistently across different sessions. We need to map the user id to the user email. Therefore we need a Dynamodb table to store user emails and their corresponding user IDs. This will allow us to retrieve the user ID based on the email and ensure that the user ID is consistent across sessions. We should also ensure that the user ID is unique and not duplicated across different users. This will help us maintain a consistent user identity and avoid issues with user sessions.
3) In conversations_router.py, when retrieving user conversations, we should limit the total number of conversations returned. This means we need to limit the number of messages using a pagination. If the user want to see more older messages, he must ask for it
4) Persist tools execution results in a dedicated DynamoDB table. This will allow us to keep track of the results of tool executions and provide a history of tool interactions
5) Implement asynchronous calendar operations to improve throughput.
6) Use dependency injection throughout to simplify configuration and testing.
7) Replace any stub Gemini and tool executor implementation with real services.
8) Implement a caching layer for frequently accessed data to improve performance and reduce latency.
9) Gemini must have a way to handle a context per user 
10) Gemini must respond in french
11) Gemini must know user preferences about timezones, language, and other settings
12) in orchestration_service.py, we need to update the handle_chat_request method.
    - We need to remove this condition "while current_turn < turn_limit:" . In fact we need to continue querying gemini until we get a final response. If it is a function call, we need to execute the function and then continue querying gemini until we get a final response.
13) I found the current python files too long, we need to split them in smaller files. Don't forget to update the imports. Don't modify the functionality of the code, just split the files.
14) Our current api is relying heavily on google calendar api. 
    - We need to implement the handling of the user's calendar in a way that will allow us to use any calendar service in the futur. 
15) Currently, our AI calendar tools are not handling attendees other than the user. 
    - We need to implement the handling of attendees in a way that will allow us to add attendees to events and meetings.
16) We are heavivly relying on Gemini for our AI capabilities. We need to implement a mechanism to handle using different AI services (openapi, claude, etc) depending on a parameter (model of choice) in settings.
    - We need to implement a fallback mechanism to handle cases where Gemini is not available or fails to respond. 
    - This will ensure that our application remains functional even in the event of a service outage or failure
17) Add a docker compose file to run the application with all its dependencies, including the database (dynamodb => for that , you need to check localdb/docker-compose) and any other services it relies on. 
    - This will allow us to easily deploy and run the application in a consistent environment.
18) the docker-compose up -d is working well. the docker container is being created but I can't access my api from my machine when I go to localhost:8080/Prod/docs. Can you tell why ?
19) We are evolving the api to handle voice messages.