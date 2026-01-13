#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Study Buddy GCP Deployment - Phase 4-6: Infrastructure (SQL, Redis, GCS)
# ═══════════════════════════════════════════════════════════════════════════════
# This script handles:
#   - Cloud SQL (PostgreSQL) instance creation
#   - Memorystore (Redis) instance creation
#   - Cloud Storage bucket creation
#
# Usage:
#   ./03_create_infra.sh [--dry-run]
# ═══════════════════════════════════════════════════════════════════════════════

source "$(dirname "$0")/00_common.sh"

check_dry_run "$@"

log_header "Phase 4-6: Infrastructure Setup (SQL, Redis, Storage)"

load_config
check_prerequisites

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: CLOUD SQL (PostgreSQL)
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 4: Cloud SQL (PostgreSQL)"

if ask_resource_action "sql-instance" "$SQL_INSTANCE"; then
    if resource_exists "sql-instance" "$SQL_INSTANCE"; then
        log_warning "Deleting Cloud SQL instance is irreversible!"
        if ask_yes_no "Are you sure you want to delete '$SQL_INSTANCE'?" "n"; then
            log_info "Deleting existing Cloud SQL instance..."
            run_cmd "gcloud sql instances delete $SQL_INSTANCE --quiet"
            log_info "Waiting for deletion (this may take several minutes)..."
            sleep 60
        else
            log_info "Skipping Cloud SQL creation"
            SQL_SKIP=true
        fi
    fi
    
    if [[ "$SQL_SKIP" != true ]]; then
        # Generate secure password
        SQL_PASSWORD=$(openssl rand -base64 24)
        
        log_info "Creating Cloud SQL instance '$SQL_INSTANCE'..."
        log_info "This may take 5-10 minutes..."
        
        run_cmd "gcloud sql instances create $SQL_INSTANCE \
            --database-version=$SQL_VERSION \
            --tier=$SQL_TIER \
            --region=$REGION \
            --storage-type=SSD \
            --storage-size=${SQL_STORAGE_SIZE}GB \
            --storage-auto-increase \
            --backup-start-time=03:00 \
            --availability-type=zonal \
            --network=$VPC_NETWORK \
            --no-assign-ip"
        
        # Wait for instance to be ready
        if [[ "$DRY_RUN" != true ]]; then
            wait_for_operation "sql-instance" "$SQL_INSTANCE" 600
        fi
        
        # Create database
        log_info "Creating database '$SQL_DATABASE'..."
        run_cmd "gcloud sql databases create $SQL_DATABASE --instance=$SQL_INSTANCE"
        
        # Create user
        log_info "Creating database user '$SQL_USER'..."
        run_cmd "gcloud sql users create $SQL_USER \
            --instance=$SQL_INSTANCE \
            --password='$SQL_PASSWORD'"
        
        # Get connection info
        if [[ "$DRY_RUN" != true ]]; then
            SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")
            
            log_success "Cloud SQL instance created"
            echo ""
            echo "┌─────────────────────────────────────────────────────────────┐"
            echo "│  ⚠️  SAVE THESE CREDENTIALS SECURELY!                        │"
            echo "├─────────────────────────────────────────────────────────────┤"
            echo "│  Connection Name: $SQL_CONNECTION"
            echo "│  Database:        $SQL_DATABASE"
            echo "│  Username:        $SQL_USER"
            echo "│  Password:        $SQL_PASSWORD"
            echo "└─────────────────────────────────────────────────────────────┘"
            echo ""
            
            # Save to temp file for secrets script
            echo "$SQL_PASSWORD" > /tmp/study-buddy-sql-password.tmp
            echo "$SQL_CONNECTION" > /tmp/study-buddy-sql-connection.tmp
            chmod 600 /tmp/study-buddy-sql-*.tmp
        fi
    fi
else
    log_info "Skipping Cloud SQL creation"
    if [[ "$DRY_RUN" != true ]]; then
        SQL_CONNECTION=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)" 2>/dev/null || echo "")
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: MEMORYSTORE (Redis)
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 5: Memorystore (Redis)"

if ask_resource_action "redis-instance" "$REDIS_INSTANCE"; then
    if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
        log_warning "Deleting Redis instance will clear all cached data!"
        if ask_yes_no "Are you sure you want to delete '$REDIS_INSTANCE'?" "n"; then
            log_info "Deleting existing Redis instance..."
            run_cmd "gcloud redis instances delete $REDIS_INSTANCE --region=$REGION --quiet"
            log_info "Waiting for deletion..."
            sleep 60
        else
            log_info "Skipping Redis creation"
            REDIS_SKIP=true
        fi
    fi
    
    if [[ "$REDIS_SKIP" != true ]]; then
        log_info "Creating Redis instance '$REDIS_INSTANCE'..."
        log_info "This may take 5-10 minutes..."
        
        run_cmd "gcloud redis instances create $REDIS_INSTANCE \
            --size=$REDIS_SIZE \
            --region=$REGION \
            --redis-version=$REDIS_VERSION \
            --tier=$REDIS_TIER \
            --network=$VPC_NETWORK \
            --connect-mode=DIRECT_PEERING"
        
        # Wait for instance to be ready
        if [[ "$DRY_RUN" != true ]]; then
            wait_for_operation "redis-instance" "$REDIS_INSTANCE" 600
        fi
        
        # Get connection info
        if [[ "$DRY_RUN" != true ]]; then
            REDIS_HOST=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(host)")
            REDIS_PORT=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(port)")
            
            log_success "Redis instance created"
            echo ""
            echo "Redis Connection Info:"
            echo "  Host: $REDIS_HOST"
            echo "  Port: $REDIS_PORT"
            echo "  URL:  redis://${REDIS_HOST}:${REDIS_PORT}"
            echo ""
            
            # Save to temp file for secrets script
            echo "$REDIS_HOST" > /tmp/study-buddy-redis-host.tmp
            echo "$REDIS_PORT" > /tmp/study-buddy-redis-port.tmp
            chmod 600 /tmp/study-buddy-redis-*.tmp
        fi
    fi
