import os

def get_model(task):
    models = {
        'planning/architecture': 'qwen3.5:9b',
        'coding/refactor': 'deepseek-coder-v2',
        'tool execution': 'qwen2.5-coder:7b',
        'fallback': 'llama3.1'
    }
    
    return models.get(task, 'default_model')

def get_ollama_model():
    task = os.environ['TASK']
    model_name = get_model(task)
    return model_name

print(get_ollama_model())