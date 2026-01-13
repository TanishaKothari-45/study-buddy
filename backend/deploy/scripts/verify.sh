#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Verification Script
# ═══════════════════════════════════════════════════════════════════════════════
# This script performs health checks on all deployed resources.
#
# Usage:
#   ./verify.sh
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

log_header "Study Buddy Deployment Verification"

load_config

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

check_pass() {
    log_success "$1"
    ((PASS_COUNT++))
}

check_fail() {
    log_error "$1"
    ((FAIL_COUNT++))
}

check_warn() {
    log_warning "$1"
    ((WARN_COUNT++))
}

# ═══════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Infrastructure Health Checks"

# VPC Connector
echo -n "VPC Connector ($VPC_CONNECTOR): "
if resource_exists "vpc-connector" "$VPC_CONNECTOR"; then
    state=$(gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR" --region="$REGION" --format="value(state)" 2>/dev/null)
    if [[ "$state" == "READY" ]]; then
        check_pass "READY"
    else
        check_warn "$state"
    fi
else
    check_fail "NOT FOUND"
fi

# Cloud SQL
echo -n "Cloud SQL ($SQL_INSTANCE): "
if resource_exists "sql-instance" "$SQL_INSTANCE"; then
    state=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(state)" 2>/dev/null)
    if [[ "$state" == "RUNNABLE" ]]; then
        check_pass "RUNNABLE"
    else
        check_warn "$state"
    fi
else
    check_fail "NOT FOUND"
fi

# Redis
echo -n "Redis ($REDIS_INSTANCE): "
if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
    state=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(state)" 2>/dev/null)
    if [[ "$state" == "READY" ]]; then
        check_pass "READY"
    else
        check_warn "$state"
    fi
else
    check_fail "NOT FOUND"
fi

# GCS Bucket
echo -n "GCS Bucket ($GCS_BUCKET): "
if resource_exists "gcs-bucket" "$GCS_BUCKET"; then
    check_pass "EXISTS"
else
    check_fail "NOT FOUND"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# SECRETS CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Secrets Health Checks"

REQUIRED_SECRETS=("OPENAI_API_KEY" "GEMINI_API_KEY" "PINECONE_API_KEY" "JWT_SECRET_KEY" "DATABASE_URL" "REDIS_URL" "ENCRYPTION_KEY")

for secret in "${REQUIRED_SECRETS[@]}"; do
    echo -n "Secret ($secret): "
    if resource_exists "secret" "$secret"; then
        # Check if service account has access
        has_access=$(gcloud secrets get-iam-policy "$secret" --format="value(bindings.members)" 2>/dev/null | grep -c "$SA_EMAIL")
        if [[ "$has_access" -gt 0 ]]; then
            check_pass "OK (SA has access)"
        else
            check_warn "EXISTS but SA may not have access"
        fi
    else
        check_fail "NOT FOUND"
    fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# CLOUD RUN CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Cloud Run Services Health Checks"

# API Service
echo -n "API Service ($API_SERVICE_NAME): "
if resource_exists "cloud-run" "$API_SERVICE_NAME"; then
    conditions=$(gcloud run services describe "$API_SERVICE_NAME" --region="$REGION" --format="value(status.conditions[0].status)" 2>/dev/null)
    if [[ "$conditions" == "True" ]]; then
        check_pass "HEALTHY"
    else
        check_warn "UNHEALTHY"
    fi
else
    check_fail "NOT DEPLOYED"
fi

# Worker Service
echo -n "Worker Service ($WORKER_SERVICE_NAME): "
if resource_exists "cloud-run" "$WORKER_SERVICE_NAME"; then
    conditions=$(gcloud run services describe "$WORKER_SERVICE_NAME" --region="$REGION" --format="value(status.conditions[0].status)" 2>/dev/null)
    if [[ "$conditions" == "True" ]]; then
        check_pass "HEALTHY"
    else
        check_warn "UNHEALTHY"
    fi
else
    check_fail "NOT DEPLOYED"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINT CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

log_step "API Endpoint Health Checks"

if resource_exists "cloud-run" "$API_SERVICE_NAME"; then
    API_URL=$(gcloud run services describe "$API_SERVICE_NAME" --region="$REGION" --format="value(status.url)" 2>/dev/null)
    
    if [[ -n "$API_URL" ]]; then
        echo -n "API Root Endpoint: "
        response=$(curl -s -w "\n%{http_code}" "$API_URL/" --max-time 30 2>/dev/null)
        http_code=$(echo "$response" | tail -1)
        
        if [[ "$http_code" == "200" ]]; then
            check_pass "HTTP 200"
        elif [[ "$http_code" == "000" ]]; then
            check_fail "TIMEOUT/UNREACHABLE"
        else
            check_warn "HTTP $http_code"
        fi
        
        echo -n "API Health Endpoint: "
        response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/health" --max-time 30 2>/dev/null)
        http_code=$(echo "$response" | tail -1)
        
        if [[ "$http_code" == "200" ]]; then
            check_pass "HTTP 200"
        elif [[ "$http_code" == "000" ]]; then
            check_warn "TIMEOUT (may not exist)"
        else
            check_warn "HTTP $http_code"
        fi
    fi
else
    echo "API Endpoint checks skipped (service not deployed)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# RECENT LOGS CHECK
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Recent Error Logs"

echo "Checking for recent errors in API service..."
error_count=$(gcloud run services logs read "$API_SERVICE_NAME" --region="$REGION" --filter="severity>=ERROR" --limit=10 2>/dev/null | wc -l)

if [[ "$error_count" -gt 2 ]]; then
    check_warn "Found $((error_count - 2)) recent errors (check logs for details)"
    echo ""
    echo "Recent errors:"
    gcloud run services logs read "$API_SERVICE_NAME" --region="$REGION" --filter="severity>=ERROR" --limit=5 2>/dev/null
else
    check_pass "No recent errors found"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification Summary"

echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│                    Verification Results                      │"
echo "├─────────────────────────────────────────────────────────────┤"
echo "│  ✅ Passed:   $PASS_COUNT"
echo "│  ⚠️  Warnings: $WARN_COUNT"
echo "│  ❌ Failed:   $FAIL_COUNT"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    log_error "Verification found $FAIL_COUNT failed checks"
    echo "Please review the failed items above and run the appropriate setup scripts."
    exit 1
elif [[ "$WARN_COUNT" -gt 0 ]]; then
    log_warning "Verification completed with $WARN_COUNT warnings"
    echo "The deployment may still work, but please review the warnings."
    exit 0
else
    log_success "All verification checks passed!"
    exit 0
fi
