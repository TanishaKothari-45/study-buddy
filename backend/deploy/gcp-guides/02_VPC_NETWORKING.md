# 🌐 Phase 3: VPC & Networking Configuration

## Overview

This guide covers setting up the Virtual Private Cloud (VPC) networking required for Cloud Run to communicate with private resources like Memorystore Redis and Cloud SQL.

**Time Required:** ~15 minutes

---

## 📋 Prerequisites

- Completed [01_GCP_SETUP_IAM.md](./01_GCP_SETUP_IAM.md)
- Environment variables set (`PROJECT_ID`, `REGION`, `SA_EMAIL`)

```bash
# Verify environment
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
```

---

## Why VPC Connector is Needed

Cloud Run services are **serverless** and run outside your VPC by default. To access private resources:

| Resource | Location | Requires VPC? |
|----------|----------|---------------|
| Memorystore Redis | Private VPC only | ✅ Yes |
| Cloud SQL (Private IP) | Private VPC | ✅ Yes |
| Cloud SQL (Public IP) | Public | ❌ No (but less secure) |
| Cloud Storage | Public API | ❌ No |
| Secret Manager | Public API | ❌ No |

**Study Buddy** uses:
- **Memorystore Redis** → Requires VPC Connector
- **Cloud SQL** → Using Cloud SQL Connector (works without VPC, but VPC is better)

---

## Step 3.1: Understand VPC Network Options

### Option A: Use Default VPC (Recommended for simplicity)

GCP automatically creates a `default` VPC network with subnets in each region.

```bash
# List existing VPC networks
gcloud compute networks list

# List subnets in default network
gcloud compute networks subnets list --network=default --filter="region:($REGION)"
```

### Option B: Create Custom VPC (Enterprise)

For production environments requiring network isolation:

```bash
# Create custom VPC (optional, skip if using default)
gcloud compute networks create study-buddy-vpc \
  --subnet-mode=custom \
  --description="Study Buddy private VPC network"

# Create subnet in your region
gcloud compute networks subnets create study-buddy-subnet \
  --network=study-buddy-vpc \
  --region=$REGION \
  --range=10.0.0.0/24
```

---

## Step 3.2: Create Serverless VPC Access Connector

The VPC Connector bridges Cloud Run to your VPC network.

```bash
# Define connector name
export VPC_CONNECTOR="study-buddy-connector"
export VPC_NETWORK="default"  # Or "study-buddy-vpc" if using custom

# Create the VPC Access Connector
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --region=$REGION \
  --network=$VPC_NETWORK \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro

# Note on IP range:
# - Must be /28 (16 IPs)
# - Must not overlap with existing subnets
# - 10.8.0.0/28 is commonly available in default VPC
```

### VPC Connector Configuration Options

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--range` | `10.8.0.0/28` | IP range for connector (16 IPs) |
| `--min-instances` | `2` | Minimum connector instances (for availability) |
| `--max-instances` | `3` | Maximum connector instances (auto-scale) |
| `--machine-type` | `e2-micro` | Smallest/cheapest instance type |

### Verify Connector Creation

```bash
# List connectors
gcloud compute networks vpc-access connectors list --region=$REGION

# Describe the connector (detailed info)
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION

# Expected output:
# name: projects/PROJECT_ID/locations/asia-south1/connectors/study-buddy-connector
# network: default
# ipCidrRange: 10.8.0.0/28
# state: READY
# minInstances: 2
# maxInstances: 3
# machineType: e2-micro
```

---

## Step 3.3: Configure Firewall Rules (If Using Custom VPC)

If using the default VPC, firewall rules are already configured. For custom VPCs:

```bash
# Allow internal communication within VPC
gcloud compute firewall-rules create study-buddy-allow-internal \
  --network=study-buddy-vpc \
  --allow=tcp,udp,icmp \
  --source-ranges=10.0.0.0/8 \
  --description="Allow internal traffic within Study Buddy VPC"

# Allow Cloud Run to access Redis (port 6379)
gcloud compute firewall-rules create study-buddy-allow-redis \
  --network=study-buddy-vpc \
  --allow=tcp:6379 \
  --source-ranges=10.8.0.0/28 \
  --target-tags=redis \
  --description="Allow VPC connector to access Redis"

# Allow Cloud Run to access PostgreSQL (port 5432)
gcloud compute firewall-rules create study-buddy-allow-postgres \
  --network=study-buddy-vpc \
  --allow=tcp:5432 \
  --source-ranges=10.8.0.0/28 \
  --description="Allow VPC connector to access Cloud SQL"
```

---

## Step 3.4: Verify VPC Connector Connectivity

### Test with a simple Cloud Run service

```bash
# Deploy a test service with VPC connector
gcloud run deploy vpc-test \
  --image=gcr.io/cloudrun/hello \
  --region=$REGION \
  --vpc-connector=$VPC_CONNECTOR \
  --allow-unauthenticated

# Check the service status
gcloud run services describe vpc-test --region=$REGION --format="yaml(spec.template.metadata.annotations)"

# You should see:
# run.googleapis.com/vpc-access-connector: projects/PROJECT_ID/locations/asia-south1/connectors/study-buddy-connector