else
    log_info "Skipping Redis creation"
    if [[ "$DRY_RUN" != true ]]; then
        REDIS_HOST=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(host)" 2>/dev/null || echo "")
        REDIS_PORT=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(port)" 2>/dev/null || echo "6379")
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6: CLOUD STORAGE (GCS)
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Phase 6: Cloud Storage (GCS)"

if ask_resource_action "gcs-bucket" "$GCS_BUCKET"; then
    if resource_exists "gcs-bucket" "$GCS_BUCKET"; then
        log_warning "Deleting bucket will delete all stored files!"
        if ask_yes_no "Are you sure you want to delete 'gs://$GCS_BUCKET'?" "n"; then
            log_info "Deleting existing bucket and contents..."
            run_cmd "gcloud storage rm -r gs://$GCS_BUCKET"
        else
            log_info "Skipping GCS bucket creation"
            GCS_SKIP=true
        fi
    fi
    
    if [[ "$GCS_SKIP" != true ]]; then
        log_info "Creating Cloud Storage bucket 'gs://$GCS_BUCKET'..."
        
        run_cmd "gcloud storage buckets create gs://$GCS_BUCKET \
            --location=$REGION \
            --default-storage-class=$GCS_STORAGE_CLASS \
            --uniform-bucket-level-access \
            --public-access-prevention"
        
        # Configure CORS
        log_info "Configuring CORS..."
        cat > /tmp/cors-config.json << 'EOF'
[
  {
    "origin": ["*"],
    "method": ["GET", "PUT", "POST", "DELETE", "OPTIONS"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
    "maxAgeSeconds": 3600
  }
]
EOF
        run_cmd "gcloud storage buckets update gs://$GCS_BUCKET --cors-file=/tmp/cors-config.json"
        
        # Configure lifecycle (auto-delete old files)
        log_info "Configuring lifecycle rules..."
        cat > /tmp/lifecycle-config.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 7, "matchesPrefix": ["evaluate_jobs/"]}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 30, "matchesPrefix": ["temp/"]}
      }
    ]
  }
}
EOF
        run_cmd "gcloud storage buckets update gs://$GCS_BUCKET --lifecycle-file=/tmp/lifecycle-config.json"
        
        # Grant service account access
        log_info "Granting service account access..."
        run_cmd "gcloud storage buckets add-iam-policy-binding gs://$GCS_BUCKET \
            --member='serviceAccount:$SA_EMAIL' \
            --role='roles/storage.objectAdmin'"
        
        log_success "Cloud Storage bucket created"
    fi
else
    log_info "Skipping GCS bucket creation"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

log_step "Verification"

if [[ "$DRY_RUN" != true ]]; then
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                   Infrastructure Summary                     │"
    echo "├─────────────────────────────────────────────────────────────┤"
    
    # Cloud SQL
    echo "│ Cloud SQL:"
    if resource_exists "sql-instance" "$SQL_INSTANCE"; then
        sql_state=$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(state)")
        echo "│   Instance:   $SQL_INSTANCE ($sql_state)"
        echo "│   Connection: ${SQL_CONNECTION:-$(gcloud sql instances describe "$SQL_INSTANCE" --format="value(connectionName)")}"
    else
        echo "│   Not created"
    fi
    
    echo "├─────────────────────────────────────────────────────────────┤"
    
    # Redis
    echo "│ Redis:"
    if resource_exists "redis-instance" "$REDIS_INSTANCE"; then
        redis_state=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(state)")
        redis_host=$(gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --format="value(host)")
        echo "│   Instance: $REDIS_INSTANCE ($redis_state)"
        echo "│   Host:     $redis_host"
    else
        echo "│   Not created"
    fi
    
    echo "├─────────────────────────────────────────────────────────────┤"
    
    # GCS
    echo "│ Cloud Storage:"
    if resource_exists "gcs-bucket" "$GCS_BUCKET"; then
        echo "│   Bucket: gs://$GCS_BUCKET"
    else
        echo "│   Not created"
    fi
    
    echo "└─────────────────────────────────────────────────────────────┘"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

log_header "Phase 4-6 Complete!"

echo "Next steps:"
echo "  1. Run ./04_setup_secrets.sh to configure Secret Manager"
echo ""
echo "⚠️  If you created Cloud SQL, make sure to save the password shown above!"
echo "    You will need it for the secrets setup."
