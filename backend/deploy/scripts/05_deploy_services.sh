#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Phase 9-10: Cloud Build & Cloud Run Deploy
# ═══════════════════════════════════════════════════════════════════════════════
# This script handles:
#   - Building Docker image via Cloud Build
#   - Deploying API service to Cloud Run
#   - Deploying Worker service to Cloud Run
#
# Usage:
#   ./05_deploy_services.sh [--dry-run]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

check_dry_run "$@"

log_header "Phase 9-10: Cloud Build & Cloud Run Deployment"

load_config
check_prerequisites

# Get backend directory
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../../" && pwd)"

# Verify backend directory
if [[ ! -f "$BACKEND_DIR/cloudbuild.yaml" ]]; then
    log_error "cloudbuild.yaml not found in $BACKEND_DIR"
    log_info "Please ensure you're running this script from the correct location"
    exit 1
fi

if [[ ! -f "$BACKEND_DIR/Dockerfile" ]]; then
    log_error "Dockerfile not found in $BACKEND_DIR"
    exit 1
fi

log_success "Found cloudbuild.yaml and Dockerfile in $BACKEND_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFY PREREQUISITES
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verifying Prerequisites"

# Check VPC connector
if ! resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
    log_error "VPC connector '$VPC_CONNECTOR' not found"
    log_info "Please run ./02_setup_network.sh first"
    exit 1
fi
log_success "VPC connector exists"

# Check Cloud SQL
if ! resource_exists "sql-instance" "$SQL_INSTANCE"; then
    log_error "Cloud SQL instance '$SQL_INSTANCE' not found"
    log_info "Please run ./03_create_infra.sh first"
    exit 1
fi
SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
log_success "Cloud SQL instance exists: $SQL_CONNECTION"

# Check Redis
if ! resource_exists "redis-instance" "$REDIS_INSTANCE"; then
    log_error "Redis instance '$REDIS_INSTANCE' not found"
    log_info "Please run ./03_create_infra.sh first"
    exit 1
fi
log_success "Redis instance exists"

# Check secrets
REQUIRED_SECRETS=("OPENAI_API_KEY" "GEMINI_API_KEY" "PINECONE_API_KEY" "JWT_SECRET_KEY" "DATABASE_URL" "REDIS_URL" "ENCRYPTION_KEY")
for secret in "${REQUIRED_SECRETS[@]}"; do
    if ! resource_exists "secret" "$secret"; then
        log_error "Secret '$secret' not found"
        log_info "Please run ./04_setup_secrets.sh first"
        exit 1
    fi
done
log_success "All required secrets exist"

# Check Artifact Registry
if ! resource_exists "artifact-repo" "$ARTIFACT_REPO"; then
    log_error "Artifact Registry '$ARTIFACT_REPO' not found"
    log_info "Please run ./04_setup_secrets.sh first"
    exit 1
fi
log_success "Artifact Registry exists"

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD AND DEPLOY OPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Deployment Options"

echo "Choose deployment method:"
echo "  1) Full deployment (Cloud Build + both services)"
echo "  2) Deploy API service only"
echo "  3) Deploy Worker service only"
echo "  4) Run Cloud Build only (no deploy)"
echo ""
read -p "Choose option [1]: " deploy_option
deploy_option=${deploy_option:-1}

# ═══════════════════════════════════════════════════════════════════════════════
# CLOUD BUILD (Full Pipeline or Build Only)
# ═══════════════════════════════════════════════════════════════════════════════

if [[ "$deploy_option" == "1" ]] || [[ "$deploy_option" == "4" ]]; then
    log_step "Running Cloud Build"
    
    log_info "Submitting build from $BACKEND_DIR..."
    log_info "This may take 5-10 minutes..."
    
    cd "$BACKEND_DIR"
    
    run_cmd "gcloud builds submit \
        --config=cloudbuild.yaml \
        --substitutions=\
_REGION=$REGION,\
_REPO=$ARTIFACT_REPO,\
_SERVICE_ACCOUNT=$SA_EMAIL,\
_VPC_CONNECTOR=$VPC_CONNECTOR_PATH,\
_SQL_CONNECTION=$SQL_CONNECTION,\
_GCS_BUCKET=$GCS_BUCKET \
        ."
    
    if [[ "$deploy_option" == "4" ]]; then
        log_success "Cloud Build complete (no deployment)"
        exit 0
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOY API SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

