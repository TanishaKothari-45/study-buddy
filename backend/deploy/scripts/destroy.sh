#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Destroy Script
# ═══════════════════════════════════════════════════════════════════════════════
# This script tears down all deployed resources.
# ⚠️  WARNING: This is destructive and cannot be undone!
#
# Usage:
#   ./destroy.sh [--dry-run] [--force]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

# Parse arguments
FORCE=false
check_dry_run "$@"
if [[ "$1" == "--force" ]] || [[ "$2" == "--force" ]]; then
    FORCE=true
fi

log_header "⚠️  Study Buddy Deployment DESTROY"

load_config

# ═══════════════════════════════════════════════════════════════════════════════
# WARNING
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                              ⚠️  WARNING ⚠️                                 ║"
echo "╠═══════════════════════════════════════════════════════════════════════════╣"
echo "║  This script will DELETE the following resources:                          ║"
echo "║                                                                            ║"
echo "║  • Cloud Run Services (API, Worker)                                        ║"
echo "║  • Cloud SQL Instance ($SQL_INSTANCE)                                   "
echo "║  • Redis Instance ($REDIS_INSTANCE)                                     "
echo "║  • Cloud Storage Bucket (gs://$GCS_BUCKET)                              "
echo "║  • VPC Connector ($VPC_CONNECTOR)                                       "
echo "║  • Artifact Registry ($ARTIFACT_REPO)                                   "
echo "║  • All Secrets in Secret Manager                                           ║"
echo "║                                                                            ║"
echo "║  ❌ THIS CANNOT BE UNDONE!                                                 ║"
echo "║  📊 All data in the database and storage will be LOST!                     ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

if [[ "$FORCE" != true ]]; then
    echo "Type 'DESTROY' to confirm destruction of all resources:"
    read -p "> " confirmation
    
    if [[ "$confirmation" != "DESTROY" ]]; then
        log_info "Aborted. No resources were deleted."
        exit 0
    fi
    
    echo ""
    if ! ask_yes_no "Are you ABSOLUTELY SURE? This will delete all data!" "n"; then
        log_info "Aborted. No resources were deleted."
        exit 0
    fi
fi

log_warning "Starting resource destruction..."

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE CLOUD RUN SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Cloud Run Services"

if resource_exists "cloud-run" "$API_SERVICE_NAME"; then
    log_info "Deleting API service '$API_SERVICE_NAME'..."
    run_cmd "gcloud run services delete $API_SERVICE_NAME --region=$REGION --quiet"
    log_success "API service deleted"
else
    log_info "API service not found (already deleted or never created)"
fi

if resource_exists "cloud-run" "$WORKER_SERVICE_NAME"; then
    log_info "Deleting Worker service '$WORKER_SERVICE_NAME'..."
    run_cmd "gcloud run services delete $WORKER_SERVICE_NAME --region=$REGION --quiet"
    log_success "Worker service deleted"
else
    log_info "Worker service not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE CLOUD SQL
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Cloud SQL Instance"

if resource_exists "sql-instance" "$SQL_INSTANCE"; then
    log_warning "Deleting Cloud SQL instance '$SQL_INSTANCE'..."
    log_warning "This will delete all database data!"
    run_cmd "gcloud sql instances delete $SQL_INSTANCE --quiet"
    log_success "Cloud SQL instance deleted"
else
    log_info "Cloud SQL instance not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE REDIS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Redis Instance"

if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
    log_info "Deleting Redis instance '$REDIS_INSTANCE'..."
    run_cmd "gcloud redis instances delete $REDIS_INSTANCE --region=$REGION --quiet"
    log_success "Redis instance deleted"
else
    log_info "Redis instance not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE CLOUD STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Cloud Storage Bucket"

if resource_exists "gcs-bucket" "$GCS_BUCKET"; then
    log_warning "Deleting GCS bucket 'gs://$GCS_BUCKET' and all contents..."
    run_cmd "gcloud storage rm -r gs://$GCS_BUCKET"
    log_success "Cloud Storage bucket deleted"
else
    log_info "Cloud Storage bucket not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE SECRETS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Secrets"

SECRETS_TO_DELETE=("OPENAI_API_KEY" "GEMINI_API_KEY" "PINECONE_API_KEY" "JWT_SECRET_KEY" "ENCRYPTION_KEY" "DATABASE_URL" "REDIS_URL")

for secret in "${SECRETS_TO_DELETE[@]}"; do
    if resource_exists "secret" "$secret"; then
        log_info "Deleting secret '$secret'..."
        run_cmd "gcloud secrets delete $secret --quiet"
    else
        log_info "Secret '$secret' not found"
    fi
done

log_success "All secrets deleted"

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE ARTIFACT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting Artifact Registry"

if resource_exists "artifact-repo" "$ARTIFACT_REPO"; then
    log_info "Deleting Artifact Registry '$ARTIFACT_REPO'..."
    run_cmd "gcloud artifacts repositories delete $ARTIFACT_REPO --location=$REGION --quiet"
    log_success "Artifact Registry deleted"
else
    log_info "Artifact Registry not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DELETE VPC CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deleting VPC Connector"

if resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
    log_info "Deleting VPC connector '$VPC_CONNECTOR'..."
    run_cmd "gcloud compute networks vpc-access connectors delete $VPC_CONNECTOR --region=$REGION --quiet"
    log_success "VPC connector deleted"
else
    log_info "VPC connector not found (already deleted or never created)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# OPTIONAL: DELETE SERVICE ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Service Account Cleanup"

if resource_exists "service-account" "$SA_NAME"; then
    echo ""
    if ask_yes_no "Delete service account '$SA_EMAIL'?" "n"; then
        log_info "Deleting service account..."
        run_cmd "gcloud iam service-accounts delete $SA_EMAIL --quiet"
        log_success "Service account deleted"
    else
        log_info "Service account preserved"
    fi
else
    log_info "Service account not found"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# OPTIONAL: DELETE PROJECT
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Project Cleanup"

echo ""
echo "The GCP project '$PROJECT_ID' still exists."
echo "Deleting the project will remove ALL remaining resources and data."
echo ""

if ask_yes_no "Delete the entire GCP project '$PROJECT_ID'?" "n"; then
    log_warning "Deleting GCP project (30-day recovery period)..."
    run_cmd "gcloud projects delete $PROJECT_ID --quiet"
    log_success "Project scheduled for deletion"
    echo ""
    log_info "Note: Project can be recovered within 30 days from:"
    log_info "https://console.cloud.google.com/iam-admin/settings/deleted"
else
    log_info "Project preserved"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP COMPLETE
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Destruction Complete"

if [[ "$DRY_RUN" == true ]]; then
    echo "This was a DRY RUN - no resources were actually deleted."
    echo "Remove --dry-run flag to perform actual deletion."
else
    echo "All Study Buddy GCP resources have been deleted."
    echo ""
    echo "If you want to redeploy, run:"
    echo "  ./01_init_project.sh"
    echo "  ./02_setup_network.sh"
    echo "  ./03_create_infra.sh"
    echo "  ./04_setup_secrets.sh"
    echo "  ./05_deploy_services.sh"
fi
