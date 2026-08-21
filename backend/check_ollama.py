"""Check if Ollama is running and test a model."""
import asyncio
import openai as openai_client


async def main():
    client = openai_client.AsyncClient(
        api_key="ollama",
        base_url="http://localhost:11434/v1",
    )

    # List available models
    try:
        models = await client.models.list()
        print("=== Ollama models available ===")
        for m in models.data:
            print(" -", m.id)
    except Exception as e:
        print(f"❌ Ollama not reachable: {e}")
        print("   Make sure Ollama is running: ollama serve")
        return

    # Test the specific model
    model = "qwen2.5:0.5b"
    print(f"\n=== Testing {model} ===")
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say hi in one sentence."}],
            max_tokens=30,
        )
        print(f"✅ Response: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"❌ Model error: {e}")
        print(f"   Try: ollama pull {model}")


asyncio.run(main())
