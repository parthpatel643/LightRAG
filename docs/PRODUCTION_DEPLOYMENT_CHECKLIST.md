# Production Deployment Checklist

**Document Version:** 1.0  
**Last Updated:** 2026-03-05  
**Target:** AWS Production Deployment with Rollback Procedures

---

## Pre-Deployment Checklist

### Infrastructure Verification

- [ ] **AWS Services Provisioned**
  - [ ] Neptune cluster running (primary + replica)
  - [ ] DocumentDB cluster running
  - [ ] Milvus deployed on ECS/EC2
  - [ ] Redis ElastiCache cluster active
  - [ ] S3 buckets created (backups, logs)
  - [ ] CloudWatch log groups created

- [ ] **Network Configuration**
  - [ ] VPC and subnets configured
  - [ ] Security groups allow required traffic
  - [ ] NAT gateway for private subnets
  - [ ] VPC endpoints for AWS services
  - [ ] Load balancer configured
  - [ ] DNS records updated

- [ ] **IAM Permissions**
  - [ ] ECS task role created with required permissions
  - [ ] Neptune access policy attached
  - [ ] DocumentDB access policy attached
  - [ ] S3 access policy attached
  - [ ] CloudWatch access policy attached
  - [ ] Secrets Manager access (if used)

### Application Configuration

- [ ] **Environment Variables**
  - [ ] Copied `.env.production.template` to `.env`
  - [ ] Updated all placeholder values
  - [ ] Verified AWS endpoints
  - [ ] Set secure passwords and API keys
  - [ ] Configured SSL certificates
  - [ ] Set appropriate concurrency limits

- [ ] **Security Configuration**
  - [ ] Changed default admin password
  - [ ] Generated secure TOKEN_SECRET (256-bit)
  - [ ] Generated secure LIGHTRAG_API_KEY
  - [ ] Configured rate limiting
  - [ ] Enabled audit logging
  - [ ] Configured CORS origins

- [ ] **Monitoring Setup**
  - [ ] CloudWatch log groups created
  - [ ] CloudWatch alarms configured
  - [ ] SNS topics for alerts created
  - [ ] Metrics dashboards created
  - [ ] Log retention policies set

### Data Preparation

- [ ] **Backup Current System**
  - [ ] Created full backup of JSON storage
  - [ ] Uploaded backup to S3
  - [ ] Documented current data counts
  - [ ] Tested backup restoration

- [ ] **Migration Scripts Ready**
  - [ ] Export scripts tested
  - [ ] Import scripts tested
  - [ ] Validation scripts ready
  - [ ] Rollback scripts prepared

---

## Deployment Steps

### Phase 1: Initial Deployment (Day 1)

#### Step 1: Deploy Infrastructure (2-3 hours)

```bash
# 1.1 Deploy AWS services
cd k8s-deploy/databases
./00-config.sh
./01-prepare.sh
./02-install-database.sh

# 1.2 Verify services
kubectl get pods -n lightrag-databases
aws neptune describe-db-clusters --db-cluster-identifier lightrag-neptune-cluster
aws docdb describe-db-clusters --db-cluster-identifier lightrag-docdb-cluster

# 1.3 Test connectivity
python test_aws_connections.py
```

**Verification:**
- [ ] All pods running
- [ ] All AWS services healthy
- [ ] Connection tests pass

**Rollback:** If failed, delete resources and retry
```bash
./03-uninstall-database.sh
./04-cleanup.sh
```

#### Step 2: Deploy Application (1-2 hours)

```bash
# 2.1 Build Docker image
docker build -t lightrag:production -f Dockerfile .

# 2.2 Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag lightrag:production ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lightrag:production
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lightrag:production

# 2.3 Deploy to ECS
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --force-new-deployment

# 2.4 Wait for deployment
aws ecs wait services-stable --cluster lightrag-cluster --services lightrag-api
```

**Verification:**
- [ ] Docker image built successfully
- [ ] Image pushed to ECR
- [ ] ECS tasks running
- [ ] Health check passing

