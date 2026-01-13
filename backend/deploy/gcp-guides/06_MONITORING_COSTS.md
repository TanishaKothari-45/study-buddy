# 📊 Phase 11-12: Monitoring, Logging & Cost Analysis

## Overview

This guide covers:
- **Cloud Logging** - Application log management
- **Cloud Monitoring** - Metrics and dashboards
- **Alerting** - Automated notifications
- **Cost Analysis** - Detailed cost breakdown and optimization

**Time Required:** ~20 minutes (reference guide)

---

## 📋 Prerequisites

- Completed deployment (see [05_CLOUD_BUILD_DEPLOY.md](./05_CLOUD_BUILD_DEPLOY.md))
- Services running in Cloud Run

```bash
# Verify environment
source ~/study-buddy-env.sh
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
```

---

## Phase 11: Monitoring & Logging

### Step 11.1: View Cloud Run Logs

```bash
# View API service logs (last 50 entries)
gcloud run services logs read study-buddy-api \
  --region=$REGION \
  --limit=50

# View Worker service logs
gcloud run services logs read study-buddy-worker \
  --region=$REGION \
  --limit=50

# Stream logs in real-time
gcloud run services logs tail study-buddy-api --region=$REGION

# Filter by severity
gcloud run services logs read study-buddy-api \
  --region=$REGION \
  --filter="severity>=ERROR" \
  --limit=20

# Filter by time range
gcloud run services logs read study-buddy-api \
  --region=$REGION \
  --filter="timestamp>=\"2026-01-12T00:00:00Z\"" \
  --limit=50
```

### Step 11.2: Advanced Log Queries

```bash
# Search for specific text in logs
gcloud logging read "resource.type=cloud_run_revision AND textPayload:\"error\"" \
  --project=$PROJECT_ID \
  --limit=20

# Find slow requests (>5 seconds)
gcloud logging read "resource.type=cloud_run_revision AND httpRequest.latency>\"5s\"" \
  --project=$PROJECT_ID \
  --limit=20

# Find requests with specific status codes
gcloud logging read "resource.type=cloud_run_revision AND httpRequest.status>=500" \
  --project=$PROJECT_ID \
  --limit=20

# Worker job processing logs
gcloud logging read "resource.type=cloud_run_revision AND labels.\"run.googleapis.com/service_name\"=\"study-buddy-worker\" AND textPayload:\"JOB\"" \
  --project=$PROJECT_ID \
  --limit=20
```

### Step 11.3: Set Up Log-Based Metrics

```bash
# Create a metric for error count
gcloud logging metrics create error-count \
  --description="Count of errors in Study Buddy" \
  --filter="resource.type=cloud_run_revision AND severity>=ERROR AND labels.\"run.googleapis.com/service_name\"=~\"study-buddy.*\""

# Create a metric for job processing time
gcloud logging metrics create job-processing-time \
  --description="Job processing duration" \
  --filter="resource.type=cloud_run_revision AND labels.\"run.googleapis.com/service_name\"=\"study-buddy-worker\" AND textPayload:\"Completed\""

# List custom metrics
gcloud logging metrics list
```

### Step 11.4: View Cloud Run Metrics

```bash
# Open Cloud Run metrics in console
echo "https://console.cloud.google.com/run/detail/${REGION}/study-buddy-api/metrics?project=${PROJECT_ID}"

# Key metrics available:
# - Request count
# - Request latency (p50, p95, p99)
# - Container instance count
# - Container CPU utilization
# - Container memory utilization
# - Billable container instance time
```

### Step 11.5: Create Alerting Policies

```bash
# Create an alert for high error rate
gcloud alpha monitoring policies create \
  --notification-channels="YOUR_NOTIFICATION_CHANNEL_ID" \
  --display-name="High Error Rate - Study Buddy API" \
  --condition-display-name="Error rate > 5%" \
  --condition-filter="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"study-buddy-api\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\"" \
  --condition-threshold-value=0.05 \
  --condition-threshold-comparison=COMPARISON_GT \
  --condition-threshold-duration=300s \
  --condition-threshold-aggregations-alignment-period=60s

# Create an alert for high latency
gcloud alpha monitoring policies create \
  --notification-channels="YOUR_NOTIFICATION_CHANNEL_ID" \
  --display-name="High Latency - Study Buddy API" \
  --condition-display-name="p95 latency > 10s" \
  --condition-filter="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"study-buddy-api\"" \
  --condition-threshold-value=10000 \
  --condition-threshold-comparison=COMPARISON_GT
```

> **Note:** For easier alert setup, use the Cloud Console:
> https://console.cloud.google.com/monitoring/alerting

### Step 11.6: Create a Monitoring Dashboard

