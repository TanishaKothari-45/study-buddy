#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Phase 3: VPC & Networking
# ═══════════════════════════════════════════════════════════════════════════════
# This script handles:
#   - VPC Connector creation
#   - Network configuration verification
#
# Usage:
#   ./02_setup_network.sh [--dry-run]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

check_dry_run "$@"

log_header "Phase 3: VPC & Networking Configuration"

load_config
check_prerequisites

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFY VPC NETWORK EXISTS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verifying VPC Network"

if gcloud compute networks describe "$VPC_NETWORK" &> /dev/null; then
    log_success "VPC network '$VPC_NETWORK' exists"
else
    log_error "VPC network '$VPC_NETWORK' not found"
    log_info "Please ensure the network exists or update VPC_NETWORK in config.env"
    exit 1
fi

# Check for IP range conflicts
log_info "Checking for IP range conflicts..."
existing_ranges=$(gcloud compute networks subnets list --network="$VPC_NETWORK" --format="value(ipCidrRange)" 2>/dev/null)

if echo "$existing_ranges" | grep -q "${VPC_IP_RANGE%/*}"; then
    log_warning "IP range $VPC_IP_RANGE may conflict with existing subnets"
    log_info "Existing ranges:"
    gcloud compute networks subnets list --network="$VPC_NETWORK" --format="table(name,ipCidrRange,region)"
    
    if ! ask_yes_no "Continue anyway?"; then
        log_info "Please update VPC_IP_RANGE in config.env to a non-conflicting range"
        exit 0
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# CREATE VPC CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Creating Serverless VPC Access Connector"

if ask_resource_action "vpc-connector" "$VPC_CONNECTOR"; then
    if resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
        log_info "Deleting existing VPC connector..."
        run_cmd "gcloud compute networks vpc-access connectors delete $VPC_CONNECTOR \
            --region=$REGION \
            --quiet"
        
        log_info "Waiting for deletion to complete..."
        sleep 30
    fi
    
    log_info "Creating VPC connector '$VPC_CONNECTOR'..."
    log_info "This may take 2-3 minutes..."
    
    run_cmd "gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
        --region=$REGION \
        --network=$VPC_NETWORK \
        --range=$VPC_IP_RANGE \
        --min-instances=2 \
        --max-instances=3 \
        --machine-type=e2-micro"
    
    # Wait for connector to be ready
    if [[ "$DRY_RUN" != true ]]; then
        wait_for_operation "vpc-connector" "$VPC_CONNECTOR" 300
    fi
    
    log_success "VPC connector created"
else
    log_info "Skipping VPC connector creation"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification"

if [[ "$DRY_RUN" != true ]]; then
    log_info "VPC Connector Details:"
    gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR" \
        --region="$REGION" \
        --format="table(name,state,network,ipCidrRange,minInstances,maxInstances,machineType)"
    
    echo ""
    echo "VPC Connector Full Path (for Cloud Run):"
    echo "  $VPC_CONNECTOR_PATH"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Phase 3 Complete!"

echo "Next steps:"
echo "  1. Run ./03_create_infra.sh to create Cloud SQL, Redis, and GCS"
echo ""
echo "VPC Connector Info:"
echo "  Name: $VPC_CONNECTOR"
echo "  Path: $VPC_CONNECTOR_PATH"
echo "  Network: $VPC_NETWORK"
echo "  IP Range: $VPC_IP_RANGE"
