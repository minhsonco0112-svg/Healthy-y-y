"""Quick script to list available Llama models on your Groq account."""
import asyncio
import os
import openai as openai_client
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.local")


async def main():
    client = openai_client.AsyncClient(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    models = await client.models.list()
    llama = sorted(m.id for m in models.data if "llama" in m.id.lower())
    other = sorted(m.id for m in models.data if "llama" not in m.id.lower())
    print("\n=== Llama models available ===")
    for m in llama:
        print(" -", m)
    print("\n=== Other models ===")
    for m in other:
        print(" -", m)


asyncio.run(main())
