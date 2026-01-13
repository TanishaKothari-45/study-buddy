# 📚 Study Buddy - GCP Infrastructure Documentation

## Complete Guide Index

This documentation provides a comprehensive, step-by-step guide for deploying the Study Buddy backend to Google Cloud Platform. The guides are organized in phases, from initial setup to production-ready deployment.

---

## 📖 Documentation Structure

| Guide | Phase | Description | Time Est. |
|-------|-------|-------------|-----------|
| [01_GCP_SETUP_IAM.md](./01_GCP_SETUP_IAM.md) | Phase 1-2 | Project setup, API enablement, IAM & Service Accounts | 30 min |
| [02_VPC_NETWORKING.md](./02_VPC_NETWORKING.md) | Phase 3 | VPC Connector, Serverless VPC Access, Networking | 15 min |
| [03_INFRASTRUCTURE.md](./03_INFRASTRUCTURE.md) | Phase 4-6 | Cloud SQL, Memorystore Redis, Cloud Storage | 45 min |
| [04_SECRETS_REGISTRY.md](./04_SECRETS_REGISTRY.md) | Phase 7-8 | Secret Manager, Artifact Registry | 20 min |
| [05_CLOUD_BUILD_DEPLOY.md](./05_CLOUD_BUILD_DEPLOY.md) | Phase 9-10 | Cloud Build CI/CD, Cloud Run deployment | 30 min |
| [06_MONITORING_COSTS.md](./06_MONITORING_COSTS.md) | Phase 11-12 | Logging, Monitoring, Cost Analysis | 20 min |
| [07_TROUBLESHOOTING_SECURITY.md](./07_TROUBLESHOOTING_SECURITY.md) | Phase 13-14 | Troubleshooting, Security Checklist | Reference |

**Total Estimated Time:** ~2.5-3 hours for complete setup

---

## 🎯 Quick Start

If you're setting up from scratch, follow the guides in order:

```bash
# Prerequisites
# 1. Google Cloud account with billing enabled
# 2. gcloud CLI installed (https://cloud.google.com/sdk/docs/install)
# 3. Docker installed (for local testing)
# 4. Git repository access

# Quick verification
gcloud --version
docker --version
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Google Cloud Platform                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │   Cloud      │    │   Cloud      │    │   Artifact           │   │
│  │   Build      │───▶│   Run        │    │   Registry           │   │
│  │   (CI/CD)    │    │              │    │   (Docker Images)    │   │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
│                            │                                         │
│                            │ VPC Connector                          │
│                            ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     VPC Network                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │   │
│  │  │   Cloud      │  │  Memorystore │  │   Cloud          │   │   │
│  │  │   SQL        │  │  (Redis)     │  │   Storage        │   │   │
│  │  │  (PostgreSQL)│  │              │  │   (GCS Bucket)   │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Secret Manager                              │   │
│  │  OPENAI_API_KEY | GEMINI_API_KEY | DATABASE_URL | REDIS_URL  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Services Deployed

### 1. Study Buddy API (`study-buddy-api`)
- **Type:** Cloud Run Service
- **Purpose:** Main FastAPI backend serving REST API
- **Configuration:**
  - 2 vCPU, 2GB RAM
  - Scale: 0-10 instances (scale-to-zero)
  - Timeout: 300 seconds
  - Public access (unauthenticated)

### 2. Study Buddy Worker (`study-buddy-worker`)
- **Type:** Cloud Run Service  
- **Purpose:** Background job processing (Mock tests, Evaluations, Mains answers)
- **Configuration:**
  - 2 vCPU, 2GB RAM
  - Scale: 1-3 instances (always-on)
  - Timeout: 900 seconds
  - No HTTP traffic (internal only)
  - CPU boost enabled

---

## 💰 Cost Summary

| Resource | Spec | Monthly Cost (Est.) |
|----------|------|---------------------|
| Cloud Run (API) | 2 vCPU, 2GB, scale-to-zero | $20-50 |
| Cloud Run (Worker) | 2 vCPU, 2GB, min 1 instance | $30-60 |
| Cloud SQL | db-f1-micro | $10-15 |
| Memorystore Redis | 1GB Basic | $35 |
| VPC Connector | e2-micro | $10-15 |
| Cloud Storage | ~10GB | $0.50-2 |
| Secret Manager | 7 secrets | <$1 |
| Artifact Registry | ~5GB | $0.50-1 |
| **Total** | | **$105-180/month** |

See [06_MONITORING_COSTS.md](./06_MONITORING_COSTS.md) for detailed cost analysis and optimization tips.

---

## 🔧 Environment Variables Required

The application requires the following environment variables/secrets:

| Variable | Type | Description |
|----------|------|-------------|
| `OPENAI_API_KEY` | Secret | OpenAI API key for embeddings |
| `GEMINI_API_KEY` | Secret | Google Gemini API key |
| `PINECONE_API_KEY` | Secret | Pinecone vector database API key |
| `JWT_SECRET_KEY` | Secret | JWT signing key (min 32 chars) |
| `ENCRYPTION_KEY` | Secret | User API key encryption |
| `DATABASE_URL` | Secret | PostgreSQL connection string |
| `REDIS_URL` | Secret | Redis connection URL |
| `ENVIRONMENT` | Env Var | `production` or `local` |
| `PINECONE_INDEX_NAME` | Env Var | `study-buddy` |
| `GCS_BUCKET_NAME` | Env Var | `study-buddy-uploads` |

---

## 🚀 Quick Deploy (After Setup)

Once all infrastructure is configured, deploy with:

```bash
# From project root
cd backend
gcloud builds submit --config=cloudbuild.yaml .
```

---

## 📞 Support & Troubleshooting

- See [07_TROUBLESHOOTING_SECURITY.md](./07_TROUBLESHOOTING_SECURITY.md) for common issues
- Check Cloud Logging for runtime errors
- Review Cloud Build logs for deployment issues

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Jan 2026 | Initial documentation |
