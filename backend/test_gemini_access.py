"""
Quick script to test which Gemini models you have access to
Run this: python test_gemini_access.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

try:
    import google.generativeai as genai

    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in environment")
        raise SystemExit(1)

    genai.configure(api_key=api_key)
    print("✅ API Key configured\n")

    print("📋 Listing all available models:\n")

    # List all available models
    for model in genai.list_models():
        if 'generateContent' in getattr(model, 'supported_generation_methods', []):
            print(f"✅ {model.name}")
            print(f"   Display Name: {getattr(model, 'display_name', '')}")
            desc = getattr(model, 'description', '') or ''
            print(f"   Description: {desc[:100]}...")
            print()

    print("\n🧪 Testing recommended models:\n")

    # Test specific models
    test_models = [
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-pro',
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro-latest',
    ]

    for model_name in test_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Say 'OK' only")
            if getattr(response, 'text', '').strip():
                print(f"✅ {model_name} - WORKS")
        except Exception as e:
            print(f"❌ {model_name} - {str(e)[:80]}")

    print("\n✅ Test complete!")

except ImportError:
    print("❌ google-generativeai not installed")
    print("Run: pip install google-generativeai")
except Exception as e:
    print(f"❌ Error: {e}")
