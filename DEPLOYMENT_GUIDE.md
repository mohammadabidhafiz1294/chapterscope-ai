# EduQuantum Predictor - Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the EduQuantum Predictor system in various environments.

## Prerequisites

### System Requirements
- Python 3.8+
- PostgreSQL 12+ or MySQL 8+
- 4GB RAM minimum, 8GB recommended
- 10GB storage space
- Linux/Windows/macOS

### Dependencies
- Django 4.2+
- Qiskit 0.44+
- Google Gemini API access
- Redis (optional, for caching)

## Quick Start Deployment

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/your-org/eduquantum-predictor.git
cd eduquantum-predictor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Configuration

#### PostgreSQL Setup
```bash
# Install PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE eduquantum_db;
CREATE USER eduquantum_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE eduquantum_db TO eduquantum_user;
\q
```

#### MySQL Setup
```bash
# Install MySQL
sudo apt-get install mysql-server

# Secure installation
sudo mysql_secure_installation

# Create database and user
mysql -u root -p
CREATE DATABASE eduquantum_db;
CREATE USER 'eduquantum_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON eduquantum_db.* TO 'eduquantum_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 3. Configuration

Create `.env` file in the project root:

```env
# Database Configuration
DATABASE_URL=postgresql://eduquantum_user:your_password@localhost:5432/eduquantum_db
# Or for MySQL:
# DATABASE_URL=mysql://eduquantum_user:your_password@localhost:3306/eduquantum_db

# Security
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# AI Services
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-1.5-pro

# Quantum Computing
QISKIT_IBMQ_TOKEN=your-ibmq-token  # Optional

# Email Configuration (Optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True

# File Upload
MEDIA_ROOT=/var/www/eduquantum/media
STATIC_ROOT=/var/www/eduquantum/static

# Redis (Optional)
REDIS_URL=redis://localhost:6379/0
```

### 4. Database Migration

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 5. Static Files

```bash
# Collect static files
python manage.py collectstatic --noinput
```

### 6. Start Server

```bash
# Development server
python manage.py runserver

# Production server (using gunicorn)
gunicorn eduquantum_predictor.wsgi:application --bind 0.0.0.0:8000
```

## Docker Deployment

### Docker Compose Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: eduquantum_db
      POSTGRES_USER: eduquantum_user
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  web:
    build: .
    command: gunicorn eduquantum_predictor.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - .:/code
      - static_volume:/code/static
      - media_volume:/code/media
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=postgresql://eduquantum_user:your_password@db:5432/eduquantum_db
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=your-secret-key
      - GEMINI_API_KEY=your-gemini-key

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - static_volume:/code/static
      - media_volume:/code/media
    depends_on:
      - web

volumes:
  postgres_data:
  static_volume:
  media_volume:
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /code/

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /code
USER app

# Run the application
CMD ["gunicorn", "eduquantum_predictor.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Nginx Configuration

Create `nginx.conf`:

```nginx
upstream eduquantum_app {
    server web:8000;
}

server {
    listen 80;
    server_name localhost;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /code/static/;
    }

    location /media/ {
        alias /code/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://eduquantum_app;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
    }
}
```

### Docker Deployment Commands

```bash
# Build and start services
docker-compose up --build -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# View logs
docker-compose logs -f web
```

## Production Deployment

### Using Gunicorn and Nginx

#### Gunicorn Configuration

Create `gunicorn.conf.py`:

```python
import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2
user = "www-data"
group = "www-data"
tmp_upload_dir = None
```

#### Systemd Service

Create `/etc/systemd/system/eduquantum.service`:

```ini
[Unit]
Description=EduQuantum Predictor
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/eduquantum
Environment="PATH=/var/www/eduquantum/venv/bin"
ExecStart=/var/www/eduquantum/venv/bin/gunicorn --config gunicorn.conf.py eduquantum_predictor.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

#### Nginx Site Configuration

Create `/etc/nginx/sites-available/eduquantum`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/eduquantum/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /var/www/eduquantum/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

### SSL Configuration (Let's Encrypt)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Test renewal
sudo certbot renew --dry-run
```

## Cloud Deployment

### AWS EC2 Deployment

#### EC2 Instance Setup
```bash
# Update system
sudo yum update -y

# Install required packages
sudo yum install -y python3 python3-pip postgresql postgresql-server nginx git

