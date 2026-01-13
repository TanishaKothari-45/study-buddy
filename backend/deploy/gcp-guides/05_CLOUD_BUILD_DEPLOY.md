# 🚀 Phase 9-10: Cloud Build CI/CD & Cloud Run Deployment

## Overview

This guide covers:
- **Cloud Build** - CI/CD pipeline configuration
- **Cloud Run** - Deploying API and Worker services
- **Deployment strategies** - Manual vs automated deployment

**Time Required:** ~30 minutes

---

## 📋 Prerequisites

- Completed all previous guides (01-04)
- All infrastructure ready (SQL, Redis, GCS, Secrets)
- `cloudbuild.yaml` and `Dockerfile` in your repository

```bash
# Verify environment
source ~/study-buddy-env.sh
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Account: $SA_EMAIL"
echo "VPC Connector: $VPC_CONNECTOR_PATH"
echo "SQL Connection: $SQL_CONNECTION"
echo "GCS Bucket: $GCS_BUCKET"
```

---

## Phase 9: Cloud Build CI/CD

### Understanding the `cloudbuild.yaml`

Study Buddy uses a multi-step Cloud Build pipeline that:
1. Builds a shared Docker image
2. Pushes to Artifact Registry
3. Deploys **API Service** to Cloud Run
4. Deploys **Worker Service** to Cloud Run

```yaml
# Simplified structure of cloudbuild.yaml
steps:
  - id: 'build-image'      # Build Docker image
  - id: 'push-image'       # Push to Artifact Registry
  - id: 'deploy-api'       # Deploy study-buddy-api
  - id: 'deploy-worker'    # Deploy study-buddy-worker
```

### Step 9.1: Review Cloud Build Configuration

```bash
# View the existing cloudbuild.yaml
cat backend/cloudbuild.yaml
```

Key configuration elements:

| Element | Value | Description |
|---------|-------|-------------|
| `_REGION` | `asia-south1` | Deployment region |
| `_REPO` | `study-buddy` | Artifact Registry repository |
| `_SERVICE_ACCOUNT` | `study-buddy-backend@...` | Runtime service account |
| `_VPC_CONNECTOR` | `projects/.../connectors/...` | VPC connector path |
| `_SQL_CONNECTION` | `PROJECT:REGION:INSTANCE` | Cloud SQL connection |
| `_GCS_BUCKET` | `study-buddy-uploads` | GCS bucket name |

### Step 9.2: Set Up Substitution Variables

```bash
# Create substitution variables file for easy reference
cat > ~/study-buddy-substitutions.txt << EOF
_REGION=${REGION}
_REPO=${ARTIFACT_REPO}
_SERVICE_ACCOUNT=${SA_EMAIL}
_VPC_CONNECTOR=${VPC_CONNECTOR_PATH}
_SQL_CONNECTION=${SQL_CONNECTION}
_GCS_BUCKET=${GCS_BUCKET}
EOF

cat ~/study-buddy-substitutions.txt
```

### Step 9.3: Grant Cloud Build Permissions

```bash
# Get Cloud Build service account
export CLOUDBUILD_SA="${PROJECT_ID}@cloudbuild.gserviceaccount.com"

# Grant Cloud Run Admin (to deploy services)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin"

# Grant Service Account User (to act as backend SA)
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser"

# Grant Artifact Registry Writer (to push images)
gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
  --location=$REGION \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"

# Grant Secret Manager Accessor (if build needs secrets)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 9.4: Manual Build & Deploy

```bash
# Navigate to backend directory
cd /path/to/study-buddy/backend

# Run Cloud Build with substitutions
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=\
_REGION=$REGION,\
_REPO=$ARTIFACT_REPO,\
_SERVICE_ACCOUNT=$SA_EMAIL,\
_VPC_CONNECTOR=$VPC_CONNECTOR_PATH,\
_SQL_CONNECTION=$SQL_CONNECTION,\
_GCS_BUCKET=$GCS_BUCKET \
  .

# This will:
# 1. Build the Docker image
# 2. Push to Artifact Registry
# 3. Deploy both API and Worker services
```

### Step 9.5: Set Up Automated Triggers (CI/CD)

```bash
# Create a build trigger for main branch
gcloud builds triggers create github \
  --name="study-buddy-deploy" \
  --repo-name="study-buddy" \
  --repo-owner="YOUR_GITHUB_USERNAME" \
  --branch-pattern="^main$" \
  --build-config="backend/cloudbuild.yaml" \
  --substitutions=\
