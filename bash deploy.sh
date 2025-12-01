PROJECT_ID="adept-might-479811-q5"

echo "🔨 Building..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/bioprocess-app

echo "🚀 Deploying..."
gcloud run deploy bioprocess-app \
  --image gcr.io/$PROJECT_ID/bioprocess-app \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --set-env-vars GOOGLE_API_KEY="${GOOGLE_API_KEY}" 

echo "🎉 Done!"