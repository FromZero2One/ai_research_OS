#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend"
echo "Installing frontend dependencies..."
npm install --legacy-peer-deps 2>&1 | tail -5
echo "Frontend install complete"
