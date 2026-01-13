# 🚀 Study Buddy - GCP Cloud Run Deployment Guide

## Quick Overview

This guide covers deploying Study Buddy backend to **Google Cloud Run** with:
- **Cloud SQL** (PostgreSQL) for persistent storage
- **Memorystore** (Redis) for caching and job queues
- **Secret Manager** for secure API key storage
- **Cloud Build** for CI/CD

---

## 📋 Prerequisites

1. Google Cloud account with billing enabled
2. `gcloud` CLI installed and authenticated
3. Docker installed (for local testing)
4. Git repository access

---

## 🔧 Phase 1: GCP Project Setup

```bash
# Set your project ID
export PROJECT_ID="your-project-id"
export REGION="asia-south1"

# Configure gcloud
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  vpcaccess.googleapis.com
```

---

## 🔐 Phase 2: Service Account & IAM

```bash
# Create service account
export SA_NAME="study-buddy-backend"
gcloud iam service-accounts create $SA_NAME \
  --display-name="Study Buddy Backend"

export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Assign roles
for ROLE in \
  roles/secretmanager.secretAccessor \
  roles/cloudsql.client \
  roles/storage.objectAdmin \
  roles/redis.editor \
  roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done
```

---

## 🗄️ Phase 3: Infrastructure

### Cloud SQL (PostgreSQL)
```bash
gcloud sql instances create study-buddy-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION

gcloud sql databases create studybuddy --instance=study-buddy-db
gcloud sql users create studybuddy_user --instance=study-buddy-db --password=YOUR_PASSWORD
```

### VPC Connector (for Redis access)
```bash
gcloud compute networks vpc-access connectors create study-buddy-connector \
  --region=$REGION \
  --network=default \
  --range=10.8.0.0/28
```

### Memorystore Redis
```bash
gcloud redis instances create study-buddy-redis \
  --size=1 \
  --region=$REGION \
  --redis-version=redis_7_0
```

---

## 🔑 Phase 4: Secrets

```bash
# Create secrets
echo -n "your-openai-key" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "your-gemini-key" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "your-pinecone-key" | gcloud secrets create PINECONE_API_KEY --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create JWT_SECRET_KEY --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create ENCRYPTION_KEY --data-file=-

# Database URL
SQL_CONNECTION=$(gcloud sql instances describe study-buddy-db --format="value(connectionName)")
echo -n "postgresql://studybuddy_user:YOUR_PASSWORD@/${studybuddy}?host=/cloudsql/${SQL_CONNECTION}" | \
  gcloud secrets create DATABASE_URL --data-file=-

# Redis URL
REDIS_HOST=$(gcloud redis instances describe study-buddy-redis --region=$REGION --format="value(host)")
echo -n "redis://${REDIS_HOST}:6379" | gcloud secrets create REDIS_URL --data-file=-

# Grant access
for SECRET in OPENAI_API_KEY GEMINI_API_KEY PINECONE_API_KEY JWT_SECRET_KEY ENCRYPTION_KEY DATABASE_URL REDIS_URL; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

## 📦 Phase 5: Build & Deploy

### Option A: Manual Deploy
```bash
cd backend

# Build image
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/study-buddy/backend

# Deploy to Cloud Run
gcloud run deploy study-buddy-api \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/study-buddy/backend \
  --region=$REGION \
  --service-account=$SA_EMAIL \
  --vpc-connector=study-buddy-connector \
  --add-cloudsql-instances=${SQL_CONNECTION} \
  --set-secrets="OPENAI_API_KEY=OPENAI_API_KEY:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,PINECONE_API_KEY=PINECONE_API_KEY:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --allow-unauthenticated
```

### Option B: Automated CI/CD with Cloud Build
```bash
# Submit build using cloudbuild.yaml
gcloud builds submit --config=cloudbuild.yaml .
```

---

## 🌐 Phase 6: Verify Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe study-buddy-api --region=$REGION --format="value(status.url)")

# Test health endpoint
curl "${SERVICE_URL}/"

# Test API
curl "${SERVICE_URL}/api/v1/health"
```

---

## 💰 Cost Estimate

| Resource | Spec | Monthly Cost |
|----------|------|--------------|
| Cloud Run | 2 vCPU, 2GB RAM, scale-to-zero | ~$20-50 |
| Cloud SQL | db-f1-micro | ~$10-15 |
| Memorystore Redis | 1GB Basic | ~$35 |
| VPC Connector | e2-micro | ~$10-15 |
| **Total** | | **~$75-115/month** |

---

## 🔄 Updating the Deployment

```bash
# Trigger new build
gcloud builds submit --config=cloudbuild.yaml .

# Or update service directly
gcloud run services update study-buddy-api --region=$REGION --image=NEW_IMAGE_URL
```

---

## 🛟 Troubleshooting

### View Logs
```bash
gcloud run services logs read study-buddy-api --region=$REGION --limit=50
```

### Check Service Status
```bash
gcloud run services describe study-buddy-api --region=$REGION
```

### Connect to Cloud SQL
```bash
gcloud sql connect study-buddy-db --user=studybuddy_user
```

---

## 📚 Files Modified for Cloud Run

| File | Changes |
|------|---------|
| `backend/app/core/config.py` | Cloud Run detection, Secret Manager support |
| `backend/app/core/database.py` | PostgreSQL + Cloud SQL support |
| `backend/app/worker.py` | Dynamic Redis URL from environment |
| `backend/requirements.txt` | Added GCP dependencies |
| `backend/Dockerfile` | Production-ready multi-stage build |
| `backend/cloudbuild.yaml` | CI/CD pipeline |
