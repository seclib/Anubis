
from typing import List, Dict, Any

def plan_steps(task: str, memory_context: str = "") -> List[Dict[str, Any]]:
	"""
	Décompose la tâche en steps avec un goal et un tool_hint.
	Ne fait que planifier, pas d'exécution.
	"""
	# Version simple : 1 step = 1 goal = task
	# À améliorer avec LLM ou heuristique plus tard
	return [
		{
			"step": 1,
			"goal": task.strip(),
			"tool_hint": "read_file"  # Suggestion par défaut, à ajuster
		}
	]
