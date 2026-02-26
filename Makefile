# AI Calendar Events Manager - Docker Operations

.PHONY: help build up down logs clean test dev prod

# Default target
help:
	@echo "Available commands:"
	@echo "  make dev      - Start development environment"
	@echo "  make prod     - Start production environment" 
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make build    - Build all images"
	@echo "  make logs     - Follow application logs"
	@echo "  make clean    - Clean up containers and volumes"
	@echo "  make test     - Run tests"
	@echo "  make health   - Check service health"
	@echo "  make init     - Initialize environment"

# Initialize environment
init:
	@echo "Setting up environment..."
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env file - please edit with your credentials"; fi
	@mkdir -p logs ssl monitoring/grafana/dashboards monitoring/grafana/datasources
	@echo "Environment initialized!"

# Development environment
dev: init
	@echo "Starting development environment..."
	docker-compose up -d
	@echo "Services started!"
	@echo "Application: http://localhost:8080"
	@echo "API Docs: http://localhost:8080/docs"
	@echo "DynamoDB Admin: http://localhost:8001"

# Production environment
prod: init
	@echo "Starting production environment..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "Production services started!"
	@echo "Application: http://localhost:80"
	@echo "Monitoring: http://localhost:3000"

# Start services with nginx
nginx: init
	@echo "Starting with nginx reverse proxy..."
	docker-compose --profile nginx up -d

# Build all images
build:
	@echo "Building all images..."
	docker-compose build

# Start all services
up: init
	@echo "Starting all services..."
	docker-compose up -d

# Stop all services
down:
	@echo "Stopping all services..."
	docker-compose down

# Follow application logs
logs:
	docker-compose logs -f orion-api

# Check service health
health:
	@echo "Checking service health..."
	@docker-compose ps
	@echo ""
	@echo "Testing API health endpoint..."
	@curl -s http://localhost:8080/health | jq . || echo "API not responding"

# Run tests
test:
	@echo "Running tests..."
	docker-compose exec orion-api python -m pytest tests/ -v

# Clean up everything
clean:
	@echo "Cleaning up containers, images, and volumes..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

# Database operations
db-reset:
	@echo "Resetting database..."
	docker-compose stop db-init dynamodb-local
	docker volume rm orion_dynamodb-data || true
	docker-compose up -d dynamodb-local
	sleep 5
	docker-compose up db-init

# Development helpers
shell:
	docker-compose exec orion-api bash

db-shell:
	@echo "Opening DynamoDB admin interface..."
	@echo "Visit: http://localhost:8001"

# Backup and restore
backup:
	@echo "Creating backup..."
	@mkdir -p backups
	docker run --rm -v orion_dynamodb-data:/data -v $(PWD)/backups:/backup ubuntu tar czf /backup/dynamodb-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz /data
	@echo "Backup created in backups/ directory"

restore:
	@echo "Available backups:"
	@ls -la backups/dynamodb-backup-*.tar.gz 2>/dev/null || echo "No backups found"
	@echo "To restore: make restore-file BACKUP_FILE=backups/dynamodb-backup-YYYYMMDD-HHMMSS.tar.gz"

restore-file:
	@if [ -z "$(BACKUP_FILE)" ]; then echo "Please specify BACKUP_FILE"; exit 1; fi
	@echo "Restoring from $(BACKUP_FILE)..."
	docker-compose stop dynamodb-local
	docker volume rm orion_dynamodb-data || true
	docker volume create orion_dynamodb-data
	docker run --rm -v orion_dynamodb-data:/data -v $(PWD):/backup ubuntu tar xzf /backup/$(BACKUP_FILE) -C /
	docker-compose up -d dynamodb-local
	@echo "Restore completed"

# Monitoring
monitor:
	@echo "Starting monitoring stack..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d prometheus grafana
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/admin)"

# Update dependencies
update:
	@echo "Updating dependencies..."
	docker-compose pull
	docker-compose build --pull

# Security scan
security-scan:
	@echo "Running security scan..."
	docker run --rm -v $(PWD):/code clair/clair:latest || echo "Clair not available, skipping security scan"