if [[ "$deploy_option" == "1" ]] || [[ "$deploy_option" == "2" ]]; then
    log_step "Deploying API Service"
    
    log_info "Deploying '$API_SERVICE_NAME' to Cloud Run..."
    
    run_cmd "gcloud run deploy $API_SERVICE_NAME \
        --image=${IMAGE_PATH}:latest \
        --region=$REGION \
        --platform=managed \
        --service-account=$SA_EMAIL \
        --vpc-connector=$VPC_CONNECTOR_PATH \
        --add-cloudsql-instances=$SQL_CONNECTION \
        --set-secrets='\
OPENAI_API_KEY=OPENAI_API_KEY:latest,\
GEMINI_API_KEY=GEMINI_API_KEY:latest,\
PINECONE_API_KEY=PINECONE_API_KEY:latest,\
JWT_SECRET_KEY=JWT_SECRET_KEY:latest,\
DATABASE_URL=DATABASE_URL:latest,\
REDIS_URL=REDIS_URL:latest,\
ENCRYPTION_KEY=ENCRYPTION_KEY:latest' \
        --set-env-vars='\
ENVIRONMENT=production,\
PINECONE_INDEX_NAME=$PINECONE_INDEX_NAME,\
GCS_BUCKET_NAME=$GCS_BUCKET' \
        --memory=$API_MEMORY \
        --cpu=$API_CPU \
        --timeout=$API_TIMEOUT \
        --concurrency=80 \
        --min-instances=$API_MIN_INSTANCES \
        --max-instances=$API_MAX_INSTANCES \
        --allow-unauthenticated"
    
    if [[ "$DRY_RUN" != true ]]; then
        API_URL=$(gcloud run services describe "$API_SERVICE_NAME" --region="$REGION" --format="value(status.url)")
        log_success "API Service deployed: $API_URL"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOY WORKER SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

if [[ "$deploy_option" == "1" ]] || [[ "$deploy_option" == "3" ]]; then
    log_step "Deploying Worker Service"
    
    log_info "Deploying '$WORKER_SERVICE_NAME' to Cloud Run..."
    
    run_cmd "gcloud run deploy $WORKER_SERVICE_NAME \
        --image=${IMAGE_PATH}:latest \
        --region=$REGION \
        --platform=managed \
        --service-account=$SA_EMAIL \
        --vpc-connector=$VPC_CONNECTOR_PATH \
        --add-cloudsql-instances=$SQL_CONNECTION \
        --set-secrets='\
OPENAI_API_KEY=OPENAI_API_KEY:latest,\
GEMINI_API_KEY=GEMINI_API_KEY:latest,\
PINECONE_API_KEY=PINECONE_API_KEY:latest,\
JWT_SECRET_KEY=JWT_SECRET_KEY:latest,\
DATABASE_URL=DATABASE_URL:latest,\
REDIS_URL=REDIS_URL:latest,\
ENCRYPTION_KEY=ENCRYPTION_KEY:latest' \
        --set-env-vars='\
ENVIRONMENT=production,\
PINECONE_INDEX_NAME=$PINECONE_INDEX_NAME,\
GCS_BUCKET_NAME=$GCS_BUCKET' \
        --command=python \
        --args='-m,app.worker_entrypoint' \
        --memory=$WORKER_MEMORY \
        --cpu=$WORKER_CPU \
        --timeout=$WORKER_TIMEOUT \
        --min-instances=$WORKER_MIN_INSTANCES \
        --max-instances=$WORKER_MAX_INSTANCES \
        --no-allow-unauthenticated \
        --cpu-boost \
        --no-cpu-throttling"
    
    if [[ "$DRY_RUN" != true ]]; then
        WORKER_URL=$(gcloud run services describe "$WORKER_SERVICE_NAME" --region="$REGION" --format="value(status.url)")
        log_success "Worker Service deployed: $WORKER_URL"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification"

if [[ "$DRY_RUN" != true ]]; then
    echo ""
    echo "Cloud Run Services:"
    gcloud run services list --region="$REGION" --format="table(SERVICE,REGION,URL,LAST_DEPLOYED)"
    
    echo ""
    
    # Test API health
    if [[ -n "$API_URL" ]]; then
        log_info "Testing API health endpoint..."
        response=$(curl -s -w "\n%{http_code}" "$API_URL/" 2>/dev/null)
        http_code=$(echo "$response" | tail -1)
        body=$(echo "$response" | head -1)
        
        if [[ "$http_code" == "200" ]]; then
            log_success "API health check passed"
            echo "Response: $body"
        else
            log_warning "API health check returned HTTP $http_code"
            log_info "This may be normal if the service is still starting up"
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Phase 9-10 Complete!"

echo "┌─────────────────────────────────────────────────────────────┐"
echo "│                    Deployment Summary                        │"
echo "├─────────────────────────────────────────────────────────────┤"
if [[ -n "$API_URL" ]]; then
    echo "│ API URL:     $API_URL"
fi
if [[ -n "$WORKER_URL" ]]; then
    echo "│ Worker URL:  $WORKER_URL (internal only)"
fi
echo "├─────────────────────────────────────────────────────────────┤"
echo "│ Useful commands:                                             │"
echo "│   View logs:    gcloud run services logs read $API_SERVICE_NAME --region=$REGION"
echo "│   Describe:     gcloud run services describe $API_SERVICE_NAME --region=$REGION"
echo "│   Update:       gcloud run services update $API_SERVICE_NAME --region=$REGION"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""
echo "Next steps:"
echo "  1. Run ./verify.sh to perform health checks"
echo "  2. Run ./status.sh to view deployment status"
echo ""
echo "🎉 Deployment complete!"
