#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Phase 7-8: Secrets & Artifact Registry
# ═══════════════════════════════════════════════════════════════════════════════
# This script handles:
#   - Secret Manager configuration (API keys, DB credentials)
#   - Artifact Registry setup
#   - Docker authentication
#
# Usage:
#   ./04_setup_secrets.sh [--dry-run]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

check_dry_run "$@"

log_header "Phase 7-8: Secret Manager & Artifact Registry"

load_config
check_prerequisites

# ═══════════════════════════════════════════════════════════════════════════════
# COLLECT API KEYS INTERACTIVELY
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Collecting API Keys"

echo "You will be prompted for the following API keys:"
echo "  1. OpenAI API Key (for embeddings)"
echo "  2. Google Gemini API Key (for AI features)"
echo "  3. Pinecone API Key (for vector database)"
echo ""
echo "These will be stored securely in GCP Secret Manager."
echo ""

# Prompt for API keys
OPENAI_KEY=$(prompt_secret "OPENAI_API_KEY" "OpenAI API Key (starts with sk-)")
GEMINI_KEY=$(prompt_secret "GEMINI_API_KEY" "Google Gemini API Key")
PINECONE_KEY=$(prompt_secret "PINECONE_API_KEY" "Pinecone API Key")

# Generate JWT and Encryption keys
log_info "Generating JWT and Encryption keys..."
JWT_SECRET=$(openssl rand -base64 32)
ENCRYPTION_SECRET=$(openssl rand -base64 32)

# Get or prompt for database credentials
if [[ -f /tmp/study-buddy-sql-password.tmp ]]; then
    SQL_PASSWORD=$(cat /tmp/study-buddy-sql-password.tmp)
    SQL_CONNECTION=$(cat /tmp/study-buddy-sql-connection.tmp)
    log_success "Loaded SQL credentials from previous step"
else
    log_warning "SQL credentials not found from previous step"
    SQL_PASSWORD=$(prompt_secret "SQL_PASSWORD" "Database password (from Cloud SQL setup)")
    
    if resource_exists "sql-instance" "$SQL_INSTANCE"; then
        SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
    else
        read -p "Enter SQL Connection Name (format: project:region:instance): " SQL_CONNECTION
    fi
fi

# Get Redis connection info
if [[ -f /tmp/study-buddy-redis-host.tmp ]]; then
    REDIS_HOST=$(cat /tmp/study-buddy-redis-host.tmp)
    REDIS_PORT=$(cat /tmp/study-buddy-redis-port.tmp)
    log_success "Loaded Redis credentials from previous step"
else
    if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
        REDIS_HOST=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(host)")
        REDIS_PORT=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(port)")
    else
        log_warning "Redis instance not found"
        read -p "Enter Redis Host: " REDIS_HOST
        read -p "Enter Redis Port [6379]: " REDIS_PORT
        REDIS_PORT=${REDIS_PORT:-6379}
    fi
fi

# Build connection URLs
DATABASE_URL="postgresql+pg8000://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DATABASE}?unix_sock=/cloudsql/${SQL_CONNECTION}/.s.PGSQL.5432"
REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 7: CREATE SECRETS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 7: Creating Secrets in Secret Manager"

declare -A SECRETS=(
    ["OPENAI_API_KEY"]="$OPENAI_KEY"
    ["GEMINI_API_KEY"]="$GEMINI_KEY"
    ["PINECONE_API_KEY"]="$PINECONE_KEY"
    ["JWT_SECRET_KEY"]="$JWT_SECRET"
    ["ENCRYPTION_KEY"]="$ENCRYPTION_SECRET"
    ["DATABASE_URL"]="$DATABASE_URL"
    ["REDIS_URL"]="$REDIS_URL"
)

