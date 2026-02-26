# Docker Setup for AI Calendar Events Manager

This document explains how to run the AI Calendar Events Manager using Docker Compose with all dependencies.

## Prerequisites

- Docker Engine 20.10+ 
- Docker Compose 2.0+
- Git

## Quick Start

1. **Clone the repository and setup environment:**
   ```bash
   git clone <repository-url>
   cd orion
   cp .env.example .env
   ```

2. **Edit the `.env` file with your credentials:**
   ```bash
   # Required: Set your Google OAuth credentials
   GOOGLE_CLIENT_ID_IOS=your-ios-client-id.googleusercontent.com
   GOOGLE_CLIENT_ID_ANDROID=your-android-client-id.googleusercontent.com
   
   # Required: Set your Gemini API key
   GEMINI_API_KEY=your-gemini-api-key-here
   
   # Generate a secure encryption key (32 bytes = 64 hex chars)
   ENCRYPTION_KEY_HEX=$(openssl rand -hex 32)
   
   # Generate a secure JWT secret
   JWT_SECRET_KEY=$(openssl rand -base64 32)
   ```

3. **Start all services:**
   ```bash
   docker-compose up -d
   ```

4. **Check service status:**
   ```bash
   docker-compose ps
   ```

5. **View logs:**
   ```bash
   docker-compose logs -f orion-api
   ```

## Available Services

### Core Services

| Service | Port | Description |
|---------|------|-------------|
| `orion-api` | 8080 | Main FastAPI application |
| `dynamodb-local` | 8000 | Local DynamoDB instance |
| `dynamodb-admin` | 8001 | DynamoDB web admin interface |

### Optional Services

| Service | Port | Description | How to Enable |
|---------|------|-------------|---------------|
| `nginx` | 80/443 | Reverse proxy with load balancing | `docker-compose --profile nginx up` |

## Service Details

### Main Application (`orion-api`)
- **URL**: http://localhost:8080
- **Health Check**: http://localhost:8080/health
- **API Documentation**: http://localhost:8080/docs
- **Features**:
  - Auto-reload in development mode
  - Health checks
  - Comprehensive logging
  - Environment-based configuration

### DynamoDB Local (`dynamodb-local`)
- **URL**: http://localhost:8000
- **Purpose**: Local DynamoDB instance for development
- **Data Persistence**: Stored in Docker volume `dynamodb-data`
- **Tables**: Automatically created by `db-init` service

### DynamoDB Admin (`dynamodb-admin`)
- **URL**: http://localhost:8001
- **Purpose**: Web interface to view and manage DynamoDB tables
- **Features**:
  - Browse tables and data
  - Execute queries
  - Monitor table metrics

### Database Initialization (`db-init`)
- **Purpose**: Creates all required DynamoDB tables
- **Runs**: Once at startup
- **Tables Created**:
  - UserGoogleTokens
  - ChatSessions
  - UserPreferences
  - UserTasks
  - UserEmailMapping
  - ToolExecutionResults

## Docker Compose Commands

### Basic Operations
```bash
# Start all services
docker-compose up -d

# Start with nginx reverse proxy
docker-compose --profile nginx up -d

# Stop all services
docker-compose down

# Stop and remove volumes (deletes data)
docker-compose down -v

# View service logs
docker-compose logs -f [service-name]

# Restart a specific service
docker-compose restart orion-api

# Rebuild and restart
docker-compose up -d --build
```

### Development Commands
```bash
# Follow application logs
docker-compose logs -f orion-api

# Execute commands in running container
docker-compose exec orion-api bash

# Run database migrations manually
docker-compose exec orion-api python -c "from db import create_all_tables; create_all_tables()"

# Check service health
docker-compose ps
```

### Debugging Commands
```bash
# Debug database connection
docker-compose exec orion-api python -c "from db import get_dynamodb_resource; print(get_dynamodb_resource().tables.all())"

# Check environment variables
docker-compose exec orion-api env | grep -E "(DYNAMO|AWS|GOOGLE|GEMINI)"

# Test API endpoints
curl http://localhost:8080/health
```

