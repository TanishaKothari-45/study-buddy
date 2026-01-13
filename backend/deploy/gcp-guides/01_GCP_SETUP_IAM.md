# 🚀 Phase 1-2: GCP Project Setup & IAM Configuration

## Overview

This guide covers the initial setup of your Google Cloud Platform project, enabling required APIs, and configuring IAM (Identity and Access Management) with service accounts.

**Time Required:** ~30 minutes

---

## 📋 Prerequisites

Before starting, ensure you have:

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed and authenticated
3. **Project Owner** or **Editor** permissions

### Install gcloud CLI

```bash
# macOS (using Homebrew)
brew install --cask google-cloud-sdk

# Verify installation
gcloud --version

# Initialize and authenticate
gcloud init
gcloud auth login
```

---

## Phase 1: GCP Project Setup

### Step 1.1: Create or Select Project

```bash
# Option A: Create a new project
gcloud projects create study-buddy-prod --name="Study Buddy Production"

# Option B: Use existing project
# List available projects
gcloud projects list

# Set your project ID (replace with your actual project ID)
export PROJECT_ID="study-buddy-prod"

# Configure gcloud to use this project
gcloud config set project $PROJECT_ID
```

### Step 1.2: Enable Billing

```bash
# List billing accounts
gcloud billing accounts list

# Link billing account to project
gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

> ⚠️ **Note:** Replace `BILLING_ACCOUNT_ID` with your actual billing account ID from the list above.

### Step 1.3: Set Default Region

```bash
# Set region (asia-south1 = Mumbai, optimal for India-based users)
export REGION="asia-south1"

# Configure defaults
gcloud config set run/region $REGION
gcloud config set compute/region $REGION

# Verify configuration
gcloud config list
```

### Step 1.4: Enable Required APIs

```bash
# Enable all required APIs in one command
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

# Verify enabled APIs
gcloud services list --enabled --filter="name:run OR name:cloudbuild OR name:artifactregistry OR name:secretmanager OR name:sqladmin OR name:redis OR name:storage OR name:vpcaccess"
```

### API Descriptions

| API | Service | Purpose |
|-----|---------|---------|
| `run.googleapis.com` | Cloud Run | Serverless container deployment |
| `cloudbuild.googleapis.com` | Cloud Build | CI/CD pipeline |
| `artifactregistry.googleapis.com` | Artifact Registry | Docker image storage |
| `secretmanager.googleapis.com` | Secret Manager | Secure secret storage |
| `sqladmin.googleapis.com` | Cloud SQL Admin | PostgreSQL database |
| `redis.googleapis.com` | Memorystore | Redis caching & job queues |
| `storage.googleapis.com` | Cloud Storage | File storage (GCS) |
| `vpcaccess.googleapis.com` | VPC Access | Connect Cloud Run to VPC |
| `compute.googleapis.com` | Compute Engine | VPC networking |
| `logging.googleapis.com` | Cloud Logging | Application logs |
| `monitoring.googleapis.com` | Cloud Monitoring | Metrics & alerts |

---

## Phase 2: IAM & Service Account Configuration

### Step 2.1: Create Service Account

```bash
# Define service account name
export SA_NAME="study-buddy-backend"

# Create the service account
gcloud iam service-accounts create $SA_NAME \
  --display-name="Study Buddy Backend Service Account" \
  --description="Service account for Study Buddy Cloud Run services"

# Get the full service account email
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Verify creation
gcloud iam service-accounts describe $SA_EMAIL
```

### Step 2.2: Assign IAM Roles

The service account needs specific roles to access GCP resources:

```bash
# Assign all required roles
for ROLE in \
  roles/secretmanager.secretAccessor \
  roles/cloudsql.client \
  roles/storage.objectAdmin \
  roles/redis.editor \
  roles/logging.logWriter \
  roles/cloudtrace.agent; do
  
  echo "Assigning role: $ROLE"
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None
done

# Verify assigned roles
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

### Role Descriptions

| Role | Purpose | Why Needed |
|------|---------|------------|
| `roles/secretmanager.secretAccessor` | Read secrets from Secret Manager | Access API keys (OPENAI, GEMINI, etc.) |
| `roles/cloudsql.client` | Connect to Cloud SQL instances | Database connectivity via Cloud SQL Proxy |
| `roles/storage.objectAdmin` | Full control of GCS objects | Upload/download files for evaluations |
| `roles/redis.editor` | Read/write to Memorystore | Job queue operations (Arq worker) |
| `roles/logging.logWriter` | Write application logs | Send logs to Cloud Logging |
| `roles/cloudtrace.agent` | Send trace data | Performance tracing (optional) |

