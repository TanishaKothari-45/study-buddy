# 🗄️ Phase 4-6: Infrastructure Setup (Cloud SQL, Redis, Storage)

## Overview

This guide covers setting up the core infrastructure services:
- **Cloud SQL** (PostgreSQL) - Primary database
- **Memorystore** (Redis) - Caching and job queues
- **Cloud Storage** (GCS) - File uploads and storage

**Time Required:** ~45 minutes

---

## 📋 Prerequisites

- Completed [01_GCP_SETUP_IAM.md](./01_GCP_SETUP_IAM.md)
- Completed [02_VPC_NETWORKING.md](./02_VPC_NETWORKING.md)
- Environment variables set

```bash
# Verify environment
source ~/study-buddy-env.sh
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "VPC Connector: $VPC_CONNECTOR"
```

---

## Phase 4: Cloud SQL (PostgreSQL)

### Step 4.1: Create Cloud SQL Instance

```bash
# Define database variables
export SQL_INSTANCE="study-buddy-db"
export SQL_DATABASE="studybuddy"
export SQL_USER="studybuddy_user"
export SQL_PASSWORD="$(openssl rand -base64 24)"  # Generate secure password

# Create the Cloud SQL instance
gcloud sql instances create $SQL_INSTANCE \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB \
  --storage-auto-increase \
  --backup-start-time=03:00 \
  --availability-type=zonal \
  --network=default \
  --no-assign-ip  # Private IP only (more secure)

# Note: Instance creation takes 5-10 minutes
echo "⏳ Waiting for instance to be ready..."
```

### Cloud SQL Instance Tiers

| Tier | vCPUs | Memory | Monthly Cost (Est.) | Use Case |
|------|-------|--------|---------------------|----------|
| `db-f1-micro` | Shared | 0.6 GB | $10-15 | Development/Light production |
| `db-g1-small` | Shared | 1.7 GB | $25-35 | Small production |
| `db-custom-1-3840` | 1 | 3.75 GB | $50-70 | Medium production |
| `db-custom-2-7680` | 2 | 7.5 GB | $100-140 | High traffic |

### Step 4.2: Create Database and User

```bash
# Create the database
gcloud sql databases create $SQL_DATABASE \
  --instance=$SQL_INSTANCE

# Create the database user
gcloud sql users create $SQL_USER \
  --instance=$SQL_INSTANCE \
  --password=$SQL_PASSWORD

# Store password securely (you'll need this for secrets)
echo "📝 Save this password securely: $SQL_PASSWORD"
```

### Step 4.3: Get Connection Information

```bash
# Get the connection name (needed for Cloud SQL Connector)
export SQL_CONNECTION=$(gcloud sql instances describe $SQL_INSTANCE \
  --format="value(connectionName)")

echo "SQL Connection Name: $SQL_CONNECTION"
# Format: PROJECT_ID:REGION:INSTANCE_NAME

# Get private IP (if using private IP)
export SQL_PRIVATE_IP=$(gcloud sql instances describe $SQL_INSTANCE \
  --format="value(ipAddresses[0].ipAddress)")

echo "SQL Private IP: $SQL_PRIVATE_IP"
```

### Step 4.4: Build Database URL

```bash
# For Cloud SQL Connector (recommended for Cloud Run)
export DATABASE_URL="postgresql+pg8000://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DATABASE}?unix_sock=/cloudsql/${SQL_CONNECTION}/.s.PGSQL.5432"

# Alternative: For direct private IP connection (requires VPC)
# export DATABASE_URL="postgresql://${SQL_USER}:${SQL_PASSWORD}@${SQL_PRIVATE_IP}:5432/${SQL_DATABASE}"

echo "Database URL: $DATABASE_URL"

# Save to env file
echo "export SQL_CONNECTION=\"$SQL_CONNECTION\"" >> ~/study-buddy-env.sh
```

### Step 4.5: Configure Backups (Optional but Recommended)

```bash
# Enable point-in-time recovery
gcloud sql instances patch $SQL_INSTANCE \
  --enable-point-in-time-recovery \
  --retained-transaction-log-days=7

# Set backup retention (default is 7 automated backups)
gcloud sql instances patch $SQL_INSTANCE \
  --backup-start-time=03:00 \
  --retained-backups-count=7
```

---

## Phase 5: Memorystore (Redis)

### Step 5.1: Create Redis Instance

```bash
# Define Redis variables
export REDIS_INSTANCE="study-buddy-redis"

# Create the Redis instance
gcloud redis instances create $REDIS_INSTANCE \
  --size=1 \
  --region=$REGION \
  --redis-version=redis_7_0 \
  --tier=basic \
  --network=default \
  --connect-mode=DIRECT_PEERING

# Note: Instance creation takes 5-10 minutes
echo "⏳ Waiting for Redis instance to be ready..."
```

### Redis Tier Comparison

