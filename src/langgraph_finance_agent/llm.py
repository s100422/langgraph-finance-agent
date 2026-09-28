from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_NAME = "gemini-3.6-flash"
llm = ChatGoogleGenerativeAI(model=MODEL_NAME)

LIGHT_MODEL_NAME = "gemini-3.5-flash-lite"
light_llm = ChatGoogleGenerativeAI(model=LIGHT_MODEL_NAME)