```bash
# Create a basic dashboard (JSON configuration)
cat > /tmp/dashboard.json << 'EOF'
{
  "displayName": "Study Buddy Overview",
  "gridLayout": {
    "columns": 2,
    "widgets": [
      {
        "title": "API Request Count",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"study-buddy-api\" AND metric.type=\"run.googleapis.com/request_count\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_RATE"
                }
              }
            }
          }]
        }
      },
      {
        "title": "API Latency (p95)",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"study-buddy-api\" AND metric.type=\"run.googleapis.com/request_latencies\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_PERCENTILE_95"
                }
              }
            }
          }]
        }
      },
      {
        "title": "Container Instance Count",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/container/instance_count\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_MEAN"
                }
              }
            }
          }]
        }
      },
      {
        "title": "Memory Utilization",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/container/memory/utilizations\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_PERCENTILE_95"
                }
              }
            }
          }]
        }
      }
    ]
  }
}
EOF

# Create the dashboard
gcloud monitoring dashboards create --config-from-file=/tmp/dashboard.json

# List dashboards
gcloud monitoring dashboards list
```

### Step 11.7: Set Up Notification Channels

```bash
# Create an email notification channel
gcloud alpha monitoring channels create \
  --display-name="Study Buddy Alerts Email" \
  --type=email \
  --channel-labels="email_address=your-email@example.com"

# List notification channels
gcloud alpha monitoring channels list

# Get channel ID for use in alerts
gcloud alpha monitoring channels list --format="value(name)"
```

---

## Phase 12: Cost Analysis

### Complete Cost Breakdown

| Service | Configuration | Monthly Cost (Est.) | Notes |
|---------|--------------|---------------------|-------|
| **Cloud Run** | | | |
| ├─ API Service | 2 vCPU, 2GB, scale-to-zero | $20-50 | Depends on traffic |
| └─ Worker Service | 2 vCPU, 2GB, min=1 | $30-60 | Always-on cost |
| **Cloud SQL** | | | |
| ├─ Instance | db-f1-micro | $8-10 | Shared CPU |
| ├─ Storage | 10GB SSD | $2-5 | Auto-increase enabled |
| └─ Backups | 7 day retention | $1-2 | |
| **Memorystore** | | | |
| └─ Redis Basic | 1GB | $35 | No HA |
| **VPC Connector** | | | |
| └─ e2-micro | 2-3 instances | $10-15 | Required for Redis |
| **Cloud Storage** | | | |
| ├─ Standard | ~10GB | $0.20 | |
| └─ Operations | Class A/B | $0.50-2 | |
| **Secret Manager** | | | |
| └─ 7 secrets | Access operations | $0.10 | Minimal |
| **Artifact Registry** | | | |
| └─ Images | ~5GB | $0.50-1 | Cleanup policy applied |
| **Cloud Build** | | | |
| └─ Build minutes | ~120 min/month | $0 | Free tier covers this |
| **Cloud Logging** | | | |
| └─ Logs ingestion | ~10GB/month | $0-5 | First 50GB free |
| **Total** | | **$105-180/month** | |

### Cost Breakdown by Category

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Monthly Cost Breakdown                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Compute (Cloud Run)          $50-110  ████████████████░░░░  45-55% │
│  ├─ API Service               $20-50                                │
│  └─ Worker Service            $30-60                                │
│                                                                      │
│  Database (Cloud SQL)         $11-17   ████░░░░░░░░░░░░░░░░  10-15% │
│  ├─ Instance                  $8-10                                 │
│  ├─ Storage                   $2-5                                  │
│  └─ Backups                   $1-2                                  │
│                                                                      │
│  Caching (Redis)              $35      ██████████░░░░░░░░░░  25-30% │
│  └─ Basic 1GB                 $35                                   │
│                                                                      │
│  Networking (VPC)             $10-15   ███░░░░░░░░░░░░░░░░░  8-12%  │
│  └─ VPC Connector             $10-15                                │
│                                                                      │
│  Storage & Other              $1-8     █░░░░░░░░░░░░░░░░░░░  2-5%   │
│  ├─ Cloud Storage             $0.70-3                               │
│  ├─ Secrets & Registry        $0.60-2                               │
│  └─ Logging                   $0-5                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Step 12.1: View Current Billing

```bash
# Open billing dashboard
echo "https://console.cloud.google.com/billing?project=${PROJECT_ID}"

# View cost breakdown by service
echo "https://console.cloud.google.com/billing/reports?project=${PROJECT_ID}"

# Export billing data (for analysis)
gcloud billing export enable --project=$PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### Step 12.2: Set Up Budget Alerts

```bash
# Create a budget with alerts
gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="Study Buddy Monthly Budget" \
  --budget-amount=200USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.75 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0

# List existing budgets
gcloud billing budgets list --billing-account=BILLING_ACCOUNT_ID
```

### Step 12.3: Cost Optimization Strategies

#### 1. Cloud Run Optimization

```bash
# Reduce API service resources (if not heavily loaded)
gcloud run services update study-buddy-api \
  --region=$REGION \
  --memory=1Gi \
  --cpu=1

# Use startup CPU boost instead of high base allocation
gcloud run services update study-buddy-api \
  --region=$REGION \
  --cpu-boost

