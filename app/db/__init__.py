# app/db/__init__.py

from .base import get_dynamodb_resource
from .user_tokens import (
    create_user_tokens_table,
    save_user_tokens,
    get_decrypted_user_tokens,
    delete_user_tokens,
    get_user_tokens_raw
)
from .chat_sessions import create_chat_sessions_table, get_user_conversations
from .user_preferences import (
    create_user_preferences_table,
    save_user_preferences,
    get_user_preferences,
    update_user_preferences,
    delete_user_preferences
)
from .user_tasks import (
    create_user_tasks_table,
    save_user_task,
    get_user_tasks,
    update_user_task,
    delete_user_task
)
from .user_email_mapping import (
    create_user_email_mapping_table,
    save_user_email_mapping,
    get_user_id_by_email,
    delete_user_email_mapping
)
from .tool_execution_results import (
    create_tool_execution_results_table,
    save_tool_execution_result,
    get_tool_execution_results_by_session,
    get_tool_execution_results_by_user,
    get_tool_execution_statistics
)
from .encryption import encrypt_token, decrypt_token

__all__ = [
    'get_dynamodb_resource',
    'create_user_tokens_table',
    'save_user_tokens',
    'get_decrypted_user_tokens',
    'delete_user_tokens',
    'get_user_tokens_raw',
    'create_chat_sessions_table',
    'get_user_conversations',
    'create_user_preferences_table',
    'save_user_preferences',
    'get_user_preferences',
    'update_user_preferences',
    'delete_user_preferences',
    'create_user_tasks_table',
    'save_user_task',
    'get_user_tasks',
    'update_user_task',
    'delete_user_task',
    'create_user_email_mapping_table',
    'save_user_email_mapping',
    'get_user_id_by_email',
    'delete_user_email_mapping',
    'create_tool_execution_results_table',
    'save_tool_execution_result',
    'get_tool_execution_results_by_session',
    'get_tool_execution_results_by_user',
    'get_tool_execution_statistics',
    'encrypt_token',
    'decrypt_token'
]