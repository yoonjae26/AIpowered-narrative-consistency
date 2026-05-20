#!/bin/bash

echo "🚀 Setting up NarrativeOS..."

# Check Python version
echo "Checking Python version..."
python3 --version

# Install Poetry if not installed
if ! command -v poetry &> /dev/null; then
    echo "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
fi

# Install dependencies
echo "Installing Python dependencies..."
poetry install

# Copy environment file
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env with your actual configuration"
fi

# Start Docker services
echo "Starting Docker services..."
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d postgres redis chromadb

echo "Waiting for services to be ready..."
sleep 10

# Run migrations (when implemented)
# poetry run alembic upgrade head

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env with your API keys"
echo "2. Run 'make dev' to start the development server"
echo "3. Visit http://localhost:8001/docs for API documentation"