| Tier | Memory | High Availability | Monthly Cost (Est.) | Use Case |
|------|--------|-------------------|---------------------|----------|
| Basic 1GB | 1 GB | ❌ No | ~$35 | Development/Light production |
| Basic 2GB | 2 GB | ❌ No | ~$70 | Small production |
| Standard 1GB | 1 GB | ✅ Yes (replica) | ~$70 | Production with HA |
| Standard 5GB | 5 GB | ✅ Yes (replica) | ~$170 | High traffic |

### Step 5.2: Get Redis Connection Information

```bash
# Get Redis host and port
export REDIS_HOST=$(gcloud redis instances describe $REDIS_INSTANCE \
  --region=$REGION \
  --format="value(host)")

export REDIS_PORT=$(gcloud redis instances describe $REDIS_INSTANCE \
  --region=$REGION \
  --format="value(port)")

echo "Redis Host: $REDIS_HOST"
echo "Redis Port: $REDIS_PORT"

# Build Redis URL
export REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}"

echo "Redis URL: $REDIS_URL"

# Save to env file
echo "export REDIS_HOST=\"$REDIS_HOST\"" >> ~/study-buddy-env.sh
echo "export REDIS_PORT=\"$REDIS_PORT\"" >> ~/study-buddy-env.sh
```

### Step 5.3: Verify Redis Connectivity

```bash
# You can test Redis connectivity from Cloud Shell or a VM in the same VPC
# Note: Redis is only accessible from within the VPC

# From Cloud Shell (if in same project):
gcloud compute ssh test-vm --zone=$REGION-a -- \
  "redis-cli -h $REDIS_HOST -p $REDIS_PORT PING"
# Expected: PONG
```

---

## Phase 6: Cloud Storage (GCS)

### Step 6.1: Create Storage Bucket

```bash
# Define bucket name (must be globally unique)
export GCS_BUCKET="study-buddy-uploads-${PROJECT_ID}"

# Create the bucket
gcloud storage buckets create gs://$GCS_BUCKET \
  --location=$REGION \
  --uniform-bucket-level-access \
  --public-access-prevention

# Alternative with storage class:
# gcloud storage buckets create gs://$GCS_BUCKET \
#   --location=$REGION \
#   --default-storage-class=STANDARD \
#   --uniform-bucket-level-access

echo "GCS Bucket: gs://$GCS_BUCKET"

# Save to env file
echo "export GCS_BUCKET=\"$GCS_BUCKET\"" >> ~/study-buddy-env.sh
```

### Storage Class Comparison

| Class | Use Case | Monthly Cost (per GB) |
|-------|----------|----------------------|
| Standard | Frequently accessed data | $0.020 |
| Nearline | Access < 1x/month | $0.010 |
| Coldline | Access < 1x/quarter | $0.004 |
| Archive | Access < 1x/year | $0.0012 |

### Step 6.2: Configure CORS (For Direct Browser Uploads)

```bash
# Create CORS configuration file
cat > /tmp/cors-config.json << 'EOF'
[
  {
    "origin": ["*"],
    "method": ["GET", "PUT", "POST", "DELETE", "OPTIONS"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
    "maxAgeSeconds": 3600
  }
]
EOF

# Apply CORS configuration
gcloud storage buckets update gs://$GCS_BUCKET \
  --cors-file=/tmp/cors-config.json

# Verify CORS
gcloud storage buckets describe gs://$GCS_BUCKET --format="json(cors_config)"
```

### Step 6.3: Set Up Lifecycle Rules (Cost Optimization)

```bash
# Create lifecycle configuration (auto-delete old files)
cat > /tmp/lifecycle-config.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 7,
          "matchesPrefix": ["evaluate_jobs/"]
        }
      },
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 30,
          "matchesPrefix": ["temp/"]
        }
      }
    ]
  }
}
EOF

# Apply lifecycle rules
gcloud storage buckets update gs://$GCS_BUCKET \
  --lifecycle-file=/tmp/lifecycle-config.json

# Verify lifecycle rules
gcloud storage buckets describe gs://$GCS_BUCKET --format="json(lifecycle_config)"
```

### Step 6.4: Grant Service Account Access

```bash
# Grant the backend service account access to the bucket
gcloud storage buckets add-iam-policy-binding gs://$GCS_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Verify permissions
gcloud storage buckets get-iam-policy gs://$GCS_BUCKET \
  --format="table(bindings.role,bindings.members)"
```

---

## 📊 Infrastructure Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Study Buddy Infrastructure                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Cloud SQL (PostgreSQL)                    │   │
│  │  Instance: study-buddy-db                                    │   │
│  │  Tier: db-f1-micro                                          │   │
│  │  Database: studybuddy                                        │   │
│  │  User: studybuddy_user                                       │   │
│  │                                                              │   │
│  │  Tables:                                                     │   │
│  │  - users (authentication, profiles)                          │   │
│  │  - api_keys (user Gemini API keys)                          │   │
│  │  - sessions (JWT sessions)                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Memorystore (Redis)                       │   │
│  │  Instance: study-buddy-redis                                 │   │
│  │  Size: 1GB Basic                                             │   │
│  │  Version: Redis 7.0                                          │   │
│  │                                                              │   │
│  │  Uses:                                                       │   │
│  │  - Arq job queue (background tasks)                          │   │
│  │  - Job status tracking                                       │   │
│  │  - User rate limiting locks                                  │   │
│  │  - Response caching                                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Cloud Storage (GCS)                       │   │
│  │  Bucket: study-buddy-uploads-PROJECT_ID                      │   │
│  │  Class: Standard                                             │   │
│  │  Location: asia-south1                                       │   │
│  │                                                              │   │
│  │  Structure:                                                  │   │
│  │  - evaluate_jobs/     (uploaded answer PDFs)                 │   │
│  │  - temp/              (temporary files)                      │   │
│  │                                                              │   │
│  │  Lifecycle: Auto-delete after 7 days                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 💰 Cost Breakdown

