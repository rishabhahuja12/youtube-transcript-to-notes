import json

content = []
with open(r'C:\Users\asus\.gemini\antigravity-cli\brain\7b8f0200-690a-4db9-9472-3f018df83bed\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if 'tool_calls' in data and len(data['tool_calls']) > 0:
                tc = data['tool_calls'][0]
                if tc['name'] == 'write_to_file' and 'Implementation Plan: React + FastAPI UI Migration' in tc['args'].get('CodeContent', ''):
                    content.append(tc['args']['CodeContent'])
        except:
            pass

out = content[1] if len(content) > 1 else (content[0] if content else 'Not found')
with open('temp_plan.md', 'w', encoding='utf-8') as f:
    f.write(out)
