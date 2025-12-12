from openai import OpenAI
import os

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is NOT set.")
        return

    print("API key detected. Testing a simple call...")

    client = OpenAI()

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input="Say hello in one short sentence.",
        )
        print("API call succeeded!")
        print("Response:", response.output_text)
    except Exception as e:
        print("API call failed with error:")
        print(repr(e))

if __name__ == "__main__":
    main()