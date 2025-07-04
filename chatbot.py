import json
import os
from dotenv import load_dotenv
import sqlite3
from groq import Groq
from flask import Flask, request, jsonify

class IntentClassifier:
    def __init__(self):
        self.intents = self._load_json('intents.json')
        self.responses = self._load_json('responses.json')
        self.queries = self._load_json('queries.json')
        self.db_config = self._load_json('db_config.json')

        load_dotenv()

        api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=api_key)
        self.fallback_intent = "fallback"

    def _load_json(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def classify_intent(self, prompt):
        prompt_system = (
            "Você é um classificador de intenções. Responda APENAS com a chave da intent correspondente ou 'fallback'.\n"
            "Intenções disponíveis:\n"
        )
        for intent in self.intents:
            patterns = ", ".join(intent['patterns'])
            prompt_system += f"- {intent['response_key']}: {patterns}\n"

        messages = [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": f"Classifique: '{prompt}'"}
        ]

        response = self.client.chat.completions.create(
            messages=messages,
            model="llama3-8b-8192",
            temperature=0.1,
            max_tokens=10,
            stop=["\n"]
        )

        intent_key = response.choices[0].message.content.strip().lower()
        valid_keys = [intent['response_key'] for intent in self.intents]
        return intent_key if intent_key in valid_keys else self.fallback_intent

    def execute_sql_query(self, query_key):
        conn = sqlite3.connect(self.db_config['path'])
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(self.queries[query_key])
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        cursor.close()
        conn.close()
        return results

    def format_response(self, intent_key, data=None):
        template = self.responses.get(intent_key, "Desculpe, não entendi.")
        if not data:
            return template
        if isinstance(data, list):
            if not data:
                return "Nenhum resultado encontrado."
            header = " | ".join(data[0].keys())
            rows = "\n".join([" | ".join(map(str, row.values())) for row in data])
            return f"{template}\n\n{header}\n{rows}"
        return template.replace("{dados}", str(data))

    def respond(self, prompt):
        intent_key = self.classify_intent(prompt)
        if intent_key in self.queries:
            data = self.execute_sql_query(intent_key)
            return self.format_response(intent_key, data)
        return self.responses.get(intent_key, self.responses.get(self.fallback_intent, "Desculpe, não entendi."))

# API
app = Flask(__name__)
# Objeto LLM
classifier = IntentClassifier()

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    try:
        payload = request.get_json()
        prompt = payload.get('prompt', '').strip()
        if not prompt:
            return jsonify({'error': 'O campo "prompt" é obrigatório.'}), 400

        bot_response = classifier.respond(prompt)
        return jsonify({'response': bot_response}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
