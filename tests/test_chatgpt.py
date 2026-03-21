from openai import OpenAI
import os

api_key = os.environ.get('OPENAI_API_KEY', '')
client = OpenAI(api_key=api_key)

response = client.responses.create(
    model="gpt-5.4-mini",
    input="根据昨天行情表现和宏观环境，今天推荐5个股票 未来一个月内可以上涨20% 要求剔除st股和科创板 要求底部无限放量 股价也在低位，给出买入价和卖出价，给出买入原因。股价必须通过搜索获得。"
)

print(response.output_text)