**Rollback:** Revert to previous task definition
```bash
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --task-definition lightrag-api:PREVIOUS_VERSION
```

#### Step 3: Smoke Tests (30 minutes)

```bash
# 3.1 Health check
curl https://api.your-domain.com/health

# 3.2 Authentication test
curl -X POST https://api.your-domain.com/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# 3.3 Query test
curl -X POST https://api.your-domain.com/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"test query","mode":"hybrid"}'

# 3.4 Document upload test
curl -X POST https://api.your-domain.com/documents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test.txt"
```

**Verification:**
- [ ] Health endpoint returns 200
- [ ] Authentication works
- [ ] Query returns results
- [ ] Document upload succeeds

**Rollback:** If smoke tests fail, investigate logs
```bash
aws logs tail /aws/lightrag/api --follow
```

### Phase 2: Data Migration (Days 2-8)

#### Step 4: Export Data (2-3 days)

```bash
# 4.1 Export KV store
python export_kv_store.py

# 4.2 Export document status
python export_doc_status.py

# 4.3 Export graph data
python export_graph_data.py

# 4.4 Export vector data
python export_vector_data.py

# 4.5 Upload to S3
aws s3 sync /backup/migration/ s3://lightrag-backups/migration/
```

**Verification:**
- [ ] All export scripts completed
- [ ] Export files created
- [ ] Data counts match source
- [ ] Files uploaded to S3

**Rollback:** Re-run failed exports
```bash
python export_COMPONENT.py --retry
```

#### Step 5: Import Data (3-5 days)

```bash
# 5.1 Import to DocumentDB
python import_to_documentdb.py

# 5.2 Import to Neptune
python import_to_neptune.py

# 5.3 Import to Milvus
python import_to_milvus.py

# 5.4 Validate import
python validate_migration.py
```

**Verification:**
- [ ] All import scripts completed
- [ ] Data counts match exports
- [ ] Validation passes
- [ ] No errors in logs

**Rollback:** Clear and re-import
```bash
python clear_aws_storage.py --component COMPONENT
python import_to_COMPONENT.py --retry
```

### Phase 3: Parallel Run (Weeks 2-3)

#### Step 6: Enable Dual-Write (1 day)

```bash
# 6.1 Update configuration
cat >> .env << 'EOF'
MIGRATION_MODE=parallel
MIGRATION_WRITE_TO_BOTH=true
MIGRATION_READ_FROM=json
EOF

# 6.2 Restart services
systemctl restart lightrag-api

# 6.3 Monitor for 24 hours
watch -n 60 'python check_data_consistency.py'
```

**Verification:**
- [ ] Writes going to both systems
- [ ] No errors in logs
- [ ] Data consistency maintained
- [ ] Performance acceptable

**Rollback:** Disable dual-write
```bash
MIGRATION_MODE=readonly
systemctl restart lightrag-api
```

#### Step 7: Gradual Traffic Shift (1-2 weeks)

```bash
# Week 1: 10% traffic to AWS
MIGRATION_READ_FROM=aws
MIGRATION_READ_PERCENTAGE=10

# Week 2: 50% traffic to AWS
MIGRATION_READ_PERCENTAGE=50

# Week 3: 100% traffic to AWS
MIGRATION_READ_PERCENTAGE=100
```

**Verification:**
- [ ] Error rates stable
- [ ] Response times acceptable
- [ ] No data inconsistencies
- [ ] User feedback positive

**Rollback:** Reduce traffic percentage
```bash
MIGRATION_READ_PERCENTAGE=0  # Back to JSON
```

### Phase 4: Cutover (Day 1)

#### Step 8: Final Cutover (4 hours)

