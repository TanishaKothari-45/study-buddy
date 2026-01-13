# 🔐 Phase 7-8: Secret Manager & Artifact Registry

## Overview

This guide covers:
- **Secret Manager** - Secure storage for API keys and credentials
- **Artifact Registry** - Docker image storage for Cloud Run deployments

**Time Required:** ~20 minutes

---

## 📋 Prerequisites

- Completed [01_GCP_SETUP_IAM.md](./01_GCP_SETUP_IAM.md)
- Completed [03_INFRASTRUCTURE.md](./03_INFRASTRUCTURE.md)
- All infrastructure variables from previous guides

```bash
# Verify environment
source ~/study-buddy-env.sh
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Account: $SA_EMAIL"
echo "SQL Connection: $SQL_CONNECTION"
echo "Redis URL: $REDIS_URL"
```

---

## Phase 7: Secret Manager

### Step 7.1: Understand Required Secrets

Study Buddy requires the following secrets:

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `OPENAI_API_KEY` | OpenAI API key for embeddings | [OpenAI Platform](https://platform.openai.com/api-keys) |
| `GEMINI_API_KEY` | Google Gemini API key | [AI Studio](https://aistudio.google.com/app/apikey) |
| `PINECONE_API_KEY` | Pinecone vector DB API key | [Pinecone Console](https://app.pinecone.io) |
| `JWT_SECRET_KEY` | JWT signing key (generated) | Auto-generated |
| `ENCRYPTION_KEY` | API key encryption key | Auto-generated |
| `DATABASE_URL` | PostgreSQL connection string | From Cloud SQL setup |
| `REDIS_URL` | Redis connection URL | From Memorystore setup |

### Step 7.2: Create Secrets

```bash
# Define your API keys (replace with actual values)
# IMPORTANT: Never commit these to version control!

export OPENAI_KEY="sk-your-openai-key-here"
export GEMINI_KEY="your-gemini-key-here"
export PINECONE_KEY="your-pinecone-key-here"

# Generate secure keys for JWT and encryption
export JWT_SECRET="$(openssl rand -base64 32)"
export ENCRYPTION_SECRET="$(openssl rand -base64 32)"

# Echo to save (do this in a secure location)
echo "Generated JWT_SECRET: $JWT_SECRET"
echo "Generated ENCRYPTION_SECRET: $ENCRYPTION_SECRET"
```

### Step 7.3: Store Secrets in Secret Manager

```bash
# Create OPENAI_API_KEY secret
echo -n "$OPENAI_KEY" | gcloud secrets create OPENAI_API_KEY \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create GEMINI_API_KEY secret
echo -n "$GEMINI_KEY" | gcloud secrets create GEMINI_API_KEY \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create PINECONE_API_KEY secret
echo -n "$PINECONE_KEY" | gcloud secrets create PINECONE_API_KEY \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create JWT_SECRET_KEY secret
echo -n "$JWT_SECRET" | gcloud secrets create JWT_SECRET_KEY \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create ENCRYPTION_KEY secret
echo -n "$ENCRYPTION_SECRET" | gcloud secrets create ENCRYPTION_KEY \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create DATABASE_URL secret
echo -n "$DATABASE_URL" | gcloud secrets create DATABASE_URL \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create REDIS_URL secret
echo -n "$REDIS_URL" | gcloud secrets create REDIS_URL \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"
```

### Step 7.4: Grant Service Account Access to Secrets

```bash
# List of secrets that the backend service account needs
SECRETS=(
  "OPENAI_API_KEY"
  "GEMINI_API_KEY"
  "PINECONE_API_KEY"
  "JWT_SECRET_KEY"
  "ENCRYPTION_KEY"
  "DATABASE_URL"
  "REDIS_URL"
)

# Grant access to each secret
for SECRET in "${SECRETS[@]}"; do
  echo "Granting access to $SECRET..."
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"
done

# Verify access (check one secret as example)
gcloud secrets get-iam-policy OPENAI_API_KEY \
  --format="table(bindings.role,bindings.members)"
```

### Step 7.5: Verify Secrets

```bash
# List all secrets
gcloud secrets list --format="table(name,createTime)"

# Verify a secret's latest version (don't echo the value!)
gcloud secrets versions list OPENAI_API_KEY --format="table(name,state,createTime)"

# Test accessing a secret value (for debugging only)
# gcloud secrets versions access latest --secret=JWT_SECRET_KEY
```

### Step 7.6: Update Secret Values (When Needed)

```bash
# To update an existing secret, add a new version:
echo -n "new-secret-value" | gcloud secrets versions add SECRET_NAME --data-file=-

# Disable old versions (optional, for security)
gcloud secrets versions disable SECRET_NAME --version=1

# Example: Rotate OPENAI_API_KEY
# echo -n "$NEW_OPENAI_KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
```

---

## Phase 8: Artifact Registry

### Step 8.1: Create Docker Repository

```bash
# Define repository name
export ARTIFACT_REPO="study-buddy"

# Create Artifact Registry repository
gcloud artifacts repositories create $ARTIFACT_REPO \
  --repository-format=docker \
  --location=$REGION \
  --description="Study Buddy Docker images"

# Verify creation
gcloud artifacts repositories describe $ARTIFACT_REPO \
  --location=$REGION
```

### Step 8.2: Configure Docker Authentication

```bash
# Configure Docker to authenticate with Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# This adds authentication helper to ~/.docker/config.json
# You should see output like:
# Adding credentials for: asia-south1-docker.pkg.dev
```

### Step 8.3: Understand Image Naming

The full image path format is:
```
{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPOSITORY}/{IMAGE}:{TAG}
```

For Study Buddy:
```bash
# Full image path
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/backend"

echo "Image Path: $IMAGE_PATH"
# Example: asia-south1-docker.pkg.dev/study-buddy-prod/study-buddy/backend

# Save to env file
echo "export IMAGE_PATH=\"$IMAGE_PATH\"" >> ~/study-buddy-env.sh
```

### Step 8.4: Build and Push Image Manually (Optional)

```bash
# Navigate to backend directory
cd /path/to/study-buddy/backend

# Build the image
docker build -t ${IMAGE_PATH}:latest -f Dockerfile .

# Push to Artifact Registry
docker push ${IMAGE_PATH}:latest

# Verify the push
gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}
```

> **Note:** You typically won't need to build manually. Cloud Build handles this automatically during deployment.

### Step 8.5: Grant Cloud Build Access to Artifact Registry

```bash
# Cloud Build service account needs to push images
gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
  --location=$REGION \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"

# Cloud Run needs to pull images
gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
  --location=$REGION \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.reader"
```

### Step 8.6: Configure Cleanup Policy (Cost Optimization)

```bash
# Create cleanup policy to delete old images (keep last 10 versions)
cat > /tmp/cleanup-policy.json << 'EOF'
{
  "cleanupPolicies": {
    "keep-last-10": {
      "action": "KEEP",
      "condition": {
        "tagState": "ANY",
        "newerThan": "2592000s"
      },
      "mostRecentVersions": {
        "keepCount": 10
      }
    },
    "delete-old-untagged": {
      "action": "DELETE",
      "condition": {
        "tagState": "UNTAGGED",
        "olderThan": "604800s"
      }
    }
  }
}
EOF

# Apply cleanup policy
gcloud artifacts repositories set-cleanup-policies $ARTIFACT_REPO \
  --location=$REGION \
  --policy=/tmp/cleanup-policy.json

# Alternatively, use gcloud to delete old images manually:
# gcloud artifacts docker images delete ${IMAGE_PATH}:old-tag --quiet
```

---

## 📊 Secret Manager Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Secret Manager                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  API Keys (External Services)                                │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │   │
│  │  │ OPENAI_API_  │ │ GEMINI_API_  │ │ PINECONE_API │        │   │
│  │  │    KEY       │ │    KEY       │ │    _KEY      │        │   │
│  │  │ sk-xxx...    │ │ AIzaSy...    │ │ pcsk_xxx...  │        │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Security Keys (Generated)                                   │   │
│  │  ┌────────────────────┐ ┌────────────────────┐              │   │
│  │  │ JWT_SECRET_KEY     │ │ ENCRYPTION_KEY     │              │   │
│  │  │ (32+ chars)        │ │ (32+ chars)        │              │   │
│  │  │ For JWT signing    │ │ For API key        │              │   │
│  │  │                    │ │ encryption         │              │   │
│  │  └────────────────────┘ └────────────────────┘              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Connection Strings                                          │   │
│  │  ┌────────────────────────────┐ ┌────────────────────────┐  │   │
│  │  │ DATABASE_URL               │ │ REDIS_URL              │  │   │
│  │  │ postgresql+pg8000://...    │ │ redis://10.x.x.x:6379  │  │   │
│  │  │ Cloud SQL connection       │ │ Memorystore connection │  │   │
│  │  └────────────────────────────┘ └────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Access Control:                                                     │
│  study-buddy-backend@PROJECT.iam → secretmanager.secretAccessor     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 💰 Cost Breakdown

| Resource | Configuration | Monthly Cost (Est.) |
|----------|--------------|---------------------|
| **Secret Manager** | | |
| - 7 secrets | Active versions | $0.06 |
| - Access operations | ~10,000 reads/month | $0.03 |
| **Artifact Registry** | | |
| - Storage | ~5GB of images | $0.50-1.00 |
| - Egress | Pull operations | $0.10-0.50 |
| **Total** | | **<$2/month** |

---

## ✅ Verification Checklist

```bash
# 1. List all secrets
gcloud secrets list --format="table(name)"
# Expected: 7 secrets listed

# 2. Verify service account access to a secret
gcloud secrets get-iam-policy OPENAI_API_KEY \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="value(bindings.role)"
# Expected: roles/secretmanager.secretAccessor

# 3. Verify Artifact Registry repository exists
gcloud artifacts repositories describe $ARTIFACT_REPO \
  --location=$REGION --format="value(name)"
# Expected: projects/PROJECT_ID/locations/REGION/repositories/study-buddy

# 4. Verify Docker authentication
cat ~/.docker/config.json | grep "${REGION}-docker.pkg.dev"
# Expected: Entry for asia-south1-docker.pkg.dev

# 5. Test Docker authentication (optional)
docker pull ${IMAGE_PATH}:latest 2>&1 | head -5
# Expected: "latest: Pulling from..." or "Image up to date"
```

---

## 🔒 Secret Management Best Practices

### 1. Never Log Secrets

```bash
# ❌ Bad: Echoing secret values
gcloud secrets versions access latest --secret=OPENAI_API_KEY

# ✅ Good: Only verify secret exists
gcloud secrets versions list OPENAI_API_KEY --format="table(name,state)"
```

### 2. Use Specific Secret Versions in Production

```bash
# In cloudbuild.yaml, use specific versions for stability:
# --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:1

# Or use :latest for automatic updates (convenient but less predictable)
# --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:latest
```

### 3. Rotate Secrets Regularly

```bash
# Schedule for quarterly rotation:
# - API keys: Rotate every 90 days
# - JWT secret: Rotate every 180 days (causes user logout)
# - Database password: Rotate every 90 days

# Add new version (old version still works)
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-

# After verifying new version works, disable old version
gcloud secrets versions disable SECRET_NAME --version=OLD_VERSION_NUMBER
```

### 4. Audit Secret Access

```bash
# View audit logs for secret access
gcloud logging read "resource.type=audited_resource AND protoPayload.serviceName=secretmanager.googleapis.com" \
  --limit=10 \
  --format="table(timestamp,protoPayload.authenticationInfo.principalEmail,protoPayload.methodName)"
```

---

## 🚨 Common Issues & Solutions

### Issue: "Permission denied when accessing secret"

```bash
# Re-grant access
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

# Verify binding
gcloud secrets get-iam-policy SECRET_NAME
```

### Issue: "Secret not found"

```bash
# List all secrets to verify name
gcloud secrets list

# Check if secret exists
gcloud secrets describe SECRET_NAME 2>&1 || echo "Secret does not exist"
```

### Issue: "Docker push fails to Artifact Registry"

```bash
# Re-authenticate Docker
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Verify repository permissions
gcloud artifacts repositories get-iam-policy $ARTIFACT_REPO \
  --location=$REGION \
  --format="table(bindings.role,bindings.members)"

# Ensure writer role for Cloud Build
gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
  --location=$REGION \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"
```

### Issue: "Artifact Registry storage costs increasing"

```bash
# List images and their sizes
gcloud artifacts docker images list ${IMAGE_PATH} \
  --format="table(package,version,createTime)" \
  --sort-by="createTime"

# Delete old images manually
gcloud artifacts docker images delete ${IMAGE_PATH}:old-tag --quiet

# Or apply cleanup policy (see Step 8.6)
```

---

## 📋 Quick Reference

```bash
# Complete secrets and registry setup
export PROJECT_ID="your-project-id"
export REGION="asia-south1"
export SA_EMAIL="study-buddy-backend@${PROJECT_ID}.iam.gserviceaccount.com"
export ARTIFACT_REPO="study-buddy"

# Create all secrets
echo -n "$OPENAI_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "$GEMINI_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "$PINECONE_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create JWT_SECRET_KEY --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create ENCRYPTION_KEY --data-file=-
echo -n "$DATABASE_URL" | gcloud secrets create DATABASE_URL --data-file=-
echo -n "$REDIS_URL" | gcloud secrets create REDIS_URL --data-file=-

# Grant access to all secrets
for SECRET in OPENAI_API_KEY GEMINI_API_KEY PINECONE_API_KEY JWT_SECRET_KEY ENCRYPTION_KEY DATABASE_URL REDIS_URL; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"
done

# Create Artifact Registry
gcloud artifacts repositories create $ARTIFACT_REPO \
  --repository-format=docker \
  --location=$REGION

# Configure Docker
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

---

## ➡️ Next Steps

Proceed to [05_CLOUD_BUILD_DEPLOY.md](./05_CLOUD_BUILD_DEPLOY.md) to set up Cloud Build CI/CD and deploy to Cloud Run.
