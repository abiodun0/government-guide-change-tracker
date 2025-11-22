# Government Guide Change Tracker

A minimal Django application with Docker Compose, PostgreSQL, Redis, and Celery.

## Prerequisites

- Docker
- Docker Compose

## Setup

1. **REQUIRED**: Create the `.env` file before starting services:
   ```bash
   ./setup-env.sh
   ```
   Or manually create a `.env` file with the following variables:
   ```bash
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
   ```
   
   **Important**: Update the `.env` file with your configuration:
   - `SECRET_KEY`: Django secret key (change in production!)
   - `DEBUG`: Set to `False` in production
   - `DB_PASSWORD`: Database password
   - Other settings as needed

2. Build and start the services:
   ```bash
   docker-compose up --build
   ```
   
   The entrypoint script will automatically:
   - Wait for PostgreSQL to be ready
   - Create the database if it doesn't exist
   - Run Django migrations

3. Create a superuser (optional):
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

## Services

- **Web**: Django application running on http://localhost:8000
- **PostgreSQL**: Database on port 5432
- **Redis**: Cache and message broker on port 6379
- **Celery**: Background task worker

## Usage

- Access the Django admin at: http://localhost:8000/admin/
- The Celery worker will process background tasks automatically

## Development

To run Django commands:
```bash
docker-compose exec web python manage.py <command>
```

To view logs:
```bash
docker-compose logs -f
```