### Step 2.3: Configure Cloud Build Service Account

Cloud Build needs permissions to deploy to Cloud Run:

```bash
# Get the Cloud Build service account
export CLOUDBUILD_SA="${PROJECT_ID}@cloudbuild.gserviceaccount.com"

# Grant Cloud Build permission to deploy to Cloud Run
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin"

# Grant Cloud Build permission to act as the backend service account
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser"

# Grant Cloud Build permission to push to Artifact Registry
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"

# Grant Cloud Build permission to access secrets (for build-time secrets if needed)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 2.4: Set Up Billing Alerts (Recommended)

```bash
# Create a budget alert (requires billing admin)
# This creates an alert at 50%, 90%, and 100% of $200 budget

gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="Study Buddy Monthly Budget" \
  --budget-amount=200USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0

# Note: You can also set this up via Console:
# https://console.cloud.google.com/billing/budgets
```

---

## 🔧 Export Environment Variables Script

Create a script to export all environment variables for future sessions:

```bash
# Create env setup script
cat > ~/study-buddy-env.sh << 'EOF'
#!/bin/bash
# Study Buddy GCP Environment Variables

export PROJECT_ID="study-buddy-prod"  # Replace with your project ID
export REGION="asia-south1"
export SA_NAME="study-buddy-backend"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export CLOUDBUILD_SA="${PROJECT_ID}@cloudbuild.gserviceaccount.com"

# Configure gcloud defaults
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

echo "✅ Study Buddy GCP environment configured"
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Service Account: $SA_EMAIL"
EOF

# Make it executable
chmod +x ~/study-buddy-env.sh

# Source it (and add to .bashrc/.zshrc for persistence)
source ~/study-buddy-env.sh
echo "source ~/study-buddy-env.sh" >> ~/.zshrc
```

---

## ✅ Verification Checklist

Run these commands to verify your setup:

```bash
# 1. Verify project is set
gcloud config get-value project
# Expected: study-buddy-prod (or your project ID)

# 2. Verify region is set
gcloud config get-value run/region
# Expected: asia-south1

# 3. Verify APIs are enabled
gcloud services list --enabled --filter="name:run" --format="value(name)"
# Expected: run.googleapis.com

# 4. Verify service account exists
gcloud iam service-accounts list --filter="email:study-buddy-backend"
# Expected: study-buddy-backend@PROJECT_ID.iam.gserviceaccount.com

# 5. Verify service account roles
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:study-buddy-backend" \
  --format="table(bindings.role)"
# Expected: List of roles assigned
```

---

## 📚 IAM Best Practices

### Principle of Least Privilege

1. **Only grant required roles** - Don't use `roles/editor` or `roles/owner`
2. **Use service accounts** - Don't use personal accounts for services
3. **Review permissions regularly** - Audit IAM policies quarterly

### Service Account Security

```bash
# List service account keys (should be empty for Cloud Run)
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL

# If you see user-managed keys, consider deleting them
# Cloud Run automatically handles authentication
```

### Organization Policies (Enterprise)

For organization-level constraints:

```bash
# Example: Restrict Cloud Run to specific regions
gcloud resource-manager org-policies set-policy \
  --organization=ORG_ID \
  policy.yaml

# Example policy.yaml:
# constraint: constraints/run.allowedIngress
# listPolicy:
#   allowedValues:
#     - internal
#     - internal-and-cloud-load-balancing
```

---

## 🚨 Common Issues & Solutions

### Issue: "Permission denied" when enabling APIs

```bash
# Solution: Ensure you have the right permissions
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"

# You need roles/serviceusage.serviceUsageAdmin or roles/editor
```

### Issue: "Billing not enabled"

```bash
# Solution: Link billing account
gcloud billing accounts list
gcloud billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### Issue: Service account doesn't have permissions

```bash
# Debug: List all roles for the service account
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"

# Re-apply missing role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/MISSING_ROLE"
```

---

## ➡️ Next Steps

Proceed to [02_VPC_NETWORKING.md](./02_VPC_NETWORKING.md) to configure VPC and networking.

---

## 📋 Quick Reference

```bash
# Quick setup commands (copy-paste friendly)
export PROJECT_ID="your-project-id"
export REGION="asia-south1"
export SA_NAME="study-buddy-backend"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com redis.googleapis.com storage.googleapis.com vpcaccess.googleapis.com

gcloud iam service-accounts create $SA_NAME --display-name="Study Buddy Backend"

for ROLE in roles/secretmanager.secretAccessor roles/cloudsql.client roles/storage.objectAdmin roles/redis.editor roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_EMAIL}" --role="$ROLE"
done
```
