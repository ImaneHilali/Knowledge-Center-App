from g4f.client import Client

try:
    client = Client()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say this is a test"}
        ]
    )
    print(response.choices[0].message.content)

except Exception as e:
    print(f"Error: {e}")