for secret_name in "${!SECRETS[@]}"; do
    secret_value="${SECRETS[$secret_name]}"
    
    if resource_exists "secret" "$secret_name"; then
        log_warning "Secret '$secret_name' already exists"
        echo ""
        echo "What would you like to do?"
        echo "  1) Skip (keep existing)"
        echo "  2) Add new version (recommended)"
        echo "  3) Delete and recreate"
        echo ""
        read -p "Choose option [1]: " choice
        choice=${choice:-1}
        
        case "$choice" in
            2)
                log_info "Adding new version to '$secret_name'..."
                run_cmd "echo -n '$secret_value' | gcloud secrets versions add $secret_name --data-file=-"
                ;;
            3)
                log_info "Deleting and recreating '$secret_name'..."
                run_cmd "gcloud secrets delete $secret_name --quiet"
                run_cmd "echo -n '$secret_value' | gcloud secrets create $secret_name --data-file=- --replication-policy='user-managed' --locations='$REGION'"
                ;;
            *)
                log_info "Skipping '$secret_name'"
                ;;
        esac
    else
        log_info "Creating secret '$secret_name'..."
        run_cmd "echo -n '$secret_value' | gcloud secrets create $secret_name --data-file=- --replication-policy='user-managed' --locations='$REGION'"
    fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# GRANT SERVICE ACCOUNT ACCESS TO SECRETS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Granting Service Account Access to Secrets"

for secret_name in "${!SECRETS[@]}"; do
    log_info "Granting access to $secret_name..."
    run_cmd "gcloud secrets add-iam-policy-binding $secret_name \
        --member='serviceAccount:$SA_EMAIL' \
        --role='roles/secretmanager.secretAccessor' \
        --quiet"
done

log_success "Service account granted access to all secrets"

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8: ARTIFACT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 8: Artifact Registry Setup"

if ask_resource_action "artifact-repo" "$ARTIFACT_REPO"; then
    if resource_exists "artifact-repo" "$ARTIFACT_REPO"; then
        log_warning "Deleting Artifact Registry will remove all stored images!"
        if ask_yes_no "Are you sure you want to delete '$ARTIFACT_REPO'?" "n"; then
            log_info "Deleting existing repository..."
            run_cmd "gcloud artifacts repositories delete $ARTIFACT_REPO --location=$REGION --quiet"
        else
            log_info "Skipping Artifact Registry creation"
            ARTIFACT_SKIP=true
        fi
    fi
    
    if [[ "$ARTIFACT_SKIP" != true ]]; then
        log_info "Creating Artifact Registry repository '$ARTIFACT_REPO'..."
        
        run_cmd "gcloud artifacts repositories create $ARTIFACT_REPO \
            --repository-format=docker \
            --location=$REGION \
            --description='Study Buddy Docker images'"
        
        log_success "Artifact Registry created"
    fi
else
    log_info "Skipping Artifact Registry creation"
fi

# Configure Docker authentication
log_info "Configuring Docker authentication..."
run_cmd "gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet"

# Grant Cloud Build write access
log_info "Granting Cloud Build write access to Artifact Registry..."
run_cmd "gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
    --location=$REGION \
    --member='serviceAccount:$CLOUDBUILD_SA' \
    --role='roles/artifactregistry.writer' \
    --quiet"

# Grant service account read access
run_cmd "gcloud artifacts repositories add-iam-policy-binding $ARTIFACT_REPO \
    --location=$REGION \
    --member='serviceAccount:$SA_EMAIL' \
    --role='roles/artifactregistry.reader' \
    --quiet"

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP TEMP FILES
# ═══════════════════════════════════════════════════════════════════════════════

log_info "Cleaning up temporary credential files..."
rm -f /tmp/study-buddy-sql-*.tmp /tmp/study-buddy-redis-*.tmp 2>/dev/null

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification"

if [[ "$DRY_RUN" != true ]]; then
    echo ""
    echo "Secrets created:"
    gcloud secrets list --format="table(name,createTime)"
    
    echo ""
    echo "Artifact Registry:"
    gcloud artifacts repositories describe "$ARTIFACT_REPO" --location="$REGION" \
        --format="table(name,format,sizeBytes)"
    
    echo ""
    echo "Docker Image Path:"
    echo "  $IMAGE_PATH"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Phase 7-8 Complete!"

echo "Next steps:"
echo "  1. Run ./05_deploy_services.sh to build and deploy to Cloud Run"
echo ""
echo "All secrets have been securely stored in Secret Manager."
echo "Artifact Registry is ready for Docker image storage."
