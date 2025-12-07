#!/bin/bash
# USAGE: API_KEY="your_key" ./deploy.sh

# Configuration
PROJECT_ID="adept-might-479811-q5"
REGION="europe-west1"
IMAGE_NAME="gcr.io/$PROJECT_ID/bioprocess-app"

# Safety Check
if [ -z "$API_KEY" ]; then
  echo "❌ Error: API_KEY is not set."
  echo "Usage: API_KEY='your_key' ./deploy.sh"
  exit 1
fi

echo "🔨 Building Container..."
gcloud builds submit --tag $IMAGE_NAME

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy bioprocess-app \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --set-env-vars GOOGLE_API_KEY="$API_KEY",GOOGLE_CLOUD_PROJECT="$PROJECT_ID"

echo "🎉 Done!"