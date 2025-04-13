import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# MongoDB connection URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "mydatabase")

# Create a MongoDB client
client = MongoClient(MONGO_URI)

# Access the database
def get_database():
    """
    Returns the MongoDB database instance.
    """
    return client[DATABASE_NAME]

# Example: Access a collection
def get_collection(collection_name):
    """
    Returns a specific collection from the database.
    """
    db = get_database()
    return db[collection_name]

# Insert a single document into a collection
def insert_document(collection_name, document):
    """
    Inserts a single document into the specified collection.
    """
    collection = get_collection(collection_name)
    result = collection.insert_one(document)
    return result.inserted_id

# Retrieve all documents from a collection
def get_all_documents(collection_name):
    """
    Retrieves all documents from the specified collection.
    """
    collection = get_collection(collection_name)
    return list(collection.find())