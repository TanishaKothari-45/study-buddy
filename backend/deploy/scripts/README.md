# 🚀 Study Buddy GCP Deployment Scripts

Automated deployment scripts for deploying Study Buddy to Google Cloud Platform.

## 📁 Script Overview

| Script | Phase | Description |
|--------|-------|-------------|
| `00_common.sh` | - | Shared functions (don't run directly) |
| `01_init_project.sh` | 1-2 | Project setup, API enablement, IAM |
| `02_setup_network.sh` | 3 | VPC connector setup |
| `03_create_infra.sh` | 4-6 | Cloud SQL, Redis, Cloud Storage |
| `04_setup_secrets.sh` | 7-8 | Secret Manager, Artifact Registry |
| `05_deploy_services.sh` | 9-10 | Cloud Build, Cloud Run deployment |
| `verify.sh` | - | Health checks on all resources |
| `status.sh` | - | Show deployment status |
| `destroy.sh` | - | Teardown all resources |

## 🚀 Quick Start

### 1. Configure

```bash
# Copy example config
cp config.env.example config.env

# Edit with your settings
nano config.env  # or vim, code, etc.
```

**Required settings in `config.env`:**
- `PROJECT_ID` - Your GCP project ID
- `BILLING_ACCOUNT_ID` - Run `gcloud billing accounts list` to find this

### 2. Make Scripts Executable

```bash
chmod +x *.sh
```

### 3. Full Deployment

Run all phases sequentially:

```bash
./01_init_project.sh    # ~5 min - Project & IAM setup
./02_setup_network.sh   # ~3 min - VPC connector
./03_create_infra.sh    # ~15 min - SQL, Redis, Storage
./04_setup_secrets.sh   # ~5 min - Secrets & Registry
./05_deploy_services.sh # ~10 min - Build & Deploy
```

Or run them in sequence:
```bash
./01_init_project.sh && \
./02_setup_network.sh && \
./03_create_infra.sh && \
./04_setup_secrets.sh && \
./05_deploy_services.sh
```

### 4. Verify Deployment

```bash
./verify.sh   # Health checks
./status.sh   # Status overview
```

## 📋 Individual Scripts Usage

### `01_init_project.sh` - Project & IAM Setup

Sets up GCP project, enables APIs, creates service account, assigns IAM roles.

```bash
./01_init_project.sh          # Interactive mode
./01_init_project.sh --dry-run  # Show what would be done
```

**Creates:**
- GCP Project (if not exists)
- Service Account (`study-buddy-backend@...`)
- IAM role bindings
- Enables 11 required APIs

### `02_setup_network.sh` - VPC Networking

Creates VPC connector for Cloud Run to access Redis/SQL.

```bash
./02_setup_network.sh
./02_setup_network.sh --dry-run
```

**Creates:**
- Serverless VPC Access Connector

### `03_create_infra.sh` - Infrastructure

Creates database, cache, and storage resources.

```bash
./03_create_infra.sh
./03_create_infra.sh --dry-run
```

**Creates:**
- Cloud SQL (PostgreSQL 15)
- Memorystore (Redis 7.0)
- Cloud Storage Bucket

**⚠️ Important:** Save the database password shown after Cloud SQL creation!

### `04_setup_secrets.sh` - Secrets & Registry

Stores API keys securely and sets up container registry.

```bash
./04_setup_secrets.sh
./04_setup_secrets.sh --dry-run
```

**Prompts for:**
- OpenAI API Key
- Gemini API Key  
- Pinecone API Key

**Creates:**
- 7 secrets in Secret Manager
- Artifact Registry repository

### `05_deploy_services.sh` - Deployment

Builds and deploys to Cloud Run.

```bash
./05_deploy_services.sh
./05_deploy_services.sh --dry-run
```

**Options when running:**
1. Full deployment (Cloud Build + both services)
2. Deploy API service only
3. Deploy Worker service only
4. Run Cloud Build only

**Deploys:**
- `study-buddy-api` - Public REST API
- `study-buddy-worker` - Background job processor

### `verify.sh` - Health Checks

Performs comprehensive health checks on all resources.

```bash
./verify.sh
```

**Checks:**
- Infrastructure status (SQL, Redis, VPC, GCS)
- Secrets access
- Cloud Run service health
- API endpoint responses
- Recent error logs

### `status.sh` - Status Overview

Shows current deployment status and estimated costs.

```bash
./status.sh
```

**Shows:**
- Cloud Run services and URLs
- Infrastructure resource status
- Secrets list
- Recent builds
- Estimated monthly cost
- Useful console links

### `destroy.sh` - Teardown

**⚠️ DESTRUCTIVE** - Deletes all resources.

```bash
./destroy.sh            # Interactive (requires typing 'DESTROY')
./destroy.sh --dry-run  # Preview what would be deleted
./destroy.sh --force    # Skip confirmations (dangerous!)
```

**Deletes:**
- Cloud Run services
- Cloud SQL instance (and all data!)
- Redis instance
- Cloud Storage bucket (and all files!)
- All secrets
- Artifact Registry
- VPC connector
- Optionally: Service account and project

## 🔧 Configuration Options

Edit `config.env` to customize:

```bash
# Project
PROJECT_ID="study-buddy-prod"
REGION="asia-south1"

# Cloud SQL
SQL_TIER="db-f1-micro"      # db-f1-micro, db-g1-small, db-custom-1-3840
SQL_STORAGE_SIZE="10"       # GB

# Redis
REDIS_SIZE="1"              # GB
REDIS_TIER="basic"          # basic, standard

# Cloud Run
API_MEMORY="2Gi"
API_CPU="2"
API_MIN_INSTANCES="0"       # 0 = scale to zero
API_MAX_INSTANCES="10"

WORKER_MEMORY="2Gi"
WORKER_CPU="2"
WORKER_MIN_INSTANCES="1"    # Keep at least 1 for job processing
WORKER_MAX_INSTANCES="3"
```

## 💰 Estimated Costs

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| Cloud SQL | db-f1-micro | ~$10 |
| Redis | 1GB Basic | ~$35 |
| VPC Connector | e2-micro | ~$12 |
| Cloud Run API | Scale-to-zero | ~$20-50 |
| Cloud Run Worker | 1 min instance | ~$40-60 |
| **Total** | | **~$115-165/month** |

## 🐛 Troubleshooting

### Script won't run
```bash
chmod +x *.sh
```

### gcloud not found
Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install

### Permission denied errors
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Resource already exists
When prompted, choose:
1. Skip (keep existing)
2. Delete and recreate
3. Abort

### Build fails
```bash
# Check recent builds
gcloud builds list --limit=5

# View build logs
gcloud builds log BUILD_ID
```

### Service not starting
```bash
# Check logs
gcloud run services logs read study-buddy-api --region=asia-south1 --limit=50
```

## 📚 Related Documentation

For detailed explanations, see the [GCP Guides](../gcp-guides/):

- [00_INDEX.md](../gcp-guides/00_INDEX.md) - Overview
- [01_GCP_SETUP_IAM.md](../gcp-guides/01_GCP_SETUP_IAM.md) - Project & IAM
- [02_VPC_NETWORKING.md](../gcp-guides/02_VPC_NETWORKING.md) - Networking
- [03_INFRASTRUCTURE.md](../gcp-guides/03_INFRASTRUCTURE.md) - SQL, Redis, GCS
- [04_SECRETS_REGISTRY.md](../gcp-guides/04_SECRETS_REGISTRY.md) - Secrets
- [05_CLOUD_BUILD_DEPLOY.md](../gcp-guides/05_CLOUD_BUILD_DEPLOY.md) - Deployment
- [06_MONITORING_COSTS.md](../gcp-guides/06_MONITORING_COSTS.md) - Monitoring
- [07_TROUBLESHOOTING_SECURITY.md](../gcp-guides/07_TROUBLESHOOTING_SECURITY.md) - Troubleshooting
