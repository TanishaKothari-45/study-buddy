#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Common Functions
# ═══════════════════════════════════════════════════════════════════════════════
# This file contains shared functions used by all deployment scripts.
# Source this file at the beginning of each script:
#   source "$(dirname "$0")/00_common.sh"
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}📌 $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

log_header() {
    echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  $1${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}\n"
}

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION LOADING
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.env"

load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        log_success "Loaded configuration from config.env"
    else
        log_error "Configuration file not found: $CONFIG_FILE"
        log_info "Please copy config.env.example to config.env and fill in your values:"
        log_info "  cp ${SCRIPT_DIR}/config.env.example ${SCRIPT_DIR}/config.env"
        exit 1
    fi
    
    # Derived variables
    export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
    export CLOUDBUILD_SA="${PROJECT_ID}@cloudbuild.gserviceaccount.com"
    export GCS_BUCKET="${GCS_BUCKET_PREFIX}-${PROJECT_ID}"
    export VPC_CONNECTOR_PATH="projects/${PROJECT_ID}/locations/${REGION}/connectors/${VPC_CONNECTOR}"
    export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/backend"
}

# ═══════════════════════════════════════════════════════════════════════════════
# DRY RUN MODE
# ═══════════════════════════════════════════════════════════════════════════════

DRY_RUN=false

check_dry_run() {
    if [[ "$1" == "--dry-run" ]] || [[ "$2" == "--dry-run" ]]; then
        DRY_RUN=true
        log_warning "DRY RUN MODE - Commands will be shown but not executed"
    fi
}

run_cmd() {
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[DRY RUN] Would execute:${NC}"
        echo -e "${CYAN}$@${NC}"
        echo ""
    else
        log_info "Executing: $@"
        eval "$@"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PREREQUISITE CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

check_prerequisites() {
    log_step "Checking Prerequisites"
    
    # Check gcloud
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it from:"
        log_info "https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    log_success "gcloud CLI found: $(gcloud --version | head -1)"
    
    # Check authentication
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 &> /dev/null; then
        log_error "Not authenticated with gcloud. Please run:"
        log_info "  gcloud auth login"
        exit 1
    fi
    log_success "Authenticated as: $(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1)"
    
    # Check Docker (optional for most phases)
    if command -v docker &> /dev/null; then
        log_success "Docker found: $(docker --version)"
    else
        log_warning "Docker not found (optional for infrastructure setup)"
    fi
}

check_project_exists() {
    if gcloud projects describe "$PROJECT_ID" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

check_billing_enabled() {
    local billing_status=$(gcloud billing projects describe "$PROJECT_ID" --format="value(billingEnabled)" 2>/dev/null)
    if [[ "$billing_status" == "True" ]]; then
        return 0
    else
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE EXISTENCE CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

resource_exists() {
    local resource_type="$1"
    local resource_name="$2"
    
    case "$resource_type" in
        "service-account")
            gcloud iam service-accounts describe "${resource_name}@${PROJECT_ID}.iam.gserviceaccount.com" &> /dev/null
            ;;
        "vpc-connector")
            gcloud compute networks vpc-access connectors describe "$resource_name" --region="$REGION" &> /dev/null
            ;;
        "sql-instance")
            gcloud sql instances describe "$resource_name" &> /dev/null
            ;;
        "redis-instance")
            gcloud redis instances describe "$resource_name" --region="$REGION" &> /dev/null
            ;;
        "gcs-bucket")
            gcloud storage buckets describe "gs://${resource_name}" &> /dev/null
            ;;
        "secret")
            gcloud secrets describe "$resource_name" &> /dev/null
            ;;
        "artifact-repo")
            gcloud artifacts repositories describe "$resource_name" --location="$REGION" &> /dev/null
            ;;
        "cloud-run")
            gcloud run services describe "$resource_name" --region="$REGION" &> /dev/null
            ;;
        *)
            log_error "Unknown resource type: $resource_type"
            return 1
            ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════════
# USER PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

