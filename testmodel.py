from openai import OpenAI
client = OpenAI(api_key="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")
models = client.models.list()
print(models)