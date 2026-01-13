#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Status Script
# ═══════════════════════════════════════════════════════════════════════════════
# This script shows the current deployment status of all resources.
#
# Usage:
#   ./status.sh
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

log_header "Study Buddy Deployment Status"

load_config

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT INFO
# ═══════════════════════════════════════════════════════════════════════════════

echo "┌─────────────────────────────────────────────────────────────────────────┐"
echo "│                          Project Configuration                           │"
echo "├─────────────────────────────────────────────────────────────────────────┤"
echo "│ Project ID:        $PROJECT_ID"
echo "│ Region:            $REGION"
echo "│ Service Account:   $SA_NAME"
echo "└─────────────────────────────────────────────────────────────────────────┘"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# CLOUD RUN SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Cloud Run Services"

if resource_exists "cloud-run" "$API_SERVICE_NAME" || resource_exists "cloud-run" "$WORKER_SERVICE_NAME"; then
    gcloud run services list --region="$REGION" \
        --format="table(SERVICE,REGION,URL,LAST_DEPLOYED_BY,LAST_DEPLOYED_AT:sort=1:reverse)"
    
    echo ""
    
    # API Service details
    if resource_exists "cloud-run" "$API_SERVICE_NAME"; then
        echo "API Service ($API_SERVICE_NAME):"
        gcloud run services describe "$API_SERVICE_NAME" --region="$REGION" \
            --format="table(spec.template.spec.containers[0].resources.limits.cpu,spec.template.spec.containers[0].resources.limits.memory,status.conditions[0].status)"
        API_URL=$(gcloud run services describe "$API_SERVICE_NAME" --region="$REGION" --format="value(status.url)")
        echo "  URL: $API_URL"
    fi
    
    # Worker Service details  
    if resource_exists "cloud-run" "$WORKER_SERVICE_NAME"; then
        echo ""
        echo "Worker Service ($WORKER_SERVICE_NAME):"
        gcloud run services describe "$WORKER_SERVICE_NAME" --region="$REGION" \
            --format="table(spec.template.spec.containers[0].resources.limits.cpu,spec.template.spec.containers[0].resources.limits.memory,status.conditions[0].status)"
    fi
else
    echo "No Cloud Run services deployed"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Infrastructure Resources"

echo "┌─────────────────────────────────────────────────────────────────────────┐"
echo "│ Resource Type          │ Name                    │ Status              │"
echo "├─────────────────────────────────────────────────────────────────────────┤"

# VPC Connector
printf "│ %-22s │ %-23s │ " "VPC Connector" "$VPC_CONNECTOR"
if resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
    state=$(gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR" --region="$REGION" --format="value(state)" 2>/dev/null)
    printf "%-18s │\n" "$state"
else
    printf "%-18s │\n" "NOT CREATED"
fi

# Cloud SQL
printf "│ %-22s │ %-23s │ " "Cloud SQL" "$SQL_INSTANCE"
if resource_exists "sql-instance" "$SQL_INSTANCE"; then
    state=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(state)" 2>/dev/null)
    printf "%-18s │\n" "$state"
else
    printf "%-18s │\n" "NOT CREATED"
fi

# Redis
printf "│ %-22s │ %-23s │ " "Redis" "$REDIS_INSTANCE"
if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
    state=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(state)" 2>/dev/null)
    printf "%-18s │\n" "$state"
else
    printf "%-18s │\n" "NOT CREATED"
fi

# GCS Bucket
printf "│ %-22s │ %-23s │ " "Cloud Storage" "$GCS_BUCKET"
if resource_exists "gcs-bucket" "$GCS_BUCKET"; then
    printf "%-18s │\n" "EXISTS"
else
    printf "%-18s │\n" "NOT CREATED"
fi

# Artifact Registry
printf "│ %-22s │ %-23s │ " "Artifact Registry" "$ARTIFACT_REPO"
if resource_exists "artifact-repo" "$ARTIFACT_REPO"; then
    printf "%-18s │\n" "EXISTS"
else
    printf "%-18s │\n" "NOT CREATED"
fi

echo "└─────────────────────────────────────────────────────────────────────────┘"

# ═══════════════════════════════════════════════════════════════════════════════
# SECRETS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Secrets"

echo "Configured secrets in Secret Manager:"
gcloud secrets list --format="table(name,createTime,replication.automatic)" 2>/dev/null || echo "No secrets found"

# ═══════════════════════════════════════════════════════════════════════════════
# RECENT BUILDS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Recent Cloud Builds"

gcloud builds list --limit=5 --format="table(id,status,createTime,duration)" 2>/dev/null || echo "No builds found"

# ═══════════════════════════════════════════════════════════════════════════════
# COST ESTIMATE
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Estimated Monthly Cost"

echo "┌─────────────────────────────────────────────────────────────────────────┐"
echo "│                       Estimated Monthly Costs                            │"
echo "├─────────────────────────────────────────────────────────────────────────┤"

total=0

# Cloud SQL
if resource_exists "sql-instance" "$SQL_INSTANCE"; then
    tier=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(settings.tier)" 2>/dev/null)
    case "$tier" in
        db-f1-micro) sql_cost=10 ;;
        db-g1-small) sql_cost=30 ;;
        db-custom-1-*) sql_cost=50 ;;
        *) sql_cost=50 ;;
    esac
    echo "│ Cloud SQL ($tier):                                      ~\$$sql_cost/month │"
    total=$((total + sql_cost))
fi

# Redis
if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
    size=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(memorySizeGb)" 2>/dev/null)
    redis_cost=$((size * 35))
    echo "│ Redis (${size}GB):                                              ~\$$redis_cost/month │"
    total=$((total + redis_cost))
fi

# VPC Connector
if resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
    vpc_cost=12
    echo "│ VPC Connector:                                              ~\$$vpc_cost/month │"
    total=$((total + vpc_cost))
fi

# Cloud Run (estimate)
if resource_exists "cloud-run" "$API_SERVICE_NAME"; then
    echo "│ Cloud Run API (scale-to-zero):                          ~\$20-50/month │"
    total=$((total + 35))
fi

if resource_exists "cloud-run" "$WORKER_SERVICE_NAME"; then
    min=$(gcloud run services describe "$WORKER_SERVICE_NAME" --region="$REGION" --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])" 2>/dev/null)
    if [[ "$min" -gt 0 ]]; then
        echo "│ Cloud Run Worker (always-on):                           ~\$40-60/month │"
        total=$((total + 50))
    else
        echo "│ Cloud Run Worker (scale-to-zero):                       ~\$10-30/month │"
        total=$((total + 20))
    fi
fi

echo "├─────────────────────────────────────────────────────────────────────────┤"
echo "│ ESTIMATED TOTAL:                                        ~\$${total}/month │"
echo "└─────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "Note: Actual costs may vary based on usage. Check Cloud Billing for accurate costs."
echo "Billing: https://console.cloud.google.com/billing/reports?project=$PROJECT_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# USEFUL LINKS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Useful Links"

echo "Cloud Console:    https://console.cloud.google.com/home/dashboard?project=$PROJECT_ID"
echo "Cloud Run:        https://console.cloud.google.com/run?project=$PROJECT_ID"
echo "Cloud SQL:        https://console.cloud.google.com/sql/instances?project=$PROJECT_ID"
echo "Cloud Build:      https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
echo "Secret Manager:   https://console.cloud.google.com/security/secret-manager?project=$PROJECT_ID"
echo "Billing:          https://console.cloud.google.com/billing/reports?project=$PROJECT_ID"