_REGION=$REGION,\
_REPO=$ARTIFACT_REPO,\
_SERVICE_ACCOUNT=$SA_EMAIL,\
_VPC_CONNECTOR=$VPC_CONNECTOR_PATH,\
_SQL_CONNECTION=$SQL_CONNECTION,\
_GCS_BUCKET=$GCS_BUCKET

# List triggers
gcloud builds triggers list
```

> **Note:** You need to connect your GitHub repository first via the Cloud Console:
> https://console.cloud.google.com/cloud-build/triggers/connect

### Step 9.6: Monitor Build Progress

```bash
# List recent builds
gcloud builds list --limit=5

# Get detailed build logs
gcloud builds log BUILD_ID

# Stream logs for ongoing build
gcloud builds log BUILD_ID --stream

# Open build in console
echo "https://console.cloud.google.com/cloud-build/builds?project=${PROJECT_ID}"
```

---

## Phase 10: Cloud Run Deployment

### Understanding the Two Services

Study Buddy deploys **two Cloud Run services** from the same Docker image:

| Service | Purpose | Configuration |
|---------|---------|---------------|
| `study-buddy-api` | REST API (FastAPI) | Public, scale-to-zero |
| `study-buddy-worker` | Background jobs (Arq) | Private, always-on |

### Step 10.1: API Service Configuration

The API service handles HTTP requests:

```bash
# Manual deployment of API service (usually done via Cloud Build)
gcloud run deploy study-buddy-api \
  --image=${IMAGE_PATH}:latest \
  --region=$REGION \
  --platform=managed \
  --service-account=$SA_EMAIL \
  --vpc-connector=$VPC_CONNECTOR_PATH \
  --add-cloudsql-instances=$SQL_CONNECTION \
  --set-secrets="\
OPENAI_API_KEY=OPENAI_API_KEY:latest,\
GEMINI_API_KEY=GEMINI_API_KEY:latest,\
PINECONE_API_KEY=PINECONE_API_KEY:latest,\
JWT_SECRET_KEY=JWT_SECRET_KEY:latest,\
DATABASE_URL=DATABASE_URL:latest,\
REDIS_URL=REDIS_URL:latest,\
ENCRYPTION_KEY=ENCRYPTION_KEY:latest" \
  --set-env-vars="\
ENVIRONMENT=production,\
PINECONE_INDEX_NAME=study-buddy,\
GCS_BUCKET_NAME=$GCS_BUCKET" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --concurrency=80 \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated
```

### API Service Configuration Explained

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--memory` | `2Gi` | Memory allocation |
| `--cpu` | `2` | vCPU allocation |
| `--timeout` | `300` | Request timeout (5 minutes) |
| `--concurrency` | `80` | Max concurrent requests per instance |
| `--min-instances` | `0` | Scale to zero when idle (cost saving) |
| `--max-instances` | `10` | Maximum instances for scaling |
| `--allow-unauthenticated` | - | Public API access |

### Step 10.2: Worker Service Configuration

The Worker service processes background jobs:

```bash
# Manual deployment of Worker service
gcloud run deploy study-buddy-worker \
  --image=${IMAGE_PATH}:latest \
  --region=$REGION \
  --platform=managed \
  --service-account=$SA_EMAIL \
  --vpc-connector=$VPC_CONNECTOR_PATH \
  --add-cloudsql-instances=$SQL_CONNECTION \
  --set-secrets="\
OPENAI_API_KEY=OPENAI_API_KEY:latest,\
GEMINI_API_KEY=GEMINI_API_KEY:latest,\
PINECONE_API_KEY=PINECONE_API_KEY:latest,\
JWT_SECRET_KEY=JWT_SECRET_KEY:latest,\
DATABASE_URL=DATABASE_URL:latest,\
REDIS_URL=REDIS_URL:latest,\
ENCRYPTION_KEY=ENCRYPTION_KEY:latest" \
  --set-env-vars="\
ENVIRONMENT=production,\
PINECONE_INDEX_NAME=study-buddy,\
GCS_BUCKET_NAME=$GCS_BUCKET" \
  --command=python \
  --args="-m,app.worker_entrypoint" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=900 \
  --min-instances=1 \
  --max-instances=3 \
  --no-allow-unauthenticated \
  --cpu-boost \
  --no-cpu-throttling
```