```bash
# 8.1 Announce maintenance window
echo "Maintenance window: $(date) - $(date -d '+4 hours')"

# 8.2 Stop writes to JSON
MIGRATION_MODE=readonly
systemctl restart lightrag-api

# 8.3 Final data sync
python sync_final_changes.py

# 8.4 Switch to AWS
cat >> .env << 'EOF'
LIGHTRAG_KV_STORAGE=MongoKVStorage
LIGHTRAG_DOC_STATUS_STORAGE=MongoDocStatusStorage
LIGHTRAG_GRAPH_STORAGE=NeptuneGraphStorage
LIGHTRAG_VECTOR_STORAGE=MilvusVectorDBStorage
EOF

# 8.5 Restart services
systemctl restart lightrag-api

# 8.6 Verify health
curl https://api.your-domain.com/health

# 8.7 Run comprehensive tests
python comprehensive_tests.py
```

**Verification:**
- [ ] All services healthy
- [ ] All tests passing
- [ ] Monitoring active
- [ ] No errors in logs

**Rollback:** Emergency rollback procedure (see below)

---

## Rollback Procedures

### Level 1: Immediate Rollback (< 15 minutes)

**Trigger:** Critical failure, data corruption, or service unavailable

```bash
# 1. Stop current deployment
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --desired-count 0

# 2. Revert to previous task definition
aws ecs update-service \
  --cluster lightrag-cluster \
  --service lightrag-api \
  --task-definition lightrag-api:PREVIOUS_VERSION \
  --desired-count 3

# 3. Verify rollback
aws ecs wait services-stable --cluster lightrag-cluster --services lightrag-api
curl https://api.your-domain.com/health

# 4. Notify team
echo "ROLLBACK EXECUTED: $(date)" | mail -s "LightRAG Rollback" team@company.com
```

**Post-Rollback:**
- [ ] Verify service restored
- [ ] Check data integrity
- [ ] Review logs for root cause
- [ ] Document incident

### Level 2: Configuration Rollback (< 30 minutes)

**Trigger:** Configuration issues, performance degradation

```bash
# 1. Restore previous configuration
cp .env.backup .env

# 2. Restart services
systemctl restart lightrag-api

# 3. Verify functionality
python smoke_tests.py

# 4. Monitor for 1 hour
watch -n 60 'curl -s https://api.your-domain.com/health | jq'
```

**Post-Rollback:**
- [ ] Configuration restored
- [ ] Services stable
- [ ] Performance normal
- [ ] Root cause identified

### Level 3: Data Rollback (< 2 hours)

**Trigger:** Data inconsistency, corruption detected

```bash
# 1. Stop all writes
MIGRATION_MODE=readonly
systemctl restart lightrag-api

# 2. Restore from backup
aws s3 sync s3://lightrag-backups/pre-migration/ /restore/

# 3. Clear AWS storage
python clear_aws_storage.py --all

# 4. Re-import from backup
python import_from_backup.py --source /restore/

# 5. Validate data
python validate_migration.py

# 6. Resume operations
MIGRATION_MODE=normal
systemctl restart lightrag-api
```

**Post-Rollback:**
- [ ] Data restored
- [ ] Validation passed
- [ ] Services operational
- [ ] Incident documented

### Level 4: Full Rollback (< 4 hours)

**Trigger:** Complete system failure, unrecoverable state

```bash
# 1. Stop all services
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --desired-count 0

# 2. Restore JSON storage
aws s3 sync s3://lightrag-backups/pre-migration/ /path/to/rag_storage/

# 3. Revert to JSON configuration
cp .env.pre-migration .env

# 4. Deploy previous version
aws ecs update-service \
  --cluster lightrag-cluster \
  --service lightrag-api \
  --task-definition lightrag-api:PRE_MIGRATION_VERSION \
  --desired-count 3

# 5. Verify complete restoration
python comprehensive_tests.py

# 6. Notify stakeholders
echo "FULL ROLLBACK EXECUTED: $(date)" | mail -s "LightRAG Full Rollback" stakeholders@company.com
```

**Post-Rollback:**
- [ ] System fully restored
- [ ] All tests passing
- [ ] Users notified
- [ ] Post-mortem scheduled

