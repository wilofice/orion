Tasks

1) In conversations_router.py, when retrieving user conversations, we should only return user messages and the AI messages. It means ConversationRole should be either USER or AI.
2) in auth_router.py, when retrieving user access and refresh tokens and authenticating the user, we are generating a GUID for the user ID. We should use the user email as the user ID instead of generating a GUID.
3) In conversations_router.py, when retrieving user conversations, we should limit the total number of conversations returned. This means we need to limit the number of messages using a pagination. If the user want to see more older messages, he must ask for it
4) Persist tools execution results in a dedicated DynamoDB table. This will allow us to keep track of the results of tool executions and provide a history of tool interactions
5) Implement asynchronous calendar operations to improve throughput.
6) Use dependency injection throughout to simplify configuration and testing.
7) Replace any stub Gemini and tool executor implementations with real services.