# Clean up test service
gcloud run services delete vpc-test --region=$REGION --quiet
```

---

## Step 3.5: Get VPC Connector Full Path

Store the full connector path for use in deployment:

```bash
# Get full connector path (needed for Cloud Build)
export VPC_CONNECTOR_PATH="projects/${PROJECT_ID}/locations/${REGION}/connectors/${VPC_CONNECTOR}"

echo "VPC Connector Path: $VPC_CONNECTOR_PATH"

# Save to env file
echo "export VPC_CONNECTOR_PATH=\"$VPC_CONNECTOR_PATH\"" >> ~/study-buddy-env.sh
```

---

## 🔧 VPC Connector Cost Optimization

### Understanding Costs

VPC Connectors run on small VM instances and incur costs even when idle:

| Component | Spec | Monthly Cost (Est.) |
|-----------|------|---------------------|
| e2-micro instances | 2-3 instances | $10-15 |
| Network egress | Variable | $0-5 |

### Cost Optimization Tips

1. **Use e2-micro** (smallest instance type)
2. **Min instances = 2** (required for high availability)
3. **Max instances = 3** (limit scale-up)
4. **Share connector** across multiple Cloud Run services

```bash
# If you need to resize later:
gcloud compute networks vpc-access connectors update $VPC_CONNECTOR \
  --region=$REGION \
  --min-instances=2 \
  --max-instances=3
```

---

## 📊 Network Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Google Cloud VPC                              │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Default Network                            │  │
│  │                                                                │  │
│  │   ┌─────────────────┐      ┌─────────────────────────────┐   │  │
│  │   │  Serverless VPC │      │        Private Subnet        │   │  │
│  │   │    Connector    │◀────▶│                              │   │  │
│  │   │  10.8.0.0/28    │      │  ┌─────────┐  ┌──────────┐  │   │  │
│  │   │                 │      │  │  Redis  │  │ Cloud SQL│  │   │  │
│  │   │  (e2-micro x2)  │      │  │  :6379  │  │  :5432   │  │   │  │
│  │   └────────▲────────┘      │  └─────────┘  └──────────┘  │   │  │
│  │            │               └─────────────────────────────────┘   │  │
│  └────────────┼───────────────────────────────────────────────────┘  │
│               │                                                      │
└───────────────┼──────────────────────────────────────────────────────┘
                │
                │ VPC Connector
                │
┌───────────────▼──────────────────────────────────────────────────────┐
│                          Cloud Run                                    │
│  ┌─────────────────────┐     ┌─────────────────────┐                │
│  │  study-buddy-api    │     │  study-buddy-worker │                │
│  │  (Public endpoint)  │     │  (Internal only)    │                │
│  └─────────────────────┘     └─────────────────────┘                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## ✅ Verification Checklist

```bash
# 1. Verify VPC connector exists and is READY
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION \
  --format="value(state)"
# Expected: READY

# 2. Verify connector network
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION \
  --format="value(network)"
# Expected: default (or your custom VPC name)

# 3. Verify IP range doesn't conflict
gcloud compute networks subnets list --network=default \
  --filter="region:($REGION)" \
  --format="table(name,ipCidrRange)"
# Verify 10.8.0.0/28 doesn't overlap

# 4. Get full connector path
echo "projects/${PROJECT_ID}/locations/${REGION}/connectors/${VPC_CONNECTOR}"
```

---

## 🚨 Common Issues & Solutions

### Issue: "IP range overlaps with existing subnet"

```bash
# Check existing IP ranges
gcloud compute networks subnets list --network=default \
  --format="table(name,ipCidrRange,region)"

# Try a different range (examples):
# 10.8.0.0/28  -> 10.8.0.16/28 -> 10.8.0.32/28 -> 10.9.0.0/28
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --region=$REGION \
  --network=$VPC_NETWORK \
  --range=10.9.0.0/28  # Different range
```

### Issue: "VPC connector in ERROR state"

```bash
# Delete and recreate
gcloud compute networks vpc-access connectors delete $VPC_CONNECTOR \
  --region=$REGION --quiet

# Wait a minute, then recreate
sleep 60
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --region=$REGION \
  --network=$VPC_NETWORK \
  --range=10.8.0.0/28
```

### Issue: "Cannot connect to Redis/Cloud SQL"

```bash
# 1. Verify connector is attached to Cloud Run service
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(spec.template.metadata.annotations)"

# 2. Verify Redis/Cloud SQL is in the same network
gcloud redis instances describe study-buddy-redis --region=$REGION \
  --format="value(authorizedNetwork)"

# 3. Check firewall rules (for custom VPC)
gcloud compute firewall-rules list --filter="network:$VPC_NETWORK"
```

---

## 📋 Quick Reference

```bash
# Quick VPC setup commands
export PROJECT_ID="your-project-id"
export REGION="asia-south1"
export VPC_CONNECTOR="study-buddy-connector"
export VPC_NETWORK="default"

# Create connector
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --region=$REGION \
  --network=$VPC_NETWORK \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro

# Get full path
export VPC_CONNECTOR_PATH="projects/${PROJECT_ID}/locations/${REGION}/connectors/${VPC_CONNECTOR}"
echo $VPC_CONNECTOR_PATH
```

---

## ➡️ Next Steps

Proceed to [03_INFRASTRUCTURE.md](./03_INFRASTRUCTURE.md) to set up Cloud SQL, Memorystore Redis, and Cloud Storage.