# Reduce max instances
gcloud run services update study-buddy-api \
  --region=$REGION \
  --max-instances=5
```

#### 2. Worker Optimization

```bash
# Option A: Scale to zero (saves ~$30-60/month)
# Note: This increases job start latency
gcloud run services update study-buddy-worker \
  --region=$REGION \
  --min-instances=0

# Option B: Use smaller instance for off-peak
# Create a Cloud Scheduler job to scale down at night
gcloud scheduler jobs create http scale-down-worker \
  --schedule="0 23 * * *" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services/study-buddy-worker" \
  --http-method=PATCH \
  --message-body='{"template":{"scaling":{"minInstanceCount":0}}}'
```

#### 3. Database Optimization

```bash
# Use smaller instance tier
gcloud sql instances patch $SQL_INSTANCE \
  --tier=db-f1-micro

# Enable auto-storage to avoid over-provisioning
gcloud sql instances patch $SQL_INSTANCE \
  --storage-auto-increase \
  --storage-auto-increase-limit=50GB

# Consider stopping dev instances when not in use
# gcloud sql instances patch $SQL_INSTANCE --activation-policy=NEVER
```

#### 4. Redis Optimization

```bash
# Note: Redis Basic tier is already the cheapest option
# For significant savings, consider:
# 1. Cloud Memorystore for Redis Cluster (for high traffic)
# 2. Self-managed Redis on Compute Engine (more effort)

# Check memory usage
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="table(memorySizeGb,host)"
```

#### 5. Storage Optimization

```bash
# Review lifecycle policies (delete old files faster)
gcloud storage buckets describe gs://$GCS_BUCKET --format="json(lifecycle_config)"

# Move infrequent data to Nearline
gcloud storage buckets update gs://$GCS_BUCKET \
  --default-storage-class=NEARLINE

# Clean up old Artifact Registry images
gcloud artifacts docker images list ${IMAGE_PATH} \
  --include-tags \
  --format="table(package,version,createTime)" \
  --sort-by="createTime"

# Delete old images
gcloud artifacts docker images delete ${IMAGE_PATH}:OLD_TAG --quiet
```

### Step 12.4: Free Tier Utilization

Take advantage of GCP free tiers:

| Service | Free Tier | Study Buddy Usage |
|---------|-----------|-------------------|
| Cloud Run | 2M requests, 360K GB-sec | ✅ Likely under |
| Cloud Build | 120 min/day | ✅ Under free tier |
| Cloud Storage | 5GB Standard | ⚠️ May exceed |
| Cloud Logging | 50GB/month | ✅ Likely under |
| Secret Manager | 10K access ops | ✅ Under free tier |

### Step 12.5: Committed Use Discounts

For stable workloads, consider 1-year commitments:

```bash
# View committed use discount options
echo "https://console.cloud.google.com/compute/commitments?project=${PROJECT_ID}"

# Potential savings:
# - Cloud Run: Up to 17% with committed use
# - Cloud SQL: Up to 52% with committed use
# - Memorystore: Up to 30% with committed use
```

---

## 📈 Key Performance Indicators (KPIs)

### API Service KPIs

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Request Latency (p95) | < 2s | > 5s |
| Error Rate | < 1% | > 5% |
| Availability | > 99.9% | < 99% |
| Instance Count | 0-5 | > 8 |

### Worker Service KPIs

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Job Success Rate | > 95% | < 90% |
| Job Processing Time | < 5 min | > 10 min |
| Queue Depth | < 100 | > 500 |
| Memory Utilization | < 80% | > 90% |

---

## ✅ Monitoring Checklist

```bash
# 1. Verify logging is working
gcloud run services logs read study-buddy-api --region=$REGION --limit=5

# 2. Check for errors in last 24 hours
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR AND timestamp>=\"$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)\"" \
  --project=$PROJECT_ID \
  --limit=10

# 3. Check instance scaling
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(status.traffic)"

# 4. View current costs (last 7 days)
echo "https://console.cloud.google.com/billing/reports?project=${PROJECT_ID}&timeRange=LAST_7_DAYS"

# 5. Verify budget alerts are set
gcloud billing budgets list --billing-account=BILLING_ACCOUNT_ID
```

---

## 📋 Quick Reference

```bash
# View logs
gcloud run services logs read study-buddy-api --region=$REGION --limit=50
gcloud run services logs tail study-buddy-api --region=$REGION

# Check metrics
echo "https://console.cloud.google.com/run/detail/${REGION}/study-buddy-api/metrics"

# View costs
echo "https://console.cloud.google.com/billing/reports?project=${PROJECT_ID}"

# Create budget
gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="Study Buddy Budget" \
  --budget-amount=150USD \
  --threshold-rule=percent=0.8

# Cost optimization - reduce worker
gcloud run services update study-buddy-worker --region=$REGION --min-instances=0
```

---

## ➡️ Next Steps

Proceed to [07_TROUBLESHOOTING_SECURITY.md](./07_TROUBLESHOOTING_SECURITY.md) for troubleshooting guide and security checklist.
