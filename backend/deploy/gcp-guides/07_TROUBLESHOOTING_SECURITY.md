# 🛠️ Phase 13-14: Troubleshooting & Security

## Overview

This guide covers:
- **Common Issues** - Deployment and runtime problems
- **Debugging Techniques** - Log analysis and diagnostics
- **Security Checklist** - Production hardening
- **Maintenance Procedures** - Ongoing operations

**Time Required:** Reference guide (as needed)

---

## Phase 13: Troubleshooting Guide

### 13.1 Deployment Issues

#### Issue: Cloud Build fails with "permission denied"

**Symptoms:**
- Build step fails with 403 error
- "Permission denied" in build logs

**Solution:**
```bash
# Check Cloud Build service account permissions
export CLOUDBUILD_SA="${PROJECT_ID}@cloudbuild.gserviceaccount.com"

gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${CLOUDBUILD_SA}" \
  --format="table(bindings.role)"

# Grant missing roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser"
```

#### Issue: Docker image push fails to Artifact Registry

**Symptoms:**
- "unauthorized" or "denied" error during push

**Solution:**
```bash
# Re-authenticate Docker
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Verify repository exists
gcloud artifacts repositories describe $ARTIFACT_REPO --location=$REGION

# Verify permissions
gcloud artifacts repositories get-iam-policy $ARTIFACT_REPO \
  --location=$REGION
```

#### Issue: Cloud Run deployment fails

**Symptoms:**
- Deployment times out
- "Container failed to start" error

**Solution:**
```bash
# Check deployment logs
gcloud run services logs read study-buddy-api \
  --region=$REGION \
  --filter="severity>=ERROR" \
  --limit=50

# Check if secrets are accessible
for SECRET in OPENAI_API_KEY GEMINI_API_KEY DATABASE_URL REDIS_URL; do
  echo -n "$SECRET: "
  gcloud secrets versions access latest --secret=$SECRET > /dev/null 2>&1 \
    && echo "OK" || echo "FAILED"
done

# Verify service account has secret access
gcloud secrets get-iam-policy DATABASE_URL \
  --filter="bindings.members:${SA_EMAIL}"
```

---

### 13.2 Runtime Issues

#### Issue: Service returns 503 (Service Unavailable)

**Symptoms:**
- Intermittent 503 errors
- Cold start delays

**Solution:**
```bash
# Check instance count
gcloud run services describe study-buddy-api \
  --region=$REGION \
  --format="yaml(status.conditions)"

# Increase min instances to reduce cold starts
gcloud run services update study-buddy-api \
  --region=$REGION \
  --min-instances=1

# Check health endpoint
curl -v "${API_URL}/"
```

#### Issue: Cannot connect to Cloud SQL

**Symptoms:**
- Database connection errors in logs
- "Connection refused" or timeout errors

**Solution:**
```bash
# Verify Cloud SQL instance is running
gcloud sql instances describe $SQL_INSTANCE \
  --format="value(state)"
# Expected: RUNNABLE

# Verify Cloud SQL is attached to service
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(spec.template.metadata.annotations)" | grep cloudsql

# Test connection string format
echo "Connection Name: ${SQL_CONNECTION}"
# Format: PROJECT_ID:REGION:INSTANCE_NAME

# Check DATABASE_URL secret
gcloud secrets versions access latest --secret=DATABASE_URL | head -c 50
# Should start with: postgresql+pg8000://
```

#### Issue: Cannot connect to Redis (Memorystore)

**Symptoms:**
- Redis connection timeout
- Worker not processing jobs

**Solution:**
```bash
# Verify Redis instance is running
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="table(name,state,host,port)"
# Expected: READY state

# Verify VPC connector is attached
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="yaml(spec.template.metadata.annotations)" | grep vpc

# Verify Redis is in same network as VPC connector
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="value(authorizedNetwork)"
# Should be: projects/PROJECT_ID/global/networks/default

# Check VPC connector status
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION \
  --format="value(state)"
# Expected: READY
```

#### Issue: Secret access errors

**Symptoms:**
- "Permission denied accessing secret" in logs
- Service fails to start

