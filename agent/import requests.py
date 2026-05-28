import requests
import json

def call_llm(model: str, context: dict):
    """
    Fonction pour appeler l'API Ollama et générer du texte brut.

    Args:
        model (str): Le modèle à utiliser.
        context (dict): Le contexte de la requête.

    Returns:
        str: Le texte brut généré par l'API Ollama.
    """
    # Construire la requête JSON
    data = {
        "prompt": json.dumps(context),
        "model": model,
        "strict": True  # Ajouter prompt system strict pour tool calling JSON
    }

    # Envoyer la requête à l'API Ollama
    response = requests.post("http://localhost:11434/api/generate", json=data)

    # Récupérer le texte brut généré
    text = response.json()["text"]

    return text

# Exemple d'utilisation de la fonction
context = {
    "prompt": "Créer un texte intéressant"
}
model = "ollama"

resultat = call_llm(model, context)
print(resultat)