# Configure PostgreSQL
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Clone repository
git clone https://github.com/your-org/eduquantum-predictor.git
cd eduquantum-predictor

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### AWS RDS Database
```bash
# Install AWS CLI
pip install awscli

# Configure AWS CLI
aws configure

# Create RDS instance via AWS Console or CLI
aws rds create-db-instance \
    --db-instance-identifier eduquantum-db \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --master-username eduquantum_user \
    --master-user-password your_password \
    --allocated-storage 20
```

### Heroku Deployment

#### Heroku CLI Setup
```bash
# Install Heroku CLI
npm install -g heroku

# Login to Heroku
heroku login

# Create Heroku app
heroku create eduquantum-predictor

# Add PostgreSQL addon
heroku addons:create heroku-postgresql:hobby-dev

# Set environment variables
heroku config:set SECRET_KEY=your-secret-key
heroku config:set GEMINI_API_KEY=your-gemini-key
heroku config:set DEBUG=False

# Deploy
git push heroku main

# Run migrations
heroku run python manage.py migrate

# Create superuser
heroku run python manage.py createsuperuser
```

Create `Procfile` for Heroku:

```
web: gunicorn eduquantum_predictor.wsgi:application --log-file -
```

Create `runtime.txt`:

```
python-3.11.6
```

## Monitoring and Maintenance

### Health Checks

Create health check endpoint in Django:

```python
# views.py
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    try:
        # Check database connection
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()

        return JsonResponse({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=500)
```

Add to `urls.py`:

```python
path('health/', health_check, name='health_check'),
```

### Log Configuration

Create `logging.conf`:

```ini
[loggers]
keys=root,eduquantum

[handlers]
keys=console,file

[formatters]
keys=verbose,simple

[logger_root]
level=INFO
handlers=console,file

[logger_eduquantum]
level=DEBUG
handlers=console,file
qualname=eduquantum_predictor
propagate=0

[handler_console]
class=StreamHandler
level=INFO
formatter=simple
args=(sys.stdout,)

[handler_file]
class=FileHandler
level=DEBUG
formatter=verbose
args=('/var/log/eduquantum/eduquantum.log',)

[formatter_verbose]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s

[formatter_simple]
format=%(levelname)s - %(message)s
```

### Backup Strategy

#### Database Backup Script

```bash
#!/bin/bash
# backup_db.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/eduquantum"
BACKUP_FILE="$BACKUP_DIR/db_backup_$DATE.sql"

mkdir -p $BACKUP_DIR

pg_dump -U eduquantum_user -h localhost eduquantum_db > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Keep only last 7 days
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +7 -delete

echo "Database backup completed: $BACKUP_FILE.gz"
```

#### Automated Backup with Cron

```bash
# Add to crontab (crontab -e)
0 2 * * * /path/to/backup_db.sh
```

## Troubleshooting

### Common Issues

#### Database Connection Issues
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection
psql -U eduquantum_user -d eduquantum_db -h localhost

# Reset database
python manage.py reset_db
python manage.py migrate
```

#### Static Files Not Loading
```bash
# Check permissions
sudo chown -R www-data:www-data /var/www/eduquantum/static/
sudo chown -R www-data:www-data /var/www/eduquantum/media/

# Collect static files
python manage.py collectstatic --noinput
```

#### Memory Issues
```bash
# Check memory usage
free -h

# Monitor processes
ps aux --sort=-%mem | head

# Increase swap space if needed
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### Performance Optimization

```python
# settings.py - Performance settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}

# Use database indexes
# models.py
class Topic(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    frequency = models.FloatField(db_index=True)

# Enable compression
MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    # ... other middleware
]
```

## Security Checklist

- [ ] Change default SECRET_KEY
- [ ] Set DEBUG=False in production
- [ ] Use HTTPS with SSL certificate
- [ ] Configure ALLOWED_HOSTS
- [ ] Set secure cookies (SESSION_COOKIE_SECURE=True)
- [ ] Use strong passwords for database
- [ ] Regularly update dependencies
- [ ] Implement rate limiting
- [ ] Set up firewall rules
- [ ] Enable database backups
- [ ] Monitor logs for security issues

## Support

For deployment support:
- Check the logs: `tail -f /var/log/eduquantum/eduquantum.log`
- Health check: Visit `/health/` endpoint
- Database status: Check PostgreSQL/MySQL logs
- Performance monitoring: Use Django Debug Toolbar in development

## Version History

### v1.0.0
- Initial production deployment
- Docker containerization
- PostgreSQL/MySQL support
- Nginx configuration
- SSL support
- Monitoring and health checks