**Solution:**
```bash
# List all secrets and verify they exist
gcloud secrets list --format="table(name)"

# Check service account access to each secret
for SECRET in OPENAI_API_KEY GEMINI_API_KEY PINECONE_API_KEY JWT_SECRET_KEY ENCRYPTION_KEY DATABASE_URL REDIS_URL; do
  echo -n "$SECRET: "
  gcloud secrets get-iam-policy $SECRET \
    --filter="bindings.members:${SA_EMAIL}" \
    --format="value(bindings.role)" 2>/dev/null | head -1 || echo "NO ACCESS"
done

# Re-grant access if needed
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

#### Issue: Worker not processing jobs

**Symptoms:**
- Jobs stay in "pending" state
- No processing logs in worker

**Solution:**
```bash
# Check worker is running with min-instances > 0
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="value(spec.template.spec.containerConcurrency)"

# Check worker logs for Arq startup
gcloud run services logs read study-buddy-worker --region=$REGION \
  --filter="textPayload:Arq OR textPayload:Worker" \
  --limit=20

# Verify worker command is correct
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="yaml(spec.template.spec.containers[0].command,spec.template.spec.containers[0].args)"
# Expected: command: python, args: -m,app.worker_entrypoint

# Check Redis connectivity
gcloud run services logs read study-buddy-worker --region=$REGION \
  --filter="textPayload:Redis" \
  --limit=10
```

#### Issue: High memory usage / OOM errors

**Symptoms:**
- Container killed with OOM
- "Memory limit exceeded" in logs

**Solution:**
```bash
# Increase memory allocation
gcloud run services update study-buddy-api \
  --region=$REGION \
  --memory=4Gi

# Check current memory usage in metrics
echo "https://console.cloud.google.com/run/detail/${REGION}/study-buddy-api/metrics?project=${PROJECT_ID}"

# Review memory-intensive operations in code
# Consider batch processing or streaming for large files
```

---

### 13.3 Debugging Commands Quick Reference

```bash
# ═══════════════════════════════════════════════════════════
# LOGS
# ═══════════════════════════════════════════════════════════

# API logs (last 50)
gcloud run services logs read study-buddy-api --region=$REGION --limit=50

# Worker logs (last 50)
gcloud run services logs read study-buddy-worker --region=$REGION --limit=50

# Stream logs in real-time
gcloud run services logs tail study-buddy-api --region=$REGION

# Error logs only
gcloud run services logs read study-buddy-api --region=$REGION \
  --filter="severity>=ERROR" --limit=20

# Specific time range
gcloud logging read "resource.type=cloud_run_revision AND timestamp>=\"2026-01-12T00:00:00Z\"" \
  --project=$PROJECT_ID --limit=50

# ═══════════════════════════════════════════════════════════
# SERVICE STATUS
# ═══════════════════════════════════════════════════════════

# Service health
gcloud run services describe study-buddy-api --region=$REGION \
  --format="table(status.conditions[].type,status.conditions[].status)"

# Current revisions
gcloud run revisions list --service=study-buddy-api --region=$REGION

# Instance count
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(status.traffic)"

# ═══════════════════════════════════════════════════════════
# INFRASTRUCTURE STATUS
# ═══════════════════════════════════════════════════════════

# Cloud SQL
gcloud sql instances describe $SQL_INSTANCE --format="table(name,state,tier)"

# Redis
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="table(name,state,host,port)"

# VPC Connector
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION --format="table(name,state,network)"

# Secrets
gcloud secrets list --format="table(name,createTime)"

# ═══════════════════════════════════════════════════════════
# CONNECTIVITY TESTS
# ═══════════════════════════════════════════════════════════

# Test API health
curl -s "${API_URL}/" | jq .

# Test API with timeout
curl -m 30 -v "${API_URL}/api/v1/health"

# Check SSL certificate
echo | openssl s_client -connect $(echo $API_URL | sed 's|https://||'):443 2>/dev/null | openssl x509 -noout -dates
```

---

## Phase 14: Security Checklist

### 14.1 Pre-Production Security Audit

#### ✅ Authentication & Authorization

```bash
# [ ] JWT secret is strong (32+ characters)
gcloud secrets versions access latest --secret=JWT_SECRET_KEY 2>/dev/null | wc -c
# Should be > 32

# [ ] API endpoints require authentication where appropriate
# Review: backend/app/api/v1/router.py for auth dependencies

# [ ] Service account follows least privilege
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SA_EMAIL}" \
  --format="table(bindings.role)"
# Should only have: secretmanager.secretAccessor, cloudsql.client, storage.objectAdmin, redis.editor, logging.logWriter
```

#### ✅ Network Security

```bash
# [ ] Cloud SQL uses private IP (no public IP)
gcloud sql instances describe $SQL_INSTANCE \
  --format="value(ipAddresses[].type)"
