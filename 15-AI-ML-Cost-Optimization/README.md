# 15 — AI/ML Cost Optimization (Platform Level)

> *Beyond pure GPU compute, an AI platform encompasses vector databases, data pipelines, embedding generation, and prompt orchestration. FinOps here requires looking at the entire pipeline.*

---

## 📊 The Hidden Costs of AI/ML Pipelines

When building RAG (Retrieval-Augmented Generation) or fine-tuning pipelines, costs often accumulate outside the LLM itself:

1. **Vector Databases (OpenSearch / Pinecone / pgvector):** Highly memory-intensive, running 24/7.
2. **Embedding Generation:** Processing millions of documents through embedding models costs money and compute time.
3. **Data Egress:** Moving massive datasets across AZs/Regions for training.
4. **ETL Pipelines:** EMR/Glue costs to clean and prep data before training.

---

## 🔍 Vector Database Rightsizing

If using Amazon OpenSearch Serverless for vector storage:
- It bills in **OCUs (OpenSearch Compute Units)**.
- 1 OCU = $0.24/hour (Search) + $0.24/hour (Indexing).
- A minimum deployment (2 OCUs) costs ~$350/month even if idle.

**Optimization:**
- For Dev/Test RAG pipelines, use a local Chroma/FAISS database or a tiny RDS PostgreSQL instance with `pgvector` (`db.t4g.small` = ~$12/month).
- Reserve OpenSearch Serverless / Pinecone for Production.

---

## 📉 Embedding Cost Optimization

Embedding models turn text into numerical vectors. 

**Cost Comparison for 1 Billion Tokens:**
- OpenAI `text-embedding-3-small`: $20.00
- Cohere Embed (Bedrock): ~$100.00
- Amazon Titan Embeddings V2: $20.00
- HuggingFace `all-MiniLM-L6-v2` on AWS Inferentia: **~$2.00 (Self-hosted compute)**

**Action:** If you are embedding billions of tokens for enterprise search, do not use per-token APIs. Host an open-source embedding model (like `BGE-m3` or `MiniLM`) on an AWS Inferentia (`inf2.xlarge`) instance or a CPU instance.

---

## 🚦 Caching AI Responses (Semantic Caching)

LLM API calls (Bedrock/Anthropic) are expensive and slow. If 10 users ask "What is the company holiday policy?", you shouldn't pay the LLM 10 times.

**Implement Semantic Caching:**
Instead of exact text matching, cache the *meaning* of the question.

```python
# Pseudo-architecture for Semantic Caching
# 1. User asks question -> Embed question into vector
# 2. Query Redis/VectorDB for similar questions (cosine similarity > 0.95)
# 3. If match found -> Return cached answer (Cost: $0.0001, Latency: 10ms)
# 4. If no match -> Call Bedrock LLM -> Cache Answer -> Return (Cost: $0.05, Latency: 3s)
```

AWS Services for caching: **ElastiCache (Redis) with Vector Search capability**.

---

## ✅ AI/ML Platform FinOps Checklist

- [ ] Implement Prompt/Semantic Caching for all user-facing AI applications.
- [ ] Self-host embedding generation for bulk document processing instead of using APIs.
- [ ] Use `pgvector` on RDS Graviton for dev/test vector stores instead of expensive managed vector DBs.
- [ ] Log token usage per-user and per-tenant to enable AI unit economics (Cost per AI interaction).
- [ ] Implement request truncation/windowing (limit conversation history length sent to LLMs).
