#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Phase 1-2: Project Setup & IAM
# ═══════════════════════════════════════════════════════════════════════════════
# This script handles:
#   - Project creation/selection
#   - API enablement
#   - Service account creation
#   - IAM role assignment
#
# Usage:
#   ./01_init_project.sh [--dry-run]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

# Parse arguments
check_dry_run "$@"

log_header "Phase 1-2: GCP Project Setup & IAM Configuration"

# Load configuration
load_config
check_prerequisites

# Show configuration
print_config_summary

if ! ask_yes_no "Proceed with this configuration?"; then
    log_info "Aborted by user"
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PROJECT SETUP
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 1: Project Setup"

# Check if project exists
if check_project_exists; then
    log_success "Project '$PROJECT_ID' exists"
else
    log_info "Creating project '$PROJECT_ID'..."
    run_cmd "gcloud projects create $PROJECT_ID --name='Study Buddy Production'"
fi

# Set project as default
run_cmd "gcloud config set project $PROJECT_ID"

# Check billing
if check_billing_enabled; then
    log_success "Billing is enabled for project '$PROJECT_ID'"
else
    if [[ -z "$BILLING_ACCOUNT_ID" ]]; then
        log_error "Billing is not enabled and BILLING_ACCOUNT_ID is not set in config.env"
        log_info "Please run: gcloud billing accounts list"
        log_info "Then set BILLING_ACCOUNT_ID in config.env"
        exit 1
    fi
    log_info "Enabling billing for project..."
    run_cmd "gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT_ID"
fi

# Set region defaults
run_cmd "gcloud config set run/region $REGION"
run_cmd "gcloud config set compute/region $REGION"

# ═══════════════════════════════════════════════════════════════════════════════
# ENABLE REQUIRED APIS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Enabling Required APIs"

REQUIRED_APIS=(
    "run.googleapis.com"
    "cloudbuild.googleapis.com"
    "artifactregistry.googleapis.com"
    "secretmanager.googleapis.com"
    "sqladmin.googleapis.com"
    "redis.googleapis.com"
    "storage.googleapis.com"
    "vpcaccess.googleapis.com"
    "compute.googleapis.com"
    "logging.googleapis.com"
    "monitoring.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    log_info "Enabling $api..."
    run_cmd "gcloud services enable $api --quiet"
done

log_success "All required APIs enabled"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: SERVICE ACCOUNT & IAM
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 2: Service Account & IAM Configuration"

# Create service account
if ask_resource_action "service-account" "$SA_NAME"; then
    if resource_exists "service-account" "$SA_NAME"; then
        log_info "Deleting existing service account..."
        run_cmd "gcloud iam service-accounts delete $SA_EMAIL --quiet"
    fi
    
    log_info "Creating service account '$SA_NAME'..."
    run_cmd "gcloud iam service-accounts create $SA_NAME \
        --display-name='Study Buddy Backend Service Account' \
        --description='Service account for Study Buddy Cloud Run services'"
    
    log_success "Service account created: $SA_EMAIL"
else
    log_info "Skipping service account creation"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# ASSIGN IAM ROLES TO SERVICE ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Assigning IAM Roles to Service Account"

SA_ROLES=(
    "roles/secretmanager.secretAccessor"
    "roles/cloudsql.client"
    "roles/storage.objectAdmin"
    "roles/redis.editor"
    "roles/logging.logWriter"
    "roles/cloudtrace.agent"
)

for role in "${SA_ROLES[@]}"; do
    log_info "Assigning $role..."
    run_cmd "gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member='serviceAccount:$SA_EMAIL' \
        --role='$role' \
        --condition=None \
        --quiet"
done

log_success "All IAM roles assigned to service account"

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURE CLOUD BUILD SERVICE ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Configuring Cloud Build Service Account"

CLOUDBUILD_ROLES=(
    "roles/run.admin"
    "roles/artifactregistry.writer"
    "roles/secretmanager.secretAccessor"
)

for role in "${CLOUDBUILD_ROLES[@]}"; do
    log_info "Assigning $role to Cloud Build..."
    run_cmd "gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member='serviceAccount:$CLOUDBUILD_SA' \
        --role='$role' \
        --quiet"
done

# Grant Cloud Build permission to act as backend service account
log_info "Granting Cloud Build permission to impersonate backend service account..."
run_cmd "gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
    --member='serviceAccount:$CLOUDBUILD_SA' \
    --role='roles/iam.serviceAccountUser' \
    --quiet"

log_success "Cloud Build service account configured"

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification"

log_info "Verifying project configuration..."
echo ""
echo "Project:            $(gcloud config get-value project)"
echo "Region:             $(gcloud config get-value run/region)"
echo "Service Account:    $SA_EMAIL"
echo ""

log_info "Verifying enabled APIs..."
gcloud services list --enabled --filter="name:run OR name:cloudbuild OR name:artifactregistry OR name:secretmanager OR name:sqladmin OR name:redis" --format="table(name)"

log_info "Verifying service account roles..."
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:$SA_EMAIL" \
    --format="table(bindings.role)"

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Phase 1-2 Complete!"

echo "Next steps:"
echo "  1. Run ./02_setup_network.sh to create VPC connector"
echo ""
echo "Or run all phases with:"
echo "  ./01_init_project.sh && ./02_setup_network.sh && ./03_create_infra.sh && ./04_setup_secrets.sh && ./05_deploy_services.sh"