# Should only show: PRIVATE

# [ ] Redis is only accessible via VPC
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION \
  --format="value(connectMode)"
# Should be: DIRECT_PEERING

# [ ] Worker service is not publicly accessible
gcloud run services describe study-buddy-worker --region=$REGION \
  --format="value(spec.template.metadata.annotations['run.googleapis.com/ingress'])"
# Should be: internal or all (with no-allow-unauthenticated)
```

#### ✅ Secret Management

```bash
# [ ] No secrets in environment variables (use Secret Manager)
gcloud run services describe study-buddy-api --region=$REGION \
  --format="yaml(spec.template.spec.containers[0].env)" | grep -i key
# Should not show any API keys in plain text

# [ ] Secrets have appropriate access controls
for SECRET in OPENAI_API_KEY GEMINI_API_KEY PINECONE_API_KEY JWT_SECRET_KEY; do
  echo "=== $SECRET ==="
  gcloud secrets get-iam-policy $SECRET --format="table(bindings.role,bindings.members)"
done

# [ ] No service account keys exist (use workload identity)
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL
# Should be empty or only system-managed keys
```

#### ✅ Data Protection

```bash
# [ ] GCS bucket has public access prevention
gcloud storage buckets describe gs://$GCS_BUCKET \
  --format="value(iamConfiguration.publicAccessPrevention)"
# Should be: enforced

# [ ] GCS bucket uses uniform access
gcloud storage buckets describe gs://$GCS_BUCKET \
  --format="value(iamConfiguration.uniformBucketLevelAccess.enabled)"
# Should be: True

# [ ] Encryption key for user API keys is set
gcloud secrets versions list ENCRYPTION_KEY --format="table(name,state)"
# Should have at least one ENABLED version
```

### 14.2 Ongoing Security Practices

#### Secret Rotation Schedule

| Secret | Rotation Frequency | Impact of Rotation |
|--------|-------------------|-------------------|
| `OPENAI_API_KEY` | Every 90 days | No downtime |
| `GEMINI_API_KEY` | Every 90 days | No downtime |
| `PINECONE_API_KEY` | Every 90 days | No downtime |
| `JWT_SECRET_KEY` | Every 180 days | Users must re-login |
| `ENCRYPTION_KEY` | Every 365 days | Re-encrypt user keys |
| `DATABASE_URL` | On compromise only | Redeploy services |
| `REDIS_URL` | On compromise only | Redeploy services |

#### Secret Rotation Procedure

```bash
# 1. Add new secret version
echo -n "new-api-key-value" | gcloud secrets versions add OPENAI_API_KEY --data-file=-

# 2. Deploy services to pick up new version (if using :latest)
gcloud run services update study-buddy-api --region=$REGION

# 3. Verify new secret is working (check logs)
gcloud run services logs read study-buddy-api --region=$REGION \
  --filter="textPayload:OPENAI" --limit=5

# 4. Disable old version after verification
gcloud secrets versions list OPENAI_API_KEY
gcloud secrets versions disable OPENAI_API_KEY --version=OLD_VERSION_NUMBER
```

### 14.3 IAM Audit Procedure

```bash
# Monthly IAM audit script
echo "=== Service Account Permissions ==="
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount" \
  --format="table(bindings.members,bindings.role)"

echo ""
echo "=== Service Account Keys (should be empty) ==="
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL

echo ""
echo "=== Secret Access Audit ==="
gcloud logging read "resource.type=audited_resource AND protoPayload.serviceName=secretmanager.googleapis.com" \
  --project=$PROJECT_ID \
  --limit=20 \
  --format="table(timestamp,protoPayload.authenticationInfo.principalEmail,protoPayload.resourceName)"
```

### 14.4 Security Incident Response

#### If API Key is Compromised

```bash
# 1. Immediately rotate the compromised key
echo -n "new-key" | gcloud secrets versions add COMPROMISED_SECRET --data-file=-

# 2. Disable all old versions
gcloud secrets versions list COMPROMISED_SECRET
gcloud secrets versions disable COMPROMISED_SECRET --version=1
gcloud secrets versions disable COMPROMISED_SECRET --version=2

# 3. Redeploy services
gcloud run services update study-buddy-api --region=$REGION
gcloud run services update study-buddy-worker --region=$REGION

# 4. Review access logs for unauthorized usage
gcloud logging read "protoPayload.serviceName=secretmanager.googleapis.com AND resource.labels.secret_id=COMPROMISED_SECRET" \
  --project=$PROJECT_ID \
  --limit=100

