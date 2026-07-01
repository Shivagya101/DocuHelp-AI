import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# Initialize the single global LLM instance using the official ChatGroq provider
# ChatGroq perfectly supports .with_structured_output() using Pydantic models!
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY", "NOT_SET"),
    model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    temperature=0.0,
)
