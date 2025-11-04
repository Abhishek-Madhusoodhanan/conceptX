"""
Test which Gemini models are available with your API key
Run: python test_models.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("TESTING GEMINI MODEL ACCESS")
print("=" * 60)

# Test 1: List available models using genai SDK
try:
    import google.generativeai as genai

    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not found")
        raise SystemExit(1)

    genai.configure(api_key=api_key)
    print("\n✅ API Key configured\n")

    print("📋 Available models that support generateContent:\n")

    available = []
    for model in genai.list_models():
        if 'generateContent' in getattr(model, 'supported_generation_methods', []):
            # Extract just the model ID
            model_id = model.name.replace('models/', '')
            available.append(model_id)
            print(f"  ✅ {model_id}")
            print(f"     Display: {getattr(model, 'display_name', '')}")
            print()

    if not available:
        print("❌ No models found! Check your API key permissions.")
        raise SystemExit(1)

    # Test 2: Try using LangChain with found models
    print("\n" + "=" * 60)
    print("TESTING WITH LANGCHAIN")
    print("=" * 60 + "\n")

    from langchain_google_genai import ChatGoogleGenerativeAI

    for model_name in available[:3]:  # Test first 3 models
        try:
            print(f"Testing {model_name}...")
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.7,
                max_retries=1,
                timeout=30,
            )
            response = llm.invoke("Say 'Hello' only")
            if getattr(response, 'content', ''):
                print(f"  ✅ {model_name} WORKS with LangChain")
                print(f"  Response: {response.content[:50]}")
            print()
        except Exception as e:
            print(f"  ❌ {model_name} failed: {str(e)[:80]}")
            print()

    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)

    if available:
        print(f"\nUse these models in your agent.py:")
        print(f"\navailable_models = [")
        for model in available[:5]:
            print(f'    "{model}",')
        print(f"]")

except ImportError as e:
    print(f"❌ Missing package: {e}")
    print("Run: pip install google-generativeai langchain-google-genai")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
