from openai import OpenAI

client = OpenAI(
    base_url = "https://across-release-enrolled-technologies.trycloudflare.com/v1",
    api_key = "sk-3k9X72s9Zpq8R5tL4nD7gJ1kH6bA2cF5"
)

response = client.chat.completions.create(
    model = "Qwen3.6-35B-A3B",
    messages = [{"role": "user", "content": "你好"}]
)

print(response.choices[0].message.content)