### Worker Service Configuration Explained

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--command` | `python` | Override default CMD |
| `--args` | `-m,app.worker_entrypoint` | Run worker module |
| `--timeout` | `900` | 15 minutes for long jobs |
| `--min-instances` | `1` | Always running (for job processing) |
| `--max-instances` | `3` | Limited scaling |
| `--no-allow-unauthenticated` | - | No public access |
| `--cpu-boost` | - | Boost CPU on startup |
| `--no-cpu-throttling` | - | Full CPU even when no requests |

### Step 10.3: Verify Deployment

```bash
# Get service URLs
gcloud run services describe study-buddy-api \
  --region=$REGION \
  --format="value(status.url)"

gcloud run services describe study-buddy-worker \
  --region=$REGION \
  --format="value(status.url)"

# Save API URL
export API_URL=$(gcloud run services describe study-buddy-api \
  --region=$REGION \
  --format="value(status.url)")

echo "API URL: $API_URL"
```

### Step 10.4: Test the Deployment

```bash
# Test health endpoint
curl "${API_URL}/"
# Expected: {"status": "healthy", ...}

# Test API version endpoint
curl "${API_URL}/api/v1/health"
# Expected: {"status": "ok", ...}

# Test with verbose output for debugging
curl -v "${API_URL}/" 2>&1 | head -30
```

### Step 10.5: View Service Details

```bash
# Describe API service
gcloud run services describe study-buddy-api \
  --region=$REGION \
  --format="yaml(spec.template.spec.containers[0])"

# List all services
gcloud run services list --region=$REGION

# View service revisions
gcloud run revisions list --service=study-buddy-api --region=$REGION
```

---

## 📊 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloud Build Pipeline                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────────┐   │
│  │   GitHub      │    │  Cloud Build  │    │ Artifact Registry │   │
│  │   Push/PR     │───▶│   Trigger     │───▶│  Docker Image     │   │
│  │               │    │               │    │                   │   │
│  └───────────────┘    └───────────────┘    └─────────┬─────────┘   │
│                                                       │              │
│                             ┌─────────────────────────┴──────────┐  │
│                             ▼                                    ▼  │
│                    ┌─────────────────┐              ┌─────────────┐ │
│                    │ study-buddy-api │              │study-buddy- │ │
│                    │  (Cloud Run)    │              │   worker    │ │
│                    │                 │              │ (Cloud Run) │ │
│                    │ • Public        │              │ • Private   │ │
│                    │ • Scale 0-10    │              │ • Scale 1-3 │ │
│                    │ • 2 vCPU/2GB    │              │ • Always-on │ │
│                    └────────┬────────┘              └──────┬──────┘ │
│                             │                              │        │
│                             └──────────────┬───────────────┘        │
│                                            │                        │
│                    ┌───────────────────────▼─────────────────────┐  │
│                    │              VPC Connector                   │  │
│                    │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │  │
│                    │  │Cloud SQL │  │  Redis   │  │    GCS    │ │  │
│                    │  │PostgreSQL│  │Memorystore│  │  Bucket  │ │  │
│                    │  └──────────┘  └──────────┘  └───────────┘ │  │
│                    └────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 💰 Cloud Run Cost Breakdown

### API Service (Scale-to-Zero)

| Component | Configuration | Cost Calculation |
|-----------|--------------|------------------|
| CPU | 2 vCPU × $0.00002400/sec | Per-second when active |
| Memory | 2 GB × $0.00000250/sec | Per-second when active |
| Requests | $0.40 per million | Per request |

**Estimated Monthly Cost:** $20-50 (depends on traffic)

### Worker Service (Always-On)

| Component | Configuration | Cost Calculation |
|-----------|--------------|------------------|
| CPU | 2 vCPU × $0.00002400/sec × 24/7 | ~$62/month |
| Memory | 2 GB × $0.00000250/sec × 24/7 | ~$6.50/month |

**Estimated Monthly Cost:** $30-60 (min 1 instance always running)

### Free Tier (First 2 Million Requests)

Cloud Run includes a generous free tier:
- 2 million requests/month
- 360,000 GB-seconds memory
- 180,000 vCPU-seconds

---

## ✅ Deployment Verification Checklist

```bash
# 1. Verify build succeeded
gcloud builds list --limit=1 --format="table(id,status,createTime)"
# Expected: SUCCESS status

# 2. Verify API service is running
gcloud run services describe study-buddy-api --region=$REGION \
  --format="value(status.conditions[0].status)"