## Configuration

### Environment Variables

All configuration is handled through environment variables. See `.env.example` for required variables.

#### Required for Production:
- `GOOGLE_CLIENT_ID_IOS` - Google OAuth client ID for iOS
- `GOOGLE_CLIENT_ID_ANDROID` - Google OAuth client ID for Android  
- `GEMINI_API_KEY` - Google Gemini AI API key
- `ENCRYPTION_KEY_HEX` - 32-byte encryption key (64 hex characters)
- `JWT_SECRET_KEY` - Secret key for JWT tokens

#### Development Defaults:
- Local DynamoDB endpoint is automatically configured
- Dummy AWS credentials are used for local DynamoDB
- Development JWT secret (change for production)

### Security Notes

⚠️ **Important for Production:**

1. **Generate secure secrets:**
   ```bash
   # Generate encryption key
   openssl rand -hex 32
   
   # Generate JWT secret  
   openssl rand -base64 32
   ```

2. **Use proper AWS credentials** when deploying to production
3. **Enable HTTPS** by configuring SSL certificates in nginx
4. **Restrict CORS origins** in production environment
5. **Use secrets management** (AWS Secrets Manager, etc.) for sensitive data

## Monitoring and Health Checks

### Health Check Endpoints
- **Application**: `GET /health`
- **DynamoDB**: Automatic container health checks
- **Nginx**: Proxies health checks to application

### Logging
- **Application logs**: `docker-compose logs orion-api`
- **DynamoDB logs**: `docker-compose logs dynamodb-local`
- **Nginx logs**: `docker-compose logs nginx` (when enabled)

### Metrics
- Container metrics: `docker stats`
- Service status: `docker-compose ps`

## Troubleshooting

### Common Issues

1. **Port conflicts:**
   ```bash
   # Check what's using the port
   lsof -i :8080
   
   # Change ports in docker-compose.yml if needed
   ```

2. **DynamoDB connection issues:**
   ```bash
   # Check if DynamoDB is running
   docker-compose logs dynamodb-local
   
   # Test connection
   curl http://localhost:8000/
   ```

3. **Environment variables not loaded:**
   ```bash
   # Verify .env file exists and has correct format
   cat .env
   
   # Restart services to reload environment
   docker-compose down && docker-compose up -d
   ```

4. **Application won't start:**
   ```bash
   # Check application logs
   docker-compose logs orion-api
   
   # Rebuild container
   docker-compose build orion-api
   ```

### Performance Tuning

1. **Increase memory limits:**
   ```yaml
   # In docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 1G
       reservations:
         memory: 512M
   ```

2. **Adjust worker processes:**
   ```bash
   # For production, use gunicorn instead of uvicorn
   CMD ["gunicorn", "boot:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
   ```

## Production Deployment

### AWS ECS/Fargate
1. Push images to ECR
2. Create ECS task definition
3. Configure ALB for load balancing
4. Use RDS/DynamoDB instead of local instances

### Docker Swarm
1. Convert compose file to stack format
2. Deploy with `docker stack deploy`
3. Configure secrets and configs

### Kubernetes
1. Convert services to Kubernetes manifests
2. Use Helm charts for deployment
3. Configure ingress and services

## Development Workflow

1. **Make code changes** in the `app/` directory
2. **Changes auto-reload** (development mode)
3. **Test endpoints** using `/docs` or curl
4. **Check logs** with `docker-compose logs -f orion-api`
5. **Debug database** using DynamoDB Admin at port 8001

## Backup and Restore

### DynamoDB Data
```bash
# Backup (using AWS CLI with local endpoint)
aws dynamodb scan --table-name UserPreferences --endpoint-url http://localhost:8000

# Export data volume
docker run --rm -v orion_dynamodb-data:/data -v $(pwd):/backup ubuntu tar czf /backup/backup.tar.gz /data
```

### Restore Data
```bash
# Import data volume
docker run --rm -v orion_dynamodb-data:/data -v $(pwd):/backup ubuntu tar xzf /backup/backup.tar.gz -C /
```