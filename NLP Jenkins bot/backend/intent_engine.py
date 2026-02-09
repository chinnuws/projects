import re

INTENT_KEYWORDS = {
    "create_aks_cluster": ["aks", "kubernetes cluster", "create cluster"],
    "create_namespace": ["namespace"],
    "create_rolebinding": ["rolebinding", "role binding", "rbac"]
}

def extract_intent(user_input: str):
    text = user_input.lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if re.search(keyword, text):
                return intent

    return None