| Resource | Configuration | Monthly Cost (Est.) |
|----------|--------------|---------------------|
| **Cloud SQL** | | |
| - Instance (db-f1-micro) | 1 shared vCPU, 0.6GB RAM | $8-10 |
| - Storage (10GB SSD) | Auto-scaling | $2-5 |
| - Backups | 7 day retention | $1-2 |
| **Memorystore Redis** | | |
| - Basic 1GB | Single instance | $35 |
| **Cloud Storage** | | |
| - Standard storage | ~10GB | $0.20 |
| - Operations | Class A/B | $0.50-2 |
| **Total** | | **$47-55/month** |

---

## ✅ Verification Checklist

```bash
# 1. Verify Cloud SQL instance
gcloud sql instances describe $SQL_INSTANCE \
  --format="table(name,state,databaseVersion,tier,region)"
# Expected: RUNNABLE state

# 2. Verify Cloud SQL database
gcloud sql databases list --instance=$SQL_INSTANCE
# Expected: studybuddy database

# 3. Verify Redis instance
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="table(name,state,tier,memorySizeGb,host)"
# Expected: READY state

# 4. Verify GCS bucket
gcloud storage buckets describe gs://$GCS_BUCKET \
  --format="table(name,location,storageClass)"
# Expected: Bucket exists in asia-south1

# 5. Verify all environment variables
echo "SQL_CONNECTION: $SQL_CONNECTION"
echo "DATABASE_URL: $DATABASE_URL"
echo "REDIS_URL: $REDIS_URL"
echo "GCS_BUCKET: $GCS_BUCKET"
```

---

## 🚨 Common Issues & Solutions

### Issue: Cloud SQL instance creation fails

```bash
# Check if SQL Admin API is enabled
gcloud services list --enabled --filter="name:sqladmin"

# If not enabled:
gcloud services enable sqladmin.googleapis.com
```

### Issue: Redis instance not accessible

```bash
# Verify Redis is in the same network as VPC connector
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="value(authorizedNetwork)"

# Should match: projects/PROJECT_ID/global/networks/default

# Verify VPC connector network
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION \
  --format="value(network)"
```

### Issue: Storage permission denied

```bash
# Re-grant permissions
gcloud storage buckets add-iam-policy-binding gs://$GCS_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Verify
gcloud storage buckets get-iam-policy gs://$GCS_BUCKET
```

### Issue: High Cloud SQL costs

```bash
# Downgrade to smaller tier (development)
gcloud sql instances patch $SQL_INSTANCE \
  --tier=db-f1-micro

# Enable auto-scaling storage to avoid over-provisioning
gcloud sql instances patch $SQL_INSTANCE \
  --storage-auto-increase
```

---

## 📋 Quick Reference

```bash
# Complete infrastructure setup commands
export PROJECT_ID="your-project-id"
export REGION="asia-south1"

# Cloud SQL
export SQL_INSTANCE="study-buddy-db"
export SQL_DATABASE="studybuddy"
export SQL_USER="studybuddy_user"
export SQL_PASSWORD="$(openssl rand -base64 24)"

gcloud sql instances create $SQL_INSTANCE \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB

gcloud sql databases create $SQL_DATABASE --instance=$SQL_INSTANCE
gcloud sql users create $SQL_USER --instance=$SQL_INSTANCE --password=$SQL_PASSWORD

export SQL_CONNECTION=$(gcloud sql instances describe $SQL_INSTANCE --format="value(connectionName)")

# Redis
export REDIS_INSTANCE="study-buddy-redis"

gcloud redis instances create $REDIS_INSTANCE \
  --size=1 \
  --region=$REGION \
  --redis-version=redis_7_0 \
  --tier=basic

export REDIS_HOST=$(gcloud redis instances describe $REDIS_INSTANCE --region=$REGION --format="value(host)")
export REDIS_URL="redis://${REDIS_HOST}:6379"

# GCS
export GCS_BUCKET="study-buddy-uploads-${PROJECT_ID}"

gcloud storage buckets create gs://$GCS_BUCKET \
  --location=$REGION \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://$GCS_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"
```

---

## ➡️ Next Steps

Proceed to [04_SECRETS_REGISTRY.md](./04_SECRETS_REGISTRY.md) to set up Secret Manager and Artifact Registry.
