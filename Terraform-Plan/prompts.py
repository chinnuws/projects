PLAN_SUMMARY_PROMPT = """
You are a Terraform infrastructure expert. Given this Terraform plan summary, provide a clear, concise explanation of what will happen.

Terraform Plan Summary:
{summary}

Explain:
1. What resources are being created, updated, deleted, or replaced.
2. Why these changes might be happening (common reasons).
3. Potential risks or things to verify before apply.
4. High-level business impact.

Keep the explanation under 300 words and use a professional tone.
"""

RESOURCE_EXPLANATION_PROMPT = """
Explain this specific Terraform resource change for non-technical stakeholders.

Resource type: {resource_type}
Resource name: {resource_name}
Address: {address}
Operation: {operation}
Details: {details}

Provide:
- A simple English explanation.
- What this resource does in the infrastructure.
- Business impact of this change.
"""
