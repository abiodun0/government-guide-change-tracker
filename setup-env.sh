#!/bin/bash

# Setup script to create .env file if it doesn't exist

if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cat > .env << 'EOF'
# Django Settings
SECRET_KEY=django-insecure-change-this-in-production-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database Settings
DB_NAME=government_guide_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=db
DB_PORT=5432

# Redis Settings
REDIS_PORT=6379

# Web Server Settings
WEB_PORT=8000
EOF
    echo ".env file created successfully!"
else
    echo ".env file already exists. Skipping creation."
fi

