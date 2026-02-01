# AI-Driven Jenkins ChatOps -- Complete Design & Implementation Guide

## Overview

This document consolidates the entire discussion into a single,
end-to-end guide for building an **AI-powered frontend chatbot** that
understands natural language, collects parameters conversationally, and
triggers **Jenkins jobs** securely using **Azure GenAI services**,
**Python**, and **AKS**.

------------------------------------------------------------------------

## Goals

-   Natural language → intent detection
-   Map intent → Jenkins job
-   Conversational parameter collection
-   Validation & confirmation
-   Trigger Jenkins jobs
-   Return execution status
-   Support multiple concurrent users safely

------------------------------------------------------------------------

## High-Level Architecture

User → Chat UI (Python) → FastAPI Backend → Azure OpenAI → Redis (state)
→ Jenkins

------------------------------------------------------------------------

## Technology Stack

### Frontend

-   Python (Streamlit)
-   Chat-based UI

### Backend

-   Python FastAPI
-   REST orchestration

### AI

-   Azure OpenAI (GPT-4o / GPT-4.1)
-   Structured JSON outputs (no agents required)

### State Management

-   Azure Redis Cache (session state)

### Configuration

-   Kubernetes ConfigMaps (jobs.yaml)
-   Kubernetes Secrets (tokens, passwords)

### CI/CD Target

-   Jenkins (REST API trigger)

### Platform

-   AKS (Ingress already available)

------------------------------------------------------------------------

## Job Registry (ConfigMap)

Use YAML to define: - Intent - Jenkins Job Name - Required Parameters -
Documentation Link

Example:

``` yaml
CREATE_NAMESPACE:
  description: "Create Kubernetes namespace"
  jenkins_job: "k8s/namespace/create"
  documentation: "https://confluence/k8s/namespace"
  parameters:
    - name: cluster_name
      required: true
    - name: resource_group
      required: true
    - name: namespace_name
      required: true
```

------------------------------------------------------------------------

## Conversational Flow

1.  User enters request
2.  Azure OpenAI classifies intent
3.  Backend loads job metadata
4.  Missing parameters are requested
5.  User confirms execution
6.  Jenkins job is triggered
7.  Status returned to UI

------------------------------------------------------------------------

## Redis Integration

### Why Redis?

-   Maintains conversation state across messages
-   Fast, cheap, TTL-based cleanup
-   Perfect for session memory

### Data Model

-   Key: session:`<uuid>`{=html}
-   Value: JSON state
-   TTL: 30 minutes

### Python Integration

``` python
redis_client.get("session:abc123")
redis_client.setex("session:abc123", 1800, json_data)
```

------------------------------------------------------------------------

## Jenkins Integration

-   Trigger via REST:

```{=html}
<!-- -->
```
    POST /job/<job-name>/buildWithParameters

-   Auth via Jenkins API token
-   Secrets stored in Kubernetes Secrets

------------------------------------------------------------------------

## Local Development

1.  Create Python virtualenv
2.  Run FastAPI backend (uvicorn)
3.  Run Streamlit frontend
4.  Use local jobs.yaml
5.  Point to Jenkins test instance

------------------------------------------------------------------------

## AKS Deployment

### Namespace

Admin-only namespace for chatbot components

### ConfigMaps

-   jobs.yaml
-   prompt templates

### Secrets

-   Jenkins credentials
-   OpenAI keys
-   Redis password

### Deployments

-   Backend (FastAPI)
-   Frontend (Streamlit)

### Ingress

-   Route frontend access

------------------------------------------------------------------------

## Concurrency & Scaling

-   Redis isolates session per user
-   FastAPI handles concurrent requests easily
-   Azure OpenAI handles high RPM
-   Jenkins queues jobs safely

10 concurrent users: **No issues**\
50+ users: Add backend replicas\
100+ users: Add rate limiting & HPA

------------------------------------------------------------------------

## Cost Breakdown (Monthly Estimate)

  Component             Cost
  --------------------- ------------
  Azure OpenAI          \$10--30
  Azure Redis (Basic)   \$16--20
  AKS                   Existing
  Jenkins               Existing
  Total                 \~\$30--50

------------------------------------------------------------------------

## Security Notes

-   Admin-only namespace
-   Acceptable to use AKS Secrets & ConfigMaps
-   For regulated workloads: migrate secrets to Key Vault

------------------------------------------------------------------------

## Key Design Decisions

-   No MCP server required
-   No agents required
-   Deterministic backend logic
-   YAML-driven job registry
-   Redis for session state

------------------------------------------------------------------------

## Final Takeaway

This solution is **not just a chatbot** --- it is an **AI-assisted
DevOps control plane** that is:

-   Safe
-   Explainable
-   Scalable
-   Cost-effective
-   Enterprise-ready

------------------------------------------------------------------------

End of document.