# Expected: True

# 3. Verify Worker service is running
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="value(status.conditions[0].status)"
# Expected: True

# 4. Test API health
curl -s "${API_URL}/" | jq .
# Expected: JSON response with status

# 5. Check API logs
gcloud run services logs read study-buddy-api --region=$REGION --limit=10

# 6. Check Worker logs
gcloud run services logs read study-buddy-worker --region=$REGION --limit=10

# 7. Verify secrets are accessible (from logs)
gcloud run services logs read study-buddy-api --region=$REGION \
  --filter="textPayload:initialized OR textPayload:connected" \
  --limit=5
```

---

## 🔄 Updating Deployments

### Option 1: Full CI/CD Pipeline

```bash
# Trigger full rebuild and deploy
cd backend
gcloud builds submit --config=cloudbuild.yaml .
```

### Option 2: Update Service Configuration Only

```bash
# Update API service memory
gcloud run services update study-buddy-api \
  --region=$REGION \
  --memory=4Gi

# Update Worker scaling
gcloud run services update study-buddy-worker \
  --region=$REGION \
  --min-instances=2 \
  --max-instances=5
```

### Option 3: Deploy Specific Image Version

```bash
# Deploy a specific image tag
gcloud run deploy study-buddy-api \
  --image=${IMAGE_PATH}:BUILD_ID \
  --region=$REGION

# Rollback to previous revision
gcloud run services update-traffic study-buddy-api \
  --region=$REGION \
  --to-revisions=study-buddy-api-00001=100
```

---

## 🚨 Common Issues & Solutions

### Issue: Build fails with "permission denied"

```bash
# Check Cloud Build service account permissions
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${CLOUDBUILD_SA}" \
  --format="table(bindings.role)"

# Re-grant necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin"
```

### Issue: Service fails to start (secret access)

```bash
# Check service logs for secret errors
gcloud run services logs read study-buddy-api --region=$REGION \
  --filter="severity=ERROR" \
  --limit=20

# Verify secrets are accessible
for SECRET in OPENAI_API_KEY GEMINI_API_KEY PINECONE_API_KEY JWT_SECRET_KEY DATABASE_URL REDIS_URL ENCRYPTION_KEY; do
  echo -n "$SECRET: "
  gcloud secrets get-iam-policy $SECRET \
    --filter="bindings.members:${SA_EMAIL}" \
    --format="value(bindings.role)" 2>/dev/null || echo "NOT ACCESSIBLE"
done
```

### Issue: Cannot connect to Redis/Cloud SQL

```bash
# Verify VPC connector is attached
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(spec.template.metadata.annotations)" | grep vpc

# Verify Cloud SQL instance is attached
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(spec.template.metadata.annotations)" | grep cloudsql
```

### Issue: Worker not processing jobs

```bash
# Check worker is running
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="value(status.conditions[0].status)"

# Check worker logs for errors
gcloud run services logs read study-buddy-worker --region=$REGION \
  --filter="textPayload:error OR textPayload:Error" \
  --limit=20

# Verify Redis connectivity
gcloud run services logs read study-buddy-worker --region=$REGION \
  --filter="textPayload:Redis OR textPayload:Arq" \
  --limit=10
```

---

## 📋 Quick Reference

```bash
# Deploy both services
cd backend
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_REGION=$REGION,_REPO=$ARTIFACT_REPO,_SERVICE_ACCOUNT=$SA_EMAIL,_VPC_CONNECTOR=$VPC_CONNECTOR_PATH,_SQL_CONNECTION=$SQL_CONNECTION,_GCS_BUCKET=$GCS_BUCKET .

# Get API URL
export API_URL=$(gcloud run services describe study-buddy-api --region=$REGION --format="value(status.url)")
echo $API_URL

# Test API
curl "${API_URL}/"

# View logs
gcloud run services logs read study-buddy-api --region=$REGION --limit=20
gcloud run services logs read study-buddy-worker --region=$REGION --limit=20

# Update service
gcloud run services update study-buddy-api --region=$REGION --memory=4Gi

# Rollback
gcloud run services update-traffic study-buddy-api --region=$REGION --to-revisions=REVISION_NAME=100
```

---

## ➡️ Next Steps

Proceed to [06_MONITORING_COSTS.md](./06_MONITORING_COSTS.md) to set up monitoring, logging, and cost optimization.