---

## Post-Deployment Verification

### Day 1: Immediate Verification

```bash
# Health checks
curl https://api.your-domain.com/health

# Performance tests
python benchmark_production.py

# Error rate check
aws logs filter-pattern /aws/lightrag/api --filter-pattern "ERROR" --start-time -1h

# User acceptance testing
python user_acceptance_tests.py
```

**Checklist:**
- [ ] All health checks passing
- [ ] Response times < 500ms (p95)
- [ ] Error rate < 0.1%
- [ ] User tests passing

### Week 1: Monitoring

```bash
# Daily checks
- [ ] Review CloudWatch dashboards
- [ ] Check error logs
- [ ] Monitor resource utilization
- [ ] Review slow query logs
- [ ] Check backup completion

# Weekly review
- [ ] Performance trends
- [ ] Cost analysis
- [ ] User feedback
- [ ] Optimization opportunities
```

### Week 2-4: Optimization

```bash
# Performance tuning
- [ ] Analyze slow queries
- [ ] Optimize indexes
- [ ] Tune connection pools
- [ ] Adjust cache settings

# Cost optimization
- [ ] Review resource utilization
- [ ] Right-size instances
- [ ] Optimize storage
- [ ] Review data retention
```

---

## Emergency Contacts

| Role | Name | Contact | Availability |
|------|------|---------|--------------|
| **Deployment Lead** | [Name] | [Email/Phone] | 24/7 during deployment |
| **AWS Admin** | [Name] | [Email/Phone] | On-call |
| **Database Admin** | [Name] | [Email/Phone] | On-call |
| **Security Lead** | [Name] | [Email/Phone] | Business hours |
| **Product Owner** | [Name] | [Email/Phone] | Business hours |

---

## Success Criteria

### Technical Metrics
- [ ] All services healthy (100% uptime)
- [ ] Query response time < 500ms (p95)
- [ ] Error rate < 0.1%
- [ ] Data consistency 100%
- [ ] All monitoring active
- [ ] Backups completing successfully

### Business Metrics
- [ ] Zero data loss
- [ ] No user-reported issues
- [ ] Performance meets SLA
- [ ] Cost within budget
- [ ] Team trained on new system

---

## Documentation Updates

Post-deployment documentation tasks:

- [ ] Update architecture diagrams
- [ ] Document configuration changes
- [ ] Update runbooks
- [ ] Create troubleshooting guides
- [ ] Update API documentation
- [ ] Document lessons learned

---

## Decommissioning Old System

**Timeline:** 30 days after successful cutover

```bash
# Week 1-2: Monitor new system
# Week 3: Archive JSON storage
tar -czf json-storage-archive-$(date +%Y%m%d).tar.gz /path/to/rag_storage/
aws s3 cp json-storage-archive-*.tar.gz s3://lightrag-archives/

# Week 4: Decommission old infrastructure
# - Stop old services
# - Remove old EC2 instances
# - Delete old storage (after final backup)

# Week 5+: Keep archives for 1 year
```

---

## Appendix: Quick Reference

### Common Commands

```bash
# Check service status
aws ecs describe-services --cluster lightrag-cluster --services lightrag-api

# View logs
aws logs tail /aws/lightrag/api --follow

# Check metrics
aws cloudwatch get-metric-statistics --namespace LightRAG/Production --metric-name QueryLatency

# Restart service
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --force-new-deployment

# Scale service
aws ecs update-service --cluster lightrag-cluster --service lightrag-api --desired-count 5
```

### Troubleshooting Quick Links

- [Architecture Bottlenecks](./ARCHITECTURE_BOTTLENECKS.md)
- [Neptune Configuration](./AWS_NEPTUNE_CONFIGURATION.md)
- [Migration Strategy](./AWS_MIGRATION_STRATEGY.md)
- [Production .env Template](../.env.production.template)

---

**Document Status:** ✅ Complete  
**Last Review:** 2026-03-05  
**Next Review:** After deployment completion