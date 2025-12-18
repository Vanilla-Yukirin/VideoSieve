#!/bin/bash
set -e

echo "====================================="
echo "VideoSieve Installation Validation"
echo "====================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
if [ $? -eq 0 ]; then
    echo "✓ Python 3 is installed"
else
    echo "✗ Python 3 is not installed"
    exit 1
fi

# Check Node version
echo ""
echo "Checking Node.js version..."
node --version
if [ $? -eq 0 ]; then
    echo "✓ Node.js is installed"
else
    echo "✗ Node.js is not installed"
    exit 1
fi

# Check FFmpeg
echo ""
echo "Checking FFmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "✓ FFmpeg is installed"
else
    echo "⚠ FFmpeg is not installed (required for audio processing)"
fi

# Check backend structure
echo ""
echo "Checking backend structure..."
if [ -f "backend/app/main.py" ] && [ -f "backend/requirements.txt" ]; then
    echo "✓ Backend files present"
else
    echo "✗ Backend files missing"
    exit 1
fi

# Check frontend structure
echo ""
echo "Checking frontend structure..."
if [ -f "frontend/package.json" ] && [ -f "frontend/src/app/page.tsx" ]; then
    echo "✓ Frontend files present"
else
    echo "✗ Frontend files missing"
    exit 1
fi

# Check Docker files
echo ""
echo "Checking Docker configuration..."
if [ -f "docker-compose.yml" ] && [ -f "backend/Dockerfile" ] && [ -f "frontend/Dockerfile" ]; then
    echo "✓ Docker configuration present"
else
    echo "✗ Docker configuration missing"
    exit 1
fi

# Check documentation
echo ""
echo "Checking documentation..."
if [ -f "docs/ARCHITECTURE.md" ] && [ -f "docs/API.md" ] && [ -f "docs/DEPLOYMENT.md" ]; then
    echo "✓ Documentation complete"
else
    echo "✗ Documentation missing"
    exit 1
fi

echo ""
echo "====================================="
echo "✓ All validation checks passed!"
echo "====================================="
echo ""
echo "Next steps:"
echo "1. Backend: cd backend && pip install -r requirements.txt"
echo "2. Frontend: cd frontend && npm install"
echo "3. Configure .env files"
echo "4. Start services (see README.md)"
