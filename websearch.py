from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model="gpt-5.4",
    use_responses_api=True,
)

web_llm = llm.bind_tools([
    {"type": "web_search"}
])

response = web_llm.invoke("Siapakah gun gun febrianza?")

print(response.text)