# Step-by-step Flow

1. Generate Terraform JSON

2. Run:
terraform plan -out=tfplan
terraform show -json tfplan > plan.json

3. Run the summarizer:
python summarizer.py plan.json --explain

4. Parsing and summarization (no Azure yet)

- The program loads `plan.json` and iterates `resource_changes`.
- For `aws_instance.web[0]` with action `["update"]`, it outputs:
  - `operation = "update"` and explanation like “Terraform will update aws_instance 'web' at address 'aws_instance.web'.”
- For `aws_s3_bucket.logs` with action `["create"]`, it produces `operation = "create"` and a similar explanation.
- It builds:
  - `total_changes = 2`
  - `operations_breakdown = {"update": 1, "create": 1}`
  - `summary_text` describing both resources.

5. Index creation (first run only)

- The program calls `create_index_if_not_exists`.
- Azure AI Search index `terraform-plans` is created with:
  - Text fields (`type`, `name`, `operation`, `content`)
  - Vector field `content_vector` with 1536 dimensions and HNSW vector search.

6. Embedding generation and caching

- For each resource, `content_text` is created (type, name, operation, address, explanation).
- `embedding_hash = md5(content_text)` is computed.
- If no existing document or hash changed, an embedding is requested from Azure OpenAI using the embedding deployment.
- The document with `content_vector` and `embedding_hash` is uploaded to the index.

7. Optimization on subsequent plans

- If you rerun `terraform plan` and the output is identical, the summarizer recomputes `content_text` and `embedding_hash`.
- When trying to index again, it fetches existing docs:
  - If `embedding_hash` matches, the resource is skipped (no new embedding call).
  - Only resources whose explanations changed generate new embeddings.
- This means embeddings are not created every time, only when the underlying resource change summary text actually changes, which reduces cost and latency significantly.

8. AI explanation

- If `--explain` is used, the tool takes `summary_text` and sends it to the chat deployment (e.g., `gpt-4o-mini`) with `PLAN_SUMMARY_PROMPT`.
- The model returns a concise explanation of the plan, which is printed to the CLI.

---

# What happens on repeated runs

| Scenario                      | Embedding Calls | Index Updates |
|-------------------------------|-----------------|---------------|
| First run on new plan          | 2               | 2 docs        |
| Second run, identical plan     | 0               | 0 docs        |
| Third run, only S3 bucket added| 1               | 1 doc         |

This behavior comes from the `embedding_hash` check in `index_plan_with_embeddings`, which ensures embeddings are only recomputed when the text that feeds the embedding actually changes.


