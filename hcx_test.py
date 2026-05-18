import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["CLOVASTUDIO_API_KEY"],
    base_url="https://clovastudio.stream.ntruss.com/v1/openai",
)

response = client.chat.completions.create(
    model="HCX-005",
    messages=[
        {"role": "system", "content": "당신은 친절한 한국어 AI 어시스턴트입니다."},
        {"role": "user", "content": "안녕! 너 자신을 한 문장으로 소개해줘."},
    ],
)

print(response.choices[0].message.content)
print("\n--- 사용 토큰 ---")
print(response.usage)