ask_yes_no() {
    local prompt="$1"
    local default="${2:-y}"
    
    if [[ "$default" == "y" ]]; then
        prompt="${prompt} [Y/n]: "
    else
        prompt="${prompt} [y/N]: "
    fi
    
    read -p "$prompt" response
    response=${response:-$default}
    
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

ask_resource_action() {
    local resource_type="$1"
    local resource_name="$2"
    
    if resource_exists "$resource_type" "$resource_name"; then
        log_warning "$resource_type '$resource_name' already exists."
        echo ""
        echo "What would you like to do?"
        echo "  1) Skip (keep existing)"
        echo "  2) Delete and recreate"
        echo "  3) Abort script"
        echo ""
        read -p "Choose option [1]: " choice
        choice=${choice:-1}
        
        case "$choice" in
            1) return 1 ;;  # Skip
            2) return 0 ;;  # Delete and recreate
            3) exit 0 ;;    # Abort
            *) return 1 ;;  # Default to skip
        esac
    fi
    return 0  # Resource doesn't exist, proceed
}

prompt_secret() {
    local secret_name="$1"
    local secret_description="$2"
    local secret_value=""
    
    echo ""
    log_info "Please enter your $secret_description"
    log_info "(Input will be hidden for security)"
    read -s -p "$secret_name: " secret_value
    echo ""
    
    if [[ -z "$secret_value" ]]; then
        log_error "$secret_name cannot be empty"
        exit 1
    fi
    
    echo "$secret_value"
}

# ═══════════════════════════════════════════════════════════════════════════════
# WAIT FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

wait_for_operation() {
    local operation_type="$1"
    local resource_name="$2"
    local timeout="${3:-600}"
    local interval="${4:-10}"
    local elapsed=0
    
    log_info "Waiting for $operation_type to complete (timeout: ${timeout}s)..."
    
    while [[ $elapsed -lt $timeout ]]; do
        case "$operation_type" in
            "sql-instance")
                local state=$(gcloud sql instances describe "$resource_name" --format="value(state)" 2>/dev/null)
                if [[ "$state" == "RUNNABLE" ]]; then
                    log_success "$operation_type '$resource_name' is ready"
                    return 0
                fi
                ;;
            "redis-instance")
                local state=$(gcloud redis instances describe "$resource_name" --region="$REGION" --format="value(state)" 2>/dev/null)
                if [[ "$state" == "READY" ]]; then
                    log_success "$operation_type '$resource_name' is ready"
                    return 0
                fi
                ;;
            "vpc-connector")
                local state=$(gcloud compute networks vpc-access connectors describe "$resource_name" --region="$REGION" --format="value(state)" 2>/dev/null)
                if [[ "$state" == "READY" ]]; then
                    log_success "$operation_type '$resource_name' is ready"
                    return 0
                fi
                ;;
        esac
        
        echo -n "."
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    
    echo ""
    log_error "Timeout waiting for $operation_type '$resource_name'"
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

print_config_summary() {
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                    Configuration Summary                     │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ Project ID:        $PROJECT_ID"
    echo "│ Region:            $REGION"
    echo "│ Service Account:   $SA_NAME"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ SQL Instance:      $SQL_INSTANCE ($SQL_TIER)"
    echo "│ Redis Instance:    $REDIS_INSTANCE (${REDIS_SIZE}GB)"
    echo "│ GCS Bucket:        $GCS_BUCKET"
    echo "│ VPC Connector:     $VPC_CONNECTOR"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ API Service:       $API_SERVICE_NAME"
    echo "│ Worker Service:    $WORKER_SERVICE_NAME"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP ON ERROR
# ═══════════════════════════════════════════════════════════════════════════════

cleanup_on_error() {
    log_error "Script failed. Please check the error above."
    log_info "You may need to manually clean up partially created resources."
    exit 1
}

trap cleanup_on_error ERR

# ═══════════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Export common variables
export SCRIPT_DIR
export CONFIG_FILE
export DRY_RUN