# 5. Revoke the old API key in the provider's console
# (OpenAI, Gemini, Pinecone dashboards)
```

#### If Database is Compromised

```bash
# 1. Change database password
gcloud sql users set-password $SQL_USER \
  --instance=$SQL_INSTANCE \
  --password="NEW_SECURE_PASSWORD"

# 2. Update DATABASE_URL secret
export NEW_DATABASE_URL="postgresql+pg8000://${SQL_USER}:NEW_SECURE_PASSWORD@/${SQL_DATABASE}?unix_sock=/cloudsql/${SQL_CONNECTION}/.s.PGSQL.5432"
echo -n "$NEW_DATABASE_URL" | gcloud secrets versions add DATABASE_URL --data-file=-

# 3. Redeploy services
gcloud run services update study-buddy-api --region=$REGION
gcloud run services update study-buddy-worker --region=$REGION

# 4. Review Cloud SQL audit logs
gcloud sql operations list --instance=$SQL_INSTANCE --limit=50
```

---

## 📋 Production Readiness Checklist

### Before Going Live

```bash
# ═══════════════════════════════════════════════════════════
# INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════

# [ ] All services deployed and healthy
gcloud run services list --region=$REGION

# [ ] Cloud SQL running
gcloud sql instances describe $SQL_INSTANCE --format="value(state)"

# [ ] Redis running  
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION --format="value(state)"

# [ ] VPC connector ready
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION --format="value(state)"

# ═══════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════

# [ ] All secrets configured
gcloud secrets list

# [ ] JWT secret is strong
gcloud secrets versions access latest --secret=JWT_SECRET_KEY 2>/dev/null | wc -c

# [ ] No public IP on Cloud SQL
gcloud sql instances describe $SQL_INSTANCE --format="value(ipAddresses[].type)"

# [ ] GCS bucket is private
gcloud storage buckets describe gs://$GCS_BUCKET \
  --format="value(iamConfiguration.publicAccessPrevention)"

# ═══════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════

# [ ] Budget alerts configured
gcloud billing budgets list --billing-account=BILLING_ACCOUNT_ID

# [ ] Log-based metrics created
gcloud logging metrics list

# [ ] Notification channels set up
gcloud alpha monitoring channels list

# ═══════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════

# [ ] API health check passes
curl -s "${API_URL}/" | jq .status

# [ ] Authentication works
curl -s "${API_URL}/api/v1/auth/test" -H "Authorization: Bearer TEST_TOKEN"

# [ ] Worker processing jobs
gcloud run services logs read study-buddy-worker --region=$REGION \
  --filter="textPayload:Completed" --limit=5
```

---

## 📋 Quick Troubleshooting Reference

```bash
# Service not starting?
gcloud run services logs read SERVICE_NAME --region=$REGION --filter="severity>=ERROR" --limit=20

# Secret access issues?
gcloud secrets get-iam-policy SECRET_NAME

# Database connection issues?
gcloud sql instances describe $SQL_INSTANCE --format="value(state)"
gcloud run services describe study-buddy-api --region=$REGION --format="yaml" | grep cloudsql

# Redis connection issues?
gcloud redis instances describe $REDIS_INSTANCE --region=$REGION --format="value(state,host)"
gcloud run services describe study-buddy-api --region=$REGION --format="yaml" | grep vpc

# Build failing?
gcloud builds list --limit=1
gcloud builds log BUILD_ID

# Need to rollback?
gcloud run services update-traffic study-buddy-api --region=$REGION --to-revisions=PREVIOUS_REVISION=100
```

---

## 🎉 Congratulations!

You have completed the full GCP infrastructure setup for Study Buddy. Your deployment includes:

- ✅ **Cloud Run** - API and Worker services
- ✅ **Cloud SQL** - PostgreSQL database
- ✅ **Memorystore** - Redis caching and job queues
- ✅ **Cloud Storage** - File uploads
- ✅ **Secret Manager** - Secure credential storage
- ✅ **Artifact Registry** - Docker image storage
- ✅ **Cloud Build** - CI/CD pipeline
- ✅ **VPC Connector** - Private resource access
- ✅ **Monitoring & Alerts** - Operational visibility

**Total Monthly Cost Estimate:** $105-180/month

For ongoing maintenance, refer back to this documentation as needed, and remember to:
- Rotate secrets quarterly
- Review IAM permissions monthly
- Monitor costs weekly
- Apply security patches